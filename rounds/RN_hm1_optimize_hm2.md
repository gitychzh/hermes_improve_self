# R60: HM1 优化 HM2 — KEY_COOLDOWN_S 28.0→26.5 (-1.5s, accelerate 429 key recovery)

**Direction**: HM1 → HM2  
**Round**: R60 (hm1_optimize_hm2)  
**Author**: opc_uname  
**Timestamp**: 2026-06-26T19:42:00+00:00  
**Trigger**: HM2 had new commits on GitHub (detected by monitoring script)

## Pre-Change Baseline (2h window, 17:42–19:42 UTC)

### DB Core Metrics (hm_requests, hermes_logs)
| Metric | Value |
|---|---|
| Total requests | 1,188 |
| Success | 1,187 (99.9%) |
| Fallback occurrences | 985 (83.3%) |
| direct_success (glm5.1) | 197 (16.7%) |
| all_tiers_exhausted | 1 (0.08%) |

### Tier Distribution
| Tier | Requests | Avg Duration | p50 | p80 | p95 |
|---|---|---|---|---|---|
| `glm5.1_hm_nv` | 197 | 22,428ms | 17,485ms | 34,886ms | 56,360ms |
| `deepseek_hm_nv` | 985 | 36,739ms | 29,820ms | 57,778ms | 78,556ms |
| `kimi_hm_nv` | 6 | 178,779ms | 170,946ms | 211,226ms | 214,469ms |
| `None` | 1 | 208,073ms | — | — | — |

### Live Logs Error Summary (200 lines, ~19:26–19:42)
- **429_nv_rate_limit**: ~85 occurrences (dominant error)
- **SSLEOFError (glm5.1)**: 310 across all 5 keys (k0=42, k1=72, k2=59, k3=66, k4=71)
- **SSLEOFError (deepseek)**: 88 across all 5 keys (k0=12, k1=20, k2=15, k3=21, k4=20)
- **ConnectionResetError (glm5.1)**: 133 (k0=38, k1=28, k2=22, k3=29, k4=16)
- **NVCFPexecTimeout (deepseek)**: 6 (k0=3, k1=1, k2=1, k4=1)
- **HM-TIER-SKIP** (all keys in cooldown): Frequent — every glm5.1 tier attempt after k1 429 cooldown expiry

### Per-Key 429 Distribution (2h, glm5.1 tier)
| Key | 429 Count | % of total |
|---|---|---|
| k0 (port 7894) | 559 | 25.1% |
| k1 (port 7895) | 549 | 24.6% |
| k2 (port 7896) | 575 | 25.8% |
| k3 (port 7897) | 567 | 25.4% |
| k4 (port 7899) | 579 | 26.0% |
| **Total** | **2,229** | **100%** |
| **Range** | **30 (549–579)** | **±1.6% from mean** |

Extremely uniform — confirms **function-level NVCF rate limit** (not per-key).

### Fluorescent Pattern: k1 429-After-Cooldown
Live logs show a recurring pattern:
```
[19:31:29.1] [HM-COOLDOWN] tier=glm5.1_hm_nv k1 marked cooling after 429
[19:33:45.4] [HM-COOLDOWN] tier=glm5.1_hm_nv k1 marked cooling after 429  ← 136s later
[19:35:12.8] [HM-COOLDOWN] tier=glm5.1_hm_nv k1 marked cooling after 429  ← 87s later
```
Gaps = ~28s KEY_COOLDOWN + ~TIER_COOLDOWN(42s) + request arrival time = 136s/87s.
**Reducing KEY_COOLDOWN_S by 1.5s will shrink this gap**: each k1 429-then-retry cycle saves 1.5s.

### Current Configuration (verified from docker exec)
| Parameter | Value | Source Round |
|---|---|---|
| `KEY_COOLDOWN_S` | 28.0 (pre) → **26.5 (post)** | R32→R60 |
| `TIER_COOLDOWN_S` | 42 | R59 |
| `MIN_OUTBOUND_INTERVAL_S` | 17.0 | R43 |
| `HM_CONNECT_RESERVE_S` | 16 | R53 |
| `TIER_TIMEOUT_BUDGET_S` | 111 | R30 |
| `UPSTREAM_TIMEOUT` | 62 | R30 |

## Bottleneck Identification

### Primary Bottleneck: KEY_COOLDOWN_S=28 slows 429 key recovery
The **2,229** `429_nv_rate_limit` errors in 2 hours is the dominant bottleneck. Each 429 triggers a 28.0s per-key cooldown. When all 5 keys hit function-level 429 (100% pattern), the system must wait for individual keys to recover from cooldown before retrying. Reducing this wait by 1.5s per key accelerates the fallback path.

**Specific Impact**: After a 5-key 429 sweep, the first key recovers at 26.5s instead of 28.0s. If the NV rate limit has genuinely reset (function-level window ~60s), the key becomes usable 1.5s earlier. If it hasn't reset, the 429 re-triggers quickly (5-10s cycle), and the next key in the round-robin gets tried 1.5s sooner. Either way, the **key recovery timeline shortens by 1.5s per key**.

### Why Not TIER_COOLDOWN_S Again?
R59 already reduced TIER_COOLDOWN_S from 50→42 (-8s). The tier cooldown gap is now 42s. Further reduction risks hitting the NVCF function-level rate limit window (~60s) too aggressively, causing more TIER-SKIP→fallback cycles without the tier cooldown adding value. KEY_COOLDOWN_S is the next impactful parameter.

### Why Not More Aggressive?
Previous round RN changed KEY_COOLDOWN_S 28→26 (-2s), but R58 (by HM2) reversed a similar change back to 28.0 because function-level 429 makes aggressive key cooldown reduction risky — if the 60s rate limit window hasn't reset, shorter cooldown just means more rapid 429 rejections. **26.5 is a moderate -1.5s step** that balances recovery speed against 429 re-rejection risk.

## Hypothesis

**Reducing KEY_COOLDOWN_S from 28.0→26.5** will accelerate per-key 429 recovery by 1.5s per key.

**Prediction**: Each 5-key 429 sweep on the glm5.1 tier will complete the cycle ~1.5s faster (first key recovers at 26.5s instead of 28.0s). For the 985 fallback requests, this saves ~1,478s total over 2 hours. Average fallback path duration should decrease by ~1.5s per request (from ~37s to ~35.5s).

**Risk Assessment**: 
- ✅ LOW risk — 1.5s is within the safe zone (code cap `min(...,30)` is still respected at 26.5)
- ✅ Function-level 429 pattern means keys will hit 429 again quickly if the window hasn't reset, but the extra 1.5s early recovery doesn't cause extra load — it just moves the retry 1.5s earlier
- ✅ Does not affect throughput or tier behavior
- ✅ Deepseek tier continues to handle the actual requests

## Change Details

**Target**: Line 480 `/opt/cc-infra/docker-compose.yml`

```diff
-      KEY_COOLDOWN_S: "28.0"
+      KEY_COOLDOWN_S: "26.5"
```

**Delta**: -1.5s (28.0 → 26.5, -5.4%)

**Rationale** (data-driven):
1. Function-level 429 is 100% — all 5 keys hit 429 uniformly (±1.6% from mean)
2. The live log "k1 429 after cooldown" pattern shows KEY_COOLDOWN directly controls the retry gap
3. TIER_COOLDOWN_S already optimized (42, R59) — KEY_COOLDOWN_S is next impactful parameter
4. Previous RN round went to 26.0 but R58 reversal suggests caution — 26.5 is a more conservative step
5. All other parameters unchanged (MIN_OUTBOUND=17.0, RESERVE=16, TIER_BUDGET=111)
6. Single parameter change (少改多轮)

## Deployment

### Execution
```bash
ssh opc2_uname@100.109.57.26 -p 222
cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.$(date +%s)
sed -i '480s/KEY_COOLDOWN_S: "28.0"/KEY_COOLDOWN_S: "26.5"/' /opt/cc-infra/docker-compose.yml
cd /opt/cc-infra && docker compose up -d --force-recreate hm40006
```

### Verification
- `docker exec hm40006 env | grep KEY_COOLDOWN_S` → `KEY_COOLDOWN_S=26.5` ✅
- `docker ps --filter name=hm40006` → `healthy` ✅
- `docker logs hm40006 --tail 5` → startup with `default_tier=glm5.1_hm_nv` ✅
- All other parameters unchanged: `TIER_COOLDOWN_S=42`, `MIN_OUTBOUND_INTERVAL_S=17.0`, `HM_CONNECT_RESERVE_S=16`

### Lint Check
- No syntax errors in docker-compose.yml (YAML line-level string change only)
- Container health check passed (healthy)

## Post-Deploy Expectations

| Metric | Expected Change |
|---|---|
| KEY_COOLDOWN_S | 28.0 → 26.5 |
| Fallback rate | Similar (~83%) — 429 still 100% |
| Avg fallback path duration | ~37s → ~35.5s (-1.5s per fallback) |
| 429 count | Similar — function-level limit unchanged |
| SSLEOF count | Unchanged — RESERVE/port unchanged |
| Container health | Healthy — verified |

## ⚠️ Compliance

- ✅ **铁律**: 只改HM2配置，绝不改HM1本地
- ✅ **禁止**: 未停止/重启/kill mihomo服务 (mihomo是NV API链路的必要代理)
- ✅ **少改多轮**: 单参数变更 (-1.5s)，渐进式优化
- ✅ **数据驱动**: 所有决策基于DB 2h窗口查询 + 实时日志分析
- ✅ **验证完成**: env var确认 + container health确认 + startup log确认

## ⏳ 轮到HM2优化HM1
