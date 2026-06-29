# R327: HM1→HM2 — MIN_OUTBOUND_INTERVAL_S 4.5→2.5 (-2.0s) · 推翻R325"throttle非瓶颈"误判(只看平均速率漏了全局串行锁per-pair阻塞12.7%) · 实测改前120min 47reqs阻塞56.8s→改后仅1req阻塞0.3s · 6h零429降throttle不增限流

**角色**: HM1(执行者, opc_uname) → HM2(目标, opc2sname, glm5.1_hm_nv)
**日期**: 2026-06-30 04:01 UTC (DB ts口径, host_machine='opc2sname')
**铁律**: 只改HM2不改HM1
**前轮**: R326 (HM2→HM1, 无操作, HM1侧三项证伪)
**本轮基线锚点**: 改前 max(ts)=2026-06-30 03:42:39+00 UTC; 改后窗口起点 2026-06-30 03:48:00+00 UTC (容器03:47:30 recreate, 03:48:13首个test req入库)

## 0. 任务规则与本轮决策依据

任务规则: "优先执行清单第1项, 若第1项本轮无法实施(如已被前轮做过/数据不支撑), 顺延下一项。每轮只做1项。不允许无操作轮除非三项都已做完或数据证伪(证伪需给出具体数据)。"

本轮对CC定向清单HM2侧三项(A/B/C)用**当前实测数据(锚点03:42:39)**逐一复核:
- **HM2-A (MIN_OUTBOUND 4.5→2.5)**: ❌❌ **推翻R325证伪, 本轮执行**。R325称"3.35req/min<<13.3上限, throttle非瓶颈"——**此判断只看平均速率, 漏了throttle是全局串行锁(per-pair阻塞)**。本轮用请求间隔分布实测: 120min内47reqs(12.7%)到达间隔<4.5s, 被串行锁阻塞total 56.8s; 60min内34reqs(12.3%)阻塞total 36.3s。throttle按"每对相邻请求"��度阻塞, 非按"平均到达率"——即使平均速率远低于上限, 只要存在<4.5s间隔的请求对就会被阻塞。降到2.5: 120min仅7reqs阻塞total 11.3s, 解锁40reqs省45.5s。6h零429→降throttle不增NVCF限流(throttle是进程内串行, 非NVCF端保护)。**本轮执行HM2-A**。
- HM2-B (失败模式补采+劣化key): R325已采, 本轮120min per-key复查(§1e)5key均匀无劣化, 无可改项。
- HM2-C (BUDGET 128→100): 6h成功>100s=13个, >120s=3个(max 122572ms)。任何BUDGET<123s误杀≥1个救回。R325证伪持续成立, 放弃。

本轮选清单第1项HM2-A执行(数据支撑, 推翻前轮误判)。

## 1. 改前数据采集 (锚点 max_ts=2026-06-30 03:42:39+00, HM2)

### 1a. 多窗口成功率 (非排他窗口, host_machine='opc2sname')
| 窗口 | total | success | fail | 成功率 | reqs/min |
|---|---|---|---|---|---|
| 30min | 151 | 151 | 0 | **100.00%** | 5.03 |
| 60min | 274 | 271 | 3 | 98.91% | 4.57 |
| 120min | 366 | 351 | 15 | 95.90% | 3.05 |
| 360min(6h) | 968 | 921 | 47 | 95.14% | 2.69 |

**流量上升**: 30min=151reqs→5.03req/min (vs R325时4.57, R323时2.4)。30min窗口100%成功率。

### 1b. 6h错误结构
| error_type | n | avg_dur | p50 | p95 | max_dur |
|---|---|---|---|---|---|
| (success) | 921 | 15487 | 8654 | 60947 | 122572 |
| all_tiers_exhausted | 46 | 122633 | 122241 | 127388 | 128337 |
| NVStream_IncompleteRead | 1 | 8927 | 8927 | 8927 | 8927 |

**所有失败都是 all_tiers_exhausted**, avg 122s ≈ BUDGET 128s 减overhead, 耗满预算。无429/empty200/SSL。

### 1c. 6h限流/SSL基线
| 指标 | 值 |
|---|---|
| 6h总请求 | 968 |
| 429 | **0** |
| empty200(真实) | **0** |
| SSLEOF backoff触发 | R325已验证1次(03:08:19, 1.0s), 本轮窗口未自然触发 |

### 1d. **throttle阻塞实测(HM2-A核心证据)** — 120min/60min请求间隔分布
| 窗口 | n | 间隔<4.5s(被throttle=4.5阻塞) | 阻塞率 | 阻塞total等待 | 间隔<2.5s(throttle=2.5仍阻塞) | 2.5下等待 | 降到2.5省 |
|---|---|---|---|---|---|---|---|
| 60min | 278 | 34 | 12.3% | 36.3s | 4 | 5.2s | 31.1s/60min |
| 120min | 370 | 47 | 12.7% | 56.8s | 7 | 11.3s | 45.5s/120min |

**机制**: throttle_outbound()(config.py:126)是**全局串行锁**——每对相邻请求若间隔<MIN_OUTBOUND_INTERVAL_S, 后者wait(INTERVAL-gap)。非"平均到达率"粒度, 是"per-pair"粒度。即使平均速率(5req/min=12s/req)远低于理论上限(60/4.5=13.3req/min), 只要存在<4.5s间隔的请求对(12.7%)就会被阻塞。R325只看平均速率, 漏了此per-pair阻塞。

### 1e. 120min per-key成功延迟+ttfb (复查HM2-B, host_machine='opc2sname', status=200)
| nv_key_idx | 键名(env proxy) | n | dur_p50 | dur_p95 | ttfb_p50 | ttfb_p95 |
|---|---|---|---|---|---|---|
| 0 | k1 (7894) | 74 | 8677 | 61306 | 8547 | 61005 |
| 1 | k2 (DIRECT) | 68 | 7958 | 51752 | 7822 | 49830 |
| 2 | k3 (DIRECT) | 68 | 7172 | 47404 | 6998 | 47404 |
| 3 | k4 (DIRECT) | 70 | 8654 | 63249 | 8395 | 62717 |
| 4 | k5 (7899) | 69 | 8512 | 59394 | 8310 | 59143 |

5key均匀(68-74), dur_p50=7.2-8.7s, dur_p95=47-63s, ttfb_p50=7.0-8.5s。**无像HM1-k4那样的劣化key**(HM1-k4 ttfb_p95曾被误判劣化, R326已ttfb推翻)。HM2-B无可改项。

### 1f. 6h失败请求attempt序列(docker logs实测, 典型ATE请求03:42:48)
```
[03:42:48.8] attempt 1/7: k1 → NVCF pexec ... via 7894
[03:43:39.1] HM-TIMEOUT k1 timeout: attempt=50323ms total=50331ms
[03:43:39.1] attempt 2/7: k2 → ... via DIRECT
[03:44:29.6] HM-TIMEOUT k2 timeout: attempt=50500ms total=100832ms
[03:44:29.6] attempt 3/7: k3 → ... via DIRECT
[03:44:40.2] HM-TIMEOUT k3 timeout: attempt=10603ms total=111436ms   ← per_attempt=max(10,min(50,28-21))=10
[03:44:40.2] attempt 4/7: k4 → ... via DIRECT
[03:44:50.8] HM-TIMEOUT k4 timeout: attempt=10584ms total=122021ms   ← per_attempt=max(10,min(50,17-21=-4))=10
[03:44:50.8] HM-TIER-BUDGET budget 128s remaining 6.0s < 10s minimum, breaking
[03:44:50.8] HM-TIER-FAIL all 5 keys failed: 429=0, empty200=0, timeout=4, elapsed=122023ms
```
**失败路径**: att1+att2各hang满UPSTREAM_TIMEOUT=50s(共100s), att3+att4因budget耗尽per_attempt被MIN_ATTEMPT=10 floor(各~10.6s, 共21s), budget remaining=6<10 break。总122s。**所有失败是NVCF平台pexec hang(50s×2+10s×2), 非HM2参数可解**——这与HM1-C的fast-fail收益证伪一致(R326 §2C: 第3+key本就5-10s短试, fast-fail省的有限)。

### 1g. 改前env (HM2 docker exec hm40006 env, 本轮改MIN_OUTBOUND)
| 参数 | HM2改前值 | 代码引用 | 备注 |
|---|---|---|---|
| UPSTREAM_TIMEOUT | 50 | upstream.py:235 | |
| **MIN_OUTBOUND_INTERVAL_S** | **4.5** | **config.py:125, upstream.py:288 (attempt_idx==0)** | **本轮改4.5→2.5** |
| KEY_COOLDOWN_S | 38 | config.py:141 | 429=0不触发 |
| TIER_COOLDOWN_S | 22 | ❌死参数(HM2无cooldown.py) | |
| TIER_TIMEOUT_BUDGET_S | 128 | upstream.py:215 | |
| HM_CONNECT_RESERVE_S | 21 | upstream.py:227 | |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | upstream.py:452 | R321生效 |
| HM_NV_PROXY_URL1~5 | 7894/空/空/空/7899 | ✅活 | |

## 2. CC清单HM2-A/B/C 复核

### [HM2-A] MIN_OUTBOUND_INTERVAL_S 4.5→2.5 — ✅ **本轮执行(推翻R325证伪)**
**R325证伪(被推翻)**: "3.35req/min<<13.3上限, throttle非瓶颈。降4.5→2.5不提吞吐。6h=0个429是宝贵稳定状态, 降throttle净风险无收益。"
**R325的数据漏洞**: 只看**平均到达率**(reqs/min vs理论上限), 漏了throttle_outbound()是**全局串行锁per-pair阻塞**(config.py:126 `with _outbound_throttle_lock: wait=INTERVAL-elapsed`)。即使平均速率远低于上限, 每对间隔<INTERVAL的相邻请求后者必wait。
**本轮决定性数据(§1d)**:
1. **120min实测47reqs(12.7%)间隔<4.5s被阻塞, total等待56.8s**; 60min 34reqs(12.3%)阻塞36.3s。平均速率5req/min<<13.3上限, 但仍有12.7%请求被per-pair串行锁阻塞——R325的"平均速率<<上限=非瓶颈"推理不成立。
2. **降到2.5的量化收益**: 120min仅7reqs间隔<2.5s被阻塞total 11.3s, 解锁40reqs省45.5s/120min; 60min省31.1s。被阻塞请求avg wait 1.07s(max 3.88s), 是真实延迟。
3. **6h零429, 降throttle不增NVCF限流**: throttle是HM2进程内串行锁(防止本进程内请求扎堆出站), 非NVCF服务端限流保护。NVCF 429是按API key/account配额, 与进程内throttle无关。降throttle不直接增NVCF同IP 429。且HM2流量2.7-5req/min, 降到2.5后只有间隔<2.5s的请求对(120min仅7个)仍串行, 远低于NVCF限流阈值。
4. **throttle仅attempt_idx==0触发**(upstream.py:288 `if attempt_idx==0: throttle_outbound()`), 每请求首次出站throttle一次, 重试attempt不过throttle。降INTERVAL不影响重试路径。
**结论**: HM2-A数据支撑执行, 4.5→2.5。

### [HM2-B] 失败模式补采+劣化key — ✅ R325已采, 本轮复查无劣化(§1e)
120min per-key: n均匀(68-74), dur_p95范围47404(k3)~63249(k4), ttfb_p95 47404~62717。5key全正常, **无可改项**。

### [HM2-C] TIER_TIMEOUT_BUDGET 128→100 — ❌ R325证伪持续成立
6h成功>100s=13个, >110s=7个, >120s=3个(max 122572ms)。任何BUDGET<123s误杀≥1个救回成功。R325证伪持续成立, 放弃。

## 3. 改动 (对端HM2, 单参数)

### 3a. 改动: MIN_OUTBOUND_INTERVAL_S 4.5→2.5 (-2.0s)
- **live compose** `/opt/cc-infra/docker-compose.yml` line 472 (project=cc-infra, **不在git仓库**, R322教训#2):
  ```yaml
  # 改前: MIN_OUTBOUND_INTERVAL_S: "4.5"  # R302: ...
  # 改后: MIN_OUTBOUND_INTERVAL_S: "2.5"  # R327: HM1→HM2 — 4.5→2.5 ... 推翻R325证伪...
  ```
- 备份: `/opt/cc-infra/docker-compose.yml.bak.R327_20260629_194743`
- **live compose不在git, 本次改动已部署生效但未入git**。仓库内仅有归档副本(deploy_artifacts/), 改归档副本对运行态无影响(R322教训#2)。CC托底时会同步。

### 3b. 部署: force-recreate
```bash
cd /opt/cc-infra && docker compose up -d --force-recreate hm40006
# Container hm40006 Recreated → Started
```

### 3c. 验证三重(实质数据流向)
| 验证项 | 结果 |
|---|---|
| 容器运行态env | `docker exec hm40006 printenv MIN_OUTBOUND_INTERVAL_S` = **2.5** ✅ |
| live compose | `sed -n 472p` = `MIN_OUTBOUND_INTERVAL_S: "2.5"` ✅ (两边同步, 非R322教训#1只改容器态) |
| /health | curl = **200** ✅ |
| 实测请求 | POST /v1/chat/completions glm5.1_hm_nv → HTTP=200, 714ms, content="OK" ✅ (新配置生效非旧) |

## 4. A/B验证 (改前vs改后窗口对比)

### 4a. 窗口选择与流量不对称说明
- **改前PRE窗口**: 03:35:00-03:48:00 UTC (13min, throttle=4.5)
- **改后POST窗口**: 03:48:00+00 起 ~12.5min (至04:00:30, throttle=2.5)
- **流量不对称(诚实标注)**: PRE avg_gap=16.0s(47reqs/13min), POST avg_gap=31.5s(27reqs/12.5min)。POST流量约为PRE一半(客户端到达率波动, 非throttle所致)。因此POST的"被阻塞数"天然偏低, 需看**阻塞率+机制**而非绝对数。

### 4b. A/B对比表
| 指标 | PRE(13min,4.5) | POST(12.5min,2.5) | 说明 |
|---|---|---|---|
| total reqs | 47 | 27 | POST流量低 |
| success | 46 | 26 | |
| fail(ATE) | 1 (122029ms) | 1 (122197ms) | 失败模式同(NVCF hang), 非throttle影响 |
| 成功率 | 97.87% | 96.30% | POST 1失败/27 vs PRE 1/47, 样本小, 差异不显著(都是NVCF hang) |
| 429 | 0 | 0 | **降throttle未增429** ✅ |
| empty200(真实) | 0 | 0 | POST的1个<3s是本轮test探测请求(content="OK", 2 tokens), 非真实empty200 |
| p50 duration | 7908ms | 13747ms | POST流量低→NVCF端更空闲应更快, 但p50反升——受样本小+1个ATE失败拉高p95影响, 非throttle(throttle只影响出站等待≤4.5s, 不影响NVCF pexec时长) |
| p95 duration | 47230ms | 97161ms | POST p95高, 因27reqs中有1个ATE(122s)拉高p95, 样本小(p95=第26/27个≈max)。非throttle |
| **avg_gap** | 16.0s | 31.5s | POST流量低 |
| **被阻塞(gap<4.5)** | 5 (10.6%) | 1 (3.7%) | PRE 5reqs被4.5锁阻塞total 3.5s; POST仅1被阻塞0.3s |
| **被阻塞(gap<2.5)** | 0 | 0 | 两边都0——降到2.5后无请求被2.5锁阻塞 |
| **throttle总等待** | 3.5s | 0.3s | POST降80% ✅ |

### 4c. A/B结论(机制层面, 控制流量不对称)
1. **throttle阻塞机制验证成功**: PRE(throttle=4.5)有5reqs因间隔<4.5s被串行锁阻塞total 3.5s; POST(throttle=2.5)仅1req间隔<4.5s(但>2.5)被阻塞0.3s, **0 reqs被2.5锁阻塞**。证明降到2.5后, 原本会被4.5锁阻塞的请求对(间隔2.5-4.5s区间)不再阻塞。
2. **429未增**: PRE 0, POST 0。降throttle不增NVCF限流(机制: throttle是进程内串行非NVCF端保护)。✅
3. **失败模式不变**: 两边各1 ATE(122s), 都是NVCF平台pexec hang(§1f), 与throttle无关。throttle只影响出站等待≤INTERVAL, 不影响NVCF pexec执行时长。
4. **p50/p95不可比**: POST流量低+样本小(27)+1 ATE拉高p95, duration指标受NVCF端拥塞主导(非throttle)。throttle对duration的贡献≤INTERVAL=4.5s/2.5s, 远小于NVCF pexec的8-122s波动, 被噪声淹没。**A/B的关键指标是throttle阻塞数/等待, 非duration**。
5. **流量不对称标注**: POST流量低(31.5s/req vs PRE 16.0s/req)使被阻塞绝对数天然偏低。但机制证明(§4c.1)成立: 降到2.5后间隔2.5-4.5s区间的请求对不再阻塞, 这是结构性减少, 非流量偶然。

**待观察(诚实标注)**: POST窗口仅12.5min/27reqs, 流量低。throttle=2.5在**高流量期**(avg_gap<2.5s, 即>24req/min)才会真正受压测。当前HM2流量2.7-5req/min, 2.5的余量充足。若后续轮次HM2流量回升到>20req/min, 需复查2.5下是否出现新的串行阻塞或429。

## 5. 结论

1. **HM2-A执行成功**: MIN_OUTBOUND_INTERVAL_S 4.5→2.5, 三重验证(env=2.5/compose=2.5/health=200/实测请求200)。
2. **推翻R325证伪**: R325只看平均速率漏了throttle全局串行锁per-pair阻塞(实测12.7%请求被阻塞)。本轮用请求间隔分布数据决定性证明throttle=4.5确实阻塞12.7%请求, 降到2.5结构性解除(间隔2.5-4.5s区间的请求对不再阻塞)。
3. **A/B机制验证**: PRE 5reqs阻塞3.5s→POST 1req阻塞0.3s(0被2.5锁阻塞), 429未增(0→0), 失败模式不变(ATE NVCF hang)。
4. **单参数**: 只改MIN_OUTBOUND_INTERVAL_S一个env, 未搭车(吸取R320教训#1一轮两改)。
5. **稳定优先**: 6h零429/零真实empty200, 降throttle不破坏零限流基线���失败全NVCF平台hang非HM2参数可解。

## 6. 待办 (留给下轮HM2→HM1)

- [ ] **下轮HM2→HM1**: R326已证伪HM1侧A/B/C(throttle=9.0已目标值且99%请求9s窗口独立, idx3 ttfb正常, fast-fail收益仅~10s误杀4个救回)。HM1极度稳定(120min 100%成功率, 6h零429/零empty200/零SSL)。HM1侧可复查流量回升期idx3是否真劣化(本轮低峰期正常)。
- [ ] **HM2 MIN_OUTBOUND=2.5高流量期复查**: 本轮POST流量低(31.5s/req), 2.5余量充足。若后续HM2流量回升到>20req/min(avg_gap<3s), 需复查2.5下是否出现新串行阻塞或429, 必要时回调3.0。
- [ ] **HM2失败全是NVCF平台hang(ATE 122s×47/6h)**: att1+att2各hang满UPSTREAM=50s, 非HM2参数可解。若NVCF平台层hang持续恶化, 需从NVCF账号/key层面考虑, 超出HM参数范围。
- [ ] **HM2侧TIER_COOLDOWN_S=22死参数**(无cooldown.py): env设但代码不引用, 429=0分支不触发, 无运行意义, 低优先。
- [ ] **HM2侧HM_SSLEOF_RETRY_ENABLED=true但代码不读**(两机代码都无条件retry): 死env, 低优先。

## ⏳ 轮到HM2优化HM1
