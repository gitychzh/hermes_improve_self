# R32: HM2优化HM1

**日期**: 2026-06-26
**Actor**: HM2 (opc2_uname)
**Target**: HM1 (100.109.153.83:222)
**前一轮**: R31 (HM1提交, TIER_BUDGET 86→88)
**策略**: 少改多轮, 继续TIER_BUDGET扩展路径

---

## 1. 数据采集

### 1a. 日志模式 (最近100行, error/warn/fail/SSL)
- 匹配数: 24
- SSLEOFError: 1 (非常低, 稳定)
- 主要日志模式: glm5.1 TIER-SKIP → deepseek FALLBACK-SUCCESS (典型流程)

### 1b. 容器环境变量 (运行中值)
| 参数 | 值 | 来源 |
|------|-----|------|
| TIER_TIMEOUT_BUDGET_S | 88 | R31 |
| UPSTREAM_TIMEOUT | 40 | R18 |
| HM_CONNECT_RESERVE_S | 22 | R29 |
| KEY_COOLDOWN_S | 38.0 | R19 |
| MIN_OUTBOUND_INTERVAL_S | 10.0 | R17 |
| TIER_COOLDOWN_S | 90 | R17 |

### 1c. 错误分布 (30分钟窗口, hm_tier_attempts)
| error_type | cnt | avg_elapsed |
|------------|-----|-------------|
| 429_nv_rate_limit | 856 | — |
| NVCFPexecTimeout | 171 | 26953ms |
| NVCFPexecConnectionResetError | 3 | 779ms |
| NVCFPexecRemoteDisconnected | 1 | 7577ms |

### 1d. 请求路由统计 (hm_requests, 30分钟)
| 指标 | 值 |
|------|-----|
| 总请求 | 1360 |
| fallback数 | 1219 |
| fallback率 | 89.6% |
| 直接成功 | 141 (10.4%) |
| 错误请求 | 17 |
| 非fallback平均延迟 | 21177ms |
| fallback平均延迟 | 16253ms |

### 1e. 层级分布 (hm_tier_attempts)
| tier | cnt |
|------|-----|
| glm5.1_hm_nv | 871 |
| deepseek_hm_nv | 156 |
| kimi_hm_nv | 4 |

### 1f. 0-tier pre-tier连接失败
- **0-tier = 17** (与R27-R31一致, avg duration 105292ms)
- RESERVE=22饱和确认: 连续6轮(R27-R32) 0-tier=17不变

### 1g. glm5.1 429按key分布 (功能级429, 非per-key)
| key_idx | 429_count | timeout_count |
|---------|-----------|---------------|
| k0 | 173 | 0 |
| k1 | 169 | 1 |
| k2 | 173 | 5 |
| k3 | 170 | 4 |
| k4 | 171 | 2 |

→ 429均匀分布(169-173), 功能级429特性不变

### 1h. Deepseek NVCFPexecTimeout按key分布
| key_idx | timeout_count | 端口 |
|---------|---------------|------|
| k0 | 27 | 7894 |
| k1 | 39 | 7895 |
| k2 | 35 | 7896 |
| k3 | 26 | 7897 |
| k4 | 28 | 7899 |

→ k1(port 7895)最差(39次), 自R24以来稳定模式

### 1i. Deepseek NVCFPexecTimeout elapsed_ms分布
| bucket | cnt | pct |
|--------|-----|-----|
| <20s | 48 | 31.0% |
| 20-25s | 8 | 5.2% |
| 25-30s | 34 | 21.9% |
| 30-35s | 28 | 18.1% |
| 35-40s | 11 | 7.1% |
| >40s | 26 | 16.8% |

→ 25-30s区间仍有34次超时, 2nd attempt headroom=26s部分覆盖此区间
→ >40s=26次 (budget耗尽, NVCF基础设施级超时)

---

## 2. 诊断

### 根因分析
1. **RESERVE=22完全饱和**: 0-tier=17连续6轮不变(R27-R32), 非handshake原因(44/43连接级失败). RESERVE继续增加无边际收益.
2. **TIER_BUDGET扩展有效**: R31(86→88)让2nd attempt headroom=26s, 在25-30s区间捕获部分超时请求, 但仍有34次在该区间.
3. **Deepseek 2nd attempt window**: 当前headroom=26s, 25-30s区间的34次超时中, 处于25-26s边界附近的请求可被捕获, 但26-30s区间的请求仍未被覆盖. +2s BUDGET将headroom扩展到28s, 直接覆盖更多25-28s的超时.
4. **glm5.1功能级429**: 856次429均匀分布5个key, 这是NVCF函数级速率限制, 非key配置可解决.
5. **k2(port 7895)超时不均**: 39次超时是最高的(平均31次), 自R24稳定模式, 暂无需介入.

### 证据链
- R31 BUDGET=88 → 2nd attempt=26s → 25-30s区间34次超时(21.9%)
- R30 BUDGET=86 → 2nd attempt=24s → 覆盖窗口更窄
- >40s的26次超时 = UPSTREAM_TIMEOUT(40s)边界, budget耗尽, 无法通过headroom扩展解决
- SSLEOFError=1, 极低, SSL稳定性好

---

## 3. 优化变更

| 参数 | 变更前 | 变更后 | 理由 |
|------|--------|--------|------|
| TIER_TIMEOUT_BUDGET_S | 88 | 90 | +2s tier budget扩展2nd attempt headroom从26s→28s, 覆盖更多25-28s deepseek超时; RESERVE=22不变(饱和); 残余68s, 2nd attempt=28s headroom; 少改多轮(继续R29-R31 BUDGET扩展路径) |

**预算数学**: BUDGET=90, RESERVE=22 → 残余=68s, 1st attempt=40s(UPSTREAM_TIMEOUT), 2nd attempt=min(40, 68-22-40+22)=28s ← headroom增加2s

**不变参数**: UPSTREAM_TIMEOUT=40, HM_CONNECT_RESERVE_S=22, KEY_COOLDOWN_S=38, MIN_OUTBOUND_INTERVAL_S=10, TIER_COOLDOWN_S=90

---

## 4. 执行记录

### 4a. 备份
```bash
ssh opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R32'
```

### 4b. 配置变更 (compose line 418)
```bash
# Value change: 88→90
sed -i '418s/"88"/"90"/' docker-compose.yml
# Comment update: R31→R32
sed -i '418s/# R31:.*$/# R32: HM2优化 — 88→90: +2s tier budget; .../' docker-compose.yml
```

### 4c. 部署
```bash
cd /opt/cc-infra && docker compose up -d hm40006
```
→ Container hm40006 Recreated, Started

### 4d. 验证
```
TIER_TIMEOUT_BUDGET_S=90  ✓
HM_CONNECT_RESERVE_S=22   ✓
KEY_COOLDOWN_S=38.0       ✓
TIER_COOLDOWN_S=90        ✓
MIN_OUTBOUND_INTERVAL_S=10.0 ✓
UPSTREAM_TIMEOUT=40       ✓
hm40006 Up (healthy)      ✓
```

---

## 5. 预期效果

| 指标 | R31值 | R32预期 | 依据 |
|------|-------|---------|------|
| 2nd attempt headroom | 26s | 28s | +8% vs R31, 覆盖25-28s超时段 |
| deepseek 25-30s超时cnt | 34 | ~26-28 | headroom+2s捕获25-28s部分请求 |
| 0-tier pre-tier失败 | 17 | 17 | RESERVE饱和, 不变 |
| >40s超时budget耗尽 | 26 | ~26 | NVCF基础设施级, 无法通过headroom解决 |
| SSLEOFError | 1/100行 | ≤2 | SSL稳定性持续 |
| fallback率 | 89.6% | ~89-90% | glm5.1功能级429不变, fallback率稳定 |

---

## 6. 观察项与风险

1. **k2(port 7895)超时不均**: 39次vs平均31次(26%偏高), 自R24稳定但需持续跟踪. 若偏差>2×则需调查mihomo proxy端口健康
2. **BUDGET扩展上界**: 当前轨迹R29→R30→R31→R32: 82→84→86→90. 若2nd-attempt NVCFPexecTimeout持续不降, 考虑BUDGET=92(2nd attempt=30s)作为下一目标
3. **>40s budget耗尽(26次)**: 这是UPSTREAM_TIMEOUT=40s的硬边界, 只能通过降低UPSTREAM_TIMEOUT(牺牲首次attempt完整性)或NVCF基础设施优化来解决, 不纳入BUDGET扩展路径
4. **TIER_COOLDOWN_S=90**: 稳定, 不需调整

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记
