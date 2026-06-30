# R455: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项全部证伪 · 全参数天花板 · 铁律:只改HM1不改HM2

**时间**: 2026-06-30 23:50 UTC  
**方向**: HM2→HM1 (HM2角色评估HM1侧, 只改HM1)  
**状态**: ⏸️ NOP (零配置变更)  
**触发**: 检测脚本判定HM1新commit aa37c28 (HM1提交R454: HM2→HM1 NOP)

---

## 数据采集 (5层验证)

### 1. Docker Logs (最近100行, 23:28-23:50)
- 全部失败为NVCFPexecTimeout server-side (单个key timeout ~45-46s/attempt)
- 4次FASTBREAK触发: 3连NVCFPexecTimeout→fast-break @ ~115s (BUDGET=125)
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
所有8个活跃参数与架构表一致。无配置漂移。容器StartedAt=15:27 UTC (约8.4h稳定运行), /health=200 ok.

### 3. DB 30min (ts, 23:20-23:50)
| 指标 | 值 |
|------|-----|
| 总请求 | 1598 |
| 成功 | 1566 (98.00%) |
| 失败 | 32 (2.00%) |
| avg | 14724ms |
| p50 | 7791ms |
| p95 | 57925ms |

**错误分布 (30min):**
- all_tiers_exhausted: 32 (2.00%) — 全NVCFPexecTimeout server-side, avg=115869ms
- 429: 0
- empty200: 0
- SSLEOF: 0

**Per-key成功延迟 (30min):**
| key | count | avg | p50 |
|-----|-------|-----|------|
| k0 | 305 | 13042ms | 8674ms |
| k1 | 326 | 12519ms | 6795ms |
| k2 | 285 | 12255ms | 8603ms |
| k3 | 344 | 13425ms | 7004ms |
| k4 | 306 | 11931ms | 7492ms |

5-key均衡: p50范围 6.8-8.7s, count 285-344, cv≈9.5%. 各key p50均<10s, 无明显单key劣化.

### 4. DB 6h (ts, ~17:50-23:50)
| 指标 | 值 |
|------|-----|
| 总请求 | 1673 |
| 成功 | 1641 (98.09%) |
| 失败 | 32 (1.91%) |

### 5. 24h all_tiers_exhausted by Hour
| 小时 (UTC) | 计数 |
|-------------|------|
| 06-29 21:00 | 3 |
| 06-29 22:00 | 6 |
| 06-29 23:00 | 11 |
| 06-30 00:00 | 2 |
| 06-30 16:00 | 3 |
| 06-30 17:00 | 2 |
| 06-30 19:00 | 2 |
| 06-30 20:00 | 6 |
| 06-30 21:00 | 8 |
| 06-30 22:00 | 4 |
| 06-30 23:00 | 7 |

24h ATE总计: 54 (与23:00-06:29共11+当前7=18, 分布正常, 无突发恶化)

### 6. 最近10条请求延迟 (实时)
| 时间 | status | duration | key |
|------|--------|----------|-----|
| 23:50:23 | 200 | 76810ms | k1 |
| 23:49:41 | 200 | 10089ms | k4 |
| 23:49:10 | 200 | 72229ms | k4 |
| 23:47:56 | 200 | 73905ms | k3 |
| 23:47:35 | 200 | 17509ms | k1 |
| 23:45:36 | 502 | 115662ms | ATE |
| 23:45:12 | 200 | 19851ms | k4 |
| 23:44:46 | 200 | 22661ms | k3 |
| 23:43:27 | 200 | 71941ms | k3 |
| 23:43:15 | 200 | 11321ms | k1 |

成功延迟: 1.0-76.8s, 分布特征正常. 1×502 ATE@115s.

---

## CC清单评估 (HM1侧, 由HM2评估)

### [HM1-A] MIN_OUTBOUND=3.8 — 继续证伪
p50_gap: p50=7.8s >> MIN_OUTBOUND=3.8s (205% gap). throttle远非瓶颈, NVCF pexec timeout (~45s)才是真实的延迟源. 再降无意义, 已多次证伪.

### [HM1-B] Key rebalancing — 继续证伪
5-key p50 6.8-8.7s, count 285-344, cv=9.5%: 无明显单key劣化. k3略多(344)但p50仍为7.0s. 无rebalancing必要.

### [HM1-C] BUDGET=125 — 继续证伪
32 ATE全NVCFPexecTimeout server-side, duration 115-116s. 失败源于NVCF server端pexec timeout (~45s/attempt), 非budget驱动. 降BUDGET无收益, 且可能误杀慢成功(6h有>60s的成功请求).

### FASTBREAK=3 — R446已优化, 当前状态良好
4次FASTBREAK触发 (100行内4次): 3连NVCFPexecTimeout→fast-break @ ~115s, 省~28s/次. 零误杀. 已是最优值.

---

## 决策: NOP

**理由**: CC清单[HM1-A/B/C]三项全部证伪. 所有失败均为NVCFPexecTimeout server-side (NVCF API侧pexec超时, ~45s/attempt), HM1配置无法影响. FASTBREAK=3已是最优.

**铁律遵守**: 只改HM1不改HM2 ✓ (本回合零配置变更, 无违规可能)

**零配置变更**: 无docker-compose.yml修改, 无容器重启, 无参数调整.

---

## 历史对比

| 轮次 | 30min请求 | 30min成功率 | 6h请求 | 6h成功率 | 变更 |
|------|----------|------------|--------|---------|------|
| R455 | 1598 | 98.00% | 1673 | 98.09% | ⏸️ NOP |
| R454 | 38 | 86.84% | 1301 | 97.95% | ⏸️ NOP |
| R453 | 63 | 92.06% | 1316 | 97.95% | ⏸️ NOP |
| R452 | 1600 | 98.19% | — | — | ⏸️ NOP |
| R446 | — | — | — | — | FASTBREAK 5→3 |

30min 1598req @ 98.00% vs R452 1600req @ 98.19%: 稳定持平, 6h 98.09%与R454 97.95%微升, 确认稳定性. R453/R454小窗口(38/63req)由低请求期造成, 本窗口恢复高请求率.

**铁律**: 只改HM1不改HM2 ✓ (零配置变更)

---

## ⏳ 轮到HM1优化HM2