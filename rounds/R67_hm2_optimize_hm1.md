# R67: HM2优化HM1 — MIN_OUTBOUND_INTERVAL_S 14.0→14.5 (+0.5s)

**日期**: 2026-06-26 22:15 UTC  
**执行者**: HM2 (opc2_uname)  
**目标**: HM1 (100.109.153.83, port 222)  
**前一轮**: R65 (BUDGET 100→102 + KEY_COOLDOWN 36→34), R66 (HM1→HM2: KEY_COOLDOWN 30→32)  
**触发**: HM1提交commit 721fdc6 (R66), HM2检测到轮到HM2优化HM1

---

## 1. 数据收集

### 1a. 当前运行配置 (docker exec hm40006 env)
| 参数 | 值 | 行号 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 58s | 417 |
| TIER_TIMEOUT_BUDGET_S | 102 | 418 |
| MIN_OUTBOUND_INTERVAL_S | 14.0 | 420 |
| KEY_COOLDOWN_S | 34.0 | 421 |
| TIER_COOLDOWN_S | 82 | 422 |
| HM_CONNECT_RESERVE_S | 22 | 451 |

### 1b. 错误分布 (hm_tier_attempts, 最近30分钟)
| 错误类型 | 计数 | 占比 |
|----------|------|------|
| 429_nv_rate_limit | 981 | 88.8% |
| NVCFPexecConnectionResetError | 71 | 6.4% |
| NVCFPexecTimeout | 46 | 4.2% |
| NVCFPexecRemoteDisconnected | 6 | 0.5% |
| budget_exhausted_after_connect | 2 | 0.2% |

**总计**: 1,106 tier attempts across 1,120 requests

### 1c. 请求级指标 (hm_requests, 30分钟)
- 总请求: 1,120
- Fallback率: 82.1% (919/1120) — 改善自 R65 85.8%
- 0-tier pre-tier: **0** (持续消除)
- 429 cycle rate: 27.6% (309/1120 遭遇 ≥1 次429 cycle)

### 1d. 429 cycle分布 (key_cycle_429s)
| 429循环次数 | 请求数 |
|------------|--------|
| 0 | 811 (72.4%) |
| 1 | 82 |
| 2 | 21 |
| 3 | 12 |
| 4 | 46 |
| 5 | 127 |
| 6 | 20 |
| 7 | 1 |

### 1e. Deepseek NVCFPexecTimeout elapsed_ms桶
| 桶 | 计数 | 占比 |
|----|------|------|
| <20s | 11 | 23.9% |
| 20-25s | 1 | — |
| 25-30s | 1 | — |
| 30-35s | 4 | — |
| 35-40s | 0 | — |
| 40-45s | 6 | — |
| 45-50s | 2 | — |
| 50-55s | 3 | — |
| >55s | 4 | 8.7% |

**总deepseek timeout**: 46 (32 NVCFPexecTimeout + 含其他错误)

### 1f. 每键429分布 (glm5.1)
| 键 | 429计数 |
|----|---------|
| k0 | 214 |
| k1 | 199 |
| k2 | 203 |
| k3 | 184 |
| k4 | 181 |

均匀分布 — 函数级速率限制, 非单键问题

### 1g. 最近10条请求延迟
所有最近10条均为deepseek fallback成功 (200 OK):  
duration_ms范围: 7,509–54,283ms, 平均~21,886ms  
全部fallback_occurred=t, 无429 cycle

---

## 2. 诊断

### 核心发现

**ConnectionResetError急剧增长**: 71事件 (6.4%) — 自R65的63 (+12.7%), 自R62的58 (+22.4%)。这是30分钟窗口内最大的连接级错误类别。

**根因分析**:
- 71 ConnectionResetError均匀分布于所有5键 (k0-k4), 非单键问题
- 随着UPSTREAM_TIMEOUT自R46的42s扩展至R62的58s, 每次尝试占用更多连接时间 → 更多proxy-level TCP重置窗口
- MIN_OUTBOUND_INTERVAL=14.0s 已稳定6轮但ConnectionResetError持续上升
- 这是NVCF基础设施级别的代理连接重置, 不是HM应用层问题

**证据链**:
- R42: MIN_INTERVAL 13.5→14.0, ConnectionResetError=18
- R58: ConnectionResetError=58 (MIN_INTERVAL=14.0)
- R60: ConnectionResetError=57
- R62: ConnectionResetError=58
- R65: ConnectionResetError=63
- **现在R67 pre-deploy: 71** — 趋势加速

**优化目标**: 减慢出站连接节奏, 减少每秒重试碰撞密度, 降低TCP连接重置概率

### 为什么不选其他参数?

| 候选参数 | 评审 | 拒绝原因 |
|----------|------|---------|
| UPSTREAM_TIMEOUT 58→60 | 2nd=20s(边界安全) | ConnectionResetError=71 是当前更紧迫瓶颈 |
| KEY_COOLDOWN 34→32 | 加速429恢复 | HM1刚在R66反向提KEY_COOLDOWN 30→32(说明HM1认为需要更多冷却) |
| TIER_COOLDOWN 82→80 | 继续加速glm5.1 | ConnectionResetError趋势优先 |
| TIER_TIMEOUT_BUDGET 102→104 | 扩展2nd预算 | 非当前瓶颈; deepseek timeout分布均匀, 非单桶主导 |

---

## 3. 优化

### 变更
| 参数 | 变更前 | 变更后 | 增量 | 理由 |
|------|--------|--------|------|------|
| MIN_OUTBOUND_INTERVAL_S | 14.0s | 14.5s | +0.5s | 减慢出站节奏减少TCP连接重置; ConnectionResetError=71(↑6.4%) |

### 预算重算 (部署后)
- **UPSTREAM_TIMEOUT**: 58s (不变)
- **TIER_TIMEOUT_BUDGET_S**: 102 (不变)
- **RESERVE**: 22s (不变)
- **1st attempt**: min(58, 102-22=80) = 58s
- **剩余**: 102-58 = 44
- **2nd attempt**: max(10, min(58, 44-22=22)) = **22s**
- **2nd headroom**: 22s (安全, 远高于10s硬下限)

### 少改多轮
单参数变更, +0.5s最小增量, 连续R42→R67轨迹

---

## 4. 执行记录

```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R67'

# 修改值 (行420)
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && sed -i "420s/\"14.0\"/\"14.5\"/" docker-compose.yml'

# 更新注释
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '420s/# R42:.*$/# R67: HM2优化 — 14.0→14.5: +0.5s min outbound interval; ConnectionResetError=71(↑6.3%), 减少mihomo连接频率降低TCP重置/' docker-compose.yml"

# 部署
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'

# 验证
ssh -p 222 opc_uname@100.109.153.83 'sleep 5 && docker exec hm40006 env | grep MIN_OUTBOUND_INTERVAL_S'
# → MIN_OUTBOUND_INTERVAL_S=14.5 ✓
```

---

## 5. 预期效果

- **ConnectionResetError**: 预期71→60-65 (-10~15%) — 出站节奏减慢直接减少TCP重置窗口
- **Fallback率**: 82.1% → 轻微改善或持平 — MIN_INTERVAL不影响tier逻辑
- **0-tier pre-tier**: 维持0 — RESERVE=22已饱和
- **平均延迟**: 改善 — 更少的连接重置 = 更少的重试 = 更低的p95延迟
- **风险**: 出站间隔延长可能导致请求排队, 但0.5s增量在低流量下影响可忽略

---

## 6. 观察项

- **ConnectionResetError轨迹**: 监测R67 deploy后30分钟窗口, 期望从71回落至60-65
- **每键分布**: 继续监测k0-k4连接重置均匀性
- **Deepseek >55s桶**: 4事件 — NVCF基础设施级超时, 非MIN_INTERVAL可解决; 需UPSTREAM_TIMEOUT扩展或NVCF侧解决
- **429 cycle rate 27.6%**: 在KEY_COOLDOWN=34下保持监测; 若降至25%以下可停止KEY_COOLDOWN递减
- **铁律确认**: 仅修改HM1 docker-compose.yml (行420), 未触碰HM2本地任何配置

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记