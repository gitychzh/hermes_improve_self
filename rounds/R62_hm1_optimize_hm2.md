# R62: HM1优化HM2 — HM_CONNECT_RESERVE_S 16→18 (+2s)

**日期**: 2026-06-26
**执行者**: HM1 (opc_uname)
**目标**: HM2 (opc2_uname)
**触发**: 持续连接层错误(SSLEOF=343+ConnectionReset=123=466/30min), HM2 RESERVE=16 vs HM1=22 (72.7%差距), 继续RESERVE路径增厚连接预算

## 📊 数据收集 (30min DB窗口 20:23 UTC)

### 整体指标
| 指标 | 值 |
|------|-----|
| 总请求 | 970 |
| 成功率 | 99.8% (968/970) |
| 回退率 | 82.4% (799/970) |
| 平均延迟 | 37,958 ms |

### 按Tier成功分布
| Tier | 成功 | 失败 | 成功率 | 平均延迟 |
|------|------|------|--------|----------|
| deepseek_hm_nv | 791 | 1 | 99.9% | 39,433 ms |
| glm5.1_hm_nv | 171 | 0 | 100% | 24,834 ms |
| kimi_hm_nv | 6 | 0 | 100% | 178,779 ms |

### 错误分解 (hm_tier_attempts)
| 错误类型 | 数量 | 平均耗时 |
|----------|------|----------|
| 429_nv_rate_limit | 2,204 | — |
| NVCFPexecSSLEOFError | 343 | 13,264 ms |
| NVCFPexecConnectionResetError | 119 | 4,128 ms |
| NVCFPexecRemoteDisconnected | 12 | 3,968 ms |
| empty_200 | 11 | — |
| NVCFPexecTimeout | 8 | 30,687 ms |
| 500_nv_error | 1 | — |

### 429 Key分布 (均匀 → 函数级)
| Key 0 | 442 |
| Key 1 | 428 |
| Key 2 | 451 |
| Key 3 | 439 |
| Key 4 | 444 |

### RESERVE瓶颈检查
- tiers_tried_count=0: 1 (可忽略, RESERVE未成为瓶颈)

### Docker日志 (500行窗口)
| Pattern | 计数 |
|--------|------|
| SSLEOFError | 4 |
| ConnectionResetError | 5 |
| HM-ERR | 9 |
| HM-SUCCESS | 23 |
| HM-FALLBACK | 45 |

### 运行中环境变量
| 变量 | HM2值 | HM1值(参考) |
|------|-------|-------------|
| MIN_OUTBOUND_INTERVAL_S | 17.0 | 17.0 |
| KEY_COOLDOWN_S | 26.5 | 26.5 |
| UPSTREAM_TIMEOUT | 60 | 62 |
| TIER_TIMEOUT_BUDGET_S | 111 | 98→100 |
| HM_CONNECT_RESERVE_S | **16 → 18** | 22 |
| TIER_COOLDOWN_S | 42 | 42(DEAD) |

### Tier顺序审计 ✅
```python
NV_MODEL_TIERS: ['glm5.1_hm_nv', 'deepseek_hm_nv', 'kimi_hm_nv']
DEFAULT_NV_MODEL: glm5.1_hm_nv
glm5.1 at position 0 (PRIMARY) ✅
```

### 死变量确认
- `TIER_COOLDOWN_S` — 零匹配(已确认不存在于任何.py文件)
- `HM_CONNECT_RESERVE_S` — ✅ 活跃 (upstream.py:233 `os.environ.get("HM_CONNECT_RESERVE_S", "5")`)
- 硬编码all-keys-429冷却: `duration_s=22` (upstream.py:493) — 非环境变量可控

## 🔍 问题诊断

**根本原因**: HM2的连接层错误(SSLEOF=343+ConnectionReset=119=462/30min)持续高位。RESERVE路径从R49(8)→R51(10)→R53(12)→R57(14)→16逐步增厚,但至今未完全消除SSLEOF。HM1的RESERVE=22 vs HM2=16(72.7%差距) → HM2还需要更多SOCKS5+SSL连接预留时间。

**数据证据**:
- 30min窗口: SSLEOF=343(avg 13,264ms) + ConnectionReset=119(avg 4,128ms) = 462连接层错误
- 429仍为主导(2,204, 83% of all errors),但均匀分布 → 函数级速率限制
- 回退率82.4%,深层次99.9%成功 — 系统稳定,优化目标是减少连接错误
- 10min docker logs: SSLEOF=4, ConnectionReset=5 — 低强度但持续
- RESERVE瓶颈: tiers_tried_count=0仅1 — RESERVE未成为瓶颈,可继续增厚

**策略**: 每轮+2s增厚RESERVE,跟随R49→R51→R53→R57→R62路径。累计从8→18(+125%),目标收敛至接近HM1的22。

## 📋 优化计划

| # | 变更 | 前 | 后 | 理由 | 风险 |
|---|------|----|----|------|------|
| 1 | HM_CONNECT_RESERVE_S | 16 | **18** (+2s) | 继续RESERVE路径;每轮+2s给SOCKS5+SSL更多握手时间;SSLEOF(343/30min)需更多连接预算 | 低 — 单参数+2s增量;已验证路径R49→R51→R53→R57→R62 |

**不触碰**:
- MIN_OUTBOUND=17.0 — 稳定,与HM1一致
- KEY_COOLDOWN=26.5 — 在25-28s甜区,低于30s代码帽
- UPSTREAM_TIMEOUT=60 — 刚被R61调过(62→60)
- 硬编码22s all-keys-429 — 源码修改需独立轮次评估

## ⚙️ 执行记录

```bash
# 1. 备份
ssh opc2_uname@100.109.57.26 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R62'

# 2. 编辑 (Python脚本 → SCP)
# Line 510: HM_CONNECT_RESERVE_S: "16" → "18"
# 新注释: # R62: HM1优化 — 16→18 (+2s SOCKS5+SSL reserve; ...)

# 3. 重新部署 (docker compose自动检测变更+重建)
docker compose up -d hm40006
# → Container hm40006 Recreate → Recreated → Starting → Started

# 4. 验证
docker exec hm40006 env | grep HM_CONNECT_RESERVE_S
# → 18 ✅
docker ps --format "{{.Names}} {{.Status}}" | grep hm40006
# → hm40006 Up 12 seconds (healthy) ✅
```

## 📈 部署后验证

| 检查项 | 结果 |
|--------|------|
| HM_CONNECT_RESERVE_S运行值 | 18 ✅ (确认变更) |
| 容器健康状态 | healthy ✅ |
| 服务启动 | 12s前启动 ✅ |
| compose文件注释 | R62 ✅ |

**预期效果**: +2s RESERVE → SSLEOF/ConnectionReset每30min减少~10-20%;更快的连接建立;更少的SSL协议违例。实际效果需HM2下次数据采集验证(R63)。

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记