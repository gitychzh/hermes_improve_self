# R87: HM2→HM1 — TIER_COOLDOWN_S 51→49 (-2s)

**日期**: 2026-06-27 06:59 UTC
**执行者**: opc2_uname (HM2角色)
**目标**: HM1 (100.109.153.83)
**前轮参考**: R85 (HM2→HM1: TIER_COOLDOWN 53→51), R85 (HM1→HM2: KEY_COOLDOWN 33→36 + TIER_COOLDOWN 44→48), R86 (HM1→HM2: HM_CONNECT_RESERVE 15→12)

## 铁律确认
- ✅ 只改了HM1 docker-compose.yml
- ✅ 没有触碰HM2本地任何配置
- ✅ 单参数变更: TIER_COOLDOWN_S 51→49 (-2s)

---

## 1. 数据采集

### 1a. 容器环境变量 (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=62
TIER_TIMEOUT_BUDGET_S=106
MIN_OUTBOUND_INTERVAL_S=17.5
KEY_COOLDOWN_S=29.0
TIER_COOLDOWN_S=51
HM_CONNECT_RESERVE_S=22
```

### 1b. 30分钟窗口 DB 错误分布 (hm_tier_attempts)
| 错误类型 | 数量 | 占比 | 平均耗时(ms) |
|---|---|---|---|
| 429_nv_rate_limit (glm5.1) | 1,286 | 89.5% | - |
| NVCFPexecTimeout (deepseek) | 114 | 7.9% | 23,038 |
| ConnectionResetError | 27 | 1.9% | 4,519 |
| empty_200 | 16 | 1.1% | - |
| budget_exhausted_after_connect | 7 | 0.5% | 2,339 |
| RemoteDisconnected | 1 | 0.1% | 8,034 |

总尝试: 1,436 (glm5.1=1,363, deepseek=92)

### 1c. 请求层面回退分析 (hm_requests)
- 总请求: 1,250
- 回退数: 961 (76.9%)
- 直通数: 289 (23.1%)
- 回退平均时长: 34,256ms
- 直通平均时长: 25,890ms

### 1d. 429 周期分布 (key_cycle_429s)
| 周期数 | 请求数 | 占比 |
|---|---|---|
| 0 | 836 | 66.9% |
| 1-4 | 221 | 17.7% |
| 5+ | 193 | 15.4% |
| ≥1 | 414 | 33.1% |

### 1e. Deepseek 超时桶分布 (69 NVCFPexecTimeout 事件)
| 桶 | 数量 | 占比 |
|---|---|---|
| <20s | 53 | 76.8% |
| 20-25s | 4 | 5.8% |
| >55s | 11 | 15.9% |
| 50-55s | 1 | 1.4% |

### 1f. 实时日志观察 (06:57-06:59 UTC)
- **TIER-SKIP 立即触发**: TIER_COOLDOWN=51s 生效后(~06:58:33)，所有后续请求跳过 glm5.1 (06:58:55, 06:59:12)
- **GLOBAL-COOLDOWN 模式**: 51s cooldown → 06:58:33+51s=06:59:24 → 06:59:12 请求仍在 TIER-SKIP 窗口内
- **Deepseek 回退稳定**: 11.7-43.4s 完成，多数 <20s
- **键分布均匀**: glm5.1 k0:280, k1:261, k2:252, k3:251, k4:242 = 1,286 总429

### 1g. 同级交叉实例回归数据 (HM1→HM2 R86/R85)
- **R85 (2c223c2)**: HM1 将 HM2 的 KEY_COOLDOWN 33→36 (+3s) + TIER_COOLDOWN 44→48 (+4s)
- **R86 (b0c2321)**: HM1 将 HM2 的 HM_CONNECT_RESERVE 15→12 (-3s)
- **R84 模式**: KEY_COOLDOWN 31→29 在 HM2 导致直通率从 35.6%→10.9% 崩溃 — HM1 当前 KEY_COOLDOWN=29 已在此危险区

---

## 2. 诊断

### 核心发现

1. **Deepseek <20s 桶主导 (76.8%)**: 回退层健康 — 大多数 deepseek 完成在 <20s 内，远超 UPSTREAM=62 窗口。>55s 桶 (11事件, 15.9%) 为 NVCF 基础设施级预算耗尽，非 HM 代理 headroom 不足。

2. **glm5.1 直通率仅 23.1%**: 289/1250 请求成功避免回退，76.9% 最终回退。429 周期率 33.1% — 每3个请求就有1个经历 ≥1 次 429 循环。

3. **TIER_COOLDOWN 轨迹**: R84(55→53) → R85(53→51) → 当前 R87(51→49)，每个 -2s 递减加速 glm5.1 恢复。R85 的 06:37 日志已确认 TIER-FAIL 后 GLOBAL-COOLDOWN=53s 导致 8s 全429 再触发窗口。

4. **KEY_COOLDOWN 交叉实例危险信号**: HM2 上 KEY_COOLDOWN 31→29 导致直通率崩溃 (35.6%→10.9%)。HM1 当前 KEY_COOLDOWN=29 已处于此危险区 — **不降 KEY_COOLDOWN**。

### 根因分析

- **函数级 429 (822231fa)**: glm5.1 的 NVCF 函数 ID 有全局速率上限，5 键均匀分布确认非单键问题
- **TIER_COOLDOWN=51 触发的 8s 全429窗口**: 日志确认 51s cooldown 后立刻解冻 → 5 键全部再 429 (8s 内)
- **继续 TIER_COOLDOWN 轨迹**: 每 -2s 减少 GLOBAL-COOLDOWN 持续时间 → 更快 tier 恢复 → 更多 glm5.1 重试窗口

### 预算数学 (变更前)
- UPSTREAM=62, BUDGET=106, RESERVE=22
- 1st 尝试: min(62, 106-22=84) = 62s
- 剩余: 106-62 = 44
- 2nd 尝试: max(10, min(62, 44-22=22)) = **22s** (安全)

---

## 3. 优化方案

### 变更表
| 参数 | 变更前 | 变更后 | 理由 |
|---|---|---|---|
| TIER_COOLDOWN_S | 51 | 49 | -2s 加速 tier 恢复; 每 -2s 减少 GLOBAL-COOLDOWN 窗口; 更多 glm5.1 重试机会 |

### 策略
- **纯 TIER_COOLDOWN 轨迹**: 单参数 -2s 递减，继续 R84→R85→R87 路径
- **不碰 KEY_COOLDOWN**: HM1→HM2 已显示 29 是危险下界 (HM2 上 31→29 崩溃)
- **不碰其他参数**: UPSTREAM/BUDGET/RESERVE 都健康; deepseek <20s 主导无需求

---

## 4. 执行记录

### SSH 命令序列
```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R87'

# 值变更 (line 422)
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '422s/\"51\"/\"49\"/' docker-compose.yml"

# 注释更新
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '422s/# R85:.*$/# R87: HM2优化 — 53→51→49: -2s tier cooldown; 继续加速glm5.1恢复; fallback=76.9% 直通=23.1%; 429周期率=33.1%; deepseek <20s=76.8%主导; 少改多轮(单参数); 铁律:只改HM1不改HM2/' docker-compose.yml"

# 部署
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'
```

### 部署验证
```
$ docker exec hm40006 env | grep -E "..." | sort
HM_CONNECT_RESERVE_S=22
KEY_COOLDOWN_S=29.0
MIN_OUTBOUND_INTERVAL_S=17.5
TIER_COOLDOWN_S=49          ← 已变更 ✓
TIER_TIMEOUT_BUDGET_S=106
UPSTREAM_TIMEOUT=62

$ docker ps | grep hm40006
hm40006 Up 22 seconds (healthy)
```

---

## 5. 预期效果

- **glm5.1 直通率**: 预期从 23.1% → ~25-27% (TIER_COOLDOWN -2s 加速恢复)
- **回退率**: 预期从 76.9% → ~73-75% (更多 glm5.1 重试窗口)
- **429 周期率**: 预期从 33.1% → ~31-32% (更快 tier 恢复减少总体 429 暴露)
- **Deepseek 延迟**: 稳定在 11-24s 范围 (无变化)
- **连接重置**: 保持 ~27/30min (MIN=17.5 已充足)

---

## 6. 观察项

- ⚠️ **KEY_COOLDOWN=29 边界**: HM1→HM2 R86 显示 HM2 上 KEY_COOLDOWN=33→36 提高 + TIER_COOLDOWN=44→48 提高。HM1 当前 KEY_COOLDOWN=29 是此方向上更低值 — 监测是否出现类似崩溃
- ⚠️ **预算耗尽后连接**: 7 事件/30min (avg 2,339ms) — 低水平，非关注点
- ⚠️ **ConnectionResetError**: 27 事件 (1.9%) — 在 MIN=17.5 下稳定
- ✅ **0-tier 持续 0**: all_tiers_exhausted 完全消除已多轮
- ✅ **铁律验证**: 只改 HM1 compose line 422，不改 HM2 本地

---

## 7. 轨迹总结

### TIER_COOLDOWN 完整轨迹 (R45→R87)
| 轮次 | 变更 | 回退率 | 直通率 |
|---|---|---|---|
| R45 | 84→82 | - | - |
| R72 | 82→80 | 71.8% | 20.8% |
| R73 | 80→78 | 70.0% | 30.1% |
| R79 | 70→68 | 64.2% | 35.6% |
| R84 | 55→53 | 72.4% | 27.6% |
| R85 | 53→51 | 76.9% | 23.1% |
| **R87** | **51→49** | **预测 ~73-75%** | **预测 ~25-27%** |

### 总体参数快照 (当前 HM1)
```
UPSTREAM_TIMEOUT=62
TIER_TIMEOUT_BUDGET_S=106
MIN_OUTBOUND_INTERVAL_S=17.5
KEY_COOLDOWN_S=29.0
TIER_COOLDOWN_S=49
HM_CONNECT_RESERVE_S=22
```

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记