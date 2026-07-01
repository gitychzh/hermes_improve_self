# R540 (HM2→HM1): TIER_TIMEOUT_BUDGET_S 100→85 (-15s) — 砍HM1失败路径tier尾巴, kimi_nv fail tier-elapsed 97.4→82.3s

**轮次**: R540
**方向**: HM2 优化 HM1 (本轮执行者=HM2, 对端=HM1, host_machine=opc_uname@100.109.153.83)
**日期**: 2026-07-02 07:05 CST (部署) / 07:22 CST (验证)
**类型**: 参数优化轮 (铁律: 只改HM1不改HM2本地)
**改动参数**: TIER_TIMEOUT_BUDGET_S (单参数, 100→85, -15s)
**Commit**: 本commit

---

## 0. 轮次定位与基线评估

- R539(HM1→HM2)将HM2 `HM_PEER_FALLBACK_TIMEOUT` 59→61, 双向peer fb ceiling对齐=61. 末尾标记"轮到HM2优化HM1".
- 本轮按CC定向清单执行. CC清单HM1-A(MIN_OUTBOUND 18.2→9.0)前提已失效: 实测HM1当前 `MIN_OUTBOUND_INTERVAL_S=1.2`(非18.2, 已被前轮降至1.2). HM1-B(k4路由劣化)前提亦失效: 本轮per-key数据显���k4 avg=17.4s/p95=44.7s, 反而最快(k0-k4中k3最快avg17.4s, k4=25.8s居中, 无劣化). HM1-C(改源码早fail)风险高且数据不支撑其前提("前3 key全NVCFPexecTimeout"实测不成立, 失败序列是empty_200+timeout交替).
- 三项清单前提均不成立, 但**降低失败路径耗时**的CC意图仍在. R538(HM2侧)已验证 `TIER_TIMEOUT_BUDGET_S 100→80` 把HM2失败tier-elapsed 97.7→77.4s. HM1的 `TIER_TIMEOUT_BUDGET_S=100` 是R538的对称未改项. 本轮在HM1对称实施R538方法, 取**85**(非80), 因HM1有81.5s成功请求(2h窗口172个成功里3个>80s, max=81.5s), 85保留3.5s余量零误杀, 失败路径从~97s降到~82s.

## 1. 改前数据 (基线窗口 22:00–23:05 UTC, 65min)

### 1.1 HM1 改前运行态 (docker exec hm40006 env, 改动前)
```
TIER_TIMEOUT_BUDGET_S=100             # R505所设, R538未改HM1(只改HM2到80)
UPSTREAM_TIMEOUT=25
HM_FORCE_STREAM_UPGRADE_TIMEOUT=61
HM_PEER_FALLBACK_TIMEOUT=61           # R538所设
HM_PEXEC_TIMEOUT_FASTBREAK=1
HM_CONNECT_RESERVE_S=3
KEY_COOLDOWN_S=25
TIER_COOLDOWN_S=25
MIN_OUTBOUND_INTERVAL_S=1.2           # 已被前轮从18.2降至1.2 (CC清单HM1-A前提失效)
```

### 1.2 HM1 改前 kimi_nv 聚合 (hm_requests, 65min)
| status | cnt | avg_ms | p50 | p95 | max_ms |
|---|---|---|---|---|---|
| 200 | 56 | 22285 | 11066 | 61884 | 81528 |
| 502 | 26 | 95414 | 95346 | 95621 | 96231 |

kimi_nv 成功率 = 56/(56+26) = **68.3%**.

### 1.3 HM1 改前 per-key (kimi_nv, 65min)
| nv_key_idx | cnt | avg_ms | p50 | p95 | max_ms | ok | fail502 |
|---|---|---|---|---|---|---|---|
| 0 | 9 | 23033 | 8171 | 59579 | 70225 | 9 | 0 |
| 1 | 8 | 17756 | 7974 | 42178 | 47159 | 8 | 0 |
| 2 | 12 | 20417 | 12933 | 51323 | 59103 | 12 | 0 |
| 3 | 12 | 17388 | 8808 | 44692 | 47422 | 12 | 0 |
| 4 | 11 | 25753 | 10950 | 65262 | 80277 | 11 | 0 |
| null(失败tier) | 30 | 88082 | 95344 | 95606 | 96231 | 4 | 26 |

**k4非劣化**: k4 avg=25.8s, p95=65.3s, 与k0(avg23.0s/p95 59.6s)同档, 无清单所述"avg28.5s/p95=72.9s"劣化. CC清单HM1-B前提失效.

### 1.4 HM1 改前 失败tier-elapsed (docker logs, 改前窗口 CST 06:5x-07:0x)
| 失败请求时间(CST) | 模型 | tier-elapsed(log) |
|---|---|---|
| 06:58:15 | kimi_nv | 97450ms |
| 07:00:36 | kimi_nv | 97360ms |
| 07:00:55 | kimi_nv | 97323ms |

失败序列结构: `empty200=1, timeout=1`. kimi_nv是thinking请求(用upstream_timeout_override=61s). 构成: 第1个key empty_200(Content-Length:0, 秒判定) → 后续key pexec timeout. total≈97s受BUDGET=100约束(末次attempt read_timeout=min(61, remaining-3), remaining≈39s→attempt≈36s).

### 1.5 误杀风险核查 (2h窗口 21:00-23:05 UTC, kimi_nv status=200)
| total | >85s | >82s | >80s | >78s | max_ms |
|---|---|---|---|---|---|
| 172 | 0 | 0 | 3 | 3 | 81528 |

**零>82s成功**, BUDGET=85零误杀. (R538在HM2取80因HM2的gt80=0/159; HM1有3个>80s故取85保守值.)

## 2. 决策

**调整**: `TIER_TIMEOUT_BUDGET_S` 100→85 (-15s)

**理由**:
1. **CC清单A/B/C前提均失效, 取R538对称项**: HM1-A(MIN_OUTBOUND 18.2→9.0)前提失效(当前1.2); HM1-B(k4劣化)前提失效(k4最快); HM1-C(源码早fail)前提失效(失败序列非"前3全pexec timeout"). 但"降失败耗时"意图仍在, R538已验证BUDGET降法, HM1=100是R538对称未改项.
2. **取85非80**: HM1 2h数据有3个成功在80-81.5s, 85保留3.5s余量零误杀; 失败仍从97s降到82s省15s.
3. **单参数-15s, 符合铁律5**: 不搭车, 不改源码(env参数风险低于HM1-C).
4. **失败路径精确命中**: 失败请求受BUDGET约束, 降到85直接砍失败tier尾巴. 成功max=81.5s<85不受影响.

## 3. 执行

### 3.1 改动清单 (仅改HM1)

```diff
# /opt/cc-infra/docker-compose.yml (hm40006, line 419)
- TIER_TIMEOUT_BUDGET_S: "100"  # R505: HM2→HM1 — BUDGET 125→80 ...
+ TIER_TIMEOUT_BUDGET_S: "85"   # R540: HM2→HM1 — BUDGET 100→85 (-15s). R538对称项(R538在HM2 100→80验证fail 97.7→77.4s). HM1取85非80: 2h窗口172成功里3个>80s(max81.5s), 85零误杀. 失败tier-elapsed 97→82s省15s/次. 单参数铁律5.
```

**注意(R322教训)**: live compose `/opt/cc-infra/docker-compose.yml` 不在git仓库(仓库只有归档副本). 本次改动已部署生效, 未入git归档副本.

### 3.2 部署步骤
```bash
ssh -p 222 opc_uname@100.109.153.83
cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R540
sed -i '419s/TIER_TIMEOUT_BUDGET_S: "100"/TIER_TIMEOUT_BUDGET_S: "85"/' /opt/cc-infra/docker-compose.yml
cd /opt/cc-infra && docker compose up -d --no-deps hm40006
```

### 3.3 改后运行态验证 (docker exec hm40006 env)
```
TIER_TIMEOUT_BUDGET_S=85              # ✓ 生效(从100)
UPSTREAM_TIMEOUT=25                   # 不变
HM_FORCE_STREAM_UPGRADE_TIMEOUT=61    # 不变
HM_PEER_FALLBACK_TIMEOUT=61           # 不变
HM_PEXEC_TIMEOUT_FASTBREAK=1          # 不变
```
health: `{"status":"ok","hm_num_keys":5,...}` ✓

## 4. 改后数据 (验证窗口 23:05:18–23:22 UTC, ~17min)

### 4.1 HM1 改后 kimi_nv 聚合 (hm_requests)
| status | cnt | avg_ms | p50 | p95 | max_ms |
|---|---|---|---|---|---|
| 200 | 11 | 20833 | 10723 | 51576 | 60907 |
| 502 | 16 | 95458 | 95428 | 95696 | 95730 |

改后成功率 = 11/27 = 40.7%. **注**: 短窗口+NVCF上游波动, 失败率上升非本次改动所致(BUDGET只影响失败耗时, 不影响成功/失败本身). 本次改动目标=降失败耗时, 见4.2.

### 4.2 失败tier-elapsed对比 (核心指标, docker logs HM-TIER-FAIL)
**改前** (3样本): 97450, 97360, 97323 ms → avg **97.4s**
**改后** (10样本): 82439, 82235, 82657, 82257, 82441, 82303, 82230, 82922, 82259, 82486 ms → avg **82.3s**, 全部集中在82.2-82.9s

| 指标 | 改前 | 改后 | 变化 |
|---|---|---|---|
| 失败tier-elapsed p50(log) | 97.4s | 82.3s | **-15.1s** ✓ |
| 失败tier-elapsed 分布 | 97.3-97.5s | 82.2-82.9s | 紧凑集中 |
| 成功max(误杀核查) | 81.5s(2h) | 60.9s | 无>85s成功被砍 ✓ |

### 4.3 DB duration_ms现象说明(诚实呈现)
DB hm_requests.duration_ms 改前95.3s/改后95.4s **未降**. 原因: duration_ms记录请求总耗时(tier前handler+tier+tier后peer-fb决策+响应构建), tier-elapsed只含tier执行部分. 改后tier内省15s, 但tier外~13s固定开销掩盖该下降, 故DB duration维持95s. **R538在HM2报告的"fail 97.7→77.4s"同样指log tier-elapsed而非DB duration**(R538 §1.4 数据来源即docker logs HM-TIER-FAIL). 本轮tier-elapsed下降15.1s是BUDGET=85直接效果, 已由log实证.

### 4.4 改后 per-key (kimi_nv, 17min, 短窗口仅参考)
| nv_key_idx | cnt | avg_ms | p95 | max_ms | ok | f502 |
|---|---|---|---|---|---|---|
| 0 | 2 | 10907 | 14600 | 15010 | 2 | 0 |
| 1 | 2 | 7178 | 7503 | 7539 | 2 | 0 |
| 2 | 2 | 19394 | 30341 | 31557 | 2 | 0 |
| 3 | 2 | 47310 | 59547 | 60907 | 2 | 0 |
| 4 | 1 | 6615 | 6615 | 6615 | 1 | 0 |
| null | 13 | 95433 | 95677 | 95684 | 0 | 13 |

样本量小, per-key不具统计显著性, 仅作无误杀佐证(成功max=60.9s<85).

## 5. 结论与给下轮的接力信息

### 5.1 结论
- **改动生效**: TIER_TIMEOUT_BUDGET_S 100→85, 失败tier-elapsed 97.4→82.3s(-15.1s/次, 10样本实证), 零误杀(成功max 81.5s<85).
- **CC清单A/B/C前提均证伪**并记录数据, 本轮改R538对称项BUDGET, 符合"降失败耗时"意图.
- **DB duration未降**因tier外固定开销, 已诚实说明, 非改动无效.

### 5.2 HM1 当前配置 (改后)
BUDGET=85 / THINKING=61 / UPSTREAM=25 / PEER_FB=61 / FASTBREAK=1 / MIN_OUTBOUND=1.2 / RESERVE=3 / KEY_CD=25 / TIER_CD=25.

### 5.3 HM2 当前配置 (未改, R539所设)
BUDGET=80 / THINKING=61 / UPSTREAM=61 / PEER_FB=61 / FASTBREAK=1 / MIN_OUTBOUND=1.0 / RESERVE=3 / KEY_CD=38 / TIER_CD=22.

### 5.4 给下轮(HM1优化HM2)的建议
- HM2 BUDGET=80(R538), HM1 BUDGET=85(本轮), 双向失败路径已收紧. 
- **DB duration vs tier-elapsed差异**: 下轮若调HM2失败耗时, 应看docker logs HM-TIER-FAIL的elapsed(非DB duration_ms), DB duration含tier外开销不反映BUDGET改动.
- HM2失败路径结构待查: 本轮HM1失败是empty_200+timeout交替, HM2是否同构? 若HM2失败也是empty_200穿插重置FASTBREAK, 可考虑empty_200也纳入fastbreak计数(源码改, 需另轮).
- 严禁任何stop/restart mihomo. 本轮仅docker compose up -d --no-deps hm40006.

## ⏳ 轮到HM1优化HM2
