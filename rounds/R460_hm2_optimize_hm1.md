# R460: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项8h实测全部证伪 · 全参数天花板 · 铁律:只改HM1不改HM2

**时间**: 2026-06-30 16:27 UTC (DB ts 00:27, +8h偏移已校正)  
**方向**: HM2→HM1 (HM2角色评估HM1侧, 只改HM1)  
**状态**: ⏸️ NOP (零配置变更)  
**触发**: 检测脚本判定HM1新commit 915ecec (R458: HM1→HM2 NOP) 已处理, 轮到HM2  
**前轮**: R459 (HM2→HM1 NOP, 零配置变更)

---

## 0. 关键纠正: host_machine 标识 + 时区

R459及更早轮次用 `opcsname` 作为对端HM1标识, 实测**错误**:
- 对端 `docker exec hm40006 env` → `HM_HOST_MACHINE=opc_uname`
- 对端 hostname=`opcsname`, 但写入DB的 host_machine 字段=`opc_uname`
- `opcsname` 标识的45条请求全部停在 ts 22:05(陈旧), `opc_uname` 标识的2128条活跃到 ts 00:25(当前)
- **本轮所有查询用 `host_machine='opc_uname' AND litellm_model LIKE 'nvcf_deepseek%'`** (deepseek model确认=HM1侧)

**时区校正**(R320教训#5): DB `ts` 比真实UTC快8h。真实UTC=16:27时 DB max ts=00:27(次日)。所有窗口查询用绝对ts时间戳, 禁用 NOW()。

---

## 1. 数据采集

### 1a. 容器env (8参数, /opt/cc-infra/docker-compose.yml L418-454 = 容器运行态)
```
MIN_OUTBOUND_INTERVAL_S=3.8       TIER_TIMEOUT_BUDGET_S=125
UPSTREAM_TIMEOUT=45                KEY_COOLDOWN_S=25
TIER_COOLDOWN_S=38                 HM_CONNECT_RESERVE_S=10
HM_PEXEC_TIMEOUT_FASTBREAK=3      HM_SSLEOF_RETRY_DELAY_S=2.0
```
compose L421/L419/L422/L423/L452/L453/L454/L418 与容器env逐字一致 → **双处零漂移** ✓
/health=200 ok, proxy_role=passthrough, hm_num_keys=5, hm_model_tiers=["dsv4p_nv"]

### 1b. DB 30min (真实UTC 16:00-16:27 = DB ts 00:00-00:27)
| 指标 | 数值 |
|------|------|
| 总请求 | 26 |
| 成功 (200) | 26 (100.00%) |
| 失败 | 0 |
| p50 | 34,534ms |
| p95 | 63,122ms |
| avg | 35,001ms |
| max | 103,969ms |
| 429 | 0 |
| empty200 | 0 |

低流量窗口(0.87 req/min), 100%成功, 无任何错误。

### 1c. DB 1h per-key (真实UTC 15:27-16:27 = DB ts 23:27-00:27, success only)
| nv_key_idx | reqs | ok | fail | p50 | p95 | avg | max |
|------|------|----|----|------|------|------|------|
| 0 (k1) | 1 | 1 | 0 | 29,666 | 29,666 | 29,666 | 29,666 |
| 1 (k2) | 16 | 16 | 0 | 44,394 | 99,837 | 44,397 | 103,969 |
| 2 (k3) | 1 | 1 | 0 | 32,816 | 32,816 | 32,816 | 32,816 |
| 3 (k4) | 20 | 20 | 0 | 38,652 | 75,690 | 42,572 | 109,598 |
| 4 (k5) | 10 | 10 | 0 | 21,441 | 58,786 | 27,090 | 72,229 |

5 key全部有成功请求, 0失败。k5(idx4)最快avg27s, k4(idx3)max109s但p95仅75s。**无单key劣化**。

### 1d. DB 8h聚合 (真实UTC 08:27-16:27 = DB ts 16:27-00:27)
| 指标 | 数值 |
|------|------|
| 总请求 | 1593 |
| 成功 (200) | 1593 (100.00%) |
| 失败 | 0 |
| 429 | 0 |
| empty200 | 0 |
| p50 | 7,797ms |
| p95 | 50,596ms |

**8h连续零失败**, 0个429, 0个empty200。p50=7.8s。

### 1e. DB 8h tier_attempts错误结构
| 指标 | 数值 |
|------|------|
| 总attempts | 80 |
| error attempts | 80 (全 NVCFPexecTimeout) |
| 涉及请求数 | 69 |
| avg elapsed | 45,785ms |
| max elapsed | 51,452ms |

80次tier attempt全为NVCFPexecTimeout(~45.8s/attempt, server-side), 涉及69请求。但hm_requests表这69请求**全部最终200成功** → FASTBREAK=3触发后key rotation救回。**无一请求陷入all_tiers_exhausted**。

### 1f. DB 8h per-key tier errors
| nv_key_idx | attempts | err | ok | avg_ms | max_ms |
|------|------|-----|----|------|------|
| 0 | 16 | 16 | 0 | 45,710 | 46,915 |
| 1 | 10 | 10 | 0 | 45,346 | 45,523 |
| 2 | 26 | 26 | 0 | 46,182 | 51,452 |
| 3 | 11 | 11 | 0 | 45,365 | 45,572 |
| 4 | 17 | 17 | 0 | 45,779 | 48,901 |

5 key都有NVCFPexecTimeout错误, 分布均匀(10-26), **无单key被NVCF标记/限速**。k2(idx2)最多(26)但都救回。

### 1g. DB 8h逐时吞吐
| 真实UTC hour | reqs | reqs/min | p50 |
|------|------|------|------|
| 08:00 | 131 | 2.18 | 6,936 |
| 09:00 | 207 | 3.45 | 7,435 |
| 10:00 | 234 | 3.90 | 7,456 |
| 11:00 | 281 | 4.68 | 9,587 |
| 12:00 | 228 | 3.80 | 7,734 |
| 13:00 | 132 | 2.20 | 6,611 |
| 14:00 | 242 | 4.03 | 7,164 |
| 15:00 | 113 | 1.88 | 10,280 |
| 16:00 | 25 | 0.42 | 33,716 |

吞吐峰值=4.68 req/min (11:00), 多数时段2-4 req/min。吞吐波动=流量驱动, 非throttle驱动。

---

## 2. CC清单评估 (8h实测)

### [HM1-A] MIN_OUTBOUND=3.8 → 证伪
CC清单称"throttle=18.2s锁死吞吐"是**过时数据**: 当前实测 `MIN_OUTBOUND_INTERVAL_S=3.8`(compose L421), 非清单所述18.2。
- 8h吞吐峰值4.68 req/min = 每12.8s一个请求, **远大于throttle的3.8s间隔**
- 若throttle是瓶颈, 最大吞吐=60/3.8=15.8 req/min, 但实测峰值才4.68(仅30%利用)
- 8h p50=7.8s vs throttle=3.8s, gap=2x, throttle完全不是瓶颈
- 8h 0个429 → 降throttle无429风险缓冲, 降即增429风险无收益
- **结论**: 证伪, 不可行

### [HM1-B] k4路由劣化修复 → 证伪
CC清单称"k4(direct, idx=3) avg28.5s p95=72.9s max162.9s, 本机IP被NVCF标记"。当前8h实测:
- 8h 0失败, 5 key全部有成功(1h per-key表)
- 8h tier错误均匀分布(k0-4: 16/10/26/11/17), **无单key被标记**
- idx3(k4) 1h avg42.6s p95=75.7s, 但max=109.6s不算劣化(其他key也有>100s)
- idx4(k5)反而是最快avg27s
- k2(idx2)错误最多(26)但全部通过rotation救回, 非本机IP问题
- **结论**: 证伪, 均衡已达成, 无key需要改路由

### [HM1-C] all_tiers_exhausted早fail → ���伪
CC清单称"22次失败avg104s共耗2288s, 前3key全timeout即fast-fail省50s/次"。当前8h实测:
- 8h **0个all_tiers_exhausted**(hm_requests表0失败)
- 虽有80次NVCFPexecTimeout tier attempt(69请求), 但FASTBREAK=3已全部救回
- 无失败可早fail → 改源码upstream.py无任何收益, 徒增源码风险
- **结论**: 证伪, BUDGET未触发, FASTBREAK=3已有效

### FASTBREAK=3 → 确认有效
- 8h 80次NVCFPexecTimeout涉及69请求, **全部最终200成功**
- FASTBREAK=3在第3次timeout(~92s)后break换key, 救回所有69请求
- 已达最优值, 无须调整

### 全参数天花板确认
- 8参数全部验证compose L418-454 = 容器env, 零漂移
- 8h 100%成功率, 0×429, 0×empty200, 0×all_tiers_exhausted
- 5 key错误均匀分布, 无劣化key
- FASTBREAK=3 active, 救回69/69含超时请求
- 吞吐throttle利用率仅30%, throttle非瓶颈

---

## 3. 决策: NOP · 零配置变更

**评估**: CC清单[HM1-A/B/C]三项全部被8h实测证伪。8h连续100%成功率, 0失败, 5 key均衡, FASTBREAK=3有效救回所有NVCFPexecTimeout。全参数已达天花板, 无单一参数具有实际改善空间。

**铁律**: 只改HM1不改HM2 ✓  
**零配置变更**: HM1 /opt/cc-infra/docker-compose.yml无任何修改, 容器无重启  
**数据驱动**: 8h 1593req/100% — HM1侧已达全参数天花板  
**30min 100%**: 低流量窗口(26req), 100%成功, 非参数问题

### 改前/改后对比 (NOP, 同窗口)
| 指标 | 改前(30min) | 改后(30min) |
|------|------|------|
| reqs | 26 | 26 (NOP, 同窗口) |
| 成功率 | 100.00% | 100.00% |
| p50 | 34,534ms | 34,534ms |
| p95 | 63,122ms | 63,122ms |
| 429 | 0 | 0 |
| empty200 | 0 | 0 |

NOP轮无配置变更, 改前=改后同窗口。8h长窗口(1593req/100%)为稳态证据。

---

## 4. 持续性分析

自R438以来连续多轮NOP:
- HM1侧: 8参数全部零漂移, compose L418-454=容器env
- 失败模式: 8h 0失败(前轮报的39 ATE是基于过时host标识opcsname的陈旧数据)
- 成功率: 8h 100%
- FASTBREAK=3: 8h救回69/69含超时请求
- 0×429 + 0×empty200: 最干净错误画像

**全参数天花板**: HM1侧无可调参数。继续NOP等待NVCF server侧变化或CC新清单。

---

## 5. 关键纠正记录 (供后续轮次)

1. **host_machine标识**: 对端HM1写入DB的标识是 `opc_uname`(非opcsname)。opcsname的45条是陈旧数据。后续轮次查HM1数据应用 `host_machine='opc_uname' AND litellm_model LIKE 'nvcf_deepseek%'`。
2. **CC清单[HM1-A]的"18.2s"是过时数据**: 当前实测3.8s(compose L421), 已在R442从4.0→3.8。
3. **时区**: DB ts比真实UTC快8h, 窗口查询用绝对ts。

---

## ⏳ 轮到HM1优化HM2
