# R24: HM2优化HM1 — 2026-06-26 07:24 UTC

**Actor**: HM2 (opc2_uname)
**Target**: HM1 (100.109.153.83, ssh port 222)
**Previous round**: R23 — HM_CONNECT_RESERVE_S 14→16 (+2s, 0-tier ↓31→↓28 — 97.0% success, 82.3% fallback)

---

## 1. Data Collection

### 1.1 Container Environment (docker exec hm40006 env)
All R23 values confirmed running:
- `HM_CONNECT_RESERVE_S=16`
- `UPSTREAM_TIMEOUT=40`
- `TIER_TIMEOUT_BUDGET_S=80`
- `MIN_OUTBOUND_INTERVAL_S=10.0`
- `KEY_COOLDOWN_S=38.0`
- `TIER_COOLDOWN_S=90`

### 1.2 Error Distribution (hm_tier_attempts, 30-min window)

| Error Type | Count | Avg Elapsed (ms) |
|-----------|-------|-----------------|
| 429_nv_rate_limit | 551 | <1 |
| NVCFPexecTimeout | 140 | 27687 |
| NVCFPexecConnectionResetError | 3 | 1748 |
| empty_200 | 2 | - |
| NVCFPexecRemoteDisconnected | 1 | 7577 |

### 1.3 Fallback Rate (hm_requests, 30-min window)

| Metric | Value |
|--------|-------|
| Total requests | 1093 |
| Non-fallback (f) | 185 (avg 22096ms) |
| Fallback (t) | 908 (avg 16896ms) |
| **Fallback rate** | **83.1%** |
| Overall success (200) | 97.5% (1071/1098) |

### 1.4 0-Tier / Pre-Tier Failures (hm_requests, error_type + tiers_tried_count)

| Error Type | tiers_tried_count | Count | Avg Duration (ms) |
|-----------|-------------------|-------|-------------------|
| all_tiers_exhausted | 0 | 28 | 82052 |
| NVStream_IncompleteRead | 2 | 1 | 14898 |

### 1.5 Per-Key 429 Distribution (glm5.1_hm_nv, 5 keys)

| Key Index | 429 Count | Other Errors |
|-----------|----------|-------------|
| k0 | 116 | conn_reset:1 |
| k1 | 108 | conn_reset:2, timeout:2 |
| k2 | 112 | timeout:5 |
| k3 | 109 | timeout:5 |
| k4 | 111 | timeout:3 |

Perfectly even distribution across all 5 keys (103-116 range) — confirms function-level 429 not per-key.

### 1.6 Deepseek Tier Attempts (per-key, errors only)

| Key Index | NVCFPexecTimeout | Other |
|-----------|-----------------|-------|
| k0 | 21 | - |
| k1 | 28 | remote_disconn:1 |
| k2 | 30 | - |
| k3 | 20 | empty_200:1 |
| k4 | 23 | empty_200:1 |

### 1.7 Fallback Success Latency Distribution

| Bucket | Count | % |
|--------|-------|---|
| 0-10s | 420 | 46.2% |
| 10-20s | 313 | 34.3% |
| 20-30s | 68 | 7.5% |
| 30-50s | 51 | 5.6% |
| 50s+ | 63 | 6.9% |

### 1.8 Log Pattern (last 100 lines)
Primary pattern: 100% HM-TIER-SKIP on glm5.1 (TIER_COOLDOWN=90s active). All requests flow: glm5.1 all-keys-cooldown → deepseek fallback → success on first or second deepseek key. Some deepseek timeouts at ~45s on k3 retry followed by k4 success. No new error surge; kimi tier nearly unused (3 attempts total).

---

## 2. Diagnosis

### Root Cause Analysis

**Primary bottleneck**: 0-tier pre-tier connection failures (HM_CONNECT_RESERVE_S related).
- Count: 28 (down from 31 in R23, continuing decline trajectory: 42→37→34→31→28)
- Avg duration: 82052ms — connection setup failing BEFORE any tier key cycling begins
- Each +2s RESERVE increment removes ~3-4 failures

**Secondary pattern**: glm5.1 function-level 429 (551 total, 5 keys evenly distributed 103-116).
- NOT fixable via per-key rotation parameters — NVCF function ID (822231fa) has a global rate cap
- Deepseek tier absorbs all traffic: 122 timeouts across 5 keys, evenly distributed (20-30 per key)
- 97.5% success rate, 83.1% fallback — the fallback tier is reliable

**New observation**: `NVStream_IncompleteRead` (1 occurrence, tiers_tried_count=2, 14898ms). First appearance of this error type. Low count, but monitor for growth trend. This is a response-stream level error, not a connection-level failure — unrelated to HM_CONNECT_RESERVE.

### Evidence Chain
1. `hm_requests` → 28 all_tiers_exhausted with tiers_tried_count=0 → connection fails before first key attempt
2. `hm_tier_attempts` → 551 gls5.1 429s (all 5 keys evenly) → function-level rate limit, not per-key
3. `hm_requests` fallback → 908 deepseek fallbacks, 97.5% succeed at 200 → fallback tier reliable
4. `docker logs` → "HM-TIER-SKIP tier=glm5.1_hm_nv all keys in cooldown, skipping" → TIER_COOLDOWN=90s is working correctly

### Metric Trajectory (R19→R20→R21→R22→R23→R24-pre)
- 0-tier failures: 42 → 42 → 37 → 34 → 31 → **28** ← continuing decline
- RESERVE: 8 → 10 → 12 → 14 → 16 → **18** ← incremental +2s per round
- Fallback rate: 73.0% → 77.6% → ~80% → 82.3% → 83.1% ← stable/slightly up
- Success rate: 95.8% → 95.9% → ~96% → 97.0% → 97.5% ← improving

---

## 3. Optimization Plan

**Strategy**: Single-parameter incremental (少改多轮). Continue the RESERVE +2s per round trajectory that has driven 0-tier failures from 42→28.

**Change**: `HM_CONNECT_RESERVE_S`: 16 → **18** (+2s SOCKS5+SSL handshake reserve)

**Budget calculation at RESERVE=18**:
- TIER_BUDGET = 80s, RESERVE = 18s → residual = 62s
- 1st deepseek attempt: full 40s UPSTREAM_TIMEOUT
- 2nd deepseek attempt: 62s - 40s = **22s** headroom (well above minimum 10s)
- Safe: no risk of 2nd attempt budget exhaustion

**Unchanged**: UPSTREAM_TIMEOUT=40, TIER_BUDGET=80, MIN_INTERVAL=10.0, KEY_COOLDOWN=38.0, TIER_COOLDOWN=90.

---

## 4. Execution Record

### Commands Executed
```bash
# Backup
ssh -p 222 opc_uname@100.109.153.83 "cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R24"

# Apply change (line 451, value + comment)
ssh target "cd /opt/cc-infra && \
  sed -i '451s/\"16\"/\"18\"/' docker-compose.yml && \
  sed -i '451s/# R23:.*$/# R24: HM2优化 — 16→18: +2s SOCKS5+SSL连接预留; .../' docker-compose.yml"

# Deploy
ssh target "cd /opt/cc-infra && docker compose up -d hm40006"

# Verify
ssh target "docker exec hm40006 env | grep HM_CONNECT_RESERVE_S"
# → HM_CONNECT_RESERVE_S=18 ✓
# → hm40006 Up 23 seconds (healthy) ✓
```

### Compose Line Changed
- Line 451: `"16"` → `"18"` (comment updated to R24)

---

## 5. Expected Effects

| Effect | Prediction | Confidence |
|--------|----------|-----------|
| 0-tier failures ↓ | 28 → ~23-25 (↓10-18%) | High — trajectory 42→28 supports this |
| Fallback rate | Stable at 82-84% | High — RESERVE doesn't affect fallback ratio |
| Overall success | Stable at 97-98% | High — deepseek tier is reliable |
| NVStream_IncompleteRead | Monitor — if >3 next round, investigate | Low — 1 occurrence, may be transient |

**Risk assessment**: LOW. Single-parameter change, well-established trajectory, ample budget headroom. RESERVE=18 is 2s below the 20s boundary where TIER_BUDGET coupling would need adjustment.

---

## 6. Observation Items

1. **NVStream_IncompleteRead**: New error type (1 occurrence). If count rises above 3 in next round, may need a separate investigation (possible stream disconnect under load).
2. **RESERVE=20 boundary approaching**: At 18, RESERVE is 2s from the 20s threshold. If 0-tier failures still >20 next round, consider whether to raise RESERVE to 20 (± TIER_BUDGET 80→85) or investigate mihomo proxy health as alternative root cause.
3. **TIER_COOLDOWN=90s stability**: 90s has been stable since R17. No evidence of thrashing or excessive SKIP windows — keep.
4. **KEY_COOLDOWN=38.0 ceiling**: At 38/10=3.8 cycles, healthy. KEY_COOLDOWN ≤ UPSTREAM_TIMEOUT=40 — no need to change. Keep at 38.

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记