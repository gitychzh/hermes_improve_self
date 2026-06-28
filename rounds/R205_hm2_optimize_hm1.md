# R205: HM2 → HM1 — 无变更 (全7参数均衡; 30min 99.91% 0 ATE 0 429 0 fallback; 34th consecutive R162+R158 validation; P50=18.2s P95=42.3s; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 13:10 UTC, 30min/1h/6h windows)

### Config Snapshot (docker exec hm40006 env)
| Parameter | Value |
|-----------|-------|
| UPSTREAM_TIMEOUT | 70 |
| TIER_TIMEOUT_BUDGET_S | 156 |
| KEY_COOLDOWN_S | 38 |
| TIER_COOLDOWN_S | 38 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 |
| HM_CONNECT_RESERVE_S | 24 |
| PROXY_TIMEOUT | 300 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 |

### Docker Logs (last 100 lines, grep error/warn)
```
[13:09:21.2] [ERR] NV stream TimeoutError after 115581ms: The read operation timed out
```
- 仅1条错误: NVStream_TimeoutError (NVCF网络层超时, 非配置可控)
- 运行正常: 大量 [HM-SUCCESS] first-attempt success 记录, k1-k5 轮转正常

### 30min Metrics
| Metric | Value |
|--------|-------|
| Total Requests | 1174 |
| Success (200) | 1173 |
| Error (502) | 1 |
| 429 | 0 |
| Success Rate | **99.91%** |
| all_tiers_exhausted | **0** |
| fallback | **0** |
| P50 Latency | 18,187ms (18.2s) |
| P95 Latency | 42,307ms (42.3s) |

### 1h Metrics
| Metric | Value |
|--------|-------|
| Total Requests | 1249 |
| Success (200) | 1247 |
| Error (502) | 2 |
| 429 | 0 |
| Success Rate | **99.84%** |
| all_tiers_exhausted | **0** |
| fallback | **0** |

### 6h Metrics
| Metric | Value |
|--------|-------|
| Total Requests | 1936 |
| Success (200) | 1934 |
| Error (502) | 2 |
| 429 | 0 |
| Success Rate | **99.90%** |
| all_tiers_exhausted | **0** |
| fallback | **0** |
| P50 Latency | 18,249ms (18.2s) |
| P95 Latency | 45,417ms (45.4s) |

### 6h Error Breakdown
| error_type | count | avg_dur_ms |
|------------|-------|------------|
| NVStream_IncompleteRead | 1 | 6,827 |
| NVStream_TimeoutError | 1 | 115,582 |

- 2 errors均为NVCF网络层偶发事件, 非HM配置问题

### Per-Key Distribution (30min)
| Key | Count | P50(ms) | P95(ms) | Errors |
|-----|-------|---------|---------|--------|
| k0 | 242 | 16,882 | 40,310 | 0 |
| k1 | 234 | 18,435 | 45,734 | 1 |
| k2 | 232 | 18,990 | 41,257 | 0 |
| k3 | 231 | 18,747 | 38,796 | 0 |
| k4 | 235 | 18,514 | 42,333 | 0 |

- Per-key均匀分布 (231-242), 偏差<4.7%
- 所有key P95 < 46s, 远低于 UPSTREAM_TIMEOUT=70s
- 1个error在k1 (NVStream网络层)

## 🎯 优化分析

### Parameter Evaluation Table
| Parameter | Current | Status | Reason |
|-----------|---------|--------|--------|
| UPSTREAM_TIMEOUT | 70 | ✅ No change | P95=42.3s << 70s; R158 validated 34 rounds; k0-k4 all P95<46s |
| TIER_TIMEOUT_BUDGET_S | 156 | ✅ No change | 2×70+12=152 < 156; remaining=16s; 0 ATE confirms sufficient margin |
| KEY_COOLDOWN_S | 38 | ✅ No change | KEY=TIER=38 invariant holds (Pitfall #44); 0 429s confirms no over-provisioning |
| TIER_COOLDOWN_S | 38 | ✅ No change | KEY≥TIER invariant; aligned with KEY; no tier exhaustion observed |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ✅ No change | Request rate ~39/min=1.5s avg; 19s capacity >> 1.5s demand; no 429s |
| HM_CONNECT_RESERVE_S | 24 | ✅ No change | 0 budget_exhausted_after_connect errors; sufficient at current volume |
| PROXY_TIMEOUT | 300 | ✅ No change | No proxy-level timeouts observed |

### Bottleneck Analysis
- **0 ATE, 0 429, 0 fallback** across all windows — no config-addressable bottleneck exists
- 2 errors in 6h are both NVCF network layer (NVStream_IncompleteRead + NVStream_TimeoutError) — NOT addressable by config changes
- P50=18.2s, P95=42.3s — both at or near historical lows (R204 set P50=18.1s, P95=41.8s as records)
- System at stability plateau since R162 (34 consecutive validations)

### Assessment
**No parameter needs adjustment.** All 7 params are at equilibrium. The system is in its optimal stable state. The 2 NVStream errors are NVCF server-side network events that config cannot prevent — making changes would be over-optimization.

## 🔧 变更执行

**无变更** — 7参数全均衡, 34th consecutive R162+R158 validation.

## 📈 预期效果

| Metric | R204 | R205 | Trend |
|--------|------|------|-------|
| 30min success % | 99.92% | 99.91% | ≈ stable |
| 30min ATE | 0 | 0 | ✅ |
| 30min 429 | 0 | 0 | ✅ |
| 30min fallback | 0 | 0 | ✅ |
| 6h success % | (not collected) | 99.90% | ✅ excellent |
| P50 | 18.1s | 18.2s | ≈ stable |
| P95 | 41.8s | 42.3s | ≈ stable |

- Continuous zero ATE / zero 429 / zero fallback confirms R162+R158 equilibrium plateau
- P50/P95 within normal daily variance range
- 34th consecutive validation: stability IS the optimal state

## ⚖️ 评判标准
- ✅ 更少报错: 0 ATE, 0 429, 0 fallback (6h仅2 NVCF网络层偶发)
- ✅ 更快请求: P50=18.2s, P95=42.3s (历史低位区间)
- ✅ 超低延迟: per-key P95均<46s, 远低于70s上限
- ✅ 稳定优先: 34th consecutive R162+R158 validation
- ✅ 铁律: 只改HM1不改HM2 — 本次无变更, 铁律自然遵守

## ⏳ 轮到HM1优化HM2
