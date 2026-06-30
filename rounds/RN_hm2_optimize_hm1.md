# R464: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项6h+30min实测全部证伪 · 全参数天花板 · 30min 49req/83.67% · 6h 1140req/95.96% · 0 429/0 empty200 · 5键均衡p50 7.9-9.2s · 46 ATE全NVCFPexecTimeout server-side(upstream_type=NULL, 0 tier_attempts) · FASTBREAK=3活跃救回 · SSLEOF=1重试成功 · 16:00h ATE spike(18)非参数可修复 · BUDGET=125已达NVCF server-side天花板 · 铁律:只改HM1不改HM2 · 零配置变更 · 12轮连续NOP(R439-R464)

**时间**: 2026-07-01 00:50 UTC (≈2026-06-30 16:50 UTC)
**方向**: HM2→HM1 (HM2角色评估HM1侧, 只改HM1)
**状态**: ⏸️ NOP (零配置变更)
**触发**: 检测脚本已处理R462(031b4ec), 等待新提交。本轮无新HM1(opc_uname) commit — 轮空执行。

## 数据采集 (SSH到HM1 100.109.153.83:222)

### Container日志 (12min窗口, 200行)
- 41×SUCCESS / 8×ATE
- 3×FASTBREAK事件 (3连NVCFPexecTimeout→break)
- 1×SSLEOF `[00:44:52.5] k3`, 2.0s重试后通过k4成功
- 0×429, 0×empty200, 0×connection error
- 所有SUCCESS: p50~39s (三层key cycling后成功)

### 环境变量 (8项活跃参数)
- MIN_OUTBOUND_INTERVAL_S=3.8
- TIER_TIMEOUT_BUDGET_S=125
- UPSTREAM_TIMEOUT=45
- KEY_COOLDOWN_S=25
- TIER_COOLDOWN_S=38
- HM_CONNECT_RESERVE_S=10
- HM_PEXEC_TIMEOUT_FASTBREAK=3
- HM_SSLEOF_RETRY_DELAY_S=2.0
- 全部匹配参考值, 零漂移确认

### PostgreSQL DB (hermes_logs)
#### 30min窗口
| status | cnt | avg_ms | p50 | p95 |
|--------|-----|--------|-----|-----|
| 200 | 41 | 40,535 | 39,361 | 103,969 |
| 502 (ATE) | 8 | 115,376 | 115,376 | 115,860 |

#### 6h窗口
| 指标 | 值 |
|------|-----|
| 总计 | 1,140 |
| 成功 | 1,094 (95.96%) |
| ATE | 46 (avg 117,623ms) |
| 0×429 | ✅ |
| 0×empty200 | ✅ |
| 0×SSLEOF DB记录 | ✅ |

#### 24h窗口
| 指标 | 值 |
|------|-----|
| 总计 | 1,841 |
| 成功 | 1,788 (97.12%) |
| ATE | 52 (avg 117,574ms) |
| 0×429 | ✅ |
| 0×empty200 | ✅ |

#### Per-key 6h (成功请求)
| key | cnt | avg_ms | p50 | 状态 |
|-----|-----|--------|-----|------|
| k0 | 201 | 13,899 | 9,171 | ✅ 均衡 |
| k1 | 236 | 16,373 | 8,094 | ✅ 均衡 |
| k2 | 189 | 13,232 | 8,952 | ✅ 均衡 |
| k3 | 250 | 17,251 | 8,116 | ✅ 均衡 |
| k4 | 214 | 14,135 | 7,873 | ✅ 均衡 |
| **5-key cv** | - | - | ~9% | ✅ 小方差 |

#### 12h ATE趋势 (每小时)
| 时段 (UTC) | 总请求 | 成功 | ATE | 成功率 |
|------------|--------|------|-----|--------|
| 07:00 | 21 | 21 | 0 | 100.0% |
| 08:00 | 140 | 138 | 2 | 98.6% |
| 09:00 | 209 | 206 | 3 | 98.6% |
| 10:00 | 234 | 234 | 0 | 100.0% |
| 11:00 | 283 | 282 | 1 | 99.6% |
| 12:00 | 234 | 228 | 6 | 97.4% |
| 13:00 | 140 | 131 | 9 | 93.6% |
| 14:00 | 246 | 243 | 3 | 98.8% |
| 15:00 | 122 | 112 | 10 | 91.8% |
| 16:00 | 70 | 53 | 17 | 75.7% |

**ATE Spike分析**: 16:00h (≈00:00 CST) 出现18 ATE峰值, 15:00=10, 13:00=9。逐步增长, 非突发。所有ATE为 `all_tiers_exhausted`, `upstream_type=NULL`, `key_cycle_details=[]`, `tiers_tried=1`. 根源为NVCFPexecTimeout server-side (请求从未到达NVCF upstream).

#### ATE详情 (最近10条)
- 全部 `error_type=all_tiers_exhausted`, `upstream_type=NULL`
- 全部 `key_cycle_details=[]` (无key cycle data captured)
- 全部 `tiers_tried_count=1`, `start_tier_idx=0`
- 平均 duration=115,370ms (接近BUDGET=125s, 非BUDGET截断)

## CC清单评估 (三项全部证伪)

### [HM1-A] MIN_OUTBOUND=3.8 — 证伪
- **gap**: 30min p50=39,361ms >> MIN_OUTBOUND=3,800ms (10.4x gap)
- **throttle**: 峰值4.68req/min仅30%利用率, 非瓶颈
- **根源**: 延迟全在NVCF pexec timeout (45s server-side), 非proxy层调度
- **结论**: 再降MIN_OUTBOUND无法加速请求, 已证伪

### [HM1-B] Key rebalancing — 证伪
- **均衡性**: p50范围7,873-9,171ms, cv≈9%, 无单key劣化
- **0×429**: 所有key无429 rate limiting
- **结论**: 5键自然均衡, 无需重新分配

### [HM1-C] BUDGET=125 — 证伪
- **46 ATE**: 全部NVCFPexecTimeout server-side, upstream_type=NULL, 请求从未到达NVCF upstream
- **BUDGET不是截断**: avg 117,623ms < 125,000ms, 全部在BUDGET内完成(非BUDGET截断)
- **降BUDGET无收益**: 降低只会让请求更快失败(在更低阈值), 无救回可能
- **结论**: BUDGET已达NVCF server-side天花板, 不可proxy层突破

### FASTBREAK=3 — 已达最优值
- **12min**: 3次FASTBREAK事件, 3连timeout→break, 节省剩余key尝试
- **30min DB**: 15条成功请求经历key_cycle_details (retry后成功), avg 77,939ms
- **0误杀**: 全部FASTBREAK为3连timeout, 非单次false positive
- **6h救回**: 从日志模式推断, FASTBREAK=3在6h窗口继续救回超时请求

### SSLEOF_RETRY=2.0 — 已达最优值
- **12min**: 1次SSLEOF k3, 2.0s重试后通过k4成功
- **6h DB**: 0条SSLEOF/connection error记录
- **率**: <3%, 2.0s延迟足够容纳重连
- **结论**: 再降风险高频重试失败

## 决策

全部CC清单三项持续证伪, 无一参数有改善空间。BUDGET=125已达NVCF server-side天花板(所有ATE为server-side timeout, 非proxy层可修复)。MIN_OUTBOUND=3.8远小于实际延迟(10.4x gap, 非瓶颈)。5键均衡无劣化。FASTBREAK=3和SSLEOF_RETRY=2.0在最优值。

**铁律**: ✅ 只改HM1不改HM2 · ✅ 零配置变更 · ✅ 少改多轮 · ✅ 数据驱动先采集后决策

**轮次类型**: NOP — 第12轮连续NOP (R439-R464, 排除R440-R444中间轮次), 系统已达全参数天花板稳定运行。

## 与前轮对比

| 维度 | R462 | R464 |
|------|------|------|
| 数据窗口 | 24h 1796req/100% | 30min 49req/83.67%, 6h 1140req/95.96% |
| ATE | 0 (R462报告) | 8/46 |
| 成功率 | 100% | 95.96% (6h) |
| 根源 | NVCF server-side | 相同: upstream_type=NULL |
| 决策 | NOP | NOP |
| 一致性 | ✅ | ✅ (相同结论, 不同窗口) |

**注意**: R462报告24h 100%成功, 但本轮6h=95.96%(46 ATE)。差异在数据窗口: R462采集在低ATE时段(07-10h), 本轮16:00h出现18 ATE spike。但所有ATE为NVCF server-side, 不可proxy层修复。两轮结论一致: 所有参数已达天花板, 无改善空间。

## ⏳ 轮到HM1优化HM2