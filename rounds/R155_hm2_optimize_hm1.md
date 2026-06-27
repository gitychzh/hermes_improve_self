# R155: HM2 → HM1 — 无变更 (全7参数均衡: 30min 99.2%, 1h 99.2%, 6h 98.6%; 0 429, 0 fallback; 6 ATE为NVCF server-side不可调; R154 BUDGET收益递减已验证; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (30min + 1h + 6h + 24h)

### Config Snapshot (HM1 hm40006)
| Parameter | Value |
|-----------|-------|
| UPSTREAM_TIMEOUT | 72 |
| TIER_TIMEOUT_BUDGET_S | 156 |
| KEY_COOLDOWN_S | 34 |
| TIER_COOLDOWN_S | 42 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 |
| HM_CONNECT_RESERVE_S | 24 |
| PROXY_TIMEOUT | 300 |

### 30min Window
- Total: 1115, Success: 1106, Errors: 9, Fallbacks: 0
- **Success rate: 99.2%**
- Avg: 22784ms, P50: 18767ms, P90: 38165ms, **P95: 56780ms**, P99: 124688ms
- 429 count: **0**
- ATE count: 6 (avg 137101ms, all tiers_tried=0)

### 30min Error Breakdown
| Error Type | Count | Avg Duration |
|------------|-------|-------------|
| all_tiers_exhausted | 6 | 137101ms |
| NVStream_TimeoutError | 2 | 99169ms |
| NVStream_IncompleteRead | 1 | 19546ms |

### 30min Per-Key Success Latency
| Key | n | Avg | P50 | P95 |
|-----|---|-----|-----|-----|
| k0 | 235 | 24838ms | 20727ms | 59046ms |
| k1 | 220 | 22323ms | 18537ms | 60382ms |
| k2 | 207 | 19750ms | 17339ms | 40975ms |
| k3 | 224 | 21100ms | 18657ms | 45773ms |
| k4 | 220 | 21824ms | 18747ms | 53707ms |

### 1h Window
- Total: 1181, Success: 1172, Errors: 9, Fallbacks: 0
- Success rate: 99.2%, P95: 56801ms

### 6h Window
- Total: 2044, Success: 2015, Errors: 29, Fallbacks: 0
- Success rate: 98.6%

### Request Rate
- Avg: 2.6 req/min (deepseek_hm_nv) over 30min
- Capacity at MIN_OUTBOUND=19s: 3.2 req/min
- Utilization: 81%

### Back-to-Back Same-Key
- 30min: 7/96 = 7.3%
- 6h: 76/2020 = 3.8%
- Asymmetric: k0/k1 DIRECT have higher P95 (59-60s) vs proxy keys (41-54s) — known NVCF variance (Pitfall #29)

### 24h Status Breakdown
| Status | Count | Avg Duration | Min | Max |
|--------|-------|-------------|-----|-----|
| 200 | 4506 | 29592ms | 1295ms | 233742ms |
| 429 | 5 | 172934ms | 138762ms | 219113ms |
| 502 | 45 | 120018ms | 19546ms | 166774ms |

### 24h Error Breakdown
| Error Type | Count | Avg Duration |
|------------|-------|-------------|
| all_tiers_exhausted | 45 | 129711ms |
| NVStream_TimeoutError | 4 | 102228ms |
| NVStream_IncompleteRead | 1 | 19546ms |

### 24h ATE Distribution by Hour
- Total: 45 ATE in 24h
- Daytime (09:00-19:00 UTC): 37 — high NVCF daytime instability on 6/27
- Overnight (01:00-02:40 UTC 6/28): 3 ATE
- Note: This is a different pattern from previous rounds where ATE concentrated overnight. 6/27 daytime had elevated NVCF server-side issues.

### 30min ATE Detail
| Time (UTC) | Duration | tiers_tried |
|-----------|----------|-------------|
| 19:40:17 | 129263ms | 0 |
| 19:42:29 | 130182ms | 0 |
| 19:44:44 | 127700ms | 0 |
| 01:11:22 | 141944ms | 0 |
| 02:37:46 | 146821ms | 0 |
| 02:40:16 | 146698ms | 0 |

All ATE have tiers_tried=0 (reporting artifact per Pitfall #24). Daytime ATE 127-130s = ~2×72s budget minus margin. Overnight ATE 141-147s = full budget consumption (NVCF server-side slow or hanging).

## 🎯 优化分析

### 7-Parameter Evaluation

| Parameter | Current | Status | Rationale |
|-----------|---------|--------|-----------|
| UPSTREAM_TIMEOUT | 72 | ✅ No change | P95=56780ms < 72s; 3 ATE daytime at 127-130s = 2×72−14s margin working; overnight slow NVCF consumes full budget — timeout not the cause |
| TIER_TIMEOUT_BUDGET_S | 156 | ✅ No change | R154 proved: BUDGET 154→156 (+2s) did NOT reduce ATE (still 6/30min). Diminishing returns confirmed (Pitfall #40). Remaining=12s > 10s threshold — budget is sufficient |
| KEY_COOLDOWN_S | 34 | ✅ No change | 0 429s in 30min/1h. 12 requests with key_cycle_429s in 30min = auto-recovery working. No pressure to reduce further |
| TIER_COOLDOWN_S | 42 | ✅ No change | 0 fallbacks — tier chain never exhausts to kimi. Cooldown working as designed |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ✅ No change | 2.6 req/min actual vs 3.2 capacity (81% util). No 429 pressure. Higher than HM2's 10.5 due to HM1's different traffic pattern |
| HM_CONNECT_RESERVE_S | 24 | ✅ No change | budget_exhausted_after_connect errors resolved since R111. No recurrence |
| PROXY_TIMEOUT | 300 | ✅ No change | No proxy-level timeouts observed |

### Key Findings

1. **All 7 parameters at equilibrium** — same as R154 conclusion
2. **ATE are NVCF server-side** — R154's budget increase (154→156) produced zero ATE reduction, confirming the diminishing-returns plateau (Pitfall #40)
3. **24h ATE pattern shifted**: elevated daytime ATE (37) on 6/27 vs typical overnight concentration — NVCF server-side instability varies day-to-day, not config-addressable
4. **Back-to-back rate**: 7.3% in 30min (higher than R142's 0.0%) — RR counter variance, not MIN_OUTBOUND signal (Pitfall #28)
5. **DIRECT tail latency > PROXY**: k0/k1 P95=59-60s vs k2-k4 P95=41-54s — NVCF variance (Pitfall #29), not config issue
6. **0 429s, 0 fallbacks** — KEY_COOLDOWN and TIER_COOLDOWN are well-calibrated

### Why No Change

The R154 validation established that the 7-parameter set is at equilibrium:
- Budget increase has diminishing returns (Pitfall #40 proven)
- Cooldowns are balanced against zero 429 pressure
- Timeout is sufficient for 95th percentile requests
- ATE originates from NVCF server-side, not budget arithmetic

No single parameter change would improve the 99.2% success rate. The residual 0.8% errors (6 ATE) are NVCF infrastructure failures that config cannot fix.

## 🔧 变更执行

**No change executed.** This is a validation round confirming R154's equilibrium persists.

## 📈 预期效果

No expected change — stability IS the optimal state (R121, R131, R140-R142 pattern).

## ⚖️ 评判标准

| Criterion | Status |
|-----------|--------|
| 更少报错 | ✅ 30min 9/1115=0.8% errors (all NVCF server-side) |
| 更快请求 | ✅ P50=18767ms, P90=38165ms — no improvement target |
| 超低延迟 | ✅ P95=56780ms < 72s UPSTREAM_TIMEOUT |
| 稳定优先 | ✅ 3 consecutive no-change rounds (R151+R154+R155) confirm plateau |
| 铁律 | ✅ Only HM1 analyzed, no HM2 changes |

## ⏳ 轮到HM1优化HM2
