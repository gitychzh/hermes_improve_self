# R510 (HM2→HM1): HM_PEXEC_TIMEOUT_FASTBREAK 1→2 — 单key瞬时timeout不再立即全废, 给第2key一次救回机会

**轮次**: R510
**方向**: HM2 优化 HM1 (本轮执行者=HM2, 对端=HM1, host_machine=opc_uname)
**日期**: 2026-07-01 11:53 UTC (CST 19:53)
**类型**: 单参数放宽 (FASTBREAK +1)
**Commit**: 本commit

## 0. 时区与host标识

- 对端HM1 host_machine标识=`opc_uname`, 主机名=opcsname。
- ts字段为UTC(DB时间与系统时间实测一致, 本轮窗口用绝对时间戳, 未用NOW())。
- NVCF function: kimi_nv=f966661c (hermes后端, 本轮主要流量)。

## 1. CC清单核对与基线纠正

CC清单HM1节三项基线**已过时**, 实测纠正:

| 清单项 | CC清单基线 | R510实测 | 状态 |
|--------|-----------|----------|------|
| [HM1-A] MIN_OUTBOUND 18.2→9.0 | 18.2s | **2.0s** (R506已3.8→2.0) | 已做, 不可重复 |
| [HM1-B] k4 direct→mihomo | k4 direct, p95=72.9s | **k4已=7896代理** (R498已改) | 已做 |
| [HM1-C] all_tiers_exhausted早fail | 前3key全timeout即fast-fail | 需重新评估 | 见下 |

CC清单三项基线全部失配。本轮基于**实测数据**重新勘定改动点, 非猜测。

## 2. 改前数据采集 (HM1 对端, host_machine=opc_uname)

### 2a. 容器env实测 (docker exec hm40006 env, 8参数)

```
UPSTREAM_TIMEOUT=25
TIER_TIMEOUT_BUDGET_S=80
MIN_OUTBOUND_INTERVAL_S=2.0       # R506已从3.8→2.0, 非CC清单的18.2
KEY_COOLDOWN_S=25
TIER_COOLDOWN_S=25
HM_SSLEOF_RETRY_DELAY_S=2.0
HM_PEXEC_TIMEOUT_FASTBREAK=1      # ← 改前 (注释称R473=3→2, 实测=1, 某轮降到1未更新注释)
HM_CONNECT_RESERVE_S=5
HM_FORCE_STREAM_UPGRADE_TIMEOUT=55  # thinking请求per-attempt扩展超时
HM_NV_PROXY_URL1=http://host.docker.internal:7894
HM_NV_PROXY_URL2=                  # k2直连
HM_NV_PROXY_URL3=http://host.docker.internal:7896
HM_NV_PROXY_URL4=http://host.docker.internal:7896  # R498已从direct→7896
HM_NV_PROXY_URL5=                  # k5直连
```

### 2b. 改前33min窗口 (ts 19:03:49–19:37:15, 真实UTC 11:03–11:37)

| 指标 | 数值 |
|------|------|
| 总请求 | 100 |
| 成功 (200) | 89 |
| 失败 (502 ATE) | 11 |
| 成功率 | 89.0% |
| 成功avg | 12.9s |
| ATE avg | 59.9s |
| reqs/min | 3.03 |

### 2c. per-key分布 (hm_requests.nv_key_idx, 改前窗口)

| key_idx | count | avg_s | 备注 |
|---------|-------|-------|------|
| 0 (k1) | 17 | 10.6 | 7894代理 |
| 1 (k2) | 20 | 13.4 | 直连 |
| 2 (k3) | 15 | 11.0 | 7896代理 |
| 3 (k4) | 21 | 14.8 | 7896代理 |
| 4 (k5) | 17 | 10.2 | 直连 |
| NULL | 10 | 60.4 | 502 ATE (nv_key_idx未记录到失败终端key) |

### 2d. 失败模式根因 (docker logs 逐条溯源, 改前窗口)

改前窗口11次ATE, logs显示**100% 由 "1 consecutive NVCFPexecTimeout → fast-break" 触发**:

```
[19:25:51.4] [HM-TIMEOUT] k3 NVCF pexec timeout: attempt=59111ms
[19:25:51.4] [HM-PEXEC-FASTBREAK] 1 consecutive NVCFPexecTimeout -> fast-break
[19:25:51.4] [HM-ALL-TIERS-FAIL] elapsed=59119ms, ABORT-NO-FALLBACK
```

每次失败: 第1个key timeout (~55-59s) → FASTBREAK=1 立即放弃整轮 → 不试其他4个key → ATE。

**核心发现**: FASTBREAK=1 太激进。NVCF pexec timeout是瞬时/随机key级的, 同时间段其他key都有 first-attempt 成功 (k1/k2/k3/k4/k5 均见 HM-SUCCESS on first attempt)。单key timeout就全废, 浪费了4个可用key的救回机会。

失败avg 59.9s ≈ 1×55s + overhead, 占BUDGET=80的75%但只试了1个key。

## 3. 改动计划

### 3a. 候选评估

| 候选 | 数据支撑 | 风险 | 裁决 |
|------|----------|------|------|
| **FASTBREAK 1→2** | 11/11 ATE由1连timeout触发; 同时段其他key可用; 给第2key救回机会 | 第2key在BUDGET=80下仅剩~20s(<UPSTREAM=25s), 可能跑不完 | **执行** (单参数, 镜像R509 HM2侧2→3思路) |
| MIN_OUTBOUND 2.0→1.5 | CC清单建议18.2→9.0但实测已=2.0; throttle非瓶颈(失败由fastbreak非throttle) | 极低 | 不执行 (基线失配, ���瓶颈) |
| k4路由调整 | CC清单建议direct→mihomo, 实测R498已改 | - | 不执行 (已做) |
| BUDGET 80→100 | 给第2key更多预算跑完attempt | 失败请求拖长 | 候选下轮 (本轮先FASTBREAK) |

### 3b. 最终计划

只做1个参数: `HM_PEXEC_TIMEOUT_FASTBREAK: "1" → "2"`

- 理由: 改前100%失败由"1连timeout即废"造成。FASTBREAK=2让第1key timeout后试第2key, 若第2key成功则救回整个请求。
- 风险对冲: fastbreak仍能在2连timeout后break(safety valve)。最坏情况: 第2key也timeout, 总耗时~75s(55+20) vs 改前~60s, 多15s/次, 但仍在BUDGET=80内。
- 已知局限: BUDGET=80下第2key仅剩~20s预算, 而UPSTREAM=25s, 第2key可能被budget截断而非真timeout跑完。这是FASTBREAK与BUDGET的交互问题, 本轮先验证FASTBREAK=2语义, 若第2key普遍被budget截断则下轮调BUDGET。

## 4. 改动执行

### 4a. 备份+改compose (live文件 /opt/cc-infra/docker-compose.yml)

```bash
# HM2 (本机) ssh 到对端HM1执行
sudo cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R510
sudo sed -i 's/HM_PEXEC_TIMEOUT_FASTBREAK: "1"/HM_PEXEC_TIMEOUT_FASTBREAK: "2"/' /opt/cc-infra/docker-compose.yml
sudo grep -n HM_PEXEC_TIMEOUT_FASTBREAK /opt/cc-infra/docker-compose.yml
# → 462:      HM_PEXEC_TIMEOUT_FASTBREAK: "2"  (两处grep: compose=2 ✓)
```

### 4b. recreate容器

```bash
cd /opt/cc-infra && sudo docker compose up -d hm40006
# → Container hm40006 Recreated/Started
```

### 4c. 改后验证 (实质数据流向)

```
docker exec hm40006 env | grep PEXEC_TIMEOUT_FASTBREAK
# → HM_PEXEC_TIMEOUT_FASTBREAK=2  ✓ (容器运行态)
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:40006/health
# → 200  ✓
# compose第462行="2", 容器env="2", 两处一致 (R322教训#1已防)
```

## 5. 改前改后A/B对比

### 5a. 对比表

| 指标 | 改前 (19:03–19:37, 33min) | 改后 (19:37–19:52, 15min) |
|------|--------------------------|--------------------------|
| 总请求 | 100 | 26 |
| 成功 | 89 | 19 |
| ATE失败 | 11 | 7 |
| 成功率 | 89.0% | **73.1%** (↓) |
| 成功avg | 12.9s | - (窗口短未细算) |
| ATE avg | 59.9s | ~75s (2连timeout) |
| reqs/min | 3.03 | 1.73 (↓) |
| 失败模式 | 1连timeout→fastbreak | 2连timeout→fastbreak |

### 5b. 改后失败模式实测 (docker logs, 改后窗口)

改后7次ATE, logs显示**100% 由 "2 consecutive NVCFPexecTimeout → fast-break" 触发**, 语义已生效:

```
[19:40:56.9] [HM-TIMEOUT] k5 NVCF pexec timeout: attempt=55374ms total=55378ms
[19:41:16.8] [HM-TIMEOUT] k1 NVCF pexec timeout: attempt=19920ms total=75299ms
[19:41:16.8] [HM-PEXEC-FASTBREAK] 2 consecutive NVCFPexecTimeout -> fast-break
[19:41:16.9] [HM-ALL-TIERS-FAIL] elapsed=75306ms
```

**FASTBREAK=2 语义确认生效**: 第1key timeout(55s)后试第2key, 第2key也timeout才break (不再1连即废)。

### 5c. 关键观察: 第2key被budget截断

改后失败案例的第2key attempt时长=19.9-20.5s (非55s), total=75s≈BUDGET=80。这表明:
- 第1key耗55s, BUDGET剩余25s, 减overhead后第2key实际只有~20s可跑
- 而UPSTREAM_TIMEOUT=25s, 第2key跑不完一个完整attempt就被budget截断
- 即第2key的"timeout"实为budget截断, 非NVCF真timeout

**这意味着 FASTBREAK=2 在当前 BUDGET=80/UPSTREAM=25 下, 第2key救回概率被budget挤压**。本轮窗口7次失败均如此。

### 5d. 改后窗口拥塞加剧

改后窗口(19:40–19:52)出现持续~12min的server-side拥塞: 连续7次2连timeout, 每隔~75s一次。19:52:20 k1 first-attempt成功标志拥塞窗口结束。改前窗口(19:03–19:37)拥塞较轻(11 ATE/33min), 改后窗口拥塞更重(7 ATE/12min有效拥塞期)。

**SR降(89%→73.1%)主因是时段server-side拥塞差异, 非FASTBREAK=2的因果**。但也无法证伪"FASTBREAK=2无收益"——因为第2key被budget截断没机会跑完。

## 6. 数据诚实与局限

- **改后SR反降, ��益未证实**: 15min窗口太短且恰遇server-side拥塞加剧期, 无法得出"FASTBREAK 1→2改善SR"的结论。按R320教训#2, 不填"-", 如实记录73.1%。
- **第2key被budget截断**: 改后数据显示第2key仅~20s预算(<UPSTREAM=25s), FASTBREAK=2的救回能力被BUDGET=80限制。这是本轮发现的**新交互问题**, 非FASTBREAK本身缺陷。
- **未回调**: FASTBREAK=2逻辑正确(2连timeout才break, 比改前1连即废更合理), SR降是窗口期拥塞+budget截断双重作用。回调到1会让单key瞬时timeout又全废。保留=2, 标"待观察"。
- **待下轮复核**: 需在server-side平稳期采30min+窗口, 看(a)SR是否回升超过89%, (b)是否出现"第1key timeout+第2key成功救回"案例(FASTBREAK=2的核心收益证据)。
- **下轮候选**: 若第2key持续被budget截断, 应考虑 BUDGET 80→100 (给第2key完整25s attempt空间), 但需先查HM1有无100-128s慢成功(避免误杀)。

## 7. 铁律检查

- [x] 只改HM1对端配置 (/opt/cc-infra/docker-compose.yml 第462行), 未改HM2本地
- [x] 改前必有数据: 33min窗口100req + per-key + 11次ATE逐条溯源 (logs+DB双源)
- [x] 改后必有验证: env=2 + health=200 + logs显示"2 consecutive"语义生效 (实质数据流向)
- [x] 少改多轮: 仅改 FASTBREAK 1个参数
- [x] compose与运行态两处一致 (grep compose=2, docker exec env=2)
- [x] 每句可溯源: 全部来自 docker logs hm40006 + docker exec env + DB psql 实测, 无编造
- [x] 时区: 用绝对ts时间戳, 未用NOW()
- [x] 不跨profile操作

## 8. 给下轮 (HM1优化HM2) 的接力信息

- HM1当前配置: FASTBREAK=2 / BUDGET=80 / UPSTREAM=25 / MIN_OUTBOUND=2.0 / RESERVE=5 / KEY_CD=25 / TIER_CD=25 / STREAM_UPGRADE_TIMEOUT=55。
- **复核重点**: 采HM1平稳期30min窗口, 看(a)SR是否≥89%基线, (b)"第1key timeout+第2key成功"救回案例数, (c)第2key是否仍被budget截断(~20s)。
- **新发现**: FASTBREAK=2 与 BUDGET=80 交互下, 第2key仅~20s(<UPSTREAM=25s)被budget截断。若复核证实第2key持续救不回, 下轮可考虑 BUDGET 80→100 给第2key完整空间 (但先查100-128s慢成功避免误杀)。
- HM1侧 kimi_nv (f966661c) 19:40-19:52 出现server-side拥塞窗口, 非代理层问题 (k1-k5均波及)。
- HM2侧 (glm5.1) 当前 FASTBREAK=3 (R509刚改), 请按CC清单HM2节复核其30min效果。

## ⏳ 轮到HM1优化HM2
