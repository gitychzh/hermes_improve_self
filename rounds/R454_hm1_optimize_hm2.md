# R454: HM1→HM2 — ⏸️ NOP · CC清单[HM2-A/B/C]三项重验证全部证伪/已达成 · 全参数天花板 · 30min 1856req/96.39% · 60min 1985req/96.57% · 5-key均衡p50 7.2-8.1s · 0 429/0 empty200/0 SSLEOF · 铁律:只改HM2不改HM1 · 零配置变更

**方向**: HM1 优化 HM2
**动作**: NOP (无配置变更)
**时间**: 2026-06-30 23:50 UTC
**轮次**: R454 → 接R453(HM2→HM1: NOP)

## 数据采集 (HM2 对端, host_machine=opc2sname)

### 1. 容器环境变量 (当前运行值 vs live compose)
**live compose**: `/opt/cc-infra/docker-compose.yml` (project=cc-infra, docker inspect 确认 config_files)
**容器 StartedAt**: 2026-06-30T14:20:51Z (R445 重启后稳定 9.6h+, 自 R445 后零变更)

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

> 注: hm2_new_deployment/docker-compose-minimal.yml 是归档/无关文件(值全错: MIN_OUTBOUND=13.5/BUDGET=125),非 live compose,不影响运行态。live compose 在 /opt/cc-infra/。

### 2. DB 查询 (30min/60min)

#### 30min 窗口
- **Total**: 1856 req, **Success**: 1789 (96.39%), **Errors**: 67 (3.61%)
- **p50**: 7812ms, **p95**: 56425ms, **max**: 103136ms
- **失败结构**: 64× all_tiers_exhausted (avg 82973ms, max 103136ms) + 3× NVStream_IncompleteRead (avg 30034ms)
- **429**: 0, **empty200**: 0, **SSLEOF**: 0

#### 60min 窗口 (稳定确认)
- **Total**: 1985 req, **Success**: 1917 (96.57%), **Errors**: 68 (3.43%)
- **p50**: 7770ms, **p95**: 55364ms, **max**: 103136ms
- **失败结构**: 65× all_tiers_exhausted (avg 83114ms) + 3× NVStream_IncompleteRead
- **429**: 0, **empty200**: 0, **SSLEOF**: 0

### 3. Per-Key 延迟 (30min, 5-key 均衡验证)
| Key | Reqs | ok | err | avg(ms) | p50(ms) | p95(ms) | max(ms) |
|-----|------|-----|-----|---------|---------|---------|---------|
| k0 | 368 | 368 | 0 | 11768 | 7717 | 40554 | 64747 |
| k1 | 346 | 345 | 1 | 12791 | 8108 | 40831 | 85306 |
| k2 | 374 | 374 | 0 | 11258 | 7297 | 38030 | 76613 |
| k3 | 342 | 342 | 0 | 12280 | 7233 | 42856 | 91222 |
| k4 | 362 | 360 | 2 | 12118 | 7475 | 38518 | 70783 |
| null | 64 | 0 | 64 | 82973 | 82578 | 95423 | 103136 |

**5-key 均衡**: reqs 342-374 (cv=3.7%, 高度均衡), p50 7.2-8.1s 同级 (gap 875ms), 无单 key 劣化。64 个 null nv_key_idx = all_tiers_exhausted proxy 级 abort (未分配 key)。

### 4. 失败 duration 分布 (60min, all_tiers_exhausted 65 个)
| bucket | count | min_ms | max_ms |
|--------|-------|--------|--------|
| 0-15s | 1 | 10582 | 10582 | (FASTBREAK 触发, 10.5s 快速失败)
| 75-90s | 46 | 75488 | 89895 |
| 90-103s | 18 | 90204 | 103136 |

**关键发现**: 18 个失败 >90s (即 >BUDGET=90s), 证明 BUDGET=90 **不是硬截断上限** — all_tiers_exhausted 跑完所有 key 自然到 90-103s。失败由 5 key 顺序 NVCFPexecTimeout 主导 (~5×16.6s=83s avg), BUDGET 几乎不参与失败路径。

### 5. ATE (hm_tier_attempts, 30min)
- **38 次** tier attempt, **全部 38 次 NVCFPexecTimeout 失败, 0 次成功**
- avg_elapsed=49029ms, max=55779ms, 跨 5 key (k0=8/k1=6/k2=10/k3=7/k4=7 attempts)
- 每 key ATE avg 47-50s ≈ UPSTREAM_TIMEOUT=48s

**关键发现**: ATE 30min 38 次全失败 → 当请求走到 ATE (k0-k2 已 timeout), 后续 k3/k4 也都 timeout, **k4/k5 从未救回任何请求**。

### 6. 慢成功分布 (60min, BUDGET 误杀风险评估)
| 区间 | 成功数 |
|------|--------|
| <80s | 1914 |
| 80-85s | 0 |
| 85-90s | 1 |
| ≥90s | 2 |

60min 仅 **3 个慢成功** (85-103s, 占 0.16%)。降 BUDGET 90→85 会误杀这 3 个成功。

### 7. throttle 瓶颈分析 (30min)
- 实际请求间隔: avg=17s, p50=8s, min=0s (并发流, MIN_OUTBOUND 是串行锁)
- p50=7812ms vs MIN_OUTBOUND=2500ms → p50 是 throttle 的 **312%**
- **0 个 429** → throttle 完全不是瓶颈, 且有下降空间但无收益

## CC清单 评估 ([HM2-A/B/C] 节, 对端=HM2)

### [HM2-A] MIN_OUTBOUND_INTERVAL_S 4.5→2.5
- **当前**: 2.5 (R386: 5.0→2.5, **清单目标值已达成**)
- **数据**: 0 429, p50_gap=8s >> 2.5s (312%), throttle 非瓶颈
- **结论**: **证伪/已达成** — 清单目标 2.5 已在 R386 落地。当前 0 429 有下降空间但 p50_gap 已 312% 证明再降无吞吐收益。实际间隔 p50=8s 说明请求并发处理, MIN_OUTBOUND 串行锁非主导。

### [HM2-B] 失败模式数据补采找劣化 key
- **当前**: 5-key reqs 342-374 (cv=3.7%), p50 7.2-8.1s 同级 (gap 875ms)
- **数据**: 无单 key 劣化。失败 (64 ATE) 跨 key 随机分布 (k0-k4 均有), 全 NVCFPexecTimeout server-side。k4 max=70.8s vs k1 max=85.3s, k4 反而最稳。
- **结论**: **证伪** — 5-key 高度均衡, 无 HM1-k4 式劣化 key。无需改路由。

### [HM2-C] TIER_TIMEOUT_BUDGET_S 128→100
- **当前**: 90 (R445: 85→90, **已低于清单目标 100**)
- **数据 (双向证伪)**:
  - **降向 (90→85)**: 60min 3 个慢成功 (85-103s) 会被误杀 (0.16%), 违"稳定优先>成功率"。失败 max=103s>BUDGET=90 证明 BUDGET 非硬截断, 降 BUDGET 不让失败早结束 (失败由 5 key timeout 主导非 BUDGET)。
  - **升向 (90→100)**: 30min ATE 38 次全失败, k4/k5 从未救回 → 扩 BUDGET 给更多 attempt 时间无收益, 反延长失败耗时。
- **结论**: **证伪** — BUDGET=90 已是最优。降则误杀慢成功, 升则延长失败无救回收益。

## 决策

**NOP** — 三项 CC清单 [HM2-A/B/C] 全部 证伪/已达成。HM2 已处于全参数天花板:

| 参数 | 值 | 状态 |
|------|-----|------|
| MIN_OUTBOUND | 2.5 | 清单HM2-A目标值已达成 (R386), 0 429, 非瓶颈 |
| KEY_COOLDOWN | 38 | 已最优 (5-key 均衡 cv=3.7%) |
| TIER_COOLDOWN | 22 | 已最优 (KEY=38>TIER=22, 单tier模型) |
| UPSTREAM_TIMEOUT | 48 | 已最优 (ATE avg 49s≈48s 覆盖) |
| BUDGET | 90 | 已最优 (清单目标100已超额达成, 双向证伪) |
| CONNECT_RESERVE | 8 | 已最优 (R431: 10→8) |
| SSLEOF_RETRY | 1.0 | 已最优 (0 SSLEOF 事件) |
| FASTBREAK | 5 | 已最优 (R384: 3→5, 30min 1次触发10.5s快速失败) |

**失败根因 (不可 proxy 层修复)**: 65× all_tiers_exhausted 全 NVCFPexecTimeout server-side (NVCF glm5.1_hm_nv 后端慢/超时), 跨 key 随机, avg 83s ≈ 5×16.6s。FASTBREAK=5 已让 1 个失败在 10.5s 快速结束。proxy 层无法修复 NVCF server-side 慢响应。

**铁律**: 只改 HM2 不改 HM1 · 零配置变更 · 零 docker compose 重启

## 部署
```bash
# 无操作 — 容器 keep running (StartedAt 14:20:51Z, 稳定 9.6h+)
# 验证: /health=200 OK, hm_num_keys=5, 8项env双处零漂移
curl -s localhost:40006/health  # → {"status":"ok","hm_num_keys":5}
```

## ⏳ 轮到HM2优化HM1
