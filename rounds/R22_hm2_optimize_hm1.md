# R22: HM2优化HM1 — HM_CONNECT_RESERVE_S 12→14 (+2s SOCKS5+SSL)

**日期**: 2026-06-26 07:05 UTC  
**执行者**: HM2 (opc2_uname)  
**目标**: HM1 (100.109.153.83 hm40006)  
**前轮**: R21 (HM_CONNECT_RESERVE_S 10→12)  
**策略**: 少改多轮 — 单参数变更

---

## 1. 数据收集 (30min窗口 ~06:35-07:05 UTC)

### 1a. 日志错误/警告统计
- `docker logs hm40006 --tail 100 | grep -ciE "(error|warn|fail)"` = **25**
- 日志模式: 每~40-90s一波glm5.1全key 429→TIER-SKIP→deepseek fallback成功

### 1b. DB错误分布 (hm_tier_attempts, 30min)

| error_type | cnt | avg_elapsed_ms |
|---|---|---|
| 429_nv_rate_limit | 502 | — |
| NVCFPexecTimeout | 133 | 27,682 |
| NVCFPexecConnectionResetError | 3 | 1,748 |
| empty_200 | 2 | — |
| NVCFPexecRemoteDisconnected | 1 | 7,577 |

### 1c. 层级分布 (hm_tier_attempts)

| tier | cnt |
|---|---|
| glm5.1_hm_nv | 520 (429占502) |
| deepseek_hm_nv | 118 (Timeout 117) |
| kimi_hm_nv | 3 |

### 1d. 回退率

| 指标 | 值 |
|---|---|
| 总请求 | 1,048 |
| 回退请求 | 857 |
| 回退率 | **81.8%** |

### 1e. 0-tier pre-tier失败 (all_tiers_exhausted, tiers_tried_count=0)

| 指标 | 值 |
|---|---|
| 失败数 | **34** |
| 平均耗时 | 74,104ms |
| 占总请求 | 3.2% |

### 1f. deepseek回退成功延迟分布

| 区间 | 数量 | 占比 |
|---|---|---|
| 0-10s | 399 | 47.7% |
| 10-20s | 282 | 32.9% |
| 20-30s | 66 | 7.9% |
| 30-50s | 49 | 5.9% |
| 50s+ | 60 | 7.2% |

### 1g. glm5.1 per-key 429分布

| key_idx | 429_count | timeout_count |
|---|---|---|
| k0 | 105 | 0 |
| k1 | 98 | 2 |
| k2 | 101 | 5 |
| k3 | 98 | 5 |
| k4 | 100 | 3 |

完全均匀分布 — 确认NVCF function ID全局限速，非per-key可修。

### 1h. deepseek per-key错误分布

| key_idx | timeout | empty_200 | remote_disconnect |
|---|---|---|---|
| k0 | 21 | — | — |
| k1 | 28 | — | 1 |
| k2 | 28 | — | — |
| k3 | 18 | 1 | — |
| k4 | 20 | 1 | — |

### 1i. 运行容器参数 (docker exec hm40006 env)

| 参数 | R21值 | R22值 |
|---|---|---|
| UPSTREAM_TIMEOUT | 40 | 40 (不变) |
| TIER_TIMEOUT_BUDGET_S | 80 | 80 (不变) |
| MIN_OUTBOUND_INTERVAL_S | 10.0 | 10.0 (不变) |
| KEY_COOLDOWN_S | 38.0 | 38.0 (不变) |
| TIER_COOLDOWN_S | 90 | 90 (不变) |
| HM_CONNECT_RESERVE_S | 12 | **14** |

---

## 2. 诊断

### 核心瓶颈: 0-tier pre-tier连接级失败

R19-R21的 `HM_CONNECT_RESERVE_S` 递增轨迹:

| 轮次 | RESERVE值 | 0-tier失败数 | 减少量 |
|---|---|---|---|
| R19前(RESERVE=5) | 5 | 42 | — |
| R20后(RESERVE=10) | 10 | 37 | -5 |
| R21后(RESERVE=12) | 12 | 34 | -3 |
| R22目标(RESERVE=14) | 14 | ~29-30 | -4~-5 |

**趋势**: 每+2s RESERVE减少~3-5个0-tier失败。线性递减模式成立。

### 其他观察
1. **glm5.1 100% 429**: 502次全为429，5 key完全均匀（98-105/key）。NVCF function ID全局限速不可通过key rotation修复。
2. **deepseek是实际承压tier**: 118次timeout但key cycling吸收了绝大多数 — 811次fallback成功(tiers_tried_count=2, avg 13.9s)。
3. **回退率上升**: 81.8% (vs R21的80.4%)，因为glm5.1 429更频繁了。这不是参数问题，是NVCF限速特征。
4. **新增 NVCFPexecRemoteDisconnected**: 1次(k1)，7,577ms。偶发远程断连，不影响整体。
5. **50s+延迟占7.2%**: 60个请求。部分来自0-tier失败(34个avg 74s)和极少数deepseek超长请求。

### 为什么继续HM_CONNECT_RESERVE而非其他参数
- 0-tier失败是唯一下降趋势可追踪的指标 (42→37→34)
- UPSTREAM_TIMEOUT=40已到上限(40s足够深seek完成)
- KEY_COOLDOWN=38已接近UPSTREAM(40)，继续提升可能导致预算浪费
- TIER_COOLDOWN=90是practical下限(5key×10s=50s cycle < 90s)
- MIN_INTERVAL=10.0已充分压制429碰撞

---

## 3. 优化变更

| 参数 | 变更前 | 变更后 | 理由 |
|---|---|---|---|
| HM_CONNECT_RESERVE_S | 12 | **14** | +2s SOCKS5+SSL连接预留; 0-tier pre-tier失败持续减少(34→目标~29-30); 延续R19-R21轨迹; 少改多轮 |

**不变参数**: UPSTREAM_TIMEOUT=40, TIER_BUDGET=80, MIN_INTERVAL=10.0, KEY_COOLDOWN=38.0, TIER_COOLDOWN=90

---

## 4. 执行记录

```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R22'

# 修改line 451: 值12→14 + 更新注释
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && \
  sed -i '451s/\"12\"/\"14\"/' docker-compose.yml && \
  sed -i '451s/# R21: HM2优化.*$/# R22: HM2优化 — 12→14: +2s SOCKS5+SSL连接预留; 0-tier pre-tier连接失败持续减少(R21后34个→目标~29); 少改多轮/' docker-compose.yml"

# 部署
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'

# 验证 (等8s)
docker exec hm40006 env | grep HM_CONNECT_RESERVE_S → HM_CONNECT_RESERVE_S=14 ✓
docker ps → hm40006 Up 27 seconds (healthy) ✓
```

---

## 5. 预期效果

| 指标 | R22前 | R22后预期 |
|---|---|---|
| 0-tier pre-tier失败 | 34 | ~29-30 (-4~-5) |
| 回退率 | 81.8% | ~81% (微降) |
| deepseek fallback延迟 | 47.7% <10s | 保持 |
| 整体成功率 | 96.8% | ~97%+ |

**核心预期**: HM_CONNECT_RESERVE +2s (12→14) 使SOCKS5+SSL连接预留更充分，0-tier失败持续沿42→37→34→~30轨迹递减。

---

## 6. 风险与观察

- **RESERVE上限**: 14s意味着TIER_BUDGET中预留14s用于连接握手，剩余66s(80-14)给key cycling。当前2×UPSTREAM=80s，若RESERVE继续增加，需考虑TIER_BUDGET同步提升(80→85)。但14s尚在安全范围内。
- **0-tier失败底部**: 若RESERVE=14后0-tier失败仍>25，表明部分失败来自非握手原因(mihomo proxy健康、NVCF infra级断连)。那时需考虑其他策略。
- **glm5.1无望修复**: 429完全均匀(per-function限速)，key rotation无法改善。回退率将长期保持80%+。

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记
