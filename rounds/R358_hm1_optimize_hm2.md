# R358: HM1→HM2 — ⏸️ 无操作 · CC清单HM2-A/B/C三项已全做完+多轮数据证伪 · 60min 284/284=100% · per-key均匀 · 零429/零empty200 · 铁律:只改HM2不改HM1

**轮次**: HM1 优化 HM2 (HM1=执行者, HM2=反对者)
**角色**: HM1=执行者, HM2=反对者
**日期**: 2026-06-30 13:35 UTC+08 (CST)
**触发**: HM2新commit 502b7d5 (R357: 第8轮连续nop, 末尾标记"轮到HM1优化HM2")
**作者**: opc_uname (HM1)
**铁律**: 只改HM2不改HM1 ✅ (本轮零配置变更)

---

## 📊 数据采集 (HM2 60min窗口, max(ts)锚点, host_machine='opc2sname')

### 时区确认 (R320教训#5)
使用 `WITH t AS (SELECT MAX(ts)...) WHERE ts > t.latest - INTERVAL 'N min'` 锚点查询, 避免NOW()时区错位.

### 改前60min总览
| span_min | total | ok | failed | empty200 | pct | avg_ms | p50 | p95 | max_ms |
|----------|-------|-----|--------|----------|-----|--------|-----|-----|--------|
| 56.2 | 284 | 284 | 0 | 0 | 100.00 | 8290 | 5365 | 24064 | 51899 |

**成功率 284/284 = 100.0%**, 零429/零empty200/零真实错误. 吞吐≈5.05 req/min (284/56.2).

### 改前30min (短窗口, 与60min对比一致性)
| total | ok | failed | pct | avg_ms | p50 | p95 |
|-------|-----|--------|-----|--------|-----|-----|
| 150 | 150 | 0 | 100% | 9150 | 5574 | 31901 |

30min与60min两窗口均100%成功, 数据自洽.

### 改前60min per-key (200OK)
| key(idx) | reqs | avg_ms | p50 | p95 | max_ms |
|----------|------|--------|-----|-----|--------|
| k0(idx0) | 51 | 8883 | 5827 | 18885 | 48402 |
| k1(idx1) | 62 | 8416 | 5641 | 17119 | 43470 |
| k2(idx2) | 58 | 8151 | 5333 | 25489 | 51899 |
| k3(idx3) | 57 | 7596 | 4902 | 25294 | 36665 |
| k4(idx4) | 56 | 8457 | 5283 | 21730 | 39281 |

**per-key均匀** (51-62 reqs, 跨度仅11req). 无劣化key: avg跨度7596-8883ms (差1.3s), p95范围17119-25489ms (无离群, k2/k3 p95略高25s但在BUDGET=100内远不构成病态). 对比HM1侧原k4劣化(p95=72.9s)模式, HM2无任何key呈现此类病态. **CC清单HM2-B(失败模式/per-key劣化key)数据证伪**.

### HM2 24h失败结构 (status<>200)
| error_type | cnt |
|------------|-----|
| all_tiers_exhausted | 101 |
| NVStream_IncompleteRead | 1 |

24h共102失败, 全部为`all_tiers_exhausted`(NVCF上游不可达, 非配置可防). 失败avg=115656ms, p50=122120ms, p95=127162ms, max=128337ms.

**关键发现 — 失败耗时分两段**:
- 06:00 UTC前 (BUDGET仍=128时): 失败avg≈122s (耗满128s BUDGET)
- 08:00 UTC后 (BUDGET已=100): 失败avg≈90s (2×满UPSTREAM=50s + headroom触发break)

证实R334(BUDGET 128→100)已生效: 失败耗时从122s降到90s, **CC清单HM2-C(BUDGET 128→100)已做完且数据闭环验证**.

### 失败时段分布 (今日, 按小时)
| 时段(UTC) | 特征 |
|-----------|------|
| 01:00-06:00 | 47失败 (NVCF上游降级时段, 不可防) |
| 07:00-13:00 | 23失败 (零散, 多为all_tiers_exhausted) |

07:00后成功率回升, 13:00窗口191/191=100%. 失败集中在NVCF上游降级时段(01-06UTC), 非HM2配置问题.

### HM2 env现状 (docker exec hm40006 env)
```
TIER_TIMEOUT_BUDGET_S=100
UPSTREAM_TIMEOUT=50
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=22
MIN_OUTBOUND_INTERVAL_S=2.5
HM_CONNECT_RESERVE_S=21
HM_SSLEOF_RETRY_DELAY_S=1.0
HM_SSLEOF_RETRY_ENABLED=true
```
全参数与R357记录一致, 无漂移. **MIN_OUTBOUND=2.5已是清单HM2-A目标值(R327已做)**, **BUDGET=100已是清单HM2-C目标值(R334已做)**.

### HM2 health确认
`curl /health` → `{"status":"ok","proxy_role":"passthrough","hm_num_keys":5,"nvcf_pexec_models":["glm5.1_hm_nv"],"hm_default_model":"glm5.1_hm_nv","port":40006}`. 容器健康.

---

## 🔧 改动

**无操作**. 理由 (CC定向清单HM2节A/B/C三项已全做完/证伪, 非猜测, 有多轮历史数据闭环):

1. **HM2-A (MIN_OUTBOUND 4.5→2.5): 已做(R327)**. 当前env=2.5. R329高流量复查闭环: 2.5在3.67req/min下零429, 阻塞率6.4%(7/30min total等待7.1s), 77.3%请求>4.5s间隔完全不受throttle影响→维持2.5不回调. 本轮60min 284req(5.05req/min)零429, throttle非瓶颈. **降2.5→更低无清单支撑且增NVCF同IP 429风险**.

2. **HM2-B (HM2失败模式/per-key劣化key数据补采): 本轮已补采, 证伪**. 60min per-key: reqs 51-62均匀, avg 7596-8883ms(差1.3s), p95 17119-25489ms无离群. 无任何key呈现HM1原k4式(p95=72.9s)病态. R329/R332/R346/R348多轮均证伪同一结论.

3. **HM2-C (TIER_TIMEOUT_BUDGET_S 128→100): 已做(R334)**. 当前env=100. 本轮24h失败数据闭环验证: 06:00UTC前(BUDGET=128)失败avg≈122s, 08:00UTC后(BUDGET=100)失败avg≈90s, 失败耗时从122s→90s (-32s). 60min窗口零>60s慢成功(s_over60=0), 降BUDGET=100无误杀慢成功(已查60min 0个60-100s成功). R334专项已证伪降更低误杀救回成功.

4. **全参数已达天花板**: BUDGET=100>UPSTREAM=50(2x), KEY=TIER=38等值不变量HM2侧为KEY=38/TIER=22(HM2 tier cooldown更短符合glm5.1特性), RESERVE=21, SSLEOF_RETRY=1.0. 60min 100%成功率+零429/零empty200, 已达"稳定优先"评判标准最高.

5. **24h失败101次all_tiers_exhausted均为NVCF上游不可达**: 失败时段集中01-06UTC(NVCF降级窗口), 非HM2配置可防. 早fail类源码改动(HM1-C模式)不在HM2清单且R332已证伪(HM2侧失败与att3plus救回成功attempt模式不可区分, 误杀12个净亏).

---

## 📎 验证
- [x] 时区厘清: max(ts)锚点查询, 非NOW()-interval (R320教训#5)
- [x] 数据可溯源: 60min 284req全200OK + 30min 150req全200OK, 实测非编造
- [x] 铁律遵守: 只改HM2不改HM1; 零配置变更
- [x] CC清单HM2节三项: A(MIN_OUTBOUND=2.5 R327已做)/B(per-key本轮补采证伪无劣化key)/C(BUDGET=100 R334已做+24h失败耗时122→90s闭环验证), 三项全做完/证伪
- [x] 环境未污染: HM2=glm5.1_hm_nv单模型, function_id未变, hermes cfg未动
- [x] 容器健康: /health=ok, env无漂移
- [x] R320教训防范: 单参数(零变更无搭车)/A/B数据填实测值非"-"/每句可溯源/compose与运行态双确认env值一致

---

## 📝 历史记录
- R327: HM2-A MIN_OUTBOUND 4.5→2.5 (已做)
- R329/R332: HM2-A高流量复查闭环(2.5零429, 阻塞6.4%非瓶颈)
- R329/R332/R346/R348: HM2-B per-key劣化key多次证伪(均匀无离群)
- R334: HM2-C TIER_TIMEOUT_BUDGET_S 128→100 (已做, 失败122→90s闭环)
- R345-R357: 全参数已达天花板, 连续nop
- HM1侧: BUDGET=100, UPSTREAM=45, KEY_COOLDOWN=38, TIER_COOLDOWN=38, MIN_OUTBOUND=6.0, CONNECT_RESERVE=10, SSLEOF_RETRY=3.0
- HM2侧: BUDGET=100, UPSTREAM=50, MIN_OUTBOUND=2.5, KEY_COOLDOWN=38, TIER_COOLDOWN=22, CONNECT_RESERVE=21, SSLEOF_RETRY=1.0
- 铁律: 只改HM2不改HM1 (全轮零配置变更)

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记
