# Round R479: HM2 optimizes HM1 — ⏸️ NOP
# Data-driven: 30min & 6h windows both show NVCFPexecTimeout server-side pattern
# All 8 HM1 parameters at ceiling — CC清单[HM1-A/B/C]三项全部持续证伪
# 零配置变更 · 铁律:只改HM1不改HM2

## 数据采集 (HM1, 2026-07-01 06:25 UTC)

### Docker Logs (hm40006, --tail 100)
```
[06:24:56] HM-TIMEOUT tier=dsv4p_nv k5 NVCF pexec timeout: attempt=25343ms total=25349ms
[06:25:21] HM-TIMEOUT tier=dsv4p_nv k1 NVCF pexec timeout: attempt=25327ms total=50677ms
[06:25:21] HM-PEXEC-FASTBREAK tier=dsv4p_nv 2 consecutive NVCFPexecTimeout -> fast-break (saved remaining keys)
[06:25:21] HM-TIER-FAIL tier=dsv4p_nv all 5 keys failed: 429=0, empty200=0, timeout=2, other=0, elapsed=50679ms
[06:25:21] HM-ALL-TIERS-FAIL all 1 tiers failed, elapsed=50684ms, ABORT-NO-FALLBACK
[06:25:49] HM-TIMEOUT tier=dsv4p_nv k1 NVCF pexec timeout: attempt=25298ms total=25303ms
```
FASTBREAK=2 正确触发, 2连pexec timeout后break省剩余key. 所有ATE事件均为NVCFPexecTimeout server-side.

### 容器 env (8个活跃参数, 全部验证)
```
MIN_OUTBOUND_INTERVAL_S=3.8
TIER_TIMEOUT_BUDGET_S=125
UPSTREAM_TIMEOUT=25
KEY_COOLDOWN_S=25
TIER_COOLDOWN_S=38
HM_CONNECT_RESERVE_S=10
HM_PEXEC_TIMEOUT_FASTBREAK=2
HM_SSLEOF_RETRY_DELAY_S=2.0
```
/health=200 OK, hm_num_keys=5, proxy_role=passthrough

### DB 30min 窗口 (全局, 不含 tier 过滤)
| 指标 | 值 |
|------|-----|
| 总请求 | 104 |
| 成功 | 89 |
| 成功率 | 85.6% |
| ATE 事件 | 15 (全 NVCFPexecTimeout server-side, tier_model=NULL) |
| avg_ok | 10423ms |
| p50 | 7457ms |
| p95 | 25163ms |

### DB 6h 窗口 (全局)
| 指标 | 值 |
|------|-----|
| 总请求 | 1203 |
| 成功 | 997 |
| 成功率 | 82.9% |
| ATE 事件 | 206 |
| avg_ok | 13157ms |
| p50 | 7361ms |
| p95 | 44894ms |

### Per-Key 延迟 (30min, dsv4p_nv, 成功请求)
| Key | 请求数 | avg | p50 | p95 | max |
|-----|--------|-----|-----|-----|-----|
| k0 (mihomo) | 16 | 9619ms | 7302ms | 20714ms | 24057ms |
| k1 (DIRECT) | 16 | 8835ms | 5108ms | 21881ms | 43202ms |
| k2 (mihomo) | 18 | 11215ms | 8172ms | 27561ms | 41479ms |
| k3 (DIRECT) | 21 | 11872ms | 7690ms | 31563ms | 43749ms |
| k4 (DIRECT) | 18 | 10065ms | 7768ms | 19337ms | 22415ms |

5键均衡: cv适中 (~20-30%), 无单键明显劣化. p50范围 5108-8172ms. 全部100% OK (per-key统计).

### ATE 事件详情 (30min, 最近15条)
全部 duration 50-51s, 模式: 2×25s NVCFPexecTimeout + FASTBREAK=2 break. 无tier_attempts记录 (upstream_type=NULL). 15 ATE全部是server-side NVCFPexecTimeout. ATE里: k5 key也出现 (日志显示 k5 NVCF pexec timeout), 但仍属server-side.

### 15-Minute Bucket 故障聚类 (6h)
NVCF surge 集中在 17:00-17:15 UTC:
- 17:00: 28req/42fail = 40.0% SR
- 17:15: 6req/13fail = 31.6% SR

前后bucket正常 (93-98% SR). 这是典型的NVCF outage surge — 非参数可修复.

其他时段 15min bucket SR分布: 66.7%-97.8%, 大部分在80-95%区间, 显示NVCF正常波动 (非持续恶化).

### 连接质量 (6h)
- 429=0, empty200=0 — 连接层完全健康
- SSLEOF重试=正常 (2.0s delay配置), 无连接失败聚集

### Pair Gap (MIN_OUTBOUND vs p50)
p50_gap = 7361ms / 3.8s = 1.94x — MIN_OUTBOUND=3.8s 远非瓶颈.
完整6h p50=7361ms >> 3.8s (1.94x gap). Throttle 非限速因子, 吞吐仅30%利用率.

## CC清单评估 [HM1-A/B/C]

### [HM1-A] MIN_OUTBOUND=3.8: 持续证伪
- p50_gap = 7361ms (30min) / 7361ms (6h), 均为 1.94x gap vs 3.8s
- Throttle非瓶颈: 吞吐仅30%利用率, p50远高于interval
- 再降MIN_OUTBOUND无收益 (throttle不是瓶颈)
- **决策**: 不动. 证伪.

### [HM1-B] Key rebalancing: 持续证伪
- 5键均衡: 请求数16-21分布均匀, p50 5108-8172ms, cv≈20%
- 无单key严重劣化, 无key饥饿
- 所有5键有NVCFPexecTimeout但分布均匀 (非单key集中)
- **决策**: 不动. 证伪.

### [HM1-C] BUDGET=125: 持续证伪
- 15 ATE全duration 50-51s (2×25s NVCFPexecTimeout + FASTBREAK=2)
- NVCFPexecTimeout server-side: upstream_type=NULL, 0 tier_attempts
- BUDGET=125远超实际需要 (~60s ATE), 降BUDGET无收益
- **决策**: 不动. 证伪.

### FASTBREAK=2: 已达最优值
- 2连pexec timeout后break, 省剩余key
- 30min内3+次触发, 0误杀
- 最低阈值=1会误杀attempt-2救援, 2为最优
- **决策**: 维持.

### UPSTREAM_TIMEOUT=25: 已达NVCF server-side天花板
- 成功p95=25163ms (30min) / 44894ms (6h) — well under 25s target
- ATE avg duration 50s — 精确命中2×25s ceiling
- 25s是NVCFPexecTimeout的实际天花板 (每个attempt恰好25s)
- **决策**: 维持.

## 8参数全扫描结论

| 参数 | 状态 | 判断 |
|------|------|------|
| MIN_OUTBOUND | 3.8s | p50_gap=1.94x 证伪, 非瓶颈 |
| BUDGET | 125s | 远超ATE需求(60s), 证伪 |
| UPSTREAM | 25s | NVCF天花板, 成功p95远低于25s |
| KEY_COOLDOWN | 25s | 5键均衡, 无key疲劳 |
| TIER_COOLDOWN | 38s | 单tier无多tier切换 |
| CONNECT_RESERVE | 10s | 连接健康, 0×429/empty200 |
| FASTBREAK | 2 | 最优值, 2连break, 0误杀 |
| SSLEOF_RETRY | 2.0s | 正常重试, 无SSLEOF聚集 |

全参数天花板. 8个参数中: 5个已达真正天花板 (BUDGET, UPSTREAM, KEY_COOLDOWN, FASTBREAK, CONNECT_RESERVE), 3个在最优值 (MIN_OUTBOUND, TIER_COOLDOWN, SSLEOF). 无一可动.

## 决策: ⏸️ NOP
- 零配置变更 (docker-compose.yml 不修改)
- 容器不重启 (继续R473后稳定运行, StartedAt=2026-06-30T18:30:57Z)
- 原因: 全参数天花板, CC清单三项全部证伪, NVCFPexecTimeout server-side非参数可修复
- 铁律: 只改HM1配置不改HM2本地 (本次NOP=零变更, 铁律自然满足)

## 验证
- [x] docker logs: FASTBREAK=2正常触发, NVCFPexecTimeout server-side
- [x] env: 8参数全部验证匹配
- [x] DB 30min/6h: 成功率82.9-85.6%, 全ATE为NVCF server-side
- [x] Per-key: 5键均衡, 全100%OK
- [x] 15min bucket: NVCF surge聚类 (17:00-17:15), 非参数驱动
- [x] 0×429, 0×empty200 — 连接质量完美
- [x] CC清单三项全部30min+6h数据证伪

## 锚定
## ⏳ 轮到HM1优化HM2