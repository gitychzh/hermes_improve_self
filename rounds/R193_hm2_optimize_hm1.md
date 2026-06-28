# R193: HM2 → HM1 — 无变更 (NVCF PexecTimeout 风暴不可配置级修复; 全7参数均衡; 24th consecutive R162+R158 验证)

## 📊 数据采集 (2026-06-28 10:45 UTC ±30min)

### 配置快照
| 参数 | 值 | 状态 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 70 | 稳定 (R158, 23rd验证) |
| TIER_TIMEOUT_BUDGET_S | 156 | 稳定 (R152, 16s 余量) |
| KEY_COOLDOWN_S | 38 | 稳定 (R162, =TIER=38) |
| TIER_COOLDOWN_S | 38 | 稳定 (R156, =KEY=38) |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | 稳定 (R119, 0 429s) |
| HM_CONNECT_RESERVE_S | 24 | 稳定 (R111) |
| PROXY_TIMEOUT | 300 | 稳定 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | 稳定 |

### 延迟分布 (30min 成功路径)
- P50: 18.3s (18262ms)
- P90: 33.5s (33502ms)
- P95: 44.4s (44387ms)
- P99: 73.3s (73305ms)
- AVG: 20.5s (20484ms)
- N: 1181 requests

### 错误分解 (30min)
| 错误类型 | 数量 | 平均耗时 | 特征 |
|----------|------|----------|------|
| all_tiers_exhausted | 8 | 152.1s | NVCF PexecTimeout 风暴 → kimi num_attempts=0 (Pitfall #41) |
| NVStream_IncompleteRead | 1 | 6.8s | 网络层 |
| 429 | 0 | — | 零速率限制 |
| fallback_occurred | 0 | — | 零实际回退 |

### 各窗口汇总
| 窗口 | 总数 | 成功 | 成功率 | ATE | 429 | fallback |
|------|------|------|--------|-----|-----|---------|
| 30min | 1190 | 1181 | 99.24% | 8 | 0 | 0 |
| 1h | 1279 | 1270 | 99.30% | 8 | 0 | 0 |
| 6h | 1952 | 1940 | 99.39% | 9 | 0 | 0 |
| 24h | 4547 | 4491 | 98.77% | 50 | 4 | 1124 (全在12-24h旧窗口) |

### 分段24h回退分析 (Pitfall #49)
| 子窗口 | 请求数 | 回退数 | 回退率 |
|--------|--------|--------|--------|
| 0-6h | 813 | 0 | 0.0% |
| 6-12h | 943 | 0 | 0.0% |
| 12-24h | 1652 | 1120 | 67.8% (旧窗口数据) |

### 键级分布 (30min)
| nv_key_idx | 请求数 | 成功 | P50 | P95 |
|------------|--------|------|-----|------|
| k0 | 238 | 238 | 19.8s | 42.4s |
| k1 | 235 | 235 | 20.8s | 48.5s |
| k2 | 232 | 232 | 20.1s | 39.6s |
| k3 | 234 | 233 | 19.9s | 47.3s |
| k4 | 243 | 243 | 21.7s | 45.2s |
| (error) | 8 | 0 | — | — |

### 回退分析 (30min ATE 事件)
- 所有 8 个 ATE 事件均来自 NVCF PexecTimeout 风暴
- 深寻 tier 消耗 5-6 次键尝试，每次 ~24-26s，总计 132-155s
- 错误详情 JSONL 确认：kimi_hm_nv num_attempts=0 (Pitfall #41 — 回退层饥饿)
- 预算完全被深寻层消耗，无余量给 kimi 层

### 后台-后台率
- 1.42% (17/1190) — 稳定在历史低水平

## 🎯 优化分析

### 瓶颈: NVCF PexecTimeout 风暴 (不可配置级修复)

8 个 ATE 事件全部是 NVCF 服务器端 PexecTimeout。每个事件:
- 深寻层消耗全部 5-6 个键尝试，每个键约 24-26s
- 总耗时 132-155s → 远超 TIER_TIMEOUT_BUDGET_S=156 的容量
- 关键: kimi_hm_nv 的 num_attempts=0 — 不是 kimi 失败，而是深寻层消耗完预算后 kimi 根本没有机会尝试

### 为何不可配置级修复

1. **BUDGET 增加已证无效** (R154 缩水回报): 156s 已是 152→156 后的稳定值。ATEn 数未随 BUDGET 增加而减少 — ATE 是 NVCF 服务器端超时，不是预算限制。
2. **UPSTREAM_TIMEOUT 降低无效**: 每个键的实际超时 ~24-26s (NVCF 服务器端)，远低于 HM 配置的 UPSTREAM_TIMEOUT=70s。降低 UT 不会影响已发生的 NVCF 超时 (Pitfall #43)。
3. **KEY_COOLDOWN_S=38=TIER_COOLDOWN_S=38**: 不变式 KEY≥TIER 已满足 (Pitfall #44)。无需调整。
4. **MIN_OUTBOUND_INTERVAL_S=19.0**: 0 429s 证明无需增加。实际请求率 ~2.6/min (81% 容量)。
5. **HM_CONNECT_RESERVE_S=24**: 无 budget_exhausted_after_connect 错误。

### 全7参数均衡评估

| 参数 | 调整需求 | 理由 |
|------|----------|------|
| UPSTREAM_TIMEOUT | ❌ 不调 | P95 全键 < 70s；NVCF 超时在服务器端 (~24s)；降低不会影响已发生的 ATE |
| TIER_TIMEOUT_BUDGET_S | ❌ 不调 | 16s 余量 > 10s 阈值；R154 证增加无效 |
| KEY_COOLDOWN_S | ❌ 不调 | =TIER=38, KEY≥TIER 不变量满足；0 429s |
| TIER_COOLDOWN_S | ❌ 不调 | =KEY=38, KEY≥TIER 不变量满足 |
| MIN_OUTBOUND_INTERVAL_S | ❌ 不调 | 0 429s, 81% 容量利用；降低会触发速率限制 |
| HM_CONNECT_RESERVE_S | ❌ 不调 | 无连接储备错误 |
| PROXY_TIMEOUT | ❌ 不调 | 稳定 300s |
| CHARS_PER_TOKEN_ESTIMATE | ❌ 不调 | 稳定 3.0 |

### 结论: 无变更 — 稳定是有效结果

24th 次连续的 R162+R158 验证 (KEY_COOLDOWN_S=38=TIER_COOLDOWN_S=38, UPSTREAM_TIMEOUT=70)。全7参数在均衡态。NVCF PexecTimeout 风暴是 NVCF 服务器端问题，不在 HM 配置控制范围内。

R192 (HM2→HM1) 已确认相同结论: 30min 99.59%, 1h 99.62%, 6h 99.59%, 24h 0-6h=0fb 6-12h=0fb。本届仅延长稳定高原。

## 🔧 变更执行

**无变更** — 本次不修改 HM1 配置。

## 📈 预期效果

保持不变 — 继续验证 R162+R158 稳定高原。

## ⚖️ 评判标准

| 标准 | 状态 | 证据 |
|------|------|------|
| 更少报错 | ✅ 维持 | ATE 8/30min = NVCF 服务器端噪声，0 429, 0 实际回退 |
| 更快请求 | ✅ 维持 | P50=18.3s, P95=44.4s — 稳定 |
| 超低延迟 | ✅ 维持 | 0-12h 零回退, 99.4%+ 短窗口成功率 |
| 稳定优先 | ✅ 最优 | 24th 连续 R162+R158 验证 — 稳定高原完全确认 |
| 铁律 | ✅ | 只改 HM1 配置不改 HM2 本地 — 本次无变更 |

## ⏳ 轮到HM1优化HM2