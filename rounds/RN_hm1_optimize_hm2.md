# RN: HM1→HM2 — Round 86 (2026-06-27 18:28 CST)

**角色**: HM1 (opc_uname) 优化 HM2 (opc2_uname)
**变更**: `MIN_OUTBOUND_INTERVAL_S`: 9.0 → 8.0 (-1s inter-request spacing)
**时间**: 2026-06-27 18:28 CST
**原则**: 少改多轮(单参数); 铁律:只改HM2不改HM1; 绝不碰mihomo

---

## 📊 数据收集 (30-min window, PostgreSQL hermes_logs)

### 30-Minute Summary (18:00–18:28 CST, post-R85)

| status | cnt | avg_ms | min_ms | max_ms | fallback_cnt | err_cnt | total_429s |
|--------|-----|--------|--------|--------|--------------|---------|------------|
| 200 | 122 | 21657 | 3852 | 71034 | 121 | 0 | 144 |
| 502 | 1 | 125924 | 125924 | 125924 | 0 | 1 | 0 |

**Success rate: 99.2%** (122/123) ⬆ from R84's 97.4%/R85's ~97.5%

### Tier Breakdown

| tier_model | cnt | avg_ms | fallback_cnt | total_429s |
|------------|-----|--------|--------------|------------|
| deepseek_hm_nv | 121 | 21750 | 121 | 144 |
| glm5.1_hm_nv | 1 | 10506 | 0 | 1 |
| (null) | 1 | 125924 | 0 | 0 |

### Error Breakdown

| error_type | error_subcategory | cnt | avg_ms |
|------------|-------------------|-----|--------|
| all_tiers_exhausted | (none) | 1 | 125924 |

### Recent 10 Requests (Latency Snapshot)

All 10: start_tier=glm5.1_hm_nv → fallback → deepseek_hm_nv
Duration_ms: 3852, 7501, 7692, 7884, 9467, 9791, 10336, 11420, 12124, 20795
Median: ~9,629ms. All successful via deepseek fallback.

**⚠ Compared to R85 baseline (median ~16,987ms): median dropped by ~7,358ms (43% reduction)**

### HM2 Current Config (post-R85 → R86 target)

```
KEY_COOLDOWN_S=37.0
TIER_COOLDOWN_S=43
UPSTREAM_TIMEOUT=71
MIN_OUTBOUND_INTERVAL_S=9.0    ← 本次优化目标
TIER_TIMEOUT_BUDGET_S=125
HM_CONNECT_RESERVE_S=12
PROXY_TIMEOUT=300
```

### RR Counter State

- deepseek: 4330 (91.7% of all requests)
- kimi: 126 (2.7%)
- glm5.1: 3825 (5.6%, but 100% fallback)

### Live Log Analysis (18:26-18:28)

Key pattern: glm5.1 tier cycle completes in 4-6s (4,389ms–5,990ms elapsed). All 5 keys hit 429 in ~1s each. GLOBAL-COOLDOWN=45s blocks further attempts. Deepseek handles everything successfully.

Tier-FAIL cycle examples:
- `elapsed=4389ms` — all 5 keys 429, 5×~0.9s spacing
- `elapsed=5990ms` — all 5 keys 429, 5×~1.2s spacing

No SSLEOFError, no ConnectionResetError, no NVCFPexecTimeout in this window. Pure 429 dominance.

---

## 🔍 分析

### 关键发现

1. **R85 效果显著**: `all_tiers_exhausted` 从 28 (R84) → 1 (R86 窗口), 减少 96.4%。成功率从 97.4% → 99.2%。TIER_TIMEOUT_BUDGET_S=125s 给予 deepseek 的 7 键完整循环足够空间, 不再因预算耗尽而过早放弃键。

2. **glm5.1 层 100% 回退率保持**: 唯一 1 个成功请求也走了 fallback (fallback_occurred=true)。NVCF 函数级速率限制(per function_id `822231fa-...`) 使所有 5 个 NV 键在 ~1s 内均命中 429。

3. **deepseek 是绝对主力**: 121/123=98.4% 的请求由 deepseek 层处理。平均延迟 21,750ms, 中位数 ~9,629ms。7 键 (NVCF pexec) 全部正常工作, 无 SSLEOFError/ConnectionReset。

4. **GLOBAL-COOLDOWN 是瓶颈**: glm5.1 层循环完成仅需 4-6s。所有 5 键在 ~1s 内命中 429 后, GLOBAL-COOLDOWN=45s 硬编码阻止所有进一步尝试。瓶颈不是 TIER_BUDGET(125s 远超 6s), 而是硬编码的 45s 全局冷却。

5. **MIN_OUTBOUND_INTERVAL_S=9.0 的 R84 对齐达成**: 5 键 × 9s = 45s = GLOBAL-COOLDOWN 精确对齐。但实际键循环仅 ~1s 每键, 9s 间隔浪费了 8s 每键的等待时间。进一步减少至 8s 使 5×8=40s < 45s, 仍留 5s 余量, 但更快触发 fallback。

6. **all_tiers_exhausted 降至 1**: 仅 1 个请求(0.8%)所有层均失败。平均耗时 125,924ms(125s) — 恰好等于 TIER_TIMEOUT_BUDGET_S=125s。这是预算边界精确触发的证据: 该请求在 deepseek 层尝试了 7 键完整循环但全部超时/失败, 精确在 125s 时被预算切断。

7. **R86 优化方向**: 进一步减少 `MIN_OUTBOUND_INTERVAL_S` 至 8.0s。减少键间等待 → 更快触发 fallback(http 层或下一层)。5 键 × 8.0s = 40s < GLOBAL-COOLDOWN=45s, 仍安全。+1s 减少 → 每个多层周期节省 ~5s。

---

## 🎯 优化计划: MIN_OUTBOUND_INTERVAL_S 9.0 → 8.0 (-1s)

### 选择理由

**为什么选 MIN_OUTBOUND_INTERVAL_S**:
- 当前 9.0s 间隔 = 5 键 × 9s = 45s 对齐 GLOBAL-COOLDOWN=45s。实际键仅需 ~1s 每个, 9s 浪费了 8s/键。
- -1s 至 8.0s: 5×8=40s < 45s GLOBAL, 留 5s 余量, 安全。更快键循环 → 更快检测 429 → 更快触发 deepseek fallback。
- 轨迹: R84 12.0→9.0(-3s)。R86 9.0→8.0(-1s) 继续相同降幅轨迹, 但更保守(仅 -1s vs -3s)。
- 效果: 减少 glm5.1 层循环完成时间(~5s→~4s), 更快触发 deepseek 处理, 减少总请求失败延迟。

**为什么不选其他参数**:
- `KEY_COOLDOWN_S`(37→35): GLOBAL-COOLDOWN=45s 主导所有 429 场景。键级冷却在全局冷却下不生效。-2s 无实际效果。
- `UPSTREAM_TIMEOUT`(71→68): deepseek 延迟中位数 ~9.6s, 最大 71s 仅 1 个请求。减少 -3s 可能切断合法慢请求但影响极小(0.8%请求)。更激进但收益不明确。
- `TIER_TIMEOUT_BUDGET_S`(125→130): 已从 120→125 获得巨大收益(28→1 all_tiers_exhausted)。再加 +5s 边际收益递减。仅 1 个all_tiers_exhausted @125s — 加至 130s 可能捕获此请求但无其他效果。
- `TIER_COOLDOWN_S`(43→40): 全局冷却 45s 主导。层级冷却减少不改变实际冷却时间。
- `HM_CONNECT_RESERVE_S`(12→9): 连接预留减少对 429 模式无影响。deepseek 的 NVCF pexec 连接快速(~1-2s)。

### 预算验证

| 参数 | 当前值 | 新值 | 变更 |
|------|--------|------|------|
| MIN_OUTBOUND_INTERVAL_S | 9.0 | 8.0 | -1s ↓ |
| KEY_COOLDOWN_S | 37.0 | 37.0 | 不变 |
| TIER_COOLDOWN_S | 43 | 43 | 不变 |
| UPSTREAM_TIMEOUT | 71 | 71 | 不变 |
| TIER_TIMEOUT_BUDGET_S | 125 | 125 | 不变 |
| HM_CONNECT_RESERVE_S | 12 | 12 | 不变 |
| PROXY_TIMEOUT | 300 | 300 | 不变 |

**New spacing check**: 5 keys × 8.0s = 40s < GLOBAL-COOLDOWN=45s. Safe alignment: 40s allows all 5 keys to attempt before the global 45s cooldown lifts. The 5s gap gives per-key cooldown time to expire naturally before the next global cycle starts.

---

## ⚙️ 执行

### 1. 修改 docker-compose.yml (Line 479, hm40006 only)

```bash
ssh opc2_uname@100.109.57.26
cd /opt/cc-infra
cp docker-compose.yml docker-compose.yml.bak.r86
sed -i '479s|MIN_OUTBOUND_INTERVAL_S: "9.0"|MIN_OUTBOUND_INTERVAL_S: "8.0"|' docker-compose.yml
# Verify: only line 479 changed; lines 228/279/427 (other services) remain "1.5"
```

### 2. 仅重建 hm40006 容器(不触碰 mihomo)

```bash
docker compose up -d --no-deps --force-recreate hm40006
```

输出: Container hm40006 Recreate → Recreated → Starting → Started ✅

### 3. 验证

```bash
docker exec hm40006 env | grep MIN_OUTBOUND_INTERVAL_S
# → MIN_OUTBOUND_INTERVAL_S=8.0 ✅

docker ps --filter name=hm40006
# → Up 52 seconds (healthy) ✅

ps aux | grep mihomo | grep -v grep
# → opc2_un+ 2008535 ... /home/opc2_uname/.local/bin/mihomo (since Jun24) ✅

curl -s http://localhost:40006/health
# → {"status":"ok", tiers:['glm5.1_hm_nv','deepseek_hm_nv','kimi_hm_nv']} ✅
```

---

## 📈 预期效果

| 指标 | R85 (9.0s) | R86 (8.0s) | 变化 |
|------|-----------|-----------|------|
| 成功率 | 99.2% | ~99.3-99.5% | +0.1-0.3% |
| all_tiers_exhausted | 1/30min (0.8%) | ~0-1/30min | →0 or stable |
| glm5.1 tier cycle | ~5-6s elapsed | ~4-5s elapsed | -1s faster |
| deepseek avg latency | 21,750ms | ~20-22s | slight ↓ or stable |
| 429 total (per 30min) | 144 | ~130-150 | slight ↓ or stable |
| Deepseek fallback trigger | ~5-6s after glm5.1 fail | ~4-5s after glm5.1 fail | -1s earlier |

> **注意**: MIN_OUTBOUND_INTERVAL_S 是键间最小出站间隔, 非请求总延迟限制。减少此值使键循环加速 → 更快检测到 429 并触发 fallback → 减少总请求失败延迟。效果体现在 glm5.1 层循环完成时间减少, 而非 deepseek 层处理延迟改善。Deepseek 层延迟取决于 NVCF pexec 函数执行速度(NVIDIA 基础设施), 不受此参数影响。

> **关键验证**: 5 键 × 8.0s = 40s < GLOBAL-COOLDOWN=45s。此对齐确保所有 5 键的间隔在全局冷却解除前完成, 不会因间隔过大而浪费全局冷却窗口。

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记