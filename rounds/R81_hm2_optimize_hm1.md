# R81: HM2→HM1 — TIER_TIMEOUT_BUDGET_S 104→106 (+2s)

**时间**: 2026-06-27 04:46 UTC  
**执行者**: HM2 (opc2_uname)  
**方向**: HM2优化HM1  
**上一轮**: R80 (HM2→HM1, KEY_COOLDOWN_S 33.0→31.0)

## 📊 采集数据 (HM1 hm40006, 30min 窗口)

### HM1当前运行配置
| 参数 | 值 | 上轮变更 |
|------|-----|----------|
| UPSTREAM_TIMEOUT | 62 | R76 |
| TIER_TIMEOUT_BUDGET_S | **104** → 106 | **本轮** |
| KEY_COOLDOWN_S | 31.0 | R80: 33→31 |
| TIER_COOLDOWN_S | 55 | R79: 68→55 |
| MIN_OUTBOUND_INTERVAL_S | 17.5 | R79: 15.5→17.5 |
| HM_CONNECT_RESERVE_S | 22 | 未变 |

### Error分布 (hm_tier_attempts, 30min)
| Error类型 | 计数 | Avg ms | 占比 |
|-----------|------|--------|------|
| 429_nv_rate_limit | 1,052 | - | 83.4% |
| NVCFPexecTimeout (全部) | 118 | 25,052 | 9.3% |
| ConnectionResetError | 47 | 3,300 | 8.4% |
| empty_200 | 11 | - | - |
| budget_exhausted_after_connect | 7 | 2,270 | - |

### 请求路由 (hm_requests)
| 指标 | 值 |
|------|-----|
| 总请求数 | 1,256 |
| 回退率 | 68.7% (863/1256) |
| glm5.1 直接成功 | 31.2% (392/1256) |
| 429 cycle率 | 30.9% (388/1256 ≥1 cycle) |
| 0-tier 全部耗尽 | 1 |

### Deepseek超时桶 (30min)
| 桶 | 计数 | % |
|----|------|---|
| <20s | 47 | **74.6%** |
| 20-25s | 4 | 6.3% |
| 50-55s | 1 | 1.6% |
| >55s | 11 | 17.5% |

### glm5.1 按Key 429分布
| Key | 429计数 |
|-----|---------|
| k0 | 244 |
| k1 | 214 |
| k2 | 205 |
| k3 | 201 |
| k4 | 188 |

## 🔧 诊断分析

### 预算计算 (R80 状态，预修改)
- UPSTREAM=62, BUDGET=104, RESERVE=22
- 1st key: min(62, 104-22=82) = 62s
- Remain = 104-62 = 42
- 2nd key: max(10, min(62, 42-22=20)) = **20s** ← 决策边界

### 核心问题
1. **2nd-attempt 在决策边界 (20s)** — 连续数轮在20s，需要恢复headroom
2. **429 仍主导但回退改善** — fallback=68.7% (从R79的64.2%略有回升，但远低于R80前几轮的86-94%)
3. **glm5.1 直接成功率健康** — 31.2%，高于25%阈值
4. **Deepseek超时模式改变** — `<20s`桶主导(74.6%)，不再是大超时(>40s/50s)主导

### 优化选择
**TIER_TIMEOUT_BUDGET_S: 104 → 106 (+2s)**

**机制**:
- 总预算从104s增至106s，2nd-attempt从20s→22s (+2s headroom)
- 不改变1st key行为 (UPSTREAM=62不变)
- 不影响主tier (glm5.1) — 主tier仍是函数级429
- +2s预算直接扩展2nd key的deepseek完成窗口

**预算计算 (R81后)**:
- UPSTREAM=62, BUDGET=106, RESERVE=22
- 1st key: min(62, 106-22=84) = 62s
- Remain = 106-62 = 44
- 2nd key: max(10, min(62, 44-22=22)) = 22s (+2s 恢复)

**为什么不是 TIER_COOLDOWN 或 KEY_COOLDOWN**:
- TIER_COOLDOWN=55 已经很低 (R79从68→55)，继续降低风险ConnectionResetError激增
- KEY_COOLDOWN=31.0 接近HM2基线(30s)，429 cycle率30.9% 不算极端
- 2nd-attempt 在决策边界 (20s) 是更直接的决策信号

**预期效果**:
- 2nd-attempt从20s→22s，deepseek 2nd key有更多时间完成
- deepseek Timeout 可能减少~5-8个 (减少边界截断)
- 回退率可能从68.7%降至~65% (更可靠的deepseek层)
- 平均延迟可能从~31s降至~29s

## 📝 执行记录

```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R81'

# 值变更 (行418)
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '418s/\"104\"/\"106\"/' docker-compose.yml"

# 评论更新
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '418s/# R69:.*$/# R81: HM2优化 — 104→106: +2s tier budget; UPSTREAM=62 BUDGET=106 RESERVE=22 1st=62s 2nd=22s; 恢复2nd-attempt headroom +2s; fallback=68.7% glm5.1直接=31.2%; ConnectionResetError=47(安定); 少改多轮(单参数); 铁律:只改HM1不改HM2/' docker-compose.yml"

# 部署
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'
```

### 验证
```bash
docker exec hm40006 env | grep -E 'TIER_TIMEOUT_BUDGET_S|UPSTREAM_TIMEOUT'
# → UPSTREAM_TIMEOUT=62, TIER_TIMEOUT_BUDGET_S=106 ✓
docker ps --format '{{.Names}} {{.Status}}' | grep hm40006
# → hm40006 Up 52 seconds (healthy) ✓
```

## 📈 预期效果

- ✅ 少改多轮 (单参数 +2s)
- ✅ 基于实时数据: 2nd-attempt在决策边界(20s)，BUDGET扩展直接恢复headroom
- ✅ 容器健康验证通过
- ✅ TIER_TIMEOUT_BUDGET_S 104→106 (+2s)，2nd-attempt 20s→22s

## ⚠️ 观察项目

1. 监控 ConnectionResetError 在 BUDGET扩展后是否保持稳定 (<50)
2. 下一轮检查 deepseek timeout 计数是否下降
3. 下一轮UPSTREAM→64 时 BUDGET=106 下 2nd=20s (决策边界) — 已标注

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记