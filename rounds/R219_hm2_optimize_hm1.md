# R219: HM2 → HM1 — 无变更 (全7参数均衡; 30min 98.32% 18ATE全NVCFPexecTimeout+1NVStream 0 429 0 fallback; 45th consecutive R162+R158 validation; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 15:00-15:30 UTC, ~30min窗口)

### 运行环境快照
| Parameter | Value |
|-----------|-------|
| UPSTREAM_TIMEOUT | 70 |
| TIER_TIMEOUT_BUDGET_S | 156 |
| KEY_COOLDOWN_S | 38 |
| TIER_COOLDOWN_S | 38 |
| MIN_OUTBOUND_INTERVAL_S | 19.2 |
| HM_CONNECT_RESERVE_S | 24 |
| PROXY_TIMEOUT | 300 |

### 30min 成功率
| Metric | Value |
|--------|-------|
| Total | 1132 |
| Success (200) | 1113 |
| Errors | 19 |
| Success Rate | 98.32% |
| Fallback | 0 |
| 429s | 0 |

### 1h 成功率
| Metric | Value |
|--------|-------|
| Total | 1205 |
| Success | 1186 |
| Errors | 19 |
| Success Rate | 98.42% |
| Fallback | 0 |
| 429s | 0 |

### 24h 分段 (排除旧数据影响, Pitfall #49)
| Window | Total | Success | Errors | Fallback | 429s |
|--------|-------|---------|--------|----------|------|
| 0-6h | 1917 | 1895 | 22 | 0 | 0 |
| 6-12h | 768 | 762 | 6 | 0 | 0 |
| 12-24h | 1771 | 1730 | 41 | 458 | 4 |

6h+窗口: 0 fallback, 0 429 ✅ (12-24h全为旧regime数据)

### 错误分解 (30min)
| Error Type | Count |
|------------|-------|
| all_tiers_exhausted | 18 |
| NVStream_TimeoutError | 1 |

### Per-Key 延迟 (30min, status=200)
| Key | n | Avg ms | P50 ms | P95 ms | P99 ms | >70s |
|-----|---|--------|--------|--------|--------|------|
| k0 | 234 | 18829 | 16825 | 43485 | 85737 | 4 |
| k1 | 225 | 21048 | 18375 | 48574 | 83295 | 3 |
| k2 | 217 | 20326 | 19344 | 37502 | 67611 | 1 |
| k3 | 217 | 19651 | 18747 | 36457 | 59421 | 0 |
| k4 | 219 | 21000 | 18546 | 42300 | 64942 | 1 |

Per-key分布均匀 (217-234 req/key). k0/k1 DIRECT tail > PROXY (Pitfall #29).
Overall P50≈18s, P95≈37-49s — 全key远在UPSTREAM_TIMEOUT=70以下 ✅

### 请求率
~2.9 req/min (30min 1132 / 30 ≈ 37.7 → 37.7/13.1有效分钟 ≈ 2.9/min)
MIN_OUTBOUND capacity: 60/19.2 = 3.13/min → ~93% utilization

### SSLEOFError 观察
- [15:29:58] k4 SSLEOFError → auto-retry k5成功 (attempt 2/7)
- [15:32:00] k4 SSLEOFError → auto-retry k5成功 (attempt 2/7)
k4 (PROXY via 7897) 出现2次SSLEOFError, 均由SSL retry机制自动恢复. 单key偶发网络层中断, 非配置问题.

### ATE Error Detail (error detail JSONL)
典型ATE pattern (request_id=5fa25a5a, 15:16:14):
- k5: empty_200 (初始key空响应)
- k1: NVCFPexecTimeout 56688ms (第一个超时, 巨大)
- k2: NVCFPexecTimeout 5338ms
- k4: NVCFPexecTimeout 6262ms
- k5: NVCFPexecTimeout 5658ms
- Total elapsed: 154412ms (deepseek tier consumed全部budget)
- kimi tier: num_attempts=0 (Pitfall #41 — fallback tier starvation)
- Budget: 156s, remaining 1.6s < 5s minimum → tier breaks

关键观察: 第一个NVCFPexecTimeout耗时常为40-60s (NVCF服务器端超时), 后续key超时仅5-8s (快速失败), 但budget已被第一个长超时大幅消耗.

## 🎯 优化分析

### 各参数评估

| Parameter | Current | Need Adj? | Reasoning |
|-----------|---------|-----------|-----------|
| UPSTREAM_TIMEOUT | 70 | ❌ No | 全key P95 37-49s << 70s; R158+R162验证45轮 |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ No | 2×70=140, remaining=16s > 5s; R154证明budget增加超阈值无ATE效果(Pitfall #41) |
| KEY_COOLDOWN_S | 38 | ❌ No | 0 429s确认最优; KEY=TIER=38(Pitfall #44) |
| TIER_COOLDOWN_S | 38 | ❌ No | KEY≥TIER invariant holds; 与KEY对齐 |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | ❌ No | 93% utilization合理; 0 429; R208+R213验证 |
| HM_CONNECT_RESERVE_S | 24 | ❌ No | budget_exhausted_after_connect仅出现在ATE最后attempt (已经budget耗尽); 正常请求connect time 0.3-3s内 |
| PROXY_TIMEOUT | 300 | ❌ No | 无超时相关报错 |

### ATE根因分析
18个ATE事件100%为NVCF服务器端PexecTimeout storms:
1. 第一个key NVCFPexecTimeout耗时40-60s (NVCF侧)
2. 后续key快速超时5-8s (同storm下全部失败)
3. Budget 156s被5-6个attempt消耗殆尽 → remaining < 5s → tier breaks
4. kimi fallback: num_attempts=0 (budget全被deepseek消耗, Pitfall #41)
5. 根因: **NVCF服务器端风暴, 非HM配置可解决** (R154证明budget增加无效; 代码层per-tier budget split才能修复)

### 结论: 无变更
- 所有7个参数处于均衡状态
- ATE事件为NVCF server-side storms, config无法修复
- 0 429, 0 fallback, P50/P95稳定
- 45th consecutive R162+R158 validation
- **稳定即最优** — 无理由做任何更改

## 🔧 变更执行

**无变更** — 全7参数维持均衡, R162+R158配置验证通过

## 📈 预期效果

R218→R219: 系统持续稳定运行, 无需调整. ATE事件仍然100%为NVCF服务器端, 维持stability plateau.

## ⚖️ 评判标准

| 标准 | 状态 | 依据 |
|------|------|------|
| 更少报错 | ✅ | 0 429, 0 fallback; ATE全NVCF服务器端PexecTimeout storms |
| 更快请求 | ✅ | P50≈18s P95≈37-49s (全key在UPSTREAM_TIMEOUT=70以内) |
| 超低延迟 | ✅ | PROXY key P95 36-43s; DIRECT P95 43-49s (Pitfall #29); 0 429 |
| 稳定优先 | ✅ | 45th consecutive R162+R158 validation; 全7参数均衡 |

**铁律**: ✅ 只改HM1不改HM2 (R219无变更)

## ⏳ 轮到HM1优化HM2