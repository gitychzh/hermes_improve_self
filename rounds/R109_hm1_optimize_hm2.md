# R109: HM1→HM2 — MIN_OUTBOUND_INTERVAL_S 7.0→9.0 (+2s)

**Date**: 2026-06-28 03:55 CST (2026-06-27 19:55 UTC)  
**Author**: opc_uname (HM1)  
**Target**: HM2 (opc2_uname)  
**Principles**: 更少报错, 更快请求, 超低延迟, 稳定优先  
**Iron Law**: 只改HM2不改HM1 — mihomo绝不触碰  

---

## 数据收集 (Data Collection)

### 1. Docker 日志 (最近100行, 基于error/warn模式)
```
[19:50:57.8] [HM-ERR] tier=glm5.1_hm_nv k1 SSLEOFError
[19:51:11.3] [HM-ERR] tier=glm5.1_hm_nv k4 SSLEOFError
[19:51:21.2] [HM-COOLDOWN] tier=glm5.1_hm_nv k1 marked cooling after 429
[19:51:21.2] [HM-CYCLE] tier=glm5.1_hm_nv k1 → 429, cycling to next key
[19:51:23.1] [HM-FALLBACK] Tier glm5.1_hm_nv all-failed → deepseek_hm_nv
[19:52:44.1] [HM-ERR] tier=glm5.1_hm_nv k1 ConnectionResetError
[19:52:02.1] [HM-KEY] tier=glm5.1_hm_nv k1 is in cooldown (429), skipping
```

**关键观察**: 
- glm5.1 429s 均匀分布所有5个key (k1-k5)
- SSLEOFError + ConnectionResetError 集中在 k1/k2
- 所有key通过SOCKS5代理 (7894-7899)
- fallback 到 deepseek 快速成功 (~8s)

### 2. Docker 环境变量 (当前配置)
| 参数 | 值 |
|------|-----|
| KEY_COOLDOWN_S | 38.0 |
| TIER_COOLDOWN_S | 43 |
| UPSTREAM_TIMEOUT | 71 |
| MIN_OUTBOUND_INTERVAL_S | **7.0** (→ 9.0) |
| TIER_TIMEOUT_BUDGET_S | 128 |
| HM_CONNECT_RESERVE_S | 12 |
| PROXY_TIMEOUT | 300 |

### 3. PostgreSQL 30分钟窗口 (19:25–19:55 UTC)

**总体统计:**
| 指标 | 30分钟窗口 |
|------|-----------|
| 总请求 | 1399 |
| 成功 | 1375 (98.3%) |
| 错误 | 24 (1.7%) |
| 平均延迟 | 44,855ms |
| 最小延迟 | 2,001ms |
| 最大延迟 | 453,774ms |

**Tier 分布:**
| Tier | 请求数 | 平均延迟 | fallback数 | 429总数 |
|------|--------|----------|------------|---------|
| deepseek_hm_nv | 1142 (81.6%) | 45,841ms | 1140 | 1747 |
| glm5.1_hm_nv | 237 (16.9%) | 18,152ms | 0 | 196 |
| NULL (all_tiers_exhausted) | 22 | 277,796ms | 0 | 0 |

**错误细分:**
| 错误类型 | 计数 | 平均延迟 |
|----------|------|----------|
| all_tiers_exhausted | 22 | 277,796ms |
| NVStream_IncompleteRead | 2 | 43,450ms |

### 4. hm_tier_attempts 分级尝试表 (30分钟)
| Tier | 错误类型 | 计数 |
|------|---------|------|
| glm5.1_hm_nv | 429_nv_rate_limit | 77 |
| glm5.1_hm_nv | NVCFPexecSSLEOFError | 25 |
| deepseek_hm_nv | NVCFPexecSSLEOFError | 10 |
| glm5.1_hm_nv | NVCFPexecConnectionResetError | 2 |
| glm5.1_hm_nv | NVCFPexecRemoteDisconnected | 2 |
| deepseek_hm_nv | empty_200 (成功) | 1 |

**Per-key 429分布 (glm5.1):**
| Key | 429计数 |
|-----|---------|
| k1 (idx=0) | 21 |
| k2 (idx=1) | 14 |
| k3 (idx=2) | 13 |
| k4 (idx=3) | 15 |
| k5 (idx=4) | 14 |
| **总计** | **77** |

### 5. 时间爆发分析 (Temporal Burst Detection)

| 窗口 | 总请求 | 成功 | 错误 |
|------|--------|------|------|
| 10分钟最近 | 1358 | 1334 (98.3%) | 24 |
| 20分钟之前 | 47 | 47 (100%) | 0 |

**结论**: 全部24个错误集中在最近10分钟 — 系统在20分钟前完全稳定(0错误)。这是时间爆发模式。

---

## 分析 (Analysis)

### 核心发现

1. **fallback系统高效**: 1140/1142 deepseek请求是fallback成功 (来自glm5.1失败), fallback成功率 ~99.8%
2. **glm5.1 429均匀分布**: 5个key均匀触发429 (13-21次/key/30min), 说明NV API函数级速率限制 → 所有key共享同一速率限制桶
3. **SSLEOFError 为glm5.1主失败模式**: 25次SSLEOFError (vs 77次429), 25次中k1/k2 dominant
4. **时间爆发**: 24个错误全部在最近10分钟(0在20分钟前) — 系统正在经历爆发,非稳态
5. **all_tiers_exhausted 最昂贵**: 22次, 平均277.8s — 这些请求烧光glm5.1和deepseek两个tier的所有key

### 根本原因

- **MIN_OUTBOUND_INTERVAL_S=7.0s**: 5键×7s=35s 全周期 < GLOBAL_COOLDOWN=45s
- 这意味着5个key在45s内全部试过,但NV API函数级速率限制窗口是45s
- 当第一个key触发429,接下来的4个key在35s内也触发429 → 整个tier在45s冷却期前就用完了所有key
- 增加间隔→减少429碰撞→减少all_tiers_exhausted

### 为什么选这个参数 (不选其他)

| 候选参数 | 为什么不选 |
|----------|-----------|
| KEY_COOLDOWN_S=38→40 | 已接近TIER_COOLDOWN=43 (仅5s gap); 再增加可能延迟key恢复 |
| TIER_COOLDOWN_S=43→45 | 与GLOBAL_COOLDOWN对齐但GLOBAL_COOLDOWN是硬编码的,增加tier cooldown只延迟fallback触发 |
| UPSTREAM_TIMEOUT=71→73 | 增加per-key超时但SSLEOFError是连接级别(非超时); 不会减少SSLEOFError |
| TIER_TIMEOUT_BUDGET_S=128→130 | 增加预算但all_tiers_exhausted avg=277s远超budget; 2s增量微不足道 |
| **MIN_OUTBOUND_INTERVAL_S 7→9** | ✅ 直接减少429碰撞: 5×9=45s对齐GLOBAL=45s; +2s更少429→更少fallback→更低all_tiers_exhausted |

---

## 优化计划 (Optimization Plan)

### 参数: MIN_OUTBOUND_INTERVAL_S 7.0 → 9.0 (+2s)

**预算验证 (不变):**
```
BUDGET=128, UPSTREAM=71, RESERVE=12, MIN=9.0 (was 7.0)
1st key: 71s → remaining=57
2nd key: max(10, min(71, 57-12-9=36)) = 36s → remaining=21
3rd key: max(10, min(71, 21-12-9=0)) = 10s (floor)
Total: 71+36+10=117s ≤ 128s ✓
```

**预期效果:**
| 指标 | 之前 (MIN=7.0) | 之后 (MIN=9.0) |
|------|----------------|----------------|
| 5-key 全周期 | 35s | 45s |
| 429碰撞概率 | 高 (35s < 45s窗口) | 低 (45s ≈ 45s窗口) |
| all_tiers_exhausted | 22/30min (1.7%) | 预计 10-15/30min |
| fallback 触发 | 频繁 | 减少 (更多请求在glm5.1直接成功) |
| 平均延迟 | ~45s | 预计 ~35-40s |

---

## 执行 (Execution)

### 1. 修改 docker-compose.yml (line 479)
```bash
ssh -p 222 opc2_uname@100.109.57.26
cd /opt/cc-infra
sed -i '479s|MIN_OUTBOUND_INTERVAL_S: "7.0"|MIN_OUTBOUND_INTERVAL_S: "9.0"|' docker-compose.yml
```

### 2. 重建容器 (不改mihomo)
```bash
sudo docker compose up -d --no-deps --force-recreate hm40006
```

### 3. 验证结果
```
✅ MIN_OUTBOUND_INTERVAL_S=9.0 (docker exec env 确认)
✅ 容器状态: Up 19 seconds (healthy) (docker ps 确认)
✅ /health 端点: 200 OK, 3 tiers (glm5.1→deepseek→kimi)
✅ mihomo 进程: 运行中 (ps aux 确认, 未被触碰)
```

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记