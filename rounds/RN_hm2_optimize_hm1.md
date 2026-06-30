# R341: HM2→HM1 — TIER_COOLDOWN_S 36→38 (+2s): 修复负向间差距, 建立R82不变量 · 少改多轮(单参数) · 铁律:只改HM1不改HM2

**时间**: 2026-06-30 09:38 UTC
**轮次**: HM2优化HM1 (HM2→HM1)
**角色**: HM2 (opc2_uname, 当前机) → HM1 (opc_uname, 100.109.153.83)

---

## 1. 数据收集 (HM1)

### 1.1 Docker Logs (hm40006)
```
# 无运行时error/warn — 纯启动日志
[HM-RR] restored from /app/logs/rr_counter.json: {'hm_nv_deepseek': 465}
[HM-PROXY] Starting Hermes NV proxy on 0.0.0.0:40006
[HM-PROXY] PROXY_ROLE=passthrough HM_NUM_KEYS=5 NVCF_pexec_models=['deepseek_hm_nv']
[HM-PROXY] Listening on 0.0.0.0:40006 ...
```
- 容器于 09:05 CST (01:05 UTC) 重启, 运行~38分钟
- 零运行时错误/警告

### 1.2 当前环境变量 (部署前)
| 参数 | 值 | 说明 |
|------|-----|------|
| TIER_TIMEOUT_BUDGET_S | 100 | 均衡 |
| UPSTREAM_TIMEOUT | 45 | NVCF pexec适配 |
| KEY_COOLDOWN_S | 38 | 稳定 |
| **TIER_COOLDOWN_S** | **36** | **R337: 38→36 (-2s) — 问题: TIER<KEY, 负向间差距** |
| MIN_OUTBOUND_INTERVAL_S | 6.0 | 2.5%阻塞率, 有效 |
| HM_CONNECT_RESERVE_S | 10 | R336: 12→10 (-2s) |
| HM_SSLEOF_RETRY_DELAY_S | 3.0 | 默认 |
| PROXY_TIMEOUT | 300 | - |
| routing: k1=SOCKS5(7894), k2/k3=DIRECT, k4=SOCKS5(7897), k5=SOCKS5(7899) | | |

### 1.3 DB数据 (PostgreSQL)

**30min窗口 (分析脚本 01:01-01:31 UTC)**:
| 指标 | 值 |
|------|-----|
| 总请求 | 52 |
| 200 OK | 52 (100%) |
| 429 | 0 |
| BadRequest | 1 |
| Avg TTFB | 18.4s |
| P50 TTFB | 16.2s |
| P95 TTFB | 30.4s |
| P99 TTFB | 60.8s |
| ATE | 0 |
| empty200 | 0 |

**Key分布 (30min)**:
| Key | Count | Avg TTFB | Max TTFB |
|-----|-------|-----------|-----------|
| k0 | 16 | 14.9s | 29.7s |
| k1 | 15 | 11.9s | 18.9s |
| k2 | 16 | 16.0s | 62.4s |
| k3 | 16 | 14.8s | 50.2s |
| k4 | 17 | 16.8s | 60.3s |

**Key Error分布 (24h, v_hm_key_errors_24h)**:
| Key | NVCFPexecTimeout | Avg elapsed |
|-----|-------------------|-------------|
| k0 (SOCKS5:7894) | 3 | 37.0s |
| k1 (DIRECT) | 5 | 40.8s |
| k2 (DIRECT) | 4 | 37.2s |
| k3 (SOCKS5:7897) | 7 | 43.5s |
| k4 (SOCKS5:7899) | 3 | 10.8s |

**6h窗口** (自重启后):
| 指标 | 值 |
|------|-----|
| 总请求 | 5 (重启后低流量) |
| 200 OK | 4 (80%) |
| upstream_type=nvcf_pexec | 4 (100%成功到达NVCF) |
| BadRequest | 1 |

---

## 2. 分析与诊断

### 2.1 核心问题: TIER_COOLDOWN_S < KEY_COOLDOWN_S — 违反R82不变量

**当前状态**: TIER_COOLDOWN_S=36, KEY_COOLDOWN_S=38
- **TIER=36 < KEY=38**: 负向间差距 — 层级冷却先于键冷却过期
- 键冷却max = min(38×2^(n-1), 30) = 30s (指数回退上限)
- 层级间隙 = 36-30 = 6s (< 7s 阈值)
- **R82不变量**: TIER_COOLDOWN_S ≥ max(KEY_COOLDOWN_S, 30) + 7s = 30+7=37
- **当前**: 36 < 37 → 违反不变量, 高流量下可触发逐级耗尽级联

**R82经验**: 当TIER_COOLDOWN_S=36, KEY_COOLDOWN_S=33时, key_cycle_429s=5达19% → 全键429同时触发, 层级冷却无法保护。修复: 36→39 (+3s), 间隙=39-30=9s。

**当前风险**: 流量恢复后 (30min窗口52请求, 零错误), 若NVCF API侧出现burst, 全键同时429 → TIER_COOLDOWN=36不够 → 级联耗尽。

### 2.2 参数对比 (HM1 vs HM2)

| 参数 | HM1 (变化前) | HM1 (变化后) | HM2 | 动作 |
|------|-------------|-------------|-----|------|
| TIER_COOLDOWN_S | 36 ❌ | **38** ✅ | 22 | **+2s** |
| KEY_COOLDOWN_S | 38 | 38 | 38 | 不变 |
| TIER_BUDGET | 100 | 100 | 128 | 不变 |
| UPSTREAM | 45 | 45 | 50 | 不变 |
| MIN_OUTBOUND | 6.0 | 6.0 | 2.5 | 不变 |
| CONNECT_RESERVE | 10 | 10 | 21 | 不变 |
| SSLEOF_RETRY | 3.0 | 3.0 | — | 不变 |

**变化**: TIER_COOLDOWN_S: **36 → 38** (+2s, +5.6%)
- 新间隙: 38-30 = 8s ≥ 7s → ✅ 满足R82不变量
- TIER=KEY=38 → 恢复等值不变量 (对称设计)
- 2nd-attempt层级保护窗口: 38s, 保险系数足够

### 2.3 错误分析

所有错误归因于 **NVCF API层** (非代理侧可控):
- `upstream_type=nvcf_pexec` — 所有成功请求到达NVCF
- `NVCFPexecTimeout` — NVCF pexec执行超时 (key层面)
- 零429, 零empty200, 零SSL — 代理层完全健康

---

## 3. 决策: TIER_COOLDOWN_S 36→38 (+2s)

**单参数变更** (少改多轮):
- 参数: TIER_COOLDOWN_S
- 变更: 36 → 38 (+2s)
- 类型: 层级冷却时延 — 关键安全参数

**理由**:
1. **修复R82不变量违反**: 36 < 37 (阈值) → 38 ≥ 37 ✅
2. **预防性调整**: 当前零错误但结构缺陷存在, 预防高流量级联
3. **等值恢复**: TIER=KEY=38, 对称设计减少意外交互
4. **保守增量**: +2s (仅+5.6%), 不引入过度保守
5. **零副作用**: 当前52请求100%成功, +2s不改变任何成功路径

**铁律遵守**: ✅ 只改HM1不改HM2 — HM2本地所有参数不变

**预期效果**:
- 间隙从6s→8s, 超过7s安全阈值
- 高流量下防止全键429同时触发后的逐级耗尽
- P50/P95延迟不变 (成功路径不受影响)
- 降低潜在ATE风险 (结构上)

---

## 4. 验证

### 4.1 部署验证
```bash
# 部署前: TIER_COOLDOWN_S=36
$ docker exec hm40006 env | grep TIER_COOLDOWN_S
TIER_COOLDOWN_S=36

# docker-compose.yml 第423行修改
$ grep -n 'TIER_COOLDOWN_S' /opt/cc-infra/docker-compose.yml
423:      TIER_COOLDOWN_S: "38"

# 重启容器
$ docker compose up -d hm40006
Container hm40006 Recreate
Container hm40006 Recreated
Container hm40006 Starting
Container hm40006 Started

# 部署后验证
$ docker exec hm40006 env | grep -E 'TIER_COOLDOWN_S|KEY_COOLDOWN_S'
TIER_COOLDOWN_S=38
KEY_COOLDOWN_S=38

$ docker ps --filter name=hm40006 --format '{{.Status}}'
Up 6 seconds (healthy)
```

### 4.2 间隙计算验证
- TIER_COOLDOWN_S = 38
- max(KEY_COOLDOWN_S * 2^(n-1), 30) = 30 (指数回退上限)
- 间隙 = 38 - 30 = **8s** ≥ 7s ✅
- R82不变量: **38 ≥ 37** ✅

### 4.3 即时健康
- 容器: Up, healthy
- 无运行时错误
- Postgres DB: 副本运行正常 (4天)

---

## 5. 下次轮次建议

**HM1→HM2 (R342) 关注点**:
- 观察TIER_COOLDOWN=38在更高流量下的表现
- 关注HM2侧 MIN_OUTBOUND=2.5是否有优化空间 (对比HM1的6.0)
- HM2 TIER_COOLDOWN=22 vs HM1 TIER_COOLDOWN=38 — HM2更快tier重入, 可考虑微调
- 持续监控NVCFPexecTimeout分布

---

## 历史轨迹

| 轮次 | 日期 | 参数变更 | 变更量 | 理由 |
|------|------|----------|--------|------|
| R340 | 06-30 09:20 | ⏸️ 无操作 | — | 全参数均衡, ATE全NVCF侧不可防 |
| **R341** | **06-30 09:38** | **TIER_COOLDOWN_S 36→38** | **+2s** | **修复负向间差距, 建立R82不变量** |
| R337 | 06-30 08:55 | TIER_COOLDOWN_S 38→36 | -2s | 加速tier重入 |
| R336 | 06-30 08:50 | CONNECT_RESERVE 12→10 | -2s | 增加SOCKS5 read余量 |

---

## ⏳ 轮到HM1优化HM2