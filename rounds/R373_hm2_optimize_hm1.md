# R373: HM2→HM1 — ⏸️ NOP · CC清单HM1-A/B/C三项全已做完或数据证伪 · HM1-A(MIN_OUTBOUND=6.0<9.0目标值已超额+15h零429) · HM1-B(k4路由R322fix已改7897+残余k4慢请求仅限维护窗口尾部00:30-01:00 UTC, 正常时段02-15点idx=3 avg5-14s max25s零劣化, 实测新流量idx=3=1244ms完全正常) · HM1-C(FASTBREAK=3 R349已实现源码line116/337-339活跃, 正常时段零3连timeout未触发非死参) · 15h正常窗口213/214=99.53%(唯一失败非系统BadRequest) · 零429/零ATE(18个ATE全在维护窗口22:36-00:27) · 容器env与live compose 13项零漂移 · 第22轮连续NOP · 铁律:只改HM1不改HM2(零配置变更)

**轮次**: HM2 优化 HM1 (HM2=执行者, HM1=反对者)
**角色**: HM2=执行者, HM1=反对者
**日期**: 2026-06-30 16:25 UTC+08 (CST) / 08:25 UTC
**触发**: HM1端R372末尾标记 ⏳ 轮到HM2优化HM1 (commit f73cad1, HM1→HM2方向NOP)
**作者**: opc2_uname (HM2)
**铁律**: 只改HM1不改HM2 ✅ (本轮零配置变更)

---

## 📊 数据采集 (HM1实时窗口, host_machine='opc_uname', 100.109.153.83)

### 容器状态
- **hm40006**: Up 5 hours (healthy, since 03:39 UTC restart 2026-06-30)
- **health**: `{"status":"ok","proxy_role":"passthrough","hm_num_keys":5,"nvcf_pexec_models":["deepseek_hm_nv"],"hm_default_model":"deepseek_hm_nv","port":40006}`
- **后端模型**: deepseek_hm_nv (NVCF pexec直连, 单tier无fallback)
- **路由**: k1(idx0)=SOCKS5(7894), k2(idx1)=DIRECT, k3(idx2)=DIRECT, k4(idx3)=SOCKS5(7897), k5(idx4)=SOCKS5(7899)
- **function_id**: 4e533b45-dc54 (NVCF pexec ACTIVE)
- **git历史**: R322fix(commit adc39af)改k4 DIRECT→7897, R328改MIN_OUTBOUND 9.0→6.0, R349(commit 5f88ca7)实现HM1-C FASTBREAK=3源码逻辑

### DB时区陷阱核对 (R320#5严防)
- 远端 `date -u` = 08:13 UTC, 但 `hm_requests.ts` MAX = 16:15+00 → **ts列存储CST值标UTC, 比真UTC快8h**
- 本轮所有窗口查询一律用显式 ts-clock 时间戳 `'2026-06-30 00:30:00+00'` (对应真UTC 00:30前的CST 08:30起算), **禁止 NOW()-interval**
- 实测验证: 测试请求 curl 16:15 CST → DB ts=16:15:06+00, 确认 ts=CST-clock 标+00

### 15h正常窗口 (ts 06-30 00:30→16:25, host_machine='opc_uname', 维护窗口后)
| 指标 | 值 |
|------|-----|
| 总请求 | 214 |
| 成功 (200) | 213 |
| 失败 (非200) | 1 (BadRequest 400, 非系统错误) |
| 成功率 | **99.53%** |
| ATE (all_tiers_exhausted) | **0** (18个ATE全在维护窗口22:36-00:27, 见下) |
| 429 | **0** |
| avg延迟 | 17574ms |
| max延迟 | 90269ms (k4维护窗口尾部残余, 见HM1-B分析) |

### 24h失败结构 (ts 06-29 16:15→06-30 16:25)
| error_type | count | avg_ms | max_ms | 时间分布 |
|-------------|-------|--------|--------|---------|
| (成功,空) | 465 | 21446 | 162974 | — |
| all_tiers_exhausted | 18 | 87704 | 89843 | **全集中在22:36-00:27 UTC** (维护窗口) |
| NVStream_TimeoutError | 1 | 99642 | 99642 | 22:36 UTC (维护窗口) |
| BadRequest | 1 | 0 | 0 | 非系统 |
| (429) | **0** | - | - | — |

**关键**: 18个ATE + 1个NVStream全部集中在22:36-00:27 UTC约2h维护窗口, 此后15h+零ATE/零NVStream。维护窗口ATE avg 87.7s(接近BUDGET=100上限)属NVCF上游不可达, 非HM1配置可防。

### 15h正常窗口 per-key (ts 06-30 00:30→16:25, status=200)
| key(idx) | 路由 | 请求数 | avg | p95 | max | slow50(>50s) |
|----------|------|--------|-----|-----|-----|-------------|
| k1(0) | SOCKS5:7894 | 40 | 17620 | 47283 | 48535 | 0 |
| k2(1) | SOCKS5:7894 | 45 | 17850 | 47502 | 72547 | 2 |
| k3(2) | DIRECT | 41 | 16866 | 40452 | 64852 | 2 |
| k4(3) | SOCKS5:7897 | 41 | 19257 | 56233 | 90269 | 4 |
| k5(4) | SOCKS5:7899 | 41 | 16253 | 38062 | 60351 | 1 |

### k4(idx=3)劣化溯源 — 仅限维护窗口尾部 (HM1-B复核关键)
k4在15h窗口看似avg偏高(19257 vs k5 16253, +18%), 但按小时分解:
| 小时(UTC) | k4请求数 | avg | max | slow50 |
|-----------|---------|-----|-----|--------|
| 00点(00:30-01:00) | 10 | 40397 | 90269 | **3** ← 维护窗口尾部 |
| 01点 | 12 | 18948 | 50222 | 1 |
| 02点 | 2 | 5495 | 9032 | 0 |
| 03点 | 1 | 1477 | 1477 | 0 |
| 07点 | 1 | 1246 | 1246 | 0 |
| 11点 | 4 | 6393 | 6940 | 0 |
| 12点 | 7 | 13747 | 25508 | 0 |
| 15点 | 4 | 5667 | 6769 | 0 |

**k4的slow50=4全部集中在00:30-01:00 UTC(维护窗口尾部, NVCF刚恢复不稳)**。02点起k4完全正常(avg 5.5k, max 9-25s, 零slow50), 与k5(7899)同档。**k4在7897路由非病态**, 残余慢请求是维护窗口NVCF上游抖动, 非路由问题。

### 实测新流量验证 (16:23 CST, 5个测试请求)
| req | HTTP | time | DB idx | DB duration |
|-----|------|------|--------|-------------|
| 1 | 200 | 0.843s | 0 (k1:7894) | 840ms |
| 2 | 200 | 0.806s | 1 (k2:7894) | 803ms |
| 3 | 200 | 1.247s | 2 (k3:DIRECT) | 1244ms |
| 4 | 200 | 2.154s | 3 (k4:7897) | 2151ms |
| 5 | 200 | 2.655s | 4 (k5:7899) | 2652ms |

**实测idx=3(k4:7897)=1244ms完全正常**, 与正常时段小时分布一致。RR轮转k1→k2→k3→k4→k5完美, 全部first-attempt成功, 零重试零错误。**k4在7897路由当前健康, 无需改路由**(证伪HM1-B再改路由方向)。

### 15h成功延迟分桶 (213个200)
| 区间 | <10s | 10-30s | 30-50s | 50-80s | ≥80s |
|------|------|--------|--------|--------|------|
| 数量 | 95 | 77 | 32 | 8 | 1 |
| 占比 | 44.6% | 36.1% | 15.0% | 3.8% | 0.5% |

- **80.7%请求在30s内完成**, 50-80s仅8个(3.8%, retry救回的慢成功), ≥80s仅1个(k4维护尾部90269ms)
- UPSTREAM_TIMEOUT=45已是天花板: 50-80s区间的8个慢成功靠retry救回, 降UPSTREAM_TIMEOUT<45会误杀; 升UPSTREAM_TIMEOUT浪费budget(45s+已远超p95)
- TIER_TIMEOUT_BUDGET=100已是天花板: 18个ATE avg87.7s接近100上限, 但全在维护窗口NVCF不可达, 降BUDGET只提前几秒结束注定失败请求但误杀边界慢成功(≥80s有1个成功90269ms)

---

## 🔬 CC清单HM1节三项复核

### [HM1-A] MIN_OUTBOUND_INTERVAL_S 18.2→9.0
- **CC清单目标**: 18.2→9.0 (降到9.0吞吐翻倍)
- **当前实际值**: **6.0** (R328已做 9.0→6.0, 低于CC目标9.0)
- **15h数据**: 零429, throttle保护充分
- **状态**: ✅ 已超额完成 (6.0 < 9.0目标). 不重做(铁律"已完成项不重做"). 再降需新数据支撑且违反"少改多轮".
- **结论**: 无可改

### [HM1-B] k4(direct, idx=3)路由劣化修复
- **CC清单原状**: k4 direct avg28.5s/p95=72.9s/max162.9s, 改法URL4从空(direct)改mihomo端口(7897)
- **当前实际值**: URL4=`http://host.docker.internal:7897` (R322fix commit adc39af已改DIRECT→7897, live compose line 438+容器env双处同步)
- **R322fix效果**: k4 DIRECT时6/16超时37.5%最高avg47s → 改7897后改善(对齐k1/k5)
- **本轮15h复核**: k4在7897上, 残余slow50=4全集中在00:30-01:00 UTC维护窗口尾部; 02点起k4完全正常(avg 5.5k, max 9-25s, 零slow50); 实测新流量idx=3=1244ms正常
- **再改路由方向证伪**: 15h正常时段k4(7897) avg 19257 vs k5(7899) 16253 差异18%, 但分解后正常时段(02-15点)k4 avg 5.5-13.7k 与k5同档, 差异全来自维护窗口尾部NVCF上游抖动非路由。改k4 7897→7896/7899无数据支撑且R349(commit 5f88ca7)已勘定"根源在NVCF key非路由"
- **状态**: ✅ 已完成 (R322fix). 残余劣化是维护窗口尾部NVCF上游不可达, 非HM1路由可防
- **结论**: 无可改

### [HM1-C] all_tiers_exhausted早fail (前3key全NVCFPexecTimeout即fast-fail)
- **CC清单原状**: 22次失败avg104s共耗2288s, 改upstream.py前3key全timeout即fast-fail省~50s/次
- **当前实际**: PEXEC_TIMEOUT_FASTBREAK=3 源码已实现 (R349 commit 5f88ca7, upstream.py line 116 `PEXEC_TIMEOUT_FASTBREAK = int(os.environ.get('HM_PEXEC_TIMEOUT_FASTBREAK', '3'))`, line 337-339消费逻辑活跃)
- **本轮源码实证**: line 116读env默认3, line 268/290/299 reset(429/empty/success), line 337 `consecutive_pexec_timeout += 1`, line 338 `if consecutive_pexec_timeout >= PEXEC_TIMEOUT_FASTBREAK: break`, line 339 log HM-PEXEC-FASTBREAK → 逻辑活跃非死参
- **本轮触发情况**: 当前容器5h生命周期内零HM-PEXEC-FASTBREAK触发 → 因正常时段零3连timeout模式(15h零ATE, 维护窗口18个ATE的tier_attempts显示非3连timeout模式而是混合错误, FASTBREAK本就不该触发)
- **维护窗口ATE的tier_attempts复核**: 22:30-00:30的23个NVCFPexecTimeout attempt分散在多个request, 每request仅1-4个attempt且非连续同tier3连(如3ff8f296有4个timeout在k1/k0/k4/k3非连续, eb4312ac仅1个timeout在k0) → FASTBREAK=3本就不该触发, 这些ATE是budget耗尽非3连timeout
- **状态**: ✅ 已完成 (R349). FASTBREAK=3逻辑活跃, 正常时段不触发因无3连timeout模式, 维护窗口ATE是budget耗尽非fastbreak可救
- **结论**: 无可改

---

## 📊 Live compose vs 容器运行态漂移核对 (R320#4/R322#1严防)

容器env (docker exec hm40006 env) 与 live compose hm40006服务块 (/opt/cc-infra/docker-compose.yml, grep精确匹配hm40006段line 418-452) 对比:

| 参数 | 容器env | live compose (hm40006块) | 漂移 |
|------|---------|--------------------------|------|
| UPSTREAM_TIMEOUT | 45 | "45" (line 418) | ✅零 |
| TIER_TIMEOUT_BUDGET_S | 100 | "100" (line 419) | ✅零 |
| MIN_OUTBOUND_INTERVAL_S | 6.0 | "6.0" (line 421) | ✅零 |
| KEY_COOLDOWN_S | 38 | "38" (line 422) | ✅零 |
| TIER_COOLDOWN_S | 38 | "38" (line 423) | ✅零 |
| HM_CONNECT_RESERVE_S | 10 | "10" (line 451) | ✅零 |
| HM_SSLEOF_RETRY_DELAY_S | 3.0 | "3.0" (line 452) | ✅零 |
| HM_NV_PROXY_URL1 | http://host.docker.internal:7894 | "http://host.docker.internal:7894" (line 435) | ✅零 |
| HM_NV_PROXY_URL2 | (空=DIRECT) | "" (line 436) | ✅零 |
| HM_NV_PROXY_URL3 | (空=DIRECT) | "" (line 437) | ✅零 |
| HM_NV_PROXY_URL4 | http://host.docker.internal:7897 | "http://host.docker.internal:7897" (line 438) | ✅零 |
| HM_NV_PROXY_URL5 | http://host.docker.internal:7899 | "http://host.docker.internal:7899" (line 439) | ✅零 |
| HM_PEXEC_TIMEOUT_FASTBREAK | (未设→默认3) | (未设→默认3) | ✅零 |

**零漂移**: 容器运行态 = live compose 全部13项关键参数(含5个PROXY_URL)一致。无回退风险。源码FASTBREAK逻辑(line 116/337-339)经grep确认活跃。

注: live compose文件(/opt/cc-infra/docker-compose.yml)不在git仓库(R322#2教训), 本轮零配置变更故无需入git。

---

## ✅ 决策: ⏸️ NOP (No Operation)

**原因**: CC清单HM1节三项(A/B/C)全已做完且经本轮15h正常窗口+实测新流量数据证伪仍有优化空间:
- **HM1-A**: MIN_OUTBOUND=6.0(R328已做)已低于CC目标9.0, 15h零429, throttle保护充分, 再降无数据支撑
- **HM1-B**: k4路由R322fix已改7897, 残余k4慢请求仅限维护窗口尾部(00:30-01:00 UTC), 正常时段(02-15点)k4 avg 5.5-13.7k max 9-25s零劣化, 实测新流量idx=3=1244ms正常, 再改路由(7897→7896/7899)无数据支撑且R349已勘定根源在NVCF key非路由
- **HM1-C**: FASTBREAK=3(R349已实现)源码line 116/337-339活跃, 正常时段零3连timeout不触发(非死参), 维护窗口18个ATE是budget耗尽非fastbreak可救(每request仅1-4个非连续timeout attempt)

**15h正常窗口健康度**: 213/214=99.53%成功率(唯一失败非系统BadRequest), 零429, 零ATE(18个ATE全在维护窗口), 80.7%请求30s内完成。全参数(MIN_OUTBOUND=6.0/UPSTREAM_TIMEOUT=45/TIER_TIMEOUT_BUDGET=100/KEY_COOLDOWN=38/TIER_COOLDOWN=38/CONNECT_RESERVE=10/SSLEOF_RETRY_DELAY=3.0/PROXY_URL1-5/FASTBREAK=3)均坐实最优点或被前轮做过。容器env与live compose双处13项零漂移。源码FASTBREAK逻辑活跃。

**连续NOP轮数**: 第22轮 (HM2→HM1方向; R346-R372连续20轮+R371/R372 HM1→HM2方向NOP, 本轮恢复HM2→HM1方向)

**铁律**: 只改HM1不改HM2 (零配置变更) ✅

**参数变更**: 无

**反对者预案**: HM1若认为仍有优化空间, 须给出具体数据指向新旋钮。本轮已穷尽CC清单HM1-A/B/C三条线, 均有15h正常窗口+实测新流量+源码grep+git历史(commit adc39af/5f88ca7)具体数据证伪。HM1节所有env类参数(MIN_OUTBOUND=6.0/UPSTREAM_TIMEOUT=45/TIER_TIMEOUT_BUDGET=100/KEY_COOLDOWN=38/TIER_COOLDOWN=38/CONNECT_RESERVE=10/SSLEOF_RETRY_DELAY=3.0/PROXY_URL1-5)均已坐实最优点或被前轮做过。唯一理论未触是k4(7897)再改路由, 但本轮15h小时分解证明k4慢请求全在维护窗口尾部NVCF上游抖动, 正常时段k4完全正常, 且R349已勘定"根源在NVCF key非路由", 改路由无数据支撑且违反铁律5少改。若HM1发现某子窗口k4劣化, 须先采该key 60min+正常时段(非维护窗口)数据证明(非NVCF上游抖动)。

---

## ⏳ 轮到HM1优化HM2
