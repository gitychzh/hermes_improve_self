# R323: HM1→HM2 — ⏸️ 无操作: CC清单HM2-A/B/C三项经当前数据全部证伪 + 主动候选全证伪

**角色**: HM1(执行者, opc_uname) → HM2(目标, opc2sname)
**日期**: 2026-06-30 03:08 UTC (容器/DB时区对齐, 实测HM2容器=19:08 local=03:08 UTC)
**铁律**: 只改HM2不改HM1
**前轮**: R322 (HM2→HM1, k4 DIRECT→mihomo 7897, R321 SSLEOF backoff 1.0已生效)
**本轮基线锚点**: max(ts)=2026-06-30 03:03:52 UTC (HM2 DB, host_machine='opc2sname', R317 §0 max(ts)口径, 规避DB now()时区错位)

> **§6注 (CC托底补充, 2026-06-30 03:11 UTC)**: 本轮HM1 session跑期间, HM2的R322孤儿session(commit后未退出)抢跑了一个错误标注为"R323"的commit f772db5, 把HM1 TIER_TIMEOUT_BUDGET_S 90→100部署生效(compose+env=100, healthy). 改动本身合理(预算公式 BUDGET≥2×UPSTREAM+5=95, 90<95违反→100≥95修复, 升BUDGET不误杀), 不回调. 该错误commit写到了rounds/RN_hm2_optimize_hm1.md模板(watch已用grep -v RN_排除,不影响触发), 方向标反(HM2→HM1), 翻轮标记没翻. CC已kill HM2孤儿session(见记忆r323-cross-host-collision). 下轮HM2读本R323_hm1文件为准, BUDGET=100是既成事实.

## 0. 任务规则与本轮决策依据

任务规则: "优先执行清单第1项, 若第1项本轮无法实施(如已被前轮做过/数据不支撑), 顺延下一项。每轮只做1项, A/B验证后翻轮。" + "不允许无操作轮除非三项都已做完或数据证伪(证伪需给出具体数据)"。

本轮对CC定向清单HM2侧三项(A/B/C)逐一用**当前30-180min窗口实测数据**复核, 三项均**数据证伪不可改**。同时主动挖掘的3个单参数候选(UPSTREAM_TIMEOUT↓/CONNECT_RESERVE↑或↓/fast-fail早停)也逐个数据证伪。证伪数据见§2。**无���全可改项**, 按"三项全做完或数据证伪"例外执行无操作轮。

## 1. 改前数据采集 (锚点 max_ts=2026-06-30 03:03:52 UTC)

### 1a. 多窗口成功率
| 窗口 | total | success | fail | 成功率 |
|---|---|---|---|---|
| 15min | 54 | 52 | 2 | 96.30% |
| 30min | 104 | 101 | 3 | 97.12% |
| 60min | 144 | 134 | 10 | 93.06% |
| 120min | (per-key总) | — | — | — |

### 1b. 30min错误结构
| error_type | n | avg_dur | p50 | p95 | max_dur |
|---|---|---|---|---|---|
| (success) | 101 | 12812 | 9003 | 33165 | 89037 |
| all_tiers_exhausted | 3 | 122032 | 122001 | 122217 | 122241 |

**关键**: 所有失败都是 `all_tiers_exhausted`, 无429/empty200/SSL。失败请求avg 122s = BUDGET 128s 减去 overhead, 耗满预算。

### 1c. 6h稳定基线 (2026-06-29 21:03:52 ~ 03:03:52 UTC)
| 指标 | 值 |
|---|---|
| 总请求(6h) | 881 |
| 429 | **0** |
| empty200 | **0** |
| SSLEOF触发(6h docker logs) | **0** (R321 SSLEOF代码就绪, 频率1.2/h未自然触发, 6h期望7次但实际0次) |

**6h零限流是宝贵稳定状态**, 任何增NVCF同IP压力的改动违背"稳定优先"。

### 1d. 60min per-key成功延迟 (排查HM2-B劣化key)
| nv_key_idx | 键名(proxy) | n | avg_dur | p50 | p95 | max_dur |
|---|---|---|---|---|---|---|
| 0 | k1 (7894) | 28 | 18858 | 12424 | 61037 | 117077 |
| 1 | k2 (DIRECT) | 26 | 20023 | 11558 | 67129 | 105949 |
| 2 | k3 (DIRECT) | 28 | 14952 | 7704 | 50820 | 89037 |
| 3 | k4 (DIRECT) | 28 | 20184 | 9576 | 78487 | 109740 |
| 4 | k5 (7899) | 25 | 17735 | 9567 | 70025 | 119957 |

120min窗口更稳定: n均匀(49-56), p95范围50554(k2)~71831(k4)。**无像HM1-k4(p95=72.9s远超其他~55s)那样的劣化key**, 5key分布正常。

### 1e. 60min per-key超时分布 (hm_tier_attempts, NVCFPexecTimeout)
| nv_key_idx | tmo_n | avg_elapsed | max_elapsed |
|---|---|---|---|
| 0 | 2 | 50345 | 50358 |
| 1 | 4 | 52503 | 55038 |
| 2 | 5 | 50642 | 50743 |
| 3 | 3 | 37234 | 50654 |
| 4 | 4 | 41278 | 52608 |

超时散布全5key(2-5次), **无单key超时集中** (对比HM1-k4曾6/16=37.5%集中)。超时是NVCF平台层hang, 非key/路由问题。

### 1f. 改前env (docker exec hm40006 env, 本轮未改)
| 参数 | HM2值 | HM1值(对比) |
|---|---|---|
| TIER_TIMEOUT_BUDGET_S | 128 | 90→100 (见§6注) |
| UPSTREAM_TIMEOUT | 50 | 45 |
| MIN_OUTBOUND_INTERVAL_S | 4.5 | 9.0 |
| KEY_COOLDOWN_S | 38 | 38 |
| TIER_COOLDOWN_S | 22 | 38 |
| HM_CONNECT_RESERVE_S | 21 | 24 |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 (R321生效) | 3.0 |
| HM_NV_PROXY_URL1~5 | 7894/空/空/空/7899 | — |

## 2. CC清单三项 + 主动候选 — 逐个数据证伪

### [HM2-A] MIN_OUTBOUND_INTERVAL_S 4.5→2.5 — ❌ 数据证伪 (机制不成立 + 净风险)
**CC命题**: "降到2.5→吞吐+80%。风险: NVCF同IP 429"
**本轮数据证伪**:
1. **吞吐非throttle瓶颈**: 60min=144reqs→2.4req/min; 4.5s throttle理论上限=60/4.5=**13.3req/min**。实测2.4远低于上限(5.5倍余量)→吞吐受**客户端到达率**限制, 非throttle。降4.5→2.5不提吞吐。
2. **burst vs normal对比 (180min稳定窗口, gap阈值4.5s)**:
   | arrival | n | succ | succ_pct |
   |---|---|---|---|
   | burst(<4.5s) | 70 | 66 | **94.29%** |
   | normal(>=4.5s) | 424 | 405 | **95.52%** |
   burst与normal成功率仅差1.2pp(60min窗口n=13时差11pp是小样本假象, 180min n=70稳定后收敛)→**throttle 4.5s在burst时无可观测同IP惩罚**, 降值不改善成功率。
3. **6h=0个429是宝贵状态**: 降throttle增NVCF同IP压力(虽180min无可观测惩罚但6h零限流是稳定基线, 增压力无收益增风险), 破坏零限流基线。净风险无收益。
4. **代码逻辑确认** (R321已查): `throttle_outbound()` 仅在 `attempt_idx==0`(每请求首次出站)触发, 全局串行锁; 重试attempt不过throttle。throttle按"请求"粒度非"attempt"粒度。
**结论**: HM2-A数据扎实证伪, 放弃。

### [HM2-B] 失败模式数据补采 + 劣化key排查 — ✅ 完成, 无劣化key无可改项
120min per-key成功: n均匀(49-56), p95范围50554~71831, 超时散布全5key(2-5次)。**无像HM1-k4那样的劣化key** (HM1-k4曾p95=72.9s远超其他~55s且超时6/16集中)。5key全正常, **无可改项**。

### [HM2-C] TIER_TIMEOUT_BUDGET 128→100 — ❌ 决定性证伪 (误杀>100s救援成功)
**CC命题**: "BUDGET=128偏大, 失败请求耗满128s。降到100→失败早结束28s。风险: 误杀100-128s慢成功"
**本轮决定性数据 (120min, 锚点03:03:52)**:
- 成功请求中 **>100s = 8个, >110s = 5个, >120s = 2个** (max=122572ms)。这些是**3次NVCFPexecTimeout后attempt 4救回**的流式成功(stream=True全量):
  | request_id | duration_ms | 超时次数(救回前) |
  |---|---|---|
  | 11ee5811 | 122572 | 3 |
  | 6c12a16f | 121567 | 3 |
  | 49b7419a | 119957 | 3 |
  | 506085e9 | 117077 | 3 |
  | 1805a2ca | 111269 | 2 |
  | 75163cc8 | 109740 | 2 |
  | 7916cb3f | 106593 | 2 |
  | 9981b0d0 | 105949 | 2 |
- **BUDGET=100误杀路径**: attempt1超时50s@50s, attempt2超时50s@100s → remaining=28→break → **attempt3/4永不试** → 8个救回成功全变502。误杀8/260=**3.1%成功率**。
- R319用6c12a16f(121.6s)决定性证伪, 本轮该请求**仍在发生**(120min内49b7419a=122572ms是同模式新案例), 证伪持续成立。
**结论**: HM2-C决定性证伪, 放弃。

### 主动候选1: UPSTREAM_TIMEOUT 50→40 (降失败请求单attempt耗时) — ❌ 证伪 (误杀45-50s慢成功)
180min窗口成功请求: **45-50s=9个, 40-45s=9个, 35-40s=9个**。降UPSTREAM_TIMEOUT=40会误杀9个45-50s慢成功。R319已证伪同向, 本轮数据再确认。放弃。

### 主动候选2: HM_CONNECT_RESERVE_S 21调整 — ❌ 证伪 (双向均无益或增风险)
代码逻辑 (upstream.py line 228-236): `per_attempt_timeout = max(MIN_ATTEMPT_TIMEOUT=10, min(UPSTREAM_TIMEOUT, remaining - CONNECT_RESERVE))`。
- **降CONNECT_RESERVE(21→10)**: per_attempt上限升高 → attempt超时**更晚**发生 → ATE耗时**增加**而非减少, 与目标相反。
- **升CONNECT_RESERVE(21→30)**: per_attempt上限降低 → attempt超时**更早** → 等效降UPSTREAM_TIMEOUT, 误杀45-50s慢成功(同主动候选1)。
- 实测connect时间(R40注释+日志attempt间隔4-6s): 2-5s, 远小于21s reserve, 但reserve仅影响read timeout上限计算, 不影响实际connect(post_connect_remaining re-check保护)。双向无净益。放弃。

### 主动候选3: 前3key全NVCFPexecTimeout早fail (HM1-C模拟) — ❌ 决定性证伪 (误杀3次超时救回)
HM2-C数据已证明: 4个成功(122572/121567/119957/117077ms)是**3次超时后attempt4救回**。前3key全timeout即fast-fail会**直接误杀这4个救回**。与HM2-C同源证伪。放弃。

## 3. 本轮无改动的合理性论证

1. **CC清单三项全证伪**: A(throttle非瓶颈+burst成功率反降), B(无劣化key), C(误杀8个>100s救回)。每项有具体数据, 非空泛。
2. **主动候选三项全证伪**: UPSTREAM_TIMEOUT↓(误杀9个45-50s), CONNECT_RESERVE双向(无益或误杀), fast-fail(误杀4个3次超时救回)。
3. **6h零429/零empty200基线**: 881请求0限流, 任何增NVCF同IP压力的改动(throttle↓)破坏稳定。
4. **R321 SSLEOF已生效**: env=1.0+代码读env, 6h未自然触发(低频1.2/h), 代码路径就绪, 无需再动。
5. **失败模式本质**: ATE全为NVCF平台层hang(timeout=4, 429=0, empty200=0, SSL=0), 非key/路由/限流问题, **非HM2可调参数能解决**——是NVCF平台本身的间歇性hang, HM2侧5key轮转+BUDGET救回已是正确响应。

**零变更=最高稳定性**, 符合"稳定优先"评判标准。HM2侧当前无安全可改的单参数点。

## 4. R321待办复核 (本轮闭环)
- [x] **SSLEOF backoff代码路径**: env=1.0 ✅, 代码line 452 `ssleof_delay=float(os.environ.get("HM_SSLEOF_RETRY_DELAY_S","3.0"))` ✅, 6h docker logs `HM-SSL-RETRY`=0次(低频未自然触发, 代码就绪待自然验证, 下轮可继续复核)
- [x] **HM2-A数据���确认**: throttle非瓶颈(2.4req/min vs 13.3上限), 本轮再证伪, 不建议试
- [x] **HM2流量评估**: 60min=144reqs=2.4req/min, 仍低流量, ATE占比波动大(15min 96.3% vs 60min 93.06%), 需高流量窗口稳定评估——但当前无高流量, 不影响证伪结论(证伪基于机制+救援数据, 非成功率波动)

## 5. 待办 (留给下轮HM2→HM1)
- [ ] 下轮HM2→HM1: R322 k4路由(DIRECT→mihomo 7897)改后效果需30min+窗口观测k4超时率是否从37.5%下降(R322改后仅15min 1请求, 数据不足)
- [ ] HM2 SSLEOF backoff若自然触发, 复核docker logs `HM-SSL-RETRY`显示"1.0s backoff"
- [ ] HM2若未来流量上升至>10req/min, 可重新评估HM2-A(throttle是否变瓶颈)
- [ ] HM2失败模式(NVCF平台hang)非HM2参数可解, 若成功率持续<95%需排查NVCF平台侧而非HM2

## ⏳ 轮到HM2优化HM1
