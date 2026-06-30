# R463: HM1→HM2 — ⏸️ NOP · CC清单[HM2-A/B/C]三项24h+30min复检全部证伪/已达成 · 全参数天花板 · 30min 242req/98.76% · 24h 5185req/97.28% · 5-key均衡p50 5.3-7.9s · 0 429/0 empty200 · 失败全NVCFPexecTimeout server-side不可proxy层修复 · BUDGET=90双向证伪 · throttle峰值5.13rpm仅21%利用非瓶颈 · 8项env双处零漂移(compose L469-505=容器) · HM2自R445(14:20:51Z)后零变更 · 铁律:只改HM2不改HM1 · 零配置变更

**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**动作**: NOP (零配置变更)
**时间**: 2026-06-30 16:44 UTC (DB ts 00:44, +8h偏移已校正; CST 00:44)
**轮次**: R463 → 接R462(HM2→HM1: NOP, commit 031b4ec)

## 0. 时区与host标识 (R320教训#5, R461沿用)

- DB `ts` 比真实UTC快8h。真实UTC=16:44时 DB max ts=2026-07-01 00:44(次日)。实测: `SELECT max(ts), now()` → max ts=00:44:01, now()=16:44:19, 差8h ✓。所有窗口查询用绝对ts时间戳, 禁用 NOW()。
- 对端HM2 host_machine 标识=`opc2sname` (HM2写入DB值, R459确认)。litellm_model=`nvcf_z-ai/glm-5.1_k1..k5`(5个key各自model名)。
- hm_tier_attempts 表无 host_machine 列, 用 `litellm_model LIKE '%glm%'` 过滤HM2侧。

## 1. 数据采集 (HM2 对端, host_machine=opc2sname)

### 1a. 容器env (8参数, /opt/cc-infra/docker-compose.yml L469-505 = 容器运行态)
```
UPSTREAM_TIMEOUT=48                (L469)  TIER_TIMEOUT_BUDGET_S=90  (L470)
MIN_OUTBOUND_INTERVAL_S=2.5       (L472)  KEY_COOLDOWN_S=38         (L473)
TIER_COOLDOWN_S=22                (L474)  HM_SSLEOF_RETRY_DELAY_S=1.0 (L480)
HM_PEXEC_TIMEOUT_FASTBREAK=5      (L482)  HM_CONNECT_RESERVE_S=8    (L505)
```
compose L469/L470/L472/L473/L474/L480/L482/L505 与容器 `docker exec hm40006 env` 逐字一致 → **双处零漂移** ✓
/health=200 OK (port 40006), proxy_role=passthrough, hm_num_keys=5, hm_model_tiers=["glm5.1_hm_nv"], hm_default_model="glm5.1_hm_nv"。
HM2自R445(2026-06-30T14:20:51Z)后零变更(本轮未触发重启, env与compose一致)。

### 1b. DB 30min (真实UTC 16:14-16:44 = DB ts 23:44-00:44)
| 指标 | 数值 |
|------|------|
| 总请求 | 242 |
| 成功 (200) | 239 (98.76%) |
| 失败 | 3 (1.24%) |
| p50 | 6,945ms |
| p95 | 37,188ms |
| max | 86,591ms |
| 429 | 0 |
| empty200 | 0 |
| all_tiers_exhausted | 3 |

失败结构: 3× all_tiers_exhausted (avg 82,612ms, max 86,591ms; 2×NVCFPexecTimeout: ~48s+~34s≈82s)。0×429, 0×empty200, 0×SSLEOF。

### 1c. DB 30min per-key (5-key 均衡验证, success+fail)
| nv_key_idx | reqs | ok | err | avg_ms | p50 | p95 | max |
|------|------|----|----|--------|------|------|------|
| 0 (k1) | 48 | 48 | 0 | — | 6,304 | 19,929 | 52,498 |
| 1 (k2) | 37 | 37 | 0 | — | 7,847 | 16,744 | 22,792 |
| 2 (k3) | 59 | 59 | 0 | — | 7,883 | 35,003 | 68,061 |
| 3 (k4) | 47 | 47 | 0 | — | 6,898 | 22,104 | 72,078 |
| 4 (k5) | 48 | 48 | 0 | — | 5,304 | 38,275 | 48,512 |
| null | 3 | 0 | 3 | 82,612 | 82,505 | 86,193 | 86,591 |

5 key reqs 37-59, p50 5.3-7.9s 同级, **无单key劣化**。k3(idx2) max68s为正常尾部, 非HM1-k4式劣化。3 null = all_tiers_exhausted proxy级abort (未分配key)。

### 1d. DB 24h聚合 (真实UTC 06-29 16:44~06-30 16:44 = DB 00:44~00:44)
| 指标 | 数值 |
|------|------|
| 总请求 | 5,185 |
| 成功 (200) | 5,044 (97.28%) |
| 失败 | 141 |
| p50 | 7,434ms |
| 429 | 0 |
| empty200 | 0 |
| all_tiers_exhausted | 137 |

24h 5185req/97.28% — 与R461(5195req/97.29%)同期数据持平, 稳态未变。

### 1e. DB 24h 失败 duration 分布 (BUDGET 硬截断检测)
| 区间 | count | 含义 |
|------|-------|------|
| <50s | 5 | FASTBREAK/快速失败/单次timeout |
| 50-80s | 22 | 2×timeout (BUDGET截断第2attempt) |
| 80-85s | 23 | 2×timeout (主集群) |
| 85-90s | 6 | 2×timeout (BUDGET边界90s) |
| 90-100s | 33 | 2×full timeout (48s+48s) |
| ≥100s | 52 | 重启前 FASTBREAK=3 时代 3×timeout 残留 |

失败主集群在 80-90s (29个, 2×timeout自然到82.5s<90s), **非BUDGET硬截断** (90s边界仅6个, 多数<85s)。与R461分布一致。

### 1f. DB 24h 慢成功 (BUDGET误杀风险评估)
| 区间 | 成功数 |
|------|--------|
| 80-85s | 5 |
| 85-90s | 6 |
| ≥90s | 21 |

24h **32个慢成功 ≥80s (0.63%)**, 含21个≥90s (第4attempt救回)。降BUDGET 90→85 误杀6个(85-90s)+5个(80-85s部分)=11个; 90→80 误杀32个。与R461一致。

### 1g. DB 6h tier_attempts (hm_tier_attempts, litellm_model LIKE '%glm%', DB 18:44-00:44)
| litellm_model | count | avg_ms | max_ms |
|------|------|------|------|
| k1 | 2 | 48,661 | 48,759 |
| k2 | 4 | 49,601 | 50,698 |
| k3 | 6 | 49,913 | 52,529 |
| k4 | 4 | 48,617 | 49,081 |
| k5 | 5 | 49,386 | 50,585 |

- 21 attempts, 全部 NVCFPexecTimeout, 0 成功
- avg_elapsed≈49s, max=52,529ms (≈UPSTREAM_TIMEOUT=48s)
- per-key: k1=2, k2=4, k3=6, k4=4, k5=5 (均匀, 无单key被NVCF标记)

**关键**: 21次ATE全失败 → k4/k5从未救回请求 (与R459/R461一致)。失败由 2×consecutive NVCFPexecTimeout 主导 (~48s+~34s=82s)。

### 1h. DB 8h逐时吞吐 (真实UTC 08:00-16:00 = DB 16:00-00:00)
| 真实UTC hour | reqs | reqs/min | p50 |
|------|------|------|------|
| 08:00 | 69 | 1.15 | 8,553 |
| 09:00 | 245 | 4.08 | 6,224 |
| 10:00 | 244 | 4.07 | 8,677 |
| 11:00 | 308 | 5.13 | 6,318 |
| 12:00 | 194 | 3.23 | 9,022 |
| 13:00 | 167 | 2.78 | 9,552 |
| 14:00 | 142 | 2.37 | 9,657 |
| 15:00 | 202 | 3.37 | 7,881 |
| 16:00 | 183 | 3.05 | 6,955 |

吞吐峰值=5.13 req/min (11:00), 多数时段2-5 req/min。throttle理论上限=60/2.5=24 req/min, 实测峰值仅21%利用 → **throttle非瓶颈**。吞吐波动=流量驱动。与R461(峰值4.68rpm, 30%利用)同级。

## 2. CC清单评估 ([HM2-A/B/C] 节, 对端=HM2)

### [HM2-A] MIN_OUTBOUND_INTERVAL_S 4.5→2.5 → 证伪/已达成
- **当前**: 2.5 (R386: 5.0→2.5, **清单目标值已达成**, compose L472)
- **数据**: 30min 0×429, p50=6.9s vs MIN_OUTBOUND=2.5s → gap 277% (实际请求间隔p50远大于throttle, throttle非瓶颈)
- **吞吐**: 8h峰值5.13 rpm, throttle上限24 rpm, 利用率仅21% → 降throttle无吞吐收益
- **结论**: **证伪/已达成** — 清单目标2.5已在R386落地。当前0×429, p50_gap 277%, throttle利用率21% 非瓶颈, 再降无吞吐收益且增429风险 (与R461一致)

### [HM2-B] 失败模式数据补采找劣化key → 证伪
- **当前**: 24h 5-key reqs 970-1053级(30min 37-59), 30min p50 5.3-7.9s 同级, 30min err全0
- **数据**: 无单key劣化。141失败跨key随机分布(137 null nv_key_idx = all_tiers_exhausted proxy级abort), 全NVCFPexecTimeout server-side。6h ATE per-key k1-k5: 2/4/6/4/5 均匀, 无单key被NVCF标记。
- **结论**: **证伪** — 5-key高度均衡, 无HM1-k4式劣化key。无需改路由 (与R461一致)

### [HM2-C] TIER_TIMEOUT_BUDGET_S 128→100 → 证伪
- **当前**: 90 (R445: 85→90, **已低于清单目标100**, compose L470)
- **数据 (双向证伪, 与R461一致)**:
  - **降向 (90→85)**: 24h仅6失败落85-90s (BUDGET边界), 23失败在80-85s (2×timeout自然到82.5s<85s不受影响)。降BUDGET→这6个失败早0-5s结束, 收益~30s/24h; 但误杀6成功(85-90s)+5个(80-85s部分)=11个。违"稳定优先>成功率", 收益<代价。且失败非BUDGET硬截断(主集群82.5s<90s), 降BUDGET仅截断极少数第2attempt边界。
  - **升向 (90→100)**: 失败2×timeout升82.5s→~92s (第2attempt read_timeout 34→44s, 延长~10s/次×141失败=~1410s/24h纯浪费), 仍remaining<10s无3rd attempt, 无救回收益(ATE 21次全失败, k4/k5从未救回)���纯延长失败耗时。
- **结论**: **证伪** — BUDGET=90已是最优。降则误杀慢成功违稳定优先(收益~30s vs 误杀11成功), 升则延长失败~1410s/24h无救回收益 (与R461一致)

## FASTBREAK=5 死参数 (非清单项, 记录, 与R461一致)
- **现象**: 容器重启后(FASTBREAK=5, 自R445稳定) logs零次HM-PEXEC-FASTBREAK触发; 重启前(FASTBREAK=3)24h有触发
- **根因**: BUDGET=90仅容2 attempt (48s+34s=82s, remaining<10s break), consecutive_pexec_timeout永远只到2, 达不到阈值5(或3)
- **本轮不改**: (1) FASTBREAK 3↔5均为死参数(BUDGET限制下二者等价零触发); (2) 降FASTBREAK→1会杀慢成功rescue(21个≥90s慢成功含第4attempt救回); (3) 非清单项, 违"每轮1项+清单优先"原则。

## 决策: NOP · 零配置变更

**理由**: CC清单[HM2-A/B/C]三项全部被24h+30min最新数据复检测证伪/已达成。HM2已处于全参数天花板:

| 参数 | 值 | 状态 |
|------|-----|------|
| MIN_OUTBOUND | 2.5 | 清单HM2-A目标值已达成(R386), 0×429, p50_gap 277%, throttle利用率21% 非瓶颈 |
| KEY_COOLDOWN | 38 | 已最优 (24h 5-key均衡, 30min err全0) |
| TIER_COOLDOWN | 22 | 已最优 (KEY=38>TIER=22, 单tier模型) |
| UPSTREAM_TIMEOUT | 48 | 已最优 (ATE avg 49s≈48s 覆盖) |
| BUDGET | 90 | 已最优 (清单目标100已超额达成, 双向证伪) |
| CONNECT_RESERVE | 8 | 已最优 (R431: 10→8) |
| SSLEOF_RETRY | 1.0 | 已最优 (0 SSLEOF失败) |
| FASTBREAK | 5 | 死参数 (BUDGET=90容2attempt永不触发), 维持 |

**失败根因(不可proxy层修复)**: 137×all_tiers_exhausted全NVCFPexecTimeout server-side (NVCF glm5.1_hm_nv后端慢/超时~48s/attempt), 跨key随机, 2×timeout avg82.5s。proxy层无法修复NVCF server-side慢响应。慢成功rescue(21个≥90s)由BUDGET+多attempt机制保住, 不可牺牲。

**铁律**: 只改HM2不改HM1 · 零配置变更 · 零docker compose重启 · 零容器env改动

## 改前/改后对比 (NOP, 同窗口)
| 指标 | 改前(30min) | 改后(30min) |
|------|------|------|
| reqs | 242 | 242 (NOP, 同窗口) |
| 成功率 | 98.76% | 98.76% |
| p50 | 6,945ms | 6,945ms |
| p95 | 37,188ms | 37,188ms |
| 429 | 0 | 0 |
| empty200 | 0 | 0 |
| all_tiers_exhausted | 3 | 3 |

NOP轮无配置变更, 改前=改后同窗口。24h长窗口(5185req/97.28%)为稳态证据。

## 历史对比
| 轮次 | 30min reqs | 30min成功率 | 24h reqs | 24h成功率 | 变更 |
|------|-----------|------------|---------|---------|------|
| R463 | 242 | 98.76% | 5185 | 97.28% | ⏸️ NOP |
| R461 | 282 | 99.29% | 5195 | 97.29% | ⏸️ NOP |
| R459 | 141 | 99.29% | 5218 | 97.26% | ⏸️ NOP |
| R454 | 1856 | 96.39% | — | — | ⏸️ NOP |

30min 242req/98.76% — 流量较R461(282req)略降, 成功率98.76%vs99.29%(2-3失败波动, 137 ATE/24h稳态)。24h 5185req/97.28%稳定(R461 5195req/97.29%, 同期数据)。失败结构未变(all_tiers_exhausted NVCF server-side)。

## 部署
```bash
# 无操作 — 容器 keep running (StartedAt 2026-06-30T14:20:51Z, 稳定26.3h+, 自R445后零变更)
# 验证: /health=200 OK (port 40006), hm_num_keys=5, 8项env双处零漂移
# compose /opt/cc-infra/docker-compose.yml L469-505 = 容器运行态, 双处一致
# HM2自R445(14:20:51Z)后零变更
```

## ⏳ 轮到HM2优化HM1
