# R63: HM2优化HM1 — KEY_COOLDOWN_S 38→36 (-2s键冷却加速429恢复)

**日期**: 2026-06-26
**执行者**: HM2 (opc2_uname)
**目标**: HM1 (opc_uname)
**触发**: 检测脚本判定轮到HM2执行优化(HM1提交了新commit); 30min数据分析显示429 cycle延迟glm5.1直通率仅14.5%

## 📊 数据收集 (30min DB窗口 20:40 UTC)

### 整体指标
| 指标 | 值 |
|------|-----|
| 总请求 | 1,115 |
| 成功率 | 99.9% (1,114/1,115) |
| 回退率 | 85.4% (953/1,115) |
| 平均延迟 | 21,964 ms |
| glm5.1直通延迟 | 17,515 ms |
| 回退平均延迟 | 22,720 ms |

### 按Tier成功分布
| Tier | 总尝试 | 成功 | 失败 | 平均耗时 |
|------|--------|------|------|----------|
| deepseek_hm_nv | — | 942 | 40 timeout | 30,749 ms |
| glm5.1_hm_nv | 1,091 | 162直通 | 1,019 429 | 4,317 ms |
| kimi_hm_nv | 1 | 1 | 1 timeout | 43,048 ms |

### 错误分解 (30min hm_tier_attempts)
| 错误类型 | 数量 | 平均耗时 |
|----------|------|----------|
| 429_nv_rate_limit | 1,019 | — |
| NVCFPexecConnectionResetError | 61 | 1,895 ms |
| NVCFPexecTimeout | 46 | 33,050 ms |
| NVCFPexecRemoteDisconnected | 5 | 1,322 ms |
| budget_exhausted_after_connect | 3 | 935 ms |

### 429 Key分布 (均匀 → 函数级)
| Key 0 | 209 |
| Key 1 | 205 |
| Key 2 | 209 |
| Key 3 | 200 |
| Key 4 | 196 |

### 429 cycle分布 (jsonb key_cycle_429s)
| 0 | 804 (72.1%) |
| 1 | 66 |
| 2 | 27 |
| 3 | 20 |
| 4 | 51 |
| 5 | 131 |
| 6 | 14 |
| 7 | 1 |

→ 310/1115=27.8% 请求遇≥1次429 cycle

### Deepseek超时分析 (30min)
| 耗时区间 | 数量 |
|----------|------|
| <20s | 14 |
| 20-30s | 3 |
| 30-40s | 5 |
| 40-50s | 11 |
| 50-58s | 4 |
| >60s | 3 |

→ 18/40=45% deepseek超时在>40s区间 (接近UPSTREAM=58s边界)

### Successful deepseek请求延迟分布
| 区间 | 数量 |
|------|------|
| <20s | 543 |
| 20-30s | 213 |
| 30-40s | 89 |
| 40-50s | 40 |
| 50-60s | 38 |
| >60s | 19 |

→ 19/942=2.0% deepseek成功请求>60s

### Docker日志 (500行窗口)
| Pattern | 计数 |
|--------|------|
| HM-SUCCESS | 22 |
| HM-ERR | 2 (ConnectionResetError×2) |
| HM-CYCLE (429) | 6 |
| HM-TIMEOUT | 4 |
| HM-TIER-FAIL | 1 |

### 运行中环境变量
| 变量 | HM1值 | HM2值(参考) |
|------|-------|-------------|
| KEY_COOLDOWN_S | 38.0 | 26.5 |
| UPSTREAM_TIMEOUT | 58 | 60 |
| TIER_TIMEOUT_BUDGET_S | 100 | — |
| MIN_OUTBOUND_INTERVAL_S | 14.0 | 17.0 |
| TIER_COOLDOWN_S | 82 | — |
| HM_CONNECT_RESERVE_S | 22 | 18 |

## 🔍 问题诊断

**根本原因**: glm5.1_hm_nv tier的429_nv_rate_limit (1,019/30min) 是主导错误类型(95% of non-empty errors)。glm5.1的直接成功率仅为 14.5% (162/1115) — 5个NVCF键在函数级速率限制下持续被429阻挡。KEY_COOLDOWN=38s (R19, 已过44轮) 对429恢复速度约束过紧。

**数据证据**:
- 30min窗口: 429=1,019 (均匀分布, 函数级速率限制 → 非单键耗尽)
- 27.8% 请求遇≥1次 429 cycle (310/1115) — 每个cycle引入额外延迟, 减损glm5.1直通
- glm5.1直通率仅14.5% (R40 ring fallback下glm5.1→deepseek→kimi链, 大部分请求被deepseek吸收)
- 429 cycle分布: 5次cycle=131 (最常), 6次=14, 7次=1 → 频繁重试说明冷却时间过长
- 每个429 cycle: 38s冷却 → 5 keys × 38s = 190s完整键池回收时间 → 0.132 req/s per key
- deepseek作为主力tier: 成功942 (84.5% of total), 但该为HM2侧(不触碰)
- 连接错误: ConnectionReset=61 (30min) — 中等水平, 但429主导
- RESERVE=22 — 充足, 0-tier=0 (无瓶颈)

**策略**: 每轮-2s加速键冷却, 从R19(35→38)逆推回归。少改多轮(单参数)。36s → 5 keys × 36s = 180s → 0.139 req/s per key (+5.7% capacity). 目标: 提高glm5.1直通率从14.5%→~16-18%, 减少429 cycle发生率从27.8%→~25%.

## 📋 优化计划

| # | 变更 | 前 | 后 | 理由 | 风险 |
|---|------|----|----|------|------|
| 1 | KEY_COOLDOWN_S | 38.0 | **36.0** (-2s) | 加速429键恢复; 27.8%请求遇429 cycle; 38s已运行44轮(R19→R63), 需要渐进回归; 5 keys×36s=180s full recovery vs 190s; 每键+0.007 req/s容量 | 低 — 单参数 -2s 增量; 已验证路径; 不会触发硬编码 all-keys-429 冷却(22s固定) |

**不触碰**:
- UPSTREAM_TIMEOUT=58 — 刚被R62优化(56→58), 稳定
- TIER_TIMEOUT_BUDGET=100 — R61优化后稳定, 2nd attempt headroom=22s
- MIN_OUTBOUND=14.0 — 与HM2的17.0不同但HM1稳定
- TIER_COOLDOWN=82 — R45优化后稳定, 不需要同时多参数变更
- HM_CONNECT_RESERVE=22 — 充足, 0-tier=0 无瓶颈
- 硬编码all-keys-429冷却(22s) — 不属于env控制范围, 需源码修改单独轮

## ⚙️ 执行记录

```bash
# 1. 备份
ssh opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R63'

# 2. 编辑 (sed → docker-compose.yml line 421)
# Old: KEY_COOLDOWN_S: "38.0"  # R19: ...
# New: KEY_COOLDOWN_S: "36.0"  # R63: HM2优化 — 38→36: -2s...

# 3. 重新部署
docker compose up -d hm40006
# → Container hm40006 Recreate → Recreated → Starting → Started

# 4. 验证
docker exec hm40006 env | grep KEY_COOLDOWN_S
# → 36.0 ✅
docker ps --format "{{.Names}} {{.Status}}" | grep hm40006
# → hm40006 Up 38 seconds (healthy) ✅
```

## 📈 部署后验证

| 检查项 | 结果 |
|--------|------|
| KEY_COOLDOWN_S运行值 | 36.0 ✅ (确认变更) |
| 容器健康状态 | healthy ✅ |
| 服务启动 | 38s前启动 ✅ |
| compose文件注释 | R63 ✅ |
| 备份 | docker-compose.yml.bak.R63 ✅ |

**预期效果**: -2s KEY_COOLDOWN → 更快429键冷却恢复 → glm5.1 429 retry 频率↓5-8% → 更多glm5.1直通请求 → 减少deepseek fallback依赖 → 潜在降低~2-3%回退率。实际效果需HM1下次数据采集验证。

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记