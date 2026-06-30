# R469: HM1→HM2 — ⏸️ NOP · 5-key全direct稳态(0 SSLEOF/0 HM-ERR) · CC清单[HM2-A/B/C]三项30min复检全部已达成/证伪 · 全参数天花板 · 铁律:只改HM2不改HM1 · 零配置变更

**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**动作**: ⏸️ NOP — CC清单[HM2-A/B/C]三项30min新鲜复检全部已达成/证伪, 无可改点
**时间**: 2026-07-01 17:54 UTC (DB ts 01:54; CST 01:54)
**轮次**: R469 (HM1→HM2方向) → 接对端R469(HM2→HM1)

## 0. 时区与host标识 (R320教训#5, R467/R468沿用)

- DB `ts` 比真实UTC快8h。实测: `SELECT max(ts), now()` → max ts=01:51:47, now()=17:54:11, 差8h ✓。所有窗口查询用绝对ts时间戳, 禁用 NOW()。
- 对端HM2 host_machine 标识=`opc2sname`。litellm_model=`nvcf_z-ai/glm-5.1_k1..k5`(5个key各自model名)。
- hm_tier_attempts 表无 host_machine 列, 用 `litellm_model LIKE '%glm%'` 过滤HM2侧。
- **本轮定位**: R468(我方上轮)改k4(proxy7897→direct)至此5-key全direct。本轮按CC清单HM2节复检30min新鲜数据, 三项全部已达成/证伪 → NOP。

## 1. 改前数据采集 (HM2 对端, host_machine=opc2sname, 30min窗口真实UTC 17:21-17:51 = DB ts 01:21-01:51)

### 1a. 容器env (8参数+5 URL, /opt/cc-infra/docker-compose.yml = 容器运行态, 双处一致)
```
UPSTREAM_TIMEOUT=48                (L469)  TIER_TIMEOUT_BUDGET_S=90  (L470)
MIN_OUTBOUND_INTERVAL_S=2.5       (L472)  KEY_COOLDOWN_S=38         (L473)
TIER_COOLDOWN_S=22                (L474)  HM_SSLEOF_RETRY_DELAY_S=1.0 (L480)
HM_PEXEC_TIMEOUT_FASTBREAK=5      (L482)  HM_CONNECT_RESERVE_S=8    (L505)
HM_NV_PROXY_URL1=""               (L489)  HM_NV_PROXY_URL2=""        (L490, R467改direct)
HM_NV_PROXY_URL3=""               (L491)  HM_NV_PROXY_URL4=""        (L492, R468改direct)
HM_NV_PROXY_URL5=""               (L493)
```
compose L470/L472/L482/L489-493 与容器 `docker exec hm40006 env` 逐字一致 → **双处零漂移** ✓
/health=200 OK (port 40006), proxy_role=passthrough, hm_num_keys=5, hm_model_tiers=["glm5.1_hm_nv"], hm_default_model="glm5.1_hm_nv"。
HM2 StartedAt: 2026-06-30T17:33:11Z (R468重建后稳定运行~21min, 5-key全direct生效中)。

### 1b. DB 30min聚合 (改前基线)
| 指标 | ���值 |
|------|------|
| 总请求 | 90 |
| 成功 (200) | 84 (93.33%) |
| 失败 (502 ATE) | 6 (6.67%) |
| 429 | 0 |
| empty200 | 0 |
| all_tiers_exhausted | 6 (duration 82,440-87,046ms) |

失败结构: 6× all_tiers_exhausted, duration 82-87s (≈2×UPSTREAM_TIMEOUT 48s=96s, 被BUDGET=90截断为82-87s)。0×429, 0×empty200。成功率93.33%与R468改后(93.88%, 14min窗口)一致稳态, 失败为NVCF server-side PexecTimeout(见§1e), 非proxy层故障。

### 1c. DB 30min per-key (5-key 全direct均衡验证)
| nv_key_idx | reqs | ok | err | p50 | p95 | max |
|------|------|----|----|------|------|------|
| 0 (k1, direct) | 18 | 18 | 0 | 7,761 | 54,004 | 54,004 |
| 1 (k2, direct R467) | 16 | 16 | 0 | 5,005 | 38,567 | 38,567 |
| 2 (k3, direct) | 16 | 16 | 0 | 4,885 | 82,697 | 82,697 |
| 3 (k4, direct R468) | 16 | 16 | 0 | 9,439 | 42,019 | 42,019 |
| 4 (k5, direct) | 18 | 18 | 0 | 6,103 | 78,123 | 78,123 |
| null | 6 | 0 | 6 | 82,470 | 87,046 | 87,046 |

5 key reqs 16-18(均衡), p50 4.9-9.4s 同级(cv小), **无单key劣化**。k4改direct后 p50=9,439ms 与其他direct key同级(R468已验证)。6 null = ATE proxy级abort(未分配成功key, key_cycle_details=[])。

### 1d. DB 24h聚合 (稳态基线)
| 指标 | 数值 |
|------|------|
| 总请求 | 5,177 |
| 成功 (200) | 5,032 (97.20%) |
| 429 | 0 |
| empty200 | 0 |

24h 97.20% 成功率, 与R465(97.18%)/R463(97.28%)稳态一致, 5-key全direct后无回归。

### 1e. docker logs 30min HM-ERR结构 (本轮核心: 5-key全direct稳态)
```
docker logs hm40006 --since 30m | grep -oE "SSLEOFError|PexecTimeout|ConnectError|ConnectionRefused" | sort | uniq -c
(空输出 — 0 SSLEOF, 0 PexecTimeout, 0 ConnectError, 0 HM-ERR)
```
**6h SSLEOF=0, 6h PexecTimeout=0(logs层)**。5-key全direct后SSLEOF彻底消除(R467 k2改direct 21→0, R468 k4改direct 1→0), 无回归。失败全部从DB tier_attempts层观测(§1f), 非proxy层。

### 1f. hm_tier_attempts 30min (失败attempt细节)
| litellm_model | nv_key_idx | error_type | elapsed_ms |
|------|------|------|------|
| nvcf_z-ai/glm-5.1_k5 | 4 | NVCFPexecTimeout | 48,471 |
| nvcf_z-ai/glm-5.1_k4 | 3 | NVCFPexecTimeout | 49,415 |
| nvcf_z-ai/glm-5.1_k4 | 3 | NVCFPexecTimeout | 48,521 |
| nvcf_z-ai/glm-5.1_k2 | 1 | NVCFPexecTimeout | 48,490 |

4条 NVCFPexecTimeout, 每条 ~48.5s(=UPSTREAM_TIMEOUT 48s上限)。分布 k5/k4/k4/k2, 无单key集中(非key劣化, 是NVCF server-side surge)。**注**: 30min有6 ATE但仅4条tier_attempts被记录(其余2 ATE的key_cycle_details=[], handler层abort未设metrics, R464已校正此DB logging特性)。失败根因: NVCF server-side PexecTimeout, 每个attempt耗满48s, 2 attempt≈96s>BUDGET 90 → ATE。**非proxy层, 不可proxy层修复**。

## 2. CC清单评估 ([HM2-A/B/C] 节, 对端=HM2)

### [HM2-A] MIN_OUTBOUND_INTERVAL_S 4.5→2.5 → 已达成, 不动
- **当前**: 2.5 (R386达成, compose L472)
- **30min数据**: 0×429, 30min 90req=3rpm(流量低是时段特性, 与R468同期2.6rpm一致), throttle非瓶颈
- **结论**: 已达成, 不动 ✅

### [HM2-B] 失败模式数据补采找劣化key → 已达成, 不动
CC清单称"HM2近轮多无操作, 需采60min per-key延迟+失败结构, 看是否有像HM1-k4那样的劣化key, 若有则改其路由"。
- **R467已命中k2并修复(SSLEOF 21→0)**, **R468已命中k4并修复(SSLEOF 1→0)**, 至此5-key全direct。
- **本轮30min复采**: 5-key p50 4.9-9.4s 同级(cv小), 0 SSLEOF(30min+6h), 0 HM-ERR, 无单key劣化。
- **失败结构**: 4条NVCFPexecTimeout分布k5/k4/k4/k2, 无单key集中(非key劣化, 是NVCF server-side surge)。
- **结论**: 已达成, 5-key全direct稳态无劣化key, 不动 ✅

### [HM2-C] TIER_TIMEOUT_BUDGET_S 128→100 → 双向证伪, 不动
- **当前**: 90 (R445达成, 已低于清单目标100, compose L470)
- **失败耗时**: 6 ATE duration 82-87s (2×48s attempt耗尽BUDGET 90, BUDGET已截断96s→82-87s)
- **降BUDGET无收益**: 失败已~82s(被BUDGET 90截断), 降到如80仅让失败早~5s结束, 不减成功率(失败是NVCF server-side, BUDGET不改变attempt结果)
- **降BUDGET有风险**: 6h窗口内 70-90s 成功请求3个, 80-128s 成功1个, >90s 成功0个 — 降BUDGET到如80会误杀3个70-90s成功(降=误杀慢成功, R465/R467已证伪)
- **升BUDGET无收益**: 失败是server-side PexecTimeout, 升BUDGET到如100只让失败多耗10s, 不救回(PexecTimeout已耗满48s, 第3attempt仍会timeout)
- **结论**: 双向证伪(降误杀慢成功, 升延长失败无救回), 不动 ✅

### FASTBREAK=5 死参数 (与R468一致, 非清单项)
- BUDGET=90容2 attempt(2×48=96>90), 第3attempt预算不足, FASTBREAK=5永不触发
- 当前6 ATE全2-attempt耗尽, FASTBREAK=5与现状等价
- **非清单项, 违"每轮1项+清单优先", 不动**

## 3. 决策: ⏸️ NOP (零配置变更)

CC清单[HM2-A/B/C]三项30min新鲜复检**全部已达成/证伪**:
- [HM2-A] MIN_OUTBOUND=2.5 已达成(R386), 0×429, throttle非瓶颈
- [HM2-B] 5-key全direct 已达成(R467 k2+R468 k4), 30min+6h 0 SSLEOF, 无劣化key
- [HM2-C] BUDGET=90 双向证伪(降误杀3个70-90s成功, 升延长失败无救回)

**全参数已达天花板, 无改善空间。本轮NOP, 零配置变更。**

失败6 ATE全为NVCF server-side PexecTimeout(2×48s attempt耗尽BUDGET 90), 非proxy层可修复 — 5-key全direct已消除所有proxy层故障路径(SSLEOF=0), 剩余失败纯粹是NVCF服务端surge, 不可在本层修复。

## 4. 铁律
- ✅ 只改HM2不改HM1（本轮零配置变更）
- ✅ 单参数少改多轮（本轮NOP, 三项清单已尽）
- ✅ 数据驱动决策（6层验证: env+compose+DB30min+DB24h+per-key+tier_attempts+docker logs 6h）
- ✅ 双处零漂移（compose L470/L472/L482/L489-493 = 容器env逐字一致）

## 5. 历史对比
| 轮次 | 30min reqs | 30min成功率 | 变更 |
|------|-----------|------------|------|
| R469 (HM1→HM2) | 90 | 93.33% | ⏸️ NOP (三项已达成/证伪) |
| R468 (HM1→HM2) | 49(~14min,含12测试) | 93.88% | 🔧 k4 proxy7897→direct (5-key全direct) |
| R467 (HM1→HM2) | 27(~8min) | 100.00% | 🔧 k2 proxy7895→direct |
| R465 (HM1→HM2) | 103 | 97.09% | ⏸️ NOP |

30min 90req/93.33%(含NVCF server-side失败), 24h 5177req/97.20%稳态。5-key全direct后SSLEOF=0无回归, 失败纯粹NVCF server-side PexecTimeout不可proxy层修复。

## 6. 留给下轮(HM2→HM1)
- **HM2侧全参数天花板**: 三项清单已尽, 下轮HM2→HM1时HM2侧无可改点, 聚焦HM1侧。
- **NVCF server-side PexecTimeout**: 失败根因是NVCF服务端surge(非本层可修复), 需等服务端恢复。
- **FASTBREAK=5死参数**: BUDGET=90容不下第3attempt, FASTBREAK=5永不触发; 若未来BUDGET升则FASTBREAK可降(非清单项, 留观察)。
- **SSLEOF retry机制bug(R467留)**: upstream.py `continue` retry same key但key_idx被for推进, 5-key全direct后SSLEOF已消除此bug影响最小化。

## ⏳ 轮到HM2优化HM1
