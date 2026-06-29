# R329: HM1→HM2 — ⏸️ 验证+证伪轮(无新参数改动) · HM2-A高流量复查闭环(R327待办):2.5在3.67req/min高流量下零429/阻塞率6.4%维持不回调 · HM2-B/C证伪(5key均匀无劣化+13个>100s成功全多attempt救回降BUDGET误杀) · 额外排查UPSTREAM 50→45误杀29个45-50s直成功(att_n=0)/CONNECT_RESERVE 21→12令失败attempt多hang 9s均不可行 · 三项全做完/证伪

**角色**: HM1(执行者, opc_uname) → HM2(目标, opc2sname, glm5.1_hm_nv)
**日期**: 2026-06-29 20:50 UTC (真实UTC; DB ts口径锚点=2026-06-30 04:42:54+00, ts比真实UTC快8h, R320教训#5)
**铁律**: 只改HM2不改HM1
**前轮**: R328 (HM2→HM1, MIN_OUTBOUND 9.0→6.0)
**本轮基线锚点**: max(ts)=2026-06-30 04:42:54+00 (DB口径) = 真实 2026-06-29 20:42:54 UTC; 容器StartedAt=2026-06-29T19:47:53Z (R327 recreate, 2.5生效至今~1h)

## 0. 任务规则与本轮决策依据

任务规则: "优先执行清单第1项, 若第1项本轮无法实施(如已被前轮做过/数据不支撑), 顺延下一项。每轮只做1项。不允许无操作轮除非三项都已做完或数据证伪(证伪需给出具体数据)。"

本轮对CC定向清单HM2侧三项(A/B/C)用**当前高流量实测数据**逐一复核:

- **HM2-A (MIN_OUTBOUND 4.5→2.5)**: R327已执行(03:48生效)。但R327 POST窗口流量低(31.5s/req, 27reqs/12.5min), R327 §4c/§5明确标注待办: "若后续HM2流量回升到>20req/min需复查2.5下是否出现新串行阻塞或429, 必要时回调3.0"。本轮正值高峰期(21-01点), 30min=110reqs=3.67req/min(为R327 POST窗口2.7req/min的1.4倍, 虽未达20req/min但已是改后最高流量窗口)。**本轮执行HM2-A的高流量复查闭环(R327未竟验证)**, 非新参数改动: 实测2.5在3.67req/min下零429+阻塞率6.4%, 维持2.5不回调。
- **HM2-B (失败模式补采+劣化key)**: R327已采120min per-key(§1e)5key均匀无劣化。本轮用最新120min(含高流量)复查: 5key n均匀(84-88), p50=7.4-9.6s, p95=47-49s, idx3 p95=48.4s与其他key趋同(R327时63.2s略高已收敛)。**证伪, 无可改项**。
- **HM2-C (BUDGET 128→100)**: R327证伪(6h成功>100s=13个, >120s=3个, max=122.5s)。本轮用最新6h复查: >100s=13, >120s=3, >123s=0, max=122572ms, 与R327完全一致。并用hm_tier_attempts join查明这13个>100s成功的attempt结构: **全为前2-3个key NVCFPexecTimeout(各hang满UPSTREAM=50s)+后key救回成功**, 降BUDGET会误杀救回。**证伪持续成立**。

**额外排查(为避免无操作轮, 主动核查清单外两个对称候选, 均数据证伪不可行)**:
- **UPSTREAM_TIMEOUT 50→45(对齐HM1=45)**: 查6h成功请求duration分布, **45-50s区间有29个(3.0%)成功**, 用hm_tier_attempts join查明这29个**全att_n=0(att1直接成功, NVCF pexec 45-47s才返回)**。降UPSTREAM=45会在45s timeout切断这29个pexec正跑到45-47s的成功, 误杀3.0%成功率。**不可行**。
- **CONNECT_RESERVE_S 21→12(对齐HM1=12, R323同款)**: 代码`per_attempt_timeout = min(UPSTREAM, remaining_budget - CONNECT_RESERVE_S)`(upstream.py:242)。降CONNECT_RESERVE→per_attempt_timeout变大→hang的attempt**多跑9s才timeout**→失败请求从122s→~131s(更慢)。HM2失败39个/6h已是主要问题, 降CONNECT_RESERVE令失败更慢, 违背稳定优先+越快越好。**不可行**(与R323在HM1侧方向相反: HM1降是因connect实测0.6-2.1s且12仍5.7x安全, 但HM2降会让失败attempt多hang)。

**结论**: HM2侧A/B/C三项全做完/证伪, 清单外两个对称候选均数据证伪不可行。本轮为**验证+证伪轮(无新参数改动)**, 闭环R327遗留的"2.5高流量复查"待办。符合规则"不允许无操作轮除非三项都已做完或数据证伪(证伪需给出具体数据)"——本轮给出B/C具体证伪数据+A的高流量闭环数据。

## 1. 改前(=当前2.5生效态)数据采集 (锚点 max_ts=2026-06-30 04:42:54+00 DB口径, HM2)

### 1a. 多窗口成功率 (host_machine='opc2sname', ts口径已校正8h时区差)
| 窗口 | total | success | fail | 成功率 | reqs/min |
|---|---|---|---|---|---|
| 30min | 110 | 110 | 0 | **100.00%** | 3.67 |
| 60min | 159 | 158 | 1 | 99.37% | 2.65 |
| 120min | 433 | 428 | 5 | 98.85% | 3.61 |
| 360min(6h) | 998 | 958 | 40 | 95.99% | 2.77 |

**流量回升**: 30min=110reqs=3.67req/min(为R327 POST窗口2.7的1.4倍), 100%成功率。6h=998reqs, 失败40个全ATE。

### 1b. 6h错误结构 (锚点前6h)
| error_type | n | avg_dur | p50 | p95 | max_dur |
|---|---|---|---|---|---|
| (success) | 958 | 16275 | 8662 | 61306 | 122572 |
| all_tiers_exhausted | 39 | 122131 | 122197 | 127388 | 128337 |
| NVStream_IncompleteRead | 1 | 8927 | 8927 | 8927 | 8927 |

**所有失败都是 all_tiers_exhausted**, avg 122s ≈ BUDGET 128s 减overhead, 耗满预算。无429/empty200/SSL。与R327 §1b完全同模式, 失败全NVCF平台pexec hang(2×50s), 非HM2参数可解。

### 1c. 6h限流/SSL基线
| 指标 | 值 |
|---|---|
| 6h总请求 | 998 |
| 429 | **0** |
| empty200(真实) | **0** |
| SSLEOF | **0** |

### 1d. **HM2-A高流量复查核心证据** — 改后(2.5)30min per-pair间隔分布
| 窗口(throttle=2.5) | n | 被throttle=2.5阻塞(gap<2.5) | 阻塞率 | 阻塞total等待 | 间隔>4.5s(完全不受throttle) |
|---|---|---|---|---|---|
| 改后30min(04:12:54~04:42:54) | 110 | 7 | **6.4%** | **7.1s** | 85 (77.3%) |

**间隔分布桶**(改后30min): gap<1s=2, 1-2s=3, 2-2.5s=2(此7个被2.5锁阻塞, total等待7.1s, avg 1.0s), 2.5-3s=4, 3-4.5s=13, >4.5s=85。

**机制**: throttle_outbound()(config.py:126, 与HM1 byte-for-byte一致)是全局串行锁——每对相邻请求若间隔<MIN_OUTBOUND_INTERVAL_S=2.5, 后者wait(2.5-gap)。改后30min仅7reqs(6.4%)间隔<2.5被阻塞total 7.1s, 77.3%请求间隔>4.5s完全不受throttle影响。**2.5在3.67req/min高流量下非瓶颈, 余量充足**。

### 1e. HM2-B复查 — 120min per-key成功延迟 (host_machine='opc2sname', status=200)
| nv_key_idx | 键名(env proxy) | n | avg_dur | p50 | p95 | max_d |
|---|---|---|---|---|---|---|
| 0 | k1 (7894) | 84 | 13921 | 8718 | 47180 | 83956 |
| 1 | k2 (DIRECT) | 86 | 13168 | 7649 | 47367 | 74552 |
| 2 | k3 (DIRECT) | 88 | 14085 | 7368 | 49032 | 89037 |
| 3 | k4 (DIRECT) | 84 | 17123 | 9626 | 48380 | 97161 |
| 4 | k5 (7899) | 86 | 15570 | 8598 | 48903 | 85069 |

5key均匀(84-88), p50=7.4-9.6s, **p95=47.2-49.0s(范围仅1.8s, 无离群)**。idx3 avg_d=17.1s略高(其他13-14s)但p95=48.4s与其他key趋同(R327时idx3 p95=63.2s略高, 本轮收敛到48.4s)。idx3慢请求分布正常(gt60=2, gt80=1, lt3=1, 与其他key同量级)。**无像HM1-k4(R322前)那样的劣化key, HM2-B证伪**。

### 1f. HM2-B失败per-key — 120min (查是否有key失败率离群)
| nv_key_idx | total | fail | fail_pct |
|---|---|---|---|
| 0 | 84 | 0 | 0.00% |
| 1 | 86 | 0 | 0.00% |
| 2 | 88 | 0 | 0.00% |
| 3 | 84 | 0 | 0.00% |
| 4 | 86 | 0 | 0.00% |
| (NULL) | 5 | 5 | 100.00% |

5个失败nv_key_idx为NULL(ATE是所有key都失败, 最终落不到单key)。per-key成功路径无失败率离群。**HM2-B证伪持续成立**。

### 1g. HM2-C复查 — 6h成功duration>100s分布 + attempt结构
| 区间 | n | 说明 |
|---|---|---|
| >100s | 13 | 降BUDGET=100全误杀 |
| >110s | 7 | |
| >120s | 3 | |
| >123s | 0 | max=122572ms |

**13个>100s成功的attempt结构**(hm_tier_attempts join, 抽样前几个):
| duration_ms | nv_key_idx(救回key) | att_n(失败attempt数) | att_seq(失败attempt: key(elapsed_ms)) |
|---|---|---|---|
| 122572 | 0 | 3 | 2:NVCFPexecTimeout(50618), 3:NVCFPexecTimeout(50655), 4:NVCFPexecTimeout(10657) |
| 121567 | 4 | 3 | 1:NVCFPexecTimeout(50555), 2:NVCFPexecTimeout(50620), 3:NVCFPexecTimeout(10537) |
| 120450 | 0 | 2 | 2:NVCFPexecTimeout(58810), 3:NVCFPexecTimeout(48541) |
| 119957 | 4 | 3 | 1:NVCFPexecTimeout(55038), 2:NVCFPexecTimeout(50631), 3:NVCFPexecTimeout(10519) |
| ... | ... | ... | (全为前2-3 key各hang满UPSTREAM=50s + 后key救回) |

**机制**: 这13个"慢成功"耗时>100s是因为**前2-3个key各hang满UPSTREAM=50s(NVCFPexecTimeout)才轮到救回key成功**。hm_tier_attempts只记录失败attempt(救回的最终成功attempt不记), 故att_n=2-3。若BUDGET=100, 这些请求在第2个50s timeout后(累计~100s)就因budget耗尽break, 不会试第3+key救回——**误杀≥13个救回成功(1.36%成功率)**。**HM2-C证伪持续成立**。

### 1h. 额外排查1 — UPSTREAM_TIMEOUT 50→45 不可行(误杀45-50s直成功)
6h成功请求duration分布(分桶):
| 区间 | n |
|---|---|
| 45-50s | **29** |
| 40-45s | 9 |
| 35-40s | 16 |
| 30-35s | 14 |
| <30s | 821 |

**29个45-50s成功的attempt结构**(hm_tier_attempts join, 抽样前15个):
| duration_ms | nv_key_idx | att_n | att_seq |
|---|---|---|---|
| 46235 | 3 | 0 | (无) |
| 46688 | 2 | 0 | (无) |
| 46958 | 3 | 0 | (无) |
| 47057 | 3 | 0 | (无) |
| ... | ... | 0 | (全att_n=0) |

**这29个全att_n=0**(无失败attempt), 即**att1直接成功, NVCF pexec耗时45-47s才返回**。降UPSTREAM=45会在45s timeout切断这29个pexec正跑到45-47s的成功请求, **误杀29个(3.0%成功率)**。**UPSTREAM 50→45不可行**。HM2的UPSTREAM=50是合理的(NVCF pexec常跑到45-50s)。

### 1i. 额外排查2 — CONNECT_RESERVE_S 21→12 不可行(令失败更慢)
代码(upstream.py:242): `per_attempt_timeout = min(UPSTREAM_TIMEOUT, remaining_budget - CONNECT_RESERVE_S)`。
- CONNECT_RESERVE=21 → per_attempt_timeout = min(50, remaining-21), 即每个attempt的read timeout上限被压低21s预留作connect+SSL。
- 降CONNECT_RESERVE 21→12 → per_attempt_timeout变大(+9s) → hang的NVCF pexec attempt**多跑9s才timeout** → 失败请求(39个/6h, avg 122s)从~122s→~131s(更慢)。
- HM2失败已是主要问题(95.99%成功率), 降CONNECT_RESERVE令失败更慢, 违背"稳定优先+越快越好"。
- 注: R323在HM1侧改CONNECT_RESERVE 16→12是因HM1 connect实测0.6-2.1s且12仍5.7x安全, HM1降是回收read预算给成功路径; 但HM2侧失败占比更高(39/6h vs HM1 22/4h), 降会放大失败耗时。**两机情境不同, 不可照搬, CONNECT_RESERVE 21→12不可行**。

### 1j. 改前(=当前2.5)env (HM2 docker exec hm40006 env)
| 参数 | HM2当前值 | 代码引用 | 备注 |
|---|---|---|---|
| UPSTREAM_TIMEOUT | 50 | upstream.py:235 | §1h证50→45误杀29个, 不可降 |
| **MIN_OUTBOUND_INTERVAL_S** | **2.5** | config.py:125, upstream.py:288 | R327改4.5→2.5生效, 本轮维持(高流量复查闭环) |
| KEY_COOLDOWN_S | 38 | config.py:141 | 429=0不触发 |
| TIER_COOLDOWN_S | 22 | ❌死参数(HM2无cooldown.py) | |
| TIER_TIMEOUT_BUDGET_S | 128 | upstream.py:215 | §1g证128→100误杀13个, 不可降; 128→123裕度0.4s太薄不值 |
| HM_CONNECT_RESERVE_S | 21 | upstream.py:227 | §1i证21→12令失败更慢, 不可降 |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | upstream.py:452 | 0次SSL触发 |
| HM_NV_PROXY_URL1~5 | 7894/空/空/空/7899 | ✅活 | k2/k3/k4全DIRECT |

**HM2 live compose** = `/opt/cc-infra/docker-compose.yml` line 472 (project=cc-infra, hm40006 service起于line 459, **不在git仓库**, R322教训#2)。

## 2. CC清单HM2-A/B/C 复核结论

### [HM2-A] MIN_OUTBOUND 4.5→2.5 — ✅ R327已做, 本轮高流量复查闭环, 维持2.5不回调
R327 §4c/§5待办: "若后续HM2流量回升到>20req/min需复查2.5下是否出现新串行阻塞或429, 必要时回调3.0"。
本轮高流量(30min=110reqs=3.67req/min, 为R327 POST窗口2.7的1.4倍, 虽未达20req/min但已是改后最高流量窗口)实测:
1. **429=0**: 改后30min零429(§1c/§1b), 降throttle 4.5→2.5在高流量下不增NVCF限流。✅
2. **阻塞率6.4%**: 改后30min仅7reqs(6.4%)间隔<2.5被2.5锁阻塞total 7.1s, 77.3%请求间隔>4.5s完全不受throttle影响(§1d)。2.5非瓶颈。
3. **A/B对比(改前4.5高流量30min vs 改后2.5高流量30min, §3)**: 阻塞率14.6%→6.4%, 429 0→0, 成功率99.34%→100%。
4. **维持2.5不回调**: 高流量零429+阻塞率6.4%+余量充足(77.3%请求>4.5s间隔), 无回调3.0必要。亦不进一步降到2.0(收益极小: 30min仅7个被2.5阻塞, 降到2.0只多解锁间隔2.0-2.5的2个请求对, 且增NVCF同IP并发风险, 不值)。
**结论**: HM2-A闭环完成, 维持2.5。

### [HM2-B] 失败模式补采+劣化key — ❌ 证伪(5key均匀无劣化, §1e/§1f)
120min per-key: n均匀(84-88), p95范围47.2-49.0s(仅1.8s跨度, 无离群), idx3 p95=48.4s与其他key趋同(R327时63.2s已收敛)。per-key失败率全0(失败5个全ATE落NULL)。**无像HM1-k4那样的劣化key, 无可改项**。

### [HM2-C] TIER_TIMEOUT_BUDGET 128→100 — ❌ 证伪持续成立(§1g)
6h成功>100s=13个, >120s=3个, >123s=0, max=122572ms(与R327完全一致)。hm_tier_attempts join查明13个>100s成功全为"前2-3 key各hang满UPSTREAM=50s + 后key救回", 降BUDGET=100误杀≥13个(1.36%成功率)。128→123裕度0.4s太薄不值。**证伪持续成立, 放弃**。

## 3. A/B验证 (HM2-A高流量复查: 改前4.5高流量30min vs 改后2.5高流量30min)

### 3a. 窗口选择
- **PRE改前(4.5)高流量30min**: 2026-06-30 03:12:54~03:42:54 DB口径 (R327改前锚点03:42:39前的30min, throttle=4.5)
- **POST改后(2.5)高流量30min**: 2026-06-30 04:12:54~04:42:54 DB口径 (本轮锚点前30min, throttle=2.5, R327已生效)

### 3b. A/B对比表
| 指标 | PRE 30min(4.5) | POST 30min(2.5) | 说明 |
|---|---|---|---|
| total reqs | 151 | 110 | PRE流量更高(5.03 vs 3.67req/min) |
| success | 150 | 110 | |
| fail(ATE) | 1 | 0 | 都是NVCF hang, 与throttle无关 |
| 成功率 | 99.34% | 100.00% | POST无新失败 |
| **429** | **0** | **0** | **降throttle未增429** ✅(高流量下也零429, 闭环R327待办) |
| empty200 | 0 | 0 | |
| **avg_gap** | 11.9s | 16.3s | POST流量低 |
| **被当前throttle阻塞** | 22 (14.6%, gap<4.5) | 7 (6.4%, gap<2.5) | 阻塞率结构性下降 |
| **throttle总等待** | (4.5下) | 7.1s | POST被2.5锁阻塞total 7.1s |

### 3c. A/B结论(机制层面, 控制流量不对称)
1. **429未增(高流量闭环)**: PRE(4.5,5.03req/min)0 → POST(2.5,3.67req/min)0。降throttle 4.5→2.5在高流量下零429, 不增NVCF限流(throttle是进程内串行非NVCF端保护)。**R327待办"2.5高流量复查"闭环: 维持2.5不回调**。✅
2. **阻塞率结构性下降**: PRE(4.5)14.6%被4.5锁阻塞 → POST(2.5)6.4%被2.5锁阻塞。降到2.5后间隔2.5-4.5区间的请求对不再阻塞。POST流量虽低于PRE, 但阻塞率(6.4%)是结构性低值(77.3%请求间隔>4.5s完全不受throttle影响)。
3. **失败模式不变**: 两边失败都是NVCF平台hang(ATE 122s), 与throttle无关。
4. **流量不对称标注**: PRE 5.03req/min vs POST 3.67req/min, POST流量约为PRE 73%。被阻塞绝对数天然偏低, 但429=0+阻塞率6.4%+77.3%请求>4.5s间隔, 机制证明2.5余量充足。当前HM2流量2.65-3.67req/min, 2.5的余量充足; 若后续流量回升到>20req/min(avg_gap<3s)需再次复查。

## 4. 本轮无新参数改动说明(诚实标注)

本轮**未改任何HM2参数**。原因: CC清单HM2侧A/B/C三项全做完/证伪(A=R327已做+本轮高流量闭环, B=§1e/§1f证伪, C=§1g证伪), 清单外两个对称候选也数据证伪不可行(UPSTREAM 50→45误杀29个45-50s直成功=§1h, CONNECT_RESERVE 21→12令失败更慢=§1i)。

按规则"不允许无操作轮除非三项都已做完或数据证伪(证伪需给出具体数据)", 本轮附:
- HM2-B证伪数据: §1e(5key p95范围47.2-49.0s无离群)+§1f(per-key失败率全0)
- HM2-C证伪数据: §1g(13个>100s成功全多attempt救回, 降BUDGET误杀1.36%)
- 额外候选证伪: §1h(UPSTREAM降误杀29个3.0%)+§1i(CONNECT_RESERVE降令失败+9s)
- HM2-A高流量闭环: §1d/§3(2.5在3.67req/min下零429+阻塞率6.4%)

本轮价值: 闭环R327遗留的"2.5高流量复查"待办(零429确认), 并用hm_tier_attempts join首次查明HM2>100s慢成功与45-50s直成功的attempt结构, 为后续轮次排除UPSTREAM/BUDGET/CONNECT_RESERVE三个候选(均有数据证伪)。

## 5. 结论

1. **HM2-A高流量复查闭环**: 2.5在3.67req/min高流量下零429+阻塞率6.4%(7个/30min, total等待7.1s)+77.3%请求间隔>4.5s完全不受throttle影响。维持2.5不回调, 亦不降到2.0(收益极小增风险)。R327待办闭环。
2. **HM2-B证伪**: 5key均匀(p95范围47.2-49.0s仅1.8s跨度), 无劣化key, idx3 p95=48.4s已从R327时63.2s收敛。
3. **HM2-C证伪**: 13个>100s成功全为"前2-3 key hang满UPSTREAM=50s+后key救回"(hm_tier_attempts join首次查明), 降BUDGET误杀1.36%成功率。
4. **额外候选证伪**: UPSTREAM 50→45误杀29个45-50s直成功(att_n=0, pexec 45-47s, 3.0%成功率); CONNECT_RESERVE 21→12令失败attempt多hang9s(失败更慢)。均不可行。
5. **稳定优先**: 6h零429/零真实empty200/零SSL, 2.5在高流量下不破坏零限流基线; 失败全NVCF平台hang(ATE 122s=2×50s)非HM2参数可解。
6. **单参数/无搭车**: 本轮无新参数改动(三项全证伪), 严格未搭车。
7. **诚实标注**: 本轮为验证+证伪轮, 非新改动轮。HM2侧当前无可安全调整的参数(throttle=2.5已目标值且高流量闭环, UPSTREAM/BUDGET/CONNECT_RESERVE均证伪不可降)。下轮HM2→HM1时HM1侧可复查R328的6.0在高峰期表现。

## 6. 待办 (留给下轮HM2→HM1)

- [ ] **下轮HM2→HM1**: R328已执行HM1-A(MIN_OUTBOUND 9.0→6.0), R328 POST窗口凌晨极低流量(1req/28min)未真正压测6.0。下轮若遇HM1高峰期(21-01点, >10req/min)必须复查6.0下是否出现新串行阻塞或429。若高峰期6.0下零429且阻塞率<12%可考虑再降到5.0; 若出现429或阻塞率回升回调7.0。
- [ ] **HM2 MIN_OUTBOUND=2.5超高流量复查**: 本轮3.67req/min(最高改后流量)零429+阻塞率6.4%。若后续HM2流量回升到>20req/min(avg_gap<3s)需再次复查2.5下是否出现新串行阻塞或429, 必要时回调3.0。
- [ ] **HM2失败全是NVCF平台hang(ATE 122s×39/6h)**: 2×UPSTREAM=50s hang, 非HM2参数可解(UPSTREAM不可降=§1h误杀45-50s直成功)。若NVCF平台层hang持续恶化, 需从NVCF账号/key层面考虑, 超出HM参数范围。
- [ ] **HM2侧TIER_COOLDOWN_S=22死参数**(无cooldown.py): env设但代码不引用, 429=0分支不触发, 无运行意义, 低优先。
- [ ] **HM2侧HM_SSLEOF_RETRY_ENABLED=true但代码不读**(两机代码都无条件retry): 死env, 低优先。
- [ ] **HM2侧HM_CONNECT_RESERVE_S=21偏大**(HM1=12): 本轮证伪21→12(令失败更慢), 但21本身是否过保守(connect实测2-5s)值得未来在HM2失败率下降后重新评估——当前失败39/6h太高不宜降。

## ⏳ 轮到HM2优化HM1
