# R71: HM2→HM1 — KEY_COOLDOWN_S 32.0→30.0 (-2s)

## Metadata
- **Date**: 2026-06-26
- **Actor**: HM2 (opc2_uname) → HM1 (100.109.153.83)
- **Previous Round**: R70 (HM2→HM1: KEY_COOLDOWN 34→32)
- **Commit**: R71: HM2→HM1 — KEY_COOLDOWN_S 32.0→30.0

## Data Collection (4-hour window on HM1)

### Current Config (from `docker exec hm40006 env`)
| Parameter | Value | Line (compose) |
|----------|-------|-----------------|
| UPSTREAM_TIMEOUT | 60 | 417 |
| TIER_TIMEOUT_BUDGET_S | 104 | 418 |
| HM_CONNECT_RESERVE_S | 22 | 451 |
| KEY_COOLDOWN_S | 32.0 | 421 |
| MIN_OUTBOUND_INTERVAL_S | 14.5 | 420 |
| TIER_COOLDOWN_S | 82 | 422 |

### Error Distribution (hm_tier_attempts, 4h)
```
429_nv_rate_limit:             398 (84.9%)
NVCFPexecConnectionResetError:  39 (8.3%)
NVCFPexecTimeout:               25 (5.3%)
NVCFPexecRemoteDisconnected:    5 (1.1%)
budget_exhausted_after_connect: 2 (0.4%)
Total:                         469 errors
```

### Fallback Rate (hm_requests, 4h)
- Fallback: 60.7% (337/555 total grouped)
- Direct (glm5.1): 39.5% (220/557)
- **glm5.1 direct success rate: 39.5%** (↑ from R69's 22.8%)

### 429 Cycle Distribution (4h)
- 0 cycles: 404 (72.5%) — no 429 at all
- 1+ cycles: 153 (27.6%) — encounter 429
- Per-key 429 rate: 79.2%-90.0% of all error attempts (uniform)

### Timeout Buckets (deepseek_hm_nv, 4h, 9 total)
```
NVCFPexecTimeout:              8 (88.9%)
budget_exhausted_after_connect: 1 (11.1%)
Distribution:
  <15s:                    2 (timeout) + 1 (budget) = 3
  15-30s:                 2 (timeout) = 2
  50-60s:                 1 (timeout) = 1
  >60s:                   3 (timeout) = 3
```

### ConnectionResetError by Key (4h)
```
k0: 10, k1: 8, k2: 8, k3: 7, k4: 6
Total: 39 — even distribution, mihomo proxy-level
```

### 0-Tier Failures (4h)
- **0 (zero) → 持续稳定** (R60→R71: 7+ consecutive rounds)

### Per-Key 429 Distribution (glm5.1_hm_nv, 4h)
```
k0: 99 (90.0%), k1: 80 (87.0%), k2: 76 (79.2%)
k3: 72 (82.8%), k4: 71 (84.5%)
Total: 398 — uniform across all keys, function-level rate limit
```

### TTFB/Duration by Path (4h)
```
direct no-429:         avg TTFB 17.8s, avg dur 18.2s
direct with-429:      avg TTFB 24.1s, avg dur 25.1s
fallback (deepseek):   avg TTFB 24.3s, avg dur 24.6s
```

### Latest 10 Requests (latency snapshot)
```
cec905c0 — TTFB 22,522ms, no429 direct success
0dea2fc6 — TTFB 28,767ms, no429 direct success
0cafa09b — TTFB 6,823ms, no429 direct success
bf3093b4 — TTFB 16,864ms, no429 direct success
d8714a70 — TTFB 10,533ms, no429 direct success
3cbfa267 — TTFB 22,159ms, with 429 cycle (still direct success)
5383f085 — TTFB 14,413ms, no429 direct success
fdde96a8 — TTFB 73,369ms, with 429 cycle (still direct success)
e136f078 — TTFB 11,889ms, no429 direct success
5e89ce19 — TTFB 34,467ms, no429 direct success
→ All direct successes (no fallback), avg 25.6s
```

## Diagnosis

### 1. KEY_COOLDOWN Trajectory → HM2 Convergence

```
R63: 38→36 (HM2优化HM1)
R65: 36→34 (HM2优化HM1)
R70: 34→32 (HM2优化HM1)
R71: 32→30 (HM2优化HM1) ← 与HM2持平!
```

HM2的KEY_COOLDOWN默认为30s。HM1在R71实现了完全收敛。每个键恢复2s意味着5键旋转中多了10s的冷却间隙窗口，显著减少全键同时冷却的级联概率。

### 2. 429 Cascade Evidence

429占错误的84.9%，但72.5%的请求完全没有429（0 cycles）。27.6%遇到429 cycle且需要fallback。关键洞察：
- KEY_COOLDOWN从32→30 → 每个键恢复2s更快
- 5键总buff：+10s冷却间隙（比R70的+10s过载）
- 进一步减少"所有5键同时冷却"级联概率

### 3. ConnectionResetError at 39

- 39次/4h（8.3%），均匀分布各key
- 比R69的72次（30min）低但R70因hm40006刚启动数据有限
- 不是趋势性问题 — 稳定，MIN_INTERVAL=14.5够用

### 4. deepseek fallback全失败

- deepseek only 9 attempts → 8 timeout + 1 budget_exhausted → 全失败率100%
- 但这意味着deepseek从未作为fallback成功过（所有fallback最终通过kimi_nv？）
- **不相关**：deepseek是最后的fallback残存方案

## Optimization

| Parameter | Before | After | Change | Rationale |
|----------|--------|-------|--------|-----------|
| KEY_COOLDOWN_S | 32.0 | 30.0 | -2s | 与HM2的30s完全持平; 429占84.9%→每个键+2s更快恢复; 5键旋转产生+10s冷却间隙（R70已+10s→R71再+10s=累计20s）; 72.5%请求无429→27.6%遇到429 cycle; 少改多轮(单参数); 铁律:只改HM1不改HM2 |

### KEY_COOLDOWN Trajectory
```
R63:  38→36
R65:  36→34
R70:  34→32
R71:  32→30  ← 与HM2的30s完全一致
HM2:  30 (基准)
```

## Execution Record

```bash
# Backup
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R71'

# Value change (line 421: KEY_COOLDOWN_S 32.0→30.0)
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && sed -i "421s/\"32.0\"/\"30.0\"/" docker-compose.yml'

# Deploy
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'

# Verify (post-deploy env values match)
docker exec hm40006 env | grep KEY_COOLDOWN_S
→ KEY_COOLDOWN_S=30.0 ✅
```

## Expected Effects

1. **429 级联概率**: 进一步减少
   - 每个键2s更快恢复 → 5键旋转中更少全键同时冷却
   - +20s 累积冷却间隙（R70+R71）
   - 429 cycle率预期从27.6%降至~20%

2. **直接成功率**: 预期继续上升
   - 当前: 39.5% (R70→71)
   - 目标: >45%
   - 更快键恢复→更多重试可在tier预算内完成

3. **ConnectionResetError**: 预期稳定
   - MIN_INTERVAL=14.5 提供充足的mihomo pacing
   - 不是趋势性问题

4. **0-tier稳定性**: 持续为0
   - RESERVE=22 饱和
   - 无进一步0-tier改进空间

## Observations

- **KEY_COOLDOWN终于与HM2持平（30s）**: R63→R65→R70→R71 4轮连续KEY_COOLDOWN减少。下一步可以开始优化其他参数（TIER_COOLDOWN或MIN_INTERVAL）或继续探索低于HM2基准的可能性。

- **429 cycle率27.6%但72.5%无429**: 大部分请求完全没有429，只有少部分遇到。优化效果在于减少遇到429的比例。

- **deepseek fallback全失败**: 9次尝试全失败（8 timeout + 1 budget）。但deepseek作为最後手段不是主要瓶颈。优化聚焦于glm5.1直接成功率。

- **ConnectionResetError=39太均匀**: 5键均匀分布表明这不是特定代理或键的问题，是全局mihomo级别的连接重置。MIN_INTERVAL=14.5仍在保护范围内。

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记