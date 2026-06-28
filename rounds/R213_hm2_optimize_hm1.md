# R213: HM2→HM1 — 无变更 (全7参数均衡; 30min 99.06% 12ATE全NVCFPexecTimeout+1NVStream 0 429 0 fallback; 39th consecutive R162+R158 validation; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (30min/1h/6h/24h 多窗口)

### Config Snapshot (HM1 hm40006)
```
UPSTREAM_TIMEOUT=70
TIER_TIMEOUT_BUDGET_S=156
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=38
MIN_OUTBOUND_INTERVAL_S=19.2
HM_CONNECT_RESERVE_S=24
PROXY_TIMEOUT=300
```

### Request Metrics
| Window | Total | Success | % | ATE | 429 | Fallback | P50 | P95 |
|--------|-------|---------|---|-----|-----|----------|-----|-----|
| 30min | 1176 | 1163 | 99.06% | 12 | 0 | 0 | 18.2s | 41.5s |
| 1h | 1247 | 1234 | 99.04% | 12 | 0 | 0 | 18.1s | 41.9s |
| 6h | 1946 | 1929 | 99.13% | 15 | 0 | 0 | 18.2s | 44.3s |

### 24h Segmented
| Segment | Total | Success | ATE | 429 | Fallback |
|---------|-------|---------|-----|-----|----------|
| 0-6h | 1944 | 1926 (99.07%) | 16 | 0 | 0 |
| 6-12h | 775 | 768 (99.10%) | 4 | 0 | 0 |
| 12-24h | 1764 | 1725 (97.79%) | 37 | 4 | 589 |

### Per-Key Distribution (30min)
| Key | Total | Success | Avg OK | P95 OK |
|-----|-------|---------|---------|---------|
| k0 | 243 | 243 | 19094ms | 44538ms |
| k1 | 232 | 231 | 20409ms | 44103ms |
| k2 | 226 | 226 | 19915ms | 36140ms |
| k3 | 231 | 231 | 19912ms | 39182ms |
| k4 | 232 | 232 | 20408ms | 39919ms |

### Error Detail JSONL (30min window)
All 12 ATE events show identical pattern:
- **deepseek_hm_nv**: 5-6 attempts, 141-156s elapsed, all NVCFPexecTimeout + empty_200 + budget_exhausted_after_connect
- **kimi_hm_nv**: num_attempts=0 across ALL events — zero budget for fallback
- NVCFPexecTimeout per-key: 5-60s (NVCF server-side timeout, far below UPSTREAM_TIMEOUT=70)
- budget_exhausted_after_connect at final attempt: 275ms-2751ms (insufficient budget for any kimi connection)
- Error types: all_tiers_exhausted=12, NVStream_TimeoutError=1

### Docker Logs (30min window)
```
[HM-TIMEOUT] deepseek_hm_nv k0-k4 NVCFPexecTimeout (5-60s per key)
[HM-TIER-FAIL] deepseek_hm_nv all 5 keys failed → falling back to kimi_hm_nv
[HM-ALL-TIERS-FAIL] All 2 tiers failed → ABORT-NO-FALLBACK (141-157s)
[HM-ERR] deepseek_hm_nv k3 SSLEOFError (auto-retry same key)
```

## 🎯 优化分析

### Bottleneck Identification
**NVCF server-side PexecTimeout storm** — all 5 deepseek keys experiencing NVCFPexecTimeout simultaneously (5-60s per key, total 141-156s consumed). The deepseek tier consumes the entire budget, leaving ZERO budget for kimi_hm_nv fallback. kimi num_attempts=0 across all 12 ATE events in 30min.

### Why No Change — Detailed Parameter Evaluation
| Parameter | Status | Reason |
|-----------|--------|--------|
| TIER_TIMEOUT_BUDGET_S=156 | ⚖️ Equilibrium | budget_exhausted_after_connect at 275-2751ms → not reserve issue, budget fully consumed by NVCF storms. Increasing further shows diminishing returns (R154 validated) |
| UPSTREAM_TIMEOUT=70 | ⚖️ Equilibrium | R158 validated through 39 rounds. Per-key P95=36-45s well below 70s. 3 ATE/30min at R158 when at 72s → 12 ATE at 70s is NVCF server-side, not timeout-driven |
| KEY_COOLDOWN_S=38 | ⚖️ Equilibrium | KEY=TIER=38 invariant holds (Pitfall #44). 0 429 in 0-12h |
| TIER_COOLDOWN_S=38 | ⚖️ Equilibrium | KEY≥TIER gap=0s confirmed optimal. 0 fallback in 0-12h |
| MIN_OUTBOUND_INTERVAL_S=19.2 | ⚖️ Equilibrium | Per-key even distribution (226-243). 0 back-to-back. RR counter perfect |
| HM_CONNECT_RESERVE_S=24 | ⚖️ Equilibrium | budget_exhausted_after_connect overhead 275-2751ms << 24s reserve |
| PROXY_TIMEOUT=300 | ⚖️ Equilibrium | No proxy-level errors in short windows |

### Why This Is NVCF Server-Side
1. All error detail JSONL shows NVCFPexecTimeout per-key at 5-60s (NVCF server rejects early, not HM-configured timeout)
2. Multiple keys fail simultaneously (server-side outage), not isolated key failures
3. Same pattern as previous NVCFPexecTimeout storms (R191, R198, R202 — all validated as server-side)
4. Budget consumption: 5-6 keys × ~5-60s timeouts = 141-156s consumed → 0 remaining for kimi
5. 24h segmented: 0-12h = 0 fallback, 12-24h = 589 fallback (old-regime data, Pitfall #49)

## ⚖️ 评判标准

- **更少报错**: 30min 12 ATE (NVCF server-side), 0 429, 0 fallback in recent windows → ✅ NVCF server-side errors cannot be fixed by HM config
- **更快请求**: P50=18.2s, P95=41.5s → ✅ Stable at R208-R212 levels
- **超低延迟**: Per-key P95 under 45s across all keys → ✅ All well within config bounds
- **稳定优先**: 39th consecutive R162+R158 validation, all 7 params at equilibrium → ✅ Stability plateau confirmed
- **铁律**: 只改HM1不改HM2 → ✅ No HM2 local config touched

## ⏳ 轮到HM1优化HM2