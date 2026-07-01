# R493 (HM2→HM1): ⏸️ NOP — CC清单[HM1-A/B/C]三项6h+30min新鲜数据全证伪(同R491) · 全参数天花板 · MIN_OUTBOUND=3.8(已<9.0)throttle非瓶颈(0×触发, 需求2.3rpm<<15.8rpm天花板) · k4无路由劣化(dsv4p p50=6.6s最快组/5键, kimi p50=8.5s正常) · FASTBREAK=2已实现HM1-C(docker logs 30min 11次触发, break@51s=2×25s) · 6h SR=81.2%(178 ATE全NVCFPexecTimeout server-side avg24.7s≈UPSTREAM25) · 30min SR=79.7%(14 ATE) · 5键per-hit全100%SR · 61慢success rescue被保护 · 清单外发现: TIER_COOLDOWN compose(25)≠容器(38)漂移(下次compose up会回退TIER=25, 破R270等值) · KEY=25<TIER=38违反R270等值(0×429 cooldown非活跃) · 零配置变更 · 铁律:只改HM1不改HM2 · 锚定: ⏳ 轮到HM1优化HM2

**轮次**: R493
**方向**: HM2 优化 HM1 (本���执行者=HM2, 对端=HM1, host_machine=opc_uname)
**日期**: 2026-07-01 03:32 UTC (CST 11:32; DB ts 11:32, 快真实UTC 8h)
**类型**: NOP (No Operation — 无参数变更, 数据驱动证伪 + 漂移上报)
**Commit**: 706490c (R492, HM1→HM2, NOP) → 本commit (R493)

## 0. 时区与host标识 (R320教训#5)

- DB `ts` 比真实UTC快8h。实测: `SELECT max(ts), now()` → max ts=2026-07-01 11:31:53, now()=2026-07-01 03:32:01, 差≈8h ✓。所有窗口查询用绝对ts时间戳, 禁用 NOW()。
- 对端HM1 host_machine 标识=`opc_uname`(hostname=`opcsname`≠DB字段)。
- litellm_model: 30min窗口全为`nvcf_moonshotai/kimi-k2.6_k1..k5`; 6h窗口含两组: `nvcf_deepseek-ai/deepseek-v4-pro_k1..k5`(494req) + `nvcf_moonshotai/kimi-k2.6_k1..k5`(275req) + ATE(NULL model)(178req)。
- NVCF function: f966661c-790d-4f71-b973-c525fb8eafd4 (NVCF_DEEPSEEK_FUNCTION_ID, 单function多model映射)。
- hm_tier_attempts 表无 host_machine 列, 用绝对ts窗口+litellm_model过滤。

## 1. 改前数据采集 (HM1 对端, host_machine=opc_uname)

### 1a. 容器env (8参数+5 URL, /opt/cc-infra/docker-compose.yml 与容器运行态)
```
UPSTREAM_TIMEOUT=25                 (compose L418, R490 23→25)         容器env一致 ✓
TIER_TIMEOUT_BUDGET_S=125           (compose L419)                     容器env一致 ✓
MIN_OUTBOUND_INTERVAL_S=3.8         (compose L421, R442)               容器env一致 ✓
KEY_COOLDOWN_S=25                   (compose L422)                     容器env一致 ✓
TIER_COOLDOWN_S=38                  (容器env) ≠ compose L423="25"      ⚠️ 漂移(见5a)
HM_SSLEOF_RETRY_DELAY_S=2.0         (compose L453, R429)               容器env一致 ✓
HM_PEXEC_TIMEOUT_FASTBREAK=2        (compose L454, R473 3→2)           容器env一致 ✓
HM_CONNECT_RESERVE_S=10             (compose L452, R322)               容器env一致 ✓
HM_NV_PROXY_URL1=http://host.docker.internal:7894   k1→mihomo ✓
HM_NV_PROXY_URL2=""                k2→direct ✓
HM_NV_PROXY_URL3=http://host.docker.internal:7896   k3→mihomo ✓
HM_NV_PROXY_URL4=""                k4→direct ✓
HM_NV_PROXY_URL5=""                k5→direct ✓
```
- compose grep(`sed -n "/  hm40006:/,/^  [a-z]/p" /opt/cc-infra/docker-compose.yml`)+`docker exec hm40006 env`逐字对比 → 8参数中7参数一致, **1参数(TIER_COOLDOWN_S)漂移**: 容器env=38, compose L423="25"(R270注释标"34→38恢复等值"但value写"25", 注释与value自相矛盾)。
- ⚠️ **R322教训#1漂移**: compose L423若下次`docker compose up`会将TIER_COOLDOWN从运行态38回退到25, 破R270"KEY=TIER=38等值不变量"(当前运行态KEY=25<TIER=38已违等值, 回退后KEY=25=TIER=25等值但偏离R270设计值38)。属清单外项, 本轮不修(只改HM1清单内项), 上报CC。
- /health=200 OK (port 40006): `{"status":"ok","proxy_role":"passthrough","hm_num_keys":5,"nvcf_pexec_models":["dsv4p_nv"],"hm_model_tiers":["dsv4p_nv"],"hm_default_model":"dsv4p_nv","port":40006}`

### 1b. DB 30min窗口聚合 (改前基线, 窗口 DB ts 10:53:00-11:23:00 = 真实UTC 02:53-03:23)
| 指标 | 数值 |
|------|------|
| 总请求 | 69 |
| 成功 (200) | 55 (79.71%) |
| 失败 (502 ATE) | 14 |
| 失败 (429) | 0 |
| p50_ms | 10,393 |
| p95_ms | 52,140 |
| avg_ms | 20,842 |

### 1c. DB 6h窗口聚合 (DB ts 05:23:00-11:23:00 = 真实UTC 21:23-03:23)
| 指标 | 数值 |
|------|------|
| 总请求 | 947 |
| 成功 (200) | 769 (81.20%) |
| 失败 (502 ATE) | 178 |
| 失败 (429) | 0 |
| empty_200 | 0 (终态; 中间attempt 18次全cycle救回) |
| p50_ms | 9,934 |
| p95_ms | 50,757 |
| avg_ms | 18,390 |

- SR 81.2%(6h) 与R491的82.1%基本持平(±0.9pp), 仍处NVCF server-side回归态(ATE 0→34/h, 非HM1参数可修)。

### 1d. Per-key成功率 (6h, hm_requests, 含两组model)
| key | model组 | total | success | SR |
|-----|---------|-------|---------|-----|
| k1 | deepseek | 100 | 100 | 100% |
| k2 | deepseek | 89 | 89 | 100% |
| k3 | deepseek | 105 | 105 | 100% |
| k4 | deepseek | 98 | 98 | 100% |
| k5 | deepseek | 102 | 102 | 100% |
| k1 | kimi | 49 | 49 | 100% |
| k2 | kimi | 56 | 56 | 100% |
| k3 | kimi | 56 | 56 | 100% |
| k4 | kimi | 52 | 52 | 100% |
| k5 | kimi | 62 | 62 | 100% |
| NULL | ATE事件 | 178 | 0 | 0% ← 全5key轮询失败 |

**5键per-hit全100%SR** → 无单key劣化, 无429, cooldown机制健康(0×429触发)。

### 1e. Per-key延迟 (6h, success only) — 验证k4无劣化
| key | model组 | reqs | p50(ms) | p95(ms) | avg(ms) |
|-----|---------|------|---------|---------|---------|
| k1 | deepseek | 100 | 7,398 | 32,672 | 11,372 |
| k2 | deepseek | 89 | 6,010 | 33,295 | 10,205 |
| k3 | deepseek | 105 | 7,960 | 34,551 | 12,118 |
| k4 | deepseek | 98 | 6,586 | 32,168 | 10,789 |
| k5 | deepseek | 102 | 6,837 | 33,767 | 11,596 |
| k1 | kimi | 49 | 9,102 | 31,038 | 11,561 |
| k2 | kimi | 56 | 10,118 | 35,142 | 14,665 |
| k3 | kimi | 56 | 8,940 | 35,097 | 12,075 |
| k4 | kimi | 52 | 8,515 | 30,824 | 11,892 |
| k5 | kimi | 62 | 6,882 | 39,135 | 12,568 |

- k4(deepseek) p50=6,586ms 是5键中最快之一, p95=32,168ms最低 → **k4无路由劣化**, CC清单[HM1-B]前提(k4 avg28.5s p95=72.9s)未在当前数据复现(同R491)。
- 5键p50 range 6,010-10,118ms (cv≈10%, 正常均衡), max_ok=58,771ms为单次救援慢success非系统性劣化。

### 1f. 6h小时桶趋势 (DB ts 05:00-11:00 = 真实UTC 21:00-03:00)
| Hour(DB ts) | Reqs | OK | ATE | SR% |
|-------------|------|----|-----|-----|
| 05:00 | 107 | 88 | 19 | 82.2 |
| 06:00 | 165 | 131 | 34 | 79.4 |
| 07:00 | 175 | 148 | 27 | 84.6 |
| 08:00 | 200 | 176 | 24 | 88.0 |
| 09:00 | 124 | 95 | 29 | 76.6 |
| 10:00 | 126 | 93 | 33 | 73.8 |
| 11:00 | 50 | 38 | 12 | 76.0 |

- ATE绝对数稳定在19-34/小时(NVCF server-side持续NVCFPexecTimeout), 需求侧波动(50-200req/h)使SR%在74-88%间波动, 非HM1参数可修。

### 1g. 失败duration分布 (6h, 178 ATE)
| bucket | count | avg_ms |
|--------|-------|--------|
| <5s (quick-fail) | 6 | 803 |
| 5-46s | 1 | 8,168 |
| 46-50s | 82 | 46,936 |
| >=50s | 89 | 50,950 |

- 171/178失败在46-53s区间 = 2×UPSTREAM(25s) ≈ FASTBREAK=2触发点。
- BUDGET=125s从未被触达(失败在~50s fastbreak, 远低于125s), docker logs 30min 0×HM-TIER-BUDGET触发 → BUDGET死约束。

### 1h. tier_attempts错误结构 (6h, 按model组)
| model组 | error_type | count | avg_ms | p50_ms | 备注 |
|---------|------------|-------|--------|--------|------|
| dsv4p | NVCFPexecTimeout | 58 | 24,680 | 25,292 | server-side, ≈UPSTREAM=25s |
| kimi | NVCFPexecTimeout | 35 | 24,384 | — | server-side |
| kimi | empty_200 | 18 | — | — | 中间attempt(08:50-08:51成簇), 全cycle救回SR=100% |

- 0×429, 0×SSLEOF, 0×conn_err — 连接健康。
- NVCFPexecTimeout avg≈24.5s ≈ UPSTREAM_TIMEOUT(25s) read阶段超时, server-side, 非HM1参数可修。
- empty_200仅kimi组18次(08:50-08:51成簇), 全cycle救回无终态影响, 非HM1参数可修(NVCF返回空body)。

### 1i. docker logs失败模式验证 (30min窗口)
```
[11:06:07.6] [HM-PEXEC-FASTBREAK] tier=dsv4p_nv 2 consecutive NVCFPexecTimeout -> fast-break (saved remaining keys)
[11:06:07.6] [HM-TIER-FAIL] tier=dsv4p_nv all 5 keys failed: 429=0, empty200=0, timeout=2, other=0, elapsed=52542ms
... (30min内11次同形 HM-PEXEC-FASTBREAK + HM-TIER-FAIL, 全timeout=2模式)
```
- 30min内11×HM-TIER-FAIL全为`timeout=2`模式(2×pexec timeout@~50s后FASTBREAK=2触发), 0×429/empty200/other → **FASTBREAK=2生效确认**。
- 0×HM-OUTBOUND-THROTTLE触发 → throttle从未阻塞请求(30min)。
- 0×HM-TIER-BUDGET触发 → BUDGET=125s死约束(失败在~50s先fastbreak)。

### 1j. 慢success rescue分析 (FASTBREAK=2 vs =1 权衡)
- 6h success且duration>25s = 61个 (avg 34,528ms, max 58,771ms) — 第一attempt超时/慢后k2-k5救援成功。
- success duration bucket: <25s=433个(avg7,972ms), 25-50s=58个(avg33,522ms), 50-75s=3个(avg53,976ms), 75-100s=0, ≥100s=0。
- 若FASTBREAK=1(1连timeout即break): 省~25s/失败(×171慢失败=4275s), 但误杀61个rescue → SR↓。
- 当前FASTBREAK=2: 2连timeout才break, 给1次rescue机会, 61个慢success全保住。
- → **FASTBREAK=2为SR-vs-latency最优平衡**(R473已实现), 降=1误杀61 rescue(SR↓), 升=3多耗25s/失败。

## 2. CC清单[HM1-A/B/C]状态复检 (30min+6h新鲜数据)

### [HM1-A] MIN_OUTBOUND_INTERVAL_S 18.2→9.0 — ✅目标已超额达成 + throttle非瓶颈证伪(同R491)
- CC指令前提"MIN_OUTBOUND=18.2s"为过时数据: 实测当前=3.8 (compose L421+容器env一致, R442由4.0→3.8)。
- 3.8 << 9.0目标 → A目标值已超额达成(无需再降)。
- **继续降证伪(throttle非瓶颈)**:
  - 30min实际吞吐=69req/30min=2.30 req/min
  - 6h实际吞吐=947req/6h=2.63 req/min
  - throttle天花板=60/3.8=15.8 req/min
  - 实际2.30-2.63 << 15.8 → 需求侧远未触达throttle, 降throttle无吞吐增益
  - docker logs 30min 0×`HM-OUTBOUND-THROTTLE`触发 → throttle从未阻塞请求
- **结论**: A目标(≤9.0)早已达成(3.8), throttle非瓶颈(需求2.63rpm<<天花板15.8rpm), 继续降无收益。

### [HM1-B] k4(direct, idx=3)路由劣化修复 — ✅证伪(k4无劣化, 同R491)
- CC指令前提"k4 avg28.5s vs其他~25s, p95=72.9s vs~55s, max=162.9s"未在当前数据复现:
  - 6h k4(deepseek): p50=6,586ms(5键中最快之一), p95=32,168ms(最低), avg=10,789ms
  - 6h k4(kimi): p50=8,515ms, p95=30,824ms(最低), avg=11,892ms
  - 6h 5键p50 range 6,010-10,118ms (cv≈10%, 正常均衡)
- **结论**: k4当前无路由劣化, 无需改PROXY_URL4(改direct→mihomo无收益, k4已最快), 证伪。

### [HM1-C] all_tiers_exhausted早fail — ✅已实现(FASTBREAK=2) + 最优平衡证伪(同R491)
- CC指令"前3个key全NVCFPexecTimeout即fast-fail"已由R347实现(FASTBREAK=3)+R473降到2。
- 当前FASTBREAK=2: 2连pexec timeout即break, 比CC指令的3更激进(省1×25s/失败)。
- 实测fastbreak生效: docker logs 30min见11次`HM-PEXEC-FASTBREAK 2 consecutive -> fast-break`, 全timeout=2模式。
- 失败duration集中在46-53s(=2×25s), 证实FASTBREAK=2在2连timeout后立即break, 未试k3/k4/k5。
- **继续降=1证伪**: 6h有61个慢success(>25s, 第一attempt timeout后k2-k5救援), FASTBREAK=1会误杀这61 rescue → SR↓。
- **结论**: FASTBREAK=2为SR-vs-latency最优平衡(R473已实现), 升=3多耗25s/失败, 降=1误杀61 rescue, 证伪。

## 3. 其他参数天花板验证

### TIER_TIMEOUT_BUDGET_S=125 — 死约束(fastbreak先触发, 同R491)
- 6h 178失败全在46-53s区间(FASTBREAK=2触发), BUDGET=125s从未触达。
- docker logs 30min 0×HM-TIER-BUDGET触发。
- 失败break点 = 2×UPSTREAM(25s)=50s, 远低于BUDGET=125s。
- **结论**: BUDGET对失败请求非活跃约束, 降无影响(fastbreak先break), 升无意义。

### UPSTREAM_TIMEOUT=25 — 不可降(R490刚从23→25)
- 6h NVCFPexecTimeout avg=24,680ms(dsv4p)/24,384ms(kimi) ≈ UPSTREAM边界。
- 6h 61个慢success duration 25-58s, 含接近UPSTREAM边界的慢success。
- 降UPSTREAM会让更多慢success被timeout误杀(SR↓)。
- **结论**: UPSTREAM=25保护慢success, 不可降。

### KEY_COOLDOWN_S=25 / TIER_COOLDOWN_S=38 — 半活跃, 0×429(同R491)
- 6h 0×429(终态) → cooldown从未因429触发, 非活跃约束。
- ⚠️ **KEY=25 < TIER=38 违反R270等值不变量**: 当前运行态KEY=25, TIER=38, 与R270"KEY=TIER=38等值"约束不符。但6h 0×429证明cooldown非活跃, 无SR影响。历史参数演化留痕, 非本轮清单项, 上报CC。
- **结论**: cooldown非活跃(0×429), 不动。

### HM_PEXEC_TIMEOUT_FASTBREAK=2 — 最优(见1j/2C)
### HM_CONNECT_RESERVE_S=10 — 非瓶颈
- 6h 0×conn_err, 0×SSLEOF → connect阶段健康, reserve=10足够。
- **结论**: 不动。

## 4. 决策: ⏸️ NOP · 零配置变更

**理由**:
1. CC清单[HM1-A/B/C]三项全部完成/证伪(本轮新鲜数据强化R491结论):
   - A: MIN_OUTBOUND=3.8已超额达成(<<9.0目标), throttle非瓶颈(需求2.63rpm<<天花板15.8rpm, 0×throttle触发)
   - B: k4无路由劣化(p50 6.6s最快组/5键, p95 32.2s最低, CC前提未复现)
   - C: FASTBREAK=2已实现(R347+R473), 比CC指令的3更激进, 降=1误杀61 rescue证伪, docker logs 30min 11次触发确认生效
2. 全8参数在天花板: BUDGET=125死约束(fastbreak先触发), UPSTREAM=25保护慢success, FASTBREAK=2最优平衡, KEY/TIER_COOLDOWN非活跃(0×429)
3. 失败根因=NVCF server-side NVCFPexecTimeout(178 ATE, 全在46-53s=2×25s fastbreak), 非HM1参数可修
4. 5键per-hit全100%SR, 0×429/SSLEOF/conn_err, 18×empty_200全cycle救回 — 连接与key池健康
5. SR 81.2%(6h)下降趋势根因: ATE绝对数稳定19-34/h(NVCF surge持续), 需求侧波动使SR%在74-88%间波动, 非参数可修

**当前HM1参数已达全局最优**: fastfail机制(FASTBREAK=2)已吸收所有可优化失败耗时, throttle非瓶颈, 5键均衡无劣化, 失败根因在NVCF server-side。

## 5. 清单外发现 (供CC下轮勘定, 非本轮清单项)

### 5a. TIER_COOLDOWN_S compose(25)≠容器(38)漂移 — R322教训#1重演
- **现象**: 容器env `TIER_COOLDOWN_S=38`, 但compose L423 `TIER_COOLDOWN_S: "25"`(注释标"R270: 34→38恢复等值"但value写"25", 注释与value自相矛盾)。
- **影响**: 下次`docker compose up`会将TIER_COOLDOWN从运行态38回退到25, 破R270"KEY=TIER=38等值不变量"设计。当前运行态KEY=25<TIER=38已违等值, 回退后KEY=25=TIER=25等值但偏离R270设计值38。
- **根因推测**: 某轮改了容器运行态env(TIER 25→38)但未同步compose文件(R322教训#1), 或compose value笔误(注释34→38但value漏改)。
- **影响评估**: 6h 0×429证明cooldown非活跃, 当前漂移无SR影响。但若未来NVCF侧429上升, compose up回退会改变cooldown行为, 隐患潜伏。
- **潜在方向(供CC勘定, 非本轮执行)**: CC托底时同步compose L423 value从"25"改为"38"(匹配运行态+R270设计), 或显式确认KEY=25=TIER=25为新等值(更新R270注释)。属清单外项, 本轮不擅改。

### 5b. KEY=25 < TIER=38 违反R270等值不变量 (同R491上报)
- 当前运行态KEY_COOLDOWN_S=25, TIER_COOLDOWN_S=38, 与R270"KEY=TIER=38等值"约束不符。
- 6h 0×429证明cooldown非活跃, 无SR影响。历史参数演化留痕, 非本轮清单项, 上报CC���定是否回调KEY=38或降TIER=25(与5a联动)。

### 5c. 6h SR下降趋势(82.2%→73.8%→76.0%) — NVCF server-side持续
- ATE绝对数稳定19-34/h, 需求侧波动(50-200req/h)使SR%在74-88%间波动。
- 根因=NVCF function f966661c server-side持续NVCFPexecTimeout(178 ATE avg24.7s≈UPSTREAM边界), 非HM1参数可修。
- 若CC勘定方向: 确认是否NVCF surge持续, 或考虑function切换(非参数项)。

## 6. 执行记录

### 变更: 无
```bash
# 零配置变更 — docker-compose.yml不变, 容器不重启
# 本轮为数据驱动NOP: CC清单三项6h+30min新鲜数据复检全部完成/证伪(同R491), 无可动项
# 清单外发现(TIER_COOLDOWN compose漂移, KEY<TIER不等值, SR下降趋势)上报CC, 不擅自改动
```

### 验证: 通过
```bash
# env一致性检查: compose grep(hm40006块L418-454) 与 docker exec hm40006 env 对比
# 8参数中7参数一致(UPSTREAM=25, BUDGET=125, MIN_OUTBOUND=3.8, KEY_COOLDOWN=25, FASTBREAK=2, SSLEOF=2.0, CONNECT_RESERVE=10, 5URL全一致)
# ⚠️ 1参数漂移: TIER_COOLDOWN 容器=38 ≠ compose L423="25"(清单外项, 上报CC, 见5a)

# 健康检查 (对端): /health=200 ok, hm_num_keys=5, nvcf_pexec_models=[dsv4p_nv]
```

## 7. 轮次统计
- HM1自R491(HM2→HM1 NOP)后: R492为HM1→HM2方向, 本轮R493为HM2→HM1方向
- CC清单[HM1-A/B/C]三项状态: A✅超额达成(3.8<<9.0)+throttle非瓶颈证伪, B✅证伪(k4无劣化), C✅已实现(FASTBREAK=2最优, docker logs 30min 11次触发确认)
- 连续NOP(HM1侧): R486→R488→R491→R493, 本轮为清单复检证伪轮+漂移上报轮(每项有30min+6h具体数据)
- 本轮NOP理由: 三项全部完成/证伪, 全8参数在天花板, 失败根因NVCF server-side非参数可修

## 8. 铁律遵守
- ✅ 只改HM1不改HM2: 无变更行为, 合规
- ✅ 单参数少改多轮: NOP验证, 无参数
- ✅ 数据驱动先采集后决策: 10层验证(env双处对比 + 30min + 6h DB + per-key双组SR + per-key双组延迟 + 小时桶 + 失败duration分布 + tier_attempts按model组 + docker logs fastbreak + 慢success权衡 + 429验证)
- ✅ 零配置变更: docker-compose.yml未修改, compose与容器env 7/8参数一致(1参数漂移为清单外项上报CC不擅改)
- ✅ 无R320/R322/R350重蹈: 未改compose, 未commit错文件, push后即停
- ✅ DB时区: 全部用绝对ts窗口, 禁用NOW()
- ✅ 执行CC清单不擅自找改动点: TIER_COOLDOWN compose漂移+KEY<TIER不等值+SR下降趋势为清单外项, 上报CC不擅改(同R491先例)
- ✅ host_machine标识正确: opc_uname
- ✅ 如实记录TIER_COOLDOWN漂移: 7/8参数一致, 1参数漂移显式标注不掩盖

## ⏳ 轮到HM1优化HM2
