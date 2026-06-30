# R435: HM1→HM2 — ⏸️ NOP · CC清单三项全部做完/数据证伪 · 全参数天花板 · 100%稳定(30min)

**角色**: HM1 (执行者, opc_uname) → HM2 (目标, opc2sname, glm5.1_hm_nv)
**日期**: 2026-06-30 20:11 CST (DB ts口径, host_machine='opc2sname')
**铁律**: 只改HM2不改HM1 ✓
**前轮**: R437 (HM2→HM1, MIN_OUTBOUND 5.0→4.0, 注: 该轮把round写进了 rounds/RN_hm2_optimize_hm1.md 模板文件而非正式round文件, 违反R322教训#3; 本轮不评价对端操作, 仅记录以备CC托底)
**本轮**: 数据采集+CC清单三项逐一评估 → 判定NOP (三项全部已做完或被数据证伪)

## 0. 任务规则与本轮决策依据

任务规则: "优先执行清单第1项, 若第1项本轮无法实施(如已被前轮做过/数据不支撑), 顺延下一项。每轮只做1项。"
任务规则: "不允许'无操作'轮, 除非三项都已做完或数据证伪(证伪需给出具体数据)。"

本轮按规则逐一评估CC清单[HM2-A/B/C]三项, 结论: **A已做完 / B数据证伪 / C数据证伪**, 满足NOP例外条件。下文每项给出具体数据。

### CC清单[HM2]三项原文与评估结论
| 项 | CC原文 | 评估 | 结论 |
|---|---|---|---|
| [HM2-A] | MIN_OUTBOUND_INTERVAL_S 4.5→2.5, 降throttle提升吞吐 | 当前已是2.5(R386), 且throttle非瓶颈(p50_gap=6.54s>>2.5) | **已做完+再降证伪** |
| [HM2-B] | HM2失败模式数据补采, 看有无像HM1-k4的劣化key | 本轮补采: 5key均衡(34-36), p50 5.3-7.3s, 无劣化key | **数据证伪** |
| [HM2-C] | TIER_TIMEOUT_BUDGET_S 128→100, 失败早结束 | 当前已是85(R385), 再降误杀慢成功(6h有8个成功>60s, 3个≥85s max91.2s) | **数据证伪** |

## 1. 改前数据采集 (锚点 max_ts=2026-06-30 20:11+00, HM2 host_machine='opc2sname')

### 1a. 容器运行态env (docker exec → 全env验证, 与compose一致)
```
MIN_OUTBOUND_INTERVAL_S  = 2.5   (R386: HM1→HM2 5.0→2.5, CC HM2-A 已完成)
TIER_TIMEOUT_BUDGET_S   = 85    (R385: HM1→HM2 95→85, CC HM2-C 已降到85)
HM_CONNECT_RESERVE_S    = 8     (R431: HM1→HM2 10→8)
HM_SSLEOF_RETRY_DELAY_S = 1.0   (R321: HM1→HM2 3.0→1.0)
HM_PEXEC_TIMEOUT_FASTBREAK = 5  (R384: HM1→HM2 3→5)
UPSTREAM_TIMEOUT        = 50    (R284)
KEY_COOLDOWN_S          = 38    (R275)
TIER_COOLDOWN_S         = 22    (R1)
```
Routing: k1→DIRECT(PROXY_URL1空), k2→7895(mihomo), k3→DIRECT(PROXY_URL3空), k4→7897(mihomo), k5→DIRECT(PROXY_URL5空)
容器StartedAt=2026-06-30T11:34:46Z, /health=200 ok, 5 keys, glm5.1_hm_nv ✓

### 1b. 30min窗口成功率 (19:33:35~20:03:35 UTC, ts口径 max(ts)-30min)
| total | success | 429 | ATE | 5xx | 成功率 | reqs/min | avg_ms | p50 | p95 |
|---|---|---|---|---|---|---|---|---|---|
| 174 | 174 | 0 | 0 | 0 | 100.00% | 5.80 | 9100 | 6012 | 30305 |

### 1c. per-key成功延迟 (30min, status=200)
| nv_key_idx | cnt | avg_ms | p50 | p95 | max_ms |
|---|---|---|---|---|---|
| 0 (k1 DIRECT) | 35 | 9622 | 5868 | 26118 | 45890 |
| 1 (k2 7895)   | 35 | 10556 | 7335 | 34221 | 44611 |
| 2 (k3 DIRECT) | 34 | 8604 | 5348 | 28559 | 48898 |
| 3 (k4 7897)   | 34 | 8449 | 5895 | 16898 | 47083 |
| 4 (k5 DIRECT) | 36 | 8262 | 5307 | 24793 | 30919 |

**5key完全均衡(34-36), p50 5.3-7.3s, 无劣化key** → [HM2-B]证伪 ✓

### 1d. pair gap分布 (30min, 162对)
| pairs | avg_gap | p50_gap | min_gap | max_gap | gap<2.5 | gap<3.0 |
|---|---|---|---|---|---|---|
| 162 | 10.95s | 6.54s | 0.14s | 167.88s | 6 (3.7%) | 9 (5.6%) |

**p50_gap=6.54s >> throttle 2.5s**: throttle=2.5在当前流量下几乎不阻塞(仅3.7% pair受影响). 再降throttle收益极小且增NVCF同IP 429风险 → [HM2-A]再降证伪 ✓

### 1e. docker logs (近20min)
```
123×HM-SUCCESS, 0 error/warn/fail/timeout/eof/empty/429/5xx/panic
全部 first-attempt success
```

## 2. CC清单三项逐一评估 (本轮核心产出)

### 2a. [HM2-A] MIN_OUTBOUND_INTERVAL_S — 已做完+再降证伪
- CC清单目标值2.5: **当前已是2.5**(R386 commit 3441e5e已完成). 清单第1项意图(降throttle提升吞吐)已收官.
- 再降到2.0的收益/风险评估: 30min仅6/162对(3.7%)gap<2.5s受throttle影响, 其中gap<2.0s仅3对. **再降2.5→2.0最多多解3对/30min, 收益<0.02req/min, 但增加NVCF同IP 429风险**(当前零429是稳定基线, 不应破坏). 证伪再降.
- compose line 472: `MIN_OUTBOUND_INTERVAL_S: "2.5"` 与容器env一致 ✓

### 2b. [HM2-B] 数据补采 — 证伪(无劣化key)
- 本轮补采30min per-key数据(见1c): 5key均衡(34-36), p50 5.3-7.3s, p95 16.9-34.2s, 无单key劣化.
- 与R387结论一致(HM2-B当时已证伪). HM2无像HM1-k4那样的劣化key.
- 结论: 无可改的路由, 证伪.

### 2c. [HM2-C] TIER_TIMEOUT_BUDGET_S — 证伪(降BUDGET误杀慢成功)
CC清单原文"128→100", 实际HM2 BUDGET已从128→100(R334)→95(R384)→85(R385), 远低于清单的100. 清单意图是"降BUDGET让失败早结束". 本轮评估再降85→更低:

**失败机制(根因分析, 数据支撑)**:
- 6h窗口23次ATE失败, avg 91.6s, min 75.5s, max 103.1s
- tier_attempts: 22次NVCFPexecTimeout, avg 47.9s, max 55.8s (≈UPSTREAM_TIMEOUT=50s, 即每次pexec hang满50s才timeout)
- ATE失败avg 91.6s ≈ 2×47.9s = 2次pexec timeout (50s + 27s, 第2次受BUDGET剩余27s限制)
- 第3次attempt前: elapsed=77s, remaining=85-77=8s < MIN_ATTEMPT_TIMEOUT=10 → break
- 故FASTBREAK=5形同虚设(BUDGET=85只够2次timeout, 永远到不了第5次)

**再降BUDGET的误杀评估(6h成功请求耗时分布)**:
| 区间 | <30s | 30-45s | 45-60s | 60-85s | ≥85s | max |
|---|---|---|---|---|---|---|
| 个数 | 1412 | 56 | 27 | 5 | 3 | 91222ms |

- 降到60s: 误杀8个成功(5个60-85s + 3个≥85s) = 0.53% 误杀率
- 降到75s: 误杀5个成功(1个75-85s + 1个70-75s + 3个≥85s) = 0.33% 误杀率
- **R385注释称"成功80-85s区间=0个", 但本轮实测6h有5个成功60-85s + 3个≥85s** — 流量模式变化后出现了新的慢成功, 降BUDGET会误杀.
- 收益: 23 ATE×省~40s/次(若降到60) = 省920s/6h; 但误杀8个成功=8×~70s变失败+成功率-0.53%
- **评判稳定>越快>成功率**: 误杀慢成功违反稳定优先, 证伪降BUDGET.

**FASTBREAK=5死参数现象(双机共性, 记录不本轮改)**: HM1(BUDGET=125,FASTBREAK=5)同样6h 7 ATE avg 104.8s ≈ 2×46.4s, FASTBREAK=5也未触发. 这是双机共同的结构性现象(BUDGET总在FASTBREAK之前逼停). 真正减少失败耗时需"早检测NVCF pexec hang"的源码改动(让单次timeout从50s降到~10s), 但6h有26个成功>48s, 早检测会误杀这些正常慢请求. 不在CC清单, 本轮不动.

## 3. 决策: ⏸️ NOP · 零配置变更

### 3a. 为什么NOP
1. **CC清单三项全部做完或证伪**: A已做完(2.5)+再降证伪, B证伪(无劣化key), C证伪(降BUDGET误杀慢成功). 满足"不允许无操作轮"的例外条件(三项证伪均给出具体数据).
2. **30min 100%成功(174/174), 0 429, 0 ATE, 0 empty_200**: 系统完全清洁.
3. **全部active参数已到天花板**:
   - MIN_OUTBOUND=2.5 (throttle非瓶颈p50_gap=6.54s>>2.5, 再降增429风险)
   - BUDGET=85 (再降误杀慢成功, 6h有8个成功>60s)
   - UPSTREAM=50 (6h 26个成功>48s, 降到45误杀35个)
   - CONNECT_RESERVE=8 (低于实测connect, 再降误杀)
   - SSLEOF_RETRY=1.0 (1h零SSLEOF, 已最小化)
   - FASTBREAK=5 (死参数, BUDGET先到, 降它无收益)
4. **HM2失败(ATE)是NVCF server-side pexec hang, 不可从proxy层修复** (R434已确认, 本轮6h 23 ATE全NVCFPexecTimeout).

### 3b. 为什么不动任何参数
| 参数 | 当前值 | 为什么不动 |
|---|---|---|
| MIN_OUTBOUND_INTERVAL_S | 2.5 | throttle非瓶颈, 再降增429风险 |
| TIER_TIMEOUT_BUDGET_S | 85 | 降BUDGET误杀慢成功(8个>60s/6h) |
| UPSTREAM_TIMEOUT | 50 | 6h 26个成功>48s, 降误杀 |
| HM_CONNECT_RESERVE_S | 8 | 低于实测connect, 再降误杀 |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | 1h零SSLEOF, 已最小化 |
| HM_PEXEC_TIMEOUT_FASTBREAK | 5 | 死参数(BUDGET先到), 降无收益 |
| KEY_COOLDOWN_S | 38 | 全键均衡无冷启动 |
| TIER_COOLDOWN_S | 22 | single-tier, 边际 |

## 4. 参数表 (本轮后HM2状态, 无变更)

| 参数 | 值 | 来源 |
|---|---|---|
| MIN_OUTBOUND_INTERVAL_S | 2.5 | R386 (HM1→HM2, 5.0→2.5) |
| TIER_TIMEOUT_BUDGET_S | 85 | R385 (HM1→HM2, 95→85) |
| HM_CONNECT_RESERVE_S | 8 | R431 (HM1→HM2, 10→8) |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | R321 (HM1→HM2, 3.0→1.0) |
| HM_PEXEC_TIMEOUT_FASTBREAK | 5 | R384 (HM1→HM2, 3→5) |
| UPSTREAM_TIMEOUT | 50 | R284 |
| KEY_COOLDOWN_S | 38 | R275 |
| TIER_COOLDOWN_S | 22 | R1 |

## 5. 结论

1. **CC清单三项全部做完或证伪**: [HM2-A]已是2.5+throttle非瓶颈再降证伪; [HM2-B]5key均衡无劣化key证伪; [HM2-C]已是85+再降误杀慢成功证伪. 满足NOP例外条件, 每项均给具体数据.
2. **数据支撑**: 30min 174/174=100%成功, 0 429, 0 ATE, 0 empty_200; 6h 1534/1534(98.31%含26失败); 24h 4723/4851=97.36%(124 ATE全NVCF server-side).
3. **全参数天花板**: 8个active参数逐一评估, 均无零误杀纯收益的改动空间.
4. **失败机制根因**: ATE=2×NVCFPexecTimeout(50s+27s), avg 91.6s, 是NVCF平台pexec hang, 不可proxy层修复; FASTBREAK=5死参数(BUDGET先到).
5. **稳定优先**: 30min 100%+0 429基线保持, 不为边际提速破坏稳定.
6. **诚实记录**: 上轮R437(HM2→HM1)把round写进RN模板文件(commit bfb0f6b改 rounds/RN_hm2_optimize_hm1.md), 违反R322教训#3, 本轮不评价对端仅记录备CC托底.

## 6. 待办 (留给下轮HM2→HM1)
- [ ] HM2→HM1: HM1侧参数天花板复查(MIN_OUTBOUND=4.0/5.0, BUDGET=125), 若有新错误类型回传.
- [ ] 双机共性: FASTBREAK=5死参数现象 — 若CC勘定"早检测NVCF pexec hang"源码改动可立项(需先评估26个>48s成功的误杀).
- [ ] NVCF server-side PexecTimeout 持续追踪 — 不可proxy层修复, 监控趋势.

## ⏳ 轮到HM2优化HM1
