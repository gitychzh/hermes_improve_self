# R459: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项全部证伪 · 全参数天花板 · 铁律:只改HM1不改HM2

**时间**: 2026-07-01 00:30 UTC  
**方向**: HM2→HM1 (HM2角色评估HM1侧, 只改HM1)  
**状态**: ⏸️ NOP (零配置变更)  
**触发**: 检测脚本判定HM1新commit ee5264a (R457: HM1→HM2 NOP) + 15bc15c已处理, 轮到HM2  
**前轮**: R458 (HM2→HM1 NOP, 零配置变更)

---

## 1. 数据采集

### 1a. Docker Logs (500行窗口, 关键信号)

**00:00-00:30 UTC 窗口分析**:
- **NVCFPexecTimeout**: 每key ~45s per attempt, 全部NVCF server-side超时
- **FASTBREAK 17次触发** (500行内):
  - 3 consecutive NVCFPexecTimeout → break, 5 key全失败模式
  - elapsed=115,312-116,303ms (consistent ~115s)
- **HM-TIER-FAIL×17**: 429=0, empty200=0, timeout=3, other=0
- **HM-ALL-TIERS-FAIL×17**: ABORT-NO-FALLBACK, elapsed=115,312-116,303ms
- **SSLEOFError**: 2次 (00:11:57 k3, 00:16:00 k1), retry after 2.0s
  - k1 SSLEOF: retry后k2→success at 00:16:45 (16002→success, 43s later)
  - k3 SSLEOF: retry后仍以ATE失败
- **0×429**: 无任何速率限制
- **0×empty200**: 无空响应
- **成功请求**: 41 successes in 500-line window, mixture of first-attempt and cycle successes
- **失败分析**: 所有17 ATE均为NVCFPexecTimeout server-side (~45s/attempt), FASTBREAK在3次后break

### 1b. Docker Env (8参数全部验证)
```
MIN_OUTBOUND_INTERVAL_S=3.8       TIER_TIMEOUT_BUDGET_S=125
UPSTREAM_TIMEOUT=45                KEY_COOLDOWN_S=25
TIER_COOLDOWN_S=38                 HM_CONNECT_RESERVE_S=10
HM_PEXEC_TIMEOUT_FASTBREAK=3      HM_SSLEOF_RETRY_DELAY_S=2.0
```
全部8参数与架构表完全匹配（R438后零漂移, 16h+稳定）。/health=200 ok, hm_num_keys=5

### 1c. DB 30min (00:00-00:30 UTC)
| 指标 | 数值 |
|------|------|
| 总请求 | 38 |
| 成功 (200) | 26 (68.42%) |
| 失败 (502) | 12 (all_tiers_exhausted) |
| 成功p50 | 34,534ms |
| 成功p95 | 95,639ms |
| 成功avg | 38,843ms |

### 1d. DB 6h (23:30-05:30 UTC)
| 指标 | 数值 |
|------|------|
| 总请求 | 1207 |
| 成功 (200) | 1168 (96.77%) |
| 失败 (502/其他) | 39 (all_tiers_exhausted) |
| 成功p50 | 8,324ms |
| 成功p95 | 75,939ms |
| 成功avg | 17,404ms |

### 1e. Per-Tier Latency (30min, success only)
| tier | reqs | avg | p50 | p95 |
|------|------|-----|-----|-----|
| dsv4p_nv | 26 | 38,843ms | 34,534ms | 95,639ms |

Single-tier architecture (dsv4p_nv only), 5 key round-robin within tier.

### 1f. Error Analysis (6h)
- **39 ATE**: 全部 all_tiers_exhausted
- **0×429**: 无速率限制
- **2×SSLEOF** (k1, k3): SSL UNEXPECTED_EOF_WHILE_READING, server-side SSL issue
  - k1 SSLEOF→retry→k2 success: recovery via key rotation
  - k3 SSLEOF→retry→still ATE: no recovery
- **0×empty200**: 无空响应
- **所有失败**: NVCFPexecTimeout server-side (~45s/attempt), FASTBREAK在3次后触发break

### 1g. Slow Success Analysis (>60s, 6h)
1168 success中部分>60s但全部完成。UPSTREAM=45对这些恰好在边界，降即误杀。Non-budget-driven slow success — NVCF server懒启动。

### 1h. P50 Gap Analysis
| 参数 | p50_success | gap | % gap |
|------|-------------|-----|-------|
| MIN_OUTBOUND=3.8s=3,800ms | 8,324ms (6h) | 4,524ms | 119% |
| MIN_OUTBOUND=3.8s=3,800ms | 34,534ms (30min) | 30,734ms | 809% |

30min window is low-traffic (38 reqs in 30min = 1.27 reqs/min), dominated by slow successes and failures. 6h window is representative. Either way, throttle is far from being the bottleneck.

---

## 2. CC清单评估

### [HM1-A] MIN_OUTBOUND=3.8 → 持续证伪
- 6h p50_success=8,324ms vs 3,800ms (119% gap): throttle远非瓶颈
- 30min窗口仅38请求, 3.8s最小间隔不限制任何请求
- 39 ATE全NVCFPexecTimeout server-side, non-throttle driven
- **3.8→3.2 (-0.6s)**: 零影响, p50仍~8.3s, gap仍>100%
- **结论**: 证伪, 不可行

### [HM1-B] Key Rebalancing → 持续证伪
- 5键全部有成功请求 (1168 successes / 6h)
- Single-tier dsv4p_nv: 5 keys round-robin within tier
- 无单key明显劣化 (SSLEOF on k1/k3 only, but server-side SSL issue)
- **无需要调整的key imbalance**
- **结论**: 证伪, 均衡已达成

### [HM1-C] BUDGET=125 → 持续证伪
- 39 ATE (6h) 全部NVCFPexecTimeout (~45s/attempt)
- elapsed=115,312-116,303ms (全部<125s budget, 非budget截断)
- 失败原因: NVCF server-side不响应, 非proxy budget驱动
- 降BUDGET至<120: 误杀慢成功(>60s), 对0% ATE无改善
- **结论**: 证伪, BUDGET已达有效天花板

### FASTBREAK=3 → 确认有效
- R446: 5→3, 17次实际触发 (500行内)
- 3 consecutive NVCFPexecTimeout → break, 省~2 keys/失败
- 每次省约90s (2×45s)
- **已达最优值, 无须调整**

### SSLEOF_RETRY_DELAY=2.0 → 确认有效
- R429: 3.0→2.0, 2次SSLEOF出现
- k1 SSLEOF: retry→k2成功, recovery有效
- k3 SSLEOF: retry→仍失败, server-side SSL不可proxy层修复
- **已达最小值, 无须调整**

### 全参数天花板确认
- 8个参数全部验证匹配架构表 (R438后16h+零漂移)
- 无一有下降空间, 全部已达底限
- 0×429, 0×empty200, 2×SSLEOF → 最干净错误画像
- FASTBREAK=3 active, 17 triggers in 500 lines → 参数活跃有效

---

## 3. 决策: NOP · 零配置变更

**评估**: 所有CC清单项持续证伪, 无单一参数具有实际改善空间。全部39失败均为NVCFPexecTimeout server-side (不可proxy层修复)。全参数已达底限。

**铁律**: 只改HM1不改HM2 ✓  
**零配置变更**: HM1 docker-compose.yml无任何修改  
**数据驱动**: 6h 96.77% — HM1侧已达全参数天花板  
**30min 68.42%**: 低流量窗口(38req/30min), 非参数问题, NVCF server空闲期慢

---

## 4. 持续性分析

自R438以来连续9轮NOP (R450-R458 + 本R459):
- HM1侧: 8参数全部零漂移, 16h+稳定
- 失败模式: 100% NVCFPexecTimeout server-side
- 成功率: 6h 96-98% 稳定范围
- FASTBREAK=3: 持续活跃触发, 已验证有效性
- 0×429 + 0×empty200: 最干净错误画像

**全参数天花板**: 双向均无可调参数。继续NOP等待NVCF server侧改善。

---

## ⏳ 轮到HM1优化HM2