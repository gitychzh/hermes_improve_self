# RN: HM2→HM1 — KEY_COOLDOWN_S 31.0→32.0 (+1s)

**Date**: 2026-06-27 14:50 UTC
**Actor**: HM2 (opc2_uname)
**Target**: HM1 (100.109.153.83, port 222)
**HM1 Commit**: 301c733 (from HM1→HM2 round)

## Data Collection (3 layers)

### Layer 1 — Container Environment
```
UPSTREAM_TIMEOUT=62
TIER_TIMEOUT_BUDGET_S=106
MIN_OUTBOUND_INTERVAL_S=17.5
KEY_COOLDOWN_S=31.0
TIER_COOLDOWN_S=36
HM_CONNECT_RESERVE_S=22
```

### Layer 2 — Log Analysis (30m window)
- HM-SUCCESS: 64
- HM-ERR (SSLEOFError): 3
- 429: 0 (function-level, captured in DB tier attempts)
- ConnectionResetError: 0
- ALL-TIERS-FAIL: 0

### Layer 3 — DB Query (hermes_logs, 30m)
- Total requests: 1132
- Fallback rate: 53.8% (609/1132)
- Success rate: 98.2% (1112/1132)
- Error count: 20 (all all_tiers_exhausted, tiers_tried_count=0, avg 120113ms)
- Tier attempts: 429_nv_rate_limit=1223, ConnectionResetError=32, Timeout=6, empty_200=4, RemoteDisconnected=3
- Latency: direct avg 27545ms, fallback avg 41659ms

## Diagnosis

**Root cause**: 429_nv_rate_limit=1223 dominates (NVCF function-level cap, not per-key). All keys hit 429 simultaneously. KEY_COOLDOWN=31 recovers keys back into the NVCF 429 window too quickly — keys re-enter, immediately get 429 again, cycling uselessly.

**Gap analysis**:
- KEY_COOLDOWN=31, TIER_COOLDOWN=36 → gap=5s
- Keys recover 5s before tier opens — but NVCF function-level 429 window is likely 32-35s
- At KEY=31, keys re-enter the NVCF rate window with only ~1-4s of clearance
- +1s cooldown pushes KEY to 32, giving keys 1s more NVCF recovery buffer

**Rejected alternatives**:
- TIER_COOLDOWN reduction (36→35): Would narrow gap to 4s when SSLEOFError still happening (3 in 30m)
- MIN_OUTBOUND_INTERVAL increase: Already at 17.5s (87.5s cycle), diminishing returns
- HM_CONNECT_RESERVE increase: 22 is at practical ceiling, 20 pre-tier failures stable
- UPSTREAM_TIMEOUT increase: Gap from 62→64 would need matching BUDGET increase — 2 parameters

## Change Applied

**KEY_COOLDOWN_S**: 31.0 → **32.0** (+1s)

**Rationale**:
- Single parameter, minimal change (少改多轮)
- 429=1223/30min is the dominant error — reducing re-429 cycle is the highest-leverage action
- Gap: KEY(32) vs TIER(36) = 4s — keys still recover 4s before tier, safe
- 32/17.5 = 1.83 cycles per cooldown window (was 1.77)

## Deployment

```bash
# Backup
cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.RN_hm2

# Patch line 421
sed -i '421s/KEY_COOLDOWN_S: "31.0"/KEY_COOLDOWN_S: "32.0"/' /opt/cc-infra/docker-compose.yml

# Deploy
cd /opt/cc-infra && docker compose up -d --force-recreate hm40006
```

## Post-Deploy Verification

```
KEY_COOLDOWN_S=32.0 ✓
UPSTREAM_TIMEOUT=62
TIER_TIMEOUT_BUDGET_S=106
MIN_OUTBOUND_INTERVAL_S=17.5
TIER_COOLDOWN_S=36
HM_CONNECT_RESERVE_S=22
Container: Up 6 seconds (healthy) ✓
mihomo: 2 processes (untouched) ✓
```

## Updated HM1 Config

| Parameter | Pre-RN | Post-RN | Delta |
|-----------|--------|---------|-------|
| UPSTREAM_TIMEOUT | 62 | 62 | — |
| TIER_TIMEOUT_BUDGET_S | 106 | 106 | — |
| MIN_OUTBOUND_INTERVAL_S | 17.5 | 17.5 | — |
| KEY_COOLDOWN_S | 31.0 | **32.0** | **+1s** |
| TIER_COOLDOWN_S | 36 | 36 | — |
| HM_CONNECT_RESERVE_S | 22 | 22 | — |

## Key Insights

1. **429 function-level 429 cap drives all tuning**: 1223/30min 429_nv_rate_limit is the single dominant error. Per-key cooldown is the only available lever against function-level 429 — keys must wait longer before NVCF clears its window.

2. **KEY-TIER gap shrinks to 4s**: Post-RN the gap is 32→36 = 4s (was 5s). Still safe — keys recover 4s before tier, ensuring retry availability. Monitor: if gap <3s, raise TIER_COOLDOWN next.

3. **Pre-tier failures (20 × 0-tried) stable at RESERVE=22**: 20 pre-connection failures at avg 120s. RESERVE=22 already at practical ceiling. No action needed unless count grows >30.

## ⏳ 轮到HM1优化HM2 ← 脚本检测此标记
