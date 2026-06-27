# R156: HM1→HM2 — KEY_COOLDOWN_S: 34→36 (+2s)

**回合类型**: 优化 (单参数)
**时间**: 2026-06-28 04:31 UTC
**角色**: HM1 (opc_uname) 优化 HM2 (opc2_uname)
**原则**: 少改多轮 · 单参数 · 只改HM2不改HM1 · 铁律:不碰mihomo

---

## 📊 数据收集

### HM2运行环境 (docker exec env)

| 参数 | 值 |
|------|-----|
| KEY_COOLDOWN_S | **34** |
| TIER_COOLDOWN_S | **34** |
| MIN_OUTBOUND_INTERVAL_S | 10.5 |
| UPSTREAM_TIMEOUT | 71 |
| TIER_TIMEOUT_BUDGET_S | 132 |
| HM_CONNECT_RESERVE_S | 24 |
| GLOBAL_COOLDOWN_S | 45 (硬编码) |

mihomo状态: ✅ 运行中 (PID 2008535)
容器状态: hm40006 Up (healthy)

### 30-min 请求窗口 (hm_requests)

| 指标 | 值 |
|------|-----|
| 总请求 | 1456 |
| 成功 (200) | 1454 (99.86%) |
| 失败 | 2 |
| fallback触发 | 484 (33.2%) |
| 用户错误 (非empty_200) | 2 |

### 30-min 按tier延迟 (hm_requests)

| tier | 请求数 | avg_ms | p50_ms | p90_ms | p95_ms | max_ms |
|------|--------|--------|--------|--------|--------|--------|
| deepseek_hm_nv | 485 | 20,435 | 15,193 | 37,168 | 52,975 | 192,229 |
| glm5.1_hm_nv | 970 (67%) | 15,082 | 10,348 | 29,580 | 46,717 | 127,176 |

### 30-min tier级别尝试 (hm_tier_attempts)

| tier | 总尝试 | 429 | empty_200 | SSLEOF | Timeout | ConnReset |
|------|--------|-----|-----------|--------|---------|-----------|
| deepseek_hm_nv | 26 | 0 | 1 | **25** | 0 | 0 |
| glm5.1_hm_nv | **1058** | **871** | 20 | 100 | 20 | 42 |

### ATE (all_tiers_exhausted) 跨窗口

| 窗口 | ATE |
|------|-----|
| 30-min | 2 |
| 1h | 2 |
| 2h | 2 |
| 6h | 7 |

### 错误详情 JSONL (hm_error_detail.2026-06-28.jsonl)

20条最近的tier_glm5.1_hm_nv_all_keys_failed记录 — **100% 显示 `all_429: true`**:

所有glm5.1 tier失败均为全键429同步模式。每次5个NV key同时返回429 — NV API函数级速率限制是唯一瓶颈，非单key耗尽。
典型的elapsed_ms范围: 2,514ms ~ 10,100ms (平均 ~5,200ms)。

1条 all_tiers_failed (request_id=493a3fd9): glm5.1→deepseek→kimi, total_elapsed=135,358ms, deepseek elapsed=134,634ms (4×NVCFPexecTimeout cascading)。

### Docker日志关键片段 (04:29-04:31 UTC)

```
04:29:36 k2→429 → key cycling
04:30:24 k1→429 → key cycling, k2 in cooldown (skip)
04:30:29 k3→SSLEOFError
04:30:34 k2→429 → key cycling
04:30:35 k3→429 → key cycling
04:30:41 k3 in cooldown (skip)
04:31:02 k1/k2/k3 all in cooldown (skip)
04:31:08 k2/k3 in cooldown (skip)
04:31:12 k3→429 → key cycling
```

## 🔍 分析

### 核心发现

**KEY_COOLDOWN_S=34 远低于 GLOBAL_COOLDOWN=45s (gap=11s)**

HM2当前的KEY_COOLDOWN_S=34s意味着键在429后34秒解冻，但NV API函数级速率限制窗口约需45s才清除。键在34s时恢复 → 立即再次命中429（因为NV API函数级窗口未清），导致循环浪费:
- 每轮key cycle耗时4.6-9.1s (error_detail JSONL数据)
- 5 keys × 5 attempts = 25次浪费尝试/tier失败
- Docker log显示: k1/k2/k3同时"in cooldown (skip)" — 所有键在34s窗口内重复激活

**30-min glm5.1: 871 wasted 429s (82% of tier attempts)**

1058次tier尝试中871次是彻底浪费的429 → 仅187次(18%)是有用的尝试。这意味着每100次key-level尝试浪费82次 — 周期效率极低。

### 为什么不是 TIER_COOLDOWN_S?

KEY_COOLDOWN_S控制单个key的429后冷却时间。TIER_COOLDOWN_S只在整层所有key均失败后触发。当前瓶颈是NV API函数级速率限制 (`all_429: true` 100%模式) — 所有key同时返回429。KEY_COOLDOWN_S=36 → 每个key多等2s才恢复，减少在NV API窗口未清时过早重试。

TIER_COOLDOWN_S会在KEY_COOLDOWN_S收敛到45后同步调整 — 两者应同时收敛 (当前都从34同步上升)。

### 预算验证

```
Effective budget = TIER_TIMEOUT_BUDGET_S - HM_CONNECT_RESERVE_S
               = 132 - 24 = 108s

Key cycle with new KEY_COOLDOWN_S=36:
  5 keys × (36s cooldown + 10.5s spacing) ≈ 5 × 46.5 = 232.5s → 远超108s budget

但实际glm5.1 tier cycle在~4.6-9.1s完成 (不是理论232.5s) — KEy_COOLDOWN_S是冷却参数不是执行时间。
108s budget足够: 实际cycle在~5-10s完成。

5 × MIN_OUTBOUND_INTERVAL_S = 5 × 10.5 = 52.5s > GLOBAL=45s, buffer=7.5s — 已经充足。
```

## 🔧 优化计划

**参数**: KEY_COOLDOWN_S: 34 → 36 (+2s)
**理由**: 
- Gap to GLOBAL_COOLDOWN=45s: 34→45 (11s gap). +2s incremental toward 45s target.
- Reduces wasted 429 key cycles (871/1058, 82% waste rate)
- 5-cycle cost: 5×(36+10.5) = 232.5s > budget, but actual cycle <10s — cooldown not a budget consumer
- All 429s are function-level (NV API): faster cooldown = faster re-entry into same rate-limit window

**排除的其他参数**:
- TIER_COOLDOWN_S: 同步收敛目标 (34→36 与 KEY重合), 但KEY先动
- MIN_OUTBOUND_INTERVAL_S: 10.5已够, 52.5s cycle > 45s GLOBAL, buffer 7.5s
- UPSTREAM_TIMEOUT: 71s已够, p95=46.7s远低于71s
- TIER_TIMEOUT_BUDGET_S: 132s已够, effective 108s

**为什么不是无变更?** 2 ATE (30-min/1h/2h) + 871 wasted 429s → 未达100%稳定, 仍有优化空间

## 🔧 执行

```bash
# 1. 修改 docker-compose.yml (line 480)
ssh HM2 'cd /opt/cc-infra && sed -i "480s|KEY_COOLDOWN_S: \\\"34\\\"|KEY_COOLDOWN_S: \\\"36\\\"|" docker-compose.yml'

# 2. 重建容器
ssh HM2 'cd /opt/cc-infra && docker compose up -d --no-deps --force-recreate hm40006'
# → Container hm40006 Recreated → Started

# 3. 验证
docker exec hm40006 env | grep KEY_COOLDOWN_S   # → 36 ✅
docker ps --filter name=hm40006                   # → Up (healthy) ✅
pgrep -a mihomo                                   # → 2008535 running ✅
```

## ✅ 验证结果

| 检查项 | 结果 |
|--------|------|
| KEY_COOLDOWN_S=36 (容器内) | ✅ |
| 容器 Up (healthy) | ✅ |
| mihomo 运行 (PID 2008535) | ✅ |
| 无service/process/network改动 | ✅ |

## 📈 预期效果

| 指标 | Before (34) | After (36) | 变化 |
|------|------------|------------|------|
| KEY_COOLDOWN_S | 34s | 36s | +2s |
| Gap to GLOBAL=45s | 11s | 9s | -2s |
| Wasted 429s (期望) | 871/30min | ~700/30min | -171 (-20%) |
| 5-key cycle cost (理论) | 5×44.5=222.5s | 5×46.5=232.5s | +10s (噪声) |
| 30-min成功率 | 99.86% | 99.86%+ | 保持/提升 |

**影响**: 键恢复时间+2s → 减少在NV API 429窗口未清时的过早重试。预期429浪费从871降至~700 (20%减)。2 ATE应降至0 (键冷却更长时间=更少all-tiers失败)。

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记