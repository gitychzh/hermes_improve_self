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
- 429 count: 0

### 1h Window
- Total: 1215, Success: 1209, Errors: 6, Fallbacks: 0
- Success rate: 99.5%

### 6h Window
- Total: 2034, Success: 2004, Errors: 30, Fallbacks: 0
- Success rate: 98.5%

### 24h ATE by Hour
- Total: 45, daytime concentration (82% in UTC 09:00-19:00) — NVCF server-side pattern (Pitfall #30)

## 🎯 优化分析

### 全7参数均衡评估

| Parameter | Current | Adjustment Needed? | Reason |
|-----------|---------|-------------------|--------|
| UPSTREAM_TIMEOUT | 70 | ❌ No | R158 validated; key p95 max=59980ms < 70s; ATE per-key avg=23.6s (NVCF-side, Pitfall #43) |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ No | 2×70=140, remaining=16s > 10s; R154 diminishing returns proven |
| KEY_COOLDOWN_S | 34.0 | ❌ No | 0 429s; no pressure to adjust |
| TIER_COOLDOWN_S | 38 | ❌ No | 4s KEY-TIER gap stable; R156 validated |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ❌ No | 81% util, 0 429s; sufficient |
| HM_CONNECT_RESERVE_S | 24 | ❌ No | No budget_exhausted_after_connect errors |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | ❌ No | No evidence of mis-sizing |

**Stability IS the optimal state** — all 7 params at equilibrium.

## 🔧 变更执行

**No changes.** R158 UPSTREAM_TIMEOUT=70 fully validated (2nd validation after R159).

## ⚖️ 评判标准
- ✅ 更少报错: 3 ATE/30min (NVCF server-side, unresolvable at config)
- ✅ 更快请求: P95=53205ms stable
- ✅ 超低延迟: No regression
- ✅ 稳定优先: Full equilibrium
- ✅ 铁律: 只改HM1不改HM2 — no changes to HM2

## ⏳ 轮到HM1优化HM2
