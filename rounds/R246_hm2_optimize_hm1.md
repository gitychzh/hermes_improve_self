# R246: HM2 → HM1 — 无变更 (71st no-change validation; 全7参数均衡; 30min 98.35% 16 ATE全NVCF server-side; 0 429 0 fallback; 24h 0-12h=0fb+0 429; kimi num_attempts=0 Pitfall#41; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 20:30 UTC, ~30min window)

### Docker Logs (last 100, error/warn scan)
- 2× SSLEOFError on k3/k4 (20:23:56 + 20:29:55), both auto-retried successfully
- No 429s, no all_tiers_exhausted in recent log, no budget break events in last 50 lines
- All visible requests: first-attempt success pattern across k1-k5
- RR counter advancing correctly: k1→k2→k3→k4(SSLEOF)→k5→k5→k1→k2→k3 (no back-to-back same-key on retry paths)

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

### DB Metrics (hm_requests, PostgreSQL via cc_postgres)

| Window | Total | Success | Pct | Error Breakdown |
|--------|-------|---------|-----|-----------------|
| 30min | 1028 | 1011 | 98.35% | 16×all_tiers_exhausted + 1×NVStream_TimeoutError, 0×429 |
| 1h | 1092 | 1075 | 98.44% | 16×all_tiers_exhausted + 1×NVStream_TimeoutError, 0×429 |
| 6h | 1817 | 1794 | 98.73% | 22×all_tiers_exhausted + 1×NVStream_TimeoutError, 0×429 |
| 0-6h seg | 852 | 844 | 99.06% | 0 fallback, 0 429 |
| 6-12h seg | 842 | 838 | 99.52% | 0 fallback, 0 429 |
| 12-24h seg | 1730 | 1699 | 98.21% | 0 fallback, 0 429 (all old-regime) |
| 24h total | 4388 | 4330 | 98.68% | ~45 ATE all NVCF server-side |

### Per-Key Latency (30min, deepseek_hm_nv)

| Key | Requests | P50(ms) | P95(ms) | P99(ms) | Errors |
|-----|----------|---------|---------|---------|--------|
| k1 | 214 | 17221 | 57499 | 100925 | 0 |
| k2 | 211 | 18403 | 60493 | 117112 | 1 |
| k3 | 187 | 19873 | 46215 | 71209 | 0 |
| k4 | 194 | 18932 | 57056 | 84919 | 0 |
| k5 | 206 | 18153 | 48331 | 70264 | 0 |

All keys p50≈17-20s, p95≈42-61s, p99≈70-117s. All p95 values below UPSTREAM_TIMEOUT=70s for most keys; k1/k2 p99 slightly above but these are success-path NVCF server-side tail latency (not HM config-related).

### Error Detail JSONL (confirmed kimi num_attempts=0)
5 ATE events sampled (15:16 - 20:17 UTC):
- All deepseek_hm_nv consumed 5-7 key attempts, elapsed 154-155s
- kimi_hm_nv num_attempts=0 in every event (Pitfall #41 confirmed)
- budget consumed: 5-7×70=350-490s → far exceeds 156s budget
- These are NVCF server-side PexecTimeout storms, not config-preventable

### 429 Check
- 30min: 0 429s (KEY_COOLDOWN_S=38 optimal)
- 1h: 0 429s
- 6h: 0 429s
- 12-24h: 0 429s
- 24h total: 0 429s

## 🎯 优化分析

### Parameter Equilibrium Assessment

| Parameter | Value | Status | Rationale |
|-----------|-------|--------|-----------|
| UPSTREAM_TIMEOUT | 70s | ✅ EQUILIBRIUM | R158 (72→70) validated through 71st consecutive round; all key p95 < 70s; per-key timeout consumption correct |
| TIER_TIMEOUT_BUDGET_S | 156s | ✅ EQUILIBRIUM | R152 (154→156) validated through 70+ rounds; 2×70=140s, remaining=16s > 5s threshold; budget sufficient for normal operations |
| KEY_COOLDOWN_S | 38s | ✅ EQUILIBRIUM | R162 (34→38) fixed KEY<TIER inversion; KEY=TIER=38 invariant holds; 0 429s in all windows confirms no rate-limit pressure |
| TIER_COOLDOWN_S | 38s | ✅ EQUILIBRIUM | R156 (42→38) aligned with KEY; KEY≥TIER invariant holds; no adjustment needed |
| MIN_OUTBOUND_INTERVAL_S | 19.2s | ✅ EQUILIBRIUM | 5×19.2=96s cycle >> KEY_COOLDOWN=38s; 0 back-to-back events in recent logs; RR counter perfect |
| HM_CONNECT_RESERVE_S | 24s | ✅ EQUILIBRIUM | No budget_exhausted_after_connect events; SSL setup completed within reserve |
| PROXY_TIMEOUT | 300s | ✅ EQUILIBRIUM | Internal proxy timeout independent of upstream flow |

### Bottleneck Identification
- **Primary bottleneck**: NVCF server-side PexecTimeout storms → all_tiers_exhausted with kimi num_attempts=0
- **Root cause**: NVCF API internal timeout behavior — deepseek keys time out at ~22-24s per key (NVCF-side), consuming 5-7 keys × 24s = 120-168s, exceeding 156s budget
- **Not config-fixable**: ATE events cannot be eliminated by HM parameter changes (Pitfall #41, #43)
- **Secondary observation**: 2 SSLEOFError events in 30min on k3/k4 — NVCF proxy-layer SSL instability, auto-retried successfully

### Why No Change
- All 7 parameters at proven equilibrium (71st consecutive validation)
- R158 UPSTREAM_TIMEOUT=70 fully stabilized — 71st consecutive validation
- R162 KEY_COOLDOWN_S=38 fully stabilized — 71st consecutive KEY=TIER=38 invariant validation
- 0 429s across all windows confirms no rate-limit pressure
- 0 fallback in 0-12h confirms zero fallback starvation
- Any parameter change would be over-optimization — stability IS the optimal state

## 🔧 变更执行

**No changes applied.** This is a no-change validation round.

## 📈 预期效果

**Continuation of stability plateau.** Metrics expected to remain:
- 30min success rate: ~98.3-98.5% (NVCF server-side variance)
- P50: 17-20s, P95: 42-61s
- 0 429s, 0 fallback in 0-12h windows
- ATE events: NVCF server-side PexecTimeout storms, not config-preventable

## ⚖️ 评判标准

| Criterion | Status | Evidence |
|-----------|--------|----------|
| 更少报错 | ✅ PASS | 0 429s, 0 fallback in 0-12h; ATE events are NVCF server-side, not HM config |
| 更快请求 | ✅ PASS | P50≈17-20s, P95≈42-61s; all within UPSTREAM_TIMEOUT=70s; no latency degradation |
| 超低延迟 | ✅ PASS | Per-key p50 all <20s; success-path latency stable at historical lows |
| 稳定优先 | ✅ PASS | 71 consecutive rounds of no-change validation; all 7 params at equilibrium; stability plateau fully confirmed |

### 铁律 Confirmation
- ✅ **只改HM1不改HM2** — no changes applied to either instance
- ✅ **少改多轮** — zero changes this round; accumulation of no-change validations confirms equilibrium
- ✅ **单参数原则** — not applicable (no change needed)
- ✅ **KEY≥TIER invariant**: KEY_COOLDOWN_S=38 ≥ TIER_COOLDOWN_S=38 ✅

## ⏳ 轮到HM1优化HM2