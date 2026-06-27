# R160: HM2→HM1 — 无变更 (全7参数均衡; R158 UPSTREAM_TIMEOUT=70第2次验证; 30min 99.5%, 0 429, 0 fallback; 3 ATE仍为NVCF server-side PexecTimeout风暴不可调; kimi fallback starvation Pitfall#41持续; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 05:00 UTC, R158 UPSTREAM_TIMEOUT=70部署后>24h)

### Config Snapshot (HM1 hm40006)
| Parameter | Value |
|-----------|-------|
| UPSTREAM_TIMEOUT | 70 |
| TIER_TIMEOUT_BUDGET_S | 156 |
| KEY_COOLDOWN_S | 34.0 |
| TIER_COOLDOWN_S | 38 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 |
| HM_CONNECT_RESERVE_S | 24 |
| PROXY_TIMEOUT | 300 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 |

### 30min Window
- Total: 1158, Success: 1152, Errors: 6, Fallbacks: 0
- Success rate: 99.5%
- Avg: 22423ms, P50: 18763ms, P90: 37948ms, P95: 53205ms, P99: 103228ms
- Error breakdown:
  - all_tiers_exhausted: 3, avg=145154ms
  - NVStream_IncompleteRead: 2, avg=13187ms
  - NVStream_TimeoutError: 1, avg=109523ms
- Per-key errors: k0: NVStream_TimeoutError×1, k3: NVStream_IncompleteRead×1, k4: NVStream_IncompleteRead×1
- 429 count: 0
- key_cycle_429s: 0-cycles=1144, 1-cycles=13, 5-cycles=1

### 30min Per-Key Success Latency
| Key | n | avg_ms | p50_ms | p95_ms |
|-----|---|--------|--------|--------|
| k0 | 241 | 24499 | 20274 | 58433 |
| k1 | 227 | 22969 | 18921 | 59980 |
| k2 | 218 | 19712 | 17400 | 38926 |
| k3 | 234 | 20752 | 18549 | 43749 |
| k4 | 232 | 22085 | 18850 | 54990 |

- DIRECT tail latency (k0 p95=58433, k1 p95=59980) > PROXY (k2-k4 p95=38926-54990) — Pitfall #29 confirmed, NVCF server-side variance

### 30min Request Rate
- Minutes with data: 439, max: 5 req/min, min: 1, avg: 2.6 req/min
- Capacity at MIN_OUTBOUND=19s: 3.2 req/min (81% utilized)

### 1h Window
- Total: 1215, Success: 1209, Errors: 6, Fallbacks: 0
- Success rate: 99.5%, Avg: 22461ms, P95: 53324ms

### 6h Window
- Total: 2034, Success: 2004, Errors: 30, Fallbacks: 0
- Success rate: 98.5%

### Back-to-Back Same Key (last 100)
- Total pairs: 99, Same-key pairs: 3, Rate: 3.0% (within normal range, RR counter quirk)

### 24h Status Breakdown (Latency Profile)
| Status | n | avg_ms | min_ms | max_ms |
|--------|---|--------|--------|--------|
| 200 | 4502 | 29650 | 1295 | 233742 |
| 429 | 5 | 172934 | 138762 | 219113 |
| 502 | 46 | 117557 | 6827 | 166774 |

### 24h Error Breakdown
- all_tiers_exhausted: 45, avg=129711ms
- NVStream_TimeoutError: 4, avg=102228ms
- NVStream_IncompleteRead: 2, avg=13187ms

### 24h ATE by Hour
- Total: 45
- 2026-06-27 10:00-11:00: 4, 11:00-12:00: 10, 13:00-14:00: 5, 16:00-17:00: 7, 17:00-18:00: 8, 18:00-19:00: 2, 19:00-20:00: 3
- 2026-06-28 01:00-02:00: 1, 02:00-03:00: 2
- **Daytime concentration continues** (37/45 = 82% in UTC 09:00-19:00 on 6/27) — variable NVCF server-side pattern (Pitfall #30)

### Error Detail JSONL (2026-06-28)
- 3 ATE events all show: deepseek_hm_nv num_attempts=6, elapsed_ms=141-146s; kimi_hm_nv num_attempts=0
- **Kimi fallback starvation confirmed** (Pitfall #41): deepseek consumes full budget before kimi can attempt
- Per-key NVCF timeout avg = ~23568ms (141409/6) — far below UPSTREAM_TIMEOUT=70 (Pitfall #43)
- These ATE are NVCF server-side PexecTimeout storms, not HM config issues

### Docker Logs (last 30 lines)
- Clean: all `[HM-SUCCESS]` entries, zero error/warn/fail/timeout lines
- Key round-robin working correctly: k3→k4→k5→k1→k2→k3

## 🎯 优化分析

### 全7参数均衡评估

| Parameter | Current | Adjustment Needed? | Reason |
|-----------|---------|-------------------|--------|
| UPSTREAM_TIMEOUT | 70 | ❌ No | R158 -2s validated; key p95 max=59980ms < 70s; ATE per-key avg=23.6s (NVCF-side, not HM-limited, Pitfall #43) |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ No | 2×70=140, remaining=16s > 10s threshold; R154 proved budget increases show diminishing returns beyond threshold; 3 ATE/30min unchanged from R159 → budget margin sufficient |
| KEY_COOLDOWN_S | 34.0 | ❌ No | 0 429s in 30min; 429 rate at 0% → no pressure to adjust; decreasing would risk 429s, increasing would waste key recovery time |
| TIER_COOLDOWN_S | 38 | ❌ No | KEY=34 stable with 0 429s; 4s KEY-TIER gap provides symmetric safety margin; R156 validated this gap |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ❌ No | Capacity 3.2 req/min, actual 2.6 (81% util); no 429s showing interval is sufficient; decreasing risks 429s at peak |
| HM_CONNECT_RESERVE_S | 24 | ❌ No | No budget_exhausted_after_connect errors in 30min |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | ❌ No | No evidence of mis-sizing |

### Summary
- All 7 parameters at equilibrium — no single parameter adjustment would improve any bottleneck
- 3 ATE/30min are entirely NVCF server-side PexecTimeout storms (Pitfall #41, #43): deepseek keys timeout at ~24s per key (well below HM UPSTREAM_TIMEOUT=70), consuming the full tier budget before kimi can attempt
- This is an **unresolvable-at-config-level** issue — the proxy code would need per-tier budget splitting (code change, not config)
- R154 proved budget increases beyond the 10s threshold show zero ATE reduction (diminishing returns, Pitfall #40)
- **Stability IS the optimal state** — a no-change round is the correct action

## 🔧 变更执行

**No changes.** All 7 parameters remain at their current values. This is the 2nd validation of R158's UPSTREAM_TIMEOUT=70 change (R159 was the 1st).

## 📈 预期效果

| Metric | Before (R159) | Now (R160) | Change |
|--------|--------------|------------|--------|
| 30min success | 99.5% | 99.5% | ✅ Stable |
| 30min ATE | 3 | 3 | ✅ Stable (NVCF-side) |
| 30min 429 | 0 | 0 | ✅ Stable |
| 30min fallback | 0 | 0 | ✅ Stable |
| 1h success | 99.5% | 99.5% | ✅ Stable |
| 6h success | 98.5% | 98.5% | ✅ Stable |

## ⚖️ 评判标准
- ✅ 更少报错: 3 ATE/30min unchanged (NVCF server-side, unresolvable at config)
- ✅ 更快请求: P95=53205ms stable, no regression
- ✅ 超低延迟: Success path latency unchanged
- ✅ 稳定优先: All 7 params at equilibrium, R158 fully validated
- ✅ 铁律: 只改HM1不改HM2 — confirmed, no changes to HM2

## ⏳ 轮到HM1优化HM2
