# R328: HM2→HM1 — MIN_OUTBOUND_INTERVAL_S 9.0→6.0 (-3.0s) · 推翻R326低峰期证伪(HM1-A throttle非瓶颈) · 高峰4h373reqs per-pair间隔分布实测throttle=9.0阻塞69reqs(18.5%)总等待272.3s→降到6.0仅阻��38(10.2%)省159.5s · 改前高峰30min(00:30-01:00)52reqs throttle=9.0阻塞16个(30.8%) · 6h零429降throttle不增NVCF限流 · 改后低流量窗口诚实标注(凌晨0.04req/min)待高峰期复查

**角色**: HM2(执行者, opc2_uname) → HM1(目标, opcsname/opc_uname, deepseek_hm_nv)
**日期**: 2026-06-30 04:12 UTC (DB ts口径, host_machine LIKE 'opc%')
**铁律**: 只改HM1不改HM2
**前轮**: R327 (HM1→HM2, MIN_OUTBOUND 4.5→2.5, 推翻R325证伪)
**本轮基线锚点**: 改前 max(ts)=2026-06-30 04:12:19+00 UTC; 改后窗口起点 2026-06-30 04:12:19+00 UTC (容器04:12:04 recreate, 04:12:19首个test req入库)

## 0. 任务规则与本轮决策依据

任务规则: "优先执行清单第1项, 若第1项本轮无法实施(如已被前轮做过/数据不支撑), 顺延下一项。每轮只做1项。不允许无操作轮除非三项都已做完或数据证伪(证伪需给出具体数据)。"

本轮对CC定向清单HM1侧三项(A/B/C)用**当前实测数据+per-pair间隔分布(借鉴R327方法)**逐一复核:
- **HM1-A (MIN_OUTBOUND 9.0→更低)**: ❌❌ **推翻R326证伪, 本轮执行**。R326称"throttle=9.0已是目标值, HM1流量0.27-2req/min, 99%请求9s窗口内无邻居, throttle几乎从不触发串行等待, 降到更低零吞吐收益"——**此判断只看03:01低峰期数据(17reqs/2h), 漏了高峰期per-pair阻塞**。本轮用请求间隔分布实测: 高峰4h(21-01点)373reqs, **69reqs(18.5%)间隔<9.0s被throttle=9.0串行锁阻塞, total等待272.3s**; 改前高峰30min(00:30-01:00)52reqs, **16个(30.8%)被阻塞total 73.9s**。throttle按"每对相邻请求"粒度阻塞(per-pair全局串行锁, config.py:129), 非按"平均到达率"——R326只看低峰期平均速率漏了高峰期per-pair阻塞, 与R327在HM2侧推翻R325完全同逻辑。降到6.0: 高峰4h仅38reqs(10.2%)阻塞total 112.8s, 释放31reqs省159.5s/4h。6h零429→降throttle不增NVCF限流(throttle是进程内串行, 非NVCF端保护)。**本轮执行HM1-A, 9.0→6.0**(选6.0非更低: 6.0仍为HM2(2.5)的2.4倍保持梯度, 单参数少改多轮)。
- HM1-B (k4 idx3路由劣化): R326已用ttfb数据决定性证伪(今日idx3 ttfb p50=18.4s/p95=57.5s与其他key 17.8-20.8s/47.6-60.3s几乎相同, R322已改URL4→7897且生效)。本轮高峰4h per-key复查(§1e)5key均匀(idx3 p95=73.2s略高但ttfb已证非首字节劣化), 无可改项。
- HM1-C (all_tiers_exhausted早fail): R326已用代码逻辑证伪(BUDGET=100/UPSTREAM=45/CONNECT_RESERVE=12下fast-fail收益仅~10s/次非CC说的50s, 误杀4个>80s救回)。本轮无新数据推翻, 放弃。

本轮选清单第1项HM1-A执行(数据支撑, 推翻R326低峰期误判, 与R327对称)。

## 1. 改前数据采集 (锚点 max_ts=2026-06-30 04:12:19+00 UTC, HM1)

### 1a. 多窗口成功率 (相对max_ts, host_machine LIKE 'opc%')
| 窗口 | total | success | fail | 成功率 | reqs/min |
|---|---|---|---|---|---|
| 30min | 2 | 1 | 1 | 50.00% | 0.07 |
| 60min | 2 | 1 | 1 | 50.00% | 0.03 |
| 120min | 17 | 16 | 1 | 94.12% | 0.14 |
| 360min(6h) | 409 | 389 | 20 | 95.11% | 1.14 |

**当前凌晨流量极低**: 30min=2reqs(0.07req/min), 120min=17reqs。但6h窗口409reqs说明高峰期在过去几小时(见§1b hourly分布)。当前低流量窗口与R326观察一致(02-04点极低)。**A/B验证的关键是高峰期数据, 非当前低流量**(见§4说明)。

### 1b. hourly流量分布 (近8h, 显示高峰/低峰差异)
| 小时(UTC) | total | success | fail | 成功率 |
|---|---|---|---|---|
| 21:00 | 34 | 31 | 3 | 91.2% |
| 22:00 | 143 | 136 | 7 | 95.1% |
| 23:00 | 74 | 63 | 11 | 85.1% |
| 00:00 | 122 | 120 | 2 | 98.4% |
| 01:00 | 59 | 59 | 0 | 100.0% |
| 02:00 | 11 | 11 | 0 | 100.0% |
| 03:00 | 6 | 6 | 0 | 100.0% |
| 04:00 | 2 | 1 | 1 | 50.0% |

**高峰期21-01点(4h)373reqs=1.56req/min, 低峰期02-04点(2h)19reqs=0.16req/min**。R326锚点03:01正处于低峰期, 故"99%请求9s窗口无邻居"只是低峰现象。高峰期流量是低峰的10倍, per-pair间隔<9s的请求对密集(§1d)。

### 1c. 高峰4h(21-01点)错误结构 + 成功延迟
| error_type | n | avg_dur | p50 | p95 | max_dur |
|---|---|---|---|---|---|
| (success) | 350 | 26140 | 20874 | 57712 | 162974 |
| all_tiers_exhausted | 22 | 104209 | 89102 | 177950 | 181451 |
| NVStream_TimeoutError | 1 | 99642 | 99642 | 99642 | 99642 |

**所有失败都是 NVCF平台hang**: 22 ATE(avg 104s=2×45s hang, p50=89s, max=181s)+1 NVStream。无429/empty200/SSL。失败全NVCF服务端pexec hang, 非HM1参数可解。

### 1d. **throttle阻塞实测(HM1-A核心证据)** — 高峰4h + 高峰30min per-pair间隔分布
| 窗口 | n | 被throttle=9.0阻塞(gap<9.0) | 阻塞率 | 阻塞total等待 | 降到6.0仍阻塞(gap<6.0) | 6.0下等待 | 降到6.0释放 | 降到6.0省 |
|---|---|---|---|---|---|---|---|---|
| 高峰4h(21-01) | 373 | 69 | **18.5%** | **272.3s** | 38 | 112.8s | 31reqs | **159.5s/4h** |
| 高峰30min(00:30-01:00) | 52 | 16 | **30.8%** | **73.9s** | 9 | 36.2s | 7reqs | 37.7s/30min |

**机制**: throttle_outbound()(config.py:129-138)是**全局串行锁**(与HM2代码byte-for-byte一致)——每对相邻请求若间隔<MIN_OUTBOUND_INTERVAL_S, 后者wait(INTERVAL-gap)。非"平均到达率"粒度, 是"per-pair"粒度。即使平均速率(高峰1.56req/min=38s/req)远低于理论上限(60/9.0=6.67req/min), 只要存在<9s间隔的请求对(18.5%)就会被阻塞。**R326只看低峰期平均速率(03:01锚点17reqs/2h, 99%无邻居), 漏了高峰期18.5%请求被per-pair串行锁阻塞**——与R327在HM2侧推翻R325("只看平均速率漏了per-pair阻塞")完全同逻辑同漏洞。

**降到6.0的量化收益(高峰4h)**: 仅38reqs(10.2%)间隔<6.0s被阻塞total 112.8s, 解锁31reqs(间隔6-9s区间的请求对不再阻塞)省159.5s/4h。被阻塞请求avg wait 3.9s(max 8.9s), 是真实延迟。

### 1e. 高峰4h per-key成功延迟 (复查HM1-B, host_machine LIKE 'opc%', status=200)
| nv_key_idx | 键名(env proxy) | n | avg_dur | p50 | p95 |
|---|---|---|---|---|---|
| 0 | k1 (7894) | 72 | 26337 | 21765 | 50956 |
| 1 | k2 (DIRECT) | 71 | 25490 | 21669 | 60166 |
| 2 | k3 (DIRECT) | 71 | 25359 | 20086 | 55638 |
| 3 | k4 (7897) | 69 | 28939 | 23011 | 73150 |
| 4 | k5 (7899) | 67 | 24560 | 19860 | 57751 |

5key均匀(67-72), p50=20.1-23.0s, p95=51.0-73.2s。idx3 p95=73.2s略高, 但R326已用ttfb数据决定性证伪(今日idx3 ttfb p50=18.4s/p95=57.5s与其他key几乎相同, DB的73.2s是流式传输慢非pexec劣化, R322已改URL4→7897且生效)。**HM1-B无可改项**。

### 1f. 6h限流/SSL基线
| 指标 | 值 |
|---|---|
| 6h总请求 | 409 |
| 429 | **0** |
| empty200 | **0** |
| SSLEOF | **0** (HM1全历史0次SSL触发, R326已证) |

### 1g. 改前env (HM1 docker exec hm40006 env, 本轮改MIN_OUTBOUND)
| 参数 | HM1改前值 | 代码引用 | 备注 |
|---|---|---|---|
| UPSTREAM_TIMEOUT | 45 | upstream.py:137 | |
| **MIN_OUTBOUND_INTERVAL_S** | **9.0** | **config.py:125, upstream.py:198 (attempt_idx==0)** | **本轮改9.0→6.0** |
| KEY_COOLDOWN_S | 38 | cooldown.py:19 | 429=0不触发 |
| TIER_COOLDOWN_S | 38 | cooldown.py:20, upstream.py:411 | 全tier 429才触发, 0次 |
| TIER_TIMEOUT_BUDGET_S | 100 | upstream.py:117 | R323改90→100生效 |
| HM_CONNECT_RESERVE_S | 12 | upstream.py:227 | 9880398改16→12生效 |
| HM_SSLEOF_RETRY_DELAY_S | 3.0 | upstream.py:452 | 0次SSL触发, 改无效果 |
| HM_NV_PROXY_URL1~5 | 7894/空/空/7897/7899 | ✅活 | R322改URL4 direct→7897 |

**HM1 live compose** = `/opt/cc-infra/docker-compose.yml` (project=cc-infra, **不在git仓库**, R322教训#2已记录)。

## 2. CC清单HM1-A/B/C 复核

### [HM1-A] MIN_OUTBOUND_INTERVAL_S 9.0→6.0 — ✅ **本轮执行(推翻R326低峰期证伪)**
**R326证伪(被推翻)**: "throttle=9.0已是目标值, HM1流量0.27-2req/min, 99%请求9s窗口内无邻居, throttle几乎从不触发串行等待, 降到更低零吞吐收益。6h零429降throttle净风险无收益。"
**R326的数据漏洞**: 只看**03:01低峰期**数据(17reqs/2h, 99%无邻居), 漏了throttle_outbound()是**全局串行锁per-pair阻塞**(config.py:129 `with _outbound_throttle_lock: wait=INTERVAL-elapsed`)。低峰期请求间隔>9s, throttle确实不触发; 但**高峰期(21-01点)流量是低峰10倍, 18.5%请求间隔<9s被per-pair串行锁阻塞**。R326的"99%无邻居=throttle非瓶颈"推理只在低峰期成立, 高峰期不成立。
**本轮决定性数据(§1d)**:
1. **高峰4h实测69reqs(18.5%)间隔<9.0s被阻塞, total等待272.3s**; 高峰30min(00:30-01:00)16个(30.8%)阻塞73.9s。R326只看低峰期平均速率漏了高峰期per-pair阻塞——与R327在HM2侧推翻R325完全同逻辑。
2. **降到6.0的量化收益(高峰4h)**: 仅38reqs(10.2%)间隔<6.0s被阻塞total 112.8s, 解锁31reqs(间隔6-9s区间的请求对不再阻塞)省159.5s/4h; 高峰30min省37.7s。被阻塞请求avg wait 3.9s(max 8.9s), 是真实延迟。
3. **6h零429, 降throttle不增NVCF限流**: throttle是HM1进程内串行锁(防止本进程内请求扎堆出站), 非NVCF服务端限流保护。NVCF 429是按API key/account配额, 与进程内throttle无关。降throttle不直接增NVCF同IP 429。且HM1高峰1.56req/min, 降到6.0后只有间隔<6.0s的请求对(高峰4h 38个)仍串行, 远低于NVCF限流阈值。R327已在HM2侧验证降throttle(4.5→2.5)6h零429不增限流, HM1同机制。
4. **throttle仅attempt_idx==0触发**(upstream.py:198 `if attempt_idx == 0: throttle_outbound()`), 每请求首次出站throttle一次, 重试attempt不过throttle。降INTERVAL不影响重试路径。
5. **选6.0非更低(如4.5或2.5)**: 6.0仍为HM2(2.5)的2.4倍保持梯度(HM1后端deepseek, HM2后端glm5.1, 两账号不同, 保持梯度避免HM1过度并发); 单参数少改多轮, 若高峰期6.0下零429则下轮可考虑再降到5.0。
**结论**: HM1-A数据支撑执行, 9.0→6.0。

### [HM1-B] k4(idx3, 7897)路由劣化修复 — ❌ R326已决定性证伪(ttfb推翻), 本轮复查无可改项
R326用hm_metrics的ttfb_ms分key统计: 今日(06-30)idx3 ttfb p50=18.4s/p95=57.5s与其他key(17.8-20.8s/47.6-60.3s)几乎相同, DB的p95=73.7s是流式传输慢非pexec劣化, R322已改URL4 direct→7897且env实测生效。本轮高峰4h per-key(§1e)idx3 p95=73.2s略高但与R326同模式, ttfb已证非首字节劣化。**无可改项**。

### [HM1-C] all_tiers_exhausted早fail(前3key全NVCFPexecTimeout fast-fail) — ❌ R326已代码逻辑证伪, 本轮无新数据推翻
R326用BUDGET=100/UPSTREAM=45/CONNECT_RESERVE=12实际代码逻辑推演: fast-fail收益仅~10s/次(非CC说的50s), 因BUDGET耗尽后第3+key的per_attempt_timeout=max(5, remaining-reserve)=5s短超时本就试不长; 且误杀4个>80s救回成功(0.47%成功率)。本轮高峰4h失败22 ATE avg=104s(2×45s hang)印证R326分析。**收益180s/6h vs 误杀0.47%成功率不值, 证伪持续成立, 放弃**。

## 3. 改动 (对端HM1, 单参数)

### 3a. 改动: MIN_OUTBOUND_INTERVAL_S 9.0→6.0 (-3.0s)
- **live compose** `/opt/cc-infra/docker-compose.yml` line 421 (project=cc-infra, **不在git仓库**, R322教训#2):
  ```yaml
  # 改前: MIN_OUTBOUND_INTERVAL_S: "9.0"  # R320: HM2→HM1 — 18.2→9.0 ...
  # 改后: MIN_OUTBOUND_INTERVAL_S: "6.0"  # R328: HM2→HM1 — 9.0→6.0 ... 推翻R326低峰期证伪...
  ```
- 备份: `/opt/cc-infra/docker-compose.yml.bak.R328_20260630_041100`
- **live compose不在git, 本次改动已部署生效但未入git**。仓库内仅有归档副本(deploy_artifacts/), 改归档副本对运行态无影响(R322教训#2)。CC托底时会同步。

### 3b. 部署: force-recreate
```bash
cd /opt/cc-infra && sudo docker compose up -d --force-recreate hm40006
# Container hm40006 Recreated → Started
```

### 3c. 验证三重(实质数据流向)
| 验证项 | 结果 |
|---|---|
| 容器运行态env | `docker exec hm40006 printenv MIN_OUTBOUND_INTERVAL_S` = **6.0** ✅ |
| live compose | `sudo sed -n 421p` = `MIN_OUTBOUND_INTERVAL_S: "6.0"` ✅ (两边同步, 非R322教训#1只改容器态) |
| /health | curl = **200** ✅ |
| 实测请求 | POST /v1/chat/completions deepseek_hm_nv → HTTP=200, 2.07s, content="OK"(k3) ✅ (新配置生效非旧) |
| 容器StartedAt | 2026-06-29T20:12:04Z (=04:12:04 UTC, recreate成功) ✅ |

## 4. A/B验证 (改前vs改后窗口对比)

### 4a. 窗口选择与流量不对称说明(诚实标注)
- **改前PRE窗口(高流量)**: 高峰4h 2026-06-29 21:00~06-30 01:00 UTC (373reqs, throttle=9.0); 及高峰30min 00:30~01:00 (52reqs)
- **改后POST窗口(极低流量)**: 04:12:19起 ~28min (至~04:40, throttle=6.0)
- **流量严重不对称(诚实标注)**: POST窗口处于凌晨低峰(02-04点0.16req/min), 28min内仅1个自然请求(我的test探测请求), 无法做大样本A/B。**这与R327不同——R327 POST窗口至少有27reqs/12.5min, HM1 POST窗口流量更低**。原因: HM1凌晨流量本就极低(§1b hourly: 04:00仅2reqs), 与throttle无关。因此POST的A/B只能做**机制验证+稳定性验证**, 不能做duration p50/p95对比(样本=1)。

### 4b. A/B对比表
| 指标 | PRE高峰4h(9.0) | PRE高峰30min(9.0) | POST(28min,6.0) | 说明 |
|---|---|---|---|---|
| total reqs | 373 | 52 | 1 | POST凌晨极低流量(非throttle所致) |
| success | 350 | 52 | 1 | |
| fail(ATE/NVS) | 23 | 0 | 0 | POST 1req成功 |
| 成功率 | 93.8% | 100.0% | 100% | POST样本=1不可比, 但无新失败 |
| 429 | 0 | 0 | **0** | **降throttle未增429** ✅(机制) |
| empty200 | 0 | 0 | 0 | |
| p50 duration | 20874ms | — | 2066ms | POST样本=1, 不可比(且test是max_tokens=5的短请求) |
| p95 duration | 57712ms | — | 2066ms | POST样本=1, 不可比 |
| **avg_gap** | — | — | — | POST 1req无gap |
| **被阻塞(gap<9.0)** | 69 (18.5%) | 16 (30.8%) | 0 | PRE高峰18.5%被9.0锁阻塞; POST 1req无邻居 |
| **被阻塞(gap<6.0)** | 38 (10.2%) | 9 (17.3%) | 0 | 降到6.0后高峰期阻塞率18.5%→10.2% |
| **throttle总等待** | 272.3s | 73.9s | 0s | POST 1req无阻塞 |

### 4c. A/B结论(机制层面, 控制流量不对称)
1. **throttle阻塞机制验证(PRE数据决定性)**: PRE高峰4h(throttle=9.0)有69reqs(18.5%)因间隔<9.0s被串行锁阻塞total 272.3s; PRE高峰30min(00:30-01:00)16个(30.8%)阻塞73.9s。**证明throttle=9.0在高峰期确实阻塞18.5%请求**——R326"99%无邻居"只是低峰期现象, 高峰期不成立。
2. **降到6.0的结构性释放(机制推演)**: 用PRE高峰4h数据按throttle=6.0重算——仅38reqs(10.2%)间隔<6.0s被阻塞total 112.8s, **间隔6-9s区间的31reqs不再阻塞, 省159.5s/4h**; 高峰30min省37.7s。这是结构性减少(间隔6-9s的请求对在6.0下wait≤0直接放行), 非流量偶然。
3. **429未增(机制+POST实测)**: PRE 0, POST 0。降throttle不增NVCF限流(机制: throttle是进程内串行非NVCF端保护, 与R327 HM2侧4.5→2.5验证同)。POST虽仅1req, 但6.0生效后该请求正常成功无429。
4. **失败模式不变**: PRE高峰4h23失败全NVCF平台hang(ATE 104s=2×45s, NVS 99s), 与throttle无关。throttle只影响出站等待≤INTERVAL, 不影响NVCF pexec执行时长。
5. **duration不可比(诚实标注)**: POST仅1req且是max_tokens=5的test探测请求(2.07s), 无法与PRE高峰期真实流量duration对比。throttle对duration的贡献≤INTERVAL=9.0/6.0s, 远小于NVCF pexec的20-181s波动, 被噪声淹没。**A/B的关键指标是throttle阻塞数/率/等待(机制层面), 非duration**。

**待观察(诚实标注)**: POST窗口仅28min/1req, 凌晨极低流量。throttle=6.0在**高峰期**(avg_gap<6s, 即>10req/min)才会真正受压测。当前HM1凌晨0.16req/min, 6.0的余量极其充足。**下轮若遇HM1高峰期(21-01点), 必须复查6.0下是否出现新的串行阻塞或429, 必要时回调7.0或8.0**。本轮机制验证(PRE高峰18.5%阻塞→6.0下10.2%)已结构性证明收益, 但POST实测样本不足, 标"待高峰期复查"。

## 5. 结论

1. **HM1-A执行成功**: MIN_OUTBOUND_INTERVAL_S 9.0→6.0, 三重验证(env=6.0/compose=6.0/health=200/实测请求200)。
2. **推翻R326证伪**: R326只看03:01低峰期数据(17reqs/2h, 99%无邻居)漏了throttle全局串行锁per-pair阻塞(高峰4h实测18.5%请求被阻塞)。本轮用高峰期请求间隔分布数据决定性证明throttle=9.0在高峰期确实阻塞18.5%请求, 降到6.0结构性解除(间隔6-9s区间的请求对不再阻塞, 省159.5s/4h)。与R327在HM2侧推翻R325完全对称。
3. **A/B机制验证**: PRE高峰4h69reqs阻塞272.3s→6.0下仅38reqs阻塞112.8s(机制推演), 429未增(0→0), 失败模式不变(ATE NVCF hang)。
4. **单参数**: 只改MIN_OUTBOUND_INTERVAL_S一个env, 未搭车(吸取R320教训#1一轮两改)。
5. **稳定优先**: 6h零429/零真实empty200/零SSL, 降throttle不破坏零限流基线; 失败全NVCF平台hang非HM1参数可解。
6. **诚实标注低流量**: POST窗口凌晨极低流量(1req/28min), 实测样本不足, 机制验证+稳定性验证完成, duration对比标"待高峰期复查"。

## 6. 待办 (留给下轮HM1→HM2)

- [ ] **下轮HM1→HM2**: R327已执行HM2-A(MIN_OUTBOUND 4.5→2.5), HM2侧可复查2.5在高流量期是否出现新串行阻塞或429(R327 POST窗口流量也低, 31.5s/req)。HM2侧B/C已证伪。
- [ ] **HM1 MIN_OUTBOUND=6.0高峰期复查(重要)**: 本轮POST窗口凌晨极低流量(1req/28min), 6.0余量极其充足。**下轮若遇HM1高峰期(21-01点, >10req/min), 必须复查6.0下是否出现新的串行阻塞或429**。若高峰期6.0下零429且阻塞率<12%, 可考虑下轮再降到5.0; 若出现429或阻塞率回升, 回调7.0。
- [ ] **HM1失败全是NVCF平台hang(ATE 104s×22/4h)**: 2×45s hang, 非HM1参数可解。若NVCF平台层hang持续恶化, 需从NVCF账号/key层面考虑, 超出HM参数范围。
- [ ] **HM1侧HM_SSLEOF_RETRY_DELAY_S=3.0**: 0次SSL触发, 改无效果(R326已证), 低优先。
- [ ] **HM1侧HM_SSLEOF_RETRY_ENABLED未设(env)**: 两机代码都无条件retry(upstream.py:452无ENABLED检查)→死env, 低优先。

## ⏳ 轮到HM1优化HM2
