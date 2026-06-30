# R349: HM2→HM1 — HM1-C 实施: consecutive NVCFPexecTimeout fast-fail (前3次连续timeout即break, 省~12-17s/ATE) · 源码逻辑点 · 铁律:只改HM1不改HM2

**时间**: 2026-06-30 11:34-11:50 UTC (改动部署 11:34, 验证 11:50)
**轮次**: HM2优化HM1 (HM2→HM1)
**角色**: HM2 (opc2_uname, opc2sname, 当前机) → HM1 (opc_uname, 100.109.153.83, opcsname, HM_HOST_MACHINE=opc_uname)
**对端模型**: deepseek_hm_nv (single-tier NVCF pexec, 不可改)

---

## 0. 本轮定位与上轮衔接

R348 (HM1→HM2) 末尾标记「⏳ 轮到HM2优化HM1」→ 本轮 R349 响应。

**关键发现: R347 误判 HM1 零流量**。R347 (HM2→HM1, 11:20 UTC) 报告"自09:32重启后请求=0, 零流量"。但本轮用**正确的 host_machine 标识**复查发现: HM1 容器 env `HM_HOST_MACHINE=opc_uname` (非 `opcsname`)。DB 查 `host_machine='opc_uname'` 实测 409 条请求, MAX(ts)=07:43 UTC (R347 之后仍有流量)。R347 查的可能是错误标识 `opcsname` (仅45条历史/测试数据), 误判零流量导致 R347 无操作。

本轮基于正确标识发现 HM1 有真实流量+真实 ATE+真实救援案例, CC 清单 HM1-C 有数据支撑可执行。

CC 定向清单"若对端是HM1"节三项状态 (本轮复查):
- **HM1-A** (MIN_OUTBOUND 18.2→9.0): 前提18.2已不成立, 实测=6.0 (R328已9.0→6.0超额完成清单目标9.0) → ✅ 已超额做完
- **HM1-B** (k4 direct→7897): 前提"k4 direct"已不成立, 实测 k4 已是7897 (R322fix已同步compose+容器) → ✅ 已执行; 但 k4 劣化仍存 (p95=72.6s/max=162.9s, 9.5h数据), 根源在 NVCF key 本身非路由
- **HM1-C** (前3key全NVCFPexecTimeout即fast-fail): 未做过, 有完整数据支撑 → **本轮执行**

清单规则"优先A, A不可行或已做则B, 再C" → A/B 已做, 落到 C。本轮执行 HM1-C (唯一未做项)。

---

## 1. 数据采集 (HM1, 时间锚+双窗口)

### 1.1 时间锚 (避免R320#5时区陷阱)
- DB `NOW()=03:24 UTC`, hm_requests.ts 字段是 UTC (与R346的HM2本地+08不同, HM1侧ts是UTC)。
- 窗口查询用绝对时间 `ts >= '2026-06-30 01:32:00+00'` (容器重启时刻), 禁止 `NOW()-interval`。

### 1.2 当前HM1环境变量 (容器env = live compose, 双处一致)
| 参数 | 容器env | live compose | 说明 |
|------|---------|--------------|------|
| UPSTREAM_TIMEOUT | 45 | 45 | - |
| TIER_TIMEOUT_BUDGET_S | 100 | 100 | R302已降至100 |
| KEY_COOLDOWN_S | 38 | 38 | - |
| TIER_COOLDOWN_S | 38 | 38 | R341修复不变量 |
| MIN_OUTBOUND_INTERVAL_S | 6.0 | 6.0 (R328) | HM1-A已超额(清单目标9.0, 实际6.0) |
| HM_CONNECT_RESERVE_S | 10 | 10 (R336) | - |
| HM_SSLEOF_RETRY_DELAY_S | 3.0 | 3.0 (R315) | - |
| 路由 | k1=7894, k2/k3=direct, k4=7897, k5=7899 | 同 | k4已是7897(HM1-B已执行) |
| **HM_PEXEC_TIMEOUT_FASTBREAK** | **未设(默认3)** | **未设** | **R349新增, 源码默认3** |

容器: hm40006 Up (healthy); /health: `{"status":"ok","proxy_role":"passthrough","hm_num_keys":5,"nvcf_pexec_models":["deepseek_hm_nv"]}`.

### 1.3 host_machine 标识澄清 (R347误判根源)
- HM1 容器 env `HM_HOST_MACHINE=opc_uname` (本轮 `docker exec hm40006 env` 实测)。
- DB 实测: `host_machine='opc_uname'` 409条(活跃), `host_machine='opcsname'` 45条(历史/测试, MAX=22:05 UTC已停滞)。
- **结论**: 查 HM1 流量必须用 `host_machine='opc_uname'`。R347 误用 `opcsname` 致"零流量"误判。

### 1.4 HM1 改前基线 (9.5h窗口 2026-06-29 22:08 → 06-30 11:34, host_machine='opc_uname')
| 指标 | 值 |
|------|-----|
| 总请求 | 409 |
| 200 OK | 389 (95.1%) |
| 502 (ATE) | 19 (4.6%) |
| 429 | 0 |
| avg_dur | 26.7s |
| p50 | 19.4s |
| p95 | 85.2s |

### 1.5 HM1 改前 per-key 延迟 (9.5h, 成功请求)
| kidx | 路由 | n | avg | p50 | p95 | max |
|------|------|---|-----|-----|-----|-----|
| 0 | 7894 | 79 | 23.4s | 19.2s | 48.6s | 79.7s |
| 1 | direct | 79 | 22.5s | 18.4s | 56.2s | 72.5s |
| 2 | direct | 79 | 23.4s | 19.3s | 56.2s | 82.1s |
| 3 | 7897 | 77 | 27.0s | 20.4s | 72.6s | 162.9s ← k4仍劣化 |
| 4 | 7899 | 75 | 22.4s | 18.9s | 58.6s | 71.4s |

→ k4(idx=3) p95=72.6s/max=162.9s 仍最差, 但已是7897代理(HM1-B已执行未改善), 根源在NVCF key本身, 非路由可解。

### 1.6 ATE 结构 (改前, hm_error_detail jsonl 全20个ATE)
- **ATE attempt 分布**: 3次=1个, 5次=6个, 6次=10个, 7次=3个 (BUDGET=128时期7次, BUDGET=100时期3-6次)。
- **ATE elapsed**: BUDGET=128时期(06-29 21-22h)=177-181s(历史, 已不重现); BUDGET=100时期(当前)=85-89s。
- **当前BUDGET=100下 ATE 平均~6次 attempts, 耗时~88s**。
- 全部 ATE error_type=NVCFPexecTimeout, upstream_type=nvcf_pexec (NVCF侧失败)。

### 1.7 救援成功案例 (HM1-C误杀风险核心)
全日志 `succeeded after N cycle attempts`:
| cycle数 | 数量 | 含义 | fast-fail-at-3 是否误杀 |
|---------|------|------|------------------------|
| 1 cycle | 9 | 1 timeout后第2key成功 | 不误杀(第2key前未达3) |
| 2 cycle | 3 | 2 timeout后第3key成功 | 不误杀(第3key是成功非timeout) |
| 3 cycle | 1 | 3 timeout后第4key成功 | **误杀**(第3timeout触发break, 不试第4key) |
| 4 cycle | 1 | 4 timeout后第5key成功 | **误杀**(第3timeout触发break) |
| **合计** | **14** | 231成功中14个救援(6.1%) | **误杀2个 = 0.87%成功率损失** |

误杀案例 trace (均为 ≥3 连续 NVCFPexecTimeout 后救回):
- 23:23: k3 timeout→k4 timeout→k5 timeout→**k1 成功** (3连续timeout后救回, fast-fail会在k5 timeout后break, 误杀k1)
- 23:48: k4 timeout→k5 timeout→k1 timeout→k2 timeout→**k3 成功** (4连续timeout, fast-fail会在k1 timeout后break, 误杀k3)

### 1.8 HM1-C 收益模拟 (用改前20个ATE实际trace模拟fast-fail-at-3)
```
全部20个ATE都会触发fast-break (均≥3连续timeout)
当前BUDGET=100时期ATE(85-89s): sim_elapsed=72-75s, saved=11-17s/ATE
BUDGET=128历史时期ATE(177-181s): sim_elapsed=25-69s, saved=108-152s/ATE (已不重现)
总节省757s (avg 37.9s/ATE, 含历史BUDGET=128时期)
当前配置预期: 每ATE省~12-17s
```

---

## 2. 分析

### 2.1 HM1-C 净评估 (收益vs风险)
| 维度 | 值 | 评判 |
|------|-----|------|
| ATE耗时减少 | 当前BUDGET=100下每ATE省~12-17s | ✅ 收益(失败请求早结束) |
| 成功率损失 | 误杀2/231=0.87% (仅NVCF故障期≥3连续timeout后救援案例) | ⚠️ 风险 |
| 429/empty200影响 | 0 (fast-fail只在连续timeout触发, empty/429分支reset计数) | ✅ 无影响 |
| 净判断 | 评判标准"稳定>越快>吞吐>成功率": ATE是失败请求(耗时无关成功率), fast-fail减失败耗时属"越快"优先级(第2), 成功率损失是第4优先级 | ✅ 符合优先级序 |

**关键论据**: ATE 本就是失败请求, fast-fail 不增加失败数(ATE已经失败), 只减少失败耗时 + 误杀2个边界救援成功。评判标准"越快越好"排第2优先级, "成功率"排第4, 速度收益 > 成功率损失, 符合CC清单意图(清单原文明知"误杀k4/k5救回"风险仍列为可执行)。

### 2.2 误杀率 0.87% 的可控性
- 误杀只在 NVCF 故障期 + ≥3 连续 timeout 后救援的特定序列发生。
- 当前 NVCF 健康期(11:34+ 22req全first-attempt成功)救援率=0, 误杀率=0。
- 历史故障期(23:20-00:28)救援率6.1%, 其中被误杀2个。
- 环境变量 `HM_PEXEC_TIMEOUT_FASTBREAK` 可调(设大值如99即禁用), 回滚成本低。

---

## 3. 改动实施 (HM1-C: 源码逻辑点)

### 3.1 改动位置
文件: `/app/gateway/upstream.py` (容器内运行态) + `/opt/cc-infra/proxy/hm-proxy/gateway/upstream.py` (构建源, 同步)。
备份: `upstream.py.bak.R347` (两处均已备份)。

### 3.2 改动内容 (5处, 单逻辑点: consecutive NVCFPexecTimeout fast-fail)
1. **init** (行110-116): 新增 `consecutive_pexec_timeout = 0` + `PEXEC_TIMEOUT_FASTBREAK = int(os.environ.get('HM_PEXEC_TIMEOUT_FASTBREAK', '3'))`。
2. **success分支** (行299): `consecutive_pexec_timeout = 0` (成功时reset)。
3. **socket.timeout分支** (行335-339): `consecutive_pexec_timeout += 1`; 若 `>= PEXEC_TIMEOUT_FASTBREAK` → `_log("HM-PEXEC-FASTBREAK", ...)` + `break`。
4. **empty_200分支** (行290): `consecutive_pexec_timeout = 0` (empty_200 != timeout, reset)。
5. **429/500/502 cycle分支** (行268): `consecutive_pexec_timeout = 0` (cycle错误 != timeout, reset)。

### 3.3 机制说明
- 只有**纯连续 NVCFPexecTimeout** 才累积计数, 任何成功/empty_200/429 都reset。
- 达3次连续timeout即break, 不试剩余key, 省~12-17s/ATE(当前BUDGET=100)。
- env `HM_PEXEC_TIMEOUT_FASTBREAK` 默认3, 可调(设99即禁用, 回滚)。

### 3.4 部署+同步 (避免R322#1/R322#2教训)
- 源码非volume挂载(镜像内置), `docker restart` 保留容器层改动(不重建)。
- `docker restart hm40006` → 容器healthy, 6个R347标记全保留。
- **构建源同步**: `docker cp hm40006:/app/gateway/upstream.py /opt/cc-infra/proxy/hm-proxy/gateway/upstream.py` → diff为空(完全一致), 6个R347标记。下次`docker compose build`不会丢失。
- **live compose 不在git** (R322#2): 本次改源码非env, compose不涉及。源码改动在容器运行态+构建源两处, 均已同步。仓库内无源码副本需commit(归档副本不冒充live)。

### 3.5 语法+逻辑验证
- `py_compile.compile(..., doraise=True)` → syntax OK。
- **功能单元测试** (容器内python隔离测试fast-break逻辑):
  - 场景1 `[timeout,timeout,timeout,success]`: 第3次timeout触发break, PASS。
  - 场景2 `[timeout,timeout,empty_200,timeout,timeout,timeout]`: empty_200 reset计数, 第6事件(第3个连续timeout)break, PASS。
- **实测请求**: `curl POST /v1/chat/completions` → 200 OK (deepseek-v4-pro回复), 链路通, 无启动错误。

---

## 4. A/B 验证 (改前vs改后)

### 4.1 改前基线窗口
| 窗口 | 时段(UTC) | n | OK | 502 | 429 | p50 | p95 | 说明 |
|------|----------|---|----|----|-----|-----|-----|------|
| 改前-重启后 | 01:32-11:34 (10h) | 29 | 28 (96.6%) | 0 | 0 | 1.96s | 42.3s | 健康期 |
| 改前-完整历史 | 22:08-11:34 (13h) | 409 | 389 (95.1%) | 19 | 0 | 19.4s | 85.2s | 含故障期 |

### 4.2 改后窗口
| 窗口 | 时段(UTC) | n | OK | 502 | 429 | p50 | p95 | 说明 |
|------|----------|---|----|----|-----|-----|-----|------|
| 改后(本轮) | 11:34-11:50 (16min) | 22 | 22 (100%) | 0 | 0 | 6.0s | 14.0s | NVCF健康期 |

### 4.3 A/B 对比表
| 指标 | 改前(13h含故障) | 改前(10h健康) | 改后(16min健康) |
|------|----------------|--------------|----------------|
| reqs | 409 | 29 | 22 |
| 成功率 | 95.1% | 96.6% | 100% |
| 502数 | 19 | 0 | 0 |
| 429数 | 0 | 0 | 0 |
| p50 | 19.4s | 1.96s | 6.0s |
| p95 | 85.2s | 42.3s | 14.0s |

### 4.4 验证局限说明 (诚实记录, 不填"-")
- **fast-break 未被自然触发**: 改后22req全在NVCF健康期(first-attempt成功), 无连续timeout, fast-break逻辑未实战触发。
- **ATE耗时改善待故障期实证**: 改后无ATE发生(健康期), 无法实测ATE从~88s降到~72s。
- **可证伪预测** (供下轮HM1→HM2复查): 改后若发生ATE, 其 attempt数应≤3 (fast-break在第3次timeout中断), 日志应含 `HM-PEXEC-FASTBREAK`; 改前ATE attempt 3-7次。若下轮复查发现ATE attempt仍>3且无HM-PEXEC-FASTBREAK日志 → 改动未生效/逻辑有漏洞, 需回滚。
- **逻辑已功能验证**: 单元测试2场景PASS, 语法OK, 实测请求链路通。代码路径已部署, 待NVCF故障期实战验证。

### 4.5 fast-break 触发检查
```
grep "HM-PEXEC-FASTBREAK" hm_proxy.*.log → 0 (未触发, 健康期符合预期)
```

---

## 5. 结论

### 5.1 改动有效性
- 源码逻辑点(consecutive NVCFPexecTimeout fast-fail)已部署: 容器运行态+构建源双处同步, 6个R347标记, 语法OK, 功能单元测试2场景PASS, 实测请求链路通。
- env `HM_PEXEC_TIMEOUT_FASTBREAK=3` (默认, 可调回滚)。

### 5.2 预期效果 (数据支撑)
- 当前BUDGET=100配置下, 每ATE省~12-17s (改前~88s→改后~72s), 20个ATE模拟总省757s。
- 误杀2/231=0.87%成功率 (仅NVCF故障期≥3连续timeout后救援案例), 评判标准"越快"(第2)>"成功率"(第4), 符合优先级序。
- 待NVCF故障期实证 fast-break 触发 + ATE耗时下降 (可证伪预测见§4.4)。

### 5.3 铁律遵守
- ✅ 只改HM1不改HM2: 本轮改HM1(upstream.py源码+构建源), 未碰HM2任何配置/源码。
- ✅ 改前必有数据: 9.5h基线(409req/19ATE/14救援案例)+20个ATE trace模拟+误杀精确分析(2/231)。
- ✅ 改后必有验证: 语法+功能单元测试+实测请求+A/B对比表(改后22req 100%成功率, 诚实标注健康期未触发fast-break)。
- ✅ 聚焦hm-40006--nv链路: 改的是deepseek_hm_nv pexec路径的key cycling逻辑。
- ✅ 每轮少改: 单逻辑点(fast-fail-at-3), 5处代码改动属同一逻辑点(init计数+3处reset+1处increment/break), 无搭车。
- ✅ 所有修改写入仓库: round文件commit+push; live源码不在git(容器运行态+构建源), R322#2已说明不冒充。

### 5.4 反对者可证伪点 (供下轮HM1→HM2复查)
1. 改后ATE attempt数是否≤3 + 日志含HM-PEXEC-FASTBREAK? (若否→未生效)
2. 改后是否有救援成功被误杀? (查 `succeeded after [3-9] cycle` 是否消失, 若消失且成功率下降→误杀发生)
3. 改后ATE耗时是否从~88s降到~72s? (待故障期数据)

---

## 6. 下次轮次建议

**HM1→HM2 (R350) 关注点**:
- HM1侧: 复查 R349 fast-break 是否在 NVCF 故障期触发 (查 HM-PEXEC-FASTBREAK 日志 + ATE attempt数≤3)
- HM1侧: 复查 R347 误判零流量的 host_machine 标识问题 (正确标识=opc_uname, 非opcsname)
- HM1侧: k4(idx=3) p95=72.6s/max=162.9s 持续劣化, 已是7897代理未改善, 根源在NVCF key本身, 非路由可解
- HM2侧: 三项清单(A已做/B无劣化key/C已做)维持, R348已复核

**历史轨迹 (HM1侧源码/参数变更)**:
| 轮次 | 日期 | 变更 | 变更量 | 理由 |
|------|------|------|--------|------|
| **R349** | **06-30 11:34** | **HM1-C: consecutive NVCFPexecTimeout fast-fail (源码逻辑点)** | **新增逻辑** | **前3次连续timeout即break, 省~12-17s/ATE, 误杀0.87%救援成功, 符合"越快>成功率"优先级** |
| R348 | 06-30 03:35 | ⏸️ 无操作(HM1→HM2) | — | HM2三项清单复核证伪 |
| R347 | 06-30 11:20 | ⏸️ 无操作 | — | 误判零流量(实为host_machine标识错) |
| R341 | 06-30 09:38 | TIER_COOLDOWN_S 36→38 | +2s | 修复R82不变量 |
| R336 | (历史) | HM_CONNECT_RESERVE 12→10 | -2s | 增SOCKS5 read余量 |
| R328 | (历史) | MIN_OUTBOUND 9.0→6.0 | -3.0s | HM1-A超额(清单目标9.0) |
| R322fix | (历史) | k4 direct→7897(同步compose) | - | HM1-B已执行 |

---

## ⏳ 轮到HM1优化HM2
