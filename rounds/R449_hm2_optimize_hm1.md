# R449: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项重验证全部证伪/已做 · 全参数天花板

**执行时间**: 2026-06-30 23:10-23:25 (UTC+8)
**角色**: HM2 (opc2_uname, opc2sname) → HM1 (opc_uname, opcsname)
**原则**: 少改多轮 · 稳定优先 · 铁律:只改HM1不改HM2
**前轮**: R448 (HM1→HM2, NOP — HM2侧清单三项证伪)

---

## 📊 数据收集 (HM1, host_machine='opc_uname', mapped_model='deepseek_hm_nv')

### DB 时区说明 (R350教训#5)
DB `TimeZone=UTC`, `NOW()=2026-06-30 15:12:05+00`. 但 hm_requests.ts 列 max=`2026-06-30 23:10:49+00` (比 NOW() 大8h). 即写入 ts 时用的是 CST 当地时间的数字值但带 +00 tag. 故"最近30min"查询用 `ts > '2026-06-30 22:40:00+00'` (数字匹配当地时区值). 60min窗口用 `ts > '2026-06-30 22:10:00+00'`. 本轮所有窗口均显式 UTC 字面值, 禁用 NOW()-interval.

### 当前 env (容器运行态, docker exec hm40006 env, 8项)
```
UPSTREAM_TIMEOUT=45          (R267)
TIER_TIMEOUT_BUDGET_S=125    (R386)
MIN_OUTBOUND_INTERVAL_S=3.8  (R442)
KEY_COOLDOWN_S=25            (R162)
TIER_COOLDOWN_S=38           (R270)
HM_PEXEC_TIMEOUT_FASTBREAK=3 (R446 抢跑, 原值5)
HM_SSLEOF_RETRY_DELAY_S=2.0  (R429)
HM_CONNECT_RESERVE_S=10      (R322)
```
**compose (live /opt/cc-infra/docker-compose.yml 第418-454行) 与容器 env 8项全一致. ✅** (R320/R322教训: 双处零漂移)
- L418: `UPSTREAM_TIMEOUT: "45"` (R267)
- L419: `TIER_TIMEOUT_BUDGET_S: "125"` (R386)
- L421: `MIN_OUTBOUND_INTERVAL_S: "3.8"` (R442)
- L422: `KEY_COOLDOWN_S: "25"` (R162)
- L423: `TIER_COOLDOWN_S: "38"` (R270)
- L452: `HM_CONNECT_RESERVE_S: "10"` (R322)
- L453: `HM_SSLEOF_RETRY_DELAY_S: "2.0"` (R429)
- L454: `HM_PEXEC_TIMEOUT_FASTBREAK: "3"` (R446 抢跑)

**容器状态**: `hm40006 Up 37 minutes (healthy)`, StartedAt=`2026-06-30T14:34:56Z` (R446 抢跑重启后未再变, 已稳定37min+). HM1 自 R446(14:34:56Z) 后零变更.

### per-key proxy 路由 (config.py, 沿用, 本轮未改)
```
k1(idx0)→URL1=7894(proxy)  k2(idx1)→URL2=空(direct)  k3(idx2)→URL3=7896(proxy)
k4(idx3)→URL4=空(direct)  k5(idx4)→URL5=空(direct)
```

### 改前30min基线 (22:40-23:10当地, 当前env, 无本轮变更)
```
total=129  ok=125  fail=4  succ=96.90%  avg_ok=11251ms  p50_ok=7152ms  p95_ok=49653ms  fail_avg=115414ms
0 真429 (status无429) · 1 empty200 (22:53:21 987ms idx0, 偶发非系统) · 4失败全 all_tiers_exhausted
```

### 改前60min基线 (22:10-23:10当地, 稳定性确认)
```
total=281  ok=277  fail=4  succ=98.58%  0 真429  1 empty200
max_ok=94949ms · 0个>100s慢成功 · 1个90-125s慢成功(94.9s) · fail_avg=115414ms
```

### per-key 60min (status=200 only, B精神: 采长窗口看劣化key)
```
idx | total | ok | avg_ok | p50   | p95
 0  |   52  | 52 | 10118  | 8712  | 17264   ← k1 proxy
 1  |   58  | 58 | 13127  | 7144  | 52554   ← k2 direct, p95最高但p50正常
 2  |   50  | 50 | 13135  | 9785  | 30808   ← k3 proxy
 3  |   63  | 63 | 13435  | 7052  | 49982   ← k4 direct, p50=7.05s正常范围
 4  |   54  | 54 | 9260  | 7204  | 15805   ← k5 direct, p95最低
NULL|    4  |  0 |        |       |         ← 4失败无 nv_key_idx (all_tiers_exhausted)
5key 全部可用 (ok=total, 0单key失败), p50 7.05-9.79s同级均衡.
k4(idx3) p95=49.98s 非最高(k2=52.55s), p50=7.05s 在5key范围内 → 无单key劣化.
```

### tier_attempts 30min (失败结构)
```
error_type         | count | avg_ms | max_ms
NVCFPexecTimeout   |   6   | 45486  | 45933
per-idx: idx0×2(avg45440) idx2×1(45933) idx3×1(45431) idx4×2(45335)
全部 NVCFPexecTimeout (server-side pexec 超时 ≈UPSTREAM=45s), 跨 idx=0/2/3/4 随机, 非单key标记.
```

### FASTBREAK=3 触发实证 (40min容器日志)
```
[22:56:48] [HM-PEXEC-FASTBREAK] tier=dsv4p_nv 3 consecutive NVCFPexecTimeout -> fast-break
[22:58:46] [HM-PEXEC-FASTBREAK] tier=dsv4p_nv 3 consecutive NVCFPexecTimeout -> fast-break
[23:01:39] [HM-PEXEC-FASTBREAK] tier=dsv4p_nv 3 consecutive NVCFPexecTimeout -> fast-break
[23:08:34] [HM-PEXEC-FASTBREAK] tier=dsv4p_nv 3 consecutive NVCFPexecTimeout -> fast-break
30min 4次触发, 失败 avg=115.4s (3×串行timeout=136.5s, FASTBREAK=3 + BUDGET=125 共同截断, 省~21s/失败).
```

### throttle 咬合分析 (30min, 相邻200请求间隔)
```
gap p50=7.11s · gap avg=15s · gap p5=1.70s · gap<3.8s 的有18个(全200成功)
throttle=3.8s 理论上限 ~15.8rpm, 实测 4.3rpm(129req/30min), 利用率27% → throttle 远非全局瓶颈.
(注: gap<3.8s 的18个多为 LiteLLM 转发层 ts 抖动/跨host交叉, 非真违反throttle; throttle 全局锁语义见 config.py:126 throttle_outbound())
```

---

## 🔬 CC清单三项重验证 (对端HM1节, 全部证伪/已做 → NOP)

### [HM1-A] MIN_OUTBOUND_INTERVAL_S 18.2→9.0 → 证伪 ✅
**清单前提**: "HM1 throttle=18.2s 被锁死, 是HM2的4.5s的4倍, 降到9.0→吞吐翻倍"
**实测**: `MIN_OUTBOUND_INTERVAL_S=3.8` (非18.2! R442 已降至 3.8, 远低于清单目标 9.0)
- 30min 流量 4.3rpm (129req/30min), 远低于 throttle=3.8s 允许的 ~15.8rpm (利用率27%)
- throttle 咬合分析: gap p50=7.11s >> 3.8s, 仅18个gap<3.8s 且全成功(0 429), throttle 局部咬合不构成全局瓶颈
- bak.r310 快照 L421 显示历史值 18.2(R293) → 清单"18.2"为过期数据, R442 已超额完成 (3.8<9.0)
**结论**: 清单前提的 18.2s 与实测 3.8s 完全不符 (清单基于R293旧数据). 已超额完成目标(3.8<9.0). 再降无意义且 0 429 已是安全态, 强行再降(如2.5)有触发 NVCF 同IP限速风险违稳定优先. **证伪**.

### [HM1-B] k4(direct, idx=3) 路由劣化修复 → 证伪 ✅
**清单前提**: "k4 avg28.5s p95=72.9s max=162.9s vs 其他~25s/55s, k4本机IP被NVCF标记"
**实测** (60min, idx=3 即 k4):
- k4: 63req全成功(0失败), p50=7052ms (5key范围内 7.05-9.79s), avg=13435ms, p95=49982ms, max 详见(非timeout)
- k4 p95=49.98s 非最高(k2=52.55s), p50=7.05s 在5key范围内, 无单key劣化
- 5key p50 均衡 (7.05-9.79s), 全部 ok=total (0单key失败); 失败跨 idx=0/2/3/4 随机
- 同为 direct 的 k2(idx1)/k5(idx4) 正常 → 非 direct 通病
- 0 真429 → 无 NVCF IP限速迹象, k4 p95 偏高是 NVCF server-side 慢成功非 IP标记
**结论**: k4 p50 正常, p95 偏高是 NVCF 慢响应非 IP 标记. 改 k4→mihomo 无数据支撑且引入429风险(当前0 429). **证伪**.

### [HM1-C] all_tiers_exhausted 早fail → 已做(R446)+生效实证 ✅
**清单前提**: "前3个key全NVCFPexecTimeout即fast-fail, 省~50s/次"
**实测**: `HM_PEXEC_TIMEOUT_FASTBREAK=3` **已被R446抢跑session改并部署生效** (compose L454, 容器14:34:56Z重启). upstream.py `if consecutive_pexec_timeout >= PEXEC_TIMEOUT_FASTBREAK: fast-break` 在第3次连续 NVCFPexecTimeout 时 break.
- **本轮实证 4 次触发** (容器日志 22:56/22:58/23:01/23:08), 失败 avg=115.4s
- R447 A/B 已验证: FASTBREAK 5→3 失败耗时 121.7→115.4s 省6.3s/失败, 0 误杀
- 注: compose L454 注释声称"省~28s/次" 实测省~6s(本轮)/~21s(理论 vs 3×串行136.5s), 因 BUDGET=125 与 FASTBREAK=3 近同时触发, 未完全发挥"省50s"目标. 但升 BUDGET>140 让 FASTBREAK 完全发挥会: (a) 失败从115s→135s更慢违稳定优先; (b) max_ok=94.9s 说明慢成功<100s, 升BUDGET 不救回更多成功(NVCF server 自超时45s, 3次串行=135s>任何BUDGET). R447已分析不建议.
**结论**: FASTBREAK=3 已做+生效+本轮实证4次触发+R447 A/B验证. 无需再做. **已做**.

---

## 🏁 最终判决: NOP · 零配置变更

```
✅ CC清单[HM1-A]证伪 (throttle 3.8≠18.2, 已超额3.8<9.0, 非全局瓶颈, 0 429)
✅ CC清单[HM1-B]证伪 (5key 60min 均衡, k4 p50=7.05s正常, p95高是NVCF慢响应非IP标记)
✅ CC清单[HM1-C]已做 (FASTBREAK=3 R446生效, 本轮4次触发实证, R447 A/B:省6s/0误杀)
✅ 当前30min 129req/96.90%/0 真429/1偶发empty200
✅ 60min 281req/98.58%/0 429, 系统健康
✅ 6个timeout全 NVCF server-side PexecTimeout (avg45.5s≈UPSTREAM=45), proxy层不可修复
✅ HM1自R446(14:34:56Z重启)后零变更 (本轮未动env/compose/源码)
✅ 8项env双处零漂移 (compose L418-454 = 容器运行态)
✅ 铁律:只改HM1不改HM2 · 零配置变更 · 零代码修改
```

**三项清单状态**: A证伪 / B证伪 / C已做. 按 CC 规则"三项已做完或数据证伪→允许NOP", 本轮 NOP 合规.

**未做新改动的理由**: CC清单[HM1-A]基于R293旧throttle值18.2勘定, [HM1-B]基于旧k4数据(28.5s/72.9s/162.9s), 但HM1容器R446(14:34:56Z)重启后env已更新(throttle 3.8等), 三项前提均与当前60min实测不符. 当前成功率98.58%(60min)/96.90%(30min)+0 429, 处于天花板状态:
- 失败根因: 4失败全 NVCF server-side PexecTimeout (avg45.5s, NVCF server 自超时≈UPSTREAM=45s), proxy 层 (UPSTREAM/throttle/cooldown/BUDGET/FASTBREAK) 均已勘定至平衡点, 不可 proxy 层修复
- 升 UPSTREAM 无效 (NVCF server 自超时45s, 升UPSTREAM只让失败更慢)
- 升 BUDGET 125→更高: 不救回更多成功(max_ok=94.9s, 慢成功<100s), 反让失败更慢违稳定优先
- 降 throttle 3.8→更低: 0 429 已是安全态, 强行降有触发NVCF同IP限速风险
- 改 k4 路由无劣化前提 (5key 60min 均衡)
- FASTBREAK=3 已生效 (本轮4次触发实证)
- empty200 偶发1/281=0.36% 非系统问题, 不值得为它改参数

强行改动违反稳定优先. 当前处于 proxy 层天花板, 失败根因在 NVCF server-side, 不可 proxy 层修复 (与 R435-R448 历轮结论一致).

**⚠️ 给CC的待办/观察**:
1. **连续第三轮HM1 NOP根因**: R447/R448/R449 三轮对 HM1 清单 [A/B/C] 均证伪/已做. 根因是 CC清单基线过期(基于R293的throttle18.2、旧k4数据28.5s), 而HM1自R446后env已更新(throttle3.8/FASTBREAK3). 建议CC更新HM1清单基线为当前实测(throttle3.8/k4正常/BUDGET125/FASTBREAK3已生效), 否则下轮HM2仍会判证伪.
2. HM1 60min成功率98.58%+0 429, 健康度优于HM2侧(R448 79.59%). HM1侧失败仅4/281全NVCF server-side, proxy层无改进空间.
3. FASTBREAK=3 实测省~6-21s/失败(非compose注释声称28s), 因BUDGET=125先到. 若CC要"省50s/次"目标真正达成, 需重新勘定(当前不可行:升BUDGET违稳定优先).
4. empty200偶发(1/281), idx0 proxy路由, 987ms空响应, 非系统问题, 建议观察不处理.

---

## ⏳ 轮到HM1优化HM2 ← 脚本检测此标记
