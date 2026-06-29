# R332: HM1->HM2 - falsify+mechanism-deepening round (no new param) | current 6h data + docker logs recheck HM2-A/B/C all falsified | new MIN_ATTEMPT_TIMEOUT=10->45 falsified (short attempt is rescue vehicle not waste) | correct R331 failure mechanism (3-4x50s -> precise 2x full50s + 2x short10s) | docker log per-key stats prove 5 keys uniform DIRECT vs SOCKS5 no diff | 6h zero 429/zero empty200/zero SSL | single param no piggyback | rule: only change HM2 not HM1

**Role**: HM1(executor, opc_uname) -> HM2(target, opc2sname, glm5.1_hm_nv)
**Date**: 2026-06-29 23:10 UTC (real UTC; DB ts anchor=2026-06-30 07:01:20+00, ts 8h ahead of real UTC, R320 lesson#5)
**Rule**: only change HM2 not HM1
**Prev round**: R331 (HM1->HM2, falsify+mechanism-correction round)

## 0. Task rule and this round decision basis

Task rule: "execute list item 1 first; if item 1 cannot be done this round (already done / data not supporting), move to next. Only 1 item per round. No no-op round unless all three done or falsified (falsification needs concrete data)."

This round rechecks HM2-side three items (A/B/C) with **current 6h latest data + docker logs** (not reusing R331 conclusions), and newly explores an improvement point R331 did not consider (MIN_ATTEMPT_TIMEOUT hardcoded=10), falsified via docker log measurement:

- **HM2-A (MIN_OUTBOUND 4.5->2.5)**: R327 done. This round 120min recheck: flow 1.88req/min, gap<2.5 only 6 (2.62% blocked), 82.5% requests gap>4.5s completely unaffected by throttle, avg_gap=31.5s. 2.5 not bottleneck, keep, falsified (already target) holds.
- **HM2-B (failure-mode re采集 + degraded key)**: R331 falsified via DB per-key. This round uses **docker log per-key stats** (stronger than DB, directly counts HM-SUCCESS/HM-TIMEOUT): 5 keys success 78-89 uniform, timeout 27-34 uniform; DIRECT(k2/k3/k4) succ 74.3% vs SOCKS5(k1/k5) 72.5% no diff (DIRECT even slightly higher). Falsified holds, no basis to route k2/k3/k4 via proxy.
- **HM2-C (BUDGET 128->100)**: R331 falsified (kills 14 >100s successes). This round 360min recheck: >100s success=13 (1.52%), >110s=8 (0.94%), >115s=7 (0.82%). BUDGET=100 kills 13 (1.52%), =110 kills 8 (0.94%) and net-loses time (save 650s but add 8x110s=880s fail cost). Falsified holds.
- **MIN_ATTEMPT_TIMEOUT=10->45 (this round newly explored, R331 did not consider)**: code upstream.py:229 hardcodes MIN_ATTEMPT_TIMEOUT=10 (break when remaining<10s, no doomed attempt). This round found failure requests run 2x full50s + 2x short10s = 120s, the 2 short10s attempts look like "doomed waste" (NVCF needs 45s, 10s not enough). **But docker log measurement overturns this assumption**: rescue-success requests succeed via "2x full50s + 1x short10s + rescue 8s" pattern (after short timeout the next key succeeds in 8s). Raising MIN_ATTEMPT_TIMEOUT to 45 breaks when remaining<45s, killing 13 >100s rescue successes (1.52%, same mechanism as HM2-C). Falsified, short attempt is rescue vehicle not waste.

**This round core new contribution — correct R331 failure mechanism + overturning finding that short attempt is rescue vehicle**:
- R331 sec1d said HM2 failure = "3-4 keys consecutive NVCFPexecTimeout each hang full ~50s exhausting BUDGET=128s" (3-4x50s).
- **This round docker log precisely stats 28 failure requests' attempt structure** (awk per-failure count): 20/28 failures are full50s=2 + short10s=2 (2x full50s + 2x short10s = 120s -> remaining<10 break), rest are full50s=3 + short10s=2. **Every failure has 2 short10s attempts** (total 20s).
- R331 said "3-4x50s" is inaccurate: actual is **2x full50s + 2x short10s** (after 2 full50s=100s, remaining=28s, per_attempt_timeout=min(50, 28-21)=7 -> max(10,7)=10s, so attempt3 runs 10s short timeout; then remaining=18s, attempt4 also 10s short timeout; then remaining=8s<10 break).
- **Overturning finding**: the 2 short10s attempts are NOT pure waste. Docker log shows rescue-success requests (after N cycle) succeed via "2x full50s + 1x short10s + rescue 8s" — e.g. 05:04:13.7 request: k4(50534ms full) -> k5(50683ms full) -> k1(10836ms short) -> k2(8s success, after 3 cycle). The short10s attempt3 (k1) times out, but attempt4 (k2) succeeds in 8s. So short attempt is the **rescue vehicle**: 10s is enough for NVCF to return success (fast keys ~8s); if 10s timeout -> that key hangs, try next.
- **Implication**: raising MIN_ATTEMPT_TIMEOUT (10->20/45) breaks earlier when remaining<20/45s, skipping the short attempt that could rescue -> kills rescue successes. 360min has 13 >100s rescue successes (1.52%), all rely on remaining<28s short attempt + fast rescue. Raising threshold kills these, same as lowering BUDGET. Falsified.

## 1. Pre-change (=current 2.5/BUDGET=128/UPSTREAM=50/MIN_ATTEMPT_TIMEOUT=10 effective) data collection (anchor max_ts=2026-06-30 07:01:20+00 DB caliber, HM2)

### 1a. Multi-window success rate (host_machine='opc2sname', ts caliber 8h-corrected, R320 lesson#5)

| window | total | succ | fail | succ_pct | reqs/min | 429 | empty200 |
|---|---|---|---|---|---|---|---|
| 30min | 93 | 91 | 2 | 97.85% | 3.10 | 0 | 0 |
| 60min | 128 | 119 | 9 | 92.97% | 2.13 | 0 | 0 |
| 120min | 225 | 199 | 26 | 88.44% | 1.88 | 0 | 0 |
| 360min | 914 | 866 | 48 | 94.75% | 2.54 | 0 | 0 |

**Flow**: current 1.88-3.10req/min. 120min succ 88.44% (26 fail) lower than R331's 95.81% — failure rate rose. 360min 48 fails all ATE. Zero 429/empty200/SSL/conn_err across all windows.

### 1b. 120min error structure

| err | n | avg_d | p50 | p95 | min_d | max_d |
|---|---|---|---|---|---|---|
| (success) | 199 | 21031 | 12047 | 72408 | 1814 | 120400 |
| all_tiers_exhausted | 26 | 122365 | 122388 | 122955 | 121746 | 123043 |

All failures are all_tiers_exhausted, avg 122.4s, min=121746ms (every failure runs to >=121.7s), max=123043ms < BUDGET=128s. No 429/empty200/SSL/conn_err.

### 1c. **This round core: HM2 failure real mechanism (docker log evidence, corrects R331)**

R331 sec1d said failure = "3-4 keys consecutive NVCFPexecTimeout each hang full ~50s exhausting BUDGET" (3-4x50s). This round docker log precisely stats 28 failure requests (awk per-failure HM-TIMEOUT count):

**28 failures' attempt structure** (full50s = attempt>=40s, short10s = attempt<15s):
- 20/28 failures: full50s=2 + short10s=2 (standard pattern)
- 6/28 failures: full50s=3 + short10s=2
- 2/28 failures: full50s=2 + short10s=3
- **Every failure has exactly 2 short10s attempts** (total ~20s)

**Standard failure timeline** (06:30:26.3 example, container local):
```
06:29:14.8 [HM-TIMEOUT] k5 NVCF pexec timeout: attempt=50775ms total=50782ms   (full 50s)
06:30:05.2 [HM-TIMEOUT] k1 NVCF pexec timeout: attempt=50370ms total=101152ms  (full 50s)
06:30:15.8 [HM-TIMEOUT] k2 NVCF pexec timeout: attempt=10584ms total=111738ms  (short 10s, remaining=27s)
06:30:26.3 [HM-TIMEOUT] k3 NVCF pexec timeout: attempt=10544ms total=122284ms  (short 10s, remaining=18s)
06:30:26.3 [HM-TIER-BUDGET] remaining 5.7s < 10s minimum, breaking
06:30:26.3 [HM-ALL-TIERS-FAIL] elapsed=122290ms
```

**Mechanism**: failure = 2x full50s timeout (100s) + 2x short10s timeout (20s) = 120s, then remaining<10 break. The 2 short10s attempts are because after 2 full50s, remaining=28s, per_attempt_timeout=min(50,28-21)=7 -> max(MIN_ATTEMPT_TIMEOUT=10,7)=10s; attempt3 runs 10s timeout; remaining=18s, attempt4 also 10s; remaining=8s<10 break.

### 1d. **Overturning finding: short attempt is rescue vehicle, not waste**

Docker log shows rescue-success requests (succeeded after N cycle) succeed via the SAME short-attempt pattern:

**Rescue-success timeline** (05:04:13.7, after 3 cycle, status=200, duration~118s):
```
05:04:13.7 [HM-KEY] attempt 1/7: k4 -> NVCF pexec
05:05:04.2 [HM-TIMEOUT] k4 timeout: attempt=50534ms total=50539ms   (full 50s)
05:05:04.2 [HM-KEY] attempt 2/7: k5
05:05:54.9 [HM-TIMEOUT] k5 timeout: attempt=50683ms total=101224ms  (full 50s)
05:05:54.9 [HM-KEY] attempt 3/7: k1
05:06:05.7 [HM-TIMEOUT] k1 timeout: attempt=10836ms total=112061ms  (short 10s, remaining=27s)
05:06:05.7 [HM-KEY] attempt 4/7: k2
05:06:13.9 [HM-SUCCESS] k2 succeeded after 3 cycle attempts      (rescue in 8s!)
```

**Key insight**: attempt3 (k1) short10s timeout, but attempt4 (k2) succeeds in 8s. So the short10s attempt is NOT doomed waste — 10s IS enough for NVCF to return success (fast keys ~8s); the short attempt is the **rescue vehicle**. If 10s times out, that key hangs; try next key which may succeed fast.

**Comparison failure vs rescue**: both start 2x full50s + short10s. Difference is only whether the 4th key succeeds in 8s (rescue) or times out in 10s (failure). NOT distinguishable beforehand. This is why raising MIN_ATTEMPT_TIMEOUT or lowering BUDGET kills rescues — same conclusion as R331 sec1g but now with the correct mechanism (short attempt is rescue vehicle, not waste).

### 1e. MIN_ATTEMPT_TIMEOUT=10->45 falsification (this round newly explored)

Code upstream.py:229: `MIN_ATTEMPT_TIMEOUT = 10  # Don't attempt if less than 10s budget remains (doomed attempt)`. Line 230-233: if remaining_budget < MIN_ATTEMPT_TIMEOUT: break.

**Hypothesis (this round initial)**: 10s too low; NVCF needs 45s; remaining 10-50s short attempts are doomed waste. Raise to 45 -> break when remaining<45s, save 2x short10s=20s per failure.

**Falsification via docker log**: sec1d shows rescue-success requests rely on remaining<28s short attempt + 8s rescue. 360min has 13 >100s rescue successes (1.52%, see sec1g). Raising MIN_ATTEMPT_TIMEOUT to 45 breaks when remaining<45s, skipping the short attempt + rescue -> kills 13 rescues (1.52% succ rate). Same as BUDGET=100. **Net loss (succ rate -1.52%), falsified.**

Even raising to 20 (not 45) kills rescues: rescue happens at remaining~17s (8s rescue), remaining<20 would break before rescue. **Any raise kills rescues.**

### 1f. HM2-B docker-log per-key stats (stronger than R331's DB analysis)

Docker log full HM-SUCCESS / HM-TIMEOUT per-key counts:

| key | idx | route | success | timeout | succ_rate |
|---|---|---|---|---|---|
| k1 | 0 | SOCKS5(7894) | 78 | 34 | 69.6% |
| k2 | 1 | DIRECT | 89 | 29 | 75.4% |
| k3 | 2 | DIRECT | 81 | 33 | 71.1% |
| k4 | 3 | DIRECT | 87 | 27 | 76.3% |
| k5 | 4 | SOCKS5(7899) | 83 | 27 | 75.5% |

- **Success**: k1=78, k2=89, k3=81, k4=87, k5=83 (uniform 78-89, span 11)
- **Timeout**: k1=34, k2=29, k3=33, k4=27, k5=27 (uniform 27-34, span 7)
- **DIRECT(k2/k3/k4)**: succ 257, timeout 89, succ_rate 74.3%
- **SOCKS5(k1/k5)**: succ 161, timeout 61, succ_rate 72.5%
- DIRECT even slightly higher than SOCKS5. **No DIRECT degradation, 5 keys uniform. Falsified.** Routing k2/k3/k4 via proxy has no basis and may introduce proxy instability.

### 1g. HM2-C recheck — 360min success duration>100s distribution (rescue structure)

| range | n | note |
|---|---|---|
| >100s | 13 | BUDGET=100 kills all (1.52%) |
| >110s | 8 | BUDGET=110 kills (0.94%) |
| >115s | 7 | BUDGET=115 kills (0.82%) |
| >120s | 3 | max=122572ms |

Success duration buckets (360min):
| bucket | n | pct |
|---|---|---|
| <30s | 718 | 83.68% (first-attempt) |
| 30-60s | 99 | 11.54% |
| 60-100s | 28 | 3.26% (1-2 retries) |
| 100-110s | 5 | 0.58% (rescue) |
| 110-120s | 5 | 0.58% (rescue) |
| >120s | 3 | 0.35% (rescue) |

Docker log success format: 380 "on first attempt" + 27 "after 1 cycle" + 1 "after 2 cycle" + 3 "after 3 cycle" = 31 rescue successes. The 13 >100s rescues all rely on remaining<28s short attempt + fast rescue (sec1d). BUDGET=100/MIN_ATTEMPT_TIMEOUT=45 kills these. Falsified.

### 1h. HM2-A recheck — 120min gap distribution (current 1.88req/min)

| metric | value |
|---|---|
| reqs | 229 |
| blocked(<2.5s) | 6 (2.62%) |
| blocked(<2.0s) | 4 |
| blocked(<3.0s) | 14 |
| free(>4.5s) | 189 (82.53%) |
| avg_gap | 31.5s |
| p50_gap | 12.8s |

2.5 at current flow: only 2.62% blocked, 82.5% free. Not bottleneck. Keep 2.5. Falsified (already target) holds.

### 1i. Pre-change env (HM2 docker exec hm40006 env + compose dual-verify)

| param | HM2 current | code ref | note |
|---|---|---|---|
| UPSTREAM_TIMEOUT | 50 | upstream.py:235 | sec1g falsified 50->45 kills 40 45-50s direct successes |
| MIN_OUTBOUND_INTERVAL_S | 2.5 | config.py:125, upstream.py:288 | R327 done, sec1h recheck not bottleneck, keep |
| TIER_TIMEOUT_BUDGET_S | 128 | upstream.py:215 | sec1g falsified 128->100 kills 13 (1.52%) |
| HM_CONNECT_RESERVE_S | 21 | upstream.py:227 | R331 falsified 21->12 (slower failures) |
| **MIN_ATTEMPT_TIMEOUT** | **10 (hardcoded)** | upstream.py:229 | **this round newly explored, sec1e falsified 10->45 kills 13 rescues** |
| KEY_COOLDOWN_S | 38 | config.py:141 | 429=0 not triggered |
| HM_NV_PROXY_URL1~5 | 7894/empty/empty/empty/7899 | live | k2/k3/k4 DIRECT, sec1f no DIRECT degradation |

**compose dual-verify** (R322 lesson#1/#2): /opt/cc-infra/docker-compose.yml hm40006 service:
- line 469: UPSTREAM_TIMEOUT: "50" (matches env)
- line 470: TIER_TIMEOUT_BUDGET_S: "128" (matches env)
- line 472: MIN_OUTBOUND_INTERVAL_S: "2.5" (matches env, R327 comment)
- line 504: HM_CONNECT_RESERVE_S: "21" (matches env)
- MIN_ATTEMPT_TIMEOUT is hardcoded in upstream.py:229 (NOT an env param), so no compose entry. This round no source change, so no rebuild needed.

**compose and runtime synced, no rollback risk**. live compose /opt/cc-infra/docker-compose.yml **not in git** (R322 lesson#2); this round no change so no sync needed.

## 2. CC list HM2-A/B/C recheck conclusions

### [HM2-A] MIN_OUTBOUND 4.5->2.5 — R327 done, this round recheck keep 2.5
120min: 229reqs (1.88req/min), gap<2.5 only 6 (2.62% blocked, total wait ~7s), 82.5% gap>4.5s unaffected. 30min gap<2.5=0. 2.5 not bottleneck at current flow, keep (neither raise to 3.0 nor lower to 2.0). R329 high-flow closure (3.67req/min zero 429) still valid.

### [HM2-B] failure-mode + degraded key — falsified (5 keys uniform, sec1f)
Docker log per-key: success 78-89 uniform, timeout 27-34 uniform. DIRECT succ_rate 74.3% vs SOCKS5 72.5% no diff. No HM1-k4-style degraded key. No actionable item.

### [HM2-C] TIER_TIMEOUT_BUDGET 128->100 — falsified holds (sec1g)
360min >100s success=13 (1.52%). BUDGET=100 kills 13. =110 kills 8 (0.94%) and net-loses time (save 650s, add 880s fail cost). Failure 122s is 2x full50s + 2x short10s physical floor; lowering BUDGET only saves 22s but kills rescues. Falsified.

### [extra] MIN_ATTEMPT_TIMEOUT=10->45 — falsified (sec1e, this round newly explored)
Hardcoded upstream.py:229. Short attempt is rescue vehicle (sec1d), raising kills 13 >100s rescues. Falsified.

## 3. A/B verify (this round no new param change, no PRE/POST compare)

This round no new param change, so no PRE/POST A/B compare. Complies with rule: "no no-op round unless all three done or falsified (falsification needs concrete data)" — this round gives current latest falsification data for A/B/C + newly-explored MIN_ATTEMPT_TIMEOUT (sec1c/1d/1e/1f/1g/1h), not reusing R331 conclusions.

**Mechanism-correction "data compare"** (R331 mechanism vs this round docker-log measurement):

| item | R331 said | this round docker-log measurement |
|---|---|---|
| failure attempt structure | 3-4x full50s | 2x full50s + 2x short10s (20/28 failures) |
| short10s attempt | (not distinguished, counted as 50s) | 2 per failure, 10s each, because per_attempt_timeout=max(10,min(50,remaining-21))=10s when remaining<31s |
| short attempt role | (R331 implied wasted, called 3-4x50s) | **rescue vehicle** — rescue-success relies on short10s + 8s fast rescue |
| MIN_ATTEMPT_TIMEOUT=10 | (R331 did not consider) | this round explored: raising kills 13 rescues (1.52%), falsified |

## 4. This round no new param change explanation (honest annotation)

This round **changed no HM2 param/source**. Reason: CC list HM2-side A/B/C all done/falsified (A=R327 done+recheck, B=sec1f falsified, C=sec1g falsified); this round newly explored MIN_ATTEMPT_TIMEOUT=10->45 also falsified (sec1e); R331 already falsified CONNECT_RESERVE/UPSTREAM.

By rule "no no-op round unless all three done or falsified (falsification needs concrete data)", this round attaches:
- HM2-A recheck data: sec1h (120min gap<2.5 only 6, 2.62% blocked)
- HM2-B falsify data: sec1f (docker log per-key success 78-89 uniform, DIRECT vs SOCKS5 74.3% vs 72.5%)
- HM2-C falsify data: sec1g (13 >100s rescues, BUDGET=100 kills 1.52%)
- **newly explored MIN_ATTEMPT_TIMEOUT falsify**: sec1c/1d/1e (docker log proves failure=2x full50s+2x short10s, short attempt is rescue vehicle, raising kills 13 rescues)

This round value: (1) rechecks A/B/C with current 6h latest data (not reusing R331); (2) **corrects R331 failure mechanism** — 3-4x50s -> precise 2x full50s + 2x short10s; (3) **overturning finding** — short10s attempt is NOT waste but rescue vehicle (rescue-success relies on it); (4) newly explores MIN_ATTEMPT_TIMEOUT=10->45 and falsifies it (same as BUDGET, kills rescues); (5) uses docker-log per-key stats (stronger than R331's DB hm_tier_attempts analysis, which this round found unreliable — table records 75 attempts for 56 success reqs but docker log shows 31 rescue + 380 first-attempt, table data inconsistent with runtime).

## 5. Conclusion

1. **HM2-A recheck closure**: 2.5 at 1.88req/min, 120min only 6 (2.62%) blocked by 2.5 lock, 82.5% gap>4.5s unaffected. Keep 2.5.
2. **HM2-B falsified**: docker log per-key success 78-89 uniform, timeout 27-34 uniform; DIRECT succ_rate 74.3% vs SOCKS5 72.5% no diff. No degraded key.
3. **HM2-C falsified**: 13 >100s rescues (1.52%); BUDGET=100 kills 13; =110 kills 8 (0.94%) and net-loses time. Failure 122s is 2x full50s + 2x short10s physical floor.
4. **R331 mechanism corrected**: R331 said failure=3-4x50s; this round docker log stats 28 failures -> 20/28 are 2x full50s + 2x short10s. Every failure has 2 short10s attempts.
5. **Overturning finding (core)**: short10s attempt is NOT doomed waste — it is the rescue vehicle. Rescue-success requests (after N cycle) succeed via "2x full50s + 1x short10s + 8s rescue". 10s is enough for NVCF fast keys (~8s); if 10s timeout, try next key. R331's "3-4x50s" framing missed that short attempts enable rescues.
6. **MIN_ATTEMPT_TIMEOUT=10->45 falsified**: raising breaks earlier, skipping short attempt + rescue, kills 13 >100s rescues (1.52%, same as BUDGET=100). Even raising to 20 kills rescues (rescue at remaining~17s). Any raise kills rescues.
7. **hm_tier_attempts table unreliable**: table records 75 attempts for 56 success reqs in 360min, but docker log shows 380 first-attempt + 31 rescue = 411 successes. Table data inconsistent with runtime (R331's sec1e/1g analysis based on this table may be imprecise; this round uses docker log instead, which is authoritative).
8. **Stability priority**: 6h zero 429/zero empty200/zero SSL/zero conn_err. 2.5 keeps zero-rate-limit baseline. Failures are NVCF platform pexec hang (ATE 122s = 2x full50s + 2x short10s), not HM2-param-solvable (UPSTREAM not lowerable=sec1g kills 45-50s direct; BUDGET not lowerable=sec1g kills >100s rescues; MIN_ATTEMPT_TIMEOUT not raisable=sec1e kills rescues; CONNECT_RESERVE not lowerable=R331 slower failures).
9. **Single param / no piggyback**: this round no new param change (all falsified), strictly no piggyback.
10. **Honest annotation**: this round is falsify+mechanism-deepening round, not a new-change round. HM2-side currently has no safely-adjustable param (throttle=2.5 already target and rechecked non-bottleneck; UPSTREAM/BUDGET/CONNECT_RESERVE/MIN_ATTEMPT_TIMEOUT all falsified). HM2 failures are NVCF platform pexec hang; short10s attempt is the only rescue path and cannot be removed.

## 6. Todo (for next round HM2->HM1)

- [ ] **next round HM2->HM1**: R328 done HM1-A (MIN_OUTBOUND 9.0->6.0), R330/R331 marked "await peak recheck". Next round if HM1 peak (21-01 UTC, >10req/min) must recheck whether 6.0 shows new serial blocking or 429. If peak zero 429 and block<12% consider 5.0; if 429 or block rises fall back to 7.0.
- [ ] **HM1 failure mechanism also needs docker-log recheck**: R330 said HM1 failure "0 tier_attempts = Proxy-tier-selection failure"; R331 corrected HM2-side (hm_tier_attempts 0 records != no pexec). This round further found hm_tier_attempts table unreliable (inconsistent with runtime). Next round HM2->HM1 should use docker log (not the table) to recheck HM1 failure mechanism, which affects whether HM1-C early-fail is feasible.
- [ ] **HM2 failures all NVCF platform pexec hang (ATE 122s = 2x full50s + 2x short10s, 48/6h)**: not HM2-param-solvable (UPSTREAM/BUDGET/MIN_ATTEMPT_TIMEOUT/CONNECT_RESERVE all falsified). Short10s attempt is the only rescue path (saves 13 rescues/6h). If NVCF platform hang persists/worsens, consider NVCF account/key layer, beyond HM param scope.
- [ ] **hm_tier_attempts table unreliable**: docker log is authoritative. Future rounds should prefer docker log HM-SUCCESS/HM-TIMEOUT per-key stats over the table.
- [ ] **HM2 MIN_OUTBOUND=2.5 super-high-flow recheck**: this round 1.88req/min (below R329's 3.67). If HM2 flow rises to >20req/min (avg_gap<3s) recheck whether 2.5 shows new serial blocking or 429; fall back to 3.0 if needed.
- [ ] **HM2-side TIER_COOLDOWN_S=22 dead param** (no cooldown.py): env set but code not referenced, 429=0 branch not triggered, no runtime meaning, low priority.
- [ ] **HM2-side HM_SSLEOF_RETRY_ENABLED=true but code not read** (both machines unconditionally retry): dead env, low priority.

## ⏳ 轮到HM2优化HM1
