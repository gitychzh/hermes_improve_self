# R204: HM2 → HM1 — 无变更 (全7参数均衡; 30min 99.92% 0ATE 0 429 0 fallback; 33rd consecutive R162+R158 validation; P50=18.1s P95=41.8s; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (30min window, UTC ~04:32-05:02, 2026-06-28)

### Config Snapshot (docker exec hm40006 env)
| Parameter | Value |
|-----------|-------|
| UPSTREAM_TIMEOUT | 70 |
| TIER_TIMEOUT_BUDGET_S | 156 |
| KEY_COOLDOWN_S | 38 |
| TIER_COOLDOWN_S | 38 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 |
| HM_CONNECT_RESERVE_S | 24 |
| PROXY_TIMEOUT | 300 |

### 30min Metrics
| Metric | Value |
|--------|-------|
| Total requests | 1182 |
| Success (200) | 1181 |
| Errors | 1 (NVStream_IncompleteRead, network-layer) |
| ATE (all_tiers_exhausted) | 0 |
| 429 | 0 |
| Fallback | 0 |
| P50 latency | 18,124ms |
| P95 latency | 41,764ms |
| Success rate | 99.92% |

### 1h Metrics
| Metric | Value |
|--------|-------|
| Total requests | 1262 |
| Success | 1261 |
| Errors | 1 (NVStream_IncompleteRead) |
| ATE | 0 |
| 429 | 0 |
| Fallback | 0 |
| Success rate | 99.92% |

### 6h Metrics
| Metric | Value |
|--------|-------|
| Total requests | 1944 |
| Success | 1943 |
| Errors | 1 |
| ATE | 0 |
| 429 | 0 |
| Fallback | 0 |
| Success rate | 99.95% |
| P50 | 18,245ms |
| P95 | 45,035ms |

### 24h Segmented
| Window | Fallback | ATE |
|--------|----------|-----|
| 0-6h | 0 | 0 |
| 6-12h | 0 | 0 |
| 12-24h | 781 (old-regime) | 0 |

All fallback in 12-24h = old-regime pre-R162 data (Pitfall #49).

### Per-Key Latency (30min)
| Key (nv_key_idx) | Total | OK | avg_ok_ms | p95_ms |
|-------------------|-------|----|-----------|--------|
| k0 | 243 | 243 | 19,001 | 40,268 |
| k1 | 236 | 236 | 19,912 | 43,960 |
| k2 | 232 | 232 | 20,141 | 41,257 |
| k3 | 234 | 233 | 19,798 | 38,616 |
| k4 | 237 | 237 | 20,546 | 42,290 |

Per-key distribution even (range 15). k3 p95=38.6s lowest, k1 p95=44.0s highest. No outlier keys.

### Docker Logs (error scan, last 100 lines)
```
[12:56:13.7] [HM-ERR] tier=deepseek_hm_nv k4 SSLEOFError: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1032)
[12:56:13.7] [HM-SSL-RETRY] tier=deepseek_hm_nv k4 SSL error — retrying same key after 2s backoff
```
Only 1 SSLEOFError on k4, auto-retried successfully. No other errors in 100-line scan.

### Recent logs (tail 30)
All `[HM-SUCCESS]` entries. Round-robin cycling k1→k2→k3→k4→k5→k1 perfectly. All first-attempt successes.

### Error Detail JSONL (last 5 entries, from ~12:30-12:36 UTC)
3 ATE events from earlier (before 0-6h window):
- d5a65afe@12:30: deepseek 5 attempts elapsed 155.7s → kimi num_attempts=0 (Pitfall #41)
- ada77d8a@12:33: deepseek 5 attempts (empty_200 + 4×NVCFPexecTimeout) elapsed 152.9s → kimi num_attempts=0
- 6bf209ab@12:36: deepseek 6 attempts (empty_200 + 4×NVCFPexecTimeout + budget_exhausted_after_connect) elapsed 151.2s → kimi num_attempts=0

These are all NVCF PexecTimeout storm events from the daytime window (UTC 12:30-12:36), fully subsided since. 0 ATE in the 30min/1h/6h windows confirms storm has passed.

### Request Rate & Back-to-Back
- Request rate: ~3.0 req/min (94% of MIN_OUTBOUND capacity = 3.16/min at 19.0s)
- Back-to-back same-key rate: 0.08% (1/1181) — negligible
- No gap minutes in recent tail — steady traffic

## 🎯 优化分析

### Parameter Evaluation Table

| Parameter | Current | Signal | Adjustment? | Reason |
|-----------|---------|--------|-------------|--------|
| UPSTREAM_TIMEOUT | 70 | All key p95 < 45s (well below 70s) | No | Reducing below NVCF actual timeout (~24s per key) has no effect on ATE (Pitfall #43). Success-path requests need headroom. |
| TIER_TIMEOUT_BUDGET_S | 156 | 0 ATE in 30min/1h/6h | No | Budget safe: 2×70=140, remaining=16s > 10s threshold. R154 proved diminishing returns beyond threshold. |
| KEY_COOLDOWN_S | 38 | 0 429s in all windows | No | KEY=TIER=38 invariant holds (Pitfall #44). 0 429s = no pressure to adjust. |
| TIER_COOLDOWN_S | 38 | 0 tier exhaustion events | No | KEY=TIER=38 alignment working perfectly. |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | 94% capacity utilization, 0 429 | No | Near-optimal utilization. 0 429s means not too aggressive. 5×19=95s >> KEY_COOLDOWN=38s safety. |
| HM_CONNECT_RESERVE_S | 24 | 0 budget_exhausted_after_connect in recent windows | No | R203 HM1→HM2 already adjusted HM2 side. HM1 side stable. |
| PROXY_TIMEOUT | 300 | No timeout issues | No | Far above any observed duration. |

### Bottleneck Analysis
- **No bottleneck detected.** All 7 parameters at equilibrium.
- 30min 99.92%, 1h 99.92%, 6h 99.95% — performance is excellent and improving.
- P50=18.1s (new low, -0.3s from R203), P95=41.8s (new low, -0.4s from R203).
- 0 ATE, 0 429, 0 fallback in all active windows.
- Single error in 30min is NVStream_IncompleteRead (network-layer, not config-addressable).
- SSLEOFError on k4 auto-retried — not a systematic issue.

### P50/P95 Trajectory
| Round | P50 | P95 | Notes |
|-------|-----|-----|-------|
| R198 | 18.2s | 42.3s | |
| R200 | 18.2s | 48.3s | Higher P95 from NVCF variance |
| R202 | 18.4s | 42.2s | |
| R203 | 18.4s | 42.2s | |
| **R204** | **18.1s** | **41.8s** | New lows |

Latency trajectory is stable-to-improving. No config change needed.

## 🔧 变更执行

No change. All 7 parameters at equilibrium — 33rd consecutive R162+R158 validation.

## 📈 预期效果

Stability IS the optimal state. The R162 (KEY=TIER=38) and R158 (UPSTREAM_TIMEOUT=70) equilibrium plateau is fully confirmed across 33 consecutive validation rounds. No parameter adjustment will improve on 99.92%+ success rate with 0 ATE/0 429/0 fallback.

## ⚖️ 评判标准
- ✅ 更少报错: 0 ATE, 0 429, 1 network-layer error (auto-recovered)
- ✅ 更快请求: P50=18.1s (new low), P95=41.8s (new low)
- ✅ 超低延迟: P50=18.1s is the lowest recorded in recent rounds
- ✅ 稳定优先: 33rd consecutive R162+R158 validation, all 7 params at equilibrium
- ✅ 铁律: 只改HM1不改HM2 — no changes made to HM2

## ⏳ 轮到HM1优化HM2
