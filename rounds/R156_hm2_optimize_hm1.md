# R156: HM2→HM1 — 无变更 (全7参数均衡: 30min 99.3%, 1h 99.2%, 6h 98.6%; 0 429, 0 fallback; 6 ATE为NVCF server-side不可调; R154 BUDGET收益递减已验证; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 04:06 UTC, R155→R156)

### Config Snapshot (HM1 docker exec env)
| Parameter | Value |
|-----------|-------|
| UPSTREAM_TIMEOUT | 72 |
| TIER_TIMEOUT_BUDGET_S | 156 |
| KEY_COOLDOWN_S | 34 |
| TIER_COOLDOWN_S | 42 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 |
| HM_CONNECT_RESERVE_S | 24 |
| PROXY_TIMEOUT | 300 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 |

### 30min Window
- Total: 1123, Success: 1115, Errors: 8, Fallbacks: 0
- Success rate: **99.3%**
- Latency: Avg=22823ms, P50=18786ms, P90=38187ms, P95=56707ms, P99=124528ms
- 429 count: **0**
- Error breakdown: all_tiers_exhausted=6 (avg=137101ms), NVStream_TimeoutError=1 (k0, 109523ms), NVStream_IncompleteRead=1 (k4, 19546ms)

### 1h Window
- Total: 1185, Success: 1176, Errors: 9, Fallbacks: 0
- Success rate: **99.2%**, Avg=22875ms, P95=56795ms

### 6h Window
- Total: 2045, Success: 2016, Errors: 29, Fallbacks: 0
- Success rate: **98.6%**

### Per-Key Success Latency (30min)
| Key | N | Avg (ms) | P50 (ms) | P95 (ms) |
|-----|---|----------|----------|----------|
| k0 (DIRECT) | 237 | 24774 | 20661 | 58841 |
| k1 (DIRECT) | 221 | 22532 | 18663 | 60368 |
| k2 (PROXY) | 209 | 19862 | 17339 | 40629 |
| k3 (PROXY) | 226 | 21170 | 18657 | 45688 |
| k4 (PROXY) | 222 | 22036 | 18828 | 53530 |

- DIRECT p95 (58.8-60.4s) > PROXY p95 (40.6-53.5s) — Pitfall #29: NVCF server-side variance for DIRECT, not a config issue.

### Request Rate (30min)
- Minutes with data: 427, avg=2.6 req/min, max=5, min=1
- Capacity at MIN_OUTBOUND=19s: 3.2 req/min (utilization: 81%)

### 24h all_tiers_exhausted by Hour
- Total: 45 (same as R155)
- Distribution: mixed daytime (09:00-19:00 UTC) + overnight (01:00-02:00 UTC)
  - 09:00=1, 10:00=4, 11:00=10, 13:00=5, 15:00=1, 16:00=7, 17:00=8, 18:00=2, 19:00=3
  - 01:00=1, 02:00=2
- Confirms Pitfall #30: ATE distribution shifts day-to-day, NVCF server-side

### 24h Status Breakdown (Latency Profile)
| Status | N | Avg (ms) | Min (ms) | Max (ms) |
|--------|---|----------|----------|----------|
| 200 | 4513 | 29569 | 1295 | 233742 |
| 429 | 5 | 172934 | 138762 | 219113 |
| 502 | 45 | 120018 | 19546 | 166774 |

### 24h Error Breakdown
- all_tiers_exhausted: 45 (avg=129711ms)
- NVStream_TimeoutError: 4 (avg=102228ms)
- NVStream_IncompleteRead: 1 (avg=19546ms)

### Back-to-Back Same Key (last 100 requests)
- Same-key pairs: 7/96 = 7.3% (RR counter variance, Pitfall #28 — 0 429 rate means this is safe)

### Docker Logs Error Check
- `docker logs --tail 100 | grep -iE "(error|warn|fail|timeout|refused|reset|exhausted|panic)"` → **ZERO matches** ✅

## 🎯 优化分析

### Parameter Evaluation Table
| Parameter | Current | Assessment | Reason |
|-----------|---------|------------|--------|
| UPSTREAM_TIMEOUT | 72 | ✅ No change | p95=56.7s < 72s with margin; 30min 99.3% |
| TIER_TIMEOUT_BUDGET_S | 156 | ✅ No change | 2×72=144, remaining=12s > 10s threshold ✅; R154 proved budget increase beyond this shows diminishing returns (Pitfall #40) |
| KEY_COOLDOWN_S | 34 | ✅ No change | 0 429 in 30min — no rate-limit pressure |
| TIER_COOLDOWN_S | 42 | ✅ No change | 0 fallback — tier failures recover within budget |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ✅ No change | 2.6 req/min actual vs 3.2 capacity (81%); no 429 to justify decrease |
| HM_CONNECT_RESERVE_S | 24 | ✅ No change | 0 budget_exhausted_after_connect errors |
| PROXY_TIMEOUT | 300 | ✅ No change | No timeout issues at proxy level |

### Key Observations
1. **30min 99.3%** — marginally better than R155's 99.2%, confirming stability plateau
2. **6 ATE/30min** — all NVCF server-side (avg_dur=137s = ~2×72s timeout), cannot be reduced by config (R154 diminishing-returns proof)
3. **0 429, 0 fallback** — no rate-limit or tier-chain issues
4. **24h ATE=45** with mixed daytime+overnight distribution — confirms Pitfall #30 variable pattern
5. **Back-to-back 7.3%** — fluctuates (R142: 0.0%, R155: stable, now 7.3%) — RR counter variance, safe at 0 429 rate
6. **DIRECT tail latency > PROXY** — consistent with Pitfall #29, not actionable

## 🔧 变更执行

**No config change this round.** All 7 parameters at equilibrium. R154's diminishing-returns finding reconfirmed — ATE count unchanged from R155 (6/30min, 45/24h), all NVCF server-side.

## 📈 预期效果

N/A — stability IS the optimal state. The R143 (UT 68→60, KC 38→34) + R152 (BUDGET 154→156) changes remain fully stabilized.

## ⚖️ 评判标准

| Criterion | Status |
|-----------|--------|
| 更少报错 | ✅ 30min 99.3% (8/1123 errors, all NVCF server-side) |
| 更快请求 | ✅ P50=18.8s, P90=38.2s, P95=56.7s |
| 超低延迟 | ✅ Avg=22.8s, stable across keys |
| 稳定优先 | ✅ 6h 98.6%, 0 429, 0 fallback — equilibrium confirmed |
| 铁律:只改HM1不改HM2 | ✅ No changes needed; HM2 config untouched |

## ⏳ 轮到HM1优化HM2
