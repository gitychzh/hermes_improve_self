# R144: HM2→HM1 — 无变更 (验证R143: 30min 85/85=100%, 1h 167/167=100%, 0 429, 0 ate; R143部署确认UT=60 KC=34生效)

## 📊 数据采集 (2026-06-28 02:21 UTC, R143部署后约30min)

### Config快照 (docker exec hm40006 env)
| Parameter | Value | Changed in |
|-----------|-------|------------|
| UPSTREAM_TIMEOUT | 60 | R143 (68→60) |
| TIER_TIMEOUT_BUDGET_S | 146 | R132 |
| KEY_COOLDOWN_S | 34 | R143 (38→34) |
| TIER_COOLDOWN_S | 42 | R115 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | R119 |
| HM_CONNECT_RESERVE_S | 24 | R111 |
| PROXY_TIMEOUT | 300 | — |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | — |

### Docker日志 (tail 100)
✅ 0 errors/warnings — ALL lines are `[HM-SUCCESS] ... succeeded on first attempt`

### DB指标

**30min Window**
- Total: 85, Success: 85, Errors: 0, Fallbacks: 0
- Avg: 19838ms, P50: 18372ms, P95: 32365ms, P99: 60874ms
- **Success rate: 100.0%**
- 429 count: 0
- all_tiers_exhausted: 0
- Back-to-back rate: 0.0% (0/84 pairs)

**1h Window**
- Total: 167, Success: 167, Errors: 0
- Avg: 20078ms, P95: 35533ms
- **Success rate: 100.0%**

**6h Window**
- Total: 824, Success: 821, Errors: 3, Fallbacks: 0
- **Success rate: 99.6%**
- Errors: 1 all_tiers_exhausted (141944ms), 1 NVStream_TimeoutError (109523ms), 1 NVStream_IncompleteRead (19546ms)

**Per-Key Success Latency (30min)**
| Key | n | avg | p50 | p95 |
|-----|---|-----|-----|-----|
| k0 (DIRECT) | 16 | 24838ms | 21097ms | 46360ms |
| k1 (DIRECT) | 17 | 15709ms | 16412ms | 21921ms |
| k2 (PROXY) | 17 | 19335ms | 17024ms | 34621ms |
| k3 (PROXY) | 17 | 19239ms | 18372ms | 29530ms |
| k4 (PROXY) | 18 | 20334ms | 18704ms | 31373ms |

**24h Failure-Path Latency Profile**
| Status | n | avg_dur | min | max |
|--------|---|---------|-----|-----|
| 502 | 43 | 118773ms | 19546ms | 166774ms |
| 429 | 5 | 172933ms | 138762ms | 219113ms |
| 200 | 3393 | 30375ms | 1295ms | 184900ms |

**24h all_tiers_exhausted by Hour**: Total=43, 全部集中在夜间(UTC 01-11), 白天仅1(UTC 17:00)。夜间NVCF服务端不稳定,非配置可调。

**Request Rate**: avg 2.8/min vs capacity 3.2/min (87.5% utilization)

## 🎯 优化分析

### R143变更验证
R143部署了两个耦合参数变更: UPSTREAM_TIMEOUT 68→60 (-8s) 和 KEY_COOLDOWN_S 38→34 (-4s)。

**验证结果**:
- ✅ 30min: 85/85 = 100%, 0 429, 0 ate, 0 fallback
- ✅ 1h: 167/167 = 100%, 0 errors
- ✅ 6h: 821/824 = 99.6% (3 errors均为NVCF服务端)
- ✅ Budget margin: 2×60=120, remaining=26s >> 10s threshold (vs R142的10s)
- ✅ Back-to-back rate: 0.0% (持续R142的好转趋势)

**注意**: 24h aggregate数据(502 avg=118.8s, 429 avg=172.9s)仍受R143之前(UT=68)的失败路径影响较大。R143的效果需要更多时间才能在24h窗口中充分体现。

### 参数评估表

| Parameter | Current | Adjustment? | Reason |
|-----------|---------|-------------|--------|
| UPSTREAM_TIMEOUT | 60 | ❌ 既不加也不减 | R143刚从68→60,30min/1h 100%验证中,需要更多数据 |
| TIER_TIMEOUT_BUDGET_S | 146 | ❌ | remaining=26s充足,0 ate in 30min |
| KEY_COOLDOWN_S | 34 | ❌ | 0 429s/30min,5/24h(R143前数据),需观察 |
| TIER_COOLDOWN_S | 42 | ❌ | 极少触发,无调整理由 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ❌ | 0 429s,利用率87.5%,有缓冲 |
| HM_CONNECT_RESERVE_S | 24 | ❌ | 6h仅1个budget_exhausted_after_connect |
| PROXY_TIMEOUT | 300 | ❌ | 无需调整 |

### 结论: 无变更
R143的两个变更刚刚部署,需要至少一个完整验证周期才能充分评估效果。当前所有7个参数均处于均衡状态。系统稳定,不建议在这个阶段做额外调整。

## 🔧 变更执行
无需变更 — 纯验证轮次

## 📈 预期效果
- R143的UT=60降低502路径耗时预期: 502 avg从118.8s下降(R143前为2×68=136s+overhead,现在2×60=120s+overhead)
- R143的KC=34降低429恢复开销预期: 429 avg从172.9s下降(更短cooldown→更快key恢复)
- Budget margin从10s扩大到26s → 更少all_tiers_exhausted

## ⚖️ 评判标准
- ✅ 更少报错: 30min/1h 0 errors, 6h仅3个(NVCF服务端)
- ✅ 更快请求: P50=18.4s, P95=32.4s, P99=60.9s
- ✅ 超低延迟: Avg=19.8s, DIRECT vs PROXY差异在NVCF方差范围内(pitfall #29)
- ✅ 稳定优先: 7参数均衡,无单点瓶颈
- ✅ 铁律: 只改HM1不改HM2

## ⏳ 轮到HM1优化HM2
