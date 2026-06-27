# R171: HM2 → HM1 — 无变更 (全7参数均衡; 30min 99.7% 0ATE 0 429 0 fallback; 6h 99.7%; 24h 45ATE全NVCF PexecTimeout风暴白天集中; 第7次R162验证; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 06:17 UTC, 30min window)

### HM1 运行时配置
| 参数 | 值 | 状态 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 70 | ✅ R158第6次验证 |
| TIER_TIMEOUT_BUDGET_S | 156 | ✅ 稳定 |
| KEY_COOLDOWN_S | 38 | ✅ R162第7次验证 |
| TIER_COOLDOWN_S | 38 | ✅ KEY=TIER对齐 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ✅ 稳定 |
| HM_CONNECT_RESERVE_S | 24 | ✅ 稳定 |
| PROXY_TIMEOUT | 300 | ✅ 稳定 |

### 30min 核心指标
| 指标 | 值 |
|------|-----|
| 总请求 | 1168 |
| 成功 | 1165 (99.7%) |
| ATE (all_tiers_exhausted) | 0 |
| 429 | 0 |
| Fallback | 0 |
| P50延迟 | 18,433ms |
| P90延迟 | 37,802ms |
| P95延迟 | 50,523ms |

### 1h 核心指标
| 指标 | 值 |
|------|-----|
| 总请求 | 1229 |
| 成功 | 1226 (99.8%) |
| ATE | 0 |
| 429 | 0 |

### 6h 核心指标
| 指标 | 值 |
|------|-----|
| 总请求 | 1959 |
| 成功 | 1954 (99.7%) |
| ATE | 0 |
| 429 | 0 |

### Per-Key 延迟 (30min)
| Key | 请求 | 成功 | P50(ms) | P90(ms) | P95(ms) | 429 | 其他错误 |
|-----|------|------|---------|---------|---------|-----|---------|
| k0 | 242 | 241 | 19,268 | 41,788 | 58,350 | 0 | 1 NVStream_IncompleteRead |
| k1 | 231 | 231 | 18,455 | 36,943 | 53,355 | 0 | 0 |
| k2 | 223 | 223 | 17,417 | 31,553 | 38,542 | 0 | 0 |
| k3 | 236 | 235 | 18,162 | 38,796 | 46,148 | 0 | 1 NVStream_IncompleteRead |
| k4 | 237 | 236 | 18,683 | 38,978 | 52,663 | 0 | 1 NVStream_TimeoutError |

### 3个30min错误详情
| 错误类型 | 数量 | 平均延迟(ms) |
|---------|------|-------------|
| NVStream_IncompleteRead | 2 | 13,187 |
| NVStream_TimeoutError | 1 | 109,523 |

### 请求速率
- 约3请求/分钟 → 19s间隔容量=158请求/分钟 → 容量使用率 ≈ 1.9%（极低负载）

### Back-to-back同Key率
- 31/1168 = 2.7%（RR计数器正常波动，Pitfall #28）

### 24h 状态分布
| Status | 数量 | 平均延迟(ms) |
|--------|------|-------------|
| 200 | 4,044 | 29,196 |
| 502 | 6 | 72,547 |

### 24h ATE时间分布
| 时段(UTC) | ATE数 |
|-----------|-------|
| 02:00 | 1 |
| 09:00 | 1 |
| 10:00 | 4 |
| 11:00 | 10 |
| 13:00 | 5 |
| 15:00 | 1 |
| 16:00 | 7 |
| 17:00 | 8 |
| 18:00 | 2 |
| 19:00 | 3 |
| 01:00 (next day) | 1 |
| 02:00 (next day) | 2 |
| **总计** | **45** |

ATE集中时段：09:00-19:00 UTC = 38/45 (84%) → 白天集中模式(Pitfall #30)，NVCF服务端PexecTimeout风暴。

### Docker日志
- 最近100行grep error/warn: 0匹配 ✅
- 最新日志全部HM-SUCCESS，一次尝试成功

## 🎯 优化分析

### 7参数评估表

| 参数 | 当前值 | 是否调整 | 原因 |
|------|--------|---------|------|
| UPSTREAM_TIMEOUT | 70 | ❌ 不调 | P95=50.5s远低于70s上限；6h 0 ATE |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ 不调 | 2×70=140, 余量=16s > 12s阈值；0 ATE |
| KEY_COOLDOWN_S | 38 | ❌ 不调 | 0 429 → 无降频压力；KEY=TIER保持 |
| TIER_COOLDOWN_S | 38 | ❌ 不调 | KEY=TIER对齐(Pitfall #44)；0 429 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ❌ 不调 | 容量使用率1.9%；0 429 |
| HM_CONNECT_RESERVE_S | 24 | ❌ 不调 | 0 budget_exhausted_after_connect错误 |
| PROXY_TIMEOUT | 300 | ❌ 不调 | 无超时相关错误 |

### 关键判断
1. **30min 99.7%**, 0 ATE, 0 429, 0 fallback → 极度稳定
2. **6h 99.7%**, 0 ATE, 0 429 → 延续稳定
3. **24h 45 ATE** 全部NVCF服务端PexecTimeout(Pitfall #41)：kimi fallback num_attempts=0，budget被deepseek超时耗尽。这是NVCF服务端问题，配置无法解决(R154 diminishing returns验证)
4. **0 429** → 无频率限制压力，cooldown参数无需调整
5. 所有key P95 < 58.4s < UPSTREAM_TIMEOUT=70s → 安全边界充裕
6. Budget余量16s(2×70=140, 156-140=16 > 12s阈值) → 无需增加
7. KEY=TIER=38对齐保持(Pitfall #44) → 无需调整
8. **3个错误**：2×NVStream_IncompleteRead(网络层), 1×NVStream_TimeoutError(NVCF服务端) → 均非配置可控

### 结论
**全7参数均衡，无变更** — 稳定优先，过度优化会破坏已建立平衡。

## ⚖️ 评判标准
- ✅ **更少报错**: 30min 3错误(0.25%), 全NVCF服务端/网络层
- ✅ **更快请求**: P50=18.4s, P95=50.5s
- ✅ **超低延迟**: P50降至18.4s(历史低位)
- ✅ **稳定优先**: 第7次R162验证，连续多轮无变更确认
- ✅ **铁律**: 仅修改HM1，未修改HM2本地配置
- ✅ **少改多轮**: 无变更是正确操作

## ⏳ 轮到HM1优化HM2 ← 脚本检测此标记
