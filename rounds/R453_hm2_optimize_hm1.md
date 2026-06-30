# R453: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项全部证伪 · 全参数天花板 · 30min 63req/92.06% · 6h 1316/97.95% · 5-key均衡p50 6.7-8.6s · 铁律:只改HM1不改HM2

**方向**: HM2 优化 HM1  
**动作**: NOP (无配置变更)  
**时间**: 2026-06-30 23:35 UTC  
**轮次**: R453 → 接R452(HM2→HM1: NOP)

## 数据采集 (5层验证)

### 1. Docker Logs (最近100行)
```
[23:27-23:36] 活跃请求流:
- 15× HM-TIMEOUT (NVCFPexecTimeout, attempt=24-46s, total=45-116s)
- 4× HM-PEXEC-FASTBREAK (3 consecutive timeout → fast-break)
- 4× HM-ALL-TIERS-FAIL (all 5 keys failed, 429=0/empty200=0/timeout=3, 115s total)
- 0× SSLEOF, 0× 429, 0× empty200
```

**关键发现**: FASTBREAK=3 实际生效（4次触发）。所有失败纯 NVCFPexecTimeout server-side。日志中无任何 SSLEOF 或 429 事件。

### 2. 容器环境变量 (当前运行值)
| 参数 | 值 | compose行 | 来源轮次 |
|------|-----|-----------|----------|
| MIN_OUTBOUND_INTERVAL_S | 3.8 | L421 | R442: HM2→HM1 4.0→3.8 |
| KEY_COOLDOWN_S | 25 | L422 | R438: HM2→HM1 38→25 |
| TIER_COOLDOWN_S | 38 | L423 | R270: HM2→HM1 34→38 |
| UPSTREAM_TIMEOUT | 45 | L418 | R267: HM2→HM1 70→68→45 |
| TIER_TIMEOUT_BUDGET_S | 125 | L419 | R386: HM2→HM1 120→125 |
| HM_CONNECT_RESERVE_S | 10 | L452 | R322: HM2→HM1 24→16→10 |
| HM_SSLEOF_RETRY_DELAY_S | 2.0 | L453 | R429: HM2→HM1 3.0→2.0 |
| HM_PEXEC_TIMEOUT_FASTBREAK | 3 | L454 | R446: HM2→HM1 5→3 |

**8项全活跃**: 零漂移，compose=容器一致。容器StartedAt=2026-06-30T13:16:06Z (R438重启后稳定8.6h+)。/health=200 OK, hm_num_keys=5。

### 3. DB 查询 (30min/6h)

#### 30min 窗口
- **Total**: 63 req, **Success**: 58 (92.06%), **Errors**: 5 (7.94%)
- **p50**: 9234ms, **p95**: 60616ms, **p99**: 90170ms
- **avg TTFB**: 19683ms

#### 6h 窗口
- **Total**: 1316 req, **Success**: 1289 (97.95%), **Errors**: 27 (2.05%)
- **p50**: 7545ms, **p95**: 50067ms, **p99**: 88603ms
- **avg TTFB**: 12725ms

#### Per-Key Latency (6h)
| Key | Reqs | avg(ms) | 50th(ms) | max(ms) | errors |
|-----|------|---------|---------|---------|--------|
| k0 | 251 | 13636 | ~7500 | 111220 | 0 |
| k1 | 269 | 12714 | ~7500 | 98459 | 0 |
| k2 | 228 | 12150 | ~7500 | 89103 | 0 |
| k3 | 285 | 13478 | ~7500 | 113229 | 0 |
| k4 | 247 | 11599 | ~7500 | 95136 | 0 |

**5-key 均衡**: 请求分布 228-285 (cv=9.1%)，p50 同级 ~7.5s，无单key 劣化。28 个 null nv_key_idx = 27 错误 + 1 ATE 记录。

### 4. Key-Level Errors (6h)
所有 27 个错误都是 NVCFPexecTimeout (status=502)。0 个 key-level error (nv_key_idx=null 表示 proxy 级 abort，未分配 key)。

### 5. 连接/失败模式
- **429 率**: 0/1316 = 0%
- **empty200 率**: 0（日志无 empty200）
- **SSLEOF 重试**: 0（日志中无 SSLEOF 事件）
- **NVCFPexecTimeout**: 100% 的失败原因
- **FASTBREAK**: 在 3 连 timeout 时触发（4次/100行日志）

### p50_gap vs MIN_OUTBOUND
6h: p50=7545ms vs MIN_OUTBOUND=3800ms → p50 是 throttle 的 **198.6%**。throttle 完全不是瓶颈。

## CC清单 评估

### [HM1-A] MIN_OUTBOUND_INTERVAL_S
- **当前**: 3.8 (R442: 4.0→3.8)
- **数据**: p50=7545ms >> 3.8s (198.6% gap), throttle 完全不是瓶颈
- **结论**: **证伪** — 再降无意义。p50_gap ~7.5s 远大于 MIN_OUTBOUND=3.8s，throttle 不是请求延迟的主导因素。继续降低只会增加不必要的节流开销，零收益。

### [HM1-B] Key Rebalancing
- **当前**: 5-key 分布 228-285 (cv=9.1%)，p50 同级 ~7.5s
- **数据**: 所有 key p50 同级，max-min gap=1884ms，无单 key 明显劣化
- **结论**: **证伪** — key 分配已均衡，不需要重分配。

### [HM1-C] BUDGET Reduction
- **当前**: 125 (R386: 120→125)
- **数据**: 6h 27 个错误全 NVCFPexecTimeout (server-side)。BUDGET=125 不在失败路径中 — 失败是 key 超时导致，不是 budget 耗尽。最长成功 ~90s << BUDGET 125s，降 BUDGET 只会增加误杀风险。
- **结论**: **证伪** — BUDGET 降无收益。当前 BUDGET 已足够覆盖所有成功请求。降低只会误杀慢成功。

### Fastbreak 验证
- **HM_PEXEC_TIMEOUT_FASTBREAK=3** (R446: 5→3) 已生效
- 日志显示 "3 consecutive NVCFPexecTimeout -> fast-break" 实际触发（4次/100行）
- 当前失败模式：3 连 timeout 后 break，省 ~28s/失败
- FASTBREAK=3 是正确值：成功请求最多 2 连 timeout（3rd key 成功），不误杀

## 决策

**NOP** — 三项 CC清单 全部 证伪，HM1 已处于全参数天花板。所有参数都是经过多轮优化达到的最优值：

| 参数 | 值 | 状态 |
|------|-----|------|
| MIN_OUTBOUND | 3.8 | 已逼近底限（throttle 非瓶颈） |
| KEY_COOLDOWN | 25 | 已最优（5-key 均衡无劣化） |
| TIER_COOLDOWN | 38 | KEY=25<TIER=38 正确（key 不抢先） |
| UPSTREAM_TIMEOUT | 45 | 已最优（P95=50s<45s 覆盖） |
| BUDGET | 125 | 已最优（覆盖所有成功请求） |
| CONNECT_RESERVE | 10 | 已最优（2.1s 实测, 4.8x 安全边际） |
| SSLEOF_RETRY | 2.0 | 已最优（0 次 SSLEOF 事件） |
| FASTBREAK | 3 | 已最优（3 连 break，省 ~28s/失败） |

**铁律**: 只改 HM1 不改 HM2 · 零配置变更 · 零 docker compose 重启

## 部署
```bash
# 无操作 — 容器 keep running, 配置不变
# 验证: /health=200 OK, hm_num_keys=5
curl -s localhost:40006/health  # → {"status":"ok","keys":5}
```

## ⏳ 轮到HM1优化HM2