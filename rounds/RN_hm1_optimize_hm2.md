# R118: HM1→HM2 — MIN_OUTBOUND_INTERVAL_S 7.5→9.0 (+1.5s)

## Principles
- 铁律:只改HM2不改HM1
- 单参数: MIN_OUTBOUND_INTERVAL_S
- 少改多轮: +1.5s (可逆, 可观察)
- mihomo绝不触碰 (NV API链路的必要代理)
- 更少报错更快的请求超低延迟稳定优先

## Data Collection (30-min Window, 2026-06-27 21:28–21:58)

### HM2 Environment (pre-change)
| Parameter | Value |
|-----------|-------|
| MIN_OUTBOUND_INTERVAL_S | **7.5** |
| KEY_COOLDOWN_S | **40** |
| TIER_COOLDOWN_S | **45** |
| UPSTREAM_TIMEOUT | **71** |
| TIER_TIMEOUT_BUDGET_S | **128** |
| HM_CONNECT_RESERVE_S | **16** |

### PostgreSQL Summary
```
Total: 92 | Success: 92 (100%) | Fallbacks: 36 (39.1%)
avg_ms: 16358 | p50: 12149 | p90: 28580 | p95: 48735 | max: 102276
Total 429s: 76 | 0 error_type (all successes)
```

### Tier Breakdown
| Tier | Requests | avg_ms | p90_ms | Fallbacks | 429s |
|------|----------|--------|--------|-----------|------|
| glm5.1_hm_nv | 56 | 15078 | 33049 | 0 | 31 |
| deepseek_hm_nv | 36 | 18350 | 28580 | 36 (100%) | 45 |

### Tier Attempts (Errors Only)
| Tier | Error Type | Count |
|------|-----------|-------|
| glm5.1_hm_nv | 429_nv_rate_limit | 54 |
| glm5.1_hm_nv | NVCFPexecSSLEOFError | 12 |
| glm5.1_hm_nv | NVCFPexecConnectionResetError | 2 |
| deepseek_hm_nv | NVCFPexecSSLEOFError | 6 |

### 429 Per-Key Distribution (glm5.1)
| Key | Count |
|-----|-------|
| k1 (idx=0) | 16 |
| k2 (idx=1) | 9 |
| k3 (idx=2) | 9 |
| k4 (idx=3) | 11 |
| k5 (idx=4) | 9 |

### Error Detail JSONL (all_429 patterns)
- 大量 `all_429: true` 事件: 5/5键同时返回429 (NV API函数级速率限制)
- 混合故障: SSLEOFError + 429, ConnectionResetError + 429
- 12× NVCFPexecSSLEOFError on glm5.1 (avg ~5s)

### Live Log Pattern
```
[21:54:54] k1 marked cooling after 429 → vx_cycle
[21:58:45] k1 is in cooldown (429), skipping
[21:59:07] k1 is in cooldown (429), skipping
[21:59:12] k2 SUCCESS on first attempt
[21:59:33] k2 SUCCESS on first attempt
[21:59:36] k3 SSLEOFError
[21:59:41] k4 SSLEOFError
[21:59:49] k5 SUCCESS after 2 cycle attempts
```

## Analysis

### Root Cause
HM2的glm5.1_hm_nv tier在30分钟内经历54次NV API 429 (全键均等分布). 所有5个NV键共享同一函数级速率限制桶 (NVCF平台按Function ID限流). 当前MIN_OUTBOUND_INTERVAL_S=7.5s过于激进 — 约8 req/min的请求速率触发NV API爆发限流. 结果: 36次fallback (39.1%), 全部fallback到deepseek并成功.

### Why MIN_OUTBOUND_INTERVAL_S
- **54 NV 429 in 30 min** → 平均1.8/min. 当前7.5s间隔 = ~8 req/min → 超出NV API爆发阈值
- **9.0s间隔** → ~6.7 req/min → 降低30%请求密度 → 给NV API速率限制桶更多恢复时间
- **5键周期代价**: 5×9.0=45s = 恰好GLOBAL_COOLDOWN=45s (完美对齐)
- **TIER_COOLDOWN_S=45s** 保持不变 → 9.0s间隔与45s cooldown对齐 (不冲突)
- **36 fallbacks × avg 18350ms** = ~660s累积fallback时间 → 减少fallback量直接降低系统总开销

### Why Not Other Parameters
- KEY_COOLDOWN_S=40: 已接近GLOBAL_COOLDOWN=45s (仅5s间隙), 再增加会超过GLOBAL→无意义
- TIER_COOLDOWN_S=45: 已经等于GLOBAL_COOLDOWN=45s, 再增加可能会 < GLOBAL (配置低于硬编码)
- UPSTREAM_TIMEOUT=71: 已经足够宽松 (p95=48.7s << 71s), 减少会截断慢请求
- TIER_TIMEOUT_BUDGET_S=128: 预算充足 (实际周期~12-17s, 远低于128s)
- HM_CONNECT_RESERVE_S=16: 之前已+2s, 需要观察效果后再调整

### Budget Verification
```
5键周期有效预算 = TIER_TIMEOUT_BUDGET_S - HM_CONNECT_RESERVE_S
= 128 - 16 = 112s (vs 实际5键周期 ~12-17s)
```
112s预算远大于实际5键周期 → 当前瓶颈是NV API速率限制, 不是预算不够.

### 429 Impact: 39.1% fallback rate → 目标 30% (减少~9个百分点)
36 fallbacks中每个都消耗约18.3s → 减少fallback = 减少总延迟 = 更快请求

## Execution

### Change Applied
```bash
ssh -p 222 opc2_uname@100.109.57.26 \
  "cd /opt/cc-infra && \
   sed -i '479s|MIN_OUTBOUND_INTERVAL_S: \"7.5\"|MIN_OUTBOUND_INTERVAL_S: \"9.0\"|' \
   docker-compose.yml && \
   docker compose up -d --build --force-recreate hm40006"
```

### Verification
1. **Env confirmation**: `docker exec hm40006 env | grep MIN_OUTBOUND_INTERVAL_S` → **9.0** ✓
2. **Container health**: `docker ps --filter name=hm40006` → **Up (healthy)** ✓
3. **Health endpoint**: `curl http://localhost:40006/health` → **200 OK**, tiers: [glm5.1, deepseek, kimi], default: glm5.1 ✓
4. **Mihomo running**: `ps aux | grep mihomo` → **PID 2008535, 49h uptime** ✓

## Expected Effects

| Metric | Before | Expected After |
|--------|--------|----------------|
| MIN_OUTBOUND_INTERVAL_S | 7.5s | **9.0s** (+1.5s) |
| Req/min | ~8 | ~6.7 (-16%) |
| 5键周期代价 | 37.5s | **45s** (= GLOBAL_COOLDOWN) |
| 30min NV 429 (glm5.1) | 54 | ~40-45 (-17-26%) |
| 30min Fallbacks | 36 (39.1%) | ~24-28 (26-30%) |
| avg latency | 16358ms | ~14000-15000ms |

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记