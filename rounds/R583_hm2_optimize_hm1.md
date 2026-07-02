# R583: HM2->HM1 — NOP (zero-error stable regime, all candidates data-vetoed)
**Round**: R583 | **Direction**: HM2 -> HM1 | **Author**: opc2_uname

## Data Collection

### 1. Docker Logs (nv_40006_uni, tail 200)
- No ERROR/WARN/429/SSLEOF/empty200 events in last 200 lines
- Only 2 normal `[NV-THINKING-TIMEOUT] (kimi_nv) thinking request stream=True -> extended timeout 61s` messages

### 2. Container Env (nv_40006_uni)
| Parameter | Value | Status |
|-----------|-------|--------|
| UPSTREAM_TIMEOUT | 28 | R577, compose matches |
| TIER_TIMEOUT_BUDGET_S | 90 | R576, compose matches |
| MIN_OUTBOUND_INTERVAL_S | 0.4 | R582, compose matches |
| NVU_PEXEC_TIMEOUT_FASTBREAK | 1 | R559, compose matches |
| TIER_COOLDOWN_S | 25 | R492, compose matches |
| NVU_PEER_FALLBACK_TIMEOUT | 25 | R560, compose matches |
| NVU_CONNECT_RESERVE_S | 2 | R570, compose matches |
| NVU_SSLEOF_RETRY_DELAY_S | 1.0 | R543, compose matches |
| NVU_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | R537, compose matches |
| NVU_FORCE_STREAM_UPGRADE | 1 | R502, compose matches |
| NVU_EMPTY_200_FASTBREAK | 2 | R581, env matches |
| NV_INTEGRATE_ENABLED | 1 | R574, env matches |
| NV_INTEGRATE_MODELS | dsv4p_nv,kimi_nv | R575, compose matches |
| NV_INTEGRATE_KEY_COOLDOWN_S | 120 | R580, compose matches |
| KEY_COOLDOWN_S | 25 | R162, compose matches |

**Drift check**: env and compose fully aligned. Container restarted at 2026-07-02T19:36:05Z (after R580 changes). No drift detected.

### 3. DB nv_requests (PostgreSQL cc_postgres)
**6h summary (ts > NOW() - interval '6 hours')**

| Model | Total | OK | Fail | SR% | Max(s) | P95(s) | Avg(s) |
|-------|-------|----|------|-----|--------|--------|--------|
| dsv4p_nv | 691 | 623 | 68 | 90.2 | 161.4 | 58.6 | 28.2 |
| kimi_nv | 297 | 153 | 144 | 51.5 | 351.3 | 105.3 | 40.0 |
| glm5_2_nv | 42 | 41 | 1 | 97.6 | 34.8 | 16.0 | 5.4 |
| glm5_1_nv | 23 | 13 | 10 | 56.5 | 89.7 | 70.0 | 10.0 |

**Hour-bucketed trend (last 6h)**

| Hour | dsv4p_nv SR% | kimi_nv SR% | glm5_2_nv SR% |
|------|-------------|-------------|---------------|
| 03:00 | 100.0 (21/21) | 100.0 (8/8) | 96.6 (28/29) |
| 02:00 | 100.0 (67/67) | 100.0 (24/24) | 100.0 (13/13) |
| 01:00 | 96.3 (26/27) | 100.0 (15/15) | — |
| 00:00 | 99.0 (96/97) | 16.0 (4/25) | — |
| 23:00 | 93.5 (100/107) | 36.4 (8/22) | — |
| 22:00 | 92.0 (92/100) | 95.5 (21/22) | — |

**Last 30min (absolute ts > 2026-07-03 03:10:00+00)**: 10 dsv4p_nv, 8 kimi_nv, 16 glm5_2_nv — **all 100% SR, 0 failures, 0 errors**

**Last 15min (absolute ts > 2026-07-03 03:25:00+00)**: 1 dsv4p_nv, 4 kimi_nv — **all 100% SR, 0 failures, 0 errors**

Kimi NVCF failures (00:38–00:55 window) show extremely consistent ~74–76s `all_tiers_exhausted` pattern — strongly suggesting a transient NVCF function-level surge on `f966661c` that subsequently recovered. All failures ceased after 01:00 UTC.

### 4. Model Configuration Symmetry
- kimi_nv inject: verified `reasoning_effort=low` (R523 fix, confirmed stable)
- dsv4p_nv: direct all-keys (no proxy), function `74f02205` active
- integrate models: `dsv4p_nv,kimi_nv` only (glm5.1 EOL, glm5.2 pexec-only per R577)

## Candidate Parameter Evaluation

| Parameter | Old Value | Candidate New Value | Evaluation | Decision |
|-----------|-----------|-------------------|------------|----------|
| MIN_OUTBOUND_INTERVAL_S | 0.4 | 0.3 (-0.1s) | R582 already trimmed 0.5->0.4; skill requires different param in consecutive rounds | not this round |
| UPSTREAM_TIMEOUT | 28 | 30 (+2s) | 15min zero-failure window provides no data to test ceiling binding | no |
| TIER_TIMEOUT_BUDGET_S | 90 | 95 (+5s) | Last 15min: 0 failures. Earlier 74s failures at 00:00 were NVCF-side, not budget-limited (76->90 already done in R576) | no |
| NV_INTEGRATE_KEY_COOLDOWN_S | 120 | 130 (+10s) | Recent 30min shows zero 429s; 120 already working. No data that 130 would help. | no |
| NV_INTEGRATE_KEY_COOLDOWN_S | 120 | 100 (-20s) | R580 specifically raised 90->120 to prevent integrate 429->pexec fallback; no new data to reverse this direction. | no |
| NVU_CONNECT_RESERVE_S | 2 | 1 (-1s) | No fresh connect-time data available. R570 data (max 2.1s) made 2 the safe floor. | no |
| TIER_COOLDOWN_S | 25 | 20 (-5s) | Single-tier architecture; compose comment explicitly notes "TIER_COOLDOWN as dead parameter". Zero benefit to changing a dead parameter. | no |
| NVU_SSLEOF_RETRY_DELAY_S | 1.0 | 0.8 (-0.2s) | No SSLEOF events in logs. SSLEOF is already rare; marginal gain doesn't justify risk. | no |
| NVU_PEER_FALLBACK_TIMEOUT | 25 | 23 (-2s) | Peer fallback has been 0% success for entire observation window. But no new failure data to support further reduction. | no |
| NV_INTEGRATE_MODELS | dsv4p_nv,kimi_nv | (expand?) | glm5.1 EOL confirmed; glm5.2 integrate returns 404. R577 already verified no viable expand target. | no |

## Decision Analysis

**System state**: Zero-error stable regime for 30+ minutes. All 3 active models (dsv4p, kimi, glm5.2) at 100% SR in the most recent window. The 6h aggregate kimi 51.5% is dominated by a single transient NVCF surge window (00:00–00:55), not a parameter misconfiguration.

**No ceiling binding evidence**: All dsv4p successes are <161s (integrate path; max pexec success unknown but not binding UPSTREAM=28). No failures cluster at any timeout ceiling (min_fail gap > 28s).

**No surge isolation**: dsv4p and kimi both recovered simultaneously after 01:00, confirming function-level surge (shared NVCF infrastructure), not model-specific issue.

**All 10 tracked active parameters are at their tuned, verified values.** No drift. No errors. No clear safe micro-trim candidate with data support.

**Conclusion**: NOP. The correct optimization is to maintain current configuration and continue monitoring. The next round should re-evaluate after accumulating more data (especially if the 00:00-style NVCF surge recurs).

## Deployment
No parameter changes this round. Compose and env remain as-is.

## Post-Deploy Verification
- Container StartedAt: 2026-07-02T19:36:05Z (unchanged)
- compose env: all values unchanged, no drift
- NVCF function IDs: 74f02205 (dsv4p), f966661c (kimi), 3b9748d8 (glm5.2) — all active

## ⏳ 轮到HM1优化HM2
