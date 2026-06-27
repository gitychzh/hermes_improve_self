# R133: HM2 → HM1 — 无变更 (验证R132: BUDGET=146, 30min 65/65 ok(100%), 0 all_tiers_exhausted; 6h 5次均>R132部署前; 参数全均衡; 稳定优先)

## 📊 数据采集 (30min窗口 + 6h参考)

### Config快照 (R132生效后)
| Parameter | Value | 备注 |
|-----------|-------|------|
| UPSTREAM_TIMEOUT | 68 | R120 |
| TIER_TIMEOUT_BUDGET_S | 146 | R132: 144→146 |
| KEY_COOLDOWN_S | 38.0 | R108 |
| TIER_COOLDOWN_S | 42 | R115 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | R107 |
| HM_CONNECT_RESERVE_S | 24 | R111 |
| PROXY_TIMEOUT | 300 | — |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | — |

### 30min请求统计
| 指标 | 值 |
|------|-----|
| total | 65 |
| success | 65 (100%) |
| fail | 0 |
| avg | 19,441ms |
| p50 | 17,761ms |
| p90 | 27,318ms |
| p95 | 55,743ms |

### 30min错误
- **0** error_type events
- **0** all_tiers_exhausted
- **0** fallback
- **0** 429 (deepseek)

### 1h Tier Health
- deepseek_hm_nv: 1,293 ok, 5 fail (99.6%), avg=29,380ms
- 5 fail均发生在R132部署前(10:19-11:46 UTC)

### 6h all_tiers_exhausted
| count | avg_ms | min_ms | max_ms | 时间范围 |
|-------|--------|--------|--------|----------|
| 5 | 138,840 | 127,700 | 166,774 | 10:19-11:46 UTC |

**关键发现**: 所有5次all_tiers_exhausted均发生在R132部署前(最晚11:46 UTC)。R132的BUDGET=146生效后(约12:00+ UTC)，**0次all_tiers_exhausted**，持续>4.5h。

### 6h budget_exhausted_after_connect
- **0** events (24h视图有8次但均>6h前)

### 24h key errors (deepseek_hm_nv)
| 错误类型 | 总数 | 分布 |
|----------|------|------|
| NVCFPexecTimeout | 86 | k0=16, k1=22, k2=18, k3=15, k4=15 (均匀) |
| budget_exhausted_after_connect | 8 | k0=2(0.8s), k1=1(3.6s), k2=2(3.2s), k3=2(2.5s), k4=1(0.7s) |
| empty_200 | 23 | k0=8, k1=5, k2=4, k3=3, k4=3 |
| NVCFPexecRemoteDisconnected | 1 | k4 |

### 30min Per-key latency (deepseek, success only)
| Key | n | avg | p50 | p90 |
|-----|---|-----|-----|-----|
| K0 | 15 | 26,356ms | 19,333ms | 47,697ms |
| K1 | 12 | 21,907ms | 16,805ms | 55,354ms |
| K2 | 13 | 14,103ms | 15,586ms | 19,135ms |
| K3 | 14 | 17,758ms | 16,213ms | 23,155ms |
| K4 | 11 | 15,773ms | 17,527ms | 22,841ms |

### 请求速率
- ~2-3 req/min (稳定一致)
- MIN_OUTBOUND_INTERVAL_S=19.0×5keys=95s cycle → 容量远超需求

## 🎯 优化分析

### 参数评估表
| Parameter | Current | 需调整? | 理由 |
|-----------|---------|---------|------|
| UPSTREAM_TIMEOUT | 68 | ❌ | 30min 0 timeout; 24h timeout均匀↑无p95集中在边界附近 |
| TIER_TIMEOUT_BUDGET_S | 146 | ❌ | R132+后0 all_tiers_exhausted; 2×68=136→余量10s刚达阈值; 验证有效 |
| KEY_COOLDOWN_S | 38.0 | ❌ | 30min 0 429; 冷却充分 |
| TIER_COOLDOWN_S | 42 | ❌ | 与KEY=38差距4s(合理) |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ❌ | 实际~2-3/min vs 容量14/min=14%利用率; 0 429→无速率压力 |
| HM_CONNECT_RESERVE_S | 24 | ❌ | 6h 0 budget_exhausted_after_connect; 充分覆盖 |
| PROXY_TIMEOUT | 300 | ❌ | 无关联问题 |

### 结论
R132的BUDGET 144→146 (+2s) 解决了all_tiers_exhausted问题：
- **Before R132**: 6h内5次all_tiers_exhausted (2×68=136, BUDGET=144→8s余量<10s阈值→break)
- **After R132**: >4.5h内0次all_tiers_exhausted (2×68=136, BUDGET=146→10s余量=最少阈值, sufficient)
- 所有7参数均处于均衡状态
- 30min 100%成功率, 0错误, 0回退

**稳定性已达成 → 不追加变更, 遵循"稳定优先"评判标准**

## 🔧 变更执行

**无变更** — 验证R132效果, 所有参数均衡

## 📈 预期效果

| 指标 | R132前(6h) | R132后(4.5h+) | 预期(R133维持) |
|------|------------|---------------|----------------|
| all_tiers_exhausted | 5次 | 0次 | 0次 |
| 30min成功率 | 100% | 100% | 100% |
| 30min avg | ~23s | 19.4s | ~19-20s |
| 30min p50 | ~18s | 17.8s | ~17-18s |
| fallback | 0% | 0% | 0% |

## ⚖️ 评判标准

- ✅ 更少报错: 0 errors (30min), 0 all_tiers_exhausted (post-R132)
- ✅ 更快请求: avg=19.4s, p50=17.8s (良好)
- ✅ 超低延迟: p90=27.3s, p95=55.7s (K0/K1 p90偏高但属于NVCF侧长尾,非HM配置可控)
- ✅ 稳定优先: R132变更验证成功,参数全均衡→不追加
- ✅ 铁律: 只改HM1不改HM2 → 更无变更,铁律自然满足

## ⏳ 轮到HM1优化HM2
