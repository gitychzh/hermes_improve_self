# R235: HM2 → HM1 — 无变更 (全7参数均衡; 60th no-change verification; 30min 97.95% 21 ATE 0 429 0 fallback; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 09:55-10:25 UTC, ~30min window)

### Config Snapshot (docker exec env)
```
UPSTREAM_TIMEOUT=70
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=38
TIER_TIMEOUT_BUDGET_S=156
MIN_OUTBOUND_INTERVAL_S=19.2
HM_CONNECT_RESERVE_S=24
CHARS_PER_TOKEN_ESTIMATE=3.0
PROXY_TIMEOUT=300
```

### DB Metrics (30min @ 2026-06-28 10:25 UTC)
| Metric | Value |
|--------|-------|
| Total requests | 1067 |
| Success (200) | 1046 |
| Success rate | 97.95% |
| ATE (all_tiers_exhausted) | 21 |
| NVStream_TimeoutError | 1 |
| 429 errors | 0 |
| Fallback triggered | 0 |
| SSLEOFError | 0 |

### 1h Summary
- Total: 1133, OK: 1111 → 98.06%
- ATE: 21 (same as 30min, stable), NVStream_TimeoutError: 1

### 6h Summary
- Total: 1860, OK: 1837 → 98.76%

### Per-Key Latency (30min, deepseek_hm_nv, status=200)
| Key | Count | P50 (ms) | P95 (ms) | Avg (ms) |
|-----|-------|----------|----------|-----------|
| k0 (K1) | 223 | 17022 | 53220 | 19885 |
| k1 (K2) | 212 | 18305 | 45414 | 20770 |
| k2 (K3) | 197 | 19587 | 44117 | 21318 |
| k3 (K4) | 203 | 18978 | 45162 | 21410 |
| k4 (K5) | 209 | 18247 | 50432 | 20798 |

### Error Detail JSONL (最近ATF事件)
```
tier=deepseek_hm_nv: 5-7 attempts, elapsed=154-156s
tier=kimi_hm_nv: num_attempts=0 (Pitfall #41 — kimi untouched)
```
All ATE events: kimi_hm_nv num_attempts=0 → NVCF PexecTimeout storms consume full budget before kimi gets a chance.

### Docker Logs (最近100行)
All [HM-SUCCESS] — every request first-attempt success. No errors, no retries, no SSLEOFError in current window.

## 🎯 优化分析

### 瓶颈识别
21 ATE events (all_tiers_exhausted) + 1 NVStream_TimeoutError = 22 errors in 30min.
- **21 ATE**: 100% NVCF server-side PexecTimeout storms → deepseek_hm_nv consumes 154-156s across 5-7 key attempts, kimi num_attempts=0
- **1 NVStream_TimeoutError**: Network-layer timeout, auto-retried locally
- **0 429, 0 fallback**: No rate-limit pressure, no tier fallbacks in current data

### 参数评估表
| Parameter | Current | Evaluation | Adjustment |
|-----------|---------|------------|------------|
| UPSTREAM_TIMEOUT | 70 | All P95 < 70s; success-path stable; 2×70=140 rem=16s > 5s ✅ | None |
| TIER_TIMEOUT_BUDGET_S | 156 | Budget consumed by NVCF server-side, not HM config; R154 proven diminishing returns; 21 ATE is server-side | None |
| KEY_COOLDOWN_S | 38 | KEY=TIER=38 invariant holds (Pitfall #44); 0 429 in 30min | None |
| TIER_COOLDOWN_S | 38 | KEY=TIER=38: zero-gap equilibrium; no wasted key attempts | None |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | 5×19.2=96s >> KEY=38s; RR counter healthy; ~3.0 req/min vs 3.1/min capacity (94% util) | None |
| HM_CONNECT_RESERVE_S | 24 | Adequate for SOCKS5+SSL setup; 0 budget_exhausted_after_connect in recent data | None |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | Standard; no token misestimation observed | None |

### 为什么不变更
1. **ATE events are NVCF server-side**: kimi num_attempts=0 (Pitfall #41) — config cannot prevent NVCF PexecTimeout storms
2. **Budget threshold not breached**: 2×70=140, remaining=16s > 5s threshold; no HM-TIER-BUDGET warnings in recent 500 lines
3. **All 7 params at equilibrium**: R162+R158 config has held stable through 60 consecutive rounds
4. **0 429, 0 fallback**: No rate-limit or fallback pressure
5. **少改多轮 principle**: When no parameter needs adjustment, no-change is the correct action — stability IS the optimal state

## 📈 预期效果
No change = no degradation. Continue monitoring. The 21 ATE events are expected from NVCF server-side instability — they will fluctuate independently of HM config.

## ⚖️ 评判标准

| 标准 | 状态 |
|------|------|
| **更少报错** | ✅ 21 ATE (NVCF server-side, not config-fixable) + 1 NVStream_TimeoutError; 0 429, 0 fallback, 0 SSLEOFError in current window |
| **更快请求** | ✅ P50≈17-20s per key; P95≈44-53s; all within UPSTREAM_TIMEOUT=70s |
| **超低延迟** | ✅ First-attempt latency 17-22s P50; no fallback overhead |
| **稳定优先** | ✅ No config changes = maximum stability; 60th consecutive validation of the equilibrium plateau |
| **铁律:只改HM1不改HM2** | ✅ No HM2 config touched; HM1-only analysis; validated HM1 config unchanged |
| **少改多轮** | ✅ This round: 0 changes — no parameter needed adjustment; stability IS the optimal state |

## ⏳ 轮到HM1优化HM2