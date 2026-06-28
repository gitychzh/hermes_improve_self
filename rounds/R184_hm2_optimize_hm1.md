# R184: HM2 → HM1 — 无变更 (全7参数均衡; 30min 99.67% 3ATE全NVCF 0 429 0 fallback; 1h 99.69%; 6h 99.48% 6ATE+4×NVStream 0 429 0 fallback; 24h ATE=45全NVCF 5×429 1355fallback全旧regime; 第18次R162验证+第18次R158验证; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (30min/1h/6h/24h, 2026-06-28 ~08:44 UTC)

### Config Snapshot (HM1 hm40006)
| Parameter | Value |
|-----------|-------|
| UPSTREAM_TIMEOUT | 70 |
| TIER_TIMEOUT_BUDGET_S | 156 |
| KEY_COOLDOWN_S | 38 |
| TIER_COOLDOWN_S | 38 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 |
| HM_CONNECT_RESERVE_S | 24 |
| PROXY_TIMEOUT | 300 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 |

### Docker Logs (last 100 lines, grep errors/warn)
- **0 matches** — all logs are [HM-SUCCESS] and [HM-REQ], zero errors/warnings/failures/panics

### Runtime Env Verification
- UPSTREAM_TIMEOUT=70 ✅
- TIER_TIMEOUT_BUDGET_S=156 ✅
- KEY_COOLDOWN_S=38 ✅
- TIER_COOLDOWN_S=38 ✅
- MIN_OUTBOUND_INTERVAL_S=19.0 ✅
- HM_CONNECT_RESERVE_S=24 ✅
- All keys (K1-K5 DIRECT + K3-K5 PROXY) loaded ✅

### DB Metrics (hm_requests via cc_postgres)

**30min window:**
| Metric | Value |
|--------|-------|
| Total | 1220 |
| Success (200) | 1216 |
| Success Rate | 99.67% |
| ATE (all_tiers_exhausted) | 3 |
| 429 | 0 |
| Fallback | 0 |
| 502 (NVStream) | 1 |
| P50 latency (all) | 18,311ms |
| P95 latency (all) | 46,892ms |
| Avg latency (success) | 20,840ms |

**30min success latency buckets:**
| Bucket | Count |
|--------|-------|
| <10s | 163 |
| 10-30s | 894 |
| 30-60s | 129 |
| 60-70s | 12 |
| >70s | 18 |

**30min error breakdown:**
| Error Type | Count | Avg Duration |
|------------|-------|-------------|
| all_tiers_exhausted | 3 | 145,154ms |
| NVStream_IncompleteRead | 1 | 6,827ms |

**1h window:**
| Metric | Value |
|--------|-------|
| Total | 1285 |
| Success (200) | 1281 |
| Success Rate | 99.69% |
| ATE | 3 |
| 429 | 0 |
| Fallback | 0 |

**6h window:**
| Metric | Value |
|--------|-------|
| Total | 1916 |
| Success (200) | 1906 |
| Success Rate | 99.48% |
| ATE | 6 |
| 429 | 0 |
| Fallback | 0 |

**24h window (segmented):**
| Window | Total | Success | ATE | 429 | Fallback |
|--------|-------|---------|-----|-----|----------|
| 0-6h | 1915 | 1905 (99.48%) | 6 | 0 | 0 |
| 6-12h | 979 | 954 (97.45%) | 23 | 0 | 0 |
| 12-24h | 1723 | 1707 (99.08%) | 16 | 5 | 1353 |

**24h overall:** 4617 total, 4566 success (98.89%), 45 ATE all NVCF PexecTimeout, 5×429, 1353 fallback (all in 12-24h old-regime, Pitfall #49)

**24h error breakdown:**
| Status | Count | Avg Duration |
|--------|-------|-------------|
| 502 | 46 | 117,557ms |
| 429 | 5 | 172,934ms |

### Per-Key Latency (30min, all requests)
| Key | nv_key_idx | Total | Success | Errors | P50 (ms) | P95 (ms) |
|-----|-----------|-------|---------|--------|-----------|-----------|
| K1 | 0 | 245 | 245 | 0 | 18,532 | 49,521 |
| K2 | 1 | 242 | 242 | 0 | 18,253 | 48,044 |
| K3 | 2 | 236 | 236 | 0 | 17,497 | 41,288 |
| K4 | 3 | 243 | 242 | 1 | 18,494 | 46,789 |
| K5 | 4 | 251 | 251 | 0 | 18,546 | 48,647 |

Per-key distribution even (~236-251 requests). K3 (key_idx=2) P95 lowest at 41s. K1 (DIRECT) tail > K3 (PROXY) — Pitfall #29 confirmed.

### Per-Key Latency (6h, success only)
| Key | nv_key_idx | Success/Total | P95 (ms) |
|-----|-----------|---------------|----------|
| K1 | 0 | 398/400 | 54,442 |
| K2 | 1 | 380/380 | 51,627 |
| K3 | 2 | 363/363 | 41,917 |
| K4 | 3 | 382/383 | 48,843 |
| K5 | 4 | 382/383 | 50,152 |

K3 (PROXY) P95 lowest; K1 (DIRECT) tail > K3 — consistent Pitfall #29 pattern.

### Error Detail JSONL (2026-06-28, latest events)
Latest 3 ATE events all show NVCF PexecTimeout storm pattern (Pitfall #41):
- deepseek_hm_nv consuming 141-146s across 6 key attempts
- kimi_hm_nv num_attempts=0 — fallback tier starvation under NVCF storms
- Budget fully consumed by deepseek timeouts
- Per-key actual elapsed: 5,622ms (NVCF server-side timeout, far below UT=70s, Pitfall #43)

### Request Rate
- ~2-4 req/min (peak at ~4/min, average ~3.0/min)
- MIN_OUTBOUND_INTERVAL_S=19.0 capacity: 60/19 ≈ 3.2 req/min
- Utilization: ~94% at 3.0 req/min

## 🎯 优化分析

### Parameter Evaluation Table

| Parameter | Current | Assessment | Action |
|-----------|---------|-----------|--------|
| UPSTREAM_TIMEOUT | 70 | R158 stable 18+ rounds; all key P95 < 55s; NVCF timeouts at ~5.6s actual (Pitfall #43); 3 ATE/30min is NVCF storms, not budget-exceeded | ❌ No change |
| TIER_TIMEOUT_BUDGET_S | 156 | 2×70=140, remaining=16s > 10s + 2s overhead; R154 diminishing returns: budget increase does NOT reduce NVCF PexecTimeout ATE | ❌ No change |
| KEY_COOLDOWN_S | 38 | KEY=TIER=38 invariant holds (Pitfall #44); 0 429 in all windows | ❌ No change |
| TIER_COOLDOWN_S | 38 | Aligned with KEY; 0 fallback in 0-6h; ATE in 6-12h/12-24h is NVCF storms (Pitfall #30, #41) | ❌ No change |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ~94% utilization; 0 429; tight but queue not backing up | ❌ No change |
| HM_CONNECT_RESERVE_S | 24 | 0 budget_exhausted_after_connect errors; no connect-timeout issues | ❌ No change |
| PROXY_TIMEOUT | 300 | Stable, no issues observed | ❌ No change |

### Why No Change
1. **All 7 parameters at equilibrium** — stable since R162 (KEY=TIER=38 alignment)
2. **30min 99.67% (1216/1220)** — 3 ATE are NVCF server-side PexecTimeout, not config-fixable (Pitfall #41)
3. **0 429 across all windows** — no rate-limiting pressure, KEY_COOLDOWN_S=38 adequate
4. **0 fallback in 0-6h window** — fallback in 24h aggregate is from old-regime data (Pitfall #49)
5. **Per-key distribution even** — no key-specific anomalies (~236-251 per key in 30min)
6. **P50=18.3s, P95=46.9s** — stable latency profile, same as R183 (46.9s)
7. **Budget margin healthy**: 2×70=140, remaining=16s, well above 10s threshold
8. **NVCF PexecTimeout storms are server-side** — actual key elapsed 5.6s < UT=70s (Pitfall #43); reducing UT would not reduce these ATE events since NVCF fires timeout internally
9. **Request rate stable at ~3.0/min** — 94% capacity utilization with 0 429s

### Comparison: R183 vs R184
- R183 caught a transient window with 0 ATE/30min (NVCF storms quiesced briefly)
- R184 sees 3 ATE/30min — this is within normal NVCF variance for daytime hours (Pitfall #30)
- Both are consistent with the R162+R158 equilibrium plateau: NVCF server-side ATE oscillates 0-3/30min

## 🔧 变更执行

**无变更** — 第18次R162验证 + 第18次R158验证

All 7 parameters remain at equilibrium. No config change applied to HM1.

Budget math holds: TIER_TIMEOUT_BUDGET_S=156 ≥ 2×UPSTREAM_TIMEOUT=140 + 10s threshold → remaining=16s ✅

KEY_COOLDOWN_S=38 ≥ TIER_COOLDOWN_S=38 → KEY≥TIER invariant holds (Pitfall #44) ✅

## 📈 预期效果

| Metric | Before (R183) | Current (R184) | Trend |
|--------|---------------|----------------|-------|
| 30min success | 99.92% (1208/1209) | 99.67% (1216/1220) | ≈ NVCF variance (3 ATE) |
| 1h success | 99.92% (1266/1267) | 99.69% (1281/1285) | ≈ NVCF variance |
| 6h success | 99.79% (1907/1911) | 99.48% (1906/1916) | ≈ More ATE in 6h |
| 0-6h ATE | 0 | 6 | ↑ NVCF storms shifted earlier |
| 0-6h fallback | 0 | 0 | ✅ Unchanged |
| 0-6h 429 | 0 | 0 | ✅ Unchanged |
| P50 latency | 18.3s | 18.3s | ✅ Unchanged |
| P95 latency | 46.9s | 46.9s | ✅ Unchanged |

Note: Higher ATE count vs R183 is NVCF server-side variance (Pitfall #30: ATE time-of-day distribution is variable). Config parameters are not implicated.

## ⚖️ 评判标准

| Criterion | Status | Evidence |
|-----------|--------|----------|
| 更少报错 | ✅ | 0 429 all windows; 0 fallback 0-6h; ATE all NVCF PexecTimeout (server-side, Pitfall #41) |
| 更快请求 | ✅ | P50=18.3s, P95=46.9s (stable) |
| 超低延迟 | ✅ | Per-key P95 41-54s, well below UPSTREAM_TIMEOUT=70 |
| 稳定优先 | ✅ | R162+R158 validated 18+ consecutive rounds; equilibrium plateau |
| 铁律:只改HM1不改HM2 | ✅ | No changes applied; HM2 local config untouched |

## ⏳ 轮到HM1优化HM2
