# R514 (HM2→HM1): HM_FORCE_STREAM_UPGRADE_TIMEOUT 55→50 — 收窄思考请求超时, 消除2nd attempt预算截断, 失败路径快5s/次

**轮次**: R514
**方向**: HM2 优化 HM1 (本轮执行者=HM2, 对端=HM1, host_machine=opc_uname)
**日期**: 2026-07-01 21:50 UTC (CST 21:50)
**类型**: 单参数收紧 (thinking timeout -5s)
**Commit**: 本commit

## 0. 时区与host标识

- 对端HM1 host_machine标识=`opc_uname`, 主机名=opc_uname。
- ts字段为UTC(日志与系统时间一致)。
- 三模型运行: kimi_nv(f966661c), dsv4p_nv(8915fd28), glm5_1_nv(6155636e)。
- 当前HM1 env基线: FASTBREAK=2, BUDGET=100, UPSTREAM=25, THINKING_TIMEOUT=55→50, OUTBOUND=2.0, KEY_CD=25, TIER_CD=25。

## 1. 改前数据采集 (HM1对端, host_machine=opc_uname)

### 1a. 容器env实测 (docker exec hm40006 env)

```
UPSTREAM_TIMEOUT=25
TIER_TIMEOUT_BUDGET_S=100
MIN_OUTBOUND_INTERVAL_S=2.0
KEY_COOLDOWN_S=25
TIER_COOLDOWN_S=25
HM_PEXEC_TIMEOUT_FASTBREAK=2
HM_CONNECT_RESERVE_S=5
HM_FORCE_STREAM_UPGRADE=1
HM_FORCE_STREAM_UPGRADE_TIMEOUT=55   ← 改前
HM_SSLEOF_RETRY_DELAY_S=2.0
```

### 1b. DB: 6h窗口 (改前基线)

| 指标 | 值 |
|------|-----|
| 总请求 | 2016 |
| 成功 | 1752 |
| SR | 86.90% |
| 失败 | 264 |
| 429 | 0 |
| empty200 | 0 (tier_attempts: dsv4p 18次) |
| avg_ttfb_ok | 12633ms |
| p50_ttfb_ok | 7456.5ms |
| p95_ttfb_ok | 40461ms |

### 1c. Per-model 6h (改前)

| 模型 | total | ok | SR% | avg_ttfb | p95_ttfb |
|------|-------|-----|-----|----------|----------|
| dsv4p_nv | 1248 | 1044 | 83.65 | 12841 | 39048 |
| kimi_nv | 712 | 660 | 92.70 | 11655 | 39297 |
| glm5_1_nv | 56 | 48 | 85.71 | 21541 | 55074 |

### 1d. Tier attempts timeout分布 (6h, 改前)

**dsv4p_nv**: 均匀函数级排队 (22-31次/key, avg≈25s, min=23.2s, max=27.2s)
**kimi_nv**: 均匀但max达55s (k0 max=55674ms, k2 max=56331ms, k4 max=55451ms)
**glm5_1_nv**: 少量timeout, max=55661ms

**诊断**: dsv4p超时紧聚25s边缘(上限27.2s), 疑NVCF函数级25s服务端截断; kimi双模式(25s常规+55s thinking upgrade), 55s超时由HM_FORCE_STREAM_UPGRADE_TIMEOUT控制。

### 1e. ATE分析 (改前窗口)

- kimi_nv ATE: 40个(有标签) + 13个(NULL标签) = 53个失败
- dsv4p_nv ATE: 3个(有标签) + 200个(NULL标签) ≈ 203个失败
- 典型kimi_nv ATE模式: 1st key timeout(~55s) → throttle(2s) → 2nd key timeout(~40s, 被BUDGET=100截断) → FASTBREAK=2 → ATE @ ~96s
- peer-fallback: 23次尝试HM2, 0次成功 (同函数级瓶颈穿透双机)

### 1f. 2nd attempt截断证据 (docker logs)

```
[21:45:20.7] HM-TIMEOUT tier=kimi_nv k2 total=55314ms (1st attempt, ~55s)
[21:46:00.8] HM-TIMEOUT tier=kimi_nv k3 total=40009ms (2nd attempt, ~40s, truncated by BUDGET)
[21:46:00.8] HM-PEXEC-FASTBREAK tier=kimi_nv 2 consecutive timeout -> break
```
**核心发现**: BUDGET=100下, 1st 55s + throttle 2s = 57s消耗, 2nd仅能跑43s即被预算截断, 未能达到完整thinking timeout=55s。

## 2. 改动计划

### 2a. 候选评估

| 候选 | 数据支撑 | 风险 | 裁决 |
|------|----------|------|------|
| **THINKING_TIMEOUT 55→50** | 2nd attempt被BUDGET截断至~40s; 50×2=100=BUDGET, 消除截断; 失败路径快5s | successes p95=39.3s (kimi), 仅边缘请求可能触及50s | **执行** |
| UPSTREAM 25→28 | dsv4p timeout max=27.2s, 可能救回边缘请求 | 疑NVCF服务端25s截断(非client socket), 增无效; dsv4p已83.7%SR | 不执行 |
| BUDGET 100→90 | 收紧失败预算 | 若thinking保持55, 2次55s=110>BUDGET, 会导致提前截断 | 不执行 |
| MIN_OUTBOUND 2.0→1.5 | 零429, 有headroom | 非瓶颈(失败由server-side timeout驱动) | 不执行 |
| FASTBREAK 2→3 | R513 HM2救回率39% | HM1函数级排队更均匀(22-31 vs HM2的分散), 第3key救回概率低; 失败路径+25s/次 | 不执行 |

### 2b. 最终计划

只做1个参数: `HM_FORCE_STREAM_UPGRADE_TIMEOUT: "55" → "50"`

- 理由: 所有thinking请求均被upgrade stream, thinking timeout=55直接控制attempt上限。降至50:
  1. 失败路径快5s/次 (1st timeout ~55→~50s)
  2. BUDGET=100下 2次attempt各50s = 100s, 消除2nd attempt budget截断(原~40s truncated→新50s full)
  3. 成功路径几乎无影响 (kimi p95=39.3s, dsv4p p95=39.0s, 仅边缘~1-2%请求可能触及50s)
- 风险对冲: 若50s误杀>2%成功率, 下轮回滚52/55并反证。

## 3. 改动执行

### 3a. 备份+改compose (live文件 /opt/cc-infra/docker-compose.yml)

```bash
# HM2侧通过SSH执行
ssh -p 222 opc_uname@100.109.153.83
sudo cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R514
sudo sed -i 's/HM_FORCE_STREAM_UPGRADE_TIMEOUT: "55"/HM_FORCE_STREAM_UPGRADE_TIMEOUT: "50"/' /opt/cc-infra/docker-compose.yml
grep -n HM_FORCE_STREAM_UPGRADE_TIMEOUT /opt/cc-infra/docker-compose.yml
# → 425:      HM_FORCE_STREAM_UPGRADE_TIMEOUT: "50"   # R514: thinking timeout 55→50
```

### 3b. 容器重启 (Recreate以应用env)

```bash
cd /opt/cc-infra && sudo docker compose up -d hm40006
# → Container hm40006 Recreate / Recreated / Starting / Started
```

**注意**: `docker compose restart` 不应用compose env变更, 必须用 `up -d` (R505发现)。

### 3c. 改后验证

```bash
docker exec hm40006 env | grep HM_FORCE_STREAM_UPGRADE
# 改后:
# HM_FORCE_STREAM_UPGRADE=1
# HM_FORCE_STREAM_UPGRADE_TIMEOUT=50
```

验证通过: compose与容器一致。

## 4. 改后基线 (后续HM1采集)

本轮改后应立即进入30min/6h观察窗口。预期:
- kimi_nv ATE平均耗时从~96s降至~88s (-8%)
- 2nd attempt救回概率可能微增 (因不再被budget截断)
- 成功路径延迟不变 (p95<50s)

## 5. CC清单更新

- [HM1-F] HM_FORCE_STREAM_UPGRADE_TIMEOUT: ✅ R514 55→50 (-5s)。P1sync HM1→HM2 (HM2 R513已执行同样优化), 双机对齐。

## 6. 锚定标记

## ⏳ 轮到HM1优化HM2
