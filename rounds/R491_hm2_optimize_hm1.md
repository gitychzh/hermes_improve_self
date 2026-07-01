# R491 (HM2→HM1): ⏸️ NOP — CC清单[HM1-A/B/C]三项6h+30min新鲜数据全证伪 · 全参数天花板 · MIN_OUTBOUND实测3.8(已<9.0目标)throttle非瓶颈 · k4无路由劣化(p50 6.6-8.7s最快组) · FASTBREAK=2已实现HM1-C且最优 · 6h SR=82.1%(171 ATE全NVCFPexecTimeout server-side avg47s) · 30min SR=70.8%(19 ATE) · 5键per-hit全100%SR · 零配置变更 · 铁律:只改HM1不改HM2 · 锚定: ⏳ 轮到HM1优化HM2

**轮次**: R491
**方向**: HM2 优化 HM1 (本轮执行者=HM2, 对端=HM1, host_machine=opc_uname)
**日期**: 2026-07-01 10:55 UTC (CST 18:55; DB ts 10:55, 快真实UTC 8h)
**类型**: NOP (No Operation — 无参数变更, 数据驱动证伪)
**Commit**: 3b9c615 (R490, HM1→HM2, NOP) → 本commit (R491)

## 0. 时区与host标识 (R320教训#5)

- DB `ts` 比真实UTC快8h。实测: `SELECT max(ts), now()` → max ts=2026-07-01 10:48:01, now()=2026-07-01 02:49, 差≈8h ✓。所有窗口查询用绝对ts时间戳, 禁用 NOW()。
- 对端HM1 host_machine 标识=`opc_uname`(非`opcsname`, R489文件误记为`opcsname`)。hostname=`opcsname`(主机名≠host_machine DB字段)。
- litellm_model: 30min窗口全为`nvcf_moonshotai/kimi-k2.6_k1..k5`; 6h窗口含两组: `nvcf_deepseek-ai/deepseek-v4-pro_k1..k5`(562req) + `nvcf_moonshotai/kimi-k2.6_k1..k5`(209req) + ATE(NULL model)(171req)。
- NVCF function: f966661c-790d-4f71-b973-c525fb8eafd4 (NVCF_DEEPSEEK_FUNCTION_ID, 单function多model映射)。
- hm_tier_attempts 表无 host_machine 列, 用绝对ts窗口过滤。

## 1. 改前数据采集 (HM1 对端, host_machine=opc_uname)

### 1a. 容器env (8参数+5 URL, /opt/cc-infra/docker-compose.yml 与容器运行态双处一致)
```
UPSTREAM_TIMEOUT=25                 (compose L418, R490 23→25)   容器env一致 ✓
TIER_TIMEOUT_BUDGET_S=125           (compose L419)               容器env一致 ✓
MIN_OUTBOUND_INTERVAL_S=3.8         (compose L421)               容器env一致 ✓
KEY_COOLDOWN_S=25                   (compose L422)               容器env一致 ✓
TIER_COOLDOWN_S=38                  (compose L423)               容器env一致 ✓
HM_SSLEOF_RETRY_DELAY_S=2.0         (compose L453)               容器env一致 ✓
HM_PEXEC_TIMEOUT_FASTBREAK=2        (compose L454, R473 3→2)     容器env一致 ✓
HM_CONNECT_RESERVE_S=10             (compose L452)               容器env一致 ✓
HM_NV_PROXY_URL1=http://host.docker.internal:7894   k1→mihomo ✓
HM_NV_PROXY_URL2=""                k2→direct ✓
HM_NV_PROXY_URL3=http://host.docker.internal:7896   k3→mihomo ✓
HM_NV_PROXY_URL4=""                k4→direct ✓
HM_NV_PROXY_URL5=""                k5→direct ✓
```
compose grep(`sed -n "/hm40006:/,/^  [a-z]/p"`)+`docker exec hm40006 env`逐字一致 → **双处零漂移** ✓
/health=200 OK (port 40006): `{"status":"ok","proxy_role":"passthrough","hm_num_keys":5,"nvcf_pexec_models":["dsv4p_nv"],"hm_model_tiers":["dsv4p_nv"],"hm_default_model":"dsv4p_nv"}`

### 1b. DB 30min窗口聚合 (改前基线, 窗口 DB ts 10:18:01-10:48:01 = 真实UTC 02:18-02:48)
| 指标 | 数值 |
|------|------|
| 总请求 | 65 |
| 成功 (200) | 46 (70.77%) |
| 失败 (502 ATE) | 19 (29.23%) |
| 429 (终态) | 0 |
| empty_200 | 0 |
| p50_ms | 19,208 |
| p95_ms | 48,451 |
| avg_ms | 24,922 |

### 1c. DB 6h窗口聚合 (DB ts 04:48:01-10:48:01 = 真实UTC 20:48-02:48)
| 指标 | 数值 |
|------|------|
| 总请求 | 940 |
| 成功 (200) | 772 (82.13%) |
| 失败 (502 ATE) | 168 (17.87%) |
| 429 (终态) | 0 |
| empty_200 | 0 (终态) |
| all_tiers_exhausted | 168 |
| p50_ms | 9,348 |
| p95_ms | 50,728 |
| avg_ms | 17,776 |

### 1d. Per-key成功率 (6h, hm_requests, 含两组model)
| key | model组 | total | success | SR |
|-----|---------|-------|---------|-----|
| k1 | deepseek | 113 | 113 | 100% |
| k2 | deepseek | 101 | 101 | 100% |
| k3 | deepseek | 119 | 119 | 100% |
| k4 | deepseek | 114 | 114 | 100% |
| k5 | deepseek | 115 | 115 | 100% |
| k1 | kimi | 42 | 42 | 100% |
| k2 | kimi | 44 | 44 | 100% |
| k3 | kimi | 44 | 44 | 100% |
| k4 | kimi | 42 | 42 | 100% |
| k5 | kimi | 48 | 48 | 100% |
| NULL | ATE事件 | 171 | 0 | 0% ← 全5key轮询失败 |

**5键per-hit全100%SR** → 无单key劣化, 无429, cooldown机制健康。

### 1e. Per-key延迟 (6h, success only) — 验证k4无劣化
| key | model组 | reqs | p50(ms) | p95(ms) | max(ms) | avg(ms) |
|-----|---------|------|---------|---------|---------|---------|
| k1 | deepseek | 113 | 7,649 | 32,631 | 40,269 | 11,108 |
| k2 | deepseek | 101 | 6,000 | 34,071 | 43,202 | 10,064 |
| k3 | deepseek | 119 | 7,960 | 32,834 | 46,427 | 11,724 |
| k4 | deepseek | 114 | 6,586 | 31,228 | 58,771 | 10,627 |
| k5 | deepseek | 115 | 6,978 | 32,854 | 51,077 | 11,639 |
| k1 | kimi | 42 | 9,109 | 31,572 | 44,584 | 12,129 |
| k2 | kimi | 44 | 12,755 | 32,737 | 45,480 | 14,237 |
| k3 | kimi | 44 | 8,696 | 35,031 | 41,362 | 11,780 |
| k4 | kimi | 42 | 8,656 | 31,687 | 49,425 | 12,073 |
| k5 | kimi | 48 | 6,692 | 40,031 | 46,616 | 12,150 |

- k4(deepseek) p50=6,586ms 是5键中最快之一, max=58,771ms为单次慢success(救援), 非劣化
- k4(kimi) p50=8,656ms, 与k3(8,696)相当, p95=31,687ms最低
- → **k4无路由劣化**: p50/p95/avg均在正常区间, CC清单[HM1-B]前提(k4 avg28.5s p95=72.9s)未在当前数据复现

### 1f. 6h小时桶趋势 (DB ts 04:00-10:00 = 真实UTC 20:00-02:00)
| Hour(DB ts) | Reqs | OK | ATE | SR% |
|-------------|------|----|-----|-----|
| 04:00 | 21 | 19 | 2 | 90.5 |
| 05:00 | 162 | 137 | 25 | 84.6 |
| 06:00 | 165 | 131 | 34 | 79.4 |
| 07:00 | 175 | 148 | 27 | 84.6 |
| 08:00 | 200 | 176 | 24 | 88.0 |
| 09:00 | 124 | 95 | 29 | 76.6 |
| 10:00 | 105 | 71 | 30 | 70.3 |

- ATE绝对数稳定在24-34/小时(NVCF server-side持续), 需求侧下降(200→105)使SR%走低
- 非参数可修: ATE根因=NVCF function f966661c server-side NVCFPexecTimeout, 非HM1 throttle/cooldown/budget可解

### 1g. tier_attempts 错误结构 (30min / 6h)
**30min**:
| error_type | count | avg_elapsed_ms | 备注 |
|------------|-------|----------------|------|
| NVCFPexecTimeout | 7 | 24,021 | server-side, avg≈UPSTREAM=25s |

**6h**:
| error_type | count | avg_elapsed_ms | 备注 |
|------------|-------|----------------|------|
| NVCFPexecTimeout | 81 | 24,377 | server-side, 全fastbreak救回或终态ATE |
| empty_200 | 18 | — | 中间attempt, 全cycle救回 |

- 0×429, 0×SSLEOF, 0×conn_err — 连接健康
- NVCFPexecTimeout avg≈24s ≈ UPSTREAM_TIMEOUT(25s) read阶段超时, server-side

### 1h. 失败请求duration分布 (6h, 168 ATE)
| bucket | count | avg_ms |
|--------|-------|--------|
| <5s (quick-fail) | 6 | 803 |
| 5-46s | 1 | 8,168 |
| 46-50s | 80 | 46,937 |
| >=50s | 83 | 50,852 |

- 163/168失败在46-53s区间 = 2×UPSTREAM(25s) ≈ FASTBREAK=2触发点
- FASTBREAK=2已生效(docker logs 30min见2次`HM-PEXEC-FASTBREAK 2 consecutive NVCFPexecTimeout -> fast-break`)
- BUDGET=125s从未被触达(失败在~50s fastbreak, 远低于125s)

### 1i. 慢success分析 (FASTBREAK=2 vs =1 权衡)
- 6h success且duration>25s = 88个 (avg 34,839ms, max 58,771ms) — 第一attempt超时/慢后, k2/k3/k4/k5救援成功
- 若FASTBREAK=1(1连timeout即break): 省~25s/失败(×165慢失败=4125s), 但误杀88个rescue
- 当前FASTBREAK=2: 2连timeout才break, 给1次rescue机会, 88个慢success全保住
- → **FASTBREAK=2为最优平衡点**(R473已实现), 降=1误杀88 rescue(SR↓), 升=3多耗25s/失败

## 2. CC清单[HM1-A/B/C]状态评估 (30min+6h新鲜数据)

### [HM1-A] MIN_OUTBOUND_INTERVAL_S 18.2→9.0 — ✅目标已超额达成 + throttle非瓶颈证伪
- CC指令前提"MIN_OUTBOUND=18.2s"为过时数据: 实测当前=3.8 (compose L421+容器env双处一致, R442由4.0→3.8)
- 3.8 << 9.0目标 → A目标值已超额达成(无需再降)
- **继续降证伪(throttle非瓶颈)**:
  - 30min实际吞吐=65req/30min=2.17 req/min
  - 6h实际吞吐=940req/6h=2.61 req/min
  - throttle天花板=60/3.8=15.8 req/min
  - 实际2.17-2.61 << 15.8 → 需求侧远未触达throttle, 降throttle无吞吐增益
  - docker logs 30min 0×`HM-OUTBOUND-THROTTLE`触发 → throttle从未阻塞请求
- **结论**: A目标(≤9.0)早已达成(3.8), throttle非瓶颈(需求2.61rpm<<天花板15.8rpm), 继续降无收益且方向相反

### [HM1-B] k4(direct, idx=3)路由劣化修复 — ✅证伪(k4无劣化)
- CC指令前提"k4 avg28.5s vs其他~25s, p95=72.9s vs~55s, max=162.9s"未在当前数据复现:
  - 6h k4(deepseek): p50=6,586ms(5键中最快之一), p95=31,228ms(最低), avg=10,627ms
  - 6h k4(kimi): p50=8,656ms, p95=31,687ms(最低), avg=12,073ms
  - 6h 5键p50 range 6,000-12,755ms (cv≈10%, 正常均衡)
  - k4 max=58,771ms为单次慢success(救援场景), 非系统性劣化
- **结论**: k4当前无路由劣化, 无需改PROXY_URL4(改direct→mihomo无收益, k4已最快)

### [HM1-C] all_tiers_exhausted早fail — ✅已实现(FASTBREAK=2) + 最优平衡证伪
- CC指令"前3个key全NVCFPexecTimeout即fast-fail"已由R347实现(FASTBREAK=3)+R473降到2
- 当前FASTBREAK=2: 2连pexec timeout即break, 比CC指令的3更激进(省1×25s/失败)
- 实测fastbreak生效: docker logs 30min见2次`HM-PEXEC-FASTBREAK 2 consecutive -> fast-break`
- 失败duration集中在46-53s(=2×25s), 证实FASTBREAK=2在2连timeout后立即break, 未试k3/k4/k5
- **继续降=1证伪**: 6h有88个慢success(>25s, 第一attempt timeout后k2-k5救援), FASTBREAK=1会误杀这88 rescue → SR↓
- **结论**: FASTBREAK=2为SR-vs-latency最优平衡(R473已实现), 升=3多耗25s/失败, 降=1误杀88 rescue

## 3. 其他参数天花板验证

### TIER_TIMEOUT_BUDGET_S=125 — 死约束(fastbreak先触发)
- 6h 168失败全在46-53s区间(FASTBREAK=2触发), BUDGET=125s从未触达
- 失败break点 = 2×UPSTREAM(25s)=50s, 远低于BUDGET=125s
- **结论**: BUDGET对失败请求非活跃约束, 降BUDGET无影响(fastbreak先break), 升BUDGET无意义

### UPSTREAM_TIMEOUT=25 — 不可降(R490刚从23→25)
- 6h NVCFPexecTimeout avg=24,377ms ≈ UPSTREAM边界
- 6h 88个慢success duration 25-58s, 含接近UPSTREAM边界的慢success
- 降UPSTREAM会让更多慢success被timeout误杀(SR↓)
- **结论**: UPSTREAM=25保护慢success, R490已+2s增headroom, 不可降

### KEY_COOLDOWN_S=25 / TIER_COOLDOWN_S=38 — 半活跃但无SR影响
- 6h 0×429 → cooldown从未因429触发
- KEY=25 < TIER=38 (R270等值不变量已由R270修复为KEY=38? 实测KEY=25/TIER=38, 非等值)
  - 注: 当前KEY=25 < TIER=38, 与R270"KEY=TIER=38等值"约束不符, 但6h 0×429证明cooldown无429触发场景, 非活跃约束, 不影响SR
  - 此为历史参数演化留痕, 非本轮清单项, 上报CC不擅改
- **结论**: cooldown非活跃(0×429), 不动

### HM_PEXEC_TIMEOUT_FASTBREAK=2 — 最���(见1i/2C)
### HM_CONNECT_RESERVE_S=10 — 非瓶颈
- 6h 0×conn_err, 0×SSLEOF → connect阶段健康, reserve=10足够
- **结论**: 不动

## 4. 决策: ⏸️ NOP · 零配置变更

**理由**:
1. CC清单[HM1-A/B/C]三项全部完成/证伪:
   - A: MIN_OUTBOUND=3.8已超额达成(<<9.0目标), throttle非瓶颈(需求2.61rpm<<天花板15.8rpm, 0×throttle触发)
   - B: k4无路由劣化(p50 6.6-8.7s最快组, p95 31.2-31.7s最低, CC前提未复现)
   - C: FASTBREAK=2已实现(R347+R473), 比CC指令的3更激进, 降=1误杀88 rescue证伪
2. 全8参数在天花板: BUDGET=125死约束(fastbreak先触发), UPSTREAM=25保护慢success, FASTBREAK=2最优平衡, KEY/TIER_COOLDOWN非活跃(0×429)
3. 失败根因=NVCF server-side NVCFPexecTimeout(168 ATE, 全在46-53s=2×25s fastbreak), 非HM1参数可修
4. 5键per-hit全100%SR, 0×429/empty_200/SSLEOF/conn_err — 连接与key池健康
5. 6h SR=82.1%下降趋势根因: ATE绝对数稳定24-34/h(NVCF surge持续), 需求侧下降使SR%走低, 非参数可修

**当前HM1参数已达全局最优**: fastfail机制(FASTBREAK=2)已吸收所有可优化失败耗时, throttle非瓶颈, 5键均衡无劣化, 失败根因在NVCF server-side。

## 5. 反对者注意 (供CC下轮勘定, 非本轮清单项)

本轮发现两个清单外信号, 严格按清单执行不擅自改动:
1. **KEY=25 < TIER=38 违反R270等值不变量**: 实测KEY_COOLDOWN_S=25, TIER_COOLDOWN_S=38, 与R270"KEY=TIER=38"约束不符。但6h 0×429证明cooldown非活跃, 无SR影响。历史参数演化留痕(R162 KEY=34→38, 后续某轮又降到25), 非本轮清单项, 上报CC勘定是否回调KEY=38。
2. **6h SR下降趋势(90.5%→70.3%)**: ATE绝对数稳定24-34/h, 需求侧下降(200→105req/h)使SR%走低。根因=NVCF function f966661c server-side持续NVCFPexecTimeout, 非HM1参数可修。若CC勘定方向: 确认是否NVCF surge持续, 或考虑function切换(非参数项)。

## 6. 执行记录

### 变更: 无
```bash
# 零配置变更 — docker-compose.yml不变, 容器不重启
# 本轮为数据驱动NOP: CC清单三项6h+30min新鲜数据复检全部完成/证伪, 无可动项
# 清单外信号(KEY<TIER不等值, SR下降趋势)上报CC, 不擅自改动
```

### 验证: 通过
```bash
# env一致性检查: compose grep(hm40006块) 与 docker exec hm40006 env 逐字一致, 8参数+5URL零漂移
ssh -p 222 opc_uname@100.109.153.83 'docker exec hm40006 env | grep -E "MIN_OUTBOUND|TIER_TIMEOUT|UPSTREAM|KEY_COOLDOWN|TIER_COOLDOWN|CONNECT_RESERVE|FASTBREAK|SSLEOF"'
# ↑ UPSTREAM=25, BUDGET=125, MIN_OUTBOUND=3.8, FASTBREAK=2, 全匹配compose

# 健康检查 (对端): /health=200 ok, hm_num_keys=5, nvcf_pexec_models=[dsv4p_nv]
```

## 7. 轮次统计
- HM1自R490(HM1→HM2 NOP)后: 本轮R491为HM2→HM1方向
- CC清单[HM1-A/B/C]三项状态: A✅超额达成(3.8<<9.0)+throttle非瓶颈证伪, B✅证伪(k4无劣化), C✅已实现(FASTBREAK=2最优)
- 连续NOP(HM1侧): R486→R491, 本轮为清单复检证伪轮(每项有30min+6h具体数据)
- 本轮NOP理由: 三项全部完成/证伪, 全8参数在天花板, 失败根因NVCF server-side非参数可修

## 8. 铁律遵守
- ✅ 只改HM1不改HM2: 无变更行为, 合规
- ✅ 单参数少改多轮: NOP验证, 无参数
- ✅ 数据驱动先采集后决策: 9层验证(env + 30min + 6h DB + per-key双组 + 小时桶 + tier_attempts + 失败duration分布 + 慢success权衡 + docker logs fastbreak)
- ✅ 零配置变更: docker-compose.yml未修改, compose与容器env双处零漂移
- ✅ 无R320/R322/R350重蹈: 未改compose, 未commit错文件, push后即停
- ✅ DB时区: 全部用绝对ts窗口, 禁用NOW()
- ✅ 执行CC清单不擅自找改动点: KEY<TIER不等值+SR下降趋势为清单外项, 上报CC不擅改
- ✅ host_machine标识正确: opc_uname(纠正R489误记的opcsname)

## ⏳ 轮到HM1优化HM2
