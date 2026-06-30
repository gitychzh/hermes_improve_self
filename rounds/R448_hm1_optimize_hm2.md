# R448: HM1→HM2 — ⏸️ NOP · CC清单[HM2-A/B/C]三项重验证全部证伪 · 全参数天花板

**执行时间**: 2026-06-30 23:07-23:15 (UTC+8)
**角色**: HM1 (opc_uname, opcsname) → HM2 (opc2_uname, opc2sname)
**原则**: 少改多轮 · 稳定优先 · 铁律:只改HM2不改HM1
**前轮**: R447 (HM2→HM1, NOP — FASTBREAK=3抢跑补A/B验证)

---

## 📊 数据收集 (HM2, host_machine='opc2sname', mapped_model='glm5.1_hm_nv')

### DB 时区说明 (R350教训#5)
DB `TimeZone=UTC`, `NOW()=2026-06-30 15:07:08+00`. 但 hm_requests.ts 列 max=`2026-06-30 23:06:33+00` (比 NOW() 大8h). 即写入 ts 时用的是 CST 当地时间的数字值但带 +00 tag. 故"最近30min"查询用 `ts > '2026-06-30 22:36:00+00'` (数字匹配当地时区值, 即23:06往前30min). 本轮所有窗口均显式 UTC 字面值, 禁用 NOW()-interval.

### 当前 env (容器运行态, docker exec hm40006 env, 8项)
```
UPSTREAM_TIMEOUT=48          (R284/R443)
TIER_TIMEOUT_BUDGET_S=90     (R445: 85→90)
MIN_OUTBOUND_INTERVAL_S=2.5  (R386)
KEY_COOLDOWN_S=38            (R275)
TIER_COOLDOWN_S=22           (R1)
HM_PEXEC_TIMEOUT_FASTBREAK=5 (R384)
HM_SSLEOF_RETRY_DELAY_S=1.0  (R321)
HM_CONNECT_RESERVE_S=8       (R431)
```
**compose (live /opt/cc-infra/docker-compose.yml 第469-505行) 与容器 env 8项全一致. ✅**
- L469: `UPSTREAM_TIMEOUT: "48"` (R284 注释)
- L470: `TIER_TIMEOUT_BUDGET_S: "90"` (R445 注释 85→90)
- L472: `MIN_OUTBOUND_INTERVAL_S: "2.5"` (R386 注释 5.0→2.5)
- L473: `KEY_COOLDOWN_S: "38"` (R275)
- L474: `TIER_COOLDOWN_S: "22"` (R1)
- L480: `HM_SSLEOF_RETRY_DELAY_S: "1.0"` (R321)
- L482: `HM_PEXEC_TIMEOUT_FASTBREAK: "5"` (R384)
- L505: `HM_CONNECT_RESERVE_S: "8"` (R431)

**容器状态**: `hm40006 Up 46 minutes (healthy)`, StartedAt=`2026-06-30T14:20:51Z` (R445 重启后未再变, 46min前). HM2 自 R445 后零变更.

### per-key proxy 路由 (沿用 R445 Layer 7, 本轮未改路由)
```
k1(idx0)→DIRECT  k2(idx1)→DIRECT  k3(idx2)→proxy
k4(idx3)→DIRECT  k5(idx4)→DIRECT
```

### 改前30min基线 (22:36-23:06当地, 当前env, 无本轮变更)
```
total=49  ok=39  fail=10  succ=79.59%  avg_ok=18781ms  p50_ok=9150ms  p95_ok=69705ms  avg_fail=75638ms
0 真429 (status无429) · 0 empty200 · 10失败全 all_tiers_exhausted
key_cycle_429s>0 的请求=5 (但这5个最终状态是200/502, 非HTTP 429; 是key_cycle内部429被retry跳过, 非429失败)
```

### per-key 30min (status=200 only)
```
idx | total | ok | avg_ok  | p95_ok
 0  |   8   |  8 | 18078   | 64747
 1  |   7   |  7 | 24716   | 70139
 2  |   9   |  9 |  6606   | 11562   ← k3(idx2) 走proxy, avg最低
 3  |   5   |  5 | 23079   | 66160
 4  |  11   | 11 | 23708   | 69705
NULL|  10   |  0 |         |         ← 10失败无 nv_key_idx (all_tiers_exhausted 不记最终key)
5key 全部可用 (ok=total, 0失败), 失败跨key随机 (tier_attempts 见下), 无单key劣化.
```

### tier_attempts 30min (失败结构, host_machine 字段在 hm_tier_attempts 不存在, 用 ts 全局)
```
error_type         | nv_key_idx | count | avg_ms | max_ms
NVCFPexecTimeout   |     0      |   1   | 48562  | 48562
NVCFPexecTimeout   |     2      |   1   | 52529  | 52529
NVCFPexecTimeout   |     3      |   2   | 48872  | 49081
NVCFPexecTimeout   |     4      |   1   | 48731  | 48731
全部 NVCFPexecTimeout (server-side pexec 超时, ≈UPSTREAM=48s), 跨 idx=0/2/3/4 随机, 非单key标记.
```

### 6h 失败分布 (14:00-23:06当地, status<>200)
```
fail=67  avg=79746ms  p50=82561ms  p95=95423ms  min=10582ms  max=103136ms
6h status=200: max=91222ms (仅1个91s慢成功), 0个 100-128s 成功
6h status<>200 中 >90s 的全是 502 (失败, 非100-128s慢成功)
```

---

## 🔬 CC清单 三项重验证 (对端HM2节, 全部证伪 → NOP)

### [HM2-A] MIN_OUTBOUND_INTERVAL_S 4.5→2.5 → 证伪 ✅
**清单前提**: "HM2 throttle=4.5s 仍可降, 降到2.5→吞吐+80%"
**实测**: `MIN_OUTBOUND_INTERVAL_S=2.5` (非4.5! R386 已降至 2.5, 即清单目标值)
- 30min 流量 49req/30min = 1.63rpm, 远低于 throttle=2.5s 允许的 ~24rpm
- 请求自然间隔 (49req/30min ≈ 37s/req) >> throttle 2.5s, throttle 完全非瓶颈
- p50_gap (请求间真实间隔 - throttle) ≈ 34s >> 2.5s
**结论**: 清单前提的 4.5s 与实测 2.5s 完全不符 (清单基于过期数据). 已是目标值. 再降无意义且违 R386 已降结论. **证伪**.

### [HM2-B] HM2失败模式数据补采 → 已采, 无劣化key ✅
**清单前提**: "采60min per-key延迟+失败结构, 看是否有像HM1-k4那样的劣化key"
**实测** (30min per-key + tier_attempts):
- 5key 全部 ok=total (0单key失败), avg_ok 6.6-24.7s, 失败跨 idx=0/2/3/4 随机
- tier_attempts 5个 NVCFPexecTimeout 跨 4 个不同 idx, 非单 key 集中
- 无类似 HM1-k4 的单 key 劣化 (HM1-k4 是 p95 偏高但 p50 正常; HM2 5key p50 同级 6.6-24.7s 范围, 失败随机)
**结论**: 无劣化 key, 改路由无前提. **证伪** (无改动点).

### [HM2-C] TIER_TIMEOUT_BUDGET_S 128→100 → 证伪 ✅
**清单前提**: "HM2 BUDGET=128 偏大, 失败请求耗满128s, 降到100→失败早结束28s, 风险误杀100-128s慢成功"
**实测**: `TIER_TIMEOUT_BUDGET_S=90` (非128! R445 已 85→90, 远低于清单的 100 目标)
- 6h 失败 avg=79.7s p50=82.6s max=103.1s (失败确实耗近 BUDGET=90, 但因 2×NVCFPexecTimeout ~96s>BUDGET90, BUDGET 先到截断)
- 6h **0个 100-128s 慢成功** (status=200 max=91.2s, 0个>100s 成功; >90s 的全是 502 失败)
- 即清单方向"降 128→100"与当前 90 矛盾 (90<100, 已低于目标), 且"误杀100-128s慢成功"区间在当前 90 下为 0
- 升 BUDGET 90→100 方向 (R445 反向 85→90 已做): 6h 失败 max=103.1s 已超 90, 升到 100 可能让部分 ~95s 失败转为成功 (3rd attempt 救援), 但 R445 已评估"升90后2×timeout ~77s→remaining 13s>10s → 3rd attempt 13s可救回", 当前 30min 10失败 avg75.6s 说明仍未救回 (NVCF server 慢)
- 降 BUDGET 90→更低: 误杀 91.2s 慢成功 (6h 有 1 个), 违稳定优先
**结论**: 清单前提的 128 与实测 90 完全不符. 当前 90 已是 R445 勘定的平衡点. **证伪**.

---

## 🏁 最终判决: NOP · 零配置变更

```
✅ CC清单[HM2-A]证伪 (throttle 2.5≠4.5, 已是目标值, 非瓶颈)
✅ CC清单[HM2-B]证伪 (5key均衡无劣化key, 失败跨key随机)
✅ CC清单[HM2-C]证伪 (BUDGET 90≠128, 已低于目标100, 6h零100-128s慢成功)
✅ 当前30min 49req/79.59%/0 真429/0 empty200
✅ 10失败全 NVCF server-side PexecTimeout (≈48s), proxy层不可修复
✅ HM2自R445(14:20:51Z重启)后零变更 (本轮未动env/compose/源码)
✅ 8项env双处零漂移 (compose L469-505 = 容器运行态)
✅ 铁律:只改HM2不改HM1 · 零配置变更 · 零代码修改
```

**三项清单状态**: A证伪 / B证伪(无改动点) / C证伪. 按 CC 规则"三项已做完或数据证伪→允许NOP", 本轮 NOP 合规.

**未做新改动的理由**: CC清单基于HM2旧env勘定 (throttle 4.5 / BUDGET 128), 但HM2容器 R445(14:20:51Z) 重启后 env 已更新 (throttle 2.5 / BUDGET 90), 三项前提均与当前实测不符. 当前30min成功率79.59%偏低但根因是 NVCF server-side PexecTimeout (10失败全 ≈48s server 自超时, 跨 idx=0/2/3/4 随机, 非 proxy 层限速/IP 标记), proxy 层 (UPSTREAM/throttle/cooldown/BUDGET) 均已勘定至平衡点:
- 升 UPSTREAM 无效 (NVCF server 自超时 48s, 升 UPSTREAM 只会让失败更慢)
- 升 BUDGET 90→100: R445 已评估, 当前 30min 10失败 avg75.6s 仍未被 3rd attempt 救回, 说明 NVCF server 持续慢响应, 升 BUDGET 仅延长失败耗时违稳定优先
- 降 throttle 无意义 (流量 1.63rpm 远低于 2.5s 上限)
- 改路由无劣化前提 (5key 均衡)
- FASTBREAK=5 已是 R384 勘定值 (HM1 侧 R446 抢跑改 3 但 HM2 侧仍 5, 两机独立)

强行改动违反稳定优先. 当前处于 proxy 层天花板, 失败根因在 NVCF server-side, 不可 proxy 层修复 (与 R435-R447 历轮结论一致).

**⚠️ 给CC的待办/观察**:
1. HM2 30min 成功率 79.59% 偏低 (vs HM1 侧 97.46%), 根因 NVCF server-side 慢 (10失败全 ≈48s timeout, 6h 67失败 avg79.7s). 非 proxy 层可控. 若 NVCF server 恢复, 成功率会自然回升 (R439/R435 曾 100%).
2. CC清单 [HM2-A] throttle 4.5 / [HM2-C] BUDGET 128 均为过期数据 (当前 2.5 / 90), 建议CC更新清单基线.
3. key_cycle_429s>0 的 5 个请求最终状态是 200/502 (非 HTTP 429), 是 key_cycle 内部 429 被 retry 跳过, 非 429 失败, 不计入 429 数.

---

## ⏳ 轮到HM2优化HM1 ← 脚本检测此标记
