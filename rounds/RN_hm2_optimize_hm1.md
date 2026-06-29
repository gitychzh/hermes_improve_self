# R306: HM2→HM1 — ⏸️ 无变更 (系统已达稳定)

**时间**: 2026-06-29 20:30 UTC (04:30 CST)  
**角色**: HM2 (优化执行者) → HM1 (被优化目标)  
**触发**: HM1提交了新commit (R305: HM2→HM1 — ⏸️ 无变更), 脚本检测轮到HM2执行  

## HM1 当前配置 (R305基线, 已稳定)

| 参数 | 值 | 说明 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 64s | NVCF upstream超时 |
| KEY_COOLDOWN_S | 38s | 键冷却时间 |
| TIER_COOLDOWN_S | 38s | 层级冷却时间 |
| MIN_OUTBOUND_INTERVAL_S | 18.2s | 最小出站间隔 |
| TIER_TIMEOUT_BUDGET_S | 182s | 层级超时预算 |
| CONNECT_RESERVE_S | 24s | 连接预留 |
| 路由模式 | ALL DIRECT | 全部5键直连NVCF (无mihomo代理) |

## 数据收集 (1h窗口: 19:30-20:30 UTC)

### Docker日志 (最近50行)
- 全部 `[HM-SUCCESS]` — 无error/warn/exception
- 所有请求: `attempt 1/7`, first-attempt 成功
- 路由: `k1-k5 → NVCF pexec ... DIRECT` (全部直连)
- 典型延迟: 16-30s 范围 (正常DeepSeek推理时间)

### 数据库统计

**1h窗口汇总**:
- 总请求(含键): 1087 (deepseek_hm_nv)
- 成功: 1086 (99.91%)
- 键级错误: 1 (NVStream_IncompleteRead: K3, 115.2s)
- ATE (all_tiers_exhausted): 24 (avg 162.3s, max 178.2s)

**2h窗口每键延迟百分位 (deepseek_hm_nv)**:

| 键 | 请求数 | P25 | P50 | P75 | P90 | P95 | P99 | 最大 |
|----|--------|-----|-----|-----|-----|-----|-----|------|
| K1 | 224 | 17.6s | 27.5s | 38.9s | 57.3s | 66.1s | 87.6s | 116.3s |
| K2 | 224 | 17.6s | 27.0s | 38.8s | 54.0s | 65.3s | 110.8s | 122.6s |
| K3 | 208 | 19.7s | 30.5s | 42.2s | 61.5s | 70.1s | 104.2s | 118.5s |
| K4 | 211 | 18.7s | 30.4s | 40.9s | 60.0s | 74.2s | 98.7s | 115.7s |
| K5 | 222 | 17.9s | 26.8s | 40.0s | 62.4s | 77.3s | 107.7s | 135.9s |

**键健康度评估**:
- K5: 最快P50 (26.8s), P95=77.3s (最宽尾) — 节点质量正常
- K2: P50=27.0s, P95=65.3s (最佳P95) — 节点稳定
- K1: P50=27.5s, P95=66.1s — 稳定
- K3/K4: P50超30s, 但仍在可接受范围 — 正常DeepSeek推理时间
- 全部5键: 0个429, 0个fallback, DIRECT直连 ✅

**错误分析**:
| 错误类型 | 数量 | 平均延迟 | 根源 |
|----------|------|---------|------|
| all_tiers_exhausted (ATE) | 24 | 162.3s | NVCFPexecTimeout (server-side, 不可修复) |
| NVStream_IncompleteRead | 1 | 115.2s | K3节点偶发流中断 |

- 无429 (rate-limit): ✅ 所有键健康
- 无fallback触发: ✅ 键池充足
- 无SSLEOFError: ✅ SSL层正常

### 环境变量对比

| 参数 | HM1 (本地) | HM2 (本地) |
|------|-----------|-----------|
| UPSTREAM_TIMEOUT | 64s | 68s |
| KEY_COOLDOWN_S | 38.0 | 38.0 |
| TIER_COOLDOWN_S | 38.0 | 22.0 |
| MIN_OUTBOUND_INTERVAL_S | 18.2s | 4.5s |
| BUDGET | 182s | 128s |
| CONNECT_RESERVE_S | 24 | 23 |
| 路由 | ALL DIRECT (5/5) | K1-K3 DIRECT, K4-K5 SOCKS5 |

## 优化分析

### 评估标准
1. **更少报错**: 24 ATE全部是 server-side NVCFPexecTimeout — 不是HM1配置问题, 不可修复
2. **更快请求**: P50在26.8-30.5s范围 — 正常DeepSeek模型推理时间, 不是网络/配置瓶颈
3. **超低延迟**: P25=17.6-19.7s — 这是NVCF的最小响应延迟 (GPU推理+网络传输)
4. **稳定优先**: 99.91%成功率, 0个429, 0个fallback — 系统已达最高稳定水平

### 决策: ⏸️ 无变更

**原因**:
1. ✅ 所有5键健康 (0个429, 全部first-attempt, DIRECT直连)
2. ✅ BUDGET=182s 已覆盖最大ATE (178.2s → 3.8s安全余量)
3. ✅ KEY=TIER=38s 双38对称 — 已是最优冷却配置
4. ✅ MIN_OUTBOUND=18.2s — 适合HM1的DIRECT路由模式 (无SOCKS5代理)
5. ✅ 无任何可调参数能改善当前状态 (全部已达最优)

**24个ATE的本质**: 全部是NVCF server-side的 `PexecTimeout` — NVCF函数执行超时, 发生在NVCF平台侧, 不是HM1的配置问题。BUDGET=182s 已给了足够的时间窗口让这些超时自然发生并被记录。任何配置调整都无法减少这些ATE, 因为它们是NVCF serverless平台的固有延迟。

**Per-key P50差异 (10.7%): K3 30.5s vs K1 27.5s** — 这是NVCF节点质量差异(不同GPU分配、不同路由路径), 不是HM1配置可调参数。所有5键都走 `_make_nvcf_direct_conn` 直连NVCF, 无mihomo代理中间层, 延迟差异完全是NVCF平台侧的节点分配策略导致的。

### 铁律遵守
- ✅ 只改HM1不改HM2 (本轮无任何改动)
- ✅ 单参数少改多轮 (本轮0变更)
- ✅ 数据驱动决策 (基于真实DB查询和docker日志)

## HM2本地状态 (供参考)
| 参数 | 值 |
|------|-----|
| UPSTREAM_TIMEOUT | 68s |
| MIN_OUTBOUND_INTERVAL_S | 4.5s |
| BUDGET | 128s |
| CONNECT_RESERVE | 23 |
| 默认模型 | glm5.1_hm_nv |

## ⏳ 轮到HM1优化HM2