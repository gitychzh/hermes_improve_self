# R32: HM2优化HM1 — 确认BUDGET=90已部署, 继续R33: BUDGET 90→92

**日期**: 2026-06-26
**Actor**: HM2 (opc2_uname)
**Target**: HM1 (100.109.153.83:222)
**前一轮**: R32 (BUDGET 88→90, 已部署验证)
**策略**: 少改多轮, 继续TIER_BUDGET扩展路径到上界

---

## 1. 数据采集 (R33窗口, ~09:51 UTC)

### 1a. 日志模式 (最近100行, error/warn/fail/SSL)
- 匹配数: 15
- SSLEOFError: 2 (glm5.1 tier, SSL-RETRY吸收成功)
- 主要日志模式: glm5.1 TIER-SKIP → deepseek FALLBACK-SUCCESS (典型流程)

### 1b. 容器环境变量 (运行中值, R32部署后)
| 参数 | 值 | 来源 |
|------|-----|------|
| TIER_TIMEOUT_BUDGET_S | 90 | R32 |
| UPSTREAM_TIMEOUT | 40 | R18 |
| HM_CONNECT_RESERVE_S | 22 | R29 |
| KEY_COOLDOWN_S | 38.0 | R19 |
| MIN_OUTBOUND_INTERVAL_S | 10.0 | R17 |
| TIER_COOLDOWN_S | 90 | R17 |

### 1c. 错误分布 (30分钟窗口, hm_tier_attempts)
| error_type | cnt | avg_elapsed |
|------------|-----|-------------|
| 429_nv_rate_limit | 881 | — |
| NVCFPexecTimeout | 176 | 26950ms |
| NVCFPexecConnectionResetError | 3 | 779ms |
| NVCFPexecRemoteDisconnected | 1 | 7577ms |

### 1d. 请求路由统计 (hm_requests, 30分钟)
| 指标 | 值 |
|------|-----|
| 总请求 | 1375 |
| fallback数 | 1241 |
| fallback率 | 90.3% |
| 直接成功 | 134 (9.7%) |
| 错误请求 | 17 |
| 非fallback平均延迟 | 21180ms (est) |
| fallback平均延迟 | 16253ms (est) |

### 1e. 层级分布 (hm_tier_attempts)
| tier | cnt |
|------|-----|
| glm5.1_hm_nv | 896 |
| deepseek_hm_nv | 161 |
| kimi_hm_nv | 4 |

### 1f. 0-tier pre-tier连接失败
- **0-tier = 17** (与R26-R32一致, avg duration 105292ms)
- RESERVE=22饱和确认: 连续7轮(R26-R32) 0-tier=17不变

### 1g. glm5.1 429按key分布 (功能级429, 非per-key)
| key_idx | 429_count | timeout_count |
|---------|-----------|---------------|
| k0 | 179 | 0 |
| k1 | 175 | 1 |
| k2 | 179 | 5 |
| k3 | 176 | 4 |
| k4 | 177 | 2 |

→ 429均匀分布(175-179), 功能级429特性不变

### 1h. Deepseek NVCFPexecTimeout按key分布
| key_idx | timeout_count | 端口 |
|---------|---------------|------|
| k0 | 28 | 7894 |
| k1 | 40 | 7895 |
| k2 | 36 | 7896 |
| k3 | 27 | 7897 |
| k4 | 29 | 7899 |

→ k1(port 7895)最差(40次), 自R24以来稳定模式

### 1i. Deepseek NVCFPexecTimeout elapsed_ms分布
| bucket | cnt | pct |
|--------|-----|-----|
| <20s | 50 | 31.3% |
| 20-25s | 9 | 5.6% |
| 25-30s | 34 | 21.3% |
| 30-35s | 28 | 17.5% |
| 35-40s | 11 | 6.9% |
| >40s | 28 | 17.5% |

→ 25-30s区间仍有34次超时(21.3%), 2nd attempt headroom=28s部分覆盖此区间(25-28s)
→ >40s=28次 (budget耗尽, NVCF基础设施级超时)

### R32→R33 变化总结
| 指标 | R32 | R33 | Δ |
|------|-----|-----|---|
| 429 count | 856 | 881 | +25 (+2.9%) |
| NVCFPexecTimeout | 171 | 176 | +5 (+2.9%) |
| Total requests | 1360 | 1375 | +15 |
| Fallback rate | 89.6% | 90.3% | +0.7% |
| 0-tier | 17 | 17 | 0 |
| >40s deepseek | 26 | 28 | +2 |
| SSLEOFError | 1 | 2 | +1 |

---

## 2. 诊断

### 根因分析
1. **RESERVE=22完全饱和**: 0-tier=17连续7轮不变(R26-R32), 非handshake原因. RESERVE继续增加无边际收益.
2. **BUDGET=90已部署**: R32的+2s已生效. 2nd attempt=28s headroom, 但25-30s区间仍有34次超时(覆盖25-28s子区间). 余下28-30s子区间(约6-7次)仍未被覆盖.
3. **BUDGET扩展继续有效**: 当前轨迹R29(84)→R30(86)→R31(88)→R32(90). 2nd attempt headroom从22s→24s→26s→28s. 继续+2s到92(30s headroom), 覆盖25-30s全区间(34次).
4. **glm5.1 功能级429**: 881次429均匀分布5个key, NVCF函数级速率限制, 非key配置可解决.
5. **k1(port 7895)超时不均**: 40次vs平均32次(25%偏高), 自R24稳定模式, 暂无需介入.

### 证据链
- R32 BUDGET=90 → 2nd attempt=28s → 覆盖25-28s子区间, 未覆盖28-30s
- R33 data shows 25-30s bucket=34 unchanged; 28s headroom misses 28-30s portion
- >40s的28次超时 = UPSTREAM_TIMEOUT(40s)边界, budget耗尽, 无法通过headroom扩展解决
- SSLEOFError=2, 极低, SSL稳定性好

---

## 3. 优化变更

| 参数 | 变更前 | 变更后 | 理由 |
|------|--------|--------|------|
| TIER_TIMEOUT_BUDGET_S | 90 | 92 | +2s tier budget扩展2nd attempt headroom从28s→30s, 覆盖25-30s全区间(34次); RESERVE=22不变(饱和); 残余70s, 2nd attempt=30s headroom; 少改多轮(单参数变更); 继续R29-R32 BUDGET扩展路径; 到达BUDGET上界 |

**预算数学**: BUDGET=92, RESERVE=22 → 残余=70s, 1st attempt=40s(UPSTREAM_TIMEOUT), 2nd attempt=min(40, 70-22-40+22)=30s ← headroom+2s

**不变参数**: UPSTREAM_TIMEOUT=40, HM_CONNECT_RESERVE_S=22, KEY_COOLDOWN_S=38, MIN_OUTBOUND_INTERVAL_S=10, TIER_COOLDOWN_S=90

---

## 4. 执行记录

### 4a. 备份
```bash
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R33'
```

### 4b. 配置变更 (compose line 418)
```bash
# Value change: 90→92
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && sed -i "418s/\"90\"/\"92\"/" docker-compose.yml'
# Comment update: R32→R33
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '418s/# R32:.*$/# R33: HM2优化 — 90→92: +2s tier budget; RESERVE=22s饱和不变(7轮验证0-tier=17); 残余70s, 2nd attempt=30s headroom(覆盖25-30s全区间); deepseek >40s timeout=28次(2nd attempt budget耗尽); 少改多轮(单参数变更); 继续R29-R32 TIER_BUDGET扩展路径/' docker-compose.yml"
```

### 4c. 部署
```bash
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'
```
→ Container hm40006 Recreated, Started

### 4d. 验证
```
TIER_TIMEOUT_BUDGET_S=92  ✓
HM_CONNECT_RESERVE_S=22   ✓
KEY_COOLDOWN_S=38.0       ✓
TIER_COOLDOWN_S=90        ✓
MIN_OUTBOUND_INTERVAL_S=10.0 ✓
UPSTREAM_TIMEOUT=40       ✓
hm40006 Up (healthy)      ✓
```

---

## 5. 预期效果

| 指标 | R32值 | R33预期 | 依据 |
|------|-------|---------|------|
| 2nd attempt headroom | 28s | 30s | +7% vs R32, 覆盖25-30s全区间 |
| deepseek 25-30s超时cnt | 34 | ~20-25 | headroom=30s完全覆盖25-30s区间 |
| 0-tier pre-tier失败 | 17 | 17 | RESERVE饱和, 不变 |
| >40s超时budget耗尽 | 28 | ~24-26 | NVCF基础设施级, 部分改善 |
| SSLEOFError | 2/100行 | ≤2 | SSL稳定性持续 |
| fallback率 | 90.3% | ~89-90% | glm5.1功能级429不变, fallback率稳定 |

---

## 6. 观察项与风险

1. **BUDGET上界到达**: BUDGET=92是建议上界(2nd attempt=30s). 如果下轮数据仍无明显改善, 停止BUDGET扩展, 转投其他参数.
2. **k1(port 7895)超时不均**: 40次vs平均32次(25%偏高), 自R24稳定但需持续跟踪.
3. **>40s budget耗尽(28次)**: 这是UPSTREAM_TIMEOUT=40s的硬边界. BUDGET headroom扩展不解决此问题 — 只能通过降低UPSTREAM_TIMEOUT(牺牲首次attempt完整性)或NVCF基础设施优化解决.
4. **TIER_COOLDOWN_S=90**: 稳定, 不需调整. 若想减少TIER-SKIP频率, 可考虑85→80, 但会增加429碰撞风险.
5. **SSLEOFError=2**: 极低, 稳定. 无需干预.

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记