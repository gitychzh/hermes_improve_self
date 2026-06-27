# R160: HM1 → HM2 — 无变更 (全7参数均衡; 30min 100% 0 errors; 少改多轮; 铁律:只改HM2不改HM1)

## 📊 数据采集 (2026-06-28 04:59-05:10 UTC)

### Config Snapshot (HM2 hm40006 — docker exec env)
| Parameter | Value | Status |
|-----------|-------|--------|
| MIN_OUTBOUND_INTERVAL_S | 11.0 | R159: 10.5→11.0 (+0.5s), 已应用 |
| UPSTREAM_TIMEOUT | 71 | 未变更 |
| TIER_TIMEOUT_BUDGET_S | 132 | 未变更 |
| KEY_COOLDOWN_S | 36 | 未变更 |
| TIER_COOLDOWN_S | 34 | 未变更, KEY-TIER gap=2s (最小安全) |
| HM_CONNECT_RESERVE_S | 24 | 未变更 |
| PROXY_TIMEOUT | 300 | 未变更 |

### 30min Window (91 requests) — Post R159 MIN_OUTBOUND=11.0
- **Success rate: 100%** (91/91, **0 errors**)
- P50: 12,386ms, P90: 35,516ms, P95: 53,322ms, P99: 69,032ms
- Avg: 17,912ms
- **Errors: 0** — zero ATE, zero other errors
- **Fallback: 49/91 (53.8%)** — all glm5.1→deepseek, **zero kimi reached**

### 30min Tier Distribution
| Tier | Requests | Pct | Avg | P95 |
|------|----------|-----|-----|-----|
| glm5.1_hm_nv | 42 | 46.2% | 12,504ms | — |
| deepseek_hm_nv | 49 | 53.8% | 22,547ms | — |

### Per-Key Success (30min)
| Key | Total | Avg | P95 | Fallback% |
|-----|-------|-----|-----|-----------|
| k0 | 9 | 16,727ms | 27,448ms | 100.0% |
| k1 | 28 | 11,090ms | 27,138ms | 32.1% |
| k2 | 18 | 16,984ms | 33,568ms | 50.0% |
| k3 | 16 | 21,956ms | 41,676ms | 75.0% |
| k4 | 20 | 25,596ms | 68,400ms | 50.0% |

### Tier Attempts (30min)
| Tier | Error Type | Count | Avg Elapsed |
|------|------------|-------|-------------|
| glm5.1_hm_nv | 429_nv_rate_limit | 69 | — |
| glm5.1_hm_nv | NVCFPexecSSLEOFError | 9 | 5,006ms |
| glm5.1_hm_nv | 500_nv_error | 2 | — |
| glm5.1_hm_nv | NVCFPexecRemoteDisconnected | 1 | 563ms |
| glm5.1_hm_nv | NVCFPexecConnectionResetError | 1 | 7,089ms |
| deepseek_hm_nv | NVCFPexecSSLEOFError | 7 | 9,166ms |
| deepseek_hm_nv | empty_200 | 1 | — |

### Fallback Paths (30min)
- 100% glm5.1_hm_nv → deepseek_hm_nv (49 events, avg=22,547ms)
- **Zero kimi_hm_nv reached** — kimi fallback starvation (Pitfall #41: kimi tier never engaged)

### 1h Window
- 207/207 = 100% success, 0 errors

### 6h Window
- 1049/1051 = 99.81% success, 2 errors

### 24h Window
- 3658/3694 = 99.03% success, 36 errors (most from 6h+ ago — pre-R159)

### Docker Logs (Recent 150 lines)
- Heavy 429 pattern on glm5.1 tier: all keys hitting `429_nv_rate_limit` → cycled → cooldown → fallback to deepseek
- No `[HM-GLOBAL-COOLDOWN]` events in recent 200 lines (global cooldown not triggering at current spacing)
- SSLEOFError on both tiers: 9 events glm5.1, 7 events deepseek
- ConnectionResetError and RemoteDisconnected on glm5.1 (rare)
- No budget-break events — TIER_TIMEOUT_BUDGET_S=132 adequate

### Request Rate
- ~3.0 req/min (91 in 30min)
- Capacity at MIN_OUTBOUND=11.0s: ~5.5 req/min
- Utilization: 54.5% of capacity (comfortable headroom)

## 🎯 优化分析

**结论: 系统已收敛，无变更必要。**

The 30min window shows **100% success, 0 errors** — the strongest possible signal that all parameters are balanced. The previous R159 change (MIN_OUTBOUND=10.5→11.0) has been absorbed and the system is stable.

**Why no change:**
1. **0 errors in 30min**: The ultimate success metric. No parameter change can improve on zero errors.
2. **All 7 parameters at equilibrium**: MIN_OUTBOUND=11.0, KEY_COOLDOWN=36, TIER_COOLDOWN=34, UPSTREAM_TIMEOUT=71, TIER_TIMEOUT_BUDGET=132, HM_CONNECT_RESERVE=24, PROXY_TIMEOUT=300.
3. **KEY-TIER gap=2s (minimum safe)**: TIER_COOLDOWN=34 vs KEY_COOLDOWN=36. Gap cannot narrow further without risking key-level false cooldown overlap.
4. **429 pattern is NVCF server-side**: 69×429 in 30min is NVCF function-level rate limiting (server-side, not configurable from HM's side). The system handles this correctly via the ring fallback pattern.
5. **p95=53s well within UPSTREAM_TIMEOUT=71s**: Success path latency has 18s headroom below timeout — no truncation risk.
6. **0 kimi fallback**: The kimi tier never engages (Pitfall #41 — kimi fallback starvation). But this is a feature, not a bug: all failures are handled by deepseek successfully.

**Decision Framework:**
- If any parameter were off-balance, adjust it incrementally (单参数少改多轮).
- Since ALL parameters show no error signal in 30min, the only correct action is: **no change**.
- The 53.8% fallback rate is a consequence of NVCF's rate limiting, not configurable from HM2's side. The system successfully absorbs it.

**Budget Verification (Pitfall #23):**
- 5×11.0=55.0s cycle vs GLOBAL=45s → buffer=10.0s
- The 30min 0-ATE proves the buffer is sufficient — no 429 collision cascade reaches tier exhaustion.

## 🔧 变更执行

**无变更** — 所有7参数已验证均衡，稳定优先。

## 📈 预期效果

| Metric | Current | Expected |
|--------|---------|-----------|
| 30min success rate | 100% | 100% (maintain) |
| 30min ATE count | 0 | 0 (maintain) |
| 24h success rate | 99.03% | ≥ 99.0% |
| Fallback rate | 53.8% | ~50-55% (NVCF rate-limit controlled) |
| P95 latency | 53,322ms | < 71s (UPSTREAM_TIMEOUT) |

## ⚖️ 评判标准

- **更少报错**: ✅ 已有 0 errors/30min — 当前配置最优
- **更快请求**: ✅ p50=12.4s, avg=17.9s — 维持当前水平
- **超低延迟**: ✅ 所有 key p95 < 71s — 无超时截断风险
- **稳定优先**: ✅ 不修改任何参数 — 避免破坏已验证的7参数均衡
- **铁律**: ✅ 只改 HM2 配置绝不动 HM1 本地 (本回合无改动)

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记