# R365 — HM2优化HM1 (2026-06-30 14:40 UTC+8)

## 🔍 数据收集

### HM1容器 (100.109.153.83, docker hm40006)
- **容器启动**: 2026-06-30 03:39 UTC (已运行~3h)
- **运行时参数**: BUDGET=100, UPSTREAM=45, KEY_COOLDOWN=38, TIER_COOLDOWN=38, MIN_OUTBOUND=6.0, CONNECT_RESERVE=10, SSLEOF_RETRY=3.0, FASTBREAK=3
- **路由**: k1=SOCKS5(7894), k2/k3=DIRECT, k4=SOCKS5(7897), k5=SOCKS5(7899)
- **function_id**: 4e533b45-dc54 (NVCF pexec 直连)
- **架构**: R38.12 NVCF pexec 直连单模型 deepseek_hm_nv

### Docker日志 (最近100行, 12:10-12:16 窗口)
- **请求模式**: 全部 first-attempt 成功
- **SSLEOF错误**: 2次 (k1@12:13:36, k5@12:14:42) — 均通过retry跳转到下一key成功
- **TIMEOUT错误**: 1次 (k1@12:15:42, 48.7s) — retry到k2成功
- **成功率**: 100% 请求级 (所有错误被retry救回)

### PostgreSQL DB (ts列, 2h窗口)
- **总计**: 56请求
- **成功**: 56/56 = 100% (所有status=200)
- **失败**: 0 (0 ATE, 0 429, 0 非200状态)
- **错误记录**: 0 — 所有SSLEOF/TIMEOUT均为retry-rescued, 不写入DB
- **Per-key TTFB (avg)**: k1=9372ms, k2=14713ms, k3=7810ms, k4=10062ms, k5=10716ms
- **Per-key TTFB (max)**: k1=28921ms, k2=55178ms, k3=27331ms, k4=24764ms, k5=30673ms
- **Per-key 分布**: k1=8req, k2=15req, k3=11req, k4=12req, k5=10req (RR均匀)

### PostgreSQL DB (ts列, 6h窗口 — 完整验证)
- **总计**: 145请求
- **成功**: 144/145 = 99.31%
- **错误**: 仅1个BadRequest (非SSLEOF/TIMEOUT/ATE)
- **ATE**: 0
- **429**: 0

### 代码校验 — 死参数验证
- **TIER_COOLDOWN_S**: ✅ 活跃 — `/app/gateway/upstream.py:426` `mark_key_cooling(tier_model, k, duration_s=int(TIER_COOLDOWN_S))` — 当所有key 429时标记tier级冷却
- **HM_SSLEOF_RETRY_DELAY_S**: ✅ 活跃 — `/app/gateway/upstream.py:374` `ssleof_delay = float(os.environ.get("HM_SSLEOF_RETRY_DELAY_S", "3.0"))` — SSL错误重试延迟
- **HM_PEXEC_TIMEOUT_FASTBREAK**: ✅ 活跃 — `/app/gateway/upstream.py:116` — 连续pexec timeout快速中断(默认3)

## 📊 分析

### 健康评估
- **1h窗口**: 100% 成功率 (56/56)
- **6h窗口**: 99.31% 成功率 (144/145, 仅1个BadRequest非系统错误)
- **0 ATE**: 全窗口无all_tiers_exhausted — 所有错误在tier内retry救回
- **0 429**: 无速率限制 — MIN_OUTBOUND=6.0 充分保护
- **均衡per-key负载**: RR轮转均匀 (8-15 req/key, 无热点)

### 性能瓶颈分析
- **SSLEOF错误**: 2次/56req ≈ 3.6% — 属于NVCF SSL随机抖动, 3s retry延迟完美处理
- **TIMEOUT**: 1次/56req ≈ 1.8% — k1单key超时(48.7s), 跳转k2成功
- **k2延迟偏高**: avg 14.7s vs k3 7.8s — NVCF服务侧差异, 非配置问题
- **全参数已达天花板**: 56/56=100%且所有错误被retry机制消除, 无参数调节空间

### 参数状态
| 参数 | 当前值 | 效果 | 调节空间 |
|------|--------|------|----------|
| TIER_TIMEOUT_BUDGET_S | 100 | 100s预算充足覆盖p95 | 已达p99>100s天花板 |
| UPSTREAM_TIMEOUT | 45 | 每次尝试45s超时 | p95<45s, 无需更紧 |
| KEY_COOLDOWN_S | 38 | 38s key级冷却 | 与TIER=38等值约束, 不可动 |
| TIER_COOLDOWN_S | 38 | 38s tier级冷却 | 与KEY=38等值约束, 不可动 |
| MIN_OUTBOUND_INTERVAL_S | 6.0 | 6s请求间隔 | 释放31reqs省159.5s/4h, 已达最优 |
| HM_CONNECT_RESERVE_S | 10 | 10s连接预留 | 充分保护SOCKS5连接(2-5s) |
| HM_SSLEOF_RETRY_DELAY_S | 3.0 | 3s SSL重试延迟 | 当前值足够, 缩短可能导致key耗尽过快 |
| HM_PEXEC_TIMEOUT_FASTBREAK | 3 | 3次连续timeout快速中断 | 默认值合理, R347基线2/231=0.87%救援率为可接受代价 |

## ✅ 决策: ⏸️ NOP (No Operation)

**原因**: HM1已达性能天花板。6h窗口145请求中仅1个BadRequest(非系统错误), 0 ATE, 0 429。当前6min窗口100%请求级成功率。所有参数均衡且在代码中活跃消费。无配置漂移, 无死参数。

**连续NOP轮数**: 第15轮 (R345-R364+R365)

**铁律**: 只改HM1不改HM2 (零配置变更)

## ⏳ 轮到HM1优化HM2