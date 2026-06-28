# R195: HM2 → HM1 — 无变更 (全7参数均衡; 30min 99.92% 0ATE 0 429 0 fallback; 1h 99.92%; 6h 99.85%; P50=18.2s P95=44.3s; 26th consecutive R162+R158 验证; NVCF PexecTimeout 风暴不可配置级修复; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 ~11:05 UTC, 30min/1h/6h/24h 窗口)

### Config Snapshot (HM1 hm40006)
| Parameter | Value |
|-----------|-------|
| UPSTREAM_TIMEOUT | 70 |
| TIER_TIMEOUT_BUDGET_S | 156 |
| KEY_COOLDOWN_S | 38 |
| TIER_COOLDOWN_S | 38 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 |
| HM_CONNECT_RESERVE_S | 24 |
| PROXY_TIMEOUT | 300 |

### Docker Logs (last 100 lines)
- ✅ All entries are `[HM-SUCCESS]` — **zero errors, zero warnings, zero timeouts**
- Clean round-robin key cycling: k4→k5→k1→k2→k3→k4 pattern
- All requests succeed on first attempt (attempt 1/7)

### Latency Percentiles (success-path, deepseek_hm_nv)
| Window | Total | OK | Err | ATE | 429 | Fallback | P50 | P95 |
|--------|-------|----|-----|-----|-----|----------|-----|-----|
| 30min | 1193 | 1192 | 1 | 0 | 0 | 0 | 18.2s | 44.3s |
| 1h | 1267 | 1266 | 1 | 0 | 0 | 0 | — | — |
| 6h | 1950 | 1947 | 3 | 0 | 0 | 0 | 18.4s | 47.4s |
| 24h segmented: 0-6h | 1949 | 1946 | 3 | 0 | 0 | 0 | — | — |
| 24h segmented: 6-12h | 917 | 914 | 3 | 0 | 0 | 0 | — | — |
| 24h segmented: 12-24h | 1443 | 1443 | 0 | 0 | 0 | 1066 | — | — |

### Per-Key Latency Distribution (30min, success-path only)
| Key | nv_key_idx | Count | P50 | P95 |
|-----|------------|-------|-----|-----|
| K1 | 0 | 240 | 17.0s | 44.9s |
| K2 | 1 | 237 | 18.5s | 48.4s |
| K3 | 2 | 234 | 18.7s | 38.2s |
| K4 | 3 | 236 | 18.0s | 47.1s |
| K5 | 4 | 245 | 18.7s | 45.1s |

- Key distribution: even (234-245 requests/key, Δ=11 = 4.5%)
- DIRECT (k0/k1) vs PROXY (k2/k3/k4): latency similar, no concerning gap

### 24h Error Breakdown
| Error Type | Count | Avg Duration |
|------------|-------|-------------|
| NVStream_TimeoutError | 4 | 102.2s |
| NVStream_IncompleteRead | 2 | 13.2s |

- Zero all_tiers_exhausted in 24h (system-wide)
- All 6 errors are NVCF/network-level, not HM config-related

### 6h Success-Path Percentiles
- P50=18.4s, P95=47.4s, P99=78.5s

### Back-to-Back Rate
- 30min: 17/1191 = 1.43% (normal, RR counter variance, Pitfall #28)

## 🎯 优化分析

### All 7 Parameters Evaluation

| Parameter | Current | Evaluation | Adjustment Needed? |
|-----------|---------|-----------|-------------------|
| UPSTREAM_TIMEOUT | 70 | P95=44.3s << 70s; 0 ATE; budget margin 2×70=140, remaining=16s > 10s threshold ✅ | ❌ No |
| TIER_TIMEOUT_BUDGET_S | 156 | 0 ATE in 30min/1h/6h/24h; 16s remaining after 2×70; R154 diminishing returns reconfirmed | ❌ No |
| KEY_COOLDOWN_S | 38 | KEY=TIER=38 invariant holds (Pitfall #44); 0 429s in all windows | ❌ No |
| TIER_COOLDOWN_S | 38 | KEY=TIER=38 alignment is correct long-term config; 0 fallback in 0-12h windows | ❌ No |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | 0 429s; 5×19=95s cycle >> KEY_COOLDOWN=38s; request rate healthy | ❌ No |
| HM_CONNECT_RESERVE_S | 24 | 0 budget_exhausted_after_connect in logs | ❌ No |
| PROXY_TIMEOUT | 300 | No issues observed | ❌ No |

### Bottleneck Analysis
- **Zero ATE** across all short windows (30min/1h/6h) and 24h segmented
- **Zero 429s** across all windows
- **Zero fallback** in 0-6h and 6-12h; 12-24h fallback=1066 all old-regime data (Pitfall #49)
- **6 errors in 24h** are all NVStream network-level (TimeoutError/IncompleteRead), not config-fixable
- Per-key distribution even (234-245), latency uniform across keys
- **Stability plateau fully confirmed** — R162+R158 equilibrium holds for 26 consecutive rounds

### Why No Change
1. All 7 parameters are at confirmed equilibrium
2. NVCF PexecTimeout storms are server-side issues, not addressable by HM1 config changes (Pitfalls #41, #43)
3. 24h fallback is entirely old-regime data (Pitfall #49) — zero fallback in recent 12h
4. P50=18.2s and P95=44.3s are at or near best-observed levels
5. Budget margin of 16s (2×70=140, remaining=16s) provides comfortable safety
6. KEY=TIER=38 invariant holds (Pitfall #44)
7. R154 diminishing-returns principle reconfirmed: budget increases beyond threshold show zero ATE improvement

## 🔧 变更执行
**无变更** — 全7参数保持当前值，不做任何调整。

## 📈 效果确认
| Metric | R194 → R195 | Trend |
|--------|-------------|-------|
| 30min success | 99.92% → 99.92% | ➡️ Stable |
| 1h success | 99.92% → 99.92% | ➡️ Stable |
| 6h success | 99.85% → 99.85% | ➡️ Stable |
| P50 | 18.2s → 18.2s | ➡️ Stable |
| P95 | 44.1s → 44.3s | ➡️ Stable |
| ATE 30min | 0 → 0 | ➡️ Zero |
| 429 30min | 0 → 0 | ➡️ Zero |
| Fallback 30min | 0 → 0 | ➡️ Zero |

## ⚖️ 评判标准
- ✅ 更少报错: 0 ATE, 0 429, 0 fallback in all short windows
- ✅ 更快请求: P50=18.2s at/below historical best
- ✅ 超低延迟: P95=44.3s (near historical low of 42.5s from R185 low-traffic)
- ✅ 稳定优先: 26th consecutive R162+R158 validation, full 7-parameter equilibrium
- ✅ 铁律: 只改HM1不改HM2 — confirmed, no HM2 changes made

## ⏳ 轮到HM1优化HM2