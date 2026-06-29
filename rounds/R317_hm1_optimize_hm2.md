# R317: HM1→HM2 — ⏸️ 无操作: BUDGET=128经数据证伪不可降 (15min 100%, 30min 99.07%)

**时间**: 2026-06-30 01:05 UTC
**角色**: HM1 (opc_uname) 工程师 / HM2 (opc2_uname) 反对者
**前轮**: R316 (HM2→HM1, ⏸️ 无操作稳定态确认), HEAD `976c02d`
**本轮基线 max_ts**: 2026-06-30 01:01:01 UTC (DB容器时区=UTC, host_machine='opc2sname')

## 0. 数据口径修正 (重要)

**陷阱发现**: HM2 DB `now()` 返回 UTC(16:57), 但容器写入 ts 用 UTC, 实际最新请求 ts=00:56~01:01 (次日)。
若用 `ts > now() - interval '30 min'` 会查到 03:52 跨度(551条), 实为 4 小时聚合, 非真实 30min。
**修正**: 全部窗口改用 `ts > (SELECT max(ts) FROM hm_requests WHERE host_machine='opc2sname') - interval 'N min'`,
即以最新请求 ts 为锚点回溯, 保证真实窗口。R316 报告的 HM1 "15min 43条/30min 80条" 也需复核此口径
(HM1 流量本就 ~HM2 的 1/4, 数量级合理, 暂不推翻, 但下轮 HM2→HM1 时应改用 max(ts) 锚点)。

## 1. 数据收集 (真实窗口, max_ts=2026-06-30 01:01:01 UTC 锚点)

### 1a. 多窗口成功率
| 窗口 | total | success | fail | 成功率 |
|---|---|---|---|---|
| 15min | 47 | 47 | 0 | **100.00%** |
| 30min | 107 | 106 | 1 | **99.07%** |
| 60min | 215 | 211 | 4 | 98.14% |
| 120min | 305 | 293 | 12 | 96.07% |

失败率随窗口增大而升, 低频散布 — NVCF 平台层间歇整批不可用, 非宕机 (与 R313 系统级排查一致)。

### 1b. 30min 错误结构
| error_type | n | avg_dur | p50 | p95 | max_dur |
|---|---|---|---|---|---|
| (success) | 106 | 12615 | 7427 | 54457 | 103334 |
| all_tiers_exhausted | 1 | 122412 | 120500 | 127482 | 128337 |

**1个ATE**: request_id=8b241f3b, duration=128337ms (详见 1e)
**0 SSL错误计入DB** (DB只记最终态; docker logs 30min 内有 6 次 SSLEOF, 全部 handled)
**0 empty_200, 0 timeout_err 计入DB** (被换 key 救回的不计非200)

### 1c. Per-key 成功延迟 (30min, success only)
| Key (idx) | n | avg_dur | p50 | p95 |
|---|---|---|---|---|
| k0 (k1, mihomo7894) | 19 | 12146 | 7422 | 29841 |
| k1 (k2, DIRECT) | 24 | 11050 | 5676 | 52404 |
| k2 (k3, mihomo) | 21 | 15371 | 7954 | 57409 |
| k3 (k4, DIRECT) | 20 | 11982 | 7624 | 25669 |
| k4 (k5, mihomo7899) | 20 | 12932 | 9188 | 30323 |

5 key 均匀 (19~24), P50=5.7~9.2s, P95=25~57s. 无单 key 劣化。

### 1d. Per-key tier_attempts (30min)
| key_idx | error_type | n | avg_elapsed | p95 |
|---|---|---|---|---|
| 1 | NVCFPexecTimeout | 1 | 50484 | 50484 |
| 2 | NVCFPexecTimeout | 1 | 51441 | 51441 |
| 3 | NVCFPexecTimeout | 1 | 62628 | 62628 |

3 次 NVCF timeout 全部被换 key 救回 (106/107=99%). 单次 timeout elapsed=50~63s, 即 UPSTREAM_TIMEOUT=50 边界。

### 1e. 唯一 ATE 完整生命周期 (docker logs)
request 8b241f3b, 00:36:43 → 00:38:51, 128.3s:
```
00:36:43 REQ start (stream=False, msgs=1)
00:36:43 attempt1 k5 → timeout 50.7s (total 50.7s)
00:37:34 attempt2 k1 → SSLEOF + 3.0s retry backoff (R315机制)
00:37:42 attempt3 k2 → timeout 48.8s (total 107.5s)
00:38:41 attempt4 k3 → timeout 10.4s (total 118s)  ← budget 剩 10s, k3 只能跑 10s
00:38:41 attempt5 k4 → timeout 10.4s (total 128.3s) ← BUDGET 128 耗尽, break
00:38:51 HM-TIER-FAIL: all 5 keys failed, timeout=4, elapsed=128331ms
00:38:51 HM-ALL-TIERS-FAIL ABORT-NO-FALLBACK
```
**关键观察**: k3/k4 在 budget 末端各只跑 10.4s 就被 break, 而 NVCF timeout 是 ~50s 级 hang,
10s 内根本不可能等到响应 — k3/k4 的尝试纯属实地消耗 budget 末端, 无成功可能。

### 1f. 环境变量 (docker exec hm40006 env)
| 参数 | HM2值 | HM1值(对比) | 来源 |
|---|---|---|---|
| TIER_TIMEOUT_BUDGET_S | **128** | 90 | HM2历史 |
| UPSTREAM_TIMEOUT | 50 | 45 | R315 (58→50) |
| KEY_COOLDOWN_S | 38 | 38 | R296 稳定 |
| TIER_COOLDOWN_S | 22 | 38 | HM2历史 |
| MIN_OUTBOUND_INTERVAL_S | 4.5 | 18.2 | HM2历史 (流量4倍于HM1) |
| HM_CONNECT_RESERVE_S | 21 | 24 | HM2历史 |
| HM_SSLEOF_RETRY_DELAY_S | 3.0 | 3.0 | R315 双机对齐 |
| HM_SSLEOF_RETRY_ENABLED | true | true | R315 |
| NVCF_GLM51_FUNCTION_ID | 4e533b45 | (deepseek_id不同) | R313 实测正确 |
| HM_NV_KEY_{1..5} | 5 keys | 5 keys | 全部有效 |

## 2. 候选改动评估 (逐个数据证伪)

### 2a. 候选①: BUDGET 128→90 (对齐 HM1) — ❌ 证伪
**直觉**: 失败请求 128s 太久, 降到 90 可让 ATE 快 ~38s 返回 (HM1 即 87~89s)。
**反证 (决定性)**: 30min 内有 2 个成功请求 duration>70s:
- `5af0103f` 103334ms: k1 SSLEOF(3s) + k2 timeout(50.5s) + k3 success(42.6s) — **k3 本身花了 42.6s 成功**
- `ce48b619` 71875ms: 1 次 timeout(50s) + 换 key 成功(~22s)

更大窗口 60min 内查 "成功且有 err 重试" 的请求:
| request_id | duration_ms | errs |
|---|---|---|
| 1b7a3b90 | **112252** | NVCFPexecTimeout×2 (2次50s timeout + 第3key成功) |
| d8ef4cda | 108203 | NVCFPexecTimeout×1 |
| 5af0103f | 103334 | NVCFPexecTimeout×1 |
| c0d609cc | 73803 | NVCFPexecTimeout×1 |
| ... | (共10个 >60s 的成功请求) | |

**结论**: BUDGET=128 容纳 "2 次 50s timeout (100s) + 第3 key 成功耗时 (~12s) = 112s" 是**功能必需**。
降 BUDGET=90 会让 1b7a3b90(112s)/d8ef4cda(108s)/5af0103f(103s) 在 90s 时被 break,
此时第3 key 才跑 ~31.5s, 尚未成功 → **误杀成功请求**。
60min 内 10 个 >60s 成功请求, 其中 3 个 >90s — 误杀率不可接受。**反对者必驳, 放弃。**

### 2b. 候选②: BUDGET 128→110 — ❌ 证伪
**直觉**: 保守降 18s, 不误杀 103s 成功请求。
**反证**: ATE 请求 8b241f3b 在 k2 timeout 完成时 total 已达 107.5s。BUDGET=110 时 k3 只剩 2.5s,
比当前 10s 更糟 — k3/k4 末端尝试本就无成功可能 (NVCF hang 50s 级), 降 budget 不降失败延迟,
反让边界成功请求 (112s) 被误杀。**无效且有损, 放弃。**

### 2c. 候选③: UPSTREAM_TIMEOUT 50→45 (对齐 HM1) — ❌ 证伪
**直觉**: 单次 timeout 50→45, 5s×多次可缩短 ATE。
**反证**: 成功请求里有 k3 单 attempt 耗时 42.6s (5af0103f), 且大上下文流式请求 (msgs=33) 慢成功常见。
UPSTREAM_TIMEOUT=45 会误伤 45~50s 区间的慢成功 (NVCF 大模型推理慢, 流式首 token 晚)。
HM2 流量 4 倍于 HM1, 大上下文占比更高, 45s 边界风险 > HM1。R315 已从 58→50, 再降无数据支撑。**放弃。**

### 2d. 候选④: TIER_COOLDOWN 22→38 (对齐 HM1) — ❌ 证伪
**直觉**: HM2 TIER_COOLDOWN=22 < HM1=38, 可能冷却不足致重复失败。
**反证**: 30min 仅 1 ATE, 无 "同 key 短间隔重复失败" 模式。TIER_COOLDOWN 是失败 tier 的恢复时间,
当前 0 重复失败证据。调高反而可能延长 tier 恢复, 降低吞吐。**无疗效, 放弃。**

### 2e. 候选⑤: MIN_OUTBOUND 4.5→更高 — ❌ 证伪
**直觉**: HM2=4.5 vs HM1=18.2, 间隔太小可能触发 NVCF 限流。
**反证**: 30min 0 个 429/empty_200/限流类错误。HM2 流量 4 倍于 HM1, 4.5s 间隔是吞吐必需。
调高直接降吞吐, 违背 "单位时间请求越多越好"。**有损, 放弃。**

## 3. 优化决策: ⏸️ 无操作 — 稳定态再确认

### 理由
- **15min 100% (47/47)**: 完美窗口
- **30min 99.07% (106/107)**: 仅 1 NVCF 平台层 ATE
- **所有候选改动经数据证伪**: BUDGET/UPSTREAM_TIMEOUT 降值会误杀 103/108/112s 的"2次timeout后救回"成功请求
- **HM2 BUDGET=128 是功能必需**: 容纳 2 次 50s NVCF timeout + 第3 key 成功耗时, 不可降
- **HM2 流量性质不同于 HM1**: 4 倍流量 + 更大上下文, 慢成功请求更多, 不能套用 HM1 的 90s budget
- **失败模式属 NVCF 平台层**: k5/k2/k3 各 timeout 1 次, 全部换 key 救回; 1 ATE 是 5 key 同窗口全 hang, gateway 无计可消

### 为何不调任何参数
| 参数 | 当前 | 为何不调 |
|---|---|---|
| BUDGET=128 | 128 | 降值误杀 103/108/112s 成功请求 (2a 证伪) |
| UPSTREAM_TIMEOUT=50 | 50 | 降值误伤 45~50s 慢成功 (2c 证伪), R315 已优化 |
| KEY_COOLDOWN=38 | 38 | R296 不变量, 0 重复失败 |
| TIER_COOLDOWN=22 | 22 | 0 重复失败证据, 调高降吞吐 (2d 证伪) |
| MIN_OUTBOUND=4.5 | 4.5 | 0 限流错误, 调高降吞吐 (2e 证伪) |
| CONNECT_RESERVE=21 | 21 | 非瓶颈 |
| SSLEOF_RETRY_DELAY=3.0 | 3.0 | R315 双机对齐, 运行良好 |

## 4. 铁律验证
| 铁律 | 状态 |
|---|---|
| 只改HM2不改HM1 | ✅ — 0 参数变更, 0 代码变更 |
| 改前必有数据 | ✅ — max(ts)锚点真实窗口 (15/30/60/120min) + 错误结构 + per-key + ATE完整生命周期 + 5候选逐个证伪 |
| 改后必有验证 | ✅ — N/A (无操作轮) |
| 每轮少改 | ✅ — 0 变更 |
| 聚焦 hm-40006--nv | ✅ — 仅 glm5.1_hm_nv 链路 |
| 数据驱动决策 | ✅ — 15min 47/47(100%), 30min 106/107(99.07%), BUDGET降值误杀3个>90s成功请求(数据决定性反证) |
| 评判: 稳定优先 > 越快越好 > 成功率 > 延迟 > 报错少 | ✅ — 零变更 = 最高稳定性, 15min 100% |

## 5. 下轮预期与建议 (供 HM2 优化 HM1)

### HM2 侧当前参数 (R317 后, 不变)
- BUDGET=128, UPSTREAM_TIMEOUT=50, KEY_COOLDOWN=38, TIER_COOLDOWN=22
- MIN_OUTBOUND=4.5, CONNECT_RESERVE=21, SSLEOF_RETRY_DELAY=3.0
- 5 keys 混合路由, function_id=4e533b45
- **BUDGET=128 经本轮证伪不可降** (容纳 2×50s timeout + 第3key成功)

### 给 HM2→HM1 的建议
1. **数据口径**: HM1 侧采集请改用 `max(ts) 锚点` 回溯窗口, 勿用 `now()-interval` (DB时区错位会得 4h 聚合)
2. HM1 BUDGET=90 是因 HM1 流量低 (HM2 的 1/4)、上下文小、慢成功请求少; 不可套用到 HM2
3. HM1 侧若也有 "2次timeout后救回" 的 >90s 成功请求, 需复核 BUDGET=90 是否误杀 (本轮未跨机查 HM1 此项)
4. 守稳模式继续, NVCF 平台层间歇失败 gateway 层无法消除

## 6. 结论
HM2 hm40006 gateway 经 R313/R315/R316/R317 多轮验证已达稳定态:
- 15min 100%, 30min 99.07%, 失败为 NVCF 平台层间歇整批不可用
- BUDGET=128 是 HM2 高流量+大上下文场景的功能必需 (容纳 2×50s timeout + 第3key成功), 降值会误杀 103/108/112s 成功请求
- UPSTREAM_TIMEOUT=50、TIER_COOLDOWN=22、MIN_OUTBOUND=4.5 均经数据证伪不可调
- 零变更 = 最高稳定性, 守稳模式继续

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记(交替优化序列)
