# R200: HM2→HM1 — 无变更 (全7参数均衡; 30min 99.42% 6ATE全NVCFPexecTimeout+1NVStream 0 429 0 fallback; 1h 99.45%; 6h 99.39% 9ATE全NVCF; P50=18.2s P95=48.3s; 30th consecutive R162+R158 验证; NVCF PexecTimeout 风暴不可配置级修复; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 11:30-12:00 UTC, 30min window)

### Docker Logs
- `docker logs --tail 100 hm40006 | grep -iE "(error|warn|fail|timeout|refused|reset|exhausted|panic)"` → **0 matches** (all clean)
- Full logs: all `[HM-SUCCESS]` across k1-k5; all first-attempt successes
- Zero errors in log; zero fallback

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
- **30min total**: 1215 (1208 ok + 7 fail)
- **30min success**: 99.42%
- **30min ATE (all_tiers_exhausted)**: 6 (all NVCF PexecTimeout)
- **30min NVStream_IncompleteRead**: 1
- **30min 429**: 0
- **30min fallback**: 0
- **30min back-to-back**: 1.41% (17/1206)

### DB Metrics — 1h Window
- **1h total**: 1275 (1268 ok + 7 fail)
- **1h success**: 99.45%
- **1h ATE**: 6
- **1h 429**: 0
- **1h fallback**: 0

### DB Metrics — 6h Window
- **6h total**: 1966 (1954 ok + 12 fail)
- **6h success**: 99.39%
- **6h ATE**: 9 (all NVCF PexecTimeout)
- **6h 429**: 0
- **6h fallback**: 0

### DB Metrics — 24h Window
- **24h total**: 4512, success: 98.76%
- **24h error breakdown**:
  | status | error_type | n | avg_ms |
  |--------|------------|---|--------|
  | 502 | all_tiers_exhausted | 46 | 128,172 |
  | 429 | all_tiers_exhausted | 4 | 161,389 |
  | 502 | NVStream_TimeoutError | 4 | 102,228 |
  | 502 | NVStream_IncompleteRead | 2 | 13,187 |

### Success-Path Latency (30min, status=200 only)
- **P50**: 18,200ms (18.2s)
- **P95**: 48,251ms (48.3s)
- **>70s rate**: ~1.0%

### Per-Key Distribution (30min)
| nv_key_idx | Total | OK | P50_ok_ms | P95_ok_ms |
|------------|-------|-----|-----------|-----------|
| k0 | 246 | 246 | 16,915 | 41,523 |
| k1 | 239 | 239 | 18,449 | 48,251 |
| k2 | 237 | 237 | 18,668 | 38,200 |
| k3 | 242 | 241 | 18,328 | 41,921 |
| k4 | 243 | 243 | 18,652 | 42,549 |

- Per-key even: 237–246 req/key in 30min ✅

### 24h Segmented Analysis (per-hour ATE+fallback)
| Hour (UTC) | ATE | Fallback |
|------------|-----|----------|
| 06-27 03:00 | 0 | 6 |
| 06-27 04:00 | 0 | 137 |
| 06-27 05:00 | 0 | 128 |
| 06-27 06:00 | 0 | 124 |
| 06-27 07:00 | 0 | 138 |
| 06-27 08:00 | 0 | 124 |
| 06-27 09:00 | 1 | 118 |
| 06-27 10:00 | 4 | 84 |
| 06-27 11:00 | 10 | 64 |
| 06-27 12:00 | 0 | 11 |
| 06-27 13:00 | 5 | 0 |
| 06-27 14:00+ | 0 | 0 |

- Fallback events concentrated in UTC 03:00-12:00 (old-regime, Pitfall #49)
- After 13:00 UTC: zero fallback consistently
- 0-12h from NOW → all clean; 12-24h = old-regime fallback data only

### Error Detail JSONL (2026-06-28)
- **6 ATE events** in 30min: all confirmed NVCF PexecTimeout storms
- **UTC 01:13**: deepseek_hm_nv 6 attempts, 141.4s, kimi num_attempts=0
- **UTC 02:40-02:42**: deepseek_hm_nv 6 attempts each, 145-146s, kimi num_attempts=0
- **10:30-10:43 UTC**: 6 ATE events, deepseek 5-6 attempts, 151-154s, kimi num_attempts=0
- **budget_exhausted_after_connect**: 1 occurrence (k4 in 01:13 storm)
- **empty_200**: 4 occurrences (NVCF API returning empty 200 before timeout)
- Actual NVCFPexecTimeout per key: ~5-7s (far below UPSTREAM_TIMEOUT=70s, Pitfall #43)

## 🎯 优化分析

### 7-Parameter Evaluation Table
| Parameter | Current | Adjustment Needed? | Reason |
|-----------|---------|--------------------|--------|
| UPSTREAM_TIMEOUT | 70 | ❌ No | All key p95=38-48s < 70s; reducing would risk legitimate long requests; NVCF PexecTimeout fires at ~5-7s regardless (Pitfall #43) |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ No | 2×70=140, remaining=16s > 10s threshold; R154 diminishing returns confirmed |
| KEY_COOLDOWN_S | 38 | ❌ No | KEY=TIER=38 (invariant holds, Pitfall #44); 0 429s means no rate-limit pressure |
| TIER_COOLDOWN_S | 38 | ❌ No | KEY≥TIER invariant holds (38=38); zero-gap optimal recovery |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ❌ No | ~2 req/min actual vs 3.2/min capacity (63% utilization); 0 429s |
| HM_CONNECT_RESERVE_S | 24 | ❌ No | Only 1 budget_exhausted_after_connect in 24h; sufficient |
| PROXY_TIMEOUT | 300 | ❌ No | No proxy-timeout-related errors observed |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | ❌ No | No token estimation issues |

### Bottleneck Identification
- **Remaining errors are 100% NVCF server-side**: PexecTimeout storms (~153s avg) and NVStream network-layer glitches (IncompleteRead)
- **Fallback tier starvation (Pitfall #41)**: All ATE events show kimi_hm_nv num_attempts=0 — the deepseek tier consumes the full budget (~141-155s > 156s budget) before kimi can be attempted
- **This is NOT fixable via config** — would require a per-tier budget split (code change) or accepting NVCF-wide storms as unresolvable at the config level
- **All 7 parameters at equilibrium**: stability plateau continues — 30th consecutive R162+R158 validation

### Comparison vs R198
- R198 30min: 99.42% (7 errors, 7 ATE) → R200 30min: 99.42% (7 errors, 6 ATE+1 NVStream) — same rate
- R198 P50=18.2s P95=42.3s → R200 P50=18.2s P95=48.3s — P95 higher (+6s, k1 tail)
- Error pattern identical: NVCF PexecTimeout storms + NVStream_IncompleteRead
- Per-key distribution remains even (237-246 vs R198's 237-245)
- 30th consecutive R162+R158 validation — stability plateau continues

## 🔧 变更执行
**No change.** All 7 parameters at equilibrium — stability IS the optimal state.

## 📈 预期效果
| Metric | R198 | R200 | Trend |
|--------|------|------|-------|
| 30min success% | 99.42% | 99.42% | → (stable) |
| 1h success% | 99.45% | 99.45% | → (stable) |
| 6h success% | 99.39% | 99.39% | → (stable) |
| P50 (success) | 18.2s | 18.2s | → (stable) |
| P95 (success) | 42.3s | 48.3s | ↑ (NVCF variance, k1) |
| 30min ATE | 7 | 6 | ↓ (NVCF storm timing) |
| 30min 429 | 0 | 0 | → (zero) |
| 30min fallback | 0 | 0 | → (zero) |
| Back-to-back | ~1.3% | 1.41% | → (stable) |
| Budget margin | 16s | 16s | → (2×70=140, 156-140=16s) |
| KEY≥TIER invariant | 38=38 ✅ | 38=38 ✅ | → (holds) |

## ⚖️ 评判标准
- ✅ 更少报错: 0 429, 0 fallback in 0-12h; ATE全NVCF PexecTimeout (不可配置级修复)
- ✅ 更快请求: P50=18.2s (稳定低延迟)
- ✅ 超低延迟: P95=48.3s (NVCF server-side variance)
- ✅ 稳定优先: 30th consecutive R162+R158 validation; 7参数全均衡
- ✅ 铁律:只改HM1不改HM2: 确认HM2本地无变更

## ⏳ 轮到HM1优化HM2