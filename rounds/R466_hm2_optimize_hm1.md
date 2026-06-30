# R466: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项30min新鲜数据全部证伪 · NVCF服务端PexecTimeout surge持续(近5h, 24h 67ATE) · FASTBREAK=3 active(2h 34次早fail, 降=2误杀11/134=8.2%>0.87%假设) · k4非劣化key(k5 p95=110s更高) · throttle利用率19%非瓶颈 · 8项env双处零漂移(compose L418-454=容器) · HM1自R462(16:30:58Z)后零变更 · 铁律:只改HM1不改HM2 · 零配置变更

**方向**: HM2 优化 HM1 (本轮执行者=HM2, 对端=HM1, host_machine=opc_uname)
**动作**: NOP (零配置变更)
**时间**: 2026-07-01 17:08 UTC (DB ts 01:08, +8h偏移已校正; CST 01:08)
**轮次**: R466 → 接R465(HM1→HM2: NOP, commit 35f8112)

## 0. 时区与host标识 (R320教训#5, R464沿用)

- DB `ts` 比真实UTC快8h。真实UTC=17:06时 DB max ts=2026-07-01 01:06:10(次日)。实测: `SELECT max(ts), now()` → max ts=01:06:10, now()=17:06:21, 差8h ✓。所有窗口查询用绝对ts时间戳, 禁用 NOW()。
- 对端HM1 host_machine 标识=`opc_uname` (HM1写入DB值, R460确认)。litellm_model=`nvcf_deepseek-ai/deepseek-v4-pro_k1..k5`(5个key各自model名)。
- hm_tier_attempts 表无 host_machine 列, 用 `litellm_model LIKE 'nvcf_deepseek%'` 过滤HM1侧。
- 关键DB logging事实(沿用R464): 失败请求(ATE)的 `key_cycle_details` 列恒为 `[]`(handlers.py失败路径未设 metrics)。ATE per-attempt 细节从 `docker logs hm40006` 取, DB tier_attempts 表只记录**成功救援**请求的失败attempt。

## 1. 数据采集 (HM1 对端, host_machine=opc_uname)

### 1a. 容器env (8参数, /opt/cc-infra/docker-compose.yml L418-454 = 容器运行态)
```
UPSTREAM_TIMEOUT=45               (L418)  TIER_TIMEOUT_BUDGET_S=125 (L419)
MIN_OUTBOUND_INTERVAL_S=3.8       (L421)  KEY_COOLDOWN_S=25         (L422)
TIER_COOLDOWN_S=38                (L423)  HM_CONNECT_RESERVE_S=10   (L452)
HM_SSLEOF_RETRY_DELAY_S=2.0       (L453)  HM_PEXEC_TIMEOUT_FASTBREAK=3 (L454)
```
compose L418/L419/L421/L422/L423/L452/L453/L454 与容器 `docker exec hm40006 env` 逐字一致 → **双处零漂移** ✓
/health=200 OK (port 40006), proxy_role=passthrough, hm_num_keys=5, hm_model_tiers=["dsv4p_nv"], hm_default_model="dsv4p_nv"(单tier)。
容器 StartedAt: 2026-06-30T16:30:58Z (本轮未触发重启, env与compose一致, 自R462后零变更, 已稳定24.6h+)。

### 1b. DB 30min (真实UTC 16:36-17:06 = DB ts 00:36-01:06)
| 指标 | 数值 |
|------|------|
| 总请求 | 91 |
| 成功 (200) | 73 (80.22%) |
| 失败 | 18 (19.78%) |
| p50 | 43,595ms |
| p95 | 120,520ms |
| max | 124,158ms |
| avg | 55,166ms |
| 429 | 0 |
| empty200 | 0 |
| all_tiers_exhausted | 18 |

失败结构: 18× all_tiers_exhausted, duration 全部 115,000-124,158ms (avg≈115s, FASTBREAK=3在3连timeout≈115s后break, BUDGET=125兜底)。0×429, 0×empty200。**注意**: 30min成功率80.22%显著低于R462(100%) — 是NVCF服务端PexecTimeout surge持续(自13:00 real起已近5h), 非配置回归。p95=120s被ATE尾部主导。

### 1c. DB 30min per-key (5-key 均衡验证, success+fail)
| nv_key_idx | reqs | ok | err | p50 | p95 | max |
|------|------|----|----|------|------|------|
| 0 (k1) | 6 | 6 | 0 | 22,707 | 75,454 | 88,945 |
| 1 (k2) | 19 | 19 | 0 | 21,845 | 86,193 | 100,443 |
| 2 (k3) | 5 | 5 | 0 | 30,282 | 42,567 | 43,203 |
| 3 (k4) | 26 | 26 | 0 | 40,013 | 98,153 | 107,795 |
| 4 (k5) | 18 | 18 | 0 | 22,820 | 110,921 | 111,568 |
| null | 18 | 0 | 18 | 115,435 | 123,927 | 124,158 |

5 key成功样本: k4(idx3) p50=40s/p95=98s偏高, 但**k5(idx4) p95=110s更高**, k2(idx1) p95=86s。k4非最劣key。k1(idx0)仅6req/k3(idx2)仅5req样本小(因多被FASTBREAK吃掉成ATE-null)。18 null = ATE proxy级abort(未分配成功key)。**无单key劣化**(详见§2 [HM1-B])。

### 1d. DB 24h聚合 (真实UTC 06-30 17:06~07-01 17:06 = DB 01:06~01:06)
| 指标 | 数值 |
|------|------|
| 总请求 | 1,907 |
| 成功 (200) | 1,839 (96.43%) |
| 失败 | 68 |
| 429 | 0 |
| empty200 | 0 |
| all_tiers_exhausted | 67 |
| p50 | 8,262ms |
| p95 | 86,149ms |
| max | 124,158ms |

24h 1907req/96.43% — 较R464(1841req/97.12%)成功率略降, 因surge从近3h延长到近5h(00:00-01:00 DB real 16:00-17:00 共33 err)。前19h≈99%+, 近5h surge拉低。67 ATE全NVCFPexecTimeout server-side, 0×429, 0×empty200。

### 1e. DB 24h 失败 duration 分布 (FASTBREAK/BUDGET 截断检测)
| 区间 | count | 含义 |
|------|-------|------|
| <50s | 1 | 单次timeout/快速失败 |
| 50-77s | 0 | — |
| 77-100s | 3 | 2×timeout边界(FASTBREAK=3 2连timeout≈77s) |
| 100-115s | 2 | 2×timeout+部分 |
| 115-125s | 62 | **主集群: 3连timeout≈115s后FASTBREAK break** |
| ≥125s | 0 | 无BUDGET硬截断 |

失败主集群在 115-125s (62个, FASTBREAK=3在第3连timeout≈115s后break), **BUDGET=125未成瓶颈**(≥125s=0个)。62/68=91%失败由FASTBREAK=3终止, 非BUDGET硬截断。

### 1f. DB 24h 慢成功 (BUDGET/FASTBREAK降级误杀风险评估)
| 区间 | 成功数 |
|------|--------|
| <77s | 1,801 |
| 77-100s | 26 |
| 100-115s | 12 |
| 115-125s | 0 |
| ≥125s | 0 |

24h **38个慢成功 ≥77s (2.07%)**, 含12个≥100s。这些是k2/k3在第2-3 key救回的成功(2连timeout后3rd attempt成功)。降FASTBREAK=3→2会在2连timeout(≈77s)后break, **误杀77-115s的38个慢成功**。

### 1g. DB 2h tier_attempts (成功救援请求的失败attempt, hm_tier_attempts表)
| nv_key_idx | attempts | avg_ms | max_ms |
|------|------|------|------|
| 0 (k1) | 11 | 45,933 | 47,011 |
| 1 (k2) | 4 | 47,279 | 49,005 |
| 2 (k3) | 20 | 45,950 | 49,493 |
| 3 (k4) | 8 | 45,759 | 48,236 |
| 4 (k5) | 3 | 45,757 | 46,348 |

46 attempts 全部 NVCFPexecTimeout, avg≈45.9s≈UPSTREAM_TIMEOUT=45(读超时打满)。per-key 3-20次均匀(k3 attempt最多=20因k3多在成功第3-key救援路径, k5最少=3因FASTBREAK=3很少试到k5)。**k4=8次非被NVCF标记**(k3=20才是最高)。这些是成功请求的中间失败attempt, ATE的3连timeout不在此表(DB logging bug, 见§0)。

### 1h. DB 8h逐时吞吐与ATE趋势 (真实UTC hour, DB ts-8h)
| 真实UTC hour(DB hr) | reqs | rpm | ok | err(ATE) | err% |
|------|------|------|-----|------|------|
| 09:00(17) | 194 | 3.23 | 192 | 2 | 1.0% |
| 10:00(18) | 234 | 3.90 | 234 | 0 | 0% |
| 11:00(19) | 283 | 4.72 | 281 | 2 | 0.7% |
| 12:00(20) | 234 | 3.90 | 228 | 6 | 2.6% |
| 13:00(21) | 140 | 2.33 | 132 | 8 | 5.7% |
| 14:00(22) | 246 | 4.10 | 242 | 4 | 1.6% |
| 15:00(23) | 122 | 2.03 | 113 | 9 | 7.4% |
| 16:00(00) | 125 | 2.08 | 99 | 26 | 20.8% |
| 17:00(01) | 17(部分) | — | 10 | 7 | — |

吞吐峰值=4.72 rpm (11:00), throttle理论上限=60/3.8=15.8 rpm, 实测峰值仅30%利用 → **throttle非瓶颈**。ATE surge从13:00 real起持续近5h(8→6→4→9→26→7), 16:00 err%=20.8%为峰值。这是NVCF服务端全局surge(非流量驱动非throttle驱动), **与HM2侧R465记录的同步surge一致**(HM2 R465: 13:00-14:00 real有39 errors)。前19h(08:00-12:00)≈0-2 err/h, 稳态健康。

### 1i. docker logs 2h 失败模式结构 (FASTBREAK=3 active验证)
来源: `docker logs hm40006 --since 2h` grep

**FASTBREAK触发**: 2h 34次 `HM-PEXEC-FASTBREAK 3 consecutive NVCFPexecTimeout -> fast-break (saved remaining keys)`, 每ATE耗≈115s(3×38s timeout)后break。30min内13次触发。

**成功救援分布** (HM-SUCCESS, 2h):
| 救援模式 | count |
|------|------|
| succeeded on first attempt (k1直成) | 85 |
| succeeded after 1 cycle (k2救, k1先fail) | 38 |
| succeeded after 2 cycle (k3救, k1+k2先fail) | 11 |
| succeeded after 3 cycle (k4救) | 0 |
| succeeded after 4 cycle (k5救) | 0 |

2h: 134成功(85+38+11) + 34 ATE = 168请求。**FASTBREAK=3在第3连timeout后break**, 34 ATE各耗≈115s(3×38s)。**关键**: `after 2 cycle`=11个(k3在第3 key救回成功), `after 3/4 cycle`=0(k4/k5从未救回)。

## 2. CC清单评估 ([HM1-A/B/C] 节, 对端=HM1)

### [HM1-A] MIN_OUTBOUND_INTERVAL_S 3.8→9.0 → 证伪
CC清单称"throttle=18.2s锁死吞吐, 降到9.0翻倍"。当前实测**再次证伪**:
- **当前**: MIN_OUTBOUND=3.8 (compose L421, R442: 4.0→3.8), **非清单所述18.2**(过时值, R460/R462/R464已纠正)。清单反向"降到9.0"实为**升throttle**(3.8→9.0=降吞吐), 逻辑反向。
- **数据**: 30min 91req=3.03 rpm, throttle理论上限=60/3.8=15.8 rpm, **利用率仅19%** → throttle非瓶颈
- 8h峰值4.72 rpm(R464记录), 仍仅30%利用
- 24h 0×429 → 升throttle(到9.0)直接砍吞吐无收益, 降throttle无429缓冲但已非瓶颈无吞吐收益
- **结论**: 证伪, 不可行 (与R460/R462/R464一致)

### [HM1-B] k4(direct)路由劣化修复 → 证伪
CC清单称"k4 avg28.5s p95=72.9s max162.9s, 本机IP被NVCF标记"。当前实测**再次证伪**:
- 30min per-key成功: **k4(idx3) p95=98s非最高, k5(idx4) p95=110s更高**, k2(idx1) p95=86s。k4非最劣key。
- 2h tier_attempts: k4=8次, **k3=20次才是最高**, k4非被NVCF标记
- 5 key PexecTimeout均匀分布(R464记录2h: k1=33/k2=23/k3=38/k4=24/k5=16), k4非最高(k3才是)
- ATE 68个全5-key-timeout(server-side surge), 非k4本机IP问题
- **结论**: 证伪, 均衡已达成, 无key需要改路由 (与R460/R462/R464一致)

### [HM1-C] all_tiers_exhausted早fail → 证伪(FASTBREAK=3已active, 降=2误杀8.2%>0.87%假设)
CC清单称"22次失败avg104s共耗2288s, 前3key全NVCFPexecTimeout即fast-fail省~50s/次"。当前实测**证伪**:
- **FASTBREAK=3已active且有效**: docker logs 2h 34次 `HM-PEXEC-FASTBREAK 3 consecutive NVCFPexecTimeout -> fast-break`, 每ATE耗≈115s(3连timeout)后break, **已不试k4/k5**(save ~90s/次 vs 试满5 key)。24h 68失败中62个(91%)在115-125s(FASTBREAK终止), 0个≥125s(BUDGET未成瓶颈)。
- **降FASTBREAK=3→2的误杀评估(新鲜数据)**: 2h docker logs 134 success中, `succeeded after 2 cycle`=11个(k3在第3 key救回, k1+k2先timeout后k3成功)。降=2会在2连timeout后break, **误杀这11个** = 11/134=**8.2%误杀率**(比R464的7/95=7.4%更高, surge期k3救回更多)。
- CC清单注释称"rescue cases (3+ timeouts后k4/k5救回)罕见(2/231=0.87%)" — 但当前2h实测**rescue发生在after 2 cycle(k3, 第3 key)而非3+ timeouts后k4/k5**, FASTBREAK=3本身即不试k4/k5(after 3/4 cycle=0), 清单假设的"k4/k5救回"本就不存在。降=2误杀的是k3救回(11个), 非0.87%假设的k4/k5救回。
- **降FASTBREAK=3→2的收益**: 34 ATE各省~38s(2连≈77s vs 3连≈115s), 总省~1292s/2h — 但代价是误杀11个成功(每个本可成功), 违反"稳定优先>越快越好"。24h外推: 68 ATE各省~1292×(68/34)=~2584s/24h, 但误杀11×(68/34)=~22个成功/24h。
- **BUDGET 125→?无收益**: ATE在115s被FASTBREAK先触发(BUDGET=125未成瓶颈, 24h 0个≥125s)。降BUDGET到<77s才会先于FASTBREAK触发, 但会误杀77-115s慢成功(24h有38个≥77s成功, 含12个≥100s)。
- **根因**: 68 ATE是NVCF服务端PexecTimeout surge(5 key全timeout), 非proxy层可修复 — 已在R463 HM2侧确认"失败全NVCFPexecTimeout server-side不可proxy层修复"
- **结论**: 证伪, FASTBREAK=3已是最优早fail值, 降=2误杀8.2%>0.87%假设不可行 (与R462/R464一致, 补充surge期误杀量化8.2%)

### 全参数天花板确认
- 8参数全部验证compose L418-454 = 容器env, 零漂移
- 24h 96.43%成功率(前19h≈99%+, 近5h NVCF surge拉低), 0×429, 0×empty200, 67 ATE全server-side
- 5 key PexecTimeout均匀(16-38次/2h), 无劣化key
- FASTBREAK=3 active, 2h 34次fast-break, 68 ATE各3连timeout≈115s break(已省k4/k5的~90s/次), BUDGET=125未成瓶颈
- 吞吐throttle利用率仅19-30%, throttle非瓶颈

## 决策: NOP · 零配置变更

**理由**: CC清单[HM1-A/B/C]三项全部被30min新鲜数据+24h+2h tier_attempts+docker logs复检测证伪。HM1侧已达全参数天花板, 当前失败surge是NVCF服务端PexecTimeout(5 key全timeout), 非proxy层可修复:

| 参数 | 值 | 状态 |
|------|-----|------|
| MIN_OUTBOUND | 3.8 | 已最优 (清单18.2过时, 实测3.8, throttle利用率19%非瓶颈, 0×429) |
| KEY_COOLDOWN | 25 | 已最优 (2h 5-key均衡, rescue 85+38+11分布健康) |
| TIER_COOLDOWN | 38 | 已最优 (TIER=38>KEY=25, 单tier模型) |
| UPSTREAM_TIMEOUT | 45 | 已最优 (tier attempt avg 45.9s≈45s 覆盖, NVCF无响应时打满) |
| BUDGET | 125 | 已最优 (ATE在115s被FASTBREAK先触发, BUDGET未成瓶颈, 24h 0个≥125s; 降<77s才影响但误杀38个慢成功) |
| CONNECT_RESERVE | 10 | 已最优 |
| SSLEOF_RETRY | 2.0 | 已最优 (0 SSLEOF失败) |
| FASTBREAK | 3 | 已最优且active (2h 34次fast-break, 降=2误杀11/134=8.2%>0.87%假设不可行; after 3/4 cycle=0证明k4/k5从未救回, FASTBREAK=3设计上已不试k4/k5) |

**失败根因(不可proxy层修复)**: 67×all_tiers_exhausted全NVCFPexecTimeout server-side (NVCF deepseek_hm_nv后端慢/超时~45s/attempt), 跨key随机, 3×timeout avg115s。proxy层无法修复NVCF server-side慢响应。慢成功rescue(38个≥77s, 含12个≥100s)由BUDGET+多attempt机制保住, 不可牺牲。

**与HM2侧surge同步**: 13:00-17:00 real(DB hr 21-01) HM1有8+6+4+9+26+7=60 errors surge, 与HM2侧R465记录的同步surge一致(HM2 R465: 13:00-14:00 real有39 errors) — 确认是NVCF服务端全局surge(非任一端配置问题), 持续近5h未自愈(R464时近3h, 本轮近5h)。HM1稳态未变(前19h≈99%+)。

**铁律**: 只改HM1不改HM2 ✓ · 零配置变更 · 零docker compose重启 · 零容器env改动

## 改前/改后对比 (NOP, 同窗口)
| 指标 | 改前(30min) | 改后(30min) |
|------|------|------|
| reqs | 91 | 91 (NOP, 同窗口) |
| 成功率 | 80.22% | 80.22% |
| p50 | 43,595ms | 43,595ms |
| p95 | 120,520ms | 120,520ms |
| 429 | 0 | 0 |
| empty200 | 0 | 0 |
| all_tiers_exhausted | 18 | 18 |

NOP轮无配置变更, 改前=改后同窗口。24h长窗口(1907req/96.43%)为稳态证据(前19h≈99%+, 近5h NVCF surge拉低)。surge为NVCF服务端波动非配置回归。

## 历史对比
| 轮次 | 30min reqs | 30min成功率 | 24h reqs | 24h成功率 | 变更 |
|------|-----------|------------|---------|---------|------|
| R466 | 91 | 80.22% | 1907 | 96.43% | ⏸️ NOP |
| R464 | 52 | 82.69% | 1841 | 97.12% | ⏸️ NOP |
| R462 | 61 | 100.00% | 1796 | 100.00% | ⏸️ NOP |
| R460 | 26 | 100.00% | 1593(8h) | 100.00% | ⏸️ NOP |

30min 91req/80.22% — 流量较R464(52req)升(surge期请求堆积), 成功率80.22%vs82.69%(NVCF服务端PexecTimeout surge持续近5h致18 ATE, 前19h≈99%+)。24h 1907req/96.43%(R464 1841req/97.12%, surge从近3h延长到近5h拉低)。失败结构: 67 ATE全NVCFPexecTimeout server-side, FASTBREAK=3已active早fail(2h 34次), 非proxy层可修复。

## 部署
```bash
# 无操作 — 容器 keep running (StartedAt 2026-06-30T16:30:58Z, 参数零变更, 自R462后零变更, 稳定24.6h+)
# 验证: /health=200 OK (port 40006), hm_num_keys=5, 8项env双处零漂移
# compose /opt/cc-infra/docker-compose.yml L418-454 = 容器运行态, 双处一致
# HM1 env与R464逐字一致, 零漂移
```

## ⏳ 轮到HM1优化HM2
