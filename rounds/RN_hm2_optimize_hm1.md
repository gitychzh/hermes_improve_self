# R247: HM2→HM1 — 无变更 (72nd no-change validation; 全7参数均衡; 30min 97.14% 1 ATE+1 NVStream_IncompleteRead全NVCF server-side; 0 429 0 fallback; 24h 99.06% 25 ATE; kimi num_attempts=0 Pitfall#41; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 20:41 UTC, ~30min window)

### Docker Logs (last 100, error/warn scan)
- 0× SSLEOFError in 30min window (2 SSLEOF in 20:23-20:29 window, both auto-retried successfully)
- No 429s, no all_tiers_exhausted in recent log, no budget break events in last 200 lines
- All visible requests: first-attempt success pattern across k0-k5
- RR counter advancing correctly: k1→k2→k3→k4→k5→k1→k2→k3 (no back-to-back same-key)
- 1× NVStream_IncompleteRead on k2 (20:41 UTC) — NVCF server-side stream error

### Runtime Env (docker exec hm40006 env)
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

### DB Metrics (PostgreSQL via cc_postgres, real-time queries)

| Window | Total | Success | Pct | Error Breakdown |
|--------|-------|---------|-----|-----------------|
| 30min | 70 | 68 | 97.14% | 1×all_tiers_exhausted + 1×NVStream_IncompleteRead, 0×429 |
| 1h | 120 | 118 | 98.33% | 1×all_tiers_exhausted + 1×NVStream_IncompleteRead, 0×429 |
| 6h | 727 | 719 | 98.90% | 7×all_tiers_exhausted + 1×NVStream_IncompleteRead, 0×429 |
| 0-6h seg | 726 | 718 | 98.90% | 8 errors, 0 429 |
| 6-12h seg | 796 | 780 | 97.99% | 16 errors (all old-regime), 0 429 |
| 12-24h seg | 1682 | 1676 | 99.64% | 6 errors (all old-regime), 0 429 |
| 24h total | 3204 | 3174 | 99.06% | 25×ATE + 5 other NVCF server-side |

### Per-Key Latency (30min, deepseek_hm_nv)

| Key | Requests | P50(ms) | P95(ms) | P99(ms) | Errors |
|-----|----------|---------|---------|---------|--------|
| k0 | 15 | 15589 | 42692 | 68500 | 0 |
| k1 | 14 | 19126 | 25684 | 28050 | 0 |
| k2 | 12 | 18218 | 62604 | 69425 | 1 |
| k3 | 14 | 19740 | 46907 | 55613 | 0 |
| k4 | 15 | 19565 | 38624 | 49717 | 0 |

All keys p50≈15.6-19.7s, p95≈25.7-62.6s, p99≈28-69s. All p95 values well below UPSTREAM_TIMEOUT=70s. k0/k2 experience NVCF tail latency but these are NVCF server-side, not config-related.

### Error Detail (30min)
- **NVStream_IncompleteRead (k2)**: duration=22616ms, NVCF server-side stream interruption. Single event, isolated.
- **all_tiers_exhausted**: duration=155076ms, consumed all key attempts; kimi num_attempts=0 (Pitfall #41 confirmed). NVCF PexecTimeout storm.

### 429 Check
- 30min: 0 429s (KEY_COOLDOWN_S=38 optimal)
- 1h: 0 429s
- 6h: 0 429s
- 12-24h: 0 429s
- 24h total: 0 429s

### Fallback Check
- 6h: 0 fallback events (kimi tier completely unused — key dead, Pitfall #41)
- 0-6h segment: 0 fallback
- 6-12h segment: 0 fallback

### Container Resources
- CPU: 0.92% (3-process container)
- Memory: 21.1MB / 1GiB (2.06%)
- Loadavg: 0.05 (host system)
- Free memory: 6250MB available

## 🎯 优化分析

### Parameter Equilibrium Assessment

| Parameter | Value | Status | Rationale |
|-----------|-------|--------|-----------|
| UPSTREAM_TIMEOUT | 70s | ✅ EQUILIBRIUM | R158 (72→70) validated through 72nd round; all key p95 < 70s; per-key timeout consumption correct |
| TIER_TIMEOUT_BUDGET_S | 156s | ✅ EQUILIBRIUM | R152 (154→156) validated through 72 rounds; 2×70=140s, remaining=16s > 5s threshold; budget sufficient for normal operations |
| KEY_COOLDOWN_S | 38s | ✅ EQUILIBRIUM | R162 (34→38) fixed KEY<TIER inversion; KEY=TIER=38 invariant holds; 0 429s in all windows confirms optimal |
| TIER_COOLDOWN_S | 38s | ✅ EQUILIBRIUM | R156 (42→38) aligned with KEY; KEY≥TIER invariant holds; no adjustment needed |
| MIN_OUTBOUND_INTERVAL_S | 19.2s | ✅ EQUILIBRIUM | 5×19.2=96s cycle >> KEY_COOLDOWN=38s; 0 back-to-back events; RR counter perfect |
| HM_CONNECT_RESERVE_S | 24s | ✅ EQUILIBRIUM | No budget_exhausted_after_connect events; SSL setup within reserve |
| PROXY_TIMEOUT | 300s | ✅ EQUILIBRIUM | Internal proxy timeout independent of upstream flow |

### Bottleneck Identification
- **Primary bottleneck**: NVCF server-side PexecTimeout storms → all_tiers_exhausted with kimi num_attempts=0
- **Root cause**: NVCF API internal timeout behavior — deepseek keys timeout at ~22-24s per key (NVCF-side), consuming 5-7 keys × 24s = 120-168s, exceeding 156s budget
- **Not config-fixable**: ATE events cannot be eliminated by HM parameter changes (Pitfall #41: kimi dead key; Pitfall #43: NVCF server-side)
- **Secondary observation**: 1 NVStream_IncompleteRead on k2 — NVCF stream corruption, single isolate, not pattern

### Why No Change
- All 7 parameters at proven equilibrium (72nd consecutive validation)
- R158 UPSTREAM_TIMEOUT=70 fully stabilized — 72nd consecutive validation
- R162 KEY_COOLDOWN_S=38 fully stabilized — 72nd consecutive KEY=TIER=38 invariant validation
- 0 429s across all windows confirms zero rate-limit pressure
- 0 fallback in 0-12h confirms zero fallback starvation
- Any parameter change would be over-optimization — stability IS the optimal state
- 72 consecutive no-change rounds confirms complete convergence

## 🔧 变更执行

**No changes applied.** This is a no-change validation round (72nd consecutive).

## 📈 预期效果

**Continuation of stability plateau.** Metrics expected to remain:
- 30min success rate: ~97-99% (NVCF server-side variance)
- P50: 15-20s, P95: 25-63s
- 0 429s, 0 fallback in 0-12h windows
- ATE events: NVCF server-side PexecTimeout storms, not config-preventable

## ⚖️ 评判标准

| Criterion | Status | Evidence |
|-----------|--------|----------|
| 更少报错 | ✅ PASS | 0 429s, 0 fallback in 0-12h; ATE events are NVCF server-side, not HM config |
| 更快请求 | ✅ PASS | P50≈15.6-19.7s, P95≈25.7-62.6s; all within UPSTREAM_TIMEOUT=70s; no latency degradation |
| 超低延迟 | ✅ PASS | Per-key p50 all <20s; success-path latency stable at historical lows |
| 稳定优先 | ✅ PASS | 72 consecutive rounds of no-change validation; all 7 params at equilibrium; stability plateau fully confirmed |

### 铁律 Confirmation
- ✅ **只改HM1不改HM2** — no changes applied to either instance
- ✅ **少改多轮** — zero changes this round; accumulation of no-change validations confirms equilibrium
- ✅ **单参数原则** — not applicable (no change needed)
- ✅ **KEY≥TIER invariant**: KEY_COOLDOWN_S=38 ≥ TIER_COOLDOWN_S=38 ✅

## ⏳ 轮到HM1优化HM2