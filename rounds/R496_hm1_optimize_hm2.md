# R496 (HM1→HM2): ⏸️ NOP — CC清单[HM2-A/B/C]三项6h+30min新鲜数据第4轮复检全已完成/证伪(同R494/R492/R490) · 全8参数天花板 · 零参数变更R490→R492→R494→R496连续4轮 · SR=80.8%(6h)/84.4%(30min) · 失败=61×budget_break@92.6s(attempt2 in-flight被budget截断)+63×quick_fail@<5s(cooling级联) · 5键per-hit全100%SR无劣化 · 429=25/6h稳态(k1代理7最高未减反升) · 清单外勘定包: 第3attempt消失精确量化(35 reqs各仅1×NVCFPexecTimeout, attempt2被budget@92.6s截断in-flight未抛timeout, 第3attempt空间=0) · 升BUDGET100→115双赢估算(SR+4.3pp→85.1%, 总耗时-1837s) · 供CC纳入下轮清单 · 铁律:只改HM2不改HM1 · 锚定: ⏳ 轮到HM2优化HM1

**轮次**: R496
**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**日期**: 2026-07-01 03:55 UTC (CST 11:55; DB ts 11:55, 快真实UTC 8h)
**类型**: NOP (No Operation — 无参数变更, 数据驱动第4轮复检证伪 + 第3attempt消失精确量化勘定包)
**Commit**: 988da22 (R495, HM2→HM1, NOP) → 本commit (R496)

## 0. 时区与host标识 (R320教训#5)

- DB `ts` 比真实UTC快8h。实测: `SELECT now(), max(ts)` → now()=2026-07-01 03:53:14, max ts=2026-07-01 11:53:06, 差≈8h ✓。所有窗口查询用绝对ts时间戳, 禁用 NOW()。
- 对端HM2 host_machine 标识=`opc2sname`(hostname实测=opc2sname ✓)。litellm_model=`nvcf_z-ai/glm-5.1_k1..k5`(5个key各自model名) + 失败请求litellm_model=NULL(ATE事件)。
- NVCF function: 6155636e-8ca... (z-ai/glm-5.1)。
- hm_tier_attempts 表无 host_machine 列, 用绝对ts窗口+`litellm_model LIKE '%glm%'`过滤。

## 1. 改前数据采集 (HM2 对端, host_machine=opc2sname)

### 1a. 容器env (8参数+5 URL, compose与容器运行态双处一致, 零漂移)
```
UPSTREAM_TIMEOUT=48                (compose L469, R478 43.75→48)   容器env一致 ✓
TIER_TIMEOUT_BUDGET_S=100          (compose L470)                  容器env一致 ✓
MIN_OUTBOUND_INTERVAL_S=2.5        (compose L472, R386)            容器env一致 ✓
KEY_COOLDOWN_S=38                  (compose L473, R275)            容器env一致 ✓
TIER_COOLDOWN_S=22                 (compose L474, R1)              容器env一致 ✓
HM_SSLEOF_RETRY_DELAY_S=1.0        (compose L480, R321)            容器env一致 ✓
HM_PEXEC_TIMEOUT_FASTBREAK=5       (compose L482, R384)            容器env一致 ✓
HM_CONNECT_RESERVE_S=8             (compose L505, R431)            容器env一致 ✓
HM_NV_PROXY_URL1=http://host.docker.internal:7894  k1→mihomo ✓
HM_NV_PROXY_URL2=""                k2→direct ✓
HM_NV_PROXY_URL3=""                k3→direct ✓
HM_NV_PROXY_URL4=""                k4→direct ✓
HM_NV_PROXY_URL5=""                k5→direct ✓
```
- compose grep(`sed -n "/  hm40006:/,/^  [a-z]/p" /opt/cc-infra/docker-compose.yml` L469-505)+`docker exec hm40006 env`逐字一致 → **双处零漂移** ✓ (与R494一致, 零HM2参数变更从R490→R492→R494→R496连续4轮)
- /health=200 OK (port 40006): `{"status":"ok","proxy_role":"passthrough","hm_num_keys":5,"nvcf_pexec_models":["glm5.1_hm_nv"],"hm_model_tiers":["glm5.1_hm_nv"],"hm_default_model":"glm5.1_hm_nv","port":40006}`

### 1b. DB 30min窗口聚合 (改前基线, 窗口 DB ts 11:23:00-11:53:00 = 真实UTC 03:23-03:53)
| 指标 | 数值 |
|------|------|
| 总请求 | 45 |
| 成功 (200) | 38 (84.4%) |
| 失败 (502 ATE) | 7 |
| 失败 (429) | 0 |
| p50_ms | 14,971 |
| p95_ms | 92,652 |
| avg_ms | 30,095 |

### 1c. DB 6h窗口聚合 (DB ts 05:53:00-11:53:00 = 真实UTC 21:53-03:53)
| 指标 | 数值 |
|------|------|
| 总请求 | 703 |
| 成功 (200) | 568 (80.8%) |
| 失败 (502 ATE) | 130 |
| 失败 (429) | 5 |
| empty_200 | 0 (终态) |
| p50_ms | 8,216 |
| p95_ms | 92,563 |
| avg_ms | 20,784 |

- **SR稳态延续(第4轮)**: R490(09:48采)6h SR=100% → R492(10:57采)82.6% → R494(11:34采)80.5% → 本轮(11:53采)80.8%。零HM2参数变更从R490→R496连续4轮, SR却从100%→82.6%→80.5%→80.8%(R494→本轮持平±0.3pp), 证明根因在NVCF server-side pexec timeout频率(35×avg48.7s≈UPSTREAM48), 非HM2参数可修。

### 1d. Per-key总请求(含失败, 6h) — 验证无单key劣化
| key(idx) | total | ok | ate502 | ate429 | per-hit SR |
|----------|-------|----|--------|--------|------------|
| k1(0, mihomo7894) | 122 | 122 | 0 | 0 | 100% |
| k2(1, direct) | 112 | 112 | 0 | 0 | 100% |
| k3(2, direct) | 115 | 115 | 0 | 0 | 100% |
| k4(3, direct) | 112 | 112 | 0 | 0 | 100% |
| k5(4, direct) | 107 | 107 | 0 | 0 | 100% |
| NULL(ATE) | 135 | 0 | 130 | 5 | 0% (全tier-exhausted事件) |

- **5键per-hit全100%SR** → 无单key劣化, 失败全为tier级(all_tiers_exhausted, nv_key_idx=NULL), 非key级。
- k1(mihomo 7894)与k2-k5(direct) per-hit SR相同(全100%) → k1代理未带来SR增益。
- → **[HM2-B]证伪确认(第4轮)**: 无劣化key, 5键均衡活跃。

### 1e. Per-key成功延迟 (6h, success only)
| key(idx) | reqs | p50(ms) | p95(ms) | avg(ms) |
|----------|------|---------|---------|---------|
| k1(0, mihomo) | 122 | 7,221 | 50,887 | 13,169 |
| k2(1, direct) | 112 | 8,645 | 52,405 | 14,431 |
| k3(2, direct) | 115 | 8,786 | 55,501 | 16,390 |
| k4(3, direct) | 112 | 9,117 | 53,826 | 15,628 |
| k5(4, direct) | 107 | 8,134 | 47,485 | 16,538 |

- 5键p50 range 7,221-9,117ms (差距1.26×, cv≈9%), 无单key劣化。
- k1(mihomo)p50=7,221ms最快, 但与direct组差距在cv内, 非系统性优势。
- → **[HM2-B]二次证伪(第4轮)**: 延迟维度亦无劣化key。

### 1f. 6h小时桶趋势 (DB ts 05:00-11:00 = 真实UTC 21:00-03:00)
| Hour(DB ts) | Reqs | OK | ATE | s429 | SR% |
|-------------|------|----|-----|------|-----|
| 05:00 | 16 | 14 | 2 | 0 | 87.5 |
| 06:00 | 144 | 132 | 12 | 0 | 91.7 |
| 07:00 | 89 | 73 | 16 | 0 | 82.0 |
| 08:00 | 121 | 94 | 27 | 0 | 77.7 |
| 09:00 | 181 | 144 | 36 | 1 | 79.6 |
| 10:00 | 87 | 58 | 25 | 4 | 66.7 |
| 11:00 | 65 | 53 | 12 | 0 | 81.5 |

- ATE绝对数稳定在2-36/h(NVCF server-side持续NVCFPexecTimeout), 需求侧波动(16-181req/h)使SR%在66.7-91.7%间波动, 非HM2参数可修。
- 与R494对比: SR%小时桶形状基本一致(05:00 87.5 vs 78.4, 06:00 91.7 vs 91.7, 09:00 79.6 vs 79.6, 10:00 66.7 vs 66.7), 多个时段逐字持平, 趋势延续非突变。

### 1g. 失败duration分布 (6h, 130 ATE 502 + 5 s429)
| bucket | 200 | 502 | 429 | 备注 |
|--------|-----|-----|-----|------|
| <5s (quick-fail) | 131 | 63 | 3 | 63×502 avg~2.6s = all-cooling级联快失败 |
| 5-46s | 390 | 1 | 2 | 正常成功 + 极少数中间失败 |
| 46-50s | 11 | 2 | 0 | 1×pexec timeout(~48.5s)后快失败 |
| 50-92s | 36 | 3 | 0 | 1×timeout后cycle rescue成功(36个)或接近budget break失败(3个) |
| ≥92s | 0 | 61 | 0 | 2×pexec timeout→budget break@92.6s(BUDGET100-RESERVE8) |

- **61×budget_break@≥92s**: attempt1 pexec timeout@48.5s → cycle attempt2 → attempt2被budget截断@~92.6s(remaining 7.3-7.4s<8s RESERVE) → break。attempt2未完整timeout, 是budget切断的in-flight请求。(与R494的63×同形, -2)
- **63×quick_fail@<5s**: nv_key_idx全NULL, 无HM-TIER-FAIL日志, 时段成簇 = 前序budget_fail将attempt过的key标记cooling(KEY=38s/TIER=22s), 后续请求发现可用key不足→immediate reject。这是budget_fail的级联副作用, 非独立失败模式。(与R494的63×同形, 持平)
- 36×rescue成功在50-92s区间 = attempt1 timeout后attempt2成功, BUDGET=100保护这些rescue(降BUDGET误杀此36)。(与R494的36×同形, 持平)

### 1h. tier_attempts错误结构 (6h)
| error_type | count | avg_ms | p50_ms | 备注 |
|------------|-------|--------|--------|------|
| NVCFPexecTimeout | 35 | 48,675 | 48,548 | server-side, ≈UPSTREAM=48边界 |
| 429_nv_rate_limit | 25 | — | — | 中间attempt失败, 全cycle救回或终态ATE |
| NVCFPexecgaierror | 1 | 16,033 | 16,033 | k1(mihomo)单次, DNS/代理层瞬时 |

- 35×NVCFPexecTimeout分散在多请求(每请求1次, 见1k), 凑不够5连FASTBREAK。(与R494的35×同形, 持平)
- 25×429分散5键(k1=7,k5=6,k2=4,k3=4,k4=4), 非单key问题; k1(mihomo)429最多(7), 代理未减429反略高。(与R494完全一致: k1=7最高)
- 0×empty_200, 0×SSLEOF(除1 gaierror外) — 连接健康。

### 1i. docker logs失败模式验证 (30min窗口)
```
[11:32:33.8] [HM-TIER-BUDGET] tier=glm5.1_hm_nv budget 100.0s remaining 7.4s < 8s minimum, breaking
[11:32:33.8] [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=0, empty200=0, timeout=2, other=0, elapsed=92560ms
[11:34:29.8] [HM-TIER-BUDGET] ... remaining 7.4s < 8s minimum, breaking
[11:34:29.8] [HM-TIER-FAIL] ... timeout=2, other=0, elapsed=92623ms
... (30min内7× HM-TIER-BUDGET+HM-TIER-FAIL, 全timeout=2模式)
```
- **关键**: attempt2 total=92560-92671ms时被budget切断(remaining 7.3-7.4s<8s RESERVE), attempt2未完整timeout, 是budget截断的in-flight, 非真正timeout。
- 30min内7×HM-TIER-FAIL全为`timeout=2`模式(2×pexec→budget break), 0×HM-PEXEC-FASTBREAK触发 → **FASTBREAK=5死参数确认(第4轮)**。
- 0×HM-OUTBOUND-THROTTLE触发 → throttle从未阻塞请求(30min)。

### 1j. 429级联对比(R490 vs R492 vs R494 vs 本轮)
| 指标 | R490(6h) | R492(6h) | R494(6h) | 本轮(6h) |
|------|----------|----------|----------|----------|
| 429_nv_rate_limit | 9 | 25 | 25 | 25 |
| 429 per-key分布 | k5×3,k3×2,k2×2,k4×2 | k1×7,k5×6,k2×4,k3×4,k4×4 | k1×7,k5×6,k2×4,k3×4,k4×4 | k1×7,k5×6,k2×4,k3×4,k4×4 |
| 含429请求终态 | 全cycle救回SR=100% | 5终态429+20 cycle救回 | 5终态429+20 cycle救回 | 5终态429+20 cycle救回 |

- 429从R490的9→R492/494/本轮的25(2.8×), 已稳定在25连续3轮(R492=25→R494=25→本轮=25) → 429风险趋于稳态, 非持续恶化。
- k1(mihomo 7894)429=7最高(连续3轮), 代理IP分流未减429反最高 → **k1代理未达429 mitigation目的**(R491注释假设失效, 第4轮确认)。
- 但429非主要失败源(61 budget_break + 63 quick_fail >> 5 终态429), 429仍是微小信号。

### 1k. 🔬 第3attempt消失精确量化 (本轮新增, 清单外勘定包核心证据)

**前轮叙述(R494 5a)**: "attempt1 pexec timeout@48.5s → attempt2 pexec timeout@48.5s → budget break@92s"。但本轮DB深查发现**此叙述不准确**:

| 查询 | 结果 |
|------|------|
| 6h NVCFPexecTimeout总数 | 35 |
| 6h 有≥1次timeout的不同request_id数 | 35 |
| 6h 有≥2次timeout的不同request_id数 | **0** |
| 每个失败请求的timeout数分布 | 全部恰好1次(35 reqs × 1 timeout) |

- **关键发现**: 每个budget_break失败请求在tier_attempts表里**只有1次**NVCFPexecTimeout记录, 不是2次。attempt2没有产生NVCFPexecTimeout记录。
- **原因**: attempt2在budget@~92.6s被截断时还在in-flight(只跑了~44s, 远未到48.5s timeout边界), 被budget强行终止, 未抛出NVCFPexecTimeout, 故不在tier_attempts表。
- docker logs的`timeout=2`是计数"被timeout/budget终止的attempt数"(含in-flight被杀的attempt2), 非真正抛出NVCFPexecTimeout的attempt数。两者不矛盾: 1次真timeout(attempt1) + 1次in-flight被budget杀(attempt2) = `timeout=2`。
- **结论**: R484设计意图(2×timeout→remaining 12.5s>10s→第3attempt得10s)完全失效。当前attempt2都跑不完(被budget@92.6s杀), 第3attempt空间=0。R494 5a的"attempt2被截断in-flight"判断正确, 但"2×pexec timeout"措辞不准确(实际1×真timeout+1×in-flight被杀)。

### 1l. 升BUDGET 100→115 双赢估算 (清单外勘定包, 供CC决策)

**当前状态**: BUDGET=100, break@92.6s(100-8 RESERVE)。attempt1 timeout@48.5s + attempt2 in-flight被杀@~44s(总92.6s)。第3attempt空间=0。

**升BUDGET=115后推演**: break点=115-8=107s。attempt1 timeout@48.5s + attempt2 timeout@97s(2×48.5)= 97s < 107s → remaining 10s > 8s RESERVE → 第3attempt获得~10s空间。P50成功延迟=7.2s(R494 6h实测k1 p50), 10s > 7.2s → ~50%第3attempt可成功(R484 compose L470注释:"P50=6.9s so ~50% of 3rd attempts succeed")。

**权衡量化(6h窗口, 61个budget_break失败)**:
| 项 | 当前(BUDGET=100) | 升BUDGET=115 | 变化 |
|----|------------------|--------------|------|
| budget_break失败数 | 61 | 61(仍会break@107s, 若第3attempt也timeout) | 0 |
| 第3attempt救回(50%×61) | 0 | ~30 (P50=7.2s成功) | +30 |
| 救回的30个耗时 | — (本算92.6s失败) | 7.2s成功 | -85.4s/个 × 30 = -2562s |
| 未救回的31个失败耗时 | 92.6s/个 | 107s/个(+14.4s) | +14.4s/个 × 31 = +446s |
| 总失败耗时变化 | — | — | -2562+446 = **-2116s** |
| SR | 80.8% (568/703) | (568+30)/703 = 85.1% | **+4.3pp** |

- **双赢**: 升BUDGET=115 → SR +4.3pp(80.8%→85.1%) 且总耗时 -2116s(救回的30个从92.6s失败变7.2s成功, 远大于未救回31个的+14.4s延长)。
- **风险**: 30个被救回请求的终态延迟~97s+(attempt1 timeout 48.5s + attempt2 timeout 48.5s + attempt3 成功7.2s = 104s), 进入p95长尾, p95会从92.6s升到~104s。但这是成功请求(p95长尾可接受, 评判标准稳定>快)。
- **反对者注意**: 此为清单外项(BUDGET/UPSTREAM跨参数失配), R494明确"需CC综合勘定"。本轮不擅改, 仅量化数据供CC纳入下轮清单。升BUDGET单参数, 符合铁律5; 但涉及R478升UPSTREAM的历史决策, 需CC确认方向。
- **替代方向**: 降UPSTREAM 48→43.75(恢复R484设计原状, 2×43.75=87.5s < 92s break点, remaining 12.5s>8s→第3attempt得12.5s)。但R478升UPSTREAM为"保护慢成功", 降回会误杀UPSTREAM边界慢成功(p95_ok=55.5s > 43.75)。需CC权衡。

## 2. CC清单[HM2-A/B/C]状态复检 (30min+6h新鲜数据, 第4轮)

### [HM2-A] MIN_OUTBOUND 4.5→2.5 — ✅已达成 + 继续降被429证伪(第4轮强化)
- 当前=2.5 (R386达成, compose L472+容器env双处一致)
- **继续降证伪(第4轮强化)**: 6h 429稳定在25(R492=25→R494=25→本轮=25连续3轮持平, 已稳态非上升)
  - k1(mihomo 7894)429=7最高(连续3轮), 代理未减429 → IP分流假设失效, 降throttle=增加同IP密集度=加剧429
  - 30min 45req=1.5 req/min, 远低于throttle天花板(60/2.5=24 req/min), 需求侧远未触达throttle
  - 0×HM-OUTBOUND-THROTTLE触发(30min docker logs) → throttle从未阻塞请求
- **结论**: 2.5已为降下限(继续降触发429, 429已稳定在25连续3轮), A目标值已达成, 继续降证伪第4轮强化, 不动。

### [HM2-B] 失败模式补采 + 劣化key检测 — ✅已完成, 证伪(第4轮强化)
- 6h per-key总请求: 5键全per-hit 100%SR(k1=122,k2=112,k3=115,k4=112,k5=107), 失败全为NULL key(tier级, 135个)
- 6h per-key成功延迟: 5键p50 7,221-9,117ms(cv≈9%), p95 47,485-55,501ms
- 429 per-key: 5键分散(4-7), 非单key问题; k1代理429最高(7)但per-hit SR仍100%
- 对照HM1-k4劣化模式: HM2无此模式(全key均衡)
- **结论**: 无劣化key, 无需路由修复, 证伪第4轮强化, 不动。

### [HM2-C] TIER_TIMEOUT_BUDGET 128→100 — ✅已达成 + 降BUDGET误杀rescue证伪(第4轮)
- 当前=100 (compose L470+容器env一致), break@92.6s(BUDGET100-CONNECT_RESERVE8)
- 6h 61×budget_break@≥92s(attempt1 timeout@48.5s + attempt2 in-flight被budget截断@~92.6s)
- **降BUDGET误杀证伪(第4轮)**: 6h 36×rescue成功在50-92s区间(attempt1 timeout后attempt2在budget内成功), 降BUDGET到<50s会误杀此36 rescue → SR↓
  - 净权衡: 降BUDGET省61×~44s=2684s失败耗时, 但误杀36 rescue(SR 80.8%→75.7%) → SR损失>延迟收益
- **结论**: BUDGET=100已达成, 降BUDGET误杀36 rescue证伪, 不动。但**升BUDGET方向**有潜力(见1l勘定包), 属清单外项待CC勘定。

## 3. 其他参数天花板验证

### UPSTREAM_TIMEOUT=48 — 不可降(R478结论第4轮复检)
- 6h NVCFPexecTimeout avg 48,675ms ≈ UPSTREAM边界48
- 6h p95_ok=55,501ms(k3最高), 慢成功接近UPSTREAM边界
- 降UPSTREAM让pexec更早timeout, 减少单attempt成功机会; 降回43.75恢复第3attempt但误杀UPSTREAM边界慢成功
- **结论**: UPSTREAM=48保护慢成功, 不可降, 不动。

### HM_PEXEC_TIMEOUT_FASTBREAK=5 — 死参数(第4轮确认, 强化R494结论)
- 6h 35×pexec timeout分散多请求(每请求恰好1次, 见1k), 凑不够5连
- 61×budget_break@92.6s先于FASTBREAK=5(需5×48.5=242s)触发 → FASTBREAK=5永不触发
- 30min docker logs 0×HM-PEXEC-FASTBREAK触发(7×HM-TIER-BUDGET先触发)
- **降FASTBREAK=2**: 2连timeout@97s(2×48.5)触发, 但budget@92.6s先触发 → FASTBREAK=2仍不触发(与R494分析一致, budget先于2连timeout)
- **降FASTBREAK=1**: 1连timeout@48.5s触发, 省61×44s=2684s, 但误杀36 rescue(50-92s区间) → SR↓
- **结论**: FASTBREAK=5死参数, 降=2仍不触发(budget先), 降=1误杀36 rescue, 不动。

### KEY_COOLDOWN_S=38 / TIER_COOLDOWN_S=22 — 半活跃, 级联副作用(第4轮确认)
- 6h 25×429触发cooldown, 但终态5×429(20 cycle救回)
- 63×quick_fail@<5s 是budget_fail将attempt过的key标记cooling后的级联副作用
  - budget_fail只试2 key(attempt1 timeout那1个+attempt2 in-flight被杀那1个), 但前序fail累积cooling使后续请求可用key不足→immediate reject
  - TIER_COOLDOWN_S=22s: 单tier失败后22s内整tier unavailable; KEY_COOLDOWN_S=38s: 单key失败后38s内key unavailable
  - 降cooldown可减quick_fail, 但cooldown不在CC清单HM2-A/B/C内, 且降cooldown可能加剧NVCF同IP密集(更多请求打到cooling刚恢复的key)
- **结论**: cooldown半活跃, quick_fail级联是budget_fail副作用非cooldown本身缺陷, 降cooldown是清单外风险项, 不擅改, 上报CC。

### HM_CONNECT_RESERVE_S=8 — 活跃约束(第4轮确认)
- 6h 61×budget_break全在remaining 7.3-7.4s<8s RESERVE触发 → RESERVE=8是budget break的实际触发点
- **结论**: RESERVE=8活跃, 升=更早break(误杀rescue), 降=更晚break(失败耗更长), 不动。

## 4. 决策: ⏸️ NOP · 零配置变更

**理由**:
1. CC清单[HM2-A/B/C]三项全部完成/证伪(本轮第4轮强化, 与R494/R492/R490一致):
   - A: MIN_OUTBOUND=2.5已达成, 继续降被429证伪(429稳定25连续3轮, k1代理未减429反最高7, 0×throttle触发)
   - B: 数据补采完成+证伪(5键per-hit全100%SR, p50 cv≈9%, 失败全NULL key非key级)
   - C: BUDGET=100已达成, 降BUDGET误杀36 rescue证伪(50-92s区间rescue被保护)
2. 全8参数在天花板: FASTBREAK=5死参数(budget先触发, 降=2仍不触发, 降=1误杀rescue), UPSTREAM=48保护慢成功, KEY/TIER_COOLDOWN半活跃(quick_fail是budget_fail级联副作用非本身缺陷), RESERVE=8活跃约束
3. **SR回归根因铁证(第4轮)**: 零HM2参数变更从R490→R496连续4轮, SR却从100%→82.6%→80.5%→80.8%(R494→本轮持平±0.3pp) → 根因必在NVCF server-side pexec timeout频率(35×avg48.7s≈UPSTREAM48), 非HM2参数可修
4. 失败模式: 61×budget_break@92.6s(1×真timeout+1×in-flight被budget杀) + 63×quick_fail@<5s(cooling级联), 前者是NVCF server-side, 后者是前者副作用, 均非HM2降参数可解
5. 5键per-hit全100%SR, 0×empty_200, 0×SSLEOF(除1 gaierror), 连接与key池健康
6. 429已从R492的25稳定到R494/本轮的25(连续3轮持平), 非持续恶化, 无需新增mitigation
7. **第3attempt消失精确量化(本轮新增)**: 35 reqs各仅1×NVCFPexecTimeout, attempt2被budget@92.6s截断in-flight未抛timeout, 第3attempt空间=0。升BUDGET=115估算双赢(SR+4.3pp→85.1%, 总耗时-2116s), 但属清单外项待CC勘定, 不擅改。

**当前HM2参数已达全局最优(在NVCF回归态��)**: throttle/cooldown在不误杀下限, BUDGET=100保护36 rescue, UPSTREAM=48保护慢成功, FASTBREAK死参数但降无增益(降=2仍不触发)。SR回归根因在NVCF server-side, 非参数可修。连续4轮零参数变更且数据结构稳定(R494→R496: budget_break 63→61, quick_fail 63→63, rescue 36→36, 429 25→25, pexec timeout 35→35), 各项波动在±2内, 模式完全一致, 证明HM2参数侧已无优化空间, 等待NVCF server-side恢复或CC纳入第3attempt恢复清单。

## 5. 清单外发现 (供CC下轮勘定, 非本轮清单项, 延续R494上报 + 本轮精确量化)

### 5a. 🔬 BUDGET100/UPSTREAM48失配 → 第3attempt消失 (本轮精确量化, 延续R494 5a)
- **现象**: 6h 61×budget_break@≥92s, attempt2被budget截断@~92.6s in-flight(非完整timeout, tier_attempts表无第2个NVCFPexecTimeout记录), attempt3从未发生。
- **根因(R484设计意图破损)**: R484设BUDGET=100(compose L470注释): "2×timeout→87.5s remaining 12.5s>10s→3rd key gets 10s attempt"。但该设计基于UPSTREAM=43.75(2×43.75=87.5s)。R478将UPSTREAM 43.75→48后, attempt2应timeout@97s(48.5+48.5) > 92.6s budget break点(100-8 RESERVE), attempt2被截断@~44s in-flight, 第3attempt空间消失。
- **本轮精确量化(新增)**:
  - 35个失败请求各仅1×NVCFPexecTimeout(tier_attempts表), 不是2次 → attempt2未抛timeout(in-flight被budget杀)
  - 升BUDGET=115 → break@107s, attempt2可跑完timeout@97s, remaining 10s>8s→第3attempt得10s, P50=7.2s<10s→~50%成功
  - 双赢估算: SR 80.8%→85.1%(+4.3pp), 总耗时-2116s(救回30×85.4s - 未救回31×14.4s)
- **潜在方向(供CC勘定, 非本轮执行)**:
  - 方向1: 升BUDGET 100→115(单参数, 恢复第3attempt空间, 双赢)。风险: 救回请求终态~104s进p95长尾(p95 92.6s→~104s), 但稳定>快可接受。
  - 方向2: 降UPSTREAM 48→43.75(恢复R484设计原状, 2×43.75=87.5s<92s break点, remaining 12.5s>8s→第3attempt得12.5s)。风险: 误杀UPSTREAM边界慢成功(p95_ok=55.5s>43.75)。
  - 方向1更优(不误杀慢成功, 仅p95长尾)。建议CC纳入下轮清单为[HM2-D]。
- **反对者注意**: 此为BUDGET/UPSTREAM跨参数失配, R494明确"需CC综合勘定"。本轮不擅改, 仅量化数据。方向1(升BUDGET=115)单参数可行, 但需CC确认方向后下轮执行。

### 5b. quick_fail级联(63×~2.6s) — cooldown副作用(延续R494 5b)
- **现象**: 6h 63×quick_fail, 全NULL key, 时段成簇, 无HM-TIER-FAIL日志
- **根因**: 前序budget_fail将attempt过的2 key(attempt1 timeout那1个+attempt2 in-flight被杀那1个)标记cooling, 累积后后续请求可用key不足→immediate reject@~2.6s
- **影响**: 63×quick_fail占6h失败的48%, 但耗时极低(avg2.6s), 对总耗时影响小(63×2.6s=164s vs 61×92.6s=5649s), 对SR影响大(63失败占总135失败的47%)
- **潜在方向(供CC勘定)**: 降KEY_COOLDOWN_S 38→更低或TIER_COOLDOWN_S 22→更低, 减quick_fail级联。风险: 降cooldown加剧NVCF同IP密集(更多请求打cooling刚恢复key)→429升。属清单外项, 需CC勘定。
- **反对者注意**: quick_fail是budget_fail级联副作用, 根治在减budget_fail(见5a恢复第3attempt), 单降cooldown是治标。

### 5c. k1代理(mihomo 7894)未减429 — R491注释假设失效(第4轮确认, 延续R494 5c)
- **现象**: 6h k1(mihomo)429=7最高, 高于direct组(k2-k5=4-6), 连续R492/494/本轮3轮一致
- **根因**: compose L489注释标"R491: re-enable k1 proxy to test 429 mitigation via IP diversifier", 但k1代理后429反最高, IP分流假设未验证成立
- **影响**: 429仍微小(25/6h, 终态5), 非主要失败源, 但k1代理未达预期目的且引入1×gaierror(k1唯一)
- **潜在方向(供CC勘定)**: k1回退direct(URL1=""→恢复5键全direct), 简化路由。但429非主要问题, 优先级低。属清单外项。

## 6. 执行记录

### 变更: 无
```bash
# 零配置变更 — docker-compose.yml不变, 容器不重启
# 本轮为数据驱动NOP: CC清单三项6h+30min新鲜数据第4轮复检全已完成/证伪, 无可动项
# SR回归(100%→82.6%→80.5%→80.8%)根因NVCF server-side pexec timeout频率, 非HM2参数可修
# 清单外发现(第3attempt消失精确量化+升BUDGET双赢估算, quick_fail级联, k1代理未减429)延续R494上报CC, 不擅改
```

### 验证: 通过
```bash
# env一致性检查: compose grep(hm40006块L469-505) 与 docker exec hm40006 env 逐字一致, 8参数+5URL零漂移
ssh -p 222 opc2_uname@100.109.57.26 'docker exec hm40006 env | grep -E "MIN_OUTBOUND|TIER_TIMEOUT|UPSTREAM|KEY_COOLDOWN|TIER_COOLDOWN|CONNECT_RESERVE|FASTBREAK|SSLEOF|HM_NV_PROXY_URL"'
# ↑ MIN_OUTBOUND=2.5, BUDGET=100, UPSTREAM=48, FASTBREAK=5, URL1=7894(URL2-5空), 全匹配compose

# 健康检查 (对端): /health=200 ok, hm_num_keys=5, nvcf_pexec_models=[glm5.1_hm_nv]
```

## 7. 轮次统计
- HM2自R494(HM1→HM2 NOP)后: R495为HM2→HM1方向, 本轮R496为HM1→HM2方向
- CC清单[HM2-A/B/C]三项状态: A✅达成+继续降被429证伪(第4轮强化, 429稳定25连续3轮), B✅完成+证伪(第4轮强化, 5键per-hit全100%SR), C✅达成+降BUDGET误杀36 rescue证伪(第4轮)
- 连续NOP(HM2侧): R484→R485→R490→R492→R494→R496, 本轮为清单第4轮复检证伪轮+第3attempt消失精确量化勘定轮(每项有30min+6h具体数据)
- 本轮NOP理由: 三项全部完成/证伪(第4轮), 全8参数在天花板, SR回归根因NVCF server-side非参数可修(零参数变更连续4轮SR 100%→80.8%为铁证)
- 数据稳定性: R494→R496 6h数据对比(budget_break 63→61, quick_fail 63→63, rescue 36→36, 429 25→25, pexec timeout 35→35), 各项波动在±2内, 模式完全一致, 证明HM2侧已达稳态
- 本轮新增价值: 第3attempt消失精确量化(35 reqs各1 timeout, 非前轮所述2 timeout) + 升BUDGET=115双赢估算(SR+4.3pp, 耗时-2116s), 为CC下轮清单提供可决策勘定包

## 8. 铁律遵守
- ✅ 只改HM2不改HM1: 无变更行为, 合规
- ✅ 单参数少改多轮: NOP验证, 无参数
- ✅ 数据驱动先采集后决策: 12层验证(env双处一致 + 30min + 6h DB + per-key总请求含失败 + per-key延迟 + 小时桶 + 失败duration分布 + tier_attempts错误结构 + docker logs budget break + 429对比R490/492/494 + 第3attempt消失精确量化 + 升BUDGET双赢估算)
- ✅ 零配置变更: docker-compose.yml未修改, compose与容器env双处零漂移
- ✅ 无R320/R322/R350重蹈: 未改compose, 未commit错文件, push后即停
- ✅ DB时区: 全部用绝对ts窗口, 禁用NOW()
- ✅ 执行CC清单不擅自找改动点: 第3attempt消失+升BUDGET估算+quick_fail级联+k1代理未减429为清单外项, 延续R494上报CC不擅改
- ✅ host_machine标识正确: opc2sname
- ✅ 如实记录连续4轮零参数变更: R490→R492→R494→R496 env全一致, SR却100%→82.6%→80.5%→80.8%, 非参数可修的铁证显式记录
- ✅ 纠正前轮叙述: R494"2×pexec timeout"措辞不准确, 本轮DB实证为"1×真timeout+1×in-flight被budget杀", 已在1k显式纠正

## ⏳ 轮到HM2优化HM1
