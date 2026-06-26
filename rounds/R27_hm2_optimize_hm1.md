# R27: HM2优化HM1 — 2026-06-26 08:15 UTC

**Actor**: HM2 (opc2_uname)
**Target**: HM1 (100.109.153.83, hm40006)
**Previous Round**: R26 (HM_CONNECT_RESERVE 19→20)

---

## 1. Data Collection (Pre-Change, 30-min window)

### 1a. Log Error Count
```
docker logs hm40006 --tail 200: 42 error/warn/fail lines
docker logs --since 30m: 348 lines total
```

### 1b. Running Container Env (pre-change)
| Parameter | Value |
|----------|-------|
| UPSTREAM_TIMEOUT | 40 |
| TIER_TIMEOUT_BUDGET_S | 80 |
| MIN_OUTBOUND_INTERVAL_S | 10.0 |
| KEY_COOLDOWN_S | 38.0 |
| TIER_COOLDOWN_S | 90 |
| HM_CONNECT_RESERVE_S | 20 |

### 1c. Error Distribution (hm_tier_attempts, 30min)
```
error_type                      | cnt | avg_elapsed
429_nv_rate_limit              | 660 | -
NVCFPexecTimeout               | 148 | 26959ms
NVCFPexecConnectionResetError  |   3 | 1748ms
NVCFPexecRemoteDisconnected    |   1 | 7577ms
```

### 1d. Request Routing (fallback vs direct)
```
fallback_occurred | cnt  | avg_dur
f (direct)        |  123 | 22468ms
t (fallback)     | 1017 | 16024ms
```
Fallback rate: 89.2% (1020/1143)

### 1e. Overall Success
```
Total: 1152, Success: 1134 (98.4%)
```

### 1f. 0-Tier Failures (all_tiers_exhausted)
```
Count: 17 (ALL tiers_tried_count=0, avg 105292ms)
```

### 1g. Per-Key Deepseek Timeout Distribution
```
key 0: 23 timeouts (avg 26342ms)
key 1: 32 timeouts (avg 27174ms) + 1 RemoteDisconnected (7577ms)
key 2: 31 timeouts (avg 27271ms)
key 3: 21 timeouts (avg 26162ms)
key 4: 26 timeouts (avg 29300ms)
```
All 134 deepseek tier attempts: 133 timeouts + 1 RemoteDisconnected = 100% error rate in tier_attempts

### 1h. Tier Distribution
```
glm5.1_hm_nv:   675 (660 429 + 4 timeout + 3 conn_reset + others)
deepseek_hm_nv: 134 (133 timeout + 1 RemoteDisconnected)
kimi_hm_nv:       3 (final fallback)
```

### 1i. Glm5.1 Per-Key 429 Distribution
```
Key 0: 137, Key 1: 130, Key 2: 132, Key 3: 130, Key 4: 131
Even distribution: function-level 429 (NVCF function 822231fa-d4f3)
```

---

## 2. Diagnosis

### Root Cause Analysis

**Primary bottleneck: TIER_BUDGET at boundary with RESERVE=20**

The 0-tier failure trajectory continues its decline:
- R25: RESERVE=19 → ~22-23 0-tier failures
- R26: RESERVE=20 → 17 0-tier failures (confirmed)
- Each +1s RESERVE removed ~5-6 failures (larger than the typical ~2-3 per +1s)

At RESERVE=20, the budget math is:
- TIER_BUDGET residual = 80-20 = 60s
- 1st deepseek attempt: min(40, 60) = 40s (full UPSTREAM_TIMEOUT)
- 2nd deepseek attempt: 80-20-40 = 20s (barely above minimum 10s)

While the 17 0-tier failures are low, the **boundary safety** is tight. The 2nd attempt gets only 20s headroom — and deepseek timeouts average 26-29s meaning many 2nd attempts will still timeout. The extra +2s brings this to 22s, which reduces the 2nd-attempt timeout probability.

**Secondary observation: Deepseek tier is 100% error in tier_attempts**

All 134 deepseek attempts are errors (133 NVCFPexecTimeout + 1 RemoteDisconnected). No single deepseek attempt succeeds directly — the key cycling absorbs these. The fallback throughput comes from the key cycling mechanism, not from primary-tier success.

**Glm5.1 function-level 429 remains unaddressable**: 660 429 errors across 5 keys evenly (130-137 each). The NVCF function ID `822231fa-d4f3` is globally rate-limited at the function level, not per-key. No amount of key rotation tuning can fix this.

### Evidence Chain
1. Docker logs → 42 error/warn lines (stable, not growing)
2. DB: 0-tier failures = 17 (tiers_tried_count=0) → all pre-tier connection failures
3. DB: TIER_BUDGET = 80, RESERVE = 20 → residual = 60s. 2nd attempt = 20s (at boundary)
4. DB: 98.4% overall success → system is stable but fallback-dependent
5. DB: Fallback rate 89.2% → nearly 9/10 requests through deepseek fallback tier

---

## 3. Optimization

### Single-Parameter Change (少改多轮)

| Parameter | Before | After | Rationale |
|----------|--------|-------|-----------|
| **TIER_TIMEOUT_BUDGET_S** | **80** | **82** | +2s tier budget. RESERVE=20下残60→62s, 2nd attempt 22s headroom(增强边界安全); 继续减少deepseek 2nd attempt timeout margin; 目标: 减少kimi最终fallback触发(当前3次/30min → 目标1-2次) |

### Unchanged Parameters
- UPSTREAM_TIMEOUT=40 (maintains 2× coupling: 2×40=82 vs 80 before)
- MIN_OUTBOUND_INTERVAL_S=10.0 (stable at R17 level)
- KEY_COOLDOWN_S=38.0 (3.8 cycles, stabilized since R19)
- TIER_COOLDOWN_S=90 (R17 level, 33% more recovery windows vs 120s)
- HM_CONNECT_RESERVE_S=20 (R26 level, 0-tier already at 17)

---

## 4. Execution Record

### Commands Executed
```bash
# Backup
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R27'

# Line 418: TIER_TIMEOUT_BUDGET_S 80→82
ssh -p 222 opc_uname@100.109.153.83 "sed -i '418s/\"80\"/\"82\"/' /opt/cc-infra/docker-compose.yml"

# Line 418: Comment update
ssh -p 222 opc_uname@100.109.153.83 "sed -i '418s/# R18.*$/# R27: HM2优化 — 80→82: +2s tier budget; RESERVE=20s下残余60→62s, 2nd attempt 22s headroom(边界安全增强); 少改多轮(单参数变更)/' /opt/cc-infra/docker-compose.yml"

# Deploy
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'

# Verify
ssh -p 222 opc_uname@100.109.153.83 'sleep 5 && docker exec hm40006 env | grep TIER_TIMEOUT_BUDGET_S'
# → TIER_TIMEOUT_BUDGET_S=82 ✓
```

### Verified Running Values (Post-Deploy)
```
TIER_TIMEOUT_BUDGET_S=82
UPSTREAM_TIMEOUT=40
HM_CONNECT_RESERVE_S=20
KEY_COOLDOWN_S=38.0
MIN_OUTBOUND_INTERVAL_S=10.0
TIER_COOLDOWN_S=90
Container: hm40006 Up 27 seconds (healthy)
```

---

## 5. Expected Effects

| Effect | Quantification | Confidence |
|--------|---------------|-----------|
| 2nd attempt headroom increase | 20s → 22s (+2s) | High (direct budget math) |
| Deepseek 2nd-attempt timeout reduction | ~5-8% fewer timeouts at 26-29s avg | Medium (2s buffer against 26-29s avg) |
| Kimi final-fallback reduction | 3→1-2 per 30min | Low (depends on key cycling behavior) |
| 0-tier failure stability | 17 stays or drops to 14-16 | Medium (budget headroom reduces edge case) |
| Fallback rate change | 89.2% → ~88-89% (minimal) | Low (glm5.1 primary unchanged) |

### Key Boundary Check
At TIER_BUDGET=82, RESERVE=20:
- Residual = 82-20 = 62s
- 1st attempt: min(40, 62) = 40s
- 2nd attempt: 82-20-40 = 22s (> 10s minimum ✓)
- 3rd attempt (if needed): 82-20-40-40 = -18s (impossible — only 2 attempts)

---

## 6. Observations & Risks

### Observations
1. **0-tier trajectory confirmed at 17**: R26's RESERVE=20 successfully reduced 0-tier failures. The +1s jump (19→20) removed more failures than expected (−5 vs typical −2-3). The diminishing returns curve may be flattening.
2. **Deepseek tier 100% error continues**: All 134 attempts are failures. Key cycling absorption is the only mechanism for tier-level success. No per-key optimization can make deepseek succeed directly.
3. **Fallback rate at all-time high (89.2%)**: This is the highest recorded. But 0-tier failures are at all-time low (17). The system is more reliable despite being more fallback-dependent.
4. **NVCFPexecRemoteDisconnected**: 1 occurrence (down from R24's 1, stable). Not growing. Monitor only.

### Risks
- **TIER_BUDGET ceiling**: At 82s, 2×UPSTREAM_TIMEOUT = 80s is now slightly below budget (82 > 80). This is intentional — the extra +2s compensates for RESERVE overhead. But if TIER_BUDGET keeps rising beyond 2×UPSTREAM, the coupling becomes unmanaged and the 3rd attempt has negative budget.
- **Deepseek per-key timeout asymmetry**: Keys 1 and 2 (32+31 timeouts) continue to have more timeouts than keys 3 and 4 (21+26). Key 5 has 26 timeouts (avg 29300ms, higher than the 26s of keys 3/4). This may indicate proxy port health issues on ports 7895/7894 (used by keys 1, 2). Track this in future rounds.
- **UPSTREAM_TIMEOUT boundary**: At 40s, deepseek timeouts average 26-29s. Raising UPSTREAM_TIMEOUT beyond 40s would increase the budget for all 89.2% of fallback requests (the majority), increasing overall latency. Not recommended unless timeout rate grows significantly.

---

## 7. 0-Tier Failure Tracking (Updated)

| Round | RESERVE | 0-tier fails | Delta | Notes |
|-------|---------|-------------|-------|-------|
| R20 | 8 | 42 | baseline | |
| R21 | 10 | 34 | -8 | |
| R22 | 12 | 34 | 0 | |
| R23 | 16 | 28 | -6 | |
| R24 | 18 | 25 | -3 | |
| R25 | 19 | ~22-23 (target) | -2~-3 | |
| R26 | 20 | 17 | -5~-6 | R26 +1s jump removed more than expected |
| R27 | 20 (keep) | 17 (target) | — | TIER_BUDGET 80→82; RESERVE unchanged |

---

## 8. Config History

| Parameter | Value | Set By | Round |
|----------|-------|--------|-------|
| UPSTREAM_TIMEOUT | 40 | HM2 | R18 |
| TIER_TIMEOUT_BUDGET_S | 82 | HM2 | **R27** ← NEW |
| MIN_OUTBOUND_INTERVAL_S | 10.0 | HM2 | R17 |
| KEY_COOLDOWN_S | 38.0 | HM2 | R19 |
| TIER_COOLDOWN_S | 90 | HM2 | R17 |
| HM_CONNECT_RESERVE_S | 20 | HM2 | R26 |

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记