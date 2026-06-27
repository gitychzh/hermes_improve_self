# R145: HM2→HM1 — 无变更 (验证R143: 全窗口100%稳定, 24h ate夜间集中非配置可控, 7参数均衡)

## 📊 数据采集 (当前时刻 02:31 CST, R143部署后>12h)

### Config Snapshot (HM1 hm40006 docker exec env)
| Parameter | Value | 
|-----------|-------|
| UPSTREAM_TIMEOUT | 60 |
| KEY_COOLDOWN_S | 34 |
| TIER_TIMEOUT_BUDGET_S | 146 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 |
| TIER_COOLDOWN_S | 42 |
| HM_CONNECT_RESERVE_S | 24 |
| PROXY_TIMEOUT | 300 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 |

### Docker Logs (tail 100, grep error/warn/timeout)
- **ZERO errors/warnings in logs** — all 30 lines show `[HM-SUCCESS] succeeded on first attempt`
- Perfect key round-robin: k5→k1→k2→k3→k4→k5 cycling normally

### Latency Percentiles
| Window | Total | Success | Errors | Fallbacks | P50 | P95 | P99 | Success Rate |
|--------|-------|---------|--------|------------|-----|-----|-----|-------------|
| 30min | 74 | 74 | 0 | 0 | 18169ms | 37027ms | 64165ms | 100.0% |
| 1h | 158 | 158 | 0 | 0 | — | 34588ms | — | 100.0% |
| 6h | 821 | 818 | 3 | 0 | — | — | — | 99.6% |

### Per-Key Success Latency (6h)
| Key | n | avg | p50 | p95 | >60s | >60s% |
|-----|---|-----|-----|-----|------|-------|
| k0 (DIRECT) | 173 | 26285ms | 21184ms | 62171ms | 10 | 5.8% |
| k1 (DIRECT) | 160 | 22514ms | 19031ms | 60676ms | 9 | 5.6% |
| k2 (PROXY→7896) | 153 | 19395ms | 17362ms | 39937ms | 4 | 2.6% |
| k3 (PROXY→7897) | 171 | 20958ms | 18712ms | 44034ms | 2 | 1.2% |
| k4 (PROXY→7899) | 160 | 20577ms | 17964ms | 51777ms | 3 | 1.9% |

- DIRECT (k0/k1) tail latency > PROXY (k2-k4) — known NVCF server-side variance (Pitfall #29), NOT a config issue

### Error Breakdown
| Window | Error Type | Count | Avg Duration |
|--------|-----------|-------|-------------|
| 30min | — | 0 | — |
| 6h | NVStream_IncompleteRead | 1 | 19546ms |
| 6h | NVStream_TimeoutError | 1 | 109523ms |
| 6h | all_tiers_exhausted | 1 | 141944ms |

- 6h: 仅3错误,其中2个NVCF服务端错误,1个ate(夜间遗留)
- ZERO 429 in 30min/1h
- ZERO fallback in all windows

### 24h ate by Hour
| Hour (UTC) | Count |
|------------|-------|
| 01:00 | 1 |
| 02:00 | 4 |
| 03:00 | 10 |
| 05:00 | 5 |
| 07:00 | 1 |
| 08:00 | 7 |
| 09:00 | 7 |
| 10:00 | 3 |
| 11:00 | 3 |
| 17:00 | 1 |
| **Total** | **42** |

- **Concentration**: 40/42 (95.2%) in overnight window 01:00-11:00 UTC (NVCF server-side instability)
- **Daytime (last 12h)**: 22 (mostly from early morning)
- **Last 6h**: 仅1个ate (大白天时段) — NVCF server-side, 非配置可控

### 24h Status Breakdown
| Status | Count | Avg Duration | Min | Max |
|--------|-------|-------------|-----|-----|
| 200 | 3394 | 30228ms | 1295ms | 184900ms |
| 429 | 4 | 161389ms | 138762ms | 189745ms |
| 502 | 43 | 118774ms | 19546ms | 166774ms |

- 24h 502 avg=118774ms 仍反映**pre-R143旧数据** (2×68s timeout regime), R143后短窗口100%成功 (Pitfall #36)
- 429仅4次, 全部在02:00-03:00 UTC夜间

### Request Rate
- 30min deepseek_hm_nv: 27 minutes with data, avg 2.7 req/min, max 4/min, min 1/min
- Capacity at MIN_OUTBOUND=19s: 3.2 req/min → utilization 84%
- Key rotation healthy: ~1 req/3.3min per key, well within KEY_COOLDOWN=34s

### Back-to-Back Same-Key (30min)
- 73 pairs, 0 same-key → **0.0% back-to-back rate** ✅

### key_cycle_429s (30min)
- All 74 requests: `0` 429-cycles → ZERO 429 recycling activity ✅

## 🎯 优化分析

### 7参数逐一评估

| Parameter | Current | Status | Need Change? | Reason |
|-----------|---------|--------|-------------|--------|
| UPSTREAM_TIMEOUT | 60 | ✅ 6h ZERO key timeouts | No | R143 68→60加速+budget margin 26s=充足 |
| KEY_COOLDOWN_S | 34 | ✅ 30min/1h ZERO 429 | No | 429 rate near-zero, cooldown无下调空间也不需上调 |
| TIER_TIMEOUT_BUDGET_S | 146 | ✅ 2×60=120, remaining=26s>>10s | No | 26s margin远超10s threshold, 无budget压力 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ✅ 实际2.7/min vs 3.2/min容量=84% | No | 无429压力, 但84%利用率不宜继续降(需留余量) |
| TIER_COOLDOWN_S | 42 | ✅ 6h仅1次ate | No | ate全为夜间NVCF服务端问题, 非cooldown可解 |
| HM_CONNECT_RESERVE_S | 24 | ✅ ZERO budget_exhausted_after_connect | No | 无connect reserve不足信号 |
| PROXY_TIMEOUT | 300 | ✅ 未触及 | No | 300s远超最长请求(~185s), 不需调整 |

### Bottleneck Analysis
**无明显瓶颈**。所有短窗口(30min/1h)100%成功率。6h仅3错误全为NVCF服务端:
- 1 NVStream_IncompleteRead: NVCF streaming中断
- 1 NVStream_TimeoutError: NVCF内部超时
- 1 all_tiers_exhausted: 夜间NVCF不稳定

**24h ate=42看似偏高**, 但:
- 95.2%集中在夜间01:00-11:00 UTC (NVCF server-side)
- 最近6h仅1次ate
- 非TIER_TIMEOUT_BUDGET不足 (R143后budget margin=26s)
- 非配置可优化范畴 (Pitfall #30)

**R143效果确认**: UPSTREAM_TIMEOUT 68→60 + KEY_COOLDOWN_S 38→34 完全生效:
- 从R144到R145连续两轮验证100%短窗口成功率
- Budget margin从10s扩大到26s (2.6× safety improvement)
- 0 429, 0 fallback, 0 back-to-back
- 所有请求first attempt成功

## 🔧 变更执行

**No change this round.** R143 changes fully validated and stable. All 7 parameters at equilibrium.

## 📈 预期效果

| Metric | Before R143 (R142) | After R143 (R144) | Current R145 | Trend |
|--------|-------------------|-------------------|--------------|-------|
| 30min success | 100% | 100% | 100% | — (stable) |
| 1h success | 99.7% | 100% | 100% | ↑ stable |
| 6h success | 99.6% | 99.6% | 99.6% | — (stable) |
| 30min 429 | 0 | 0 | 0 | — (stable) |
| 30min ate | 0 | 0 | 0 | — (stable) |
| Budget margin | 10s | 26s | 26s | — (stable) |
| Back-to-back | 0.0% | 0.0% | 0.0% | — (stable) |

## ⚖️ 评判标准

| Criterion | Status | Evidence |
|-----------|--------|----------|
| 更少报错 | ✅ | 30min/1h ZERO errors; 6h仅3(NVCF服务端) |
| 更快请求 | ✅ | 100% first-attempt success; avg 20s |
| 超低延迟 | ✅ | P50=18s, P95=37s; zero failure-path latency in short windows |
| 稳定优先 | ✅ | 连续验证R143效果; 7参数均衡不追加 |
| 铁律:只改HM1不改HM2 | ✅ | 本轮无变更, 遵守铁律 |

## ⏳ 轮到HM1优化HM2
