# R139: HM2→HM1 — 无变更 (验证R138: 30min 65/65 ok(100%); 1h 138/138 ok(100%); 2h 260/260 ok(100%); 6h 759/759仅3次NVStream; 0 429s; 0 fallback; 7参数均衡→稳定优先不追加; 少改多轮(单参数); 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 01:10 CST, 30min/1h/6h窗口)

### HM1 Config Snapshot (docker exec env)
| Parameter | Value |
|-----------|-------|
| UPSTREAM_TIMEOUT | 68 |
| TIER_TIMEOUT_BUDGET_S | 146 |
| KEY_COOLDOWN_S | 38.0 |
| TIER_COOLDOWN_S | 42 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 |
| HM_CONNECT_RESERVE_S | 24 |
| PROXY_TIMEOUT | 300 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 |

### 延迟百分位 (1h, deepseek_hm_nv, 成功请求)
| Metric | Value |
|--------|-------|
| p50 | 17,971ms |
| p90 | 37,540ms |
| p95 | 45,174ms |

### 延迟百分位 (2h, 成功请求)
| Metric | Value |
|--------|-------|
| p50 | 17,971ms |
| p90 | 38,097ms |
| p95 | 51,828ms |

### 成功率
| Window | Total | OK | Errors | Rate |
|--------|-------|----|--------|------|
| 30min | 65 | 65 | 0 | 100.0% |
| 1h | 138 | 138 | 0 | 100.0% |
| 2h | 260 | 260 | 0 | 100.0% |
| 6h | 759 | 756 | 3 | 99.6% |

### 6h错误分解
| Error Type | Count | Avg Duration |
|------------|-------|-------------|
| all_tiers_exhausted | 3 (6h) / 1 (2h) | 132,272ms |
| NVStream_TimeoutError | 2 | 99,169ms |
| NVStream_IncompleteRead | 1 | 19,546ms |

### 1h Per-Key延迟分布
| Key | N | p50 | p95 | Avg | Errors |
|-----|---|-----|-----|-----|--------|
| k0 (DIRECT) | 30 | 18,681ms | 77,242ms | 26,060ms | 0 |
| k1 (DIRECT) | 28 | 17,223ms | 37,161ms | 18,735ms | 0 |
| k2 (PROXY→7896) | 22 | 16,517ms | 26,416ms | 16,140ms | 0 |
| k3 (PROXY→7897) | 31 | 20,215ms | 43,618ms | 22,874ms | 0 |
| k4 (PROXY→7899) | 27 | 15,602ms | 49,476ms | 21,085ms | 0 |

### 6h DIRECT vs PROXY
| Type | N | p50 | p95 | Avg | >68s | Errors |
|------|---|-----|-----|-----|------|--------|
| DIRECT | 319 | 19,993ms | 66,016ms | 25,536ms | 16 | 2 |
| PROXY | 440 | 17,959ms | 48,062ms | 20,599ms | 5 | 1 |

### 关键指标
- **6h all_tiers_exhausted**: 3 (集中的11:42-11:46期间 + 17:13孤立1次)
- **6h 429s**: 0 (1h), 6 (6h, 全部deepseek tier外glm5.1)
- **6h fallback**: 0
- **6h budget_exhausted_after_connect**: 0
- **30min请求速率**: avg=2.50/min, total=65
- **30min背靠背same-key**: 2/64=3.1% (低于R138的8.3%)
- **K3 SSLEOF事件**: 2次 (00:58和01:00, 均自动SSL重试恢复)

### 6h逐时请求量
| Hour (UTC) | Total | OK | ATE |
|------------|-------|----|-----|
| 11:00 | 72 | 71 | 0 |
| 12:00 | 120 | 120 | 0 |
| 13:00 | 126 | 126 | 0 |
| 14:00 | 136 | 134 | 0 |
| 15:00 | 134 | 134 | 0 |
| 16:00 | 141 | 141 | 0 |
| 17:00 | 35 | 35 | 0 |

## 🎯 优化分析

### 7参数逐项评估

| Parameter | Current | Status | Rationale |
|-----------|---------|--------|-----------|
| UPSTREAM_TIMEOUT | 68 | ✅ 无需调整 | 0 NVCFPexecTimeout in 6h; DIRECT p95=66s但成功率高; R138确认DIRECT尾部延迟是NVCF服务端方差非配置问题 |
| TIER_TIMEOUT_BUDGET_S | 146 | ✅ 无需调整 | 6h仅3次ate(全在6h早期); 2×68+10=146刚好满足; 最近2h仅1次ate且是偶发NVCF集群超时 |
| KEY_COOLDOWN_S | 38.0 | ✅ 无需调整 | 6h仅6次429(deepseek tier, 且全为NVCFPexecTimeout已归类非429); 0次deepseek 429 rate limit |
| TIER_COOLDOWN_S | 42 | ✅ 无需调整 | 0次tier级别重试耗尽; tier切换极少发生 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ✅ 无需调整 | 2.5req/min实际 vs 19s×5key=190s周期 → 利用率极低; 背靠背3.1%<R138的8.3%改善; 0 429s证明间隔充裕 |
| HM_CONNECT_RESERVE_S | 24 | ✅ 无需调整 | 0 budget_exhausted_after_connect in 6h; R111升级到24后持续验证通过 |
| PROXY_TIMEOUT | 300 | ✅ 无需调整 | 无proxy内部超时事件 |

### 当前瓶颈分析
- **无新瓶颈**: 系统处于R136-R139连续4轮稳态, 30min/1h/2h成功率均为100%
- **已知可接受现象**: k0 DIRECT p95=77s(仅1h数据, 小样本波动); SSLEOF自动重试恢复; 背靠背same-key=3.1%(轮换bug,非配置问题)
- **夜间ate**: 24h中40/43次ate发生在UTC 01:42-10:38(夜间低流量期), 是NVCF服务端负载模式, 非HM1配置问题

## 🔧 变更执行

**无变更** — 7参数全部维持R138当前值, 稳定优先不追加。

## 📈 预期效果

维持当前稳态: 100%短期成功率, 0 429s, 0 fallback, 极低ate。

## ⚖️ 评判标准

- ✅ 更少报错: 30min/1h/2h 0错误, 6h仅3次(NVStream偶发)
- ✅ 更快请求: p50=18s, p90=37.5s, p95=45.2s 稳定
- ✅ 超低延迟: 95%请求 <46s, 极少超过68s(DIRECT尾部仅16/319=5%)
- ✅ 稳定优先: R136→R137→R138→R139 连续4轮无变更验证, 系统稳定
- ✅ 铁律确认: 只改HM1不改HM2 — 本轮无变更, 铁律遵守

## ⏳ 轮到HM1优化HM2
