# R259: HM1→HM2 — TIER_TIMEOUT_BUDGET_S 115→120 (+5s) — 单轮优化

**回合类型**: 优化 (单参数小增量)
**方向**: HM1 (opc_uname) → HM2 (opc2_uname)
**时间**: 2026-06-28 23:09–23:11 UTC
**角色**: HM1 — 优化者, 仅修改HM2配置
**变更参数**: `TIER_TIMEOUT_BUDGET_S` 115 → 120 (+5s)
**无变更参数**: KEY_COOLDOWN_S=38, TIER_COOLDOWN_S=45, UPSTREAM_TIMEOUT=63, MIN_OUTBOUND_INTERVAL_S=15.6, HM_CONNECT_RESERVE_S=24 — 全6参数不变

## 📊 数据采集 (2026-06-28 23:08–23:11 UTC, 3min burst)

### Config Snapshot (HM2 — docker exec hm40006 env, PRE-CHANGE)
| Parameter | Value |
|-----------|-------|
| KEY_COOLDOWN_S | 38 |
| TIER_COOLDOWN_S | 45 |
| UPSTREAM_TIMEOUT | 63 |
| MIN_OUTBOUND_INTERVAL_S | 15.6 |
| **TIER_TIMEOUT_BUDGET_S** | **115** (→ 120) |
| HM_CONNECT_RESERVE_S | 24 |
| PROXY_TIMEOUT | 300 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 |
| HM_DEFAULT_NV_MODEL | deepseek_hm_nv |
| HM_NV_MODEL_TIERS | ["deepseek_hm_nv", "glm5.1_hm_nv", "kimi_hm_nv"] |

### DB 30min Summary Metrics
| Metric | Value |
|--------|-------|
| 总请求数 | 1,302 |
| 成功 (200) | 1,295 (99.54%) |
| 失败 | 7 (6 ATE + 1 NVStream) |
| 平均延迟 | 22,293ms |
| P50 | 17,858ms (17.9s) |
| P95 | 52,190ms (52.2s) |
| P90 (deepseek) | 41,012ms |

### 24h Window Baseline
| Metric | Value |
|--------|-------|
| 总请求 | 5,288 |
| 成功 | 5,260 (99.47%) |
| 错误 | 28 (25 ATE + 2 NVStream + 1 NVStream_Timeout) |
| SSLEOF (tier_attempts) | 511 |
| NVCFPexecTimeout (tier_attempts) | 52 |

### 6h Window Baseline
| Metric | Value |
|--------|-------|
| 总请求 | 2,042 |
| 成功 | 2,026 (99.26%) |
| 错误 | 16 (14 ATE + 1 NVStream + 1 NVStream_Timeout) |
| Tier attempt 429_nv_rate_limit | 911 |
| SSLEOF (tier_attempts) | 174 |
| NVCFPexecTimeout (tier_attempts) | 27 |


## 📊 3-Minute Burst (23:08–23:11 UTC) — Budget Break Analysis

### Budget Break Events (last 10, all HM2 side)
| Time | Tier | Budget | Remaining | Status |
|------|------|--------|------------|--------|
| 23:08:58 | deepseek | 115s | 2.7s | BELOW 10s threshold |
| 23:09:00 | deepseek | 115s | 8.2s | BELOW 10s threshold |
| 23:10:50 | glm5.1 | 115s | 5.6s | BELOW 10s threshold |
| 23:11:06 | deepseek | 115s | 2.2s | BELOW 10s threshold |

4 budget breaks in 3 minutes — all below 10s minimum threshold. Time-localized burst, not scattered.

### Deepseek Tier Failure Detail (error_detail JSONL, 23:08-23:11)
| Entry | Tier | elapsed_ms | budget_remaining |
|-------|------|------------|------------------|
| 1 | deepseek | 107,251ms | 115-107=8s |
| 2 | deepseek | 106,586ms | 115-106=9s |
| 3 | deepseek | 106,370ms | 115-106=9s |
| 4 | deepseek | 106,428ms | 115-106=9s |
| 5 | deepseek | 107,430ms | 115-107=8s |
| 6 | deepseek | 106,712ms | 115-106=9s |
| 7 | deepseek | 113,214ms | 115-113=2s |
| 8 | deepseek | 112,797ms | 115-112=3s |
| 9 | deepseek | 112,865ms | 115-112=3s |
| 10 | deepseek | 105,331ms | 115-105=10s (at threshold) |
| 11 | deepseek | 113,604ms | 115-113=2s |
| 12 | deepseek | 106,850ms | 115-106=9s |

**Pattern**: 9/12 entries have remaining budget below 10s (range 2–9s). Only 1 entry at exactly 10s (threshold). The deepseek tier takes 105–113s total for all 5 keys to complete their attempts. With budget=115s, the remaining budget is consistently 2–10s, frequently below the 10s minimum threshold.

### Error Cause Analysis
- **NVCFPexecTimeout**: All deepseek tier failures are from NVCFPexecTimeout — the NV API pexec function times out at ~10s per key. With 5 keys and SSLEOF retries, total cycle = 105–113s.
- **SSLEOF**: 174 SSLEOF errors in 6h tier_attempts on deepseek tier — SSL connection drops from NV API server. Each SSLEOF triggers a 2s backoff + retry, adding to total elapsed time.
- **429_nv_rate_limit**: 911 × 429 in 6h tier_attempts — NV API function-level rate limiting. These 429s are at the function level (all keys simultaneously rate-limited), not per-key. The current `KEY_COOLDOWN_S=38` and `MIN_OUTBOUND_INTERVAL_S=15.6` provide sufficient spacing; the 429s are from NV API server-side behavior, not config gaps.


## 📋 分析

### Key Findings

1. **99.54% user-facing success rate** — 7 errors in 30min (6 ATE + 1 NVStream). Above 99% no-change threshold. But the rate is declining from R258's 99.69%.

2. **4 budget breaks in 3 minutes** (23:08–23:11): All below 10s minimum threshold. Time-localized burst, not scattered.

3. **Deepseek tier dominant**: 99.5% of traffic. Takes 105–113s total for 5 keys to exhaust. SSLEOF retries add latency.

4. **Glm5.1 tier peripheral**: 4 requests in 30min, all 429 at function level. Not a key-level imbalance.

5. **Kimi dead key**: num_attempts=0 over 12h — kimi tier never used, serves only as last-resort fallback.

6. **All 6 other parameters at validated convergence**: KEY_COOLDOWN_S=38, TIER_COOLDOWN_S=45, UPSTREAM_TIMEOUT=63, MIN_OUTBOUND_INTERVAL_S=15.6, HM_CONNECT_RESERVE_S=24. Only TIER_TIMEOUT_BUDGET_S needs adjustment.

### Why TIER_TIMEOUT_BUDGET_S +5s (not other params)

- **KEY_COOLDOWN_S=38**: 429_nv_rate_limit is function-level (all keys simultaneously rate-limited), not per-key. Increasing KEY_COOLDOWN_S would not reduce function-level 429 count.
- **TIER_COOLDOWN_S=45**: At GLOBAL_COOLDOWN=45s convergence. No tier-level gap to close.
- **UPSTREAM_TIMEOUT=63**: Individual key attempts timeout at 10–11s (NVCFPexecTimeout at pexec level), well within 63s ceiling. Not the bottleneck.
- **MIN_OUTBOUND_INTERVAL_S=15.6**: 5 × 15.6 = 78s cycle vs GLOBAL=45s, buffer=33s. Already large safety margin.
- **HM_CONNECT_RESERVE_S=24**: Converged with HM1=24s (gap=0). SSLEOF errors are server-side NV API behavior; increasing client-side reserve doesn't fix server drops.

### Decision Rationale

**Budget breaks at 115s**: The deepseek tier takes 105–113s for all 5 keys. At 115s budget:
- 105s total → 115-105=10s remaining (at threshold)
- 113s total → 115-113=2s remaining (well below threshold)

The +5s change to 120s:
- 105s total → 120-105=15s remaining (crosses 10s threshold, +5s improvement)
- 113s total → 120-113=7s remaining (below 10s but +5s from 2s)
- Average improvement: +5s per deepseek tier failure

The 4 budget breaks in 3 minutes demonstrate the 115s budget is too tight for the current deepseek tier behavior. +5s gives one more key chance before budget exhaustion.

**少改多轮 (单参数)**: Only TIER_TIMEOUT_BUDGET_S changed. All other 6 parameters unchanged. Single-parameter adjustment, small increment (+5s).

**Budget Break Decision Reference** (from R258): Budget breaks scattered 24h, not time-localized. But NOW (23:08-23:11) the burst shows 4 breaks in 3 minutes — time-localized cluster. This changes the decision from "no-change" to "need-change".


## 🎯 执行: TIER_TIMEOUT_BUDGET_S 115 → 120 (+5s)

**变更内容**: 在 HM2 的 docker-compose.yml 第 477 行，将 `TIER_TIMEOUT_BUDGET_S` 从 115 改为 120。

**执行步骤**:
1. `sed -i '477s|TIER_TIMEOUT_BUDGET_S: "115"|TIER_TIMEOUT_BUDGET_S: "120"|' docker-compose.yml`
2. `docker compose up -d --no-deps --force-recreate hm40006`
3. 验证: `docker exec hm40006 env | grep TIER_TIMEOUT_BUDGET_S` → 120 ✅
4. 验证: `curl -s localhost:40006/health` → 200 ✅
5. 验证: `pgrep -a mihomo` → PID 2008535 (running, untouched) ✅
6. 验证: 全6个其他参数不变 ✅

**Expected Impact**:
- Budget breaks at 120s budget: deepseek 105-113s total → remaining 7-15s
- Cross 10s threshold for most deepseek tier failures (105-110s range)
- Still below 10s for 113s+ cases (7s remaining) — but improved by +5s
- 3-minute burst pattern may recur, but with +5s more headroom per tier cycle


## 📈 Convergence Check (7 parameters)

| Parameter | HM1 Value | HM2 Value (now) | Gap | Status |
|-----------|-----------|-----------------|-----|--------|
| KEY_COOLDOWN_S | 38 | 38 | 0 | ✅ converged |
| TIER_COOLDOWN_S | 45 | 45 | 0 | ✅ converged |
| UPSTREAM_TIMEOUT | 63 | 63 | 0 | ✅ converged |
| MIN_OUTBOUND_INTERVAL_S | 15.6 | 15.6 | 0 | ✅ converged |
| **TIER_TIMEOUT_BUDGET_S** | **115** | **120** | **+5** | ⚠️ updated (was 0) |
| HM_CONNECT_RESERVE_S | 24 | 24 | 0 | ✅ converged |
| PROXY_TIMEOUT | 300 | 300 | 0 | ✅ converged |

6/7 parameters fully converged (gap=0). Only `TIER_TIMEOUT_BUDGET_S` with a +5s gap toward HM2 side (HM1 needs to catch up in next round).


## 🏁 回合完成

**铁律验证**: ✅ 仅修改HM2配置 (docker-compose.yml line 477). HM1本地配置未触碰. mihomo从未停止/重启/kill (PID 2008535 running continuously).

**优化**: 单参数小增量 — TIER_TIMEOUT_BUDGET_S 115→120 (+5s). 所有其他6参数不变. 少改多轮 — 积累式优化.

**Next round**: HM2 (opc2_uname) → HM1 (opc_uname) — R260. HM2 needs to match TIER_TIMEOUT_BUDGET_S=120 on HM1 side.

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记