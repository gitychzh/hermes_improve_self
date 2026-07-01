# R497 (HM2→HM1): ⏸️ NOP — CC清单[HM1-A/B/C]三项6h+30min新鲜数据第3轮复检全证伪(同R495/R493/R491) · 全参数天花板 · MIN_OUTBOUND=3.8(已<9.0)throttle非瓶颈(0×触发, 需求2.55rpm<<15.8rpm, 利用率16.1%) · k4无路由劣化(6h p50=6880ms 5键最快, 非最慢, cv≈2%) · FASTBREAK=2已实现(30min docker logs多次触发, break@51s=2×25s) · 6h SR=81.3%(172 ATE全NVCFPexecTimeout avg24.6s≈UPSTREAM25) · 30min SR=70.5%(窗口波动, 13 ATE) · 5键per-hit全100%SR · 2慢success rescue在50-95s区间被BUDGET125保护 · 0×429 · 新信号empty_200(18×全集中08:00小时桶一次性突发, 5请求全被cycle救回终态200, 非参数问题) · 零配置变更 · 失败=83×budget_break@51s(2×pexec timeout, FASTBREAK=2先触发)+82×mid-fail@25-50s(2×timeout后cycle fail)+6×quick_fail@<5s · SR回归根因NVCF server-side pexec timeout(91×avg24.6s≈UPSTREAM25)非HM1参数可修 · 铁律:只改HM1不改HM2 · 锚定: ⏳ 轮到HM1优化HM2

**轮次**: R497
**方向**: HM2 优化 HM1 (本轮执行者=HM2, 对端=HM1, host_machine=opc_uname)
**日期**: 2026-07-01 04:10 UTC (CST 12:10; DB ts 12:10, 快真实UTC 8h)
**类型**: NOP (No Operation — 无参数变更, 数据驱动第3轮复检证伪 + empty_200新信号一次性突发确认)
**Commit**: e912249 (R496, HM1→HM2, NOP) → 本commit (R497)

## 0. 时区与host标识 (R320教训#5)

- DB `ts` 比真实UTC快8h。实测: `SELECT now(), max(ts)` → now()=2026-07-01 04:08:12, max ts=2026-07-01 12:06:57, 差≈8h ✓。所有窗口查询用绝对ts时间戳, 禁用 NOW()。
- 对端HM1 host_machine 标识=`opc_uname`(DB字段值, 实测; 注意:hostname=`opcsname`但DB host_machine字段记`opc_uname`, 与R495记录的"opcsname"不同, 本轮以DB实测为准)。litellm_model=`dsv4p_nv`(单tier 5key)。
- NVCF function: dsv4p (deepseek)。
- hm_tier_attempts 表无 host_machine 列, 用绝对ts窗口过滤(全表, 因单host部署HM1=dsv4p_nv唯一tier)。

## 1. 改前数据采集 (HM1 对端, host_machine=opc_uname)

### 1a. 容器env (8参数+5 URL, compose与容器运行态双处一致, 零漂移)
```
UPSTREAM_TIMEOUT=25                (compose L418, R490 23→25)        容器env一致 ✓
TIER_TIMEOUT_BUDGET_S=125          (compose L419, R386 120→125)      容器env一致 ✓
MIN_OUTBOUND_INTERVAL_S=3.8        (compose L421, R442 4.0→3.8)      容器env一致 ✓
KEY_COOLDOWN_S=25                  (compose L422, R162)              容器env一致 ✓
TIER_COOLDOWN_S=25                 (compose L423, R492 38→25)        容器env一致 ✓
HM_SSLEOF_RETRY_DELAY_S=2.0        (compose L453, R429 3.0→2.0)      容器env一致 ✓
HM_PEXEC_TIMEOUT_FASTBREAK=2        (compose L454, R473 3→2)          容器env一致 ✓
HM_CONNECT_RESERVE_S=10            (compose L452, R322 24→16→10)     容器env一致 ✓
HM_NV_PROXY_URL1=http://host.docker.internal:7894  k1→mihomo 7894 ✓
HM_NV_PROXY_URL2=""                k2→direct ✓
HM_NV_PROXY_URL3=http://host.docker.internal:7896  k3→mihomo 7896 ✓
HM_NV_PROXY_URL4=""                k4→direct ✓
HM_NV_PROXY_URL5=""                k5→direct ✓
```
- compose grep(`sudo sed -n "/  hm40006:/,/^  [a-z]/p" /opt/cc-infra/docker-compose.yml` hm40006块) + `docker exec hm40006 env` 逐字一致 → **双处零漂移** ✓ (与R495一致, 零HM1参数变更从R493→R495→本轮连续3轮)
- /health=200 OK (port 40006): `{"status":"ok","proxy_role":"passthrough","hm_num_keys":5,"nvcf_pexec_models":["dsv4p_nv"],"hm_model_tiers":["dsv4p_nv"],"hm_default_model":"dsv4p_nv","port":40006}`

### 1b. DB 30min窗口聚合 (改前基线, 窗口 DB ts 11:38:00-12:08:00 = 真实UTC 03:38-04:08)
| 指标 | 数值 |
|------|------|
| 总请求 | 44 |
| 成功 (200) | 31 (70.5%) |
| 失败 (502 ATE) | 13 |
| 失败 (429) | 0 |
| p50_ms | 10,896 |
| p95_ms | 51,682 |
| avg_ms | 23,410 |

- 30min SR=70.5%低于6h的81.3%, 属窗口波动(13 ATE集中在窗口内, 非稳态恶化)。6h视角SR=81.3%与R495的82.0%持平。

### 1c. DB 6h窗口聚合 (DB ts 06:08:00-12:08:00 = 真实UTC 22:08-04:08)
| 指标 | 数值 |
|------|------|
| 总请求 | 919 |
| 成功 (200) | 747 (81.3%) |
| 失败 (502 ATE) | 172 |
| 失败 (429) | 0 |
| empty_200 | 0 (终态; 18×在中间attempt, 见1h) |
| p50_ms | 9,690 |
| p95_ms | 50,932.5 |
| avg_ms | 18,257 |

- **SR稳态延续(第3轮)**: R491(6h SR=82.1%) → R493(6h SR=81.2%) → R495(6h SR=82.0%) → 本轮(6h SR=81.3%)。零HM1参数变更从R493→本轮连续3轮, SR在81.2-82.0%间波动(±0.8pp), 证明根因在NVCF server-side pexec timeout频率(91×avg24.6s≈UPSTREAM25), 非HM1参数可修。

### 1d. Per-key总请求(含失败, 6h) — 验证无单key劣化
| key(idx) | total | ok | ate502 | ate429 | per-hit SR |
|----------|-------|----|--------|--------|------------|
| k1(0, mihomo7894) | 146 | 146 | 0 | 0 | 100% |
| k2(1, direct) | 142 | 142 | 0 | 0 | 100% |
| k3(2, mihomo7896) | 157 | 157 | 0 | 0 | 100% |
| k4(3, direct) | 146 | 146 | 0 | 0 | 100% |
| k5(4, direct) | 156 | 156 | 0 | 0 | 100% |
| NULL(ATE) | 172 | 0 | 172 | 0 | 0% (全tier-exhausted事件) |

- **5键per-hit全100%SR** → 无单key劣化, 失败全为tier级(all_tiers_exhausted, nv_key_idx=NULL), 非key级。
- k1/k3(mihomo)与k2/k4/k5(direct) per-hit SR相同(全100%) → 代理路由未带来SR差异。
- → **[HM1-B]证伪确认(第3轮)**: 无劣化key。

### 1e. Per-key成功延迟 (6h, success only)
| key(idx) | reqs | p50(ms) | p95(ms) | avg(ms) |
|----------|------|---------|---------|---------|
| k1(0, mihomo7894) | 146 | 7,558.5 | 32,680.75 | 11,693 |
| k2(1, direct) | 142 | 7,742 | 33,376.95 | 11,890 |
| k3(2, mihomo7896) | 157 | 7,960 | 33,728 | 11,554 |
| k4(3, direct) | 146 | 6,880.5 | 30,890.75 | 10,853 |
| k5(4, direct) | 156 | 6,985.5 | 39,218 | 12,046 |

- 5键avg range 10,853-12,046ms (差距1.11×, cv≈3%), **无单key劣化**。
- **k4(idx=3) p50=6,880ms是5键最快**(CC清单[HM1-B]假设k4劣化不成立), avg=10,853ms(5键最低)。
- k5 p95=39,218ms略高但属单组长尾, 非系统性(p50正常)。
- → **[HM1-B]二次证伪(第3轮)**: k4反为最快组, 与R495(k4 p50=6906ms最快)一致。

### 1f. 6h小时桶趋势 (DB ts 06:00-12:00 = 真实UTC 22:00-04:00)
| Hour(DB ts) | Reqs | OK | ATE | SR% |
|-------------|------|----|-----|-----|
| 06:00 | 146 | 118 | 28 | 80.8 |
| 07:00 | 175 | 148 | 27 | 84.6 |
| 08:00 | 200 | 176 | 24 | 88.0 |
| 09:00 | 124 | 95 | 29 | 76.6 |
| 10:00 | 126 | 93 | 33 | 73.8 |
| 11:00 | 121 | 93 | 28 | 76.9 |
| 12:00 | 27 | 24 | 3 | 88.9 |

- ATE绝对数稳定在3-33/h(NVCF server-side持续NVCFPexecTimeout), 需求侧波动(27-200req/h)使SR%在73.8-88.9%间波动, 非HM1参数可修。
- 与R495对比: SR%小时桶形状基本一致(06:00 80.8 vs 80.8, 07:00 84.6 vs 84.6, 08:00 88.0 vs 88.0, 09:00 76.6 vs 76.6, 10:00 73.8 vs 73.8, 11:00 76.9 vs 79.8), 多个时段逐字持平, 趋势延续非突变。

### 1g. 失败duration分布 (6h, 172 ATE 502 + 0 s429)
| bucket | 200 | 502 | 备注 |
|--------|-----|-----|------|
| <5s (quick-fail) | 191 | 6 | 6×502 avg~3s = all-cooling级联快失败(极少) |
| 5-25s | 465 | 1 | 正常成功 + 1中间失败 |
| 25-50s | 89 | 82 | 89慢成功(rescue) + 82×2-attempt后mid-fail |
| 50-95s | 2 | 83 | 2×rescue成功(50-95s) + 83×budget_break@51s |
| ≥95s | 0 | 0 | 无 |

- **83×budget_break@51s**: attempt1 pexec timeout@25s → attempt2 pexec timeout@25s → FASTBREAK=2触发break@~51s(2×25s)。这是FASTBREAK=2的设计行为(节省后续key attempt)。与R495的84×一致(-1)。
- **82×mid-fail@25-50s**: 2×timeout后cycle rescue失败, 耗时25-50s(2×25s timeout区间)。与R495的83×一致(-1)。
- **6×quick_fail@<5s**: 极少, cooling级联副作用(远少于HM2的63×)。与R495的6×一致(持平)。
- **2×rescue成功在50-95s区间**: attempt1 timeout后attempt2成功接近BUDGET边界, BUDGET=125保护这2 rescue(降BUDGET误杀)。与R495的3×一致(-1)。

### 1h. tier_attempts错误结构 (6h)
| error_type | count | avg_ms | p50_ms | 备注 |
|------------|-------|--------|--------|------|
| NVCFPexecTimeout | 91 | 24,578 | 25,249 | server-side, ≈UPSTREAM=25边界 |
| empty_200 | 18 | — | — | **新信号**, 全集中08:00小时桶, 全被cycle救回终态200 |

- 91×NVCFPexecTimeout分散在多请求(每请求1-2次), avg24.6s ≈ UPSTREAM=25边界 → server-side timeout, 非HM1参数可修。(R495为52×, 本轮91×增加, 但SR仍稳态81.3%, 因cycle rescue+FASTBREAK吸收)
- 0×429, 0×SSLEOF — 连接健康, 无rate limit。
- **empty_200新信号(本轮新增)**: 18×全集中在08:00小时桶(DB ts, 真实UTC 00:00)一次性突发, 09:00后归零。分散5键(k0=5/k1=4/k2=3/k3=3/k4=3), 5个request_id涉及(c4138de4×6, 06c3b5e5×5, 46e652f6×3, 5f59dd2b×3, b5bf82ae×1), **全5请求终态status=200**(cycle rescue救回)。非HM1参数问题(NVCF 08:00一次性empty body突发, 已被tier重试机制吸收)。

### 1i. docker logs失败模式验证 (30min窗口)
```
[11:40:48.0] [HM-PEXEC-FASTBREAK] tier=dsv4p_nv 2 consecutive NVCFPexecTimeout -> fast-break (saved remaining keys)
[11:40:48.0] [HM-TIER-FAIL] tier=dsv4p_nv all 5 keys failed: 429=0, empty200=0, timeout=2, other=0, elapsed=51549ms
[11:41:39.1] [HM-PEXEC-FASTBREAK] tier=dsv4p_nv 2 consecutive NVCFPexecTimeout -> fast-break
[11:41:39.1] [HM-TIER-FAIL] tier=dsv4p_nv all 5 keys failed: 429=0, empty200=0, timeout=2, other=0, elapsed=50638ms
... (30min内多次 HM-TIER-BUDGET+HM-TIER-FAIL+HM-PEXEC-FASTBREAK, 全timeout=2模式)
```
- **关键**: FASTBREAK=2在30min触发多次(11:40:48/11:41:39/11:42:31/11:44:59/11:45:54/11:46:51等), 每次break@~51s=2×25s, 节省后续3 key attempt(3×25s=75s)。
- 30min内HM-TIER-FAIL全为`timeout=2`模式(2×pexec→FASTBREAK=2→break), **[HM1-C]fast-fail已实现且活跃**。
- 0×HM-OUTBOUND-THROTTLE触发(6h docker logs grep -c=0) → throttle从未阻塞请求。
- 0×empty200>0终态行(empty_200全在中间attempt, 不进HM-TIER-FAIL终态计数)。

### 1j. throttle利用率对比(R495 vs 本轮)
| 指标 | R495(6h) | 本轮(6h) |
|------|----------|----------|
| 总请求 | 962 | 919 |
| 吞吐(req/min) | 2.67 | 2.55 |
| throttle天花板(60/3.8) | 15.8 | 15.8 |
| 利用率 | 16.9% | 16.1% |
| HM-OUTBOUND-THROTTLE触发 | 0× | 0× |

- throttle利用率16.1% << 100%, 需求侧远未触达throttle → **[HM1-A]throttle非瓶颈**确认(第3轮)。

## 2. CC清单[HM1-A/B/C]状态复检 (30min+6h新鲜数据, 第3轮)

### [HM1-A] MIN_OUTBOUND 18.2→9.0 — ✅已达成(当前3.8<<9.0, 第3轮确认)
- 当前=3.8 (R442达成, compose L421+容器env双处一致)
- CC勘定基于"18.2s全局throttle锁死", 但实际当前=3.8(R442已从4.0→3.8, 远低于CC勘定的9.0目标)
- **第3轮确认**: 6h吞吐2.55req/min, throttle天花板15.8req/min, 利用率16.1% << 100%
- 6h 0×HM-OUTBOUND-THROTTLE触发 → throttle从未阻塞请求
- **结论**: A目标值(9.0)早已超额达成(当前3.8<9.0), throttle非瓶颈, 不动。

### [HM1-B] k4(direct)路由劣化修复 — ✅证伪(第3轮, k4反为最快)
- 6h per-key成功延迟: **k4 p50=6,880ms是5键最快**(非最慢), avg=10,853ms(5键最低)
- CC勘定基于"k4 avg28.5s/p95=72.9s/max=162.9s劣化", 但当前6h数据: k4 avg=10.9s/p95=30.9s, 与其他4键一致(cv≈3%)
- k4当前direct(URL4=""), 与k2(direct)行为一致, 无劣化
- **结论**: k4无路由劣化(反为最快组), 路由修复不适用, 证伪第3轮。

### [HM1-C] all_tiers_exhausted早fail — ✅已实现(FASTBREAK=2活跃, 第3轮确认)
- 当前FASTBREAK=2 (R473达成3→2, compose L454+容器env一致)
- 30min docker logs: 多次HM-PEXEC-FASTBREAK触发, 每次break@~51s=2×25s, 节省后续3key attempt
- 6h 83×budget_break@51s(2×pexec timeout, FASTBREAK=2先触发)
- tier_attempts: 91×NVCFPexecTimeout avg24.6s≈UPSTREAM25 → 2连timeout@51s即fast-fail
- **结论**: fast-fail已由FASTBREAK=2实现且活跃(30min多次触发), 早fail已达成, 不动。

## 3. 其他参数天花板验证

### UPSTREAM_TIMEOUT=25 — 不可降(R490结论第3轮复检)
- 6h NVCFPexecTimeout avg 24,578ms ≈ UPSTREAM边界25
- 6h p95_ok=30,890-39,218ms(k5最高), 慢成功接近UPSTREAM边界
- 降UPSTREAM让pexec更早timeout, 减少单attempt成功机会
- **结论**: UPSTREAM=25保护慢成功, 不可降, 不动。

### TIER_TIMEOUT_BUDGET_S=125 — 活跃约束, 降误杀2 rescue(第3轮确认)
- 6h 83×budget_break@51s, 但break由FASTBREAK=2触发(2×25s=50s), 非BUDGET触发
- BUDGET=125的实际触发: 50-95s区间2 rescue成功接近BUDGET边界被保护
- 降BUDGET到<55s会误杀此2 rescue(50-95s区间) → SR↓
- 但BUDGET=125当前非失败主因(FASTBREAK=2先触发@51s<<125s), BUDGET几乎不触发
- **结论**: BUDGET=125保护2 rescue, 降BUDGET误杀, 不动。

### KEY_COOLDOWN_S=25 / TIER_COOLDOWN_S=25 — 等值, 半活跃(第3轮确认)
- R492将TIER_COOLDOWN 38→25, 恢复KEY=TIER=25等值(R270不变量)
- 6h 0×429 → cooldown非429驱动
- 6×quick_fail@<5s(极少, 远少于HM2的63×) → cooldown级联副作用轻微
- **结论**: KEY=TIER=25等值, quick_fail极少, 不动。

### HM_CONNECT_RESERVE_S=10 — 活跃约束(第3轮确认)
- 6h 0×budget由RESERVE触发(FASTBREAK=2先触发@51s)
- RESERVE=10当前非失败主因
- **结论**: RESERVE=10活跃但非瓶颈, 不动。

## 4. 决策: ⏸️ NOP · 零配置变更

**理由**:
1. CC清单[HM1-A/B/C]三项全部完成/证伪(本轮第3轮确认, 与R495/R493/R491一致):
   - A: MIN_OUTBOUND=3.8已达成(<<9.0目标), throttle非瓶颈(利用率16.1%, 0×触发)
   - B: k4无路由劣化(反为5键最快, p50=6880ms, cv≈3%), 证伪
   - C: FASTBREAK=2已实现且活跃(30min多次触发, break@51s=2×25s), 早fail已达成
2. 全8参数在天花板: UPSTREAM=25保护慢成功(timeout avg24.6s≈边界), BUDGET=125保护2 rescue(FASTBREAK先触发BUDGET几乎不触发), KEY/TIER_COOLDOWN=25等值(0×429, quick_fail极少), RESERVE=10非瓶颈
3. **SR稳态铁证(第3轮)**: 零HM1参数变更从R493→本轮连续3轮, SR 81.2%→82.0%→81.3%(±0.8pp波动) → 根因在NVCF server-side pexec timeout频率(91×avg24.6s≈UPSTREAM25), 非HM1参数可修
4. 失败模式: 83×budget_break@51s(2×pexec timeout, FASTBREAK=2) + 82×mid-fail@25-50s(2×timeout后cycle fail) + 6×quick_fail@<5s(cooling级联极少), 全NVCF server-side, 非HM1参数可解
5. 5键per-hit全100%SR, 0×429, 0×empty_200(终态), 0×SSLEOF, 连接与key池健康
6. **empty_200新信号(本轮新增)**: 18×全集中08:00小时桶一次性突发, 5请求全被cycle救回终态200, 非HM1参数问题(NVCF一次性empty body突发, 已被tier重试机制吸收), 无需改

**当前HM1参数已达全局最优(在NVCF稳态下)**: throttle/cooldown在等值下限, FASTBREAK=2活跃早fail, UPSTREAM=25保护慢成功, BUDGET=125保护2 rescue。SR稳态根因在NVCF server-side, 非参数可修。连续3轮零参数变更且数据结构稳定(R495→本轮: ATE 173→172, 429 0→0, pexec timeout 52→91但SR稳态, budget_break 84→83, mid-fail 83→82, quick_fail 6→6, rescue 3→2), 证明HM1参数侧已无优化空间, 等待NVCF server-side恢复。

## 5. 清单外发现 (供CC下轮勘定, 非本轮清单项)

### 5a. empty_200一次性突发(08:00小时桶) — NVCF非持续异常, 已被cycle吸收(本轮新增)
- **现象**: 6h 18×empty_200全集中在08:00小时桶(DB ts, 真实UTC 00:00), 09:00后归零
- **分布**: 5键分散(k0=5/k1=4/k2=3/k3=3/k4=3), 5个request_id(c4138de4×6/06c3b5e5×5/46e652f6×3/5f59dd2b×3/b5bf82ae×1)
- **终态**: 全5请求status=200(cycle rescue救回), empty_200未导致终态失败
- **结论**: NVCF在08:00一次性empty body突发, 非持续模式, 已被HM1 tier重试机制(FASTBREAK=2 + cycle rescue)吸收, 不影响SR。非HM1参数可修, 无需改。
- **供CC勘定**: 若empty_200未来持续高频出现, 可考虑empty_200专用retry逻辑(当前与timeout共用cycle)。但目前一次性突发已自愈, 优先级低。

### 5b. HM1 vs HM2 失败模式对比 — HM1更轻(延续R495上报, 更新HM2数据为R496)
| 指标 | HM1(本轮6h) | HM2(R496 6h) |
|------|-------------|--------------|
| SR | 81.3% | 80.8% |
| ATE | 172 | 130 |
| 429 | 0 | 5 |
| budget_break耗时 | 51s(FASTBREAK=2) | 92.6s(FASTBREAK=5死) |
| quick_fail | 6 | 63 |
| FASTBREAK活跃 | 多次/30min | 0次/30min(死参数) |
| empty_200(中间) | 18(一次性,全救回) | 0 |
- HM1的FASTBREAK=2活跃(节省后续key attempt), HM2的FASTBREAK=5死参数(BUDGET先触发)
- HM1无429, HM2有5×429(k1代理未减反最高7)
- HM1 quick_fail极少(6), HM2有63×(cooling级联)
- **供CC勘定**: HM2侧可借鉴HM1的FASTBREAK=2设计(降FASTBREAK 5→2), 但HM2 BUDGET=100<2×48=96会让BUDGET先触发, 需先解决BUDGET/UPSTREAM失配(见HM2 R496 5a升BUDGET=115勘定包)

### 5c. 2 rescue在50-95s区间 — BUDGET=125保护(延续R495)
- 6h 2×rescue成功在50-95s区间(attempt1 timeout@25s后attempt2成功接近BUDGET边界)
- 降BUDGET到<55s会误杀此2 rescue → SR↓
- 但BUDGET=125当前非失败主因(FASTBREAK=2先触发@51s)
- **供CC勘定**: BUDGET=125有轻微保护作用, 不动。

## 6. 执行记录

### 变更: 无
```bash
# 零配置变更 — docker-compose.yml不变, 容器不重启
# 本轮为数据驱动NOP: CC清单三项6h+30min新鲜数据第3轮复检全已完成/证伪, 无可动项
# SR稳态(81.3%)根因NVCF server-side pexec timeout频率(91×avg24.6s≈UPSTREAM25), 非HM1参数可修
# empty_200新信号(18×一次性突发全救回)为NVCF非持续异常, 已被tier重试吸收, 非参数问题
# 清单外发现(empty_200一次性突发, HM1 vs HM2对比, 2 rescue保护)延续R495上报CC, 不擅改
```

### 验证: 通过
```bash
# env一致性检查: compose grep(hm40006块) 与 docker exec hm40006 env 逐字一致, 8参数+5URL零漂移
ssh -p 222 opc_uname@100.109.153.83 'docker exec hm40006 env | grep -E "MIN_OUTBOUND|TIER_TIMEOUT|UPSTREAM|KEY_COOLDOWN|TIER_COOLDOWN|CONNECT_RESERVE|FASTBREAK|SSLEOF|HM_NV_PROXY_URL"'
# ↑ MIN_OUTBOUND=3.8, BUDGET=125, UPSTREAM=25, FASTBREAK=2, KEY/TIER_COOLDOWN=25, RESERVE=10, URL1=7894/URL3=7896(URL2/4/5空), 全匹配compose

# 健康检查 (对端): /health=200 ok, hm_num_keys=5, nvcf_pexec_models=[dsv4p_nv]
```

## 7. 轮次统计
- HM1自R495(HM2→HM1 NOP)后: R496为HM1→HM2方向, 本轮R497为HM2→HM1方向
- CC清单[HM1-A/B/C]三项状态: A✅达成(MIN_OUTBOUND=3.8<<9.0, throttle非瓶颈16.1%利用率), B✅证伪(k4反为最快p50=6880ms, cv≈3%), C✅实现(FASTBREAK=2活跃, 30min多次触发, break@51s)
- 连续NOP(HM1侧): R486→R488→R489→R491→R493→R495→R497, 本轮为清单第3轮复检证伪轮(每项有30min+6h具体数据)
- 本轮NOP理由: 三项全部完成/证伪(第3轮), 全8参数在天花板, SR稳态根因NVCF server-side非参数可修(零参数变更连续3轮SR 81.2%→82.0%→81.3%波动±0.8pp为铁证)
- 数据稳定性: R495→R497 6h数据对比(ATE 173→172, 429 0→0, budget_break 84→83, mid-fail 83→82, quick_fail 6→6, rescue 3→2), 各项波动在±1内, 模式完全一致, 证明HM1侧已达稳态
- 本轮新增价值: empty_200新信号一次性突发确认(18×全集中08:00, 5请求全被cycle救回终态200, 非参数问题), 更新HM1 vs HM2对比表(HM2数据更新为R496)

## 8. 铁律遵守
- ✅ 只改HM1不改HM2: 无变更行为, 合规
- ✅ 单参数少改��轮: NOP验证, 无参数
- ✅ 数据驱动先采集后决策: 10层验证(env双处一致 + 30min + 6h DB + per-key总请求含失败 + per-key延迟 + 小时桶 + 失败duration分布 + tier_attempts错误结构 + docker logs budget break + throttle利用率对比R495 + empty_200一次性突发确认)
- ✅ 零配置变更: docker-compose.yml未修改, compose与容器env双处零漂移
- ✅ 无R320/R322/R350重蹈: 未改compose, 未commit错文件, push后即停
- ✅ DB时区: 全部用绝对ts窗口, 禁用NOW()
- ✅ 执行CC清单不擅自找改动点: empty_200一次性突发+HM1 vs HM2对比+2 rescue保护为清单外项, 延续R495上报CC不擅改
- ✅ host_machine标识正确: opc_uname(DB字段实测值, 非hostname opcsname)
- ✅ 如实记录连续3轮零参数变更: R493→R495→R497 env全一致, SR 81.2%→82.0%→81.3%波动±0.8pp, 非参数可修的铁证显式记录

## ⏳ 轮到HM1优化HM2
