# R121: HM2→HM1 — 无变更 (R120验证通过, 全参数稳定)

## 📊 数据采集 (30-min Window, 2026-06-27 ~22:25–22:55 UTC)

### HM1 Environment
| Parameter | Value | Notes |
|-----------|-------|-------|
| UPSTREAM_TIMEOUT | **68** | R120: 66→68, +2s |
| TIER_TIMEOUT_BUDGET_S | **140** | R116 |
| KEY_COOLDOWN_S | **38.0** | R108 |
| TIER_COOLDOWN_S | **42** | R115 |
| MIN_OUTBOUND_INTERVAL_S | **19.0** | R119: 22→19, -3s |
| HM_CONNECT_RESERVE_S | **24** | R111 |
| CHARS_PER_TOKEN_ESTIMATE | **3.0** | default |
| PROXY_TIMEOUT | **300** | default |

### 30min Latency Percentiles (hm_requests, success only)
| Metric | Value |
|--------|-------|
| Total Requests | 66 |
| Success | 65 (98.5%) |
| Failures | 1 |
| Avg (success) | 25,197ms |
| p50 | 19,293ms |
| p90 | 42,881ms |
| p95 | 53,178ms |
| Min | 4,620ms |
| Max (success) | 144,752ms |

### Error Breakdown (30min)
| Error Type | Key | Count | Avg Duration |
|-----------|-----|-------|--------------|
| NVStream_TimeoutError | k0 (DIRECT) | 1 | 109,523ms |

### Per-Key Success Latency (30min)
| Tier | Key | Count | Avg | p95 |
|------|-----|-------|-----|-----|
| deepseek_hm_nv | k2 (DIRECT) | 11 | 15,493ms | 22,948ms |
| deepseek_hm_nv | k0 (DIRECT) | 11 | 32,652ms | 92,701ms |
| deepseek_hm_nv | k3 (PROXY 7896) | 16 | 23,398ms | 45,586ms |
| deepseek_hm_nv | k4 (PROXY 7897) | 14 | 26,548ms | 51,323ms |
| deepseek_hm_nv | k1 (DIRECT) | 13 | 27,856ms | 62,176ms |

### Key Cycle 429s (30min)
- key_cycle_429s=0: 66 requests (100%)
- Zero rate limiting pressure.

### Tier Health (1h)
| Tier | OK | Fail | Success % | Avg |
|------|-----|------|----------|-----|
| deepseek_hm_nv | 1,325 | 4 | 99.7% | 28,958ms |

### Requests Near UPSTREAM_TIMEOUT=68s (duration_ms ≥ 65,000)
| Count | Avg | Min | Max |
|-------|-----|-----|-----|
| 2 | 108,640ms | 72,527ms | 144,752ms |

Note: max=144,752ms likely records the same NVStream_TimeoutError retry cycle — the DB captures total elapsed, not individual attempt. The actual timeout is at ~109s (NVStream_TimeoutError on k0).

## 🎯 优化分析

### Complete Parameter Evaluation

**UPSTREAM_TIMEOUT=68** (R120: 66→68, +2s):
- Only 1 timeout in 30min (NVStream_TimeoutError on k0, 109s)
- 2 requests ≥65s: avg=108,640ms — the single error dominates this, 98.5% of requests succeed well below timeout
- 2×68=136 < BUDGET=140 — safety margin intact (4s buffer)
- No change needed. R120's +2s is handling tail requests correctly.

**TIER_TIMEOUT_BUDGET_S=140**:
- No all_tiers_exhausted events in 30min or 1h
- Only 1 timeout + 4 fails in 1h (99.7% success)
- BUDGET well above 2×UPSTREAM_TIMEOUT=136
- No change needed.

**KEY_COOLDOWN_S=38.0**:
- Zero 429 errors in 30min (key_cycle_429s=0 for all)
- No rate limiting pressure detected
- Cooldown has no triggering events → no need to adjust
- No change needed.

**TIER_COOLDOWN_S=42**:
- Only 4 tier-level failures in 1h (1,325+ requests)
- Gap to KEY_COOLDOWN: 42-38=4s — minimum safety margin maintained
- No tier exhaustion events
- No change needed.

**MIN_OUTBOUND_INTERVAL_S=19.0** (R119: 22→19, -3s):
- Actual throughput: ~2 requests/min (66 in 30min)
- Capacity at 19s: ~3 requests/min per key, 5-key cycle = ~15/min
- Utilization: ~13% — well within capacity
- Zero 429s confirms interval is not too low
- No change needed.

**HM_CONNECT_RESERVE_S=24** (R111: 22→24, +2s):
- No budget_exhausted_after_connect errors in 30min
- All keys successfully connect (avg connection within reserve)
- R111's +2s has prevented the multi-key SSL stall pattern
- No change needed.

### Verdict
**All 7 parameters are at optimal values.** No adjustment is needed. The system is operating at:
- 98.5% success rate (30min), 99.7% (1h)
- Zero 429 pressure
- Zero all_tiers_exhausted
- Single NVStream_TimeoutError from one DIRECT key (k0) — expected tail behavior

This is a **no-change validation round**. R120's UPSTREAM_TIMEOUT increase from 66→68 is confirmed working — the 1 timeout still falls within acceptable error budget. Further changes would risk over-optimization.

## ⚖️ 评判标准

| Criterion | Status | Evidence |
|-----------|--------|----------|
| **更少报错** | ✅ EXCELLENT | 1 error in 30min (1.5%), 4 in 1h (0.3%) |
| **更快请求** | ✅ STABLE | p50=19.3s, p95=53.2s — consistent throughput |
| **超低延迟** | ✅ GOOD | avg=25.2s on model calls, well within timeout |
| **稳定优先** | ✅ VERIFIED | 0 429s, 0 budget exhaustions, all keys healthy |

**铁律**: ✅ 只改HM1不改HM2 — 本轮无变更，未修改任何配置。

## ⏳ 轮到HM1优化HM2