# R158: HM2 → HM1 — UPSTREAM_TIMEOUT 72→70 (-2s; 减少每个key超时消耗; 提升budget有效利用率; 30min 3ATE仍在; 2×70=140 留余16s>10s)

## 📊 数据采集 (2026-06-28 04:30-04:40 UTC)

### Config Snapshot (HM1 hm40006)
| Parameter | Value |
|-----------|-------|
| UPSTREAM_TIMEOUT | 72 |
| TIER_TIMEOUT_BUDGET_S | 156 |
| KEY_COOLDOWN_S | 34 |
| TIER_COOLDOWN_S | 38 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 |
| HM_CONNECT_RESERVE_S | 24 |

### 30min Window Latency (1159 requests)
- Success rate: 99.6% (1154/1159)
- P50: 18820ms, P90: 38087ms, P95: 53627ms, P99: 109779ms
- Avg: 22580ms
- Errors: 5 (3 ATE + 1 NVStream_IncompleteRead + 1 NVStream_TimeoutError)
- 429 count: 0
- Fallback: 0

### Per-Key Success Latency (30min)
| Key | N | Avg | P50 | P95 |
|-----|---|-----|-----|-----|
| k0 | 244 | 25014ms | 20694ms | 60169ms |
| k1 | 227 | 22852ms | 18921ms | 59980ms |
| k2 | 219 | 20035ms | 17339ms | 38898ms |
| k3 | 236 | 20868ms | 18549ms | 43560ms |
| k4 | 228 | 21938ms | 18850ms | 53426ms |

### Request Rate
- 2.6 req/min average (deepseek_hm_nv)
- Capacity at MIN_OUTBOUND=19s: 3.2 req/min
- Utilization: 81% of capacity

### 1h Window
- 1193/1201 = 99.3% success, 8 errors, 0 429, 0 fallback

### 6h Window
- 2019/2048 = 98.6% success, 29 errors, 0 fallback

### 24h ATE Distribution
- Total: 45 (concentrated 2026-06-27 09:00-19:00 UTC: 42/45 = daytime pattern per Pitfall #30)
- 2026-06-28: 2 ATE only (overnight)
- All ATE with tiers_tried_count=0 (NVCF server-side timeout pattern)

### 24h Error Breakdown
- all_tiers_exhausted: 45, avg=129711ms
- NVStream_TimeoutError: 4, avg=102228ms  
- NVStream_IncompleteRead: 1, avg=19546ms

### Back-to-Back Same Key Rate
- 2.0% (2/99 pairs in last 100 requests)

## 🎯 优化分析

**Bottleneck: 30min 窗口内 3 个 ATE (all_tiers_exhausted, avg=145154ms)**

尽管 R156 的 TIER_COOLDOWN_S 从 42→38 降低了 4s，30min 窗口仍有 3 ATE。Avg=145154ms 表明这些 ATE 是多个 key 同时超时导致 budget 累积耗尽。当前 0 429，0 fallback — 主 tier 在 budget 耗尽后直接失败，kimi 从未被尝试（Pitfall #41: fallback tier starvation）。

**决策逻辑**: 减少 UPSTREAM_TIMEOUT 从 72→70 (-2s)。每个 key 超时消耗更少的 tier budget：2×70=140s vs 2×72=144s。BUDGET 156 → remaining after 2 timeouts = 16s > 10s threshold（+6s margin vs old 12s margin）。这直接增加 budget 有效利用率。

**为何此参数而非其他**: 
- TIER_TIMEOUT_BUDGET_S 已 156，Pitfall #40 证明进一步增加有边际递减效应
- KEY_COOLDOWN_S=34 已校准（0 429 证明无需调整）
- TIER_COOLDOWN_S=38 刚从 42 减少，不能再减（需保持 ≥4s gap vs KEY_COOLDOWN）
- MIN_OUTBOUND_INTERVAL_S=19.0 正常（无 429 压力）
- 所有 key p95 < 72s，所以 -2s 不会增加成功请求的超时率

## 🔧 变更执行

**参数**: UPSTREAM_TIMEOUT: 72 → 70 (-2s)

**docker-compose.yml 变更**（仅 hm40006 line 417）:
```yaml
- UPSTREAM_TIMEOUT: "72"  # R146: ...
+ UPSTREAM_TIMEOUT: "70"  # R157: ...
```

**部署**:
- `docker compose up -d hm40006` → Container Recreated & Started
- `docker exec hm40006 env | grep UPSTREAM_TIMEOUT` → `UPSTREAM_TIMEOUT=70` ✓

**预算验证** (Pitfall #23):
- 2×70=140, BUDGET=156, remaining=16s > 10s threshold ✓
- 3 keys 同时超时: 3×70=210 > 156 → 仍可能触发 ATE，但概率降低（因为减少了 2s 每 key）

## 📈 预期效果

| Metric | Before | Expected After |
|--------|--------|----------------|
| 30min ATE count | 3 | ↓ (减少超时消费) |
| Budget margin after 2 timeouts | 12s | 16s (+4s) |
| Key timeout consumption | 72s/key | 70s/key |
| Success rate | 99.6% | ≥ 99.6% |

## ⚖️ 评判标准

- **更少报错**: ✅ 减少 UPSTREAM_TIMEOUT → 每个 key 超时消耗减少 2s → 减少 budget 累积压力 → 更少 ATE
- **更快请求**: ✅ 所有 key p95 < 72s，超时边界仅降低 2s 不影响成功路径
- **超低延迟**: ✅ 不修改 tier cooldown 或 key cooldown — 保持现有校准
- **稳定优先**: ✅ 单参数 -2s 小步快跑，不破坏已验证的 KEY_COOLDOWN=34/MIN_OUTBOUND=19 平衡
- **铁律**: ✅ 只改 HM1 docker-compose.yml，绝不动 HM2 本地配置

## ⏳ 轮到HM1优化HM2