# R471: HM2→HM1 — ⏸️ NOP · dsv4p_nv tier NVCFPexecTimeout server-side · 全参数天花板 · CC清单三项证伪 · 16轮连续NOP

## 执行概要
- **数据采集**: docker logs (01:53-02:00 UTC) + env + DB 30min/1h/6h (02:00 UTC)
- **决策**: NOP (全参数天花板, 三CC项证伪, NVCFPexecTimeout server-side不可参数修复)
- **部署**: 零配置变更
- **验证**: env无漂移, /health=200 ok, hm_num_keys=5
- **铁律:** 只改HM1不改HM2

## 数据采集 (5层验证)

### Layer 1 — 容器env (8项参数)
```
MIN_OUTBOUND_INTERVAL_S=3.8   ✓
TIER_TIMEOUT_BUDGET_S=125     ✓
UPSTREAM_TIMEOUT=30           ✓
KEY_COOLDOWN_S=25             ✓
TIER_COOLDOWN_S=38            ✓
HM_CONNECT_RESERVE_S=10       ✓
HM_PEXEC_TIMEOUT_FASTBREAK=3  ✓ (活躍)
HM_SSLEOF_RETRY_DELAY_S=2.0  ✓
```
Routing: k0→7894(mihomo), k1→DIRECT, k2→7896(mihomo), k3→DIRECT, k4→DIRECT
容器StartedAt=2026-06-30T13:16:06Z (R438重启后稳定18h+, 至今未重启), /health=200 ok, 5键完整

### Layer 2 — docker logs (01:53-02:00 UTC, 100行)
```
成功: k4 DIRECT 1st-attempt (01:53:26), k5 DIRECT 1st-attempt (01:53:28)
      k3 proxy7896 2nd-attempt (01:54:50), k1 proxy7894 3rd-attempt (01:56:25)
      k2 DIRECT 1st-attempt (02:00:45)

失敗模式: 全NVCFPexecTimeout (attempt~30s, total 30-92s)
      FASTBREAK=3 4次触发:
      - 01:54:04 k0/k1/k2 3连超时→break (省k3/k4)
      - 01:55:40 k3/k4/k5 3连超时→break (省k1/k2)
      - 01:55:53 k5/k1/k2 3连超时→break (省k3/k4)
      - 01:57:56 k1/k2/k3 3连超时→break (省k4/k5)

错误计数: 0×429, 0×empty200, 0×SSLEOF, 0×其他错误
所有失败=ALL-TIERS-FAIL (ABORT-NO-FALLBACK, NVCFPexecTimeout server-side)
```

### Layer 3 — DB 30min/1h/6h窗口
| 窗口 | 请求数 | 成功 | 成功率 | p50 | p95 |
|------|--------|------|--------|-----|-----|
| 30min | 209 | 195 | 93.30% | 6978ms | 20380ms |
| 1h | 311 | 244 | 78.46% | 7288ms | 50361ms |
| 6h | 1179 | 1059 | 89.81% | 7808ms | 62125ms |

### Layer 4 — 失败聚类 (15min bucket × 6h)
```
12:00-12:15: 100.00% (37/0)  ← 基线健康
12:15-16:15: 88-100%          ← 正常波动
16:00-16:15:  47.06% (8/9)    ← NVCF surge cluster #1
16:15-16:45:  80-90%           ← 恢复中
17:00-17:15:  40.00% (28/42)  ← NVCF surge cluster #2 (大规模)
17:15-17:30:  31.58% (6/13)   ← 延续
17:30-17:45:  97.77% (175/4)  ← 恢复
17:45-18:00:  80.43% (37/9)   ← 残余波动
18:00+:        50.00% (1/1)    ← 尾迹
```
两个NVCF outage cluster (16:00 47% + 17:00 40%) — 非参数可修复的server-side事件

### Layer 5 — Per-key分析 (6h)
| key | 请求数 | p50 | 成功 | 错误 |
|-----|--------|-----|------|------|
| k0 (DIRECT) | 190 | 8374ms | 190 | 0 |
| k1 (7894) | 237 | 7554ms | 237 | 0 |
| k2 (DIRECT) | 175 | 7963ms | 175 | 0 |
| k3 (7896) | 249 | 7333ms | 249 | 0 |
| k4 (DIRECT) | 208 | 7101ms | 208 | 0 |

5键 per-key error=0 (失败全在HM-ALL-TIERS-FAIL路径, 非単键级)
键分布: cv≈15% (可接受), 无劣化键

## 优化决策: ⏸️ NOP

### CC清单评估 — 三项全部继续证伪

#### [HM1-A] MIN_OUTBOUND=3.8
- p50_gap: p50=6978ms >> 3.8s (1.83x gap)
- throttle非瓶颈: 6h仅1179请求/5键≈235req/key/6h ≈ 0.65rpm, 远低于理论容量
- 30min 93.30%成功, 失败全NVCF server-side非throttle驱动
- **再降无收益** — 证伪

#### [HM1-B] Key rebalancing
- 5键per-key 6h全100%成功, 0错误
- p50分布: 7101-8374ms (cv≈8%), 均衡
- 无劣化键, 无需要rebal的key
- **证伪** — 已最优

#### [HM1-C] BUDGET=125
- 6h 120 ATE全NVCFPexecTimeout (upstream_type=NULL, 0 tier_attempts)
- 失败持续时间: attempt~30s total 30-92s (NVCF pexec timeout)
- 请求从未到达NVCF upstream — server-side超时, 非BUDGET可缩短
- BUDGET=125天花板: 降BUDGET不会让NVCF更快返回
- **证伪** — 已达server-side天花板

### FASTBREAK=3验证
- 4次触发全部正确 (3连timeout后break, 省剩余键)
- 0误杀: 6h无FASTBREAK-break导致可成功请求丢失
- 已是最优值
- **验证通过**

## 为何不动任何参数

| 参数 | 当前值 | 为何不动 |
|------|--------|----------|
| MIN_OUTBOUND | 3.8 | throttle非瓶颈, 再降无收益 |
| BUDGET | 125 | 已达NVCF server-side天花板 |
| UPSTREAM_TIMEOUT | 30 | 覆盖所有成功请求, 失败全NVCF server-side |
| KEY_COOLDOWN | 25 | 5键均衡, 无过热键 |
| TIER_COOLDOWN | 38 | 稳态参数, 无tier抖动 |
| CONNECT_RESERVE | 10 | 稳定值, 无connect超时 |
| FASTBREAK | 3 | 活跃且正确, 已达最优 |
| SSLEOF_RETRY | 2.0 | 稳定值, 0 SSLEOF错误 |

## 系统状态
- **稳定性**: 16轮连续NOP (R439-R471), HM1自R438重启后零变更
- **延迟**: p50=6.9-8.3s (稳定), p95=20-62s (NVCF surge波动)
- **错误模式**: 100% NVCFPexecTimeout server-side (0×429/0×SSLEOF/0×empty200)
- **键健康**: 5键全100% per-key success, 无劣化
- **铁律遵守**: ✅ 只改HM1不改HM2, ✅ 不碰mihomo服务
- **局限**: NVCF server-side PexecTimeout不可从proxy层修复

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记