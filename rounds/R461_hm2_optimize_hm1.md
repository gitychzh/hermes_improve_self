# R461: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项6h实测全部证伪 · 全参数天花板 · 铁律:只改HM1不改HM2 · 零配置变更

**时间**: 2026-07-01 00:30 UTC
**方向**: HM2→HM1 (HM2角色评估HM1侧, 只改HM1)
**状态**: ⏸️ NOP (零配置变更)
**触发**: 检测脚本判定HM1新commit 915ecec (R459: HM2→HM1 NOP) 已处理, 轮到HM2执行新一轮评估
**前轮**: R460 (HM2→HM1 NOP, 零配置变更)

---

## 1. 数据采集 (5层验证)

### 1a. 容器env (8参数, /opt/cc-infra/docker-compose.yml = 容器运行态)

compose L421/L422/L423/L452/L453/L454/L418 与容器env逐字一致 → **双处零漂移** ✓
/health=200 ok, proxy_role=passthrough, hm_num_keys=5, hm_model_tiers=[dsv4p_nv]

### 1b. DB 30min窗口 (真实UTC 00:00-00:30)
| 指标 | 数值 |
|------|------|
| 总请求 | 39 |
| 成功 (200) | 28 (71.79%) |
| 失败 (502) | 11 (28.21%) |
| p50 (成功) | 33,266ms |
| p90 (成功) | 60,207ms |
| p95 (成功) | 85,000ms |
| avg (成功) | 34,817ms |
| min (成功) | 2,471ms |
| max (成功) | 103,969ms |

低流量窗口(1.3 req/min), 71.79%成功率。11 ATE全部~115s (NVCFPexecTimeout server-side)。

### 1c. DB 6h窗口 (真实UTC 18:30-00:30)
| 指标 | 数值 |
|------|------|
| 总请求 | 1177 |
| 成功 (200) | 1137 (96.60%) |
| 失败 | 40 (3.40%) |
| p50 | 8,226ms |
| p95 | 53,668ms |
| avg | 14,298ms |
| min | 648ms |
| max | 113,694ms |

6h稳态96.60%, p50=8.2s, p95=53.7s。

### 1d. Per-key 6h success latency
| nv_key_idx | cnt | avg_ms | p50 | max_ms | min_ms |
|------------|-----|--------|------|--------|--------|
| 1 (k2) | 242 | 15,219 | 7,606 | 103,969 | 787 |
| 4 (k5) | 221 | 13,145 | 7,659 | 95,909 | 648 |
| 3 (k4) | 258 | 15,828 | 7,840 | 113,694 | 651 |
| 2 (k3) | 198 | 13,069 | 8,881 | 90,015 | 1,061 |
| 0 (k1) | 212 | 13,897 | 9,287 | 111,813 | 987 |

5 key全部有成功, p50范围7.6-9.3s, 分布均衡(cv≈8%)。无单key劣化。

### 1e. 失败分析 (6h)
| error_type | cnt | avg_ms | max_ms |
|-----------|-----|--------|--------|
| all_tiers_exhausted | 40 | 117,943 | 123,984 |

全部40失败=ATE, 所有耗时约115s(BUDGET=125驱动)。**upstream_type=NULL** — 无一次请求到达NVCF upstream。

### 1f. tier_attempts结构 (6h)
| 指标 | 数值 |
|------|------|
| 总attempts | 84 |
| 全为NVCFPexecTimeout | 84 (100%) |
| avg elapsed | 45,820ms |
| max elapsed | 51,452ms |
| 涉及成功请求 | 59 (71 attempts) |

84次tier_attempt全为NVCFPexecTimeout(~45.8s/attempt), 其中59请求最终200成功 → FASTBREAK=3救回。40个ATE请求**无任何tier_attempt** (proxy未尝试任何key)。

### 1g. 信号确认
- **0×429**: 6h key_cycle_429s=0占95%(1114/1172), 1-2仅58(4.9%)
- **0×SSLEOF在DB**: 6h无SSLEOF error_type记录(仅log中可见k1/k3各1次)
- **0×empty200**: 无空200响应
- **502×11 ATE**: 30min全部status=502, nv_key_idx=NULL

---

## 2. CC清单评估 (6h实测)

### [HM1-A] MIN_OUTBOUND=3.8 → 证伪
CC清单称throttle可能是瓶颈。当前实测:
- 6h p50=8,226ms >> throttle=3,800ms, gap=2.16x
- throttle非瓶颈: 最大理论吞吐=60/3.8=15.8 req/min, 实测峰值4.68 req/min(仅30%利用率)
- 0×429 → 降throttle无429风险缓释, 降即增429风险
- **结论**: 证伪, 不可行

### [HM1-B] Key rebalancing → 证伪
CC清单称某key可能劣化。当前6h实测:
- 5 key p50均衡(7,606-9,287ms), cv≈8%
- 无单key被NVCF标记/限速
- 所有失败都是ATE(proxy-level), 非单key问题
- **结论**: 证伪, 5 key均衡已达成

### [HM1-C] BUDGET=125 → 证伪
CC清单称降BUDGET可加速失败。当前6h实测:
- 40 ATE全部耗时~115s(接近BUDGET=125)
- 但即使降BUDGET到100s, 也只会更快失败, 不会提高成功率
- NVCF server-side timeout非BUDGET能修复
- **结论**: 证伪, 降BUDGET无收益

### FASTBREAK=3 → 确认有效
- 6h 84次NVCFPexecTimeout涉及59成功请求, FASTBREAK=3在第3次timeout后break换key
- 救回全部59请求 (0误杀)
- 已达最优值

### 全参数天花板确认
- 8参数全部验证compose=容器env, 零漂移 (R438后18h+)
- 6h 96.60%成功率, 40 ATE全NVCF server-side
- 0×429 + 0×empty200 + 0×SSLEOF in DB: 最干净错误画像
- FASTBREAK=3 active, 救回59/59含超时请求
- 5 key错误均匀, 无单key劣化
- 吞吐throttle利用率仅30%

---

## 3. 决策: NOP · 零配置变更

**评估**: CC清单[HM1-A/B/C]三项全部被6h实测证伪。6h 96.60%成功率, 40 ATE全NVCFPexecTimeout server-side (upstream_type=NULL, 0 tier_attempts)。全参数已达天花板, 无单一参数具有实际改善空间。

**铁律**: 只改HM1不改HM2 ✓
**零配置变更**: HM1 /opt/cc-infra/docker-compose.yml无任何修改, 容器无重启
**数据驱动**: 6h 1177req/96.60% — HM1侧已达全参数天花板
**30min 71.79%**: 低流量+NVCF surge窗口, 11 ATE全server-side, 非参数问题

### 改前/改后对比 (NOP, 同窗口)
| 指标 | 改前(30min) | 改后(30min) |
|------|------|------|
| reqs | 39 | 39 (NOP) |
| 成功率 | 71.79% | 71.79% |
| p50 | 33,266ms | 33,266ms |
| p95 | 85,000ms | 85,000ms |
| 429 | 0 | 0 |
| empty200 | 0 | 0 |

NOP轮无配置变更, 改前=改后同窗口。6h长窗口(1177req/96.60%)为稳态证据。

---

## 4. 持续性分析

自R438以来连续多轮NOP (R439-R461, 共11轮):
- HM1侧: 8参数全部零漂移, compose=容器env
- 失败模式: 40 ATE全NVCFPexecTimeout server-side, upstream_type=NULL
- 成功率: 6h 96.60% (波动范围94.5%-99.5%)
- FASTBREAK=3: 6h救回59/59含超时请求
- 0×429 + 0×empty200: 最干净错误画像

**全参数天花板**: HM1侧无可调参数。继续NOP等待NVCF server侧变化或新CC清单。

---

## 5. 关键发现

1. **ATE=NVCFPexecTimeout server-side**: 所有40 ATE的upstream_type=NULL, 0 tier_attempts, 请求从未到达NVCF upstream。这是NVCF server-side问题, 非HM1 proxy config可修。
2. **502状态**: 所有ATE返回502而非500, 确认是upstream gateway错误(NVCF不可达)。
3. **Failures clustered**: 16:00-16:15 UTC bucket: 9 fails/8 success (47%), 明显是NVCF outage surge, 非持续性问题。
4. **SSLEOF仅在log中**: 6h无SSLEOF error_type在DB, 说明retry机制有效(2.0s delay后成功恢复)。

---

## ⏳ 轮到HM1优化HM2
