# R547 (HM1→HM2): ⏸️ NOP — [HM2-B]数据补采完成: 5key全100%SR无劣化, 失败100%为NVCF surge致empty_200(61s)+timeout(16s), FASTBREAK=1合理(timeout cycle救回0/4), A/C前提证伪(MIN_OUTBOUND已1.0, BUDGET已80). 全部参数改动候选数据否决. 单参数少改多轮. 铁律:只改HM2不改HM1

## 本轮定位

本轮我是HM1工程师, 对端=HM2(opc2sname, 容器hm40006, 后端glm5.1_hm_nv不能改). CC定向清单[HM2-*]三项:
- [HM2-A] MIN_OUTBOUND_INTERVAL_S 4.5→2.5
- [HM2-B] HM2失败模式数据补采(采60min per-key延迟+失败结构, 看是否有劣化key)
- [HM2-C] TIER_TIMEOUT_BUDGET_S 128→100

按规则优先A, A不可行则B, 再C. 本轮选第1个未完成的执行.

## 漂移检测 (对端HM2 容器env vs compose)

容器hm40006 env (docker exec env):
| 参数 | 容器env | CC清单假设 | 状态 |
|------|--------|-----------|------|
| MIN_OUTBOUND_INTERVAL_S | 1.0 | 4.5 | ❌前提证伪(已1.0<2.5) |
| TIER_TIMEOUT_BUDGET_S | 80 | 128 | ❌前提证伪(已80<100) |
| UPSTREAM_TIMEOUT | 61 | - | - |
| KEY_COOLDOWN_S | 38 | - | - |
| TIER_COOLDOWN_S | 22 | - | - |
| HM_CONNECT_RESERVE_S | 3 | - | - |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | - | - |
| HM_PEER_FALLBACK_TIMEOUT | 50 | - | - |
| HM_PEXEC_TIMEOUT_FASTBREAK | 1 | - | - |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | - | - |
| HM_NV_PROXY_URL1..5 | 7894/7894/7895/7897/7896 | - | - |
| 容器StartedAt | 2026-07-02T00:38:24Z | - | 本轮未重启 |

**[HM2-A]前提证伪**: MIN_OUTBOUND实际1.0(非CC假设的4.5), 已<2.5目标, 无可降空间.
**[HM2-C]前提证伪**: BUDGET实际80(非CC假设的128), 已<100目标, 无可降空间.
→ 顺延执行 [HM2-B] 数据补采.

## [HM2-B] 数据补采 (60min窗口 02:10-03:10 UTC, host=opc2sname)

### 总体 by mapped_model
| mapped_model | reqs | ok | sr | avg_ms | p50 | p95 | empty200_ok | fail |
|--------------|------|----|----|--------|-----|-----|-------------|------|
| kimi_nv | 1109 | 949 | 85.6% | 22899 | 11079 | 77428 | 28 | 160 |
| dsv4p_nv | 33 | 20 | 60.6% | 43255 | 40124 | 61790 | 1 | 13 |

### kimi_nv per-key (核心: 否决"劣化key"假设)
| nv_key_idx | reqs | ok | sr | avg_ms | p50 | p95 | max_ms |
|-----------|------|----|----|--------|-----|-----|--------|
| 0(k1) | 196 | 196 | 100.0% | 13722 | 8228 | 47430 | 72020 |
| 1(k2) | 201 | 201 | 100.0% | 13777 | 8061 | 48294 | 76982 |
| 2(k3) | 198 | 198 | 100.0% | 14204 | 8854 | 43009 | 63742 |
| 3(k4) | 196 | 196 | 100.0% | 14164 | 8166 | 46126 | 67645 |
| 4(k5) | 193 | 192 | 99.5% | 15340 | 8516 | 47264 | 120264 |
| **NULL** | 206 | 31 | **15.0%** | 61646 | 57354 | 97462 | 97869 |

**关键发现**: 5个key(idx0-4)全部100%SR(仅k5有1失败), p95~47s, avg~14s — **零key劣化**. 与HM1 R546结论对称(HM1也是5key全100%). nv_key_idx=NULL的206req才是失败主体(SR=15%), 这些是**从未成功分配key的请求**(见下失败链路).

### 失败结构 (kimi_nv 160 fail)
| error_type | cnt | avg_ms | max_ms |
|-----------|-----|--------|--------|
| all_tiers_exhausted | 159 | 70325(p50=77290) | 120264 |
| NVStream_IncompleteRead | 1 | 120264 | 120264 |

### 失败链路根因追踪 (日志docker logs, 样本request_id=fc5ea664 ts=09:04:28 duration=77963ms)

完整失败链路(从日志逐行重建):
```
[09:04:28.8] HM-REQ mapped_model=kimi_nv stream=True tier_chain=['kimi_nv'] (no fallback)
[09:04:28.8] HM-INJECT-THINKING (kimi_nv) body had no reasoning_effort → injected reasoning_effort='low'
[09:04:28.8] HM-KEY tier=kimi_nv attempt 1/7: k1 → NVCF pexec via 7894
   ↓ k1 pexec 跑61s (thinking请求 extended timeout=HM_FORCE_STREAM_UPGRADE_TIMEOUT=61s)
[09:05:29.8] HM-EMPTY-200 k1 (kimi_nv) → 200 Content-Length:0 (stream)   ← NVCF思考61s后返回空流
[09:05:29.8] HM-EMPTY-CYCLE tier=kimi_nv k1 empty 200, cycling            ← empty200触发cycle到k2
[09:05:29.8] HM-KEY tier=kimi_nv attempt 2/7: k2 → NVCF pexec via 7894
   ↓ k2 跑16.9s (remaining_budget=80-61=19s, per_attempt_timeout=min(61,19-3)=16s → budget截断)
[09:05:46.8] HM-TIMEOUT k2 timeout: attempt=16927ms total=77954ms
[09:05:46.8] HM-PEXEC-FASTBREAK 1 consecutive NVCFPexecTimeout -> fast-break  ← FASTBREAK=1触发
[09:05:46.8] HM-TIER-FAIL all 5 keys failed: 429=0, empty200=1, timeout=1, elapsed=77955ms
[09:05:46.8] HM-ALL-TIERS-FAIL elapsed=77963ms, ABORT-NO-FALLBACK
[09:05:46.8] HM-PEER-FB peer-originated request (hop=1) also all_tiers_exhausted, returning 502
```

### 失败模式分布 (90min日志 grep HM-TIER-FAIL)
| 模式 | cnt | 说明 |
|------|-----|------|
| e1_t1 (empty200=1, timeout=1) | 11 | empty_200耗61s + timeout耗16s = 77s |
| e0_t1 (empty200=0, timeout=1) | 4 | 纯timeout, attempt 17-62s |

**模式高度一致**: 15/15失败都是"试1-2个key后FASTBREAK=1放弃", 从未试到k3/k4/k5. 全部为peer-fb(hop=1)请求, HM2本地无fallback.

### empty_200 cycle救回率 (证FASTBREAK=1合理)
- 13次成功是"succeeded after 1 cycle attempts" — **全部是empty_200 cycle**(k1 empty_200 → k2/k3成功), duration 66-75s
- **0次是timeout cycle成功** — surge期间timeout是NVCF整体慢, 换key也timeout, 救回率=0/4

## 候选改动评估表 (全部数据否决)

| 候选 | 当前→新 | 评估数据 | 决策 |
|------|--------|----------|------|
| [HM2-A] MIN_OUTBOUND 4.5→2.5 | 实际1.0(非4.5) | CC前提证伪, 已1.0<2.5 | ❌前提不成立 |
| [HM2-C] BUDGET 128→100 | 实际80(非128) | CC前提证伪, 已80<100 | ❌前提不成立 |
| FASTBREAK 1→2 | 1→2 | timeout cycle救回率0/4(0%); surge期timeout换key仍timeout; 多耗budget无收益 | ❌ |
| FORCE_STREAM_UPGRADE_TIMEOUT 61→50 | 61→50 | 1047ok中52个>50s(5.0%)会误杀; p95=48.8s接近50 | ❌误杀过重 |
| FORCE_STREAM_UPGRADE_TIMEOUT 61→55 | 61→55 | 29个>55s(2.8%)会误杀; max_ok=76.9s | ❌误杀 |
| BUDGET 80→75 | 80→75 | max_ok=76.9s>75会误杀慢成功; 失败已77s, 降BUDGET只早结束不增SR | ❌误杀且无效 |
| empty_200提前检测 | 改源码_check_empty_200 | stream请求61s是等response header(NVCF接受连接后61s才回header), 无法更早检测; 属C类高风险 | ❌不可行 |
| ttfb timeout提前fail | 加ttfb阈值 | 成功ttfb p95=45.9s max=76.9s; 任何短ttfb阈值都误杀 | ❌误杀 |

## 决策分析

1. **[HM2-B]核心命题证伪**: HM2不存在劣化key. 5key全100%SR, 失败100%源于NVCF function-level surge(empty_200 61s + timeout 16s). 与HM1 R546结论完全对称(双机都确认NVCF surge是root cause, 网关参数已最优).
2. **FASTBREAK=1合理**: empty_200不递增consecutive_pexec_timeout(源码line 290 reset), 所以empty_200后接1次timeout才触发fast-break. timeout cycle救回率0/4证明"surge期换key无效", FASTBREAK=1节省budget是正确设计.
3. **empty_200的61s不可压缩**: kimi_nv inject=reasoning_effort:low → 所有kimi_nv请求都是thinking请求 → 都用61s extended timeout. 成功请求max=76.9s证明61s对成功是必要的. 降timeout误杀>2.8%.
4. **失败请求的budget耗尽是empty_200的后果**: empty_200耗61s后remaining=19s, 下一个key per_attempt_timeout=16s, 不足以完成正常思考(p95=47s), 注定timeout. 这是NVCF surge的级联效应, 非参数可解.
5. **peer-fb请求hop=1无法再fallback**: 失败全为HM1转来的hop=1请求, HM2本地all_tiers_exhausted后不再转发(X-Fallback-Hop≥1), 返回502. 这是设计上的循环防护, 非缺陷.

## 结论

[HM2-B]数据补采任务完成, 命题证伪: HM2无劣化key, 失败为NVCF function-level surge, 网关参数已最优. CC清单[HM2-A]/[HM2-C]前提均证伪(MIN_OUTBOUND已1.0, BUDGET已80). 全部参数改动候选被数据否决. 本轮为**数据证伪型NOP**(非"无操作"——完成了[HM2-B]的60min数据补采任务, 给出了每个候选的具体否决数据).

本轮未改任何参数/源码, 容器未重启(StartedAt=00:38:24Z, 在本轮之前).

## ⏳ 轮到HM2优化HM1
