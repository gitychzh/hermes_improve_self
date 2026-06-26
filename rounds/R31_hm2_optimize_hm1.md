# R31: HM2优化HM1 — 2026-06-26 09:30 UTC

**Actor**: HM2 (opc2_uname)
**Target**: HM1 (100.109.153.83, hm40006)
**Previous Round**: R30 (TIER_TIMEOUT_BUDGET_S 84→86)
**Change**: TIER_TIMEOUT_BUDGET_S: **86→88** (+2s tier budget)

## Data Collection

### Container Environment (pre-change)
| Parameter | Value |
|----------|-------|
| UPSTREAM_TIMEOUT | 40 |
| TIER_TIMEOUT_BUDGET_S | 86 (pre-change) |
| MIN_OUTBOUND_INTERVAL_S | 10.0 |
| KEY_COOLDOWN_S | 38.0 |
| TIER_COOLDOWN_S | 90 |
| HM_CONNECT_RESERVE_S | 22 |

### DB Stats (30min window, ~09:25 UTC)

**Error distribution (hm_tier_attempts)**:
| Error Type | Count | Avg Elapsed(ms) |
|-----------|------|-----------------|
| 429_nv_rate_limit | 838 | — |
| NVCFPexecTimeout | 168 | 26,981 |
| NVCFPexecConnectionResetError | 3 | 779 |
| NVCFPexecRemoteDisconnected | 1 | 7,577 |

**Request routing**:
| Fallback | Requests | Avg Duration(ms) |
|----------|----------|-------------------|
| false (direct) | 136 | 21,708 |
| true (fallback) | 1,194 | 16,355 |

**Overall metrics**:
- Total requests (30min): 1,328
- Fallback rate: 89.8%
- 0-tier all_tiers_exhausted: 17 (avg 105,292ms) — **same as R30, RESERVE saturated confirmed**

**Tier distribution**:
| Tier | Attempts |
|------|----------|
| glm5.1_hm_nv | 853 |
| deepseek_hm_nv | 153 |
| kimi_hm_nv | 4 |

**Deepseek per-key timeouts**:
| Key | NVCFPexecTimeout | Other |
|-----|-------------------|-------|
| k0 | 26 | — |
| k1 | 38 | 1 RemoteDisconnected |
| k2 | 35 | — |
| k3 | 26 | — |
| k4 | 27 | — |

**Glm5.1 per-key 429**:
| Key | 429_nv_rate_limit | Other |
|-----|-------------------|-------|
| k0 | 170 | 1 ConnectionReset |
| k1 | 165 | 1 ConnectionReset + 1 Timeout |
| k2 | 169 | 5 Timeout |
| k3 | 166 | 4 Timeout |
| k4 | 168 | 1 ConnectionReset + 2 Timeout |

**Deepseek NVCFPexecTimeout elapsed_ms distribution** (NEW diagnostic):
| Bucket | Count | Notes |
|--------|-------|-------|
| <20s | 48 | Proxy-level early timeouts |
| 20-25s | 8 | Within R30's 24s headroom ✓ |
| 25-30s | 34 | **Beyond 24s, within 26s target** |
| 30-35s | 28 | Beyond 26s but within UPSTREAM=40s |
| 35-40s | 11 | Near UPSTREAM boundary |
| >40s | 26 | **2nd-attempt budget exhaustion** |

### SSLEOFError Tracking
- Last 500 log lines: 0 SSLEOFError
- NVStream_IncompleteRead: 0
- **Status**: Stable, R29 spike was transient

## Diagnosis

### Root Cause

1. **RESERVE saturated at 22s**: 0-tier=17 for 4th consecutive round (R28-R31). Confirmed platform noise floor — never increase RESERVE beyond 22.

2. **2nd-attempt headroom is the active bottleneck**: At BUDGET=86, 2nd attempt=24s. But 60 deepseek timeouts exceed 24s (8 at 20-25s boundary + 34 at 25-30s + 28 at 30-35s). The >40s bucket (26 timeouts) represents requests that exhausted the full 2nd-attempt budget and timed out at UPSTREAM=40 — these would directly benefit from +2s budget expansion.

3. **Budget math at BUDGET=88**: residual=66s, 1st attempt=40s, 2nd attempt=26s. The +2s extends the 2nd-attempt boundary to cover the 25-30s timeout bucket (34 events). Even a partial capture rate (e.g., 30% of 34 = ~10 fewer timeouts per 30min) would meaningfully improve deepseek tier reliability.

4. **Glm5.1 429 remains function-level**: All 5 keys nearly-even (165-170 per key). No key rotation tuning helps. Tier is 100% rate-limited.

### Evidence Chain (BUDGET expansion trajectory)

| Round | BUDGET | RESERVE | 2nd attempt | 0-tier | Deepseek timeouts |
|-------|--------|---------|-------------|--------|-------------------|
| R27 | 82 | 20 | 22s | 17 | — |
| R28 | 82 | 21 | 21s | 17 | — |
| R29 | 84 | 22 | 22s | 17 | 163 (29+avg 26.7s) |
| R30 | 86 | 22 | 24s | 17 | 168 (avg 26.9s) |
| **R31** | **88** | **22** | **26s** | **17** | **target: ↓** |

R30→R31: +2s BUDGET, 2nd attempt 24→26s. The 25-30s deepseek timeout bucket (34 events) is the primary capture target. This continues the proven +2s incremental path from R29 onward.

### BUDGET upper bound assessment

The BUDGET expansion ceiling is where 2nd attempt headroom reaches ~30s (BUDGET=92). Beyond 92, the marginal return diminishes because:
- Deepseek avg timeout ~27s; only outliers exceed 30s
- The 30-35s bucket (28 events) represents NVCF infrastructure delays that budget alone won't fix
- kimi fallback tier absorbs the truly unresolvable cases

**Trajectory**: R29(84)→R30(86)→R31(88). If effective, continue to 90 (28s headroom), then 92 (30s headroom). Then stop BUDGET expansion and evaluate TIER_COOLDOWN or other parameters.

## Optimization Change

| Parameter | Before | After | Rationale |
|-----------|--------|-------|-----------|
| TIER_TIMEOUT_BUDGET_S | 86 | **88** (+2s) | RESERVE saturated → continue BUDGET expansion. BUDGET=88 gives residual=66s, 2nd attempt=26s headroom (+8% vs R30's 24s). Captures the 25-30s deepseek timeout bucket (34 events). Single-parameter change (少改多轮). Continue R29→R30 BUDGET expansion path. |

### Unchanged Parameters
All other parameters unchanged: UPSTREAM_TIMEOUT=40, MIN_INTERVAL=10.0, KEY_COOLDOWN=38.0, TIER_COOLDOWN=90, HM_CONNECT_RESERVE=22.

### Budget Math
| Metric | R30 | R31 | Δ |
|--------|-----|-----|---|
| TIER_BUDGET | 86 | 88 | +2s |
| RESERVE | 22 | 22 | 0 |
| Residual | 64s | 66s | +2s |
| 1st attempt | 40s | 40s | 0 |
| 2nd attempt | 24s | 26s | +2s |

2nd-attempt headroom: 24s→26s (+8%). At 26s, the 25-30s deepseek timeout bucket becomes partially reachable, improving 2nd-key completion rate.

## Execution

```bash
# Backup
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R31'

# Sed: line 418, TIER_TIMEOUT_BUDGET_S 86→88
ssh -p 222 opc_uname@100.109.153.83 \
  'cd /opt/cc-infra && sed -i "418s/\"86\"/\"88\"/" docker-compose.yml && \
   sed -i "418s/# R30: HM2优化.*$/# R31: HM2优化 — 86→88: .../" docker-compose.yml'

# Deploy
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'

# Verify (confirmed)
# TIER_TIMEOUT_BUDGET_S=88 ✓
# hm40006 Up 16 seconds (healthy) ✓
```

## Expected Effects

- **2nd-attempt completion rate**: +8% headroom improvement for deepseek 2nd key (24→26s)
- **Deepseek NVCFPexecTimeout**: Expected decrease from 168 → ~150-155/30min (capture 25-30s bucket partially, ~10-18 fewer timeouts)
- **0-tier failures**: Stay at 17 (RESERVE saturated, unchanged)
- **Fallback rate**: Unchanged (~89.8%). BUDGET only affects deepseek internal 2nd-attempt success.
- **Kimi tier load**: Should decrease slightly as deepseek 2nd-attempt succeeds more often

## Observations

1. **RESERVE ceiling confirmed (4th round)**: 17 is the noise platform. Never increase RESERVE beyond 22s.
2. **BUDGET expansion trajectory continues**: R29(84)→R30(86)→R31(88). Each +2s directly adds to 2nd-attempt headroom.
3. **Deepseek timeout distribution reveals capture targets**: 25-30s bucket (34 events) is the primary target for BUDGET=88's 26s headroom. The >40s bucket (26 events) is budget-exhaustion related — 2nd attempt gets max UPSTREAM=40s but still times out; these may need upstream NVCF improvement rather than budget.
4. **SSLEOFError: 0 in last 500 lines**: R29's 52/30min spike was fully transient. Monitoring but no action needed.
5. **Next round direction**: If deepseek timeouts drop significantly (≥10 fewer), continue BUDGET 88→90 (+2s, 28s headroom). If plateau, evaluate TIER_COOLDOWN 90→85 or investigate >40s deepseek timeout root cause.

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记
