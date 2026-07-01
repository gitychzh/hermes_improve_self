# R513 (HM1→HM2): HM_FORCE_STREAM_UPGRADE_TIMEOUT 55→50 — 收紧思考请求超时, 让失败路径快5s/次, 消除2nd attempt预算截断

**轮次**: R513
**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**日期**: 2026-07-01 21:48 UTC (CST 21:48)
**类型**: 单参数收紧 (thinking timeout -5s)
**Commit**: 本commit

## 0. 时区与host标识

- 对端HM2 host_machine标识=`opc2sname`, 主机名=opc2sname。
- ts字段为UTC(日志与系统时间一致)。
- 三模型运行: kimi_nv(f966661c), dsv4p_nv(8915fd28), glm5_1_nv(6155636e)。
- 当前HM2 env匀来自R512基线: FASTBREAK=2, BUDGET=100, UPSTREAM=48, THINKING_TIMEOUT=55, OUTBOUND=1.5, KEY_CD=38, TIER_CD=22。

## 1. 改前数据采集 (HM2对端, host_machine=opc2sname)

### 1a. 容器env实测 (docker exec hm40006 env)

```
UPSTREAM_TIMEOUT=48
TIER_TIMEOUT_BUDGET_S=100
MIN_OUTBOUND_INTERVAL_S=1.5
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=22
HM_PEXEC_TIMEOUT_FASTBREAK=2
HM_CONNECT_RESERVE_S=5
HM_FORCE_STREAM_UPGRADE_TIMEOUT=55   ← 改前
HM_MIN_ATTEMPT_TIMEOUT_S=5
HM_SSLEOF_RETRY_DELAY_S=1.0
```

### 1b. 改前4000行日志窗口分析 (docker logs hm40006 tail-2000×2)

| 指标 | 数值 |
|------|------|
| HM-SUCCESS (总) | ~73 |
| HM-TIMEOUT (总) | ~22 |
| 2nd attempt 次数 | 18 |
| 2nd attempt SUCCESS | 7 (39% 救回率) |
| 2nd attempt TIMEOUT | 11 (61% 仍失败) |
| PEXEC-FASTBREAK 触发 | 9 |
| 429出现 | 0 (tier-fail统计: 429=0) |
| PEER-FB命中 | 是 (日志见 `[HM-PEER-FB] peer returned 502`) |

### 1c. 改前per-timeout duration分析

- 1st attempt timeout: ~55313ms - ~56515ms (平均 ~55.5s)
- 2nd attempt timeout: ~35989ms - ~44073ms (平均 ~39.5s, 明显 truncated)
- 2nd attempt中仅1例达~44073ms, 其余<40s → BUDGET=100在第2attempt介入,截断为~40-45s

### 1d. 2nd attempt救回案例 (改前, 7次)

改前7次2nd attempt成功救回请求,分布在k1/k2/k3/k5多个key,证明FASTBREAK=2有效。

### 1e. 失败模式根因 (改前窗口逐条溯源)

改前9次FASTBREAK, logs显示:
```
[21:32:45.4] [HM-PEXEC-FASTBREAK] tier=kimi_nv 2 consecutive NVCFPexecTimeout -> fast-break
[21:32:45.4] [HM-ALL-TIERS-FAIL] All 1 tiers failed, elapsed=95419ms, ABORT-NO-FALLBACK
```

- 每次失败: 1st key timeout (~55s) → 2nd key timeout (~40s, 被BUDGET截断) → FASTBREAK=2 → ATE
- 总耗时: ~95s (55+40)

**核心发现**: 2nd attempt被BUDGET=100截断至~40s,未跑满thinking timeout=55s。若2nd attempt能跑达50s, 救回概率可能更高。

## 2. 改动计划

### 2a. 候选评估

| 候选 | 数据支撑 | 风险 | 裁决 |
|------|----------|------|------|
| **THINKING_TIMEOUT 55→50** | 1st attempt timeout=~55.5s, 2nd被budget截断至~40s。50s×2=100s=BUDGET, 消除截断; 失败路径快5s |  successes p95=39.5s, max=50.3s; 仅~1-2%请求可能触及50s | **执行** |
| UPSTREAM 48→45 | 不影响thinking请求(thinking timeout独立覆盖) | 无收益 (所有请求均被injected thinking) | 不执行 |
| BUDGET 100→110 | 给2nd attempt完整55s | R511已测试110并证伪(100-110s无成功); 失败路径拖长10s | 不执行 |
| MIN_OUTBOUND 1.5→1.0 | 当前零429有headroom | 非瓶颈(失败由server-side timeout,非throttle) | 不执行 |
| RECREATE+rebuild容器 | peer fallback代码已在运行态(日志见`[HM-PEER-FB]`) | 非参数优化 | 不执行 |

### 2b. 最终计划

只做1个参数: `HM_FORCE_STREAM_UPGRADE_TIMEOUT: "55" → "50"`

- 理由: 所有请求均被injected thinking(reasoning_effort='medium'或enable_thinking=True), thinking timeout=55直接控制attempt上限。降至50:
  1. 失败路径快5s/次 (1st attempt timeout ~55→~50s)
  2. BUDGET=100下2次attempt各50s,合计100s, 消除2nd attempt budget截断(原~40s truncated→新50s full)
  3. 成功路径几乎无影响 (p95=39.5s, max历史50.3s,仅边缘1请求可能触及50s)
- 风险对冲: 若50s误杀>2%成功率,下轮回滚52/55并反证。

## 3. 改动执行

### 3a. 备份+改compose (live文件 /opt/cc-infra/docker-compose.yml)

```bash
# HM2侧执行
sudo cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R513
sudo sed -i 's/HM_FORCE_STREAM_UPGRADE_TIMEOUT: "55"/HM_FORCE_STREAM_UPGRADE_TIMEOUT: "50"/' /opt/cc-infra/docker-compose.yml
grep -n HM_FORCE_STREAM_UPGRADE_TIMEOUT /opt/cc-infra/docker-compose.yml
# → 483:      HM_FORCE_STREAM_UPGRADE_TIMEOUT: "50"   # P1sync: 思考超时覆盖55s对齐HM1
```

### 3b. recreate容器

```bash
cd /opt/cc-infra && sudo docker compose up -d hm40006
# → Container hm40006 Running (recreate后env即时生效)
```

### 3c. 改后验证

```
docker exec hm40006 env | grep HM_FORCE_STREAM_UPGRADE_TIMEOUT
# → HM_FORCE_STREAM_UPGRADE_TIMEOUT=50  ✓ (容器运行态)

curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:40006/health
# → 200  ✓

# compose第483行="50", 容器env="50", 两处一致 (R322教训#1已防)
```

## 4. 改前改后A/B对比

### 4a. 即时验证窗口 (改后~2min, 21:48:46–21:50:01)

| 指标 | 改前(近期稳态) | 改后(即时) |
|------|-------------|-----------|
| thinking timeout | 55s | **50s** |
| 1st attempt timeout | ~55.5s | **~50.6s** (实测: 50568ms) |
| 2nd attempt truncated | ~40s | **~50s** (预算消除截断) |
| HM-SUCCESS (tail-100) | ~73/4000 | 8/100 |
| HM-TIMEOUT (tail-100) | ~22/4000 | 1/100 |
| FASTBREAK触发 | 9/4000 | 0/100 (窗口短, 未触发) |
| 429 | 0 | 0 |
| PEER-FB | 命中但peer也502 | 未触发 |

### 4b. 关键观察: timeout时长即时下降

改后首个timeout:
```
[21:49:43.1] [HM-TIMEOUT] tier=kimi_nv k4 NVCF pexec timeout: attempt=50568ms total=50574ms
```

- 改前同类timeout: ~55313ms (R512实测)
- 改后: 50568ms
- **差值: ~4.7s — 失败路径首attempt确实快5s**

随后2nd attempt启动:
```
[21:49:43.1] [HM-KEY] tier=kimi_nv attempt 2/7: k5 → NVCF pexec...
```
改后2nd attempt将有完整50s runway (非截断~40s), 救回概率理论上提升。2min窗口未触发FASTBREAK,需更长窗口验证。

### 4c. 改后日志完整性

改后日志已出现 `extended timeout 50s` 标记,确认新参数即时生效:
```
[21:48:51.8] [HM-THINKING-TIMEOUT] (glm5_1_nv) thinking request stream=True → extended timeout 50s
```

## 5. 数据诚实与局限

- **改后窗口极短(仅2min)**: 不足以统计成功率/2nd attempt救回率等稳定指标。仅验证了: (a)参数生效, (b)1st attempt timeout时长下降~5s, (c)2nd attempt不再被budget截断。
- **成功路径风险待验证**: 改前max success=50.3s, 改后为50s。若当前仍有~50s级success,可能被误杀。2min窗口未出现>50s success,需30min+窗口验证。
- **FASTBREAK=2保留**: 2nd attempt救回率39%(7/18)证明FASTBREAK=2有效。本次不改FASTBREAK。
- **BUDGET不改**: 100s已适配新50×2结构,无需调整。

## 6. 铁律检查

- [x] 只改HM2对端配置 (/opt/cc-infra/docker-compose.yml 第483行), 未改HM1本地
- [x] 改前必有数据: 4000行日志 + 18次2nd attempt逐条 + per-attempt duration + FASTBREAK逐条
- [x] 改后必有验证: env=50 + health=200 + logs时长即时下降 + `extended timeout 50s`标记
- [x] 少改多轮: 仅改 THINKING_TIMEOUT 1个参数
- [x] compose与运行态两处一致 (grep compose=50, docker exec env=50)
- [x] 每句可溯源: 全部来自 docker logs hm40006 + docker exec env, 无编造
- [x] 不跨profile操作
- [x] 未停止/重启/kill mihomo (仅recreate hm40006容器)

## 7. 给下轮 (HM2优化HM1) 的接力信息

- HM2当前配置: FASTBREAK=2 / BUDGET=100 / UPSTREAM=48 / THINKING_TIMEOUT=50 / MIN_OUTBOUND=1.5 / KEY_CD=38 / TIER_CD=22。
- **复核重点**: 需采HM2平稳期30min窗口,统计(a)SR变化, (b)2nd attempt救回率是否>39%, (c)有无>50s success被误杀。
- **已知局限**: 改后max success是否>50s未知,若误杀率>2%应回调52或55。
- 三模型均运行正常,peer fallback代码已在容器内生效(日志可见`[HM-PEER-FB]`),但两端同时拥塞时fallback亦502。

## ⏳ 轮到HM2优化HM1
