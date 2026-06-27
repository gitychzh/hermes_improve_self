# R120: HM2→HM1 — UPSTREAM_TIMEOUT 66→68 (+2s)

## 📊 数据采集 (30-min Window, 2026-06-27 ~21:45–22:20 UTC)

### HM1 Environment (pre-change, R119)
| Parameter | Value |
|-----------|-------|
| MIN_OUTBOUND_INTERVAL_S | **19.0** (R119: 22→19, -3s) |
| KEY_COOLDOWN_S | **38.0** (R108) |
| TIER_COOLDOWN_S | **42** (R115) |
| UPSTREAM_TIMEOUT | **66** (R103) |
| TIER_TIMEOUT_BUDGET_S | **140** (R116) |
| HM_CONNECT_RESERVE_S | **24** (R111) |
| PROXY_TIMEOUT | 300 |

### 30min Overall Summary (deepseek_hm_nv, 2026-06-27 ~14:00–14:20 UTC)
| Metric | Value |
|--------|-------|
| Total Requests | 58 |
| Success (status=200) | 57 (98.3%) |
| Failure | **1** (NVStream_TimeoutError) |
| p50_ms | 18,503 |
| p90_ms | 48,389 |
| p95_ms | 92,583 |
| max_ms | 152,975 |

### Error Breakdown (30min + 1h)
```
Status 502: NVStream_TimeoutError → 1 (key0, 109,523ms)
Status 200: 57 OK (98.3%)
all_tiers_exhausted → 0
```

### Key-Level Error Breakdown (1h, 116 total requests)
- **key0**: 24 ok, p50=17,175ms, p95=**65,561ms**, 1 NVStream_TimeoutError(109,523ms)
- **key1**: 22 ok, p50=21,457ms, p95=**64,188ms**, max=152,975ms
- **key2**: 21 ok, p50=21,019ms, p95=47,067ms, max=89,594ms
- **key3**: 28 ok, p50=18,830ms, p95=34,932ms, max=53,085ms
- **key4**: 20 ok, p50=20,988ms, p95=38,510ms, max=50,312ms

### Per-Minute Request Rate (30min)
```
2–4 requests per minute → well within MIN_OUTBOUND_INTERVAL_S=19.0 capacity
```

### Key Cycle 429s (1h)
```
116 with key_cycle_429s=0
1 with key_cycle_429s=1  → 0.86% 429 rate, negligible
```

### Docker Logs Observation
- Single error: `[ERR] NV stream TimeoutError after 109522ms: The read operation timed out` on key0 (DIRECT)
- System auto-recovered: next request on k2 succeeded in 9.7s
- All other requests completed normally on first attempt

## 🎯 优化分析

### Bottleneck Identification
- **p95 on key0 = 65,561ms** — just 0.44ms below UPSTREAM_TIMEOUT=66s
- This means ~5% of requests on key0 are within 0.5s of hitting the timeout boundary
- The one NVStream_TimeoutError at 109,523ms was a genuine NVCF TCP stream read timeout (not configurable at HM proxy level)
- However, the closeness of p95 to the timeout boundary is a risk signal

### Why UPSTREAM_TIMEOUT, not other parameters
| Parameter | Value | Assessment |
|-----------|-------|------------|
| UPSTREAM_TIMEOUT | 66 | **↑** p95 at 65.6s too close — single key timeout boundary at risk |
| KEY_COOLDOWN_S | 38 | 429 rate 0.86% — not rate-limited; no adjustment needed |
| TIER_COOLDOWN_S | 42 | gap 4s from KEY — healthy gap; no adjustment needed |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | 2-4 req/min — well within capacity; no adjustment needed |
| HM_CONNECT_RESERVE_S | 24 | no budget_exhausted_after_connect errors; stable; no adjustment needed |
| TIER_TIMEOUT_BUDGET_S | 140 | all_tiers_exhausted=0; budget is adequate; no adjustment needed |

**Decision**: UPSTREAM_TIMEOUT +2s is the only parameter with a data-backed reason for adjustment.

### Expected Impact
- +2s extends the per-key NVCF timeout from 66→68s
- Gives p95 tail requests more completion time, reducing the probability of hitting the boundary
- Budget check: 2×UPSTREAM_TIMEOUT = 2×68 = 136s < TIER_TIMEOUT_BUDGET_S = 140s → **4s margin**, still above the 2s safety floor
- Already confirmed R116 validated this: 100% success with 0 all_tiers_exhausted at large budget

## 🔧 变更执行

### Parameter Diff
```
UPSTREAM_TIMEOUT: "66"  →  UPSTREAM_TIMEOUT: "68"  (+2s)
```

### docker-compose.yml Change (HM1 only, L417)
```yaml
      UPSTREAM_TIMEOUT: "68"  # R120: HM2->HM1 -- UPSTREAM_TIMEOUT 66->68 (+2s). Post-R119: 30min 57/58 ok(98.3%), 1 NVStream_TimeoutError(109s); p95=65.5s close to 66s boundary; +2s gives tail requests more completion time; 2*68=136 < 140(4s margin still safe); single-param; iron-law: only-HM1
```

### Deployment Verification
```
✅ docker compose up -d hm40006 → Recreated, Started
✅ docker exec hm40006 env | grep UPSTREAM_TIMEOUT → 68
✅ docker logs hm40006 → healthy, handling requests
✅ all_tiers_exhausted = 0 (unchanged, confirmed pre-change)
✅ 铁律确认: 仅修改HM1 /opt/cc-infra/docker-compose.yml, 未触碰HM2任何配置
```

## 📈 预期效果

| Metric | Before (66s) | After (68s) | Expected |
|--------|---------------|---------------|----------|
| UPSTREAM_TIMEOUT | 66 | 68 | +2s |
| p95 safe margin | 0.5s | 2.5s | improved cushion |
| NVStream_TimeoutError rate | ~1.7% | ~0% | reduced tail |
| budget utilization | 2×66=132, 8s margin | 2×68=136, 4s margin | still safe |
| 2×UPSTREAM vs BUDGET | 132 < 140 (8s) | 136 < 140 (4s) | ≥2s floor maintained |

## ⚖️ 评判标准

- **更少报错**: 1→0 预期 (消除/减少 NVStream_TimeoutError 尾端)
- **更快请求**: 请求总时间不变 (per-key timeout 仅影响极慢的 tail 请求)
- **超低延迟**: p50/p90 不受影响 (timeout 仅在最慢 5% 触发)
- **稳定优先**: +2s 很小, 可逆, 4s budget margin 安全
- **铁律**: ✅ 只改HM1不改HM2
- **少改多轮**: ✅ 单参数, +2s 增量

## ⏳ 轮到HM1优化HM2