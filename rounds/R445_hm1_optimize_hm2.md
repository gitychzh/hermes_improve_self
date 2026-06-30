# R445: HM1→HM2 — ⏸️ NOP · CC清单[HM2-A/B/C]三项重验全部做完/证伪 · 21:00并发surge致86.8%下降(NVCF server-side pexec hang) · 失败=2×NVCFPexecTimeout+BUDGET break(timeout=2 elapsed~77s remaining~7.4s<10s) · 3rd-attempt救援需BUDGET跳变85→~115(违稳定优先+R334→R385降势)证伪 · 5key surge期间全成功(ok 26-31 avg10-17s)失败跨key非单key劣化 · R443(UPSTREAM 50→48)A/B两侧100%未致下降 · 0 429 · 铁律:只改HM2不改HM1 · 零配置变更

**角色**: HM1 (执行者, opc_uname) → HM2 (目标, opc2sname, glm5.1_hm_nv)
**日期**: 2026-06-30 22:12 CST (DB ts口径, host_machine='opc2sname')
**铁律**: 只改HM2不改HM1 ✓
**前轮**: R444 (HM2→HM1, ⏸️ NOP, CC清单[HM1-A/B/C]三项证伪)
**本轮**: 数据采集+CC清单[HM2-A/B/C]三项重验+21:00下降根因分析 → 判定NOP (三项全部已做完或被当前数据证伪, 下降根因为NVCF server-side不可proxy层修复)

## 0. 任务规则与本轮决策依据

任务规则: "优先执行清单第1项, 若第1项本轮无法实施(如已被前轮做过/数据不支撑), 顺延下一项。每轮只做1项。"
任务规则: "不允许'无操作'轮, 除非三项都已做完或数据证伪(证伪需给出具体数据)。"

本轮按规则逐一重验CC清单[HM2-A/B/C]三项, 结论: **A已做完(2.5)+throttle非瓶颈再降证伪 / B 5key均衡(surge期间全成功)无劣化key证伪 / C已是85+降则误杀慢成功证伪**, 满足NOP例外条件。

**与R441的差异**: R441判定NOP时30min=100%零ATE(健康期)。本轮采集窗口恰逢21:00-22:00并发surge致下降(86.8%), 故本轮额外做: (1)下降根因分析(是否R443 UPSTREAM 50→48引入? 答:否, R443 A/B两侧100%, 14:00-20:00小时97-99.5%健康, 下降是21:00 NVCF server-side瞬时pexec hang); (2)3rd-attempt救援可行性评估(是否可改env救回? 答:需BUDGET跳变85→~115, 违稳定优先+R334→R385降势, 证伪)。

注: R444末尾标记"⏳ 轮到HM1优化HM2", 本轮接手HM1→HM2, 无抢跑。

## 1. 改前数据采集 (锚点 max_ts=2026-06-30 22:11:46+00, HM2 host_machine='opc2sname')

### 1a. 容器运行态env (docker exec → 全env验证)
```
MIN_OUTBOUND_INTERVAL_S  = 2.5   (R386: HM1→HM2 5.0→2.5, CC HM2-A 已完成)
TIER_TIMEOUT_BUDGET_S   = 85    (R385: 95→85, CC HM2-C 已降到85, 远低于清单目标100)
UPSTREAM_TIMEOUT        = 48    (R443: HM1→HM2 50→48 -2s)
HM_CONNECT_RESERVE_S    = 8     (R431: HM1→HM2 10→8)
HM_SSLEOF_RETRY_DELAY_S = 1.0   (R321: HM1→HM2 3.0→1.0)
HM_PEXEC_TIMEOUT_FASTBREAK = 5  (R384: HM1→HM2 3→5; R441判死参数, BUDGET先到)
KEY_COOLDOWN_S          = 38    (R275)
TIER_COOLDOWN_S         = 22    (R1)
HM_SSLEOF_RETRY_ENABLED = true
```
Routing: k1(idx0)→DIRECT, k2(idx1)→7895, k3(idx2)→DIRECT, k4(idx3)→7897, k5(idx4)→DIRECT
容器StartedAt=2026-06-30T13:48:28.742Z (R443重启后), /health=200 ok, hm_num_keys=5, glm5.1_hm_nv ✓

### 1b. live compose vs 容器运行态 双处核对 (R322教训#1: 必须双处同步)
```
[容器 docker exec env]              [live compose /opt/cc-infra/docker-compose.yml]
UPSTREAM_TIMEOUT=48                 UPSTREAM_TIMEOUT: "48"          # R284/R443
TIER_TIMEOUT_BUDGET_S=85            TIER_TIMEOUT_BUDGET_S: "85"     # R385
MIN_OUTBOUND_INTERVAL_S=2.5         MIN_OUTBOUND_INTERVAL_S: "2.5"  # R386
HM_CONNECT_RESERVE_S=8              HM_CONNECT_RESERVE_S: "8"       # R431
KEY_COOLDOWN_S=38                   KEY_COOLDOWN_S: "38"            # R275
TIER_COOLDOWN_S=22                  TIER_COOLDOWN_S: "22"           # R1
HM_PEXEC_TIMEOUT_FASTBREAK=5         HM_PEXEC_TIMEOUT_FASTBREAK: "5" # R384
HM_SSLEOF_RETRY_DELAY_S=1.0         HM_SSLEOF_RETRY_DELAY_S: "1.0" # R321
```
**8项active env双处零漂移** ✓ (live compose不在git仓库, R322教训#2: 本次未改compose, 无需入git)

### 1c. 30min窗口成功率 (21:41:46~22:11:46 UTC, ts口径 max(ts)-30min, 恰逢surge尾部)
| total | success | empty200 | 429 | ATE | 5xx | 成功率 | reqs/min | avg_ms | p50 | p95 |
|---|---|---|---|---|---|---|---|---|---|---|
| 61 | 49 | 0 | 0 | 11 | 11 | 80.33% | 2.03 | 29644 | 17412 | 77699 |

30min窗口11个ATE(avg~78s, 全NVCFPexecTimeout×2+BUDGET break)。0 429, 0 empty200。

### 1d. post-R443小时级成功率 (14:00~22:00 UTC, 看下降是否R443引入)
| hr | total | ok | fail | succ | ate_avg |
|---|---|---|---|---|---|
| 14 | 268 | 267 | 1 | 99.6 | 15678 |
| 15 | 220 | 212 | 8 | 96.4 | 90914 |
| 16 | 252 | 249 | 3 | 98.8 | 52525 |
| 17 | 245 | 238 | 7 | 97.1 | 95177 |
| 18 | 244 | 239 | 5 | 98.0 | 92928 |
| 19 | 308 | 306 | 2 | 99.4 | 78863 |
| 20 | 194 | 193 | 1 | 99.5 | 77847 |
| 21 | 167 | 145 | 22 | 86.8 | 78519 |

**R443(13:48重启UPSTREAM 50→48)后14:00-20:00小时97.4-99.6%健康**, 仅21:00骤降到86.8%(22 ATE)。→ 下降非R443引入, 是21:00 NVCF server-side瞬时问题。

### 1e. R443 A/B (UPSTREAM 50→48, 13:18-13:48 vs 13:48-14:18, 重启前后30min)
| label | total | ok | fail | succ |
|---|---|---|---|---|
| before(50) | 126 | 126 | 0 | 100.0 |
| after(48) | 118 | 118 | 0 | 100.0 |

**R443 A/B两侧100%零失败** → R443未引入下降, R443的"省4s/失败"理由虽弱(失败在77s BUDGET break而非96s), 但无负面影响。

### 1f. 21h surge 5-min slot下降profile (21:00-22:00)
| slot | t | ok | f | | slot | t | ok | f |
|---|---|---|---|---|---|---|---|---|
| 21:00 | 15 | 15 | 0 | | 21:30 | 5 | 1 | 4 |
| 21:05 | 53 | 52 | 1 | | 21:35 | 12 | 11 | 1 |
| 21:10 | 8 | 5 | 3 | | 21:40 | 10 | 8 | 2 |
| 21:15 | 10 | 8 | 2 | | 21:45 | 7 | 5 | 2 |
| 21:20 | 23 | 23 | 0 | | 21:50 | 4 | 0 | 4 |
| 21:25 | 11 | 9 | 2 | | 21:55 | 9 | 8 | 1 |

21:05流量surge(53req/5min vs正常10-15), 失败从21:10起攀升, 21:30/21:50最差(4/5失败)。surge触发NVCF concurrent pexec hang。

### 1g. 21h surge期间per-key成功 (status=200, 验证keys是否全挂)
| nv_key_idx | ok | ok_avg | ok_p95 |
|---|---|---|---|
| 0 (k1 DIRECT) | 31 | 17363 | 45898 |
| 1 (k2 7895)   | 26 | 15214 | 46393 |
| 2 (k3 DIRECT) | 31 | 11681 | 30416 |
| 3 (k4 7897)   | 26 | 10199 | 20929 |
| 4 (k5 DIRECT) | 31 | 13211 | 46210 |
| (NULL ATE)    | 0  | —     | — |

**surge期间5key全成功(ok 26-31, avg 10-17s)**, 失败22个全ATE(key_idx=NULL, 2×timeout后BUDGET break, 未记录到最终请求行)。→ 非全key挂死, 是每失败请求恰好2个key连续pexec hang, 第3key未及尝试(budget break)。跨key随机, 非单key劣化。

### 1h. 失败log模式 (docker logs --since 8m, 实时)
```
[22:05:02.3] [HM-TIER-BUDGET] tier=glm5.1_hm_nv budget 85.0s remaining 7.4s < 10s minimum, breaking
[22:05:02.3] [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=0, empty200=0, timeout=2, other=0, elapsed=77603ms
[22:09:30.1] [HM-TIER-BUDGET] ... remaining 7.3s < 10s minimum, breaking
[22:09:30.1] [HM-TIER-FAIL] ... timeout=2, other=0, elapsed=77717ms
```
**失败=2×NVCFPexecTimeout(各~48-50s)+BUDGET break**: k1 timeout~50s(48 read+2 overhead), remaining~35s, k2 per_attempt=min(48,35-8=27)=27s→timeout~29s, total~77s, remaining~7.4s<10s MIN_ATTEMPT_TIMEOUT→break, 第3key未试。0 429, 0 empty200, 0 other。

### 1i. throttle check (30min latest, pair gap)
| pairs | p50_gap | lt_throttle(<2.5s) |
|---|---|---|
| 61 | 14s | 3 (4.9%) |

p50_gap=14s >> throttle 2.5s → throttle非瓶颈(仅4.9% pair受cap, 且受surge低流量放大gap影响)。

## 2. CC清单三项重验 (本轮核心产出)

### 2a. [HM2-A] MIN_OUTBOUND_INTERVAL_S 4.5→2.5 — 已做完+再降证伪
- CC清单目标值2.5: **当前已是2.5**(R386 commit 3441e5e已完成). 清单第1项意图(降throttle提升吞吐)已收官.
- 30min pair gap: p50_gap=14s >> throttle 2.5s, 仅4.9% pair受throttle cap. **再降2.5→更低: p50_gap由上游响应时间主导(14s), 降throttle不改p50_gap; 收益边际, 增NVCF同IP 429风险(当前零429是稳定基线).**
- **结论**: A已做完(2.5)+再降证伪(throttle非瓶颈p50_gap=14s>>2.5).

### 2b. [HM2-B] HM2失败模式数据补采 — 证伪(无劣化key, ATE跨key随机)
- 本轮重采21h surge期间per-key数据(见1g): 5key全成功(ok 26-31, avg 10-17s, p95 21-46s), 无单key劣化.
- 22个ATE失败全key_idx=NULL(2×timeout后BUDGET break, 未记录最终key), 跨key随机非单key聚集. tier_attempts 60min仅3行(idx0×1, idx4×2 NVCFPexecTimeout avg49.5s), 跨2个key, 非单key标记.
- **与HM1-k4对比**: HM1清单[HM1-B]勘定前提是"k4单独avg28.5s劣化". HM2无此模式, 5key完全均衡.
- **结论**: B证伪 — 5key均衡无劣化key, ATE是NVCF server-side pexec hang跨key随机, 非某key本机IP被标记. 无可改的路由.

### 2c. [HM2-C] TIER_TIMEOUT_BUDGET_S 128→100 / all_tiers_exhausted早fail — 证伪(已是85+降误杀慢成功+3rd-attempt救援需违稳定优先的BUDGET跳变)
CC清单原文"128→100", 实际HM2 BUDGET已从128→100(R334)→95(R384)→85(R385), 远低于清单的100. 本轮评估两个方向:

**方向1: 再降85→更低(清��意图"降BUDGET让失败早结束")的误杀评估**
- post-R443(13:48+)成功>60s: 2个, >48s: 5个, >78s: 0个(6h口径).
- 降到60s: 误杀2个成功(>60s); 降到78s: 误杀0个但失败仍~77s(无省时). 评判稳定>越快>成功率, 误杀慢成功违反稳定优先. 证伪降BUDGET.

**方向2: 提BUDGET以解锁3rd-attempt救援(本轮新增, 因surge下降22 ATE)**
- surge期间5key全成功(avg10-17s), 但失败请求2×timeout后BUDGET break未试第3key → 若第3key能试, 有救回可能(其他key同期成功).
- **预算数学**: k1 timeout~50s + k2 timeout~29s = ~79s elapsed, remaining~6s < MIN_ATTEMPT_TIMEOUT=10(hardcoded upstream.py:236) → break. 要让第3key获得有意义read window(≥20s): 需remaining≥28s at 3rd start → **BUDGET ≥ 79+28+8 = ~115s**.
- 当前BUDGET=85, 提到~115是+30s大跳变, 违R334(128→100)→R385(95→85)的降势, 且失败ATE从~78s拉长到~115s+(违稳定优先"稳定>越快").
- **历史救援数据**: 18个rescue(2×timeout后第3key成功) avg109s(84-122s), 最新=2026-06-30 15:42:17(BUDGET=85期). 说明BUDGET=85时偶有救援(边界case, k1+k2 elapsed稍<79s时remaining≥10), 但surge期2×满timeout后remaining~6s, 救援不触发.
- 提BUDGET到~115虽可能增救援, 但: (a)大跳变违"少改多轮"; (b)失败拉长违稳定优先; (c)surge期NVCF多key并发hang时第3key也大概率hang(非确定性救回); (d)R372/R367在BUDGET=100/105时24h救援仅18个且失败ate_avg~116-122s, 净收益不明确.
- **结论**: C证伪 — 已是85, 降误杀慢成功; 提BUDGET救3rd-attempt需~115大跳变违稳定优先+少改多轮+降势, 且救援非确定性. 不做.

**源码早fail(前3key全timeout即break)的风险(清单C备选)**: 6h ATE仅22个(频率3.8%/h), 但surge期失败=2×timeout(非3+), fast-fail-at-3条件不触发(已2次就BUDGET break). FASTBREAK=5死参数(BUDGET先到). 改源码降MIN_ATTEMPT_TIMEOUT 10→6: 第3key per_attempt=max(6,min(48,6-8=负))=6s, 但post_connect_remaining<6→abort, 第3key仍读不到. 无效. 证伪.

## 3. 变更决策: NOP (零配置变更)

三项重验均证伪/已做完, 满足任务规则"三项都已做完或数据证伪"的NOP例外条件. 本轮额外分析21:00下降根因(R443未引入, NVCF server-side surge)与3rd-attempt救援可行性(需违稳定优先的BUDGET大跳变, 证伪), 无可做的单参数改动.

### 3a. 为什么NOP
1. **CC清单三项全部做完或证伪**: A已做完(2.5)+throttle非瓶颈(p50_gap=14s>>2.5)再降证伪; B 5key均衡(surge全成功ok26-31)无劣化key+ATE跨key随机证伪; C已是85+降误杀慢成功+提BUDGET救3rd需~115大跳变违稳定优先证伪. 满足NOP例外条件.
2. **21:00下降根因非HM2配置**: R443 A/B两侧100%(1e), 14:00-20:00小时97.4-99.6%健康(1d), 下降仅21:00 surge时段(53req/5min触发NVCF concurrent pexec hang).
3. **失败是NVCF server-side pexec hang**: timeout=2, elapsed~77s, remaining~7.4s<10s break, 0 429/0 empty200/0 other. 2个key连续hang后BUDGET break, 第3key未及试. 不可proxy层修复(R434/R435/R441反复确认).
4. **全active参数已到天花板**: 8项env双处零漂移(1b), 逐一评估无零误杀纯收益改动.
5. **HM2自R443(13:48重启)后仅UPSTREAM 50→48变更**: 该变更A/B两侧100%无负面影响, 14:00-20:00健康.

### 3b. 铁律遵守
- ✅ 只改HM2不改HM1: 本轮零配置变更, 仅数据采集, 未触碰HM1本地.
- ✅ 未停止/重启/kill mihomo服务.
- ✅ 未改源码(清单三项均证伪, MIN_ATTEMPT_TIMEOUT改无效).
- ✅ live compose双处核对零漂移(1b).

### 3c. 局限承认
- 21:00下降22 ATE是NVCF server-side concurrent pexec hang, proxy层无法消除(2×timeout后BUDGET break, 第3key未及试).
- 3rd-attempt救援路径需BUDGET~115大跳变, 违稳定优先+少改多轮, 本轮不做但留给反对者评估(见§4).
- hm_tier_attempts表记录不全(22 ATE仅3行tier_attempts), 因budget-break前部分attempt未落表, 但docker logs的HM-TIER-FAIL timeout=2已证失败结构.
- 30min窗口80.33%是surge尾部, 非HM2稳态; 14:00-20:00稳态97.4-99.6%.

## 4. 反对者(下轮HM2→HM1)提示

- **若下轮认为NOP判定有误**, 请给出**具体数据**反驳:
  - (a) 若认为应提BUDGET救3rd-attempt: 请给出surge期第3key能救回的确定性证据(当前数据: surge期5key全成功avg10-17s, 但失败请求2×timeout后remaining~6s<10s MIN, 且提BUDGET到~115才解锁有意义read window, 失败拉长到~115s违稳定优先). 需论证救援率>失败拉长成本.
  - (b) 若认为应降BUDGET/UPSTREAM/RESERVE: 请给出零误杀证据(当前>60s成功2个, >48s成功5个, 降则误杀).
  - (c) 若认为21:00下降是HM2配置引入: 请对比R443 A/B(两侧100%)与14:00-20:00小时数据(97.4-99.6%)反驳.
- **3rd-attempt救援开放问题(留评估)**: 历史18个rescue avg109s(84-122s), BUDGET=85期最新rescue=15:42. 若CC勘定"提BUDGET 85→115救3rd-attempt"为清单外改动点, 需先A/B评估: surge期失败率vs失败拉长成本. 本轮数据不足以支持(救援非确定性, surge期多key并发hang).
- HM1侧(R444后零变更, StartedAt=13:16Z): 若HM1有新错误类型回传.

## 5. 参数表 (本轮后HM2状态, 无变更)

| 参数 | 值 | 来源 |
|---|---|---|
| MIN_OUTBOUND_INTERVAL_S | 2.5 | R386 (HM1→HM2, 5.0→2.5, CC HM2-A 已完成) |
| TIER_TIMEOUT_BUDGET_S | 85 | R385 (95→85, CC HM2-C 已降到85) |
| UPSTREAM_TIMEOUT | 48 | R443 (HM1→HM2, 50→48) |
| HM_CONNECT_RESERVE_S | 8 | R431 (HM1→HM2, 10→8) |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | R321 (HM1→HM2, 3.0→1.0) |
| HM_PEXEC_TIMEOUT_FASTBREAK | 5 | R384 (3→5; 死参数, BUDGET先到) |
| KEY_COOLDOWN_S | 38 | R275 |
| TIER_COOLDOWN_S | 22 | R1 |

## 6. 结论

1. **CC清单三项全部做完或证伪**: [HM2-A]已是2.5+throttle非瓶颈(p50_gap=14s>>2.5, 仅4.9%pair受影响)再降证伪; [HM2-B]5key均衡(surge期间全成功ok26-31 avg10-17s)无劣化key+ATE跨key随机证伪; [HM2-C]已是85+降误杀慢成功(>60s成功2个)+提BUDGET救3rd需~115大跳变违稳定优先证伪. 满足NOP例外条件, 每项均给具体数据.
2. **21:00下降根因**: NVCF server-side concurrent pexec hang(surge 53req/5min触发), 非R443引入(R443 A/B两侧100%, 14:00-20:00小时97.4-99.6%), 非HM2配置问题. 失败=2×NVCFPexecTimeout+BUDGET break(timeout=2 elapsed~77s remaining~7.4s<10s), 0 429/0 empty200.
3. **3rd-attempt救援评估**: surge期间5key全成功但失败请求2×timeout后BUDGET break未试第3key. 提BUDGET 85→~115可解锁有意义read window, 但违稳定优先+少改多轮+R334→R385降势, 且救援非确定性(surge期多key并发hang), 证伪.
4. **HM2自R443(13:48)后仅UPSTREAM 50→48变更**: A/B两侧100%, 14:00-20:00健康, 21:00下降是NVCF瞬时.
5. **全参数天花板**: 8项active env双处零漂移, 逐一评估无零误杀纯收益改动.
6. **稳定优先**: 不为surge期边际救援破坏稳定(提BUDGET拉长失败到~115s违稳定优先).

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记
