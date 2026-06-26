# R77: HM2→HM1 — TIER_COOLDOWN_S 74→72 (-2s)

**时间**: 2026-06-27 02:20 UTC  
**执行者**: HM2 (opc2_uname)  
**方向**: HM2优化HM1  
**上一轮**: R76 (HM2→HM1, UPSTREAM_TIMEOUT 60→62)

## 📊 采集数据 (HM1 hm40006, 最近30分钟)

### 容器环境 (docker exec hm40006 env)
- UPSTREAM_TIMEOUT=62 (R76: 60→62)
- TIER_TIMEOUT_BUDGET_S=104 (R69: 102→104)
- MIN_OUTBOUND_INTERVAL_S=14.5 (R67: 14.0→14.5)
- KEY_COOLDOWN_S=30.0 (R71: 32→30, 与HM2持平)
- TIER_COOLDOWN_S=74 (R75: 76→74)
- HM_CONNECT_RESERVE_S=22 (R29: 21→22)

### 请求分布 (hm_requests, 30min)
| 指标 | 数量 | 占比 |
|--------|------|------|
| 总请求 | 1,207 | 100% |
| 回退请求 | 781 | 64.7% |
| 直接成功 | 426 | 35.3% |

### Error Breakdown (hm_tier_attempts, 30min)
| Error Type | Count | Avg Elapsed |
|--------|------|-------------|
| 429_nv_rate_limit | 887 | ~2s |
| NVCFPexecTimeout | 104 | 28,662ms |
| NVCFPexecConnectionResetError | 68 | 2,854ms |
| NVCFPexecRemoteDisconnected | 6 | 2,381ms |
| budget_exhausted_after_connect | 5 | 2,361ms |

### Per-Key 429 Distribution (glm5.1_hm_nv)
| Key | 429 Count |
|---|---|
| k0 | 218 |
| k1 | 180 |
| k2 | 172 |
| k3 | 160 |
| k4 | 152 |

- 分布均匀: max/min = 218/152 = 1.43x — 函数级429限速

### 429 Cycle Stats (key_cycle_429s)
| Cycles | Requests |
|--------|----------|
| 0 | 875 (72.5%) |
| 1 | 108 |
| 2 | 35 |
| 3 | 22 |
| 4 | 51 |
| 5 | 91 |
| 6 | 17 |
| 7 | 4 |
| 8 | 2 |
| 10 | 1 |
| 11 | 1 |

- **429 cycle rate = 27.4%** (331/1206 requests have ≥1 429 cycle)
- 平均**3.6次429**/受影响的请求

### Deepseek Timeout Bucket Distribution
| Bucket | Events |
|--------|--------|
| <20s | 30 |
| 20-25s | 4 |
| 50-55s | 2 |
| 55-60s | 2 |
| 60-62s | 4 |
| >62s | 6 |

- 总timeout=104, 分布: <20s=30(28.8%), >62s=6(5.8%)
- 边界完成窗口分散, 无单桶主导

### Tier 请求分布
- glm5.1_hm_nv: 1,013 attempts (主tier, 但所有均为429失败)
- deepseek_hm_nv: 52 attempts (回退tier)

### 0-tier Pre-tier Failures
- 0-tier 连接失败: 0 (完全消除, 自R60起持续)
- tiers_tried_count=0: 0 requests

## 🔧 诊断分析

### 核心问题
1. **429主导 86.9%** — glm5.1主tier函数级429限速, 无法通过key rotation改善
2. **回退率 64.7%** — 已有改善(R76: 67%→R77: 64.7%), 但仍有较大空间
3. **TIER_COOLDOWN=74** — 在下降轨迹中(R73:78→R75:76→R77:72), 每次-2s加速glm5.1恢复
4. **ConnectionResetError=68** — 略低于R67触发阈值(71), 但持续存在

### 优化选择
**TIER_COOLDOWN_S: 74 → 72 (-2s)**

选择理由:
- UPSTREAM=62已处于高位, 继续UPSTREAM→64会推第2次到18s(硬限)
- BUDGET=104已足够, 不需要扩展
- TIER_COOLDOWN是当前最高杠杆参数 — 直接加速glm5.1从全键429恢复
- 回退率从67.5%(R75标记)→64.7%(R77实测) 已见改善, 继续-2s可进一步降低

**机制**:
- TIER_COOLDOWN从74s降至72s, glm5.1在所有5键429风暴后更快恢复重试
- 减少全键429后的等待时间 (74s→72s = -2.7%)
- 更多新的glm5.1请求有机会在下一个rate-limit窗口直接尝试(而非跳过到回退)
- 预期回退率从64.7%降至~60-62%, 直接成功率上升至~38-40%

**预算计算 (当前值)**:
- UPSTREAM=62, BUDGET=104, RESERVE=22
- 1st attempt=min(62, 104-22=82)=62s; remain=104-62=42
- 2nd attempt=max(10, min(62, 42-22=20))=20s — 安全
- TIER_COOLDOWN不影响以上计算, 仅影响层级间转换

## ✅ 执行结果

### SSH操作
```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R77'

# 改值
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && sed -i "422s/\"74\"/\"72\"/" docker-compose.yml'

# 改注释
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '422s/# R75: .../# R77: .../' docker-compose.yml"
```

### 部署验证
- `docker compose up -d hm40006` — 容器重建成功, healthy ✅
- `docker exec hm40006 env | grep TIER_COOLDOWN_S` → **72** ✅
- `docker ps --format '{{.Names}} {{.Status}}'` → hm40006 Up healthy ✅
- mihomo未触碰 ✅

### 运行确认
| 参数 | Before | After | Verified |
|------|--------|-------|----------|
| TIER_COOLDOWN_S | 74 | **72** | ✅ |
| UPSTREAM_TIMEOUT | 62 | 62 (不变) | ✅ |
| TIER_TIMEOUT_BUDGET_S | 104 | 104 (不变) | ✅ |
| MIN_OUTBOUND_INTERVAL_S | 14.5 | 14.5 (不变) | ✅ |
| KEY_COOLDOWN_S | 30.0 | 30.0 (不变) | ✅ |
| HM_CONNECT_RESERVE_S | 22 | 22 (不变) | ✅ |

## 📈 预期影响

| 指标 | 当前 | 预期 | 评级 |
|--------|------|------|------|
| 429 数量 | 887/30min | ↓ (更少等待 = 更多尝试) | ✅ |
| 回退率 | 64.7% | ↓ → 60-62% | ✅ |
| 直接成功率 | 35.3% | ↑ → 38-40% | ✅ |
| ConnectionResetError | 68 | 稳定(sub-threshold) | ⚠️ |
| 0-tier | 0 | 0 (保持) | ✅ |
| Deepseek Timeout | 104 | 稳定 | ✅ |

## 🔒 铁律确认
- ✅ 只改HM1配置(docker-compose.yml, TIER_COOLDOWN_S), 不触HM2本地
- ✅ mihomo服务未停/未重启/未kill
- ✅ 少改多轮(单参数 -2s)
- ✅ 基于30min数据: 回退率64.7% → 目标60%以下
- ✅ 容器健康验证通过

## ⏳ 轮到HM1优化HM2