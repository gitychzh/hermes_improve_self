# R131: HM2→HM1 — 无变更 (验证R129: TIER_TIMEOUT_BUDGET 144, 100%成功率, 0 all_tiers_exhausted)

**Role**: HM2 (opc2_uname) 优化 HM1 (opc_uname)
**Date**: 2026-06-27 23:55 CST
**Change**: 无变更 — 验证R129效果
**Principles**: 少改多轮(单参数); 铁律:只改HM1不改HM2; 更少报错更快请求超低延迟稳定优先

---

## 📊 数据采集 (Post-R130, 30-min Window 23:25–23:55 CST)

### HM1 Environment (current, no change from R129)
| Parameter | Value |
|----------|-------|
| TIER_TIMEOUT_BUDGET_S | **144** (R129) |
| KEY_COOLDOWN_S | **38.0** (R108) |
| TIER_COOLDOWN_S | **42** (R115) |
| UPSTREAM_TIMEOUT | **68** (R120) |
| MIN_OUTBOUND_INTERVAL_S | **19.0** (R107) |
| HM_CONNECT_RESERVE_S | **24** (R111) |
| PROXY_TIMEOUT | 300 |

### PostgreSQL 30-min Summary
| Metric | Value |
|--------|-------|
| Total requests | 61 |
| Success (200) | 61 (100.0%) |
| Failures | 0 (0.0%) |
| all_tiers_exhausted | **0** |
| Avg duration | 23,149ms |
| P50 | 18,425ms |
| P90 | 44,981ms |
| P95 | 60,655ms |
| Min | 3,043ms |
| Max | 128,118ms |

### 1h Analytics
| Metric | Value |
|--------|-------|
| Total | 136 |
| Success | 136 (100.0%) |
| Fail | 0 |
| Avg duration | 21,268ms |
| P50 | 18,557ms |
| P90 | 36,848ms |
| P95 | 51,199ms |

### Tier Health (v_hm_tier_health_1h)
| Tier | OK | Fail | Success% | Avg ms |
|------|-----|------|----------|--------|
| deepseek_hm_nv | 1308 | 5 | 99.6% | 29,411ms |

### Per-key Latency (30min, status=200)
| Key | Requests | Avg (ms) | Max (ms) | Min (ms) |
|-----|----------|-----------|----------|----------|
| k0 | 14 | 27,959 | 75,154 | 3,043 |
| k2 | 12 | 15,758 | 26,307 | 7,568 |
| k3 | 14 | 21,944 | 63,281 | 4,346 |
| k4 | 9 | 16,469 | 26,120 | 5,042 |
| k5 | 12 | 31,347 | 128,118 | 8,049 |

### Key Cycle 429s (30min): 0→60/61(98.4%), 1→1/61(1.6%)
### Fallback (30min): 0 configured, 0 triggered

---

## 🎯 优化分析

### R129效果验证: ✅ 完全成功

| Metric | R128 (Budget=142) | R129 (Budget=144) | 变化 |
|--------|-------------------|-------------------|------|
| all_tiers_exhausted / 30min | 21 | **0** | ✅ 100%消除 |
| 成功率 | 98.0% | **100.0%** | ✅ +2.0% |
| avg_ms | 29,831 | 23,149 | ✅ -22% |
| p95 | 67,859 | 60,655 | ✅ -11% |

所有7参数处于均衡, 30min零错误 → 无变更

---

## 🔧 变更执行

**无变更.** HM1 config保持R129状态.

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记
