# R440: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项重验全部证伪 · 全参数��花板 · 30min 102/105=97.14% · 0 429 · 8 ATE/6h全NVCF server-side PexecTimeout · throttle已是4.0非瓶颈(p50_gap8.26s>>4.0) · 5key均衡无劣化key · 降BUDGET误杀22个慢成功(60-125s) · 铁律:只改HM1不改HM2 · 零配置变更

**角色**: HM2 (执行者, opc2_uname) → HM1 (目标, opc_uname/opcsname, dsv4p_nv)
**日期**: 2026-06-30 20:20-20:25 CST (DB ts口径, host_machine='opc_uname')
**铁律**: 只改HM1不改HM2 ✓
**前轮**: R439 (HM1→HM2, ⏸️ NOP, CC清单[HM2-A/B/C]三项证伪)
**本轮**: 数据采集+CC清单[HM1-A/B/C]三项重验 → 判定NOP (三项全部已做完或被当前数据证伪)

## 0. 任务规则与本轮决策依据

任务规则: "优先执行清单第1项, 若第1项本轮无法实施(如已被前轮做过/数据不支撑), 顺延下一项。每轮只做1项。"
任务规则: "不允许'无操作'轮, 除非三项都已做完或数据证伪(证伪需给出具体数据)。"

本轮按规则逐一重验CC清单[HM1-A/B/C]三项, 结论: **A已超额完成+再降证伪 / B勘定前提与当前数据不符证伪 / C降BUDGET误杀慢成功证伪**, 满足NOP例外条件。下文每项给出本轮新采的具体数据。

注: R439末尾标记"⏳ 轮到HM2优化HM1", 本轮接手HM2→HM1, 无抢跑(R439 commit 1b474e1后HM1侧未触发新round)。

## 1. 改前数据采集 (锚点 max_ts=2026-06-30 20:23:43+00, HM1 host_machine='opc_uname')

### 1a. 容器运行态env (docker exec → 全env验证)
```
MIN_OUTBOUND_INTERVAL_S  = 4.0   (R437: HM2→HM1 5.0→4.0; R438前已是5.0)
TIER_TIMEOUT_BUDGET_S   = 125   (R438未动, 仍125)
UPSTREAM_TIMEOUT        = 45    (R438未动)
KEY_COOLDOWN_S          = 25    (R438: HM2→HM1 38→25)
TIER_COOLDOWN_S         = 38    (R438未动)
HM_CONNECT_RESERVE_S    = 10    (R438未动)
HM_PEXEC_TIMEOUT_FASTBREAK = 5  (R438未动)
HM_SSLEOF_RETRY_DELAY_S = 2.0   (R438未动)
```
Routing (HM_NV_PROXY_URL*): k0(idx0)→7894, k1(idx1)→DIRECT, k2(idx2)→7896, k3(idx3)→DIRECT, k4(idx4)→DIRECT
容器StartedAt=2026-06-30T12:09:03Z (R438重启后未变), /health=200 ok, hm_num_keys=5, dsv4p_nv ✓

### 1b. 30min窗口成功率 (19:53:59~20:23:43 UTC, ts口径 max(ts)-30min)
| total | success | empty200 | 429 | ATE | 5xx | 成功率 | reqs/min | avg_ms | p50 | p95 |
|---|---|---|---|---|---|---|---|---|---|---|
| 105 | 102 | 2 | 0 | 3 | 3 | 97.14% | 3.50 | 14461 | 7809 | 50193 |

注: empty200指status=200但duration_ms<1000的空响应(2个/30min, 1.9%), 非系统性, 不在本轮CC清单。

### 1c. per-key成功延迟 (6h窗口 14:23~20:23 UTC, status=200)
| nv_key_idx | cnt | avg_ms | p50 | p95 | max_ms | gt45s | empty200 |
|---|---|---|---|---|---|---|---|
| 0 (k0 7894)   | 190 | 13978 | 8084 | 46804 | 111813 | 10 | 1 |
| 1 (k1 DIRECT) | 200 | 11508 | 6531 | 38264 | 89919  | 8  | 5 |
| 2 (k2 7896)   | 180 | 12149 | 8593 | 35488 | 90015  | 7  | 2 |
| 3 (k3 DIRECT) | 206 | 11909 | 6827 | 46070 | 89033  | 12 | 4 |
| 4 (k4 DIRECT) | 188 | 11666 | 7582 | 35304 | 86967  | 4  | 2 |

**5key均衡(cnt 188-206, avg 11.7-14.0s, p50 6.5-8.6s), idx0略高avg但非离群** → 无清单[HM1-B]描述的"k4单独28.5s"那种清晰单点劣化.

### 1d. pair gap分布 (30min, 90对)
| pairs | avg_gap | p50_gap | min_gap | max_gap | gap<4.0 | gap<3.0 |
|---|---|---|---|---|---|---|
| 90 | 19.29s | 8.26s | 0.04s | 235.24s | 14 (15.6%) | 8 (8.9%) |

**p50_gap=8.26s >> throttle 4.0s**: throttle=4.0在当前流量下不阻塞(p50 gap是throttle的2倍). 仅15.6% pair gap<4.0受throttle影响. **throttle非吞吐瓶颈**.

## 2. CC清单三项重验 (本轮核心产出)

### 2a. [HM1-A] MIN_OUTBOUND_INTERVAL_S 18.2→9.0 — 已超额完成+再降证伪
- CC清单前提: "实测HM1吞吐=3.3req/min被18.2s全局throttle锁死(是HM2的4.5s的4倍). 降到9.0→吞吐翻倍."
- **当前实际值4.0s** (R437: HM2→HM1 5.0→4.0, commit e328b57), 已远低于清单目标9.0. 清单第1项意图(降throttle提吞吐)已超额完成.
- **throttle非瓶颈的实测证据**: 30min p50_gap=8.26s >> 4.0s throttle (p50 gap是throttle的2.06倍); 仅14/90对(15.6%)gap<4.0受throttle影响; 30min reqs/min=3.50 (非清单说的"3.3被锁死" — 实际受限于NVCF端处理时间avg14.5s, 非throttle).
- 再降4.0→更低的风险评估: 当前30min 0个429(稳定基线). 再降throttle增NVCF同IP 429风险, 而p50_gap已8.26s证明throttle非瓶颈, 再降收益<边际. 证伪再降.
- **结论**: A已超额完成(4.0<9.0)+再降证伪(throttle非瓶颈p50_gap8.26>>4.0).

### 2b. [HM1-B] k4(direct, idx3)路由劣化修复 — 勘定前提与当前数据不符证伪
- CC清单勘定: "k4 avg28.5s vs其他~25s, p95=72.9s vs~55s, max=162.9s. 同为direct的k2正常→非direct通病, 是k4本机IP被NVCF标记."
- **本轮6h实测 (见1c)**: idx3(k3 DIRECT, 注: 当前idx3=k3非清单说的k4; 当前idx4=k4 DIRECT) avg=11.9s, p95=46.1s, max=89.0s. **不存在清单描述的"k4 avg28.5s/p95=72.9s/max=162.9s"那种离群劣化**.
- 各direct key对比(6h): idx1(DIRECT) avg11.5s/p95=38.3s, idx3(DIRECT) avg11.9s/p95=46.1s, idx4(DIRECT) avg11.7s/p95=35.3s — 三个direct key差距<1s avg, 无单key被NVCF标记的迹象.
- 全5key均衡(见1c), idx0(7894 proxy) avg14.0s略高但不离群(差距+2.5s vs最低).
- **结论**: B勘定前提(k4单独劣化avg28.5s)在当前数据不存在, 各key均衡, 无可改的路由. 证伪. (可能清单勘定时是旧deepseek_hm_nv tier的数据, 该tier已于R438前迁移灭绝, 见R438记录"24h内41次NVCFPexecTimeout全在deepseek_hm_nv, 已于20:02迁移".)

### 2c. [HM1-C] all_tiers_exhausted早fail — 降BUDGET误杀慢成功证伪
- CC清单原文: "前3个key全NVCFPexecTimeout即fast-fail(不试k4/k5), 省~50s/次. 风险: 误杀k4/k5救回."
- **失败机制(6h窗口 14:23~20:23 UTC, 见1b+采集)**:
  - 6h 8次ATE, avg 106.8s, min 95.6s, max 121.9s (BUDGET=125)
  - tier_attempts: 12次NVCFPexecTimeout, avg 45.7s, max 46.9s (≈UPSTREAM_TIMEOUT=45s, 即每次pexec hang满45s才timeout)
  - ATE avg 106.8s ≈ 2×45.7s = 2次pexec timeout (45s + ~17s, 第2次受BUDGET剩余~17s限制... 实际min 95.6s≈2×45+5.6)
  - FASTBREAK=5形同虚设(BUDGET=125够~2.5次timeout, 到不了第5次)
- **降BUDGET的误杀评估(6h成功请求耗时分布, 975个成功)**:
  | 区间 | <60s | 60-100s | 100-125s | ≥125s | max |
  |---|---|---|---|---|---|
  | 个数 | 953 | 20 | 2 | 0 | 121860ms(失败) |
  - 成功max=121860ms(这是ATE失败, 非成功). 成功请求最高~111813ms(idx0 max).
  - 降到100s: 误杀2个成功(100-125s区间) = 0.21% 误杀率
  - 降到60s: 误杀22个成功(20个60-100s + 2个100-125s) = 2.26% 误杀率
  - **评判稳定>越快>成功率**: 降BUDGET误杀慢成功违反稳定优先+成功率优先. 证伪降BUDGET.
- **源码早fail(前3key全timeout即break)的风险**: 6h仅8次ATE(频率低1.3%/h), 而成功请求有22个>60s — 早fail逻辑若基于"前N次timeout"判定, 难以区分"NVCF pexec hang"与"正常慢请求"(两者都表现为单次attempt耗时长). 误杀风险高于收益. 且清单明确"此条需改源码, 比env风险高, 排在A/B后". A/B已证伪, C亦证伪.
- **结论**: C降BUDGET误杀慢成功(22个>60s/6h); 源码早fail误杀风险高且ATE频率低. 证伪.

## 3. 决策: ⏸️ NOP · 零配置变更

### 3a. 为什么NOP
1. **CC清单三项全部做完或证伪**: A已超额完成(4.0<9.0)+再降证伪(throttle非瓶颈p50_gap8.26>>4.0); B勘定前提与当前数据不符(无k4单独avg28.5s劣化, 各key均衡)证伪; C降BUDGET误杀22个慢成功证伪. 满足"不允许无操作轮"的例外条件(三项证伪均给出具体数据).
2. **30min 97.14%成功(102/105), 0 429**: 系统清洁(3次ATE是NVCF server-side pexec hang, 6h 8次, 频率1.3%/h, 不可proxy层修复).
3. **HM1自R438后无任何变更**: 容器StartedAt=2026-06-30T12:09:03Z(R438重启后未变), env全一致, 数据模式相同.
4. **全active参数已到天花板**:
   - MIN_OUTBOUND=4.0 (throttle非瓶颈p50_gap8.26s>>4.0, 再降增429风险)
   - BUDGET=125 (降误杀慢成功, 6h 22个成功>60s)
   - UPSTREAM=45 (6h 12次NVCFPexecTimeout avg45.7s, 但成功请求也有慢的, 降误杀)
   - KEY_COOLDOWN=25 (R438刚降, 全键均衡无冷启动)
   - FASTBREAK=5 (死参数, BUDGET先到, 降无收益)
5. **HM1失败(ATE)是NVCF server-side pexec hang, 不可proxy层修复** (R438已确认deepseek_hm_nv tier灭绝后dsv4p_nv仍偶发, 6h 8 ATE全NVCFPexecTimeout avg45.7s≈UPSTREAM=45).

### 3b. 为什么不动任何参数
| 参数 | 当前值 | 为什么不动 |
|---|---|---|
| MIN_OUTBOUND_INTERVAL_S | 4.0 | throttle非瓶颈(p50_gap8.26s>>4.0), 再降增429风险(当前0 429是稳定基线) |
| TIER_TIMEOUT_BUDGET_S | 125 | 降BUDGET误杀慢成功(6h 22个成功>60s, 2个>100s) |
| UPSTREAM_TIMEOUT | 45 | NVCFPexecTimeout avg45.7s≈45, 但成功请求也有慢的, 降误杀 |
| KEY_COOLDOWN_S | 25 | R438刚降, 全键均衡无冷启动触发 |
| TIER_COOLDOWN_S | 38 | single-tier dsv4p_nv, 边际 |
| HM_PEXEC_TIMEOUT_FASTBREAK | 5 | 死参数(BUDGET先到), 降无收益 |
| HM_CONNECT_RESERVE_S | 10 | 未观察到connect阶段瓶颈 |
| HM_SSLEOF_RETRY_DELAY_S | 2.0 | 未观察到SSLEOF聚集 |

## 4. 参数表 (本轮后HM1状态, 无变更)

| 参数 | 值 | 来源 |
|---|---|---|
| MIN_OUTBOUND_INTERVAL_S | 4.0 | R437 (HM2→HM1, 5.0→4.0) |
| TIER_TIMEOUT_BUDGET_S | 125 | (未动) |
| UPSTREAM_TIMEOUT | 45 | (未动) |
| KEY_COOLDOWN_S | 25 | R438 (HM2→HM1, 38→25) |
| TIER_COOLDOWN_S | 38 | (未动) |
| HM_CONNECT_RESERVE_S | 10 | (未动) |
| HM_PEXEC_TIMEOUT_FASTBREAK | 5 | (未动) |
| HM_SSLEOF_RETRY_DELAY_S | 2.0 | (未动) |

## 5. 结论

1. **CC清单三项全部做完或证伪**: [HM1-A]已超额完成(4.0<目标9.0)+throttle非瓶颈(p50_gap8.26>>4.0)再降证伪; [HM1-B]勘定前提(k4单独avg28.5s)与当前6h数据不符(各key均衡avg11.7-14.0s)证伪; [HM1-C]降BUDGET误杀22个慢成功(>60s/6h)证伪. 满足NOP例外条件, 每项均给具体数据.
2. **数据支撑**: 30min 102/105=97.14%成功, 0 429; 6h 975/983=99.19%(8 ATE全NVCFPexecTimeout avg45.7s).
3. **HM1自R438后零变更**: StartedAt=12:09:03Z未变, env全一致, 数据模式相同 — 无新瓶颈/新劣化/新错误类型涌现.
4. **全参数天花板**: 8个active参数逐一评估, 均无零误杀纯收益的改动空间.
5. **失败机制根因**: ATE=2×NVCFPexecTimeout(45s+~17s), avg 106.8s, 是NVCF平台pexec hang, 不可proxy层修复; FASTBREAK=5死参数(BUDGET先到).
6. **稳定优先**: 30min 97.14%+0 429基线保持, 不为边际提速破坏稳定.

## 6. 待办 (留给下轮HM1→HM2)
- [ ] HM1→HM2: HM2侧参数天花板复查(MIN_OUTBOUND=2.5, BUDGET=85, KEY_COOLDOWN=38), 若有新错误类型回传.
- [ ] 双机共性: FASTBREAK=5死参数现象 — 若CC勘定"早检测NVCF pexec hang"源码改动可立项(需先评估>45s成功的误杀).
- [ ] NVCF server-side PexecTimeout 持续追踪 — 不可proxy层修复, 监控趋势.
- [ ] empty200 (HM1 14/975=1.4%/6h) — 非系统性, 监控是否聚集, 若聚集再立项. 不在本轮CC清单.
- [ ] HM1 idx0(7894 proxy) avg略高(14.0s vs 11.5-12.1s) — 差距小+2.5s, 非离群, 监控是否恶化.

## ⏳ 轮到HM1优化HM2
