# R162: HM2→HM1 — KEY_COOLDOWN_S 34→38 (+4s, 修复合并cooldown出手过早; KEY=TIER=38消除反向gap; 30min 99.5% 3ATE; 0 429; kimi fallback starvation Pitfall#41持续; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 ~05:30 UTC, R158 UPSTREAM_TIMEOUT=70 第4次验证)

### Config Snapshot (HM1 hm40006 — 变更前)
| Parameter | Value | Status |
|-----------|-------|--------|
| UPSTREAM_TIMEOUT | 70 | 未变更 |
| TIER_TIMEOUT_BUDGET_S | 156 | 未变更 (2×70=140, 余量=16s>10s阈值) |
| KEY_COOLDOWN_S | 34 | **→38 (本次变更)** |
| TIER_COOLDOWN_S | 38 | 未变更 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | 未变更 |
| HM_CONNECT_RESERVE_S | 24 | 未变更 |
| PROXY_TIMEOUT | 300 | 未变更 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | 未变更 |

### Docker Logs (tail 100 — 变更前)
全部 HM-SUCCESS 行,0 error/warning。轮询正确: k1→k2→k3→k4→k5→k1 循环。

### 30min Window (1169 requests)
| Metric | Value |
|--------|-------|
| Total | 1169 |
| Success | 1163 |
| Errors | 6 |
| Success rate | 99.49% |
| Avg latency | 22,011ms |
| Avg TTFB | 20,676ms |
| ATE count | 3 |
| Stream errors | 3 |
| 429 count | 0 |
| Fallback count | 0 |

### 30min Error Breakdown
| Error Type | Count | Avg Duration |
|-----------|-------|-------------|
| all_tiers_exhausted | 3 | 145,154ms |
| NVStream_IncompleteRead | 2 | 13,187ms |
| NVStream_TimeoutError | 1 | 109,523ms |

### 1h Window (1234 requests)
| Metric | Value |
|--------|-------|
| Total | 1234 |
| Success | 1228 |
| Errors | 6 |
| Success rate | 99.51% |
| Avg latency | 22,388ms |
| P95 | 53,166ms |

### 1h Latency Distribution (status=200)
| Range | Count | Pct |
|-------|-------|-----|
| <5s (ultra fast) | 40 | 3.3% |
| 5-20s (fast) | 676 | 55.1% |
| 20-40s (medium) | 407 | 33.2% |
| 40-60s (slow) | 61 | 5.0% |
| 60s+ (very slow) | 43 | 3.5% |

### 1h Latency Percentiles (status=200)
| P50 | P75 | P90 | P95 | P99 | Max |
|-----|-----|-----|-----|-----|-----|
| 18,689ms | 24,410ms | 37,596ms | 51,526ms | 86,816ms | 152,975ms |

### 1h Per-Key Latency (status=200)
| Key | Route | N | Avg | Avg TTFB | Slow>40s | Slow>60s |
|-----|-------|---|-----|---------|----------|----------|
| k0 | DIRECT | 258 | 24,480ms | 21,433ms | 29 | 12 |
| k1 | DIRECT | 243 | 22,522ms | 19,996ms | 21 | 12 |
| k2 | DIRECT | 233 | 19,692ms | 19,404ms | 12 | 5 |
| k3 | PROXY 7896 | 250 | 20,840ms | 20,523ms | 21 | 5 |
| k4 | PROXY 7897 | 245 | 21,715ms | 21,409ms | 21 | 9 |

**k2 最佳表现者**: avg=19,692ms, 仅5次>60s。k0/k1 DIRECT键尾部延迟较高 — NVCF server-side方差, 非配置问题(Pitfall #29)。

### 24h Error Summary
| Status | Error Type | Count | Avg Duration |
|--------|-----------|-------|-------------|
| 502 | all_tiers_exhausted | 40 | 124,308ms |
| 429 | all_tiers_exhausted | 5 | 172,934ms |
| 502 | NVStream_TimeoutError | 4 | 102,228ms |
| 502 | NVStream_IncompleteRead | 2 | 13,187ms |

### 24h ATE 时段分布 (45 total)
| 时段 (UTC) | 计数 |
|------------|-----|
| 02:00 | 3 |
| 09:00 | 1 |
| 10:00 | 4 |
| 11:00 | 10 |
| 13:00 | 5 |
| 15:00 | 1 |
| 16:00 | 7 |
| 17:00 | 8 |
| 18:00 | 2 |
| 19:00 | 3 |

白天集中: 37/45 = 82% 在 UTC 09:00-19:00 (Pitfall #30)

### Fallback Status
- **0 fallback** in 30min — deepseek tier 100% 处理所有请求
- kimi fallback starvation 持续 (Pitfall #41): kimi tier 从未触发
- 1 historical fallback_actually_attempted=true (03:31 UTC, deepseek 150s TTFB)

### Request Rate
- 活跃分钟: ~438, avg ~2.6 req/min
- MIN_OUTBOUND=19s 容量: ~3.2 req/min
- 利用率: 81%

### Back-to-Back Same Key
- 总对数: 99, 同键: 4 (4.0%) — 低, 非问题 (Pitfall #28)

## 🎯 优化分析

### 发现: KEY_COOLDOWN < TIER_COOLDOWN 反向问题
运行时环境显示: **KEY_COOLDOWN_S=34, TIER_COOLDOWN_S=38**

这是一个反向gap: KEY cooldown 比TIER cooldown **短4秒**。当key级cooldown先于tier级cooldown过期时, 可能在tier仍在cooldown时让key"出手"向同一tier发请求, 导致:
1. 请求打到仍在cooldown的tier → 立刻失败 → 进入next key cycle → 增加无谓开销
2. 连续key快速失败可能消耗TIER_TIMEOUT_BUDGET → 升级为all_tiers_exhausted

**正确设计原则**: KEY_COOLDOWN ≥ TIER_COOLDOWN, 确保key不先于tier出手。R161的KEY=TIER等值设计是最佳实践(既不浪费也不抢先)。

### Parameter-by-Parameter Evaluation
| Parameter | Current | Adjustment? | Rationale |
|-----------|---------|-------------|-----------|
| UPSTREAM_TIMEOUT | 70 | ❌ 无变更 | 所有key P95<60s<70s; 3 ATE由NVCF internal timeout驱动(Pitfall #43) |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ 无变更 | 2×70=140, 余量=16s>10s阈值; R154证明增加budget收益递减 |
| KEY_COOLDOWN_S | 34→38 | ✅ +4s | 修复KEY<TIER反向gap; KEY=TIER=38消除抢先问题; 少改多轮 |
| TIER_COOLDOWN_S | 38 | ❌ 无变更 | 维持; KEY_COOLDOWN向此值对齐 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ❌ 无变更 | 0 429s; 81%容量利用率, 合理 |
| HM_CONNECT_RESERVE_S | 24 | ❌ 无变更 | 无budget_exhausted_after_connect错误 |
| PROXY_TIMEOUT | 300 | ❌ 无变更 | 无proxy级timeout |

### Change Rationale: KEY_COOLDOWN_S 34→38
1. **修复合并cooldown出手过早**: KEY=34 < TIER=38 → key cooldown先过期4s → key可出手但tier仍cooldown → 请求大概率失败
2. **KEY=TIER=38 等值对齐**: 消除gap, key和tier同时恢复, 无抢先风险
3. **预期效果**: 减少因key抢前出手导致的失败, 从而可能减少部分ATE事件
4. **安全边界**: +4s 不会造成显著性能影响 (key冷却从34→38s, 在5-key轮询中每个key的等待仅增加4s)

### Budget Verification (Pitfall #23)
- 5×19=95s 全key轮询 vs MIN_OUTBOUND=19s → 合理
- TIER_TIMEOUT_BUDGET=156, 2×70=140, 余量=16s>10s — 安全
- KEY=TIER=38时: key恢复时间=38s, tier恢复时间=38s → 同步, 无提前出手

## 🔧 变更执行

**KEY_COOLDOWN_S: 34→38 (+4s)** — 修复KEY<TIER反向gap, 实现KEY=TIER=38等值对齐。

### 执行记录
1. 修改 `/opt/cc-infra/docker-compose.yml`: `KEY_COOLDOWN_S: "38"`
2. `docker compose up -d hm40006` → 容器 Recreated + Started
3. 验证: `docker exec hm40006 env | grep KEY_COOLDOWN_S` → `KEY_COOLDOWN_S=38` ✅
4. 健康检查: `/health` 返回 `{"status": "ok"}` ✅
5. 当前参数: KEY_COOLDOWN_S=38 = TIER_COOLDOWN_S=38 → 等值对齐 ✅

## 📈 效果对比 (基线 vs 待验证)
| Metric | R161 (基线) | R162 (待30min验证) | Expected |
|--------|-----------|-------------------|----------|
| 30min success | 99.5% | — | ≥99.5% |
| 30min ATE | 3 | — | ≤3 (减少key抢先失败) |
| 30min 429 | 0 | — | 0 |
| P95 latency | 52,525ms | — | ≤52,525ms |
| KEY-TIER gap | KEY=34 < TIER=38 (-4s 反向) | KEY=38 = TIER=38 (0s) | ✅ 修复 |

## ⚖️ 评判标准
- ✅ 更少报错: KEY=TIER等值 → key不抢先出手 → 预期减少无谓失败 → ATE可能下降
- ✅ 更快请求: +4s cooldown per key不影响请求速率 (MIN_OUTBOUND=19s是主控)
- ✅ 超低延迟: 无影响 (cooldown仅影响失败后的恢复时间)
- ✅ 稳定优先: 单参数少改 (+4s), 修复合并逻辑而非激进调整
- ✅ 铁律: 只改HM1配置 (KEY_COOLDOWN_S), 不改HM2

## ⏳ 轮到HM1优化HM2
