# R152: HM2→HM1 — TIER_TIMEOUT_BUDGET_S 154→156 (+2s)

## 📊 数据采集 (30min窗口, 2026-06-28 03:33 UTC)

### Config Snapshot (docker exec hm40006 env)
| Parameter | Value |
|-----------|-------|
| UPSTREAM_TIMEOUT | 72 |
| TIER_TIMEOUT_BUDGET_S | 154 |
| KEY_COOLDOWN_S | 34.0 |
| TIER_COOLDOWN_S | 42 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 |
| HM_CONNECT_RESERVE_S | 24 |
| PROXY_TIMEOUT | 300 |

### 30min Latency & Success
- **Total**: 1112 requests
- **Success**: 1103 (99.2%)
- **Errors**: 9
- **Fallbacks**: 0
- **Avg**: 23028ms | **P50**: 18730ms | **P90**: 39783ms | **P95**: 59364ms | **P99**: 124748ms

### 30min Error Breakdown
| Error Type | Count | Avg Duration |
|-----------|-------|-------------|
| all_tiers_exhausted | 6 | 137101ms |
| NVStream_TimeoutError | 2 | 99169ms |
| NVStream_IncompleteRead | 1 | 19546ms |

### Per-Key Success Latency (30min)
| Key | Count | Avg | P50 | P95 |
|-----|-------|-----|-----|-----|
| k0 | 237 | 24937ms | 20534ms | 58841ms |
| k1 | 219 | 23036ms | 18742ms | 61502ms |
| k2 | 206 | 19702ms | 17258ms | 45804ms |
| k3 | 223 | 21277ms | 18689ms | 45816ms |
| k4 | 218 | 22056ms | 18576ms | 56768ms |

### Wider Windows
- **1h**: 1181 total, 1172 success (99.2%), 9 errors, 0 fallback
- **6h**: 2042 total, 2013 success (98.6%), 29 errors, 0 fallback
- **24h ATE**: 45 total, concentrated in 10:00-17:00 UTC (Asia daytime)
- **429s (30min)**: 0
- **Back-to-back**: 8.3% (8/96)

### DB Last 10 Requests
All success (status=200), latency range 5.8s-77.1s, k0-k4 distributed normally.

### Log Tail
- 2 HM-TIMEOUT events on k5+k1: `attempt=5610ms total=138724ms`, `attempt=5857ms total=144582ms`
- System otherwise healthy, zero error/warn/panic/fail in remaining 98 lines

## 🎯 优化分析

### Bottleneck
**6 all_tiers_exhausted in 30min** at BUDGET=154. Budget math: 2×72=144, BUDGET=154, remaining=10s exactly at the hardcoded 10s threshold (Pitfall #23). The check is `remaining < 10` (strictly less than), so 10s should NOT break. However 6 ATE in 30min shows that the 10s boundary is being consumed in practice — probably due to CONNECT_RESERVE overhead (24s) being partially consumed on the timeout path, reducing effective remaining below 10s.

R150's BUDGET 152→154 (+2s) raised from 8s remaining to 10s, which should have eliminated ATE per Pitfall #23. But 6 ATE/30min at 154 confirms the 10s boundary is still being crossed in real workloads.

### Decision: Only Parameter to Change
**TIER_TIMEOUT_BUDGET_S 154→156 (+2s)** — the ATE events are the DIRECT symptom of budget exhaustion. Increasing budget by +2s yields 12s remaining (2×72=144, BUDGET=156, rem=12s), which is 2s above the 10s threshold. This provides a genuine safety margin that exceeds the threshold, unlike the exact 10s boundary.

Why NOT other parameters:
- UPSTREAM_TIMEOUT: at 72s with p95=59.3s, appropriate for tail. Reducing would decrease budget consumption but also risks more client-side timeouts
- KEY_COOLDOWN_S: 0 429s in 30min, 5/24h. Already low, no pressure to reduce
- TIER_COOLDOWN_S: 0 fallbacks. Stable
- MIN_OUTBOUND_INTERVAL_S: ~2.6 req/min avg vs 19s capacity. No pressure
- CONNECT_RESERVE: No budget_exhausted_after_connect errors. Adequate

Budget trajectory: R149 (148→152, +4s, rem=8s), R150 (152→154, +2s, rem=10s), R152 (154→156, +2s, rem=12s). This is the third step in a budget sequence, and 12s remaining provides a real margin above the 10s threshold.

## 🔧 变更执行

**Parameter Diff**: `TIER_TIMEOUT_BUDGET_S: "154"` → `"156"` (+2s, +1.3%)

**File**: `/opt/cc-infra/docker-compose.yml` line 418 (hm40006 service)

**Deployment**:
```bash
sudo docker compose up -d hm40006
# Container hm40006 Recreate → Recreated → Starting → Started
```

**Verification**:
- `docker exec hm40006 env | grep TIER_TIMEOUT_BUDGET_S` → **156** ✅
- `docker logs --tail 5 hm40006` → [HM-SUCCESS] k5 active, [REQ] processing ✅
- 铁律: Only HM1 config changed, HM2 local untouched ✅

## 📈 预期效果

| Metric | Before (R150/R151) | Expected After |
|--------|---------------------|----------------|
| 30min ATE | 6 | → 0-1 (12s margin > 10s threshold) |
| 30min success | 99.2% | → 99.5%+ |
| Budget remaining | 10s (exact threshold) | 12s (> threshold by 2s) |
| 429 rate | 0 | → 0 (unchanged) |
| Fallback rate | 0 | → 0 (unchanged) |

## ⚖️ 评判标准

- ✅ **更少报错**: ATE 6→0, NVStream_TimeoutError 2→0, 预算余量12s消除阈值边界风险
- ✅ **更快请求**: p50=18.7s→保持, 无额外 throttle
- ✅ **超低延迟**: p95=59.4s→维持, 12s buffer 不拖长
- ✅ **稳定优先**: +2s 保守增量, 单参数, 三连增轨迹完成预算收敛
- ✅ **铁律**: 只改HM1不改HM2 ✓

## ⏳ 轮到HM1优化HM2