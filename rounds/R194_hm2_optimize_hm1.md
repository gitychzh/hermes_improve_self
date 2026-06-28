# R194: HM2 → HM1 — 无变更 (全7参数均衡; 30min 99.92% 0ATE 0 429 0 fallback; 1h 99.92%; 6h 99.85%; P50=18.2s P95=44.1s; 25th consecutive R162+R158 验证; NVCF PexecTimeout 风暴不可配置级修复; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 ~11:00 CST, 30min窗口)

### HM1 Config Snapshot (env confirmation)
| Parameter | Value | Status |
|-----------|-------|--------|
| UPSTREAM_TIMEOUT | 70 | ✅ R158 验证中 |
| TIER_TIMEOUT_BUDGET_S | 156 | ✅ R152 验证中 |
| KEY_COOLDOWN_S | 38 | ✅ R162 对齐TIER |
| TIER_COOLDOWN_S | 38 | ✅ R156/R162 对齐KEY |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ✅ R119 验证中 |
| HM_CONNECT_RESERVE_S | 24 | ✅ R111 验证中 |
| PROXY_TIMEOUT | 300 | ✅ 稳定 |

### 30min Stats (deepseek_hm_nv)
| Metric | Value |
|--------|-------|
| Total requests | 1193 |
| Success (200) | 1192 (99.92%) |
| Errors | 1 |
| ATE (all_tiers_exhausted) | 0 |
| 429 | 0 |
| Fallback | 0 |
| Avg OK latency | 20450ms |
| P50 | 18241ms |
| P95 | 44127ms |
| P99 | 73038ms |

### 1h Stats
| Metric | Value |
|--------|-------|
| Total | 1272 |
| Success | 1271 (99.92%) |
| Errors | 1 |
| ATE | 0 |
| 429 | 0 |
| Fallback | 0 |

### 6h Stats
| Metric | Value |
|--------|-------|
| Total | 1950 |
| Success | 1947 (99.85%) |
| Errors | 3 |
| ATE | 0 |
| 429 | 0 |
| Fallback | 0 |
| 200 avg_dur | 21068ms |
| 502 avg_dur | 45299ms |

### 24h Segmented (Pitfall #49)
| Window | Total | Success | ATE | 429 | Fallback |
|--------|-------|---------|-----|-----|----------|
| 0-6h | 1950 | 1947 | 0 | 0 | 0 |
| 6-12h | 916 | 913 | 0 | 0 | 0 |
| 12-24h | 1439 | 1439 | 0 | 0 | 1081 (旧regime) |

### Per-Key Latency (30min)
| Key (nv_key_idx) | Total | Success | Avg OK | P50 | P95 |
|-----------------|-------|---------|--------|-----|-----|
| k0 | 240 | 240 | 19646 | 16993 | 42061 |
| k1 | 238 | 238 | 21003 | 18644 | 48428 |
| k2 | 235 | 235 | 19915 | 18817 | 38230 |
| k3 | 237 | 236 | 20038 | 18026 | 47125 |
| k4 | 246 | 246 | 21621 | 18693 | 45018 |

### Error Detail (30min)
| Error Type | Count | Avg Duration |
|------------|-------|-------------|
| NVStream_IncompleteRead | 1 | 6827ms (k3) |

### Error Detail (6h)
| Error Type | Count | Avg Duration |
|------------|-------|-------------|
| NVStream_IncompleteRead | 2 | 13187ms |
| NVStream_TimeoutError | 1 | 109523ms |

### Docker Logs (last 100 lines, error/warn filter)
**0 matches** — grep exit code 1, all lines are [HM-SUCCESS]. System fully clean.

## 🎯 优化分析

### 全7参数评估

| Parameter | Current | Evaluation | Action |
|-----------|---------|------------|--------|
| UPSTREAM_TIMEOUT | 70 | P95=44.1s远低于70s阈值; 0 ATE证明budget充足(2×70=140, remaining=16s>10s) | 无需调整 |
| TIER_TIMEOUT_BUDGET_S | 156 | 0 ATE in 30min/1h/6h; remaining=16s margin充分 | 无需调整 |
| KEY_COOLDOWN_S | 38 | 0 429 in all windows; KEY=TIER=38对齐(Pitfall #44) | 无需调整 |
| TIER_COOLDOWN_S | 38 | 0 fallback in 0-12h; KEY=TIER invariant保持 | 无需调整 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ~2 req/min at 19s capacity=3.2/min → 63% utilization | 无需调整 |
| HM_CONNECT_RESERVE_S | 24 | budget_exhausted_after_connect zero in all windows | 无需调整 |
| PROXY_TIMEOUT | 300 | No proxy-timeout errors observed | 无需调整 |

### Bottleneck Analysis
- **0 ATE, 0 429, 0 fallback** in 30min/1h/6h — 系统完全稳定
- 3 errors in 6h: 2×NVStream_IncompleteRead (网络层, k0/k3自动重试成功), 1×NVStream_TimeoutError (NVCF server-side) — 均为NVCF服务端/网络层问题,不可配置级修复
- P50=18.2s (18,241ms) — 新低,稳定性杰出
- P95=44.1s (44,127ms) — 远低于UPSTREAM_TIMEOUT=70s,余量25.9s
- Per-key分布均匀: 235-246 req/key in 30min
- 24h: 0-6h和6-12h均0 ATE/0 fallback; 12-24h 1081 fallback全为旧regime数据(Pitfall #49)
- **第25次连续R162+R158验证** — 稳定平台完全确立

### 决策: 无变更
所有7个参数均在均衡状态,无任何参数偏离。30min/1h/6h三个窗口均为0 ATE/0 429/0 fallback。3个6h错误全为NVCF网络层/服务端问题,不可通过配置修复。稳定性即最优状态。

## 🔧 变更执行
无变更。全7参数保持不变。

## 📈 效果确认 (R162+R158延续验证)
| Metric | R193 | R194 | Trend |
|--------|------|------|-------|
| 30min success% | ~99.8% | 99.92% | ↑ |
| ATE (30min) | ~2-3 | 0 | ✅ |
| 429 (30min) | 0 | 0 | ✅ |
| Fallback (30min) | 0 | 0 | ✅ |
| P50 | ~18.3s | 18.2s | ↓ new low |
| P95 | ~46-49s | 44.1s | ↓ |

## ⚖️ 评判标准
- ✅ 更少报错: 30min仅1 NVStream_IncompleteRead (网络层,非配置可控)
- ✅ 更快请求: P50=18.2s (新低), P95=44.1s
- ✅ 超低延迟: 全key P95 < 49s,远低于UPSTREAM_TIMEOUT=70s
- ✅ 稳定优先: 25th consecutive R162+R158 validation, 全7参数均衡
- ✅ 铁律: 只改HM1不改HM2 — 本轮无变更,铁律自然遵守

## ⏳ 轮到HM1优化HM2