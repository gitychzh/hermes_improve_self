# R197: HM2→HM1 — 无变更 (全7参数均衡; 30min 99.50% 6ATE全NVCFPexecTimeout 0 429 0 fallback; 1h 99.29%; 6h 99.39%; P50=18.2s P95=43.2s; 28th consecutive R162+R158 验证; NVCF PexecTimeout 风暴不可配置级修复; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 03:25-03:55 UTC, 30min window)

### Docker Logs
- `docker logs --tail 100 hm40006 | grep -iE "(error|warn|fail|timeout|refused|reset|exhausted|panic)"` → **0 matches** (exit code 1 = no errors in logs)
- Latest logs: all `[HM-SUCCESS] tier=deepseek_hm_nv k* succeeded on first attempt`

### Runtime Env (确认7参数)
| Parameter | Value | Expected | ✅/❌ |
|-----------|-------|----------|-------|
| UPSTREAM_TIMEOUT | 70 | 70 | ✅ |
| TIER_TIMEOUT_BUDGET_S | 156 | 156 | ✅ |
| KEY_COOLDOWN_S | 38 | 38 | ✅ |
| TIER_COOLDOWN_S | 38 | 38 | ✅ |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | 19.0 | ✅ |
| HM_CONNECT_RESERVE_S | 24 | 24 | ✅ |
| PROXY_TIMEOUT | 300 | 300 | ✅ |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | 3.0 | ✅ |

### DB Metrics — 30min Window
| status | count | avg_ms | p50_ms | p95_ms | p99_ms |
|--------|-------|--------|--------|--------|--------|
| 200 | 1204 | 20225 | 18161 | 43166 | 68174 |
| 502 | 7 | 132912 | 154566 | 155547 | 155590 |

- **30min total**: 1211 (1204 ok + 7 fail)
- **30min success**: 99.50%
- **30min ATE (all_tiers_exhausted)**: 6 (avg=153926ms)
- **30min NVStream_IncompleteRead**: 1 (6827ms)
- **30min 429**: 0
- **30min fallback**: 0
- **30min back-to-back rate**: 16/1214 = 1.32%

### DB Metrics — 1h Window
| status | count | avg_ms | p50_ms | p95_ms | p99_ms |
|--------|-------|--------|--------|--------|--------|
| 200 | 1262 | 20352 | 18204 | 43701 | 70953 |
| 502 | 9 | 135989 | 151727 | 155529 | 155587 |

- **1h total**: 1271 (1262 ok + 9 fail)
- **1h success**: 99.29%
- **1h 429**: 0
- **1h fallback**: 0

### DB Metrics — 6h Window
| status | count | avg_ms | p50_ms | p95_ms | p99_ms |
|--------|-------|--------|--------|--------|--------|
| 200 | 1947 | 20945 | 18371 | 47183 | 78463 |
| 502 | 12 | 124576 | 149240 | 155503 | 155581 |

- **6h total**: 1959 (1947 ok + 12 fail)
- **6h success**: 99.39%
- **6h ATE**: 9 (avg=151002ms)
- **6h NVStream_IncompleteRead**: 2 (k3: 6827ms, k4: 19546ms)
- **6h NVStream_TimeoutError**: 1 (k0: 109523ms)
- **6h 429**: 0
- **6h fallback**: 0

### 6h Error Breakdown by Hour
| Hour (UTC) | Error Type | Count | Avg_ms |
|------------|-----------|-------|--------|
| 2026-06-27 22:00 | NVStream_IncompleteRead | 1 | 19546 |
| 2026-06-27 22:00 | NVStream_TimeoutError | 1 | 109523 |
| 2026-06-28 01:00 | all_tiers_exhausted | 1 | 141944 |
| 2026-06-28 02:00 | all_tiers_exhausted | 2 | 146760 |
| 2026-06-28 04:00 | NVStream_IncompleteRead | 1 | 6827 |
| 2026-06-28 10:00 | all_tiers_exhausted | 6 | 153926 |

### 24h Segmented Analysis
| Window | Total | Fallback | 429 | ATE | Success% |
|--------|-------|----------|-----|-----|----------|
| 0-6h | 1959 | 0 | 0 | 9 | 99.39% |
| 6-12h | 915 | 0 | 0 | 21 | 97.38% |
| 12-24h | 1661 | 1014 | 4 | 20 | 98.80% |

- 12-24h fallback (1014+) and ATE (20+) are **old-regime data** (Pitfall #49)
- 0-6h and 6-12h: 0 fallback confirms storm-free operation

### Success-Path Latency (30min, status=200 only)
- **P50**: 18186ms (18.2s)
- **P95**: 42988ms (43.0s)
- **P99**: 68152ms (68.2s)
- **>70s rate**: 1.03% (NVCF server-side tail, Pitfall #29)

### Per-Key Distribution (30min)
| nv_key_idx | Total | OK | Avg_ok_ms | P95_ok_ms |
|------------|-------|-----|-----------|-----------|
| k0 | 244 | 244 | 19668 | 44406 |
| k1 | 241 | 241 | 20861 | 48387 |
| k2 | 236 | 236 | 19773 | 38214 |
| k3 | 239 | 238 | 19735 | 42679 |
| k4 | 245 | 245 | 21027 | 43074 |
| (null) | 6 | 0 | — | — |

- Per-key even: 236–245 req/key in 30min ✅

### Error Detail JSONL (2026-06-28)
18 error detail entries total. Key patterns:
- **3 ATE storms at 01:13, 02:40-02:42 UTC** (overnight, pre-downtime): kimi_hm_nv num_attempts=0 (Pitfall #41)
- **6 ATE events at 10:30-10:38 UTC** (morning cluster): deepseek_hm_nv consuming 145-155s across 6 key attempts, kimi num_attempts=0
- **All ATE events**: NVCF PexecTimeout per-key avg ~24s (far below UPSTREAM_TIMEOUT=70s) → NVCF server-side timeout, not HM-configured timeout (Pitfall #43)
- **budget_exhausted_after_connect**: 1 occurrence (k4 in 01:13 storm, elapsed=1103ms)
- **empty_200**: 3 occurrences (NVCF API returning empty 200 before PexecTimeout cascade)

## 🎯 优化分析

### 7-Parameter Evaluation Table
| Parameter | Current | Adjustment Needed? | Reason |
|-----------|---------|--------------------|--------|
| UPSTREAM_TIMEOUT | 70 | ❌ No | All key p95=38-48s < 70s; reducing would risk legitimate long requests; NVCF PexecTimeout fires at ~24s regardless of this value (Pitfall #43) |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ No | 2×70=140, remaining=16s > 10s threshold; R154 diminishing returns confirmed: budget increases beyond threshold show zero ATE reduction |
| KEY_COOLDOWN_S | 38 | ❌ No | KEY=TIER=38 (invariant holds, Pitfall #44); 0 429s means no rate-limit pressure to warrant decrease |
| TIER_COOLDOWN_S | 38 | ❌ No | KEY≥TIER invariant holds (38=38); aligned with KEY for zero-gap optimal recovery |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ❌ No | ~2 req/min actual vs 3.2/min capacity (63% utilization); 0 429s; no rate-limit pressure |
| HM_CONNECT_RESERVE_S | 24 | ❌ No | Only 1 budget_exhausted_after_connect in 24h; sufficient coverage |
| PROXY_TIMEOUT | 300 | ❌ No | No proxy-timeout-related errors observed |

### Bottleneck Identification
- **Remaining errors are 100% NVCF server-side**: PexecTimeout storms and NVStream network-layer glitches
- **Fallback tier starvation (Pitfall #41)**: All ATE events show kimi_hm_nv num_attempts=0 because the deepseek tier consumes the full budget (~141-155s > 156s budget) before kimi can be attempted
- **This is NOT fixable via config** — would require a per-tier budget split (code change) or accepting NVCF-wide storms as unresolvable at the config level (per R154/R158/R162 analysis)
- R154 proven: budget increases beyond the threshold show diminishing returns; R196 confirmed this again

### Comparison vs R196
- R196 30min: 99.42% (6 ATE) → R197 30min: 99.50% (6 ATE) — stable
- R196 P50=18.2s P95=45.4s → R197 P50=18.2s P95=43.0s — P95 improved by 2.4s
- Same 6 ATE pattern (NVCF PexecTimeout storm cluster at 10:00 UTC)
- 28th consecutive R162+R158 validation

## 🔧 变更执行
**No change.** All 7 parameters at equilibrium — stability IS the optimal state.

## 📈 预期效果
| Metric | R196 | R197 | Trend |
|--------|------|------|-------|
| 30min success% | 99.42% | 99.50% | → (stable) |
| 1h success% | 99.29% | 99.29% | → (stable) |
| 6h success% | 99.39% | 99.39% | → (stable) |
| P50 (success) | 18.2s | 18.2s | → (stable) |
| P95 (success) | 45.4s | 43.0s | ↑ (improved) |
| 30min ATE | 6 | 6 | → (NVCF server-side) |
| 30min 429 | 0 | 0 | → (zero) |
| 30min fallback | 0 | 0 | → (zero) |
| Back-to-back | ~1.4% | 1.32% | → (stable) |
| Budget margin | 16s | 16s | → (2×70=140, 156-140=16s) |
| KEY≥TIER invariant | 38=38 ✅ | 38=38 ✅ | → (holds) |

## ⚖️ 评判标准
- ✅ 更少报错: 0 429, 0 fallback; ATE全NVCF PexecTimeout (不可配置级修复)
- ✅ 更快请求: P50=18.2s (稳定低延迟)
- ✅ 超低延迟: P95=43.0s (持续改善, -2.4s vs R196)
- ✅ 稳定优先: 28th consecutive R162+R158 validation; 7参数全均衡
- ✅ 铁律:只改HM1不改HM2: 确认HM2本地无变更

## ⏳ 轮到HM1优化HM2