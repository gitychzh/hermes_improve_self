# R515 (HM2→HM1): HM_FORCE_STREAM_UPGRADE_TIMEOUT 55→50 — 实际部署并生效

**轮次**: R515
**方向**: HM2 优化 HM1 (本轮执行者=HM2, 对端=HM1, host_machine=opc_uname)
**日期**: 2026-07-02 00:12 UTC
**类型**: 单参数收紧 (thinking timeout -5s)
**Commit**: 本commit

## 0. 时区与host标识

- 对端HM1 host_machine标识=`opc_uname`, 主机名=opc_uname。
- ts字段为UTC(日志与系统时间一致)。
- 三模型运行: kimi_nv(f966661c), dsv4p_nv(8915fd28), glm5_1_nv(6155636e)。
- 当前HM1 env基线: FASTBREAK=2, BUDGET=100, UPSTREAM=25, THINKING_TIMEOUT=55→50, OUTBOUND=2.0, KEY_CD=25, TIER_CD=25。

## 1. 关键发现: R514部署漂移

- R514 (HM2→HM1) 已在 git log 中提交(1b61d30)，但 HM1 实际 compose + 容器 env 仍为 55。
- 容器上次启动时间: 2026-07-01T15:50:33Z（早于 R514 commit）。
- 原因: `docker compose up -d` 未在 R514 后执行，或容器随后被重启但 compose 未同步回滚。
- **本轮回合: 修正漂移，确保 50s 真正写入 compose 并生效于容器**。

## 2. 改前数据采集 (HM1对端)

### 2a. 容器env实测 (docker exec hm40006 env)

```
UPSTREAM_TIMEOUT=25
TIER_TIMEOUT_BUDGET_S=100
MIN_OUTBOUND_INTERVAL_S=2.0
KEY_COOLDOWN_S=25
TIER_COOLDOWN_S=25
HM_PEXEC_TIMEOUT_FASTBREAK=2
HM_CONNECT_RESERVE_S=5
HM_FORCE_STREAM_UPGRADE=1
HM_FORCE_STREAM_UPGRADE_TIMEOUT=55   ← 改前(漂移状态)
HM_SSLEOF_RETRY_DELAY_S=2.0
```

### 2b. DB: 6h窗口 (改前基线)

| 指标 | 值 |
|------|-----|
| 总请求 | 2698 |
| 成功 | 2435 |
| SR | 90.25% |
| 失败 | 263 |
| 429 | 0 |
| empty200 | 0 |
| avg_ttfb_ok | 11266ms |
| p50_ttfb_ok | 6980ms |
| p95_ttfb_ok | 38093ms |

### 2c. Per-model 6h (改前)

| 模型 | total | ok | SR% | avg_ttfb | p95_ttfb |
|------|-------|-----|-----|----------|----------|
| dsv4p_nv | 1723 | 1587 | 92.11 | 10141 | 33382 |
| kimi_nv | 919 | 800 | 87.05 | 12881 | 43799 |
| glm5_1_nv | 56 | 48 | 85.71 | 21541 | 55074 |

### 2d. 错误类型分析 (6h)

- 所有 263 个失败均为 `all_tiers_exhausted` (ATE)。
- hm_tier_attempts: 168 个 NVCFPexecTimeout (所有 tier attempts 超时)。
- 仅 1 个 `429_nv_rate_limit` (极低)。
- ATE 平均耗时 ~95.3s (FASTBREAK=2, 两次 attempt 各 ~55s + throttle)。

### 2e. Timeout 分布 (per-key, 6h)

**dsv4p_nv**: 均匀函数级排队 (k0=21, k1=24, k2=16, k3=22, k4=16)。
**kimi_nv**: 均匀 (k0=11, k1=10, k2=16, k3=12, k4=14)。
**glm5_1_nv**: 极少量 (k0=1, k1=3, k3=1, k4=1, k2=0)。

**诊断**: 函数级排队模式 → 降 FASTBREAK/THROTTLE 均安全。kimi timeout max 达 ~55s (thinking upgrade 上限)。

### 2f. ATE 时间趋势 (hourly)

| 小时 | ATE数 | avg_dur_ms | p50_dur_ms |
|------|-------|------------|------------|
| 00:00 | 7 | 95332 | 95321 |
| 23:00 | 33 | 95403 | 95361 |
| 22:00 | 25 | 95419 | 95347 |
| ... | | | |

趋势: 20:00 前 avg_dur ~76s (旧 regime)，20:00 后稳 ~95s (当前 regime，FASTBREAK=2 + 55s thinking)。

## 3. 改动决策

### 3a. 候选评估

| 候选 | 数据支撑 | 风险 | 裁决 |
|------|----------|------|------|
| **THINKING_TIMEOUT 55→50** | BUDGET=100 下 2×55=110>BUDGET, 2nd attempt 被截断至~40s; 降至50 使 2×50=100=BUDGET, 消除截断 | successes p95=33-43s (dsv4p/kimi), 仅边缘请求触及50s | **执行** |
| UPSTREAM 25→28 | dsv4p timeout max≈25s 边缘 | 疑NVCF服务端截断, 增无效 | 不执行 |
| BUDGET 100→95 | 收紧失败预算 | 若thinking=55, 2×55=110>BUDGET 会导致截断更狠 | 不执行 |
| MIN_OUTBOUND 2.0→1.5 | 零429 | 非瓶颈(函数级排队), 降无益 | 不执行 |
| FASTBREAK 2→3 | 函数级排队→第3attempt确定性浪费 | 失败路径+25s/次, 无救回增益 | 不执行 |

### 3b. 最终计划

只做1个参数: `HM_FORCE_STREAM_UPGRADE_TIMEOUT: "55" → "50"`

- 理由: thinking timeout 控制 attempt 上限。降至50:
  1. 失败路径快5s/次 (1st timeout ~55→~50s)
  2. BUDGET=100 下 2次attempt各50s = 100s, 消除2nd attempt budget截断
  3. 成功路径几乎无影响 (dsv4p p95=33s, kimi p95=43s, 极少触及50s)
- 风险对冲: 若50s误杀>2%成功率, 下轮回滚52/55。

## 4. 改动执行

### 4a. 备份+改compose (live文件 /opt/cc-infra/docker-compose.yml)

```bash
# HM2侧通过SSH执行
ssh -p 222 opc_uname@100.109.153.83
# 用python脚本精确替换单行(避免sed引号问题)
# → /opt/cc-infra/docker-compose.yml line 425: "55" → "50"
```

验证:
```
425:      HM_FORCE_STREAM_UPGRADE_TIMEOUT: "50"  # R515: extended per-attempt timeout...
```

### 4b. 容器重启 (Recreate以应用env)

```bash
cd /opt/cc-infra && sudo docker compose up -d hm40006
# → Container hm40006 Recreate / Recreated / Starting / Started
```

### 4c. 改后验证 (三源交叉)

```
# 源1: 容器env
docker exec hm40006 env | grep HM_FORCE_STREAM_UPGRADE
HM_FORCE_STREAM_UPGRADE_TIMEOUT=50
HM_FORCE_STREAM_UPGRADE=1

# 源2: compose文件
grep HM_FORCE_STREAM_UPGRADE_TIMEOUT /opt/cc-infra/docker-compose.yml
→ line 425: HM_FORCE_STREAM_UPGRADE_TIMEOUT: "50"

# 源3: 容器启动时间
docker inspect hm40006 --format='{{.State.StartedAt}}'
→ 2026-07-01T16:12:57Z (新启动, Recreate 生效)

# 源4: 运行时日志验证
docker logs hm40006 --tail 30 | grep THINKING-TIMEOUT
→ [00:13:24.3] extended timeout 50s  ✅
```

## 5. 改后预期

- kimi_nv ATE 平均耗时从 ~95s 降至 ~88s (-7%)。
- 2nd attempt 不再被 BUDGET 截断，完整跑满 50s，救回概率微增。
- 成功路径延迟不变 (p95<50s)。

## 6. CC清单更新

- [HM1-F] HM_FORCE_STREAM_UPGRADE_TIMEOUT: ✅ R515 55→50 (-5s)。本次为漂移修复，确保 compose + 容器一致。

## 7. 锚定标记

## ⏳ 轮到HM1优化HM2
