# R192: HM2 → HM1 — 无变更 (全7参数均衡; 30min 99.59% 4ATE全NVCFPexecTimeout 0 429 0 fallback; 1h 99.62%; 6h 99.59% 5ATE+3NVStream; 24h 0-6h=0fb 6-12h=0fb; 第24次R162+R158连续验证; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 10:30 UTC)

### Config Snapshot (HM1)
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

### Docker Logs (最近100行 error/warn)
```
[10:30:40.2] [HM-TIMEOUT] tier=deepseek_hm_nv k4 NVCF pexec timeout: attempt=11632ms total=133266ms
[10:30:47.7] [HM-TIMEOUT] tier=deepseek_hm_nv k5 NVCF pexec timeout: attempt=7526ms total=140793ms
[10:30:53.0] [HM-TIMEOUT] tier=deepseek_hm_nv k1 NVCF pexec timeout: attempt=5261ms total=146055ms
[10:30:58.3] [HM-TIMEOUT] tier=deepseek_hm_nv k2 NVCF pexec timeout: attempt=5269ms total=151326ms
[10:30:58.3] [HM-TIER-FAIL] tier=deepseek_hm_nv all 5 keys failed: 429=0, empty200=2, timeout=4, other=0, elapsed=151327ms
[10:30:58.3] [HM-FALLBACK] Tier deepseek_hm_nv all-failed → falling back to kimi_hm_nv
[10:30:58.7] [HM-ALL-TIERS-FAIL] All 2 tiers failed, elapsed=151726ms, ABORT-NO-FALLBACK
[10:33:17.3-10:33:33.1] 第二次NVCF PexecTimeout风暴 (5键全timeout, budget remaining 2.0s < 5s, kimi num_attempts=0)
```

### 30min Overview
| Metric | Value |
|--------|-------|
| Total requests | 1215 |
| Success (200) | 1210 |
| Failures | 5 |
| **Success rate** | **99.59%** |
| P50 latency | 18.27s |
| P90 latency | 33.90s |
| P95 latency | 46.33s |
| ATE (all_tiers_exhausted) | 4 |
| Status 429 | 0 |
| Fallback | 0 |

**Error breakdown (30min)**:
| Error type | Count | Avg duration |
|------------|-------|-------------|
| all_tiers_exhausted | 4 | 149,957ms |
| NVStream_IncompleteRead | 1 | 6,827ms |

**Per-key distribution (30min)**:
| Key | Total | Success | Avg_ms | P95_ms | Errors |
|-----|-------|---------|--------|--------|--------|
| k0 | 243 | 243 | 20,073 | 44,553 | 0 |
| k1 | 241 | 241 | 20,693 | 48,387 | 0 |
| k2 | 238 | 238 | 20,032 | 38,844 | 0 |
| k3 | 240 | 239 | 20,066 | 48,098 | 1 |
| k4 | 249 | 249 | 21,633 | 44,876 | 0 |

Per-key distribution very even (238-249, range=11). All keys healthy.

### 1h Overview
| Metric | Value |
|--------|-------|
| Total | 1301 |
| Success | 1296 |
| **Success rate** | **99.62%** |
| P50 | 18.31s |
| P95 | 45.26s |
| ATE | 4 |
| 429 | 0 |
| Fallback | 0 |

### 6h Overview
| Metric | Value |
|--------|-------|
| Total | 1964 |
| Success | 1956 |
| **Success rate** | **99.59%** |
| P50 | 18.51s |
| P95 | 48.71s |
| ATE | 5 |
| 429 | 0 |
| Fallback | 0 |

**Error breakdown (6h)**:
| Error type | Count | Avg duration |
|------------|-------|-------------|
| all_tiers_exhausted | 5 | 148,354ms |
| NVStream_IncompleteRead | 2 | 13,187ms |
| NVStream_TimeoutError | 1 | 109,523ms |

**Per-key distribution (6h)**:
| Key | Total | Success | Avg_ms | P95_ms | Errors |
|-----|-------|---------|--------|--------|--------|
| k0 | 404 | 403 | 22,505 | 51,916 | 1 |
| k1 | 387 | 387 | 21,648 | 50,174 | 0 |
| k2 | 376 | 376 | 19,526 | 38,214 | 0 |
| k3 | 397 | 396 | 20,504 | 45,259 | 1 |
| k4 | 395 | 394 | 21,263 | 48,627 | 1 |

### 24h Overview (分段 — Pitfall #49)
| Window | Total | Fallback | ATE | 429 |
|--------|-------|----------|-----|-----|
| 0-6h | 1964 | 0 | 5 | 0 |
| 6-12h | 951 | 0 | 21 | 0 |
| 12-24h | 1665 | 1151 | 20 | 4 |

**24h status breakdown**:
| Status | Count | Avg_ms | Min_ms | Max_ms |
|--------|-------|--------|--------|--------|
| 200 | 4528 | 27,732 | 1,295 | 184,900 |
| 429 | 4 | 161,389 | 138,762 | 189,745 |
| 502 | 48 | 119,040 | 6,827 | 166,774 |

**P50=20.75s, P95=74.89s** (24h P95 inflated by old-regime 502s with avg~119s, Pitfall #36)

## 🎯 优化分析

### 瓶颈识别
- 当前30min窗口：4 ATE (0.33%)，全部为 NVCF PexecTimeout 风暴
- 0 429 → 无速率限制压力
- 0 fallback (30min/1h/6h) → tier chain 工作正常
- 日志可见：NVCF风暴 = 5键全timeout → 151s budget消耗 → kimi num_attempts=0 → ATE (Pitfall #41 经典模式)
- kimi tier根本没机会尝试，因为deepseek tier耗尽了全部budget (2×70=140s + 5键各~5s timeout = ~150s > 156s budget)

### 参数逐项评估

| Parameter | Current | Adjustment | Reason |
|-----------|---------|------------|--------|
| UPSTREAM_TIMEOUT | 70 | ❌ 无变更 | R158已从72→70, 2×70=140留16s余量. p95=46-48s << 70s安全. 再降会危及长请求 (>60s p95的key). NVCF实际timeout ~5s/键远低70s(Pitfall#43) — ATE非UT驱动 |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ 无变更 | R154证明增加budget无减少ATE (diminishing returns). ATE由NVCF server-side storm驱动, 非budget不足. 2×70+10=150<156, 余量16s充足 |
| KEY_COOLDOWN_S | 38 | ❌ 无变更 | KEY=TIER=38 (invariant, Pitfall#44). 0 429 → 无速率限制压力, 无需调整 |
| TIER_COOLDOWN_S | 38 | ❌ 无变更 | KEY=TIER=38 对齐已验证24轮. 不能单独降TIER (会违反KEY≥TIER). 不能升 (会浪费恢复时间) |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ❌ 无变更 | 30min 1215请求 = ~2.5req/min. 19s×5=95s cycle >> KEY_COOLDOWN=38s. 容量3.2/min, 利用率78%. 无429 = 无速率压力 |
| HM_CONNECT_RESERVE_S | 24 | ❌ 无变更 | 0 budget_exhausted_after_connect → CONNECT_RESERVE充足 |
| PROXY_TIMEOUT | 300 | ❌ 无变更 | 无相关错误触发 |

### 结论
- **全7参数均衡** — 无单参数调整可减少NVCF server-side timeout导致的ATE
- ATE = NVCF PexecTimeout风暴 → 5键timeout → budget耗尽 → kimi无法尝试 → all_tiers_exhausted (Pitfall #41)
- R154已证明增加BUDGET无减少ATE (diminishing returns)
- R158已证明降UT从72→70改善budget余量(12→16s), 但ATE仍NVCF驱动
- 唯一根本修复是per-tier budget split (代码变更, 非config可及)
- 24h fallback=1151全部在12-24h旧regime窗口 (Pitfall #49), 0-12h=0 fallback
- **稳定优先 = 最优状态**

## 🔧 变更执行

**无变更** — 第24次连续R162+R158验证

## ⚖️ 评判标准

| 标准 | 状态 | 说明 |
|------|------|------|
| 更少报错 | ✅ | 30min 4 ATE全NVCF server-side, 0 429, 0 fallback (config无法改善) |
| 更快请求 | ✅ | P50=18.3s (极低), P95=46.3s (稳定) |
| 超低延迟 | ✅ | 成功请求延迟稳定在R183-R191水平 |
| 稳定优先 | ✅ | 第24次连续验证, 全7参数均衡 |

### 铁律确认
- ✅ 只改HM1, 不改HM2 → 本轮无变更, 铁律自然遵守
- ✅ 少改多轮 → 无变更就是最少改动

## ⏳ 轮到HM1优化HM2
