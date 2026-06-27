# R134: HM2→HM1 — 无变更 (验证R133)

**日期**: 2026-06-28
**轮次**: R134 (HM2→HM1)
**决策**: 无变更
**铁律**: 只改HM1不改HM2

---

## 📊 数据采集

### Docker日志 (最近100行grep)
- 4× SSLEOFError (k3×3, k4×1), 均 SSL retry 后成功恢复
- 0× all_tiers_exhausted, 0× panic, 0× timeout budget break
- 请求正常通过, 多数 first attempt succeed

### Docker env (7参数确认)
| 参数 | 值 |
|---|---|
| UPSTREAM_TIMEOUT | 68 |
| TIER_TIMEOUT_BUDGET_S | 146 |
| KEY_COOLDOWN_S | 38.0 |
| TIER_COOLDOWN_S | 42 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 |
| HM_CONNECT_RESERVE_S | 24 |
| PROXY_TIMEOUT | 300 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 |

### Q1: 最近30分钟请求
| 指标 | 值 |
|---|---|
| 总请求 | 68 |
| 成功 | 68 (100%) |
| p50 | 18,317ms |
| p90 | 30,215ms |
| p95 | 43,326ms |
| 平均 | 19,592ms |
| fallback | 0 |
| errors | 0 |
| all_tiers_exhausted | 0 |

### Q2: Key错误24h (top 5)
| tier | key_idx | error_type | n | avg_elapsed_ms |
|---|---|---|---|---|
| glm5.1_hm_nv | 0 | 429_nv_rate_limit | 630 | - |
| glm5.1_hm_nv | 3 | 429_nv_rate_limit | 623 | - |
| glm5.1_hm_nv | 2 | 429_nv_rate_limit | 623 | - |
| glm5.1_hm_nv | 1 | 429_nv_rate_limit | 603 | - |
| glm5.1_hm_nv | 4 | 429_nv_rate_limit | 599 | - |

deepseek_hm_nv tier key errors (relevant to HM1 params):
| tier | key_idx | error_type | n | avg_elapsed_ms |
|---|---|---|---|---|
| deepseek_hm_nv | 1 | NVCFPexecTimeout | 22 | 28,791ms |
| deepseek_hm_nv | 2 | NVCFPexecTimeout | 18 | 15,119ms |
| deepseek_hm_nv | 0 | NVCFPexecTimeout | 16 | 16,070ms |
| deepseek_hm_nv | 3 | NVCFPexecTimeout | 15 | 30,258ms |
| deepseek_hm_nv | 4 | NVCFPexecTimeout | 15 | 14,869ms |
| deepseek_hm_nv | 0 | empty_200 | 8 | - |

### Q3: Tier健康1h
| tier_model | ok_1h | fail_1h | success_pct_1h | avg_duration_ms_1h |
|---|---|---|---|---|
| deepseek_hm_nv | 1,285 | 5 | 99.6% | 29,012ms |
| (None) | 0 | 21 | 0.0% | - |

### Q4: Per-minute请求率 (deepseek_hm_nv, 最近60min)
- 稳定 ~2-4 req/min
- 全部60分钟内0 errors
- 零错误窗口持续超过1小时

---

## 🔍 分析

### 稳定性指标
1. ✅ **100%成功率** (30min: 68/68)
2. ✅ **0 all_tiers_exhausted** (连续验证R133+R134)
3. ✅ **0 fallback** (30min窗口)
4. ✅ **P95=43,326ms** 远低于 BUDGET=146,000ms
5. ✅ **per-minute零错误** 连续60+分钟
6. ✅ **tier健康99.6%** (1h视图)
7. ✅ **SSL retry恢复正常** (k3/k4偶发, 均重试成功)

### 24h error背景
- deepseek_hm_nv NVCFPexecTimeout: 86次/24h (5 keys), avg 15-30s
- 这些均在上游68s超时内恢复(顺延至下一key), 不触及budget
- empty_200: 8次, 罕见
- 429_nv_rate_limit: 全部在glm5.1_hm_nv tier (不在本轮HM1 scope)

### 参数均衡评估
| 参数 | 当前值 | 状态 | 判断 |
|---|---|---|---|
| UPSTREAM_TIMEOUT | 68 | 24h timeout均在68s内 | 合理 |
| TIER_TIMEOUT_BUDGET_S | 146 | 2×68=136, 余量10s≥min threshold | 刚好满足 |
| KEY_COOLDOWN_S | 38.0 | 30min无429 on deepseek | 合理 |
| TIER_COOLDOWN_S | 42 | 无tier级冷却触发 | 合理 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | 请求率~2-4/min, 远低于限制 | 充裕 |
| HM_CONNECT_RESERVE_S | 24 | 无连接超时问题 | 合理 |
| PROXY_TIMEOUT | 300 | 无触及 | 合理 |

### 决策: 无变更
- **R133验证**: R133无变更→R134仍100%稳定, 参数组合持续有效
- **所有7参数均衡**: 无明确瓶颈, 无改善空间
- **少改多轮纪律**: 稳定时不追加变更
- **R132的BUDGET=146已稳定2轮**: 余量10s满足min threshold, 不再追加
- **连续2轮无变更验证**: 系统稳定, 优先不追加

---

## 📝 变更
- **无变更** — 所有7参数保持R133值

## ⏳ 轮到HM1优化HM2