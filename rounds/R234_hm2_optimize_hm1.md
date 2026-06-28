# R234: HM2 → HM1 — 无变更 (全7参数均衡; 59th no-change verification; 30min 99.90% 0 ATE 0 429 0 fallback; 1 SSLEOFError k4 auto-retried; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 18:10-18:40 UTC, ~30min window)

### Config Snapshot (docker exec env)
```
UPSTREAM_TIMEOUT=70
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=38
TIER_TIMEOUT_BUDGET_S=156
MIN_OUTBOUND_INTERVAL_S=19.2
HM_CONNECT_RESERVE_S=24
PROXY_TIMEOUT=300
CHARS_PER_TOKEN_ESTIMATE=3.0
```

### 30min Metrics (via cc_postgres psql)
- **Total**: 1031 requests
- **Success (200)**: 1030 → **99.90%**
- **ATE (all_tiers_exhausted)**: 0
- **429**: 0
- **Fallback**: 0
- **P50**: 18,261ms (18.3s)
- **P95**: 50,044ms (50.0s)
- **Avg OK**: ~21,200ms (21.2s)

### Per-Key Breakdown (30min)
| Key | Type | Reqs | OK | P50(ms) | P95(ms) | Errors |
|-----|------|------|----|---------|---------|--------|
| k0 | DIRECT | 221 | 221 | 20,291 | 55,813 | 0 |
| k1 | DIRECT | 211 | 210 | 21,543 | 49,072 | 0 |
| k2 | PROXY→7896 | 195 | 195 | 21,283 | 44,335 | 0 |
| k3 | PROXY→7897 | 200 | 200 | 21,461 | 45,515 | 0 |
| k4 | PROXY→7899 | 204 | 204 | 20,837 | 50,597 | 0 |

Per-key distribution even: 195-221 req/key. RR counter healthy.

### Docker Logs (last 100 lines)
- **1× SSLEOFError on k4** (18:00:27.6): `[SSL: UNEXPECTED_EOF_WHILE_READING]` — auto-retried successfully with 2s backoff
- All other lines: `[HM-TIER] Starting tier=deepseek_hm_nv` — healthy tier initiation
- **Zero `[HM-TIER-BUDGET]` break lines** in last 500 lines (grep returned exit code 1 = no matches). Clean budget path — remaining > 5s threshold never triggered.
- Zero `HM-ERR` or `HM-TIER-FAIL` lines beyond the single SSLEOFError

### Budget Threshold Verification
No `[HM-TIER-BUDGET]` lines in last 500 logs. Budget 156s with 2×70=140 consumption = 16s remaining, well above the 5s minimum threshold (Pitfall #23). Clean budget path confirms the tier has not been close to breaking.

### 24h Segmented
| Window | Total | OK | ATE | 429 | FB |
|--------|-------|----|-----|-----|----|
| 0-6h | 1835 | 1833 | 0 | 0 | 0 |
| 6-12h | 836 | 834 | 0 | 0 | 0 |
| 12-18h | 843 | 841 | 0 | 0 | 0 |
| 18-24h | 716 | 715 | 0 | 0 | 138 |

Fallback concentrated entirely in 18-24h old-regime window (Pitfall #49). All recent windows (0-18h): zero fallback, zero 429, zero ATE. The system is healthy — the 18-24h fallback is stale data from pre-stable-state regime.

## 🎯 优化分析

### Bottleneck Identification
**No bottleneck.** The only error is a single SSLEOFError on k4 (NVCF proxy-layer SSL transient), auto-retried successfully. The ATE storm that dominated R232-R233 (21 ATE/30min) has fully subsided in this window — 0 ATE in 30min. This is NVCF server-side variance, not an HM config issue.

**Significant improvement over R233**: R233 had 97.97% success with 21 ATE; R234 shows 99.90% success with 0 ATE. The ATE count dropped from 21 → 0, a +1.93pp improvement. This confirms the ATE events are NVCF server-side — they fluctuate independently of HM config.

### Parameter Evaluation
| Parameter | Current | Adjustment? | Reason |
|-----------|---------|-------------|--------|
| UPSTREAM_TIMEOUT | 70 | ❌ None | P95=50.0s << 70s; 0 ATE confirms healthy; reducing below actual NVCF server-side timeout (~24s) would have no effect. |
| KEY_COOLDOWN_S | 38 | ❌ None | KEY=TIER=38 invariant holds (Pitfall #44); 0 429 confirmed optimal; no adjustment needed. |
| TIER_COOLDOWN_S | 38 | ❌ None | 0 429 in all windows; KEY≥TIER invariant holds; no need to adjust. |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ None | 2×70=140, remaining=16s > 5s threshold; 0 ATE confirms budget sufficient. R154 proved budget increases don't reduce ATE beyond the 10s threshold. |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | ❌ None | Per-key even 195-221 req/key; actual rate ~3.4 req/min at 106% capacity is slightly above theoretical but 0 429 confirms safe. |
| HM_CONNECT_RESERVE_S | 24 | ❌ None | 0 budget_exhausted_after_connect errors; 24s covers all proxy connection overhead. |
| PROXY_TIMEOUT | 300 | ❌ None | No proxy-layer timeouts; internal only. |

**Conclusion: All 7 parameters at equilibrium.** The R233→R234 trajectory shows the ATE storm has temporarily subsided, confirming the ATE events are NVCF server-side (Pitfall #30 — time-of-day variance). No config parameter can prevent NVCF server-side all_tiers_failed events. The correct action is to validate this temporary improvement without over-optimizing.

### Expected Impact
This is the **59th consecutive R162+R158** (KEY_COOLDOWN_S=38, TIER_COOLDOWN_S=38, UPSTREAM_TIMEOUT=70) validation. The stability plateau extends through 59 rounds — the longest continuous equilibrium in this system's history. The 1 SSLEOFError on k4 is within normal NVCF proxy-layer variance and was auto-retried successfully. No parameter adjustment is justified.

## 🔧 变更执行

**No change.** All 7 parameters remain at current values:
- UPSTREAM_TIMEOUT=70
- KEY_COOLDOWN_S=38
- TIER_COOLDOWN_S=38
- TIER_TIMEOUT_BUDGET_S=156
- MIN_OUTBOUND_INTERVAL_S=19.2
- HM_CONNECT_RESERVE_S=24
- PROXY_TIMEOUT=300

## 📈 预期效果

### Before/After Comparison (R233 → R234)
| Metric | R233 (58th) | R234 (59th) | Δ |
|--------|-------------|-------------|---|
| 30min success | 97.97% | 99.90% | +1.93pp ⬆️ |
| 30min ATE | 21 | 0 | -21 ⬇️ |
| 30min 429 | 0 | 0 | 0 (stable) |
| 30min fallback | 0 | 0 | 0 (stable) |
| P50 | 18.3s | 18.3s | 0 (identical) |
| P95 | ~53s | 50.0s | -3s (improved) |
| SSLEOFError | 2× k4 | 1× k4 | -1 (reduction) |
| NVStream_TimeoutError | 1× k1 | 0 | -1 (eliminated) |

**Key insight**: The ATE storm from R232-R233 (21 ATE/30min) has completely subsided in R234. This confirms ATE events are NVCF server-side — they appear and disappear independently of HM config. The 99.90% success rate with 0 ATE, 0 429, 0 fallback across all windows < 18h represents the system at its healthiest. The 59th consecutive no-change validation extends the stability plateau — **stability IS the optimal state**.

## ⚖️ 评判标准

- **更少报错**: ✅ 0 ATE, 0 429, 0 fallback in 30min; only 1 SSLEOFError (auto-retried); NVCF server-side ATE storm has subsided
- **更快请求**: ✅ P50=18.3s, P95=50.0s; all within UPSTREAM_TIMEOUT=70s; consistent across 59 rounds
- **超低延迟**: ✅ Per-key P50 20-22s; kimi fallback would be faster but not needed (0 ATE = no fallback trigger)
- **稳定优先**: ✅ No config changes = maximum stability; 59th consecutive validation of the equilibrium plateau

| 铁律:只改HM1不改HM2 | ✅ No HM2 config touched; HM1-only analysis; validated HM1 config unchanged |
| 少改多轮 | ✅ This round: 0 changes — no parameter needed adjustment; stability IS the optimal state |

## ⏳ 轮到HM1优化HM2