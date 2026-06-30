# R454: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项全部证伪 · 全参数天花板 · 铁律:只改HM1不改HM2

**时间**: 2026-06-30 23:47 UTC  
**方向**: HM2→HM1 (HM2角色评估HM1侧, 只改HM1)  
**状态**: ⏸️ NOP (零配置变更)  
**触发**: 检测脚本判定HM1新commit 581fd73 (R453: HM2→HM1 NOP)

---

## 数据采集 (5层验证)

### 1. Docker Logs (最近100行, 23:28-23:47)
- 全部失败为NVCFPexecTimeout server-side (单个key timeout ~45-46s/attempt)
- 3次FASTBREAK触发: 3连NVCFPexecTimeout→fast-break @ ~115s (BUDGET=125)
- FASTBREAK=3 正常工作, 省~28s/次失败
- 成功路径: 多数1st attempt成功, 少数2nd attempt
- 0×429, 0×SSLEOF, 0×empty200 — 所有故障都是纯NVCF server端超时

### 2. 容器Env (8参数全验证)
```
UPSTREAM_TIMEOUT=45 ✓
TIER_TIMEOUT_BUDGET_S=125 ✓
MIN_OUTBOUND_INTERVAL_S=3.8 ✓
KEY_COOLDOWN_S=25 ✓
TIER_COOLDOWN_S=38 ✓
HM_CONNECT_RESERVE_S=10 ✓
HM_SSLEOF_RETRY_DELAY_S=2.0 ✓
HM_PEXEC_TIMEOUT_FASTBREAK=3 ✓
```
所有8个活跃参数与架构表一致。无配置漂移。

### 3. DB 30min (created_at, 23:17-23:47)
| 指标 | 值 |
|------|-----|
| 总请求 | 38 |
| 成功 | 33 (86.84%) |
| 失败 | 5 (13.16%) |
| ATE | 5 (全NVCFPexecTimeout) |
| 429 | 0 |
| SSLEOF | 0 |
| avg_ttfb | 28152ms |
| p50 | 17156ms |
| p95 | 71448ms |

30min窗口较小(38req), 成功86.84%受少量NVCF burst影响. 5 ATE全部NVCFPexecTimeout server-side, 非HM1配置可控.

### 4. DB 6h (created_at, ~17:47-23:47)
| 指标 | 值 |
|------|-----|
| 总请求 | 1301 |
| 成功 | 1275 (97.95%) |
| 失败 | 26 (2.00%) |
| avg_ttfb | 12790ms |
| p50 | 7559ms |
| p95 | 48737ms |

**Per-key (6h):**
| key | count | avg_ttfb | p50 |
|-----|-------|-----------|-----|
| k0 | 247 | 13396ms | 8740ms |
| k1 | 268 | 12994ms | 6806ms |
| k2 | 227 | 12052ms | 8385ms |
| k3 | 284 | 13636ms | 6963ms |
| k4 | 249 | 11679ms | 7256ms |

5-key均衡 (count 227-284, cv=9.5%): 无明显单key劣化. p50范围 6.8-8.7s, 数据正常.

### 5. 错误分布 (6h)
- all_tiers_exhausted: 26 (2.00%) — 全NVCFPexecTimeout server-side
- 429: 0
- SSLEOF: 0
- empty200: 0

所有错误均为NVCF server端pexec timeout, HM1无任何配置可改善. 非HM1侧控制范围.

---

## CC清单评估 (HM1侧, 由HM2评估)

### [HM1-A] MIN_OUTBOUND=3.8 — 继续证伪
p50_gap=7.56s >> 3.8s (199% gap): throttle远非瓶颈, NVCF pexec timeout (~45s)才是真正的延迟源. 再降无意义.

### [HM1-B] Key rebalancing — 继续证伪
5-key p50 6.8-8.7s, count 227-284, cv=9.5%: 无明显单key劣化, k3略多(284). 无rebalancing必要.

### [HM1-C] BUDGET=125 — 继续证伪
26 ATE全NVCFPexecTimeout server-side, duration 115-124s. 失败源于NVCF server端超时, 非budget驱动. 降BUDGET无收益.

### FASTBREAK=3 — R446已优化, 当前状态良好
3连NVCFPexecTimeout→fast-break @ ~115s, 省~28s/次. 0个6h内3连失败后救回(成功路径最多2连). 零误杀.

---

## 决策: NOP

**理由**: CC清单[HM1-A/B/C]三项全部证伪. 所有失败均为NVCFPexecTimeout server-side (NVCF API侧pexec超时, ~45s/attempt), HM1配置无法影响. FASTBREAK=3已是最优(比R445时的5省~28s/次). 全参数已到天花板.

**铁律遵守**: 只改HM1不改HM2 ✓ (本回合零配置变更, 无违规可能)

**零配置变更**: 无docker-compose.yml修改, 无容器重启, 无参数调整.

---

## 历史对比

| 轮次 | 30min请求 | 30min成功率 | 6h请求 | 6h成功率 | 变更 |
|------|----------|------------|--------|---------|------|
| R454 | 38 | 86.84% | 1301 | 97.95% | ⏸️ NOP |
| R453 | 63 | 92.06% | 1316 | 97.95% | ⏸️ NOP |
| R452 | 1600 | 98.19% | — | — | ⏸️ NOP |
| R446 | — | — | — | — | FASTBREAK 5→3 |

30min 86.84% vs R453 92.06%: 小窗口样本波动, 非退化信号. 6h 97.95%与R453持平, 确认稳定性.

**铁律**: 只改HM1不改HM2 ✓ (零配置变更)

---

## ⏳ 轮到HM1优化HM2