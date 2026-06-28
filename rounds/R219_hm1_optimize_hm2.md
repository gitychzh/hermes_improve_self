# R219: HM1 → HM2 — 部署TIER_COOLDOWN_S 44→45 (+1s) 消除GLOBAL_COOLDOWN=45s的1s部署差距

**回合类型**: 部署同步 (容器部署，compose文件已有45但运行env仍为44)
**时间**: 2026-06-28 15:37 UTC
**角色**: HM1 (opc_uname) → 优化HM2
**原则**: 少改多轮 (单参数+1s); 铁律: 只改HM2不改HM1; 更低报错/更快请求/超低延迟/稳定优先

## 📊 数据采集 (2026-06-28 15:07-15:37 UTC, ~30min窗口)

### 运行环境快照 (变更前HM2)
```
KEY_COOLDOWN_S=38        TIER_COOLDOWN_S=44     ← 运行中44, 但compose文件已是45 (部署差距)
UPSTREAM_TIMEOUT=54       MIN_OUTBOUND_INTERVAL_S=15.6
HM_CONNECT_RESERVE_S=20   TIER_TIMEOUT_BUDGET_S=115
```

### 30分钟窗口数据 (PostgreSQL hm_requests)
| 指标 | 数值 |
|------|------|
| 总请求 | 1196 |
| 成功 (200) | 1186 (99.16%) |
| 失败 | 10 (9 all_tiers_exhausted + 1 NVStream) |
| 平均延迟 | 24923ms |
| P50 | 19926ms |
| P95 | 58874ms |

### 10分钟窗口 (最近突发)
| 指标 | 数值 |
|------|------|
| 总请求 | 1144 |
| 成功 | 1135 (99.21%) |
| 失败 | 9 (8 ATE + 1 NVStream) |

### 1小时窗口
| 指标 | 数值 |
|------|------|
| 总请求 | 1275 |
| 成功 | 1264 (99.14%) |
| 失败 | 11 (10 ATE + 1 NVStream) |

### 按Tier分布 (hm_requests, 30min)
```
deepseek_hm_nv | 989 | avg=25505ms | fallback=693 (70.1%)
glm5.1_hm_nv   | 198 | avg=17108ms | fallback=3   (1.5%)
NULL (ATE)      |   9 | avg=132904ms | fallback=0
```

### Key级429分布 (hm_tier_attempts, glm5.1_hm_nv, 30min)
| Key | 429计数 | 占比 |
|-----|---------|------|
| k4 | 286 | 21.1% |
| k3 | 282 | 20.8% |
| k2 | 280 | 20.6% |
| k1 | 267 | 19.7% |
| k0 | 242 | 17.8% |
| **总计** | **1357** | **100%** |

5键429均匀分布 = 函数级限流 (NVCF per-functionID: `glm5.1`), 非per-key瓶颈

### 错误明细JSONL (host日志, 最新20条)
20条错误中:
- **14条 all_429: true** (70%) — glm5.1函数级全键429饱和
- 3条 deepseek all-keys-failed: NVCFPexecTimeout (纯上游超时, 非429)
- 3条混合模式: SSLEOFError + ConnectionReset + 429

### Tier预算断点 (host日志)
```
[14:10:37] deepseek_hm_nv budget=115s remaining 7.8s < 10s → break
[14:26:37] deepseek_hm_nv budget=115s remaining 8.4s < 10s → break
[15:26:52] deepseek_hm_nv budget=115s remaining 8.6s < 10s → break
```
3次deepseek预算断点, 全是NVCFPexecTimeout(50s+)消耗预算

### Mihomo状态
```
pgrep -a mihomo → 2008535 ✅ 运行中, 绝对不碰
```

## 🔍 分析

### 核心发现: TIER_COOLDOWN_S部署差距 (compose=45, env=44)

**Docker compose文件**: `TIER_COOLDOWN_S: "45"  # R182: HM1→HM2 — 44→45 (+1s)`
**运行env**: `TIER_COOLDOWN_S=44` (容器未重建, 仍用旧值)

这是`compose-comment-vs-running-env-pitfall`的经典案例:
- R182写入compose文件 `44→45` 并添加注释
- 但容器从未执行 `docker compose up -d --force-recreate`
- 容器运行40+分钟仍用 `TIER_COOLDOWN_S=44`
- 所有30min数据窗口都是旧参数(44)产生的

### 1s差距的影响

GLOBAL_COOLDOWN=45s是硬编码在`gateway/gateway.py`中的全局冷却时间:
- 当所有5个NV键返回429时, 触发 `_global_cooldown_until = now + 45s`
- TIER_COOLDOWN_S=44 → tier级冷却44s后解除, 比GLOBAL_COOLDOWN早1s
- 这1s窗口内: tier已冷却, 但全局冷却仍在 → 新请求进入tier → 立即命中429
- 关闭这1s差距: tier冷却=45=全局冷却, 同步解除

### 为什么不是其他参数

| 参数 | 当前值 | 为什么不改 |
|------|--------|-----------|
| KEY_COOLDOWN_S | 38 | 差距7s到GLOBAL=45, 但30min数据未显示单一key过度冷却; R199已有+2s增量; 留待观察 |
| UPSTREAM_TIMEOUT | 54 | R218刚+4s (50→54); P95=58.8s > 54s, 但需要至少1轮验证效果; 不变 |
| MIN_OUTBOUND_INTERVAL_S | 15.6 | 5×15.6=78s >> GLOBAL=45s; 安全窗口28s; 429密度证明当前间隔足够; 不变 |
| HM_CONNECT_RESERVE_S | 20 | 差距4s到HM1=24; 但SSLEOFError=97/30min, 覆盖在UPSTREAM_TIMEOUT=54内; 不变 |
| TIER_TIMEOUT_BUDGET_S | 115 | 3次deepseek断点(7.8s/8.4s/8.6s < 10s), 但断点原因是NVCFPexecTimeout(50s+)不是budget不足; 不变 |
| PROXY_TIMEOUT | 300 | 固定值, 几乎不变; 不变 |

**唯一选择**: TIER_COOLDOWN_S=44→45 (+1s) — 消除1s GLOBAL-COOLDOWN部署差距; 单参数最小变更

## 🔧 执行: TIER_COOLDOWN_S 44→45 (部署同步)

### 操作步骤
1. 确认compose文件已有45 (R182已写) → `grep TIER_COOLDOWN_S /opt/cc-infra/docker-compose.yml`
2. 重建容器 → `docker compose up -d --force-recreate --no-deps hm40006`
3. 等待5s → 验证运行env: `docker exec hm40006 env | grep TIER_COOLDOWN_S` → 45 ✅
4. 全参数验证: KEY=38, TIER=45, UPSTREAM=54, MIN=15.6, CONNECT=20, BUDGET=115 ✅

### 验证清单
| 检查项 | 状态 |
|--------|------|
| `docker exec env` 确认 TIER_COOLDOWN_S=45 | ✅ |
| `docker ps` → Up (healthy) | ✅ |
| `curl /health` → 200, 3 tiers, deepseek default | ✅ |
| `pgrep -a mihomo` → 运行中 | ✅ |
| 所有7参数 unchanged except TIER_COOLDOWN_S | ✅ |

### 容器健康检查
```
{"status": "ok", "hm_model_tiers": ["deepseek_hm_nv", "glm5.1_hm_nv", "kimi_hm_nv"],
 "hm_default_model": "deepseek_hm_nv"}
```

## 📈 预期效果

### Before/After
| | Before (运行中) | After (部署后) |
|------|------|------|
| TIER_COOLDOWN_S | 44s | **45s** |
| GLOBAL_COOLDOWN | 45s (硬编码) | 45s |
| 差距 | **-1s** | **0s** (完全对齐) |
| 30min成功率 | 99.16% (1186/1196) | → 预期 ≥99.2% |
| 10min成功率 | 99.21% (1135/1144) | → 预期 ≥99.3% |

### 评判标准
| 标准 | 状态 |
|------|------|
| 更少报错 | 9 ATE → 预期 7-8 |
| 更快请求 | 无需等待 tier/global 冷却不同步 |
| 超低延迟 | P50=19.9s, P95=58.9s |
| 稳定优先 | 单参数+1s, 少改多轮 |

**铁律**: ✅ 只改HM2不改HM1

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记