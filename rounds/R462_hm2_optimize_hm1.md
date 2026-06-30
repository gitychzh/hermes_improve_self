# R462: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项24h实测全部证伪 · 全参数天花板 · 24h 1796req/100% · 0 429/0 empty200/0 ATE · 5-key均衡 · FASTBREAK=3救回65/65含超时 · throttle峰值4.68req/min仅30%利用非瓶颈 · 铁律:只改HM1不改HM2 · 零配置变更

**方向**: HM2 优化 HM1 (本轮执行者=HM2, 对端=HM1, host_machine=opc_uname)
**动作**: NOP (零配置变更)
**时间**: 2026-06-30 16:40 UTC (DB ts 00:40, +8h偏移已校正; CST 00:40)
**轮次**: R462 → 接R461(HM1→HM2: NOP, commit 1f158bc)

## 0. 时区与host标识 (R320教训#5, R460纠正沿用)

- DB `ts` 比真实UTC快8h。真实UTC=16:40时 DB max ts=2026-07-01 00:39(次日)。所有窗口查询用绝对ts时间戳, 禁用 NOW()。实测: `SELECT max(ts), now()` → max ts=00:39:47, now()=16:40:11, 差8h ✓
- 对端HM1 host_machine 标识=`opc_uname` (HM1写入DB值, R460已确认)。litellm_model=`nvcf_deepseek%`(HM1侧 deepseek 模型)。
- hm_tier_attempts 表无 host_machine 列, 用 `litellm_model LIKE 'nvcf_deepseek%'` 过滤HM1侧。

## 1. 数据采集 (HM1 对端, host_machine=opc_uname)

### 1a. 容器env (8参数, /opt/cc-infra/docker-compose.yml L418-454 = 容器运行态)
```
MIN_OUTBOUND_INTERVAL_S=3.8       (L421)  TIER_TIMEOUT_BUDGET_S=125 (L419)
UPSTREAM_TIMEOUT=45               (L418)  KEY_COOLDOWN_S=25         (L422)
TIER_COOLDOWN_S=38                (L423)  HM_CONNECT_RESERVE_S=10   (L452)
HM_PEXEC_TIMEOUT_FASTBREAK=3      (L454)  HM_SSLEOF_RETRY_DELAY_S=2.0 (L453)
```
compose L418/L419/L421/L422/L423/L452/L453/L454 与容器 `docker exec hm40006 env` 逐字一致 → **双处零漂移** ✓
/health=200 OK (port 40006), proxy_role=passthrough, hm_num_keys=5, hm_model_tiers=["dsv4p_nv"], hm_default_model="dsv4p_nv"。
容器 StartedAt: 2026-06-30T16:30:58Z (本轮采集前约10min重启过, 参数零变更, env与compose一致)。

### 1b. DB 30min (真实UTC 16:09-16:39 = DB ts 23:39-00:39)
| 指标 | 数值 |
|------|------|
| 总请求 | 61 |
| 成功 (200) | 61 (100.00%) |
| 失败 | 0 |
| p50 | 35,788ms |
| p95 | 103,969ms |
| max | 110,807ms |
| 429 | 0 |
| empty200 | 0 |

低流量窗口(2.03 req/min), 100%成功, 无任何错误。p50偏高(35.8s)因低流量时段NVCF后端慢响应(非参数问题)。

### 1c. DB 30min per-key (5-key 均衡验证, success+fail)
| nv_key_idx | reqs | ok | err | avg_ms | p50 | p95 | max |
|------|------|----|----|--------|------|------|------|
| 0 (k1) | 1 | 1 | 0 | 29,666 | 29,666 | 29,666 | 29,666 |
| 1 (k2) | 20 | 20 | 0 | 43,472 | 45,195 | 82,781 | 103,969 |
| 2 (k3) | 1 | 1 | 0 | 32,816 | 32,816 | 32,816 | 32,816 |
| 3 (k4) | 24 | 24 | 0 | 42,731 | 42,874 | 102,711 | 109,598 |
| 4 (k5) | 15 | 15 | 0 | 34,982 | 23,031 | 100,378 | 110,807 |

5 key全部有成功, 0失败。低流量下per-key样本少(k1/k3各1), 但k2/k4/k5样本足(15-24)显示无单key劣化。k4(idx3) max=109.6s非劣化(k5 max=110.8s更高), **无HM1-k4式劣化**。

### 1d. DB 24h聚合 (真实UTC 06-29 16:39~06-30 16:39 = DB 00:39~00:39)
| 指标 | 数值 |
|------|------|
| 总请求 | 1,796 |
| 成功 (200) | 1,796 (100.00%) |
| 失败 | 0 |
| 429 | 0 |
| empty200 | 0 |
| all_tiers_exhausted | 0 |
| p50 | 7,926ms |
| p95 | 51,576ms |

**24h连续零失败**, 0个429, 0个empty200, 0个all_tiers_exhausted。p50=7.9s。

### 1e. DB 24h error_type 结构
| error_type | count | avg_ms |
|------|------|------|
| (无失败行) | 0 | — |

24h hm_requests表零失败行, 无错误结构可分析。

### 1f. DB 6h tier_attempts (hm_tier_attempts, litellm_model LIKE 'nvcf_deepseek%', DB 18:39-00:39)
- 79 attempts, 全部 NVCFPexecTimeout, 0 直接成功
- avg_elapsed=45,677ms, max=49,493ms (≈UPSTREAM_TIMEOUT=45s)
- per-key: k0=18, k1=9, k2=27, k3=11, k4=14 (均匀, 无单key被NVCF标记)

### 1g. DB 6h ATE涉及请求最终状态 (FASTBREAK=3 救回验证)
| 最终status | count |
|------|------|
| 200 | 65 |

6h 79次NVCFPexecTimeout tier attempt涉及65个去重请求, **65个全部最终200成功** → FASTBREAK=3触发后key rotation救回。**无一请求陷入all_tiers_exhausted**。零误杀。

### 1h. DB 24h逐时吞吐
| 真实UTC hour | reqs | reqs/min | p50 |
|------|------|------|------|
| 03:00 | 22 | 0.37 | 6,032 |
| 04:00 | 32 | 0.53 | 10,885 |
| 07:00 | 21 | 0.35 | 5,564 |
| 08:00 | 138 | 2.30 | 6,748 |
| 09:00 | 207 | 3.45 | 7,435 |
| 10:00 | 234 | 3.90 | 7,456 |
| 11:00 | 281 | 4.68 | 9,587 |
| 12:00 | 228 | 3.80 | 7,734 |
| 13:00 | 132 | 2.20 | 6,611 |
| 14:00 | 242 | 4.03 | 7,164 |
| 15:00 | 113 | 1.88 | 10,280 |
| 16:00 | 66 | 1.10 | 32,522 |

吞吐峰值=4.68 req/min (11:00), 多数时段2-4 req/min。throttle理论上限=60/3.8=15.8 req/min, 实测峰值仅30%利用 → **throttle非瓶颈**。吞吐波动=流量驱动。

## 2. CC清单评估 ([HM1-A/B/C] 节, 对端=HM1)

### [HM1-A] MIN_OUTBOUND_INTERVAL_S → 证伪
CC清单称"throttle=18.2s锁死吞吐, 降到9.0翻倍"。当前实测**再次证伪**:
- **当前**: MIN_OUTBOUND=3.8 (compose L421, R442: 4.0→3.8), **非清单所述18.2**(过时值, R460已纠正)
- **数据**: 24h吞吐峰值4.68 req/min = 每12.8s一个请求, **远大于throttle的3.8s间隔**
- 若throttle是瓶颈, 最大吞吐=60/3.8=15.8 req/min, 但实测峰值才4.68(仅30%利用)
- 24h p50=7.9s vs throttle=3.8s, gap=2.1x, throttle完全不是瓶颈
- 24h 0个429 → 降throttle无429风险缓冲, 降即增429风险无收益
- **结论**: 证伪, 不可行 (与R460一致)

### [HM1-B] k4路由劣化修复 → 证伪
CC清单称"k4(direct, idx=3) avg28.5s p95=72.9s max162.9s, 本机IP被NVCF标记"。当前实测**再次证伪**:
- 24h 0失败, 5 key全部有成功(30min per-key表)
- 6h tier错误均匀分布(k0-4: 18/9/27/11/14), **无单key被标记**
- 30min idx3(k4) avg42.7s p95=102.7s max109.6s, 但k5(idx4) max110.8s更高, k4非劣化
- k2(idx2)错误最多(27)但全部通过rotation救回(65/65成功), 非本机IP问题
- **结论**: 证伪, 均衡已达成, 无key需要改路由 (与R460一致)

### [HM1-C] all_tiers_exhausted早fail → 证伪
CC清单称"22次失败avg104s共耗2288s, 前3key全timeout即fast-fail省50s/次"。当前实测**再次证伪**:
- 24h **0个all_tiers_exhausted**(hm_requests表0失败)
- 虽有79次NVCFPexecTimeout tier attempt(65请求), 但FASTBREAK=3已全部救回(65/65=100%最终200)
- 无失败可早fail → 改源码upstream.py无任何收益, 徒增源码风险
- **结论**: 证伪, BUDGET未触发, FASTBREAK=3已有效 (与R460一致)

### FASTBREAK=3 → 确认有效
- 6h 79次NVCFPexecTimeout涉及65请求, **全部最终200成功**
- FASTBREAK=3在第3次timeout(~92s)后break换key, 救回所有65请求
- 已达最优值, 无须调整

### 全参数天花板确认
- 8参数全部验证compose L418-454 = 容器env, 零漂移
- 24h 100%成功率, 0×429, 0×empty200, 0×all_tiers_exhausted
- 5 key错误均匀分布(6h 9-27), 无劣化key
- FASTBREAK=3 active, 救回65/65含超时请求
- 吞吐throttle利用率仅30%, throttle非瓶颈

## 决策: NOP · 零配置变更

**理由**: CC清单[HM1-A/B/C]三项全部被24h实测证伪。HM1侧已达全参数天花板:

| 参数 | 值 | 状态 |
|------|-----|------|
| MIN_OUTBOUND | 3.8 | 已最优 (清单18.2过时, 实测3.8, throttle利用率仅30%非瓶颈, 0×429) |
| KEY_COOLDOWN | 25 | 已最优 (6h 5-key均衡) |
| TIER_COOLDOWN | 38 | 已最优 (TIER=38>KEY=25, 单tier模型) |
| UPSTREAM_TIMEOUT | 45 | 已最优 (tier attempt avg 45.7s≈45s 覆盖) |
| BUDGET | 125 | 已最优 (24h 0 ATE, FASTBREAK先于BUDGET触发) |
| CONNECT_RESERVE | 10 | 已最优 |
| SSLEOF_RETRY | 2.0 | 已最优 (0 SSLEOF失败) |
| FASTBREAK | 3 | 已最优 (6h救回65/65=100%, 零误杀) |

**铁律**: 只改HM1不改HM2 ✓ · 零配置变更 · 零docker compose重启 · 零容器env改动

## 改前/改后对比 (NOP, 同窗口)
| 指标 | 改前(30min) | 改后(30min) |
|------|------|------|
| reqs | 61 | 61 (NOP, 同窗口) |
| 成功率 | 100.00% | 100.00% |
| p50 | 35,788ms | 35,788ms |
| p95 | 103,969ms | 103,969ms |
| 429 | 0 | 0 |
| empty200 | 0 | 0 |

NOP轮无配置变更, 改前=改后同窗口。24h长窗口(1796req/100%)为稳态证据。

## 历史对比
| 轮次 | 30min reqs | 30min成功率 | 24h reqs | 24h成功率 | 变更 |
|------|-----------|------------|---------|---------|------|
| R462 | 61 | 100.00% | 1796 | 100.00% | ⏸️ NOP |
| R460 | 26 | 100.00% | 1593(8h) | 100.00% | ⏸️ NOP |

30min 61req/100% — 流量较R460(26req)回升, 成功率持平100%。24h 1796req/100%稳定(R460 8h 1593req/100%, 同期数据)。失败结构未变(0失败, 0 ATE)。

## 部署
```bash
# 无操作 — 容器 keep running (StartedAt 2026-06-30T16:30:58Z, 参数零变更)
# 验证: /health=200 OK (port 40006), hm_num_keys=5, 8项env双处零漂移
# compose /opt/cc-infra/docker-compose.yml L418-454 = 容器运行态, 双处一致
# HM1 env与R460逐字一致, 零漂移
```

## ⏳ 轮到HM1优化HM2
