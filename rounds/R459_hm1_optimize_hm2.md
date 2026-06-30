# R459: HM1→HM2 — ⏸️ NOP · CC清单[HM2-A/B/C]三项重验证全部证伪/已达成 · 全参数天花板 · 30min 141req/99.29% · 24h 5218req/97.26% · 5-key均衡p50 5.3-8.6s · 0 429/0 empty200 · 失败主集群80-90s BUDGET非硬截断·双向证伪 · FASTBREAK=5死参数(BUDGET=90仅容2attempt永不触发) · 8项env双处零漂移 · 铁律:只改HM2不改HM1 · 零配置变更

**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**动作**: NOP (零配置变更)
**时间**: 2026-07-01 00:10 UTC (CST 08:10)
**轮次**: R459 → 接R458(HM2→HM1: NOP, commit 15bc15c, HM2 session 连续触发R456/457/458均写入RN模板未单独命名文件)

## 数据采集 (HM2 对端, host_machine=opc2sname)

### 1. 容器环境变量 (运行态 vs live compose, 双处验证)
**live compose**: `/opt/cc-infra/docker-compose.yml` (project=cc-infra)
**容器 StartedAt**: 2026-06-30T14:20:51Z (R445 重启后稳定 9.8h+, 自 R445 后零变更)

| 参数 | 容器运行态 | compose行 | 一致 | 来源轮次 |
|------|-----------|----------|------|----------|
| UPSTREAM_TIMEOUT | 48 | L469 | ✓ | R284: 75→68→48 |
| TIER_TIMEOUT_BUDGET_S | 90 | L470 | ✓ | R445: 85→90 |
| MIN_OUTBOUND_INTERVAL_S | 2.5 | L472 | ✓ | R386: 5.0→2.5 (清单HM2-A目标值已达成) |
| KEY_COOLDOWN_S | 38 | L473 | ✓ | R275: 32→36→38 |
| TIER_COOLDOWN_S | 22 | L474 | ✓ | R1: 45→30→22 |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | L480 | ✓ | R321: 3.0→1.0 |
| HM_PEXEC_TIMEOUT_FASTBREAK | 5 | L482 | ✓ | R384: 3→5 |
| HM_CONNECT_RESERVE_S | 8 | L505 | ✓ | R431: 10→8 |

**8项全活跃零漂移**: compose=容器一致。/health=200 OK, hm_num_keys=5, proxy_role=passthrough, model=glm5.1_hm_nv。

> 注: hm2_new_deployment/docker-compose-minimal.yml 是归档/无关文件(值全错: MIN_OUTBOUND=13.5/BUDGET=125), 非 live compose, 不影响运行态。live compose 在 /opt/cc-infra/。

### 2. DB 30min 窗口 (23:37-00:07 CST, 绝对时间戳避免NOW()时区陷阱)
- **Total**: 141 req, **Success**: 140 (99.29%), **Errors**: 1 (0.71%)
- **p50**: 7273ms, **p95**: 26149ms, **max**: 82505ms
- **失败结构**: 1× all_tiers_exhausted (82505ms, 2×NVCFPexecTimeout: k4 48.7s + k5 33.8s)
- **429**: 0, **empty200**: 0, **SSLEOF**: 0 (1 SSLEOF 事件 k2 经 1.0s backoff retry → k3 成功救回, 未计入失败)

### 3. DB 60min 窗口 (23:07-00:07 CST, 稳定确认)
- **Total**: 232 req, **Success**: 229 (98.71%), **Errors**: 3 (1.29%)
- **p50**: 7784ms, **p95**: 36736ms
- **失败**: 3× all_tiers_exhausted (avg 78416ms)

### 4. Per-Key 延迟 (30min 成功, 5-key 均衡验证)
| Key | Reqs | ok | err | avg(ms) | p50(ms) | p95(ms) | max(ms) |
|-----|------|-----|-----|---------|---------|---------|---------|
| k0 | 28 | 28 | 0 | 7754 | 5313 | 18694 | 35387 |
| k1 | 24 | 24 | 0 | 9200 | 8599 | 16387 | 18953 |
| k2 | 34 | 34 | 0 | 11573 | 7800 | 35513 | 54099 |
| k3 | 28 | 28 | 0 | 7204 | 6358 | 12927 | 14300 |
| k4 | 29 | 29 | 0 | 10873 | 7880 | 32283 | 38809 |
| null | 1 | 0 | 1 | 82505 | 82505 | 82505 | 82505 |

**5-key 均衡**: reqs 24-34, p50 5.3-8.6s 同级, 无单 key 劣化。1 null = all_tiers_exhausted proxy级abort (未分配key)。

### 5. Per-Key 24h 失败率 (劣化key排查, 清单HM2-B)
| Key | total | ok | err | err% | ok_avg | ok_p95 |
|-----|-------|-----|-----|------|--------|--------|
| k0 | 973 | 972 | 1 | 0.10% | 11913 | 38154 |
| k1 | 1059 | 1058 | 1 | 0.09% | 12516 | 41852 |
| k2 | 1037 | 1037 | 0 | 0.00% | 11604 | 42453 |
| k3 | 1002 | 1002 | 0 | 0.00% | 12194 | 45333 |
| k4 | 1004 | 1002 | 2 | 0.20% | 11964 | 38502 |
| null | 139 | 0 | 139 | 100% | — | — |

**24h 5-key 均衡**: reqs 973-1059 (cv=3.4%), err% 0.00-0.20% (全部<0.25%, 噪声级), 无单key劣化。k2/k3(用代理7895/7897)零失败但样本量内不显著。139 null = all_tiers_exhausted 跨key随机。**HM2-B 证伪**。

### 6. 失败 duration 分布 (24h, 143 failures, 精确区间)
| 区间 | count | 含义 |
|------|-------|------|
| <50s | 5 | FASTBREAK/快速失败/单次timeout |
| 50-80s | 22 | 2×timeout (BUDGET截断第2attempt) |
| 80-85s | 23 | 2×timeout (主集群, 重启后) |
| 85-90s | 5 | 2×timeout (BUDGET边界) |
| 90-100s | 33 | 2×full timeout (48s+48s) |
| 100-110s | 2 | 2×timeout + overhead |
| ≥120s | 53 | 重启前 FASTBREAK=3 时代的 3×timeout |

**重启后(FASTBREAK=5)失败模式**: 全部 `timeout=2 elapsed≈82.5s` (logs 5×HM-TIER-FAIL 全显示 timeout=2, elapsed 82484-83141ms), 落在 80-90s 区间。重启前(FASTBREAK=3)有 53×3-attempt 失败(≥120s)。
**关键发现**: FASTBREAK=5 是**死参数** — BUDGET=90 仅容 2 attempt (48s+34s=82s, remaining<10s break), 永远达不到 5 consecutive timeout 阈值。重启后 logs 零次 HM-PEXEC-FASTBREAK 触发。

### 7. ATE (hm_tier_attempts, 6h 18:07-00:07)
- **21 次** tier attempt, **全部 21 次 NVCFPexecTimeout, 0 次成功**
- avg_elapsed=49029ms, max=55779ms, 跨 5 key (k0=1/k1=1/k2=3/k3=4/k4=2)
- 每 attempt avg ~49s ≈ UPSTREAM_TIMEOUT=48s
- **ATE 表只记录首次 timeout** (logs 显示 2×attempt 但 ATE 表 1 行/请求), 后续 attempt 未入表

**关键发现**: ATE 6h 21 次全失败 → k4/k5 从未救回任何请求 (与R454一致)。失败由 2×consecutive NVCFPexecTimeout server-side 主导 (~48s+34s=82s), BUDGET=90 在第2次 attempt 后 remaining<10s 自然 break。

### 8. 慢成功分布 (24h, BUDGET 误杀风险评估)
| 区间 | 成功数 |
|------|--------|
| <80s | 5019 |
| 80-85s | 5 |
| 85-90s | 6 |
| ≥90s | 23 |

24h **34 个慢成功 ≥80s (0.67%)**, 含 23 个 ≥90s (第4 attempt 救回, 含7个100-120s)。降 BUDGET 90→85 会误杀 6 个(85-90s)+5个(80-85s)=11个, 90→80 误杀 34 个。

### 9. Rescue 成功 (24h, 多 attempt 救回)
| cycle_429s | 成功数 | avg(ms) | 含义 |
|-----------|--------|---------|------|
| 0 | 4944 | 10540 | 首次成功 |
| 1 | 105 | 67337 | 第2 attempt 救回 |
| 2 | 10 | 100611 | 第3 attempt 救回 |
| 3 | 7 | 119600 | 第4 attempt 救回 |

24h **122 个 rescue 成功 (2.4%)**。降 FASTBREAK 到 1 会杀掉这 122 个 (违"稳定优先>成功率")。

### 10. throttle 瓶颈分析 (30min)
- 实际请求间隔: avg=12718ms, p50=7445ms, min=8ms (并发流, MIN_OUTBOUND 是串行锁)
- p50_gap: 7445ms vs MIN_OUTBOUND=2500ms → **298% gap**
- **0 个 429** → throttle 完全不是瓶颈, 且有下降空间但无吞吐收益

## CC清单 评估 ([HM2-A/B/C] 节, 对端=HM2)

### [HM2-A] MIN_OUTBOUND_INTERVAL_S 4.5→2.5
- **当前**: 2.5 (R386: 5.0→2.5, **清单目标值已达成**)
- **数据**: 0 429, p50_gap=7445ms >> 2.5s (298%), throttle 非瓶颈
- **结论**: **证伪/已达成** — 清单目标 2.5 已在 R386 落地。当前 0 429, p50_gap 298% 证明再降无吞吐收益 (实际间隔 p50=7.4s, MIN_OUTBOUND 串行锁非主导)。

### [HM2-B] 失败模式数据补采找劣化 key
- **当前**: 24h 5-key reqs 973-1059 (cv=3.4%), err% 0.00-0.20% (噪声级), p50 5.3-8.6s 同级
- **数据**: 无单 key 劣化。失败 (139 ATE) 跨 key 随机分布 (null nv_key_idx), 全 NVCFPexecTimeout server-side。k2/k3(代理)零失败但样本内不显著, k4(direct+7897) err 0.20% 略高但仅 2/1004, 噪声。
- **结论**: **证伪** — 5-key 高度均衡, 无 HM1-k4 式劣化 key。无需改路由。

### [HM2-C] TIER_TIMEOUT_BUDGET_S 128→100
- **当前**: 90 (R445: 85→90, **已低于清单目标 100**)
- **数据 (双向证伪)**:
  - **降向 (90→85)**: 24h 仅 5 失败落在 85-90s (BUDGET 边界), 23 失败在 80-85s (2×timeout 自然到 82.5s<85s 不受影响)。降 BUDGET 85 → 这 5 个失败早 0-3s 结束, 收益微 (~15s/24h); 但误杀 6 成功(85-90s)。违"稳定优先>成功率", 收益<代价。且失败非 BUDGET 硬截断 (2×timeout 自然到 82.5s<90s), 降 BUDGET 仅截断极少数第2 attempt 边界。
  - **升向 (90→100)**: 失败 2×timeout 升 82.5s→~92s (第2 attempt read_timeout 34→44s, 延长 ~10s/次 ×143 失败 = ~1430s/24h 纯浪费), 仍 remaining<10s 无 3rd attempt, 无救回收益 (ATE 21次全失败, k4/k5从未救回)。纯延长失败耗时。
- **结论**: **证伪** — BUDGET=90 已是最优。降则误杀慢成功违稳定优先 (收益~15s vs 误杀6成功), 升则延长失败 ~1430s/24h 无救回收益。

## FASTBREAK=5 死参数发现 (非清单项, 仅记录)
- **现象**: 重启后(FASTBREAK=5, 9.8h) logs 零次 HM-PEXEC-FASTBREAK 触发; 重启前(FASTBREAK=3) 24h 25次触发
- **根因**: BUDGET=90 仅容 2 attempt (48s+34s=82s, remaining<10s break), consecutive_pexec_timeout 永远只到 2, 达不到阈值 5 (或 3)
- **代码注释 (upstream.py L226-229)**: R350 设计意图 FASTBREAK=3 "save 4th key attempt", 但 R445 把 BUDGET 85→90 + R384 FASTBREAK 3→5 后, BUDGET 限制使 fastbreak 永不触发
- **本轮不改**: (1) FASTBREAK 3↔5 均为死参数 (BUDGET 限制下二者等价零触发); (2) 降 FASTBREAK→1 会杀 122 rescue/24h (2.4%); (3) 非清单项, 违"每轮1项+清单优先"原则。留作后续轮次评估 BUDGET+FASTBREAK 联动。

## 决策: NOP · 零配置变更

**理由**: CC清单[HM2-A/B/C]三项全部 证伪/已达成。HM2 已处于全��数天花板:

| 参数 | 值 | 状态 |
|------|-----|------|
| MIN_OUTBOUND | 2.5 | 清单HM2-A目标值已达成 (R386), 0 429, p50_gap 298% 非瓶颈 |
| KEY_COOLDOWN | 38 | 已最优 (24h 5-key 均衡 cv=3.4%) |
| TIER_COOLDOWN | 22 | 已最优 (KEY=38>TIER=22, 单tier模型) |
| UPSTREAM_TIMEOUT | 48 | 已最优 (ATE avg 49s≈48s 覆盖) |
| BUDGET | 90 | 已最优 (清单目标100已超额达成, 双向证伪) |
| CONNECT_RESERVE | 8 | 已最优 (R431: 10→8) |
| SSLEOF_RETRY | 1.0 | 已最优 (0 SSLEOF 失败, 1事件经retry救回) |
| FASTBREAK | 5 | 死参数 (BUDGET=90容2attempt永不触发), 但降之无收益(3亦死)且升FASTBREAK无意义, 维持 |

**失败根因 (不可 proxy 层修复)**: 142× all_tiers_exhausted 全 NVCFPexecTimeout server-side (NVCF glm5.1_hm_nv 后端慢/超时 ~48s/attempt), 跨 key 随机, 2×timeout avg 82.5s。proxy 层无法修复 NVCF server-side 慢响应。Rescue 122/24h (2.4%) 由 BUDGET+多attempt 机制保住, 不可牺牲。

**铁律**: 只改 HM2 不改 HM1 · 零配置变更 · 零 docker compose 重启 · 零容器env改动

## 历史对比

| 轮次 | 30min reqs | 30min成功率 | 24h reqs | 24h成功率 | 变更 |
|------|-----------|------------|---------|---------|------|
| R459 | 141 | 99.29% | 5218 | 97.26% | ⏸️ NOP |
| R454 | 1856 | 96.39% | — | — | ⏸️ NOP |
| R451 | 64 | 90.63% | 2009(9.1h) | 96.57% | ⏸️ NOP |

30min 141req/99.29% — 低流量时段小窗口, 但成功率创近期新高 (99.29% vs R454 96.39%)。24h 5218req/97.26% 稳定。失败结构未变 (all_tiers_exhausted NVCF server-side)。

## 部署
```bash
# 无操作 — 容器 keep running (StartedAt 14:20:51Z, 稳定 9.8h+)
# 验证: /health=200 OK, hm_num_keys=5, 8项env双处零漂移
# compose /opt/cc-infra/docker-compose.yml L469-505 = 容器运行态, 双处一致
```

## ⏳ 轮到HM2优化HM1
