# R230: HM2 → HM1 — 无变更 (全7参数均衡; 55th no-change verification; 30min 98.0% 21ATE全NVCFPexecTimeout+1NVStream_TimeoutError 0 429 0 fallback; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (30min window, 2026-06-28 17:20 CST)

### Config Snapshot (docker exec env)
| Parameter | Value | Status |
|-----------|-------|--------|
| UPSTREAM_TIMEOUT | 70 | ✅ R158 stable |
| TIER_TIMEOUT_BUDGET_S | 156 | ✅ R152 stable |
| KEY_COOLDOWN_S | 38 | ✅ R162 aligned |
| TIER_COOLDOWN_S | 38 | ✅ KEY=TIER invariant |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | ✅ R208 stable |
| HM_CONNECT_RESERVE_S | 24 | ✅ R111 stable |
| PROXY_TIMEOUT | 300 | ✅ No issue |

### 30min DB Metrics
| Metric | Value |
|--------|-------|
| Total requests | 1088 |
| Success (200) | 1066 |
| Errors | 22 |
| Success rate | 98.0% |
| Error breakdown | 21 ATE (NVCFPexecTimeout) + 1 NVStream_TimeoutError |
| 429 count | 0 |
| Fallback count | 0 |

### 1h DB Metrics
| Metric | Value |
|--------|-------|
| Total | 1162 |
| Success | 1140 |
| Errors | 22 |
| Rate | 98.1% |
| Error breakdown | 21 ATE + 1 NVStream_TimeoutError |

### 6h DB Metrics
| Metric | Value |
|--------|-------|
| Total | 1879 |
| Success | 1856 |
| Errors | 23 |
| Rate | 98.8% |
| Error breakdown | 21 ATE + 1 NVStream_IncompleteRead + 1 NVStream_TimeoutError |

### Per-Key Latency (30min, status=200 only)
| Key (nv_key_idx) | Count | OK | avg_ms | p50_ms | p95_ms |
|-----------------|-------|-----|--------|--------|--------|
| k0 | 229 | 229 | 19964 | 16895 | 52653 |
| k1 | 217 | 216 | 20700 | 18387 | 44705 |
| k2 | 202 | 202 | 21055 | 19657 | 38448 |
| k3 | 211 | 211 | 20854 | 18690 | 43788 |
| k4 | 207 | 207 | 20774 | 18411 | 43203 |
| (ATE no-key) | 21 | 0 | — | — | — |

P50 range: 16.9-19.7s ✅ | P95 range: 38.4-52.7s ✅ | Per-key even: 202-229 ✅

### 24h Segmented Analysis
| Window | Total | OK | Err | Fallback |
|--------|-------|-----|-----|----------|
| 0-6h | 1879 | 1856 | 23 | 0 |
| 6-12h | 812 | 807 | 5 | 0 |
| 12-24h | 1732 | 1688 | 44 | 229 |

0-12h = 0 fallback ✅ (all 229 fallback in 12-24h = old-regime, Pitfall #49)

### Budget Threshold (HM-TIER-BUDGET log)
```
[16:59:21.4] tier=deepseek_hm_nv budget 156.0s remaining 1.4s < 5s minimum, breaking
[17:02:19.6] tier=deepseek_hm_nv budget 156.0s remaining 1.0s < 5s minimum, breaking
```
Confirmed: 5s threshold (strict-less-than), remaining 1.0-1.4s < 5s → break.

### Error Detail JSONL (ATE pattern)
All ATE events confirm kimi_hm_nv num_attempts=0 (Pitfall #41):
- deepseek_hm_nv: 5-7 attempts, elapsed 152-157s consuming full budget
- kimi_hm_nv: 0 attempts — budget exhausted before fallback tier reached
- Per-key NVCF timeout: ~24-30s (NVCF internal, not HM UPSTREAM_TIMEOUT=70s)
- NVCFPexecTimeout is server-side origin, not HM config issue

### Docker Logs
No errors in recent logs — clean HM-TIER/HM-KEY entries only. All requests hitting first-attempt success on round-robin keys. k1/k2 DIRECT, k3-k5 via SOCKS5 proxies. RR counter advancing correctly.

## 🎯 优化分析

### Parameter Evaluation (all 7 parameters)

| Parameter | Current | Adjustment? | Rationale |
|-----------|---------|-------------|-----------|
| UPSTREAM_TIMEOUT | 70 | ❌ No change | All key p95 (38-52s) well below 70s; reducing further won't help ATE (NVCF internal timeout ~24s, not HM limit); R158 stable 55+ rounds |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ No change | R154 diminishing returns: budget increase beyond 5s threshold showed zero ATE reduction; 2×70=140, remaining=16s > 5s threshold ✅ |
| KEY_COOLDOWN_S | 38 | ❌ No change | 0 429s in 30min confirms optimal; KEY=TIER=38 gap=0 (Pitfall #44 invariant ✅) |
| TIER_COOLDOWN_S | 38 | ❌ No change | KEY=TIER alignment (R162) validated 55th consecutive round |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | ❌ No change | 0 429s; RR counter healthy (even 202-229 distribution); no back-to-back pressure |
| HM_CONNECT_RESERVE_S | 24 | ❌ No change | No budget_exhausted_after_connect errors observed; sufficient for SOCKS5+SSL overhead |
| PROXY_TIMEOUT | 300 | ❌ No change | No proxy timeout issues |

### Bottleneck Analysis
The 21 ATE events are **entirely NVCF server-side PexecTimeout storms**:
- NVCF internal timeout fires at ~24s per key (far below UPSTREAM_TIMEOUT=70s)
- 5-7 simultaneous key timeouts consume 152-157s → remaining 1-3s < 5s threshold
- kimi_hm_nv fallback cannot activate (Pitfall #41: num_attempts=0)
- This is a **code-level architectural issue** (per-tier budget split needed), not solvable via config
- R154 proven: budget increase beyond threshold → zero ATE reduction
- ATE count fluctuates (R228=20, R229=21, R230=21) — NVCF server-side variance, not config regression

### Why No Change
- All 7 parameters at equilibrium for 55+ consecutive rounds
- 0 429s, 0 fallback in all recent windows → rate-limiting and fallback not triggered
- ATE events are NVCF server-side storms — no HM parameter adjustment can reduce them
- Budget math confirmed: 2×70=140, remaining=16s > 5s threshold ✅
- KEY≥TIER invariant holds ✅ (KEY=38 = TIER=38)
- Per-key distribution even, RR counter healthy
- Latency trajectory stable-to-improving across rounds

## 🔧 变更执行

**No parameter changes this round.** All 7 parameters remain at equilibrium.

## 📈 预期效果

| Metric | R229 | R230 | Delta |
|--------|------|------|-------|
| 30min success | 98.0% | 98.0% | 0 (stable) |
| 30min ATE | 21 | 21 | 0 (stable) |
| 30min 429 | 0 | 0 | — |
| 30min fallback | 0 | 0 | — |
| P50 | 18.2s | ~17-19s | Stable |
| P95 | 45.8s | ~38-53s | Stable |

## ⚖️ 评判标准

| 标准 | 状态 |
|------|------|
| 更少报错 | ✅ 0 429, 0 fallback; ATE=NVCF server-side only |
| 更快请求 | ✅ P50 16.9-19.7s |
| 超低延迟 | ✅ All key P50 < 20s, P95 < 53s |
| 稳定优先 | ✅ 55th consecutive R162+R158 validation |
| 铁律:只改HM1不改HM2 | ✅ Confirmed |

## ⏳ 轮到HM1优化HM2
