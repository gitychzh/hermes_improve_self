# R444: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项重验全部证伪 · 全参数天花板 · 30min 92/95=96.84% · 0 429 · 3 ATE全NVCF server-side PexecTimeout(avg121.8s≈BUDGET=125) · throttle已是4.0非瓶颈(p50_gap6.83s>>4.0) · 5key 6h均衡无劣化key · 降BUDGET误杀4个100-125s慢成功 · 铁律:只改HM1不改HM2 · 零配置变更

**角色**: HM2 (执行者, opc2_uname) → HM1 (目标, opc_uname/opcsname, dsv4p_nv)
**日期**: 2026-06-30 21:48-21:56 CST (DB ts口径, host_machine='opc_uname')
**铁律**: 只改HM1不改HM2 ✓
**前轮**: R443 (HM1→HM2, UPSTREAM_TIMEOUT 50→48 -2s)
**本轮**: 数据采集+CC清单[HM1-A/B/C]三项重验 → 判定NOP (三项全部已做完或被当前数据证伪)

## 0. 任务规则与本轮决策依据

任务规则: "优先执行清单第1项, 若第1项本轮无法实施(如已被前轮做过/数据不支撑), 顺延下一项。每轮只做1项。"
任务规则: "不允许'无操作'轮, 除非三项都已做完或数据证伪(证伪需给出具体数据)。"

本轮按规则逐一重验CC清单[HM1-A/B/C]三项, 结论: **A已超额完成+throttle非瓶颈再降证伪 / B勘定前提与当前6h数据不符证伪 / C降BUDGET误杀4个慢成功证伪**, 满足NOP例外条件。下文每项给出本轮新采的具体数据(锚点 max_ts=2026-06-30 21:54:08+00)。

注: R443末尾标记"⏳ 轮到HM2优化HM1", 本轮接手HM2→HM1, 无抢跑(R443 commit 748c3db后HM1侧未触发新round)。

## 1. 改前数据采集 (锚点 max_ts=2026-06-30 21:54:08+00, HM1 host_machine='opc_uname')

### 1a. 容器运行态env (docker exec → 全env验证)
```
MIN_OUTBOUND_INTERVAL_S  = 4.0   (R437: HM2→HM1 5.0→4.0)
TIER_TIMEOUT_BUDGET_S   = 125   (R438未动, 仍125)
UPSTREAM_TIMEOUT        = 45    (R438未动)
KEY_COOLDOWN_S          = 25    (R438: HM2→HM1 38→25)
TIER_COOLDOWN_S         = 38    (R438未动)
HM_CONNECT_RESERVE_S    = 10    (R438未动)
HM_PEXEC_TIMEOUT_FASTBREAK = 5  (R438未动)
HM_SSLEOF_RETRY_DELAY_S = 2.0   (R438未动)
```
Routing (HM_NV_PROXY_URL*): k0(idx0)→7894, k1(idx1)→DIRECT(空), k2(idx2)→7896, k3(idx3)→DIRECT(空), k4(idx4)→DIRECT(空)
容器StartedAt=2026-06-30T13:16:06Z (R438重启后未变, 已稳定运行8.6h), /health=200 ok, hm_num_keys=5, dsv4p_nv ✓

### 1b. 30min窗口成功率 (21:24:00~21:54:08 UTC, ts口径 max(ts)-30min)
| total | success | empty200 | 429 | ATE | 5xx | 成功率 | reqs/min | avg_ms | p50 | p95 |
|---|---|---|---|---|---|---|---|---|---|---|
| 95 | 92 | 0 | 0 | 3 | 3 | 96.84% | 3.17 | 14401 | 6142 | 31826 |

(成功行p95=31826ms; 失败行avg=121765ms/p95=123653ms单独计算, 上表p95为成功+失败混合percentile_cont)

### 1c. 1h窗口稳定性 (20:54~21:54 UTC)
| total | ok | fail | empty200 | 成功率 | reqs/min | avg_ms | p50 | p95 |
|---|---|---|---|---|---|---|---|---|
| 130 | 120 | 10 | 2 | 92.31% | 2.17 | 18736 | 7046 | 120856 |

1h成功率92.31%低于30min(96.84%), 失败10个, 全NVCF server-side timeout主导(p95=120856ms被失败拉高, 成功行p50=7046ms仍正常)。

### 1d. per-key成功延迟 (6h窗口 15:54~21:54 UTC, status=200)
| nv_key_idx | cnt | ok | fail | ok_avg_ms | ok_p95 | ok_max | ok_gt45s |
|---|---|---|---|---|---|---|---|
| 0 (k0 7894)   | 240 | 240 |  0 | 13563 | 43392 | 111813 | 12 |
| 1 (k1 DIRECT) | 249 | 249 |  0 | 11784 | 37937 |  98461 | 10 |
| 2 (k2 7896)   | 224 | 224 |  0 | 12122 | 33235 |  90015 |  8 |
| 3 (k3 DIRECT) | 260 | 260 |  0 | 12287 | 49605 | 113694 | 16 |
| 4 (k4 DIRECT) | 234 | 234 |  0 | 11975 | 35645 |  95207 |  7 |
| (NULL)        |  21 |   0 | 21 |   —   |   —   |   —    |  — |

**5key均衡**(ok 224-260, avg 11.8-13.6s, p95 33-50s, gt45s 7-16), idx3略高p95=49.6s但非离群 → 无清单[HM1-B]描述的"k4单独28.5s"那种清晰��点劣化。失败21次nv_key_idx均为NULL(ATE全tier耗尽, key_idx未记录到最终请求行)。

### 1e. 失败请求耗时分布 (6h, status<>200, 按duration_ms分桶)
| bucket_ms | count | avg_ms |
|---|---|---|
| 95000 | 2 | 95732 |
| 96000 | 1 | 96113 |
| 101000 | 2 | 101706 |
| 120000 | 7 | 120763 |
| 121000 | 6 | 121253 |
| 122000 | 2 | 122203 |
| 123000 | 1 | 123984 |

失败分两簇: ~95-101s(5个, 2×45s timeout+间隙) 与 ~120-124s(16个, BUDGET=125耗尽)。

### 1f. tier_attempts 30min结构 (hm_tier_attempts)
| error_type | count | avg_elapsed_ms | max_elapsed_ms |
|---|---|---|---|
| NVCFPexecTimeout | 5 | 45477 | 46094 |

5次timeout尝试(avg45.5s≈UPSTREAM_TIMEOUT=45), 全NVCFPexecTimeout, 0 SSLEOF, 0 429。

### 1g. 失败request_id的timeout尝试数 (6h, hm_tier_attempts GROUP BY request_id, top25)
| attempts | pexec_to | 样本数 |
|---|---|---|
| 2 | 2 | 8个request_id (avg_elapsed≈45.4s, max≈46.1s) |
| 1 | 1 | 17个request_id (avg_elapsed≈45.5-48.9s) |

无3次以上timeout的失败请求。失败请求最多2次key级timeout即break(BUDGET耗尽或fastfail)。

## 2. CC清单三项重验

### [HM1-A] MIN_OUTBOUND_INTERVAL_S 18.2→9.0 — 证伪(已超额完成+throttle非瓶颈)

清单勘定前提: "HM1吞吐=3.3req/min被18.2s全局throttle锁死". 但当前实测:
- MIN_OUTBOUND_INTERVAL_S **已是4.0**(R437: 5.0→4.0), **< 清单目标9.0** → 已超额完成, 无18.2可降。
- 30min请求间隔分布(ts口径, 95 pairs):
  - p50_gap = **6.83s** >> throttle=4.0s → 请求间隔受**上游响应时间主导**(p50成功延迟6.1s+处理开销), 非throttle锁。
  - p95_gap = 53.54s, avg_gap=16.84s。
  - lt_throttle(gap<4.0) = 17/95 = **17.9%** pair受throttle cap。
- 再降throttle(4.0→更低): p50_gap由上游响应时间主导(6.83s), 降throttle不改p50_gap; 仅17.9% pair受cap, 收益边际。R440已用p50_gap8.26>>4.0证伪, 本轮p50_gap6.83>>4.0再印。
- **结论: 证伪。再降无收益(p50_gap>>throttle), 且4.0<清单目标9.0已超额。**

### [HM1-B] k4(direct, idx=3)路由劣化修复 — 证伪(勘定前提与当前6h数据不符)

清单勘定前提: "k4 avg28.5s vs其他~25s, p95=72.9s vs~55s, max=162.9s, k4本机IP被NVCF标记". 但当前实测(6h, status=200):
- idx4(k4 DIRECT): cnt=234, avg=11975ms, p95=35645ms, max=95207ms — 与5键同级(avg 11.8-13.6s, p95 33-50s)。
- idx3(k3 DIRECT): p95=49605ms(max=113694ms) 反而更高 → 非"k4单独劣化"。
- 5key均衡, 无离群key → 不存在清单描述的"k4本机IP被NVCF标记"模式。
- 30min窗口idx4 p95=94916ms(max=95207)是小样本(20个里)尾部, 6h回归正常(p95=35.6s) → 非系统性劣化。
- **结论: 证伪。勘定前提(k4单独28.5s)与当前6h数据(5key均衡avg11.8-13.6s)不符。**

### [HM1-C] TIER_TIMEOUT_BUDGET_S 125→100 / all_tiers_exhausted早fail — 证伪(降BUDGET误杀慢成功)

清单勘定前提: "失败请求耗满BUDGET, 降到100省~25s/次". 但当前实测(8.6h, 容器StartedAt后):
- 100-125s区间: **4个慢成功(status=200)** + 18个失败(status=502)。
- 降BUDGET 125→100 会**误杀这4个100-125s慢成功**(它们最终成功, 降BUDGET后会被提前break为失败)。
- 失败请求耗时分布(1e): 16/21失败跑到~120-124s(BUDGET耗尽), 5/21在~95-101s早结束(2次timeout后break)。降BUDGET到100对16个BUDGET-exhausted失败无实质帮助(它们在100s时仍在第2次timeout中, NVCF server-side不可proxy层修复)。
- 早fail变体("前3key全timeout即fast-fail"): 本轮6h数据显示失败request_id最多2次timeout(无3次以上), fast-fail触发条件(前3key全timeout)在样本中不成立; 且2-timeout失败已自然break, 无fast-fail省时空间。
- key_cycle_details对失败请求为空数组([]), 无法从DB看key级尝试详情, 但hm_tier_attempts的request_id聚合已证最多2次timeout。
- **结论: 证伪。降BUDGET误杀4个慢成功, 且NVCF server-side timeout不可proxy层修复。**

## 3. 变更决策: NOP (零配置变更)

三项重验均证伪, 满足任务规则"三项都已做完或数据证伪"的NOP例外条件。HM1自R438后零配置变更(StartedAt=13:16:06Z未变, 已稳定运行8.6h), 全参数已达天花板:
- throttle=4.0 < 清单目标9.0(已超额, p50_gap>>throttle非瓶颈)
- 5key均衡无劣化key(B勘定前提不成立)
- BUDGET=125降则误杀4个慢成功(C证伪)
- 失败=NVCFPexecTimeout(server-side, 不可proxy层修复), avg45.5s≈UPSTREAM_TIMEOUT=45

### 铁律遵守
- ✅ 只改HM1不改HM2: 本轮零配置变更, 仅数据采集, 未触碰HM2本地。
- ✅ 未停止/重启/kill mihomo服务。
- ✅ 未改源码(清单三项均证伪, 无可改点)。

### 局限承认
- NVCFPexecTimeout是server-side问题, proxy层无法消除(R440/R441/R443反复确认)。
- 失败请求key_cycle_details为空数组, 无法从DB追溯key级尝试顺序, 但hm_tier_attempts聚合已证最多2次timeout/失败。
- 1h成功率92.31%低于30min(96.84%), 失败10个全NVCF timeout主导, 无系统性可改点。

## 4. 反对者(下轮HM1)提示

- 若下轮认为NOP判定有误, 请给出**具体数据**反驳(如某key确实劣化的6h p95对比, 或降BUDGET后4个慢成功可接受的论证)。
- 本轮1h失败10个p95=120856ms被失败拉高, 成功行p50=7046ms正常, 失败是NVCF server-side timeout, 非HM1配置问题。
- 若CC有新勘定的清单外改动点, 请明确给出数据支撑, 本轮三项清单已无未完成项。

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记
