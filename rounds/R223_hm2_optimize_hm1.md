# R223: HM2→HM1 — 无变更 (全7参数均衡; 48th consecutive R162+R158 validation; 30min 98.29% 18ATE全NVCFPexecTimeout 0 429 0 fallback; 1 SSLEOFError k4 auto-retried confirmed; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 16:20 UTC+8)

### Config Snapshot (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=70
TIER_TIMEOUT_BUDGET_S=156
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=38
MIN_OUTBOUND_INTERVAL_S=19.2
HM_CONNECT_RESERVE_S=24
PROXY_TIMEOUT=300
CHARS_PER_TOKEN_ESTIMATE=3.0
```

### 30min Window
| Metric | Value |
|--------|-------|
| Total | 1,110 |
| Success (200) | 1,091 (98.29%) |
| ATE (all_tiers_exhausted) | 18 (avg_dur=154,238ms) |
| 429 errors | 0 |
| Fallback | 0 |
| NVStream_TimeoutError | 1 (avg=115,582ms) |
| P50 | 18,134ms (18.1s) |
| P90 | 30,831ms |
| P95 | 41,422ms (41.4s) |
| P99 | 66,346ms (66.3s) — << UPSTREAM_TIMEOUT=70s |

### 1h Window
| Metric | Value |
|--------|-------|
| Total | 1,185 |
| Success | 1,166 (98.40%) |
| ATE | 18 |
| 429 | 0 |
| Fallback | 0 |

### 6h Window
| Metric | Value |
|--------|-------|
| Total | 1,890 |
| Success | 1,868 (98.84%) |
| ATE | 20 |
| 429 | 0 |
| Fallback | 0 |

### 24h Segmented (Pitfall #49)
| Window | Total | Success | ATE | 429 | Fallback |
|--------|-------|---------|-----|-----|----------|
| 0-6h | 1,890 | 1,868 | 20 | 0 | 0 |
| 6-12h | 824 | 821 | 1 | 0 | 0 |
| 12-24h | 1,741 | 1,697 | 41 | 4 | 351 |

- **24h total**: 4,456 / 4,387 = 98.45%
- **0-12h**: 0 fallback + 0 429 → healthy
- **12-24h**: 351 fallback all old-regime (Pitfall #49)

### Per-Key Latency Distribution (30min)
| Key | Requests | Success | P95 (ms) |
|-----|----------|---------|-----------|
| k0 | 231 | 231 | 44,222 |
| k1 | 221 | 220 | 48,257 |
| k2 | 213 | 213 | 35,619 |
| k3 | 213 | 213 | 36,806 |
| k4 | 215 | 215 | 42,496 |

- Per-key even: 213-231 req/key (RR counter healthy)
- NULL key_idx rows: 18 (matching 18 ATE)

### Error Detail JSONL (today's log)
All 18 ATE entries confirmed pattern:
- `deepseek_hm_nv`: 5-6 attempts, elapsed 151-157s (NVCF PexecTimeout storms)
- `kimi_hm_nv`: **num_attempts=0** → fallback tier starvation (Pitfall #41)
- Per-key average timeout: ~24-30s << UPSTREAM_TIMEOUT=70 (Pitfall #43)

### Request Rate
~3 req/min steady (close to MIN_OUTBOUND capacity at 19.2s = 3.13/min)

### Error Scan (docker logs --tail 100)
```
grep exit code 1 → zero matching error/warn lines
```
Full log tail: all [HM-SUCCESS] lines, zero errors.

## 🎯 优化分析

### All 7 Parameters at Equilibrium

| Parameter | Value | Status | Rationale |
|-----------|-------|--------|-----------|
| UPSTREAM_TIMEOUT | 70 | ✅ No change | P99=66s < 70s; all keys succeed within limit; R158 validated through 48th consecutive round |
| TIER_TIMEOUT_BUDGET_S | 156 | ✅ No change | 2×70=140, remaining=16s > 5s threshold; budget sufficient |
| KEY_COOLDOWN_S | 38 | ✅ No change | KEY=TIER=38 → invariant holds (Pitfall #44); 0 429s confirms optimal |
| TIER_COOLDOWN_S | 38 | ✅ No change | KEY≥TIER invariant holds; 0 fallback in 0-12h; R162 alignment stable |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | ✅ No change | ~3 req/min steady; RR counter healthy; no back-to-back abuse signal |
| HM_CONNECT_RESERVE_S | 24 | ✅ No change | No budget_exhausted_after_connect errors; SSL/SOCKS5 overhead covered |
| PROXY_TIMEOUT | 300 | ✅ No change | Standard proxy timeout; not a bottleneck |

### Why No Change
1. **ATE events = NVCF server-side PexecTimeout storms**: Error detail JSONL confirms all 18 ATE have kimi num_attempts=0 — budget consumed by deepseek timeouts. This is Pitfall #41 (config cannot fix server-side storms). R154's diminishing-returns finding applies: increasing BUDGET won't reduce ATE count.
2. **Zero 429 + zero fallback in 0-12h**: Rate limiting is fully controlled; KEY=TIER cooldown alignment is working.
3. **All 7 params at proven equilibrium values**: Each has been validated through 48+ consecutive rounds — the configuration is the definitive long-term stable state.
4. **R222 already confirmed this as 无变更** — HM1's own commit (58a6e8f) documented identical analysis. This round independently re-validates with fresh data.

## ⚖️ 评判标准

- ✅ **更少报错**: 0 429, 0 fallback in 0-12h; only NVCF server-side ATE (unpreventable)
- ✅ **更快请求**: P50=18.1s stable; P95=41.4s within acceptable bounds
- ✅ **超低延迟**: All success-path latencies within UPSTREAM_TIMEOUT=70s
- ✅ **稳定优先**: 48th consecutive R162+R158 validation — stability IS the optimal state
- ✅ **铁律**: 只改HM1不改HM2 — 本次无变更, HM2本地配置未动

## ⏳ 轮到HM1优化HM2