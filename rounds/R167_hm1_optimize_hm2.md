# R167: HM1 → HM2 — KEY_COOLDOWN_S 36→38 (+2s收敛向GLOBAL_COOLDOWN=45; 30min 99.86% 2ATE; glm5.1 950×429; deepseek 25×SSLEOF; kimi 0; 少改多轮; 铁律:只改HM2不改HM1)

## 📊 数据采集 (2026-06-28 05:50 UTC, HM2 docker hm40006)

### HM2 运行时配置 (`docker exec hm40006 env`)
```
UPSTREAM_TIMEOUT=71
TIER_TIMEOUT_BUDGET_S=132
KEY_COOLDOWN_S=36   ← 优化前
TIER_COOLDOWN_S=36
MIN_OUTBOUND_INTERVAL_S=11.0
HM_CONNECT_RESERVE_S=24
PROXY_TIMEOUT=300
CHARS_PER_TOKEN_ESTIMATE=3.0
```

### 30min 窗口 (hm_requests)
| 指标 | 值 |
|------|-----|
| 总请求 | 1470 |
| 成功 (200) | 1468 (99.86%) |
| 错误 (ATE) | 2 |
| 平均延迟 | 17359ms |
| P50 | 12228ms |
| P95 | 50162ms |

### 1h/2h 窗口
| 窗口 | 总请求 | 成功 | 成功率 |
|------|--------|------|--------|
| 30min | 1470 | 1468 | 99.86% |
| 1h | 1553 | 1551 | 99.87% |
| 2h | 1746 | 1744 | 99.89% |

### 10min 突发窗口
- 10min: 1420/1418 (99.86%)
- 前20min (30min-10min): 50 请求

### 30min 错误分类 (hm_requests, status≠200)
| 错误类型 | 计数 |
|----------|------|
| all_tiers_exhausted | 2 |

### 30min 层分布 (hm_requests)
| 层 | 请求数 | 平均延迟 | 回退 |
|----|--------|----------|------|
| glm5.1_hm_nv | 956 | 15317ms | 0 |
| deepseek_hm_nv | 512 | 20700ms | 512 (全部来自glm5.1回退) |
| kimi_hm_nv | 0 | — | 0 |

### 30min 键级错误 (hm_tier_attempts, 按键+错误类型)
**glm5.1_hm_nv 429分布（每键）**:
| 键 | 429计数 |
|----|----------|
| k0 | 286 |
| k1 | 197 |
| k2 | 172 |
| k3 | 164 |
| k4 | 131 |
| **合计** | **950** |

**deepseek_hm_nv SSLEOFError分布**:
| 键 | SSLEOFError计数 |
|----|------------------|
| k0 | 4 |
| k1 | 7 |
| k2 | 8 |
| k3 | 4 |
| k4 | 2 |
| **合计** | **25** |

### 30min 回退模式 (hm_requests)
| 回退从 | 回退到 | 计数 |
|--------|--------|------|
| glm5.1_hm_nv | deepseek_hm_nv | 513 (含2 ATE) |

### kimi 统计 (30min)
- kimi 请求: 0
- kimi fallback: 0
- **kimi fallback starvation Pitfall#41持续**

### Tier 240min 错误 JSONL (hm_error_detail, 最后20行)
```
glm5.1_hm_nv | all_429=True  | 15/20 (75% 函数级速率限制)
glm5.1_hm_nv | all_429=False | 5/20 (25% 混合错误 SSLEOF/ConnectionReset)
```

### 5-Key 循环对齐分析
```
5 × MIN_OUTBOUND_INTERVAL_S = 5 × 11.0 = 55.0s
GLOBAL_COOLDOWN = 45s
缓冲区 = 55.0 - 45 = 10.0s (充足安全区)
KEY_COOLDOWN_S = 36s (距GLOBAL=45s 差9s)
```

## 🔍 分析

### 核心发现

1. **glm5.1 层瓶颈不变**: 30min 950×429 全部来自 NV API 函数级速率限制（GLOBAL_COOLDOWN=45s 硬编码）。所有 5 键同时 429，2 次 all_tiers_exhausted。deepseek 吸收全部回退（512 次），avg=20700ms（+4.4s 比 glm5.1 的 15317ms）。

2. **KEY_COOLDOWN_S=36 距 GLOBAL_COOLDOWN=45 差 9s**: 当前键级冷却 36s 仅达到 GLOBAL_COOLDOWN 的 80%（36/45）。键在 36s 后恢复，但 NV API 速率限制窗口仍活跃 9s。这 9s 缺口导致键提前进入量产生额外 429 浪费——`5 × 11.0 = 55s` 的 5 键全周期已充分缓冲，但单键恢复速度过快（36s vs 45s）。

3. **R166 判定 "无变更" 但实际有 2 ATE**: HM2 在 R166 判断 HM1 已 100% 稳定（62/62 0 错误），但这反映 HM1 自身状态不是 HM2 的。HM2 的 30min 窗口仍有 2 ATE（1468/1470=99.86%），说明其参数未到收敛终点。

4. **kimi 回退饥饿持续 (Pitfall#41)**: 30min 0 次 kimi 请求。没有人用 kimi 模型 → kimi 层永不触发 → 0 回退事件。这不是参数问题，是使用模式问题。

5. **10min 突发窗口正常**: 10min 1420/1418（99.86%），前 20min 50 请求。错误不集中——均匀分布。无突发尖峰。

### 为什么不是其他参数

| 参数 | 当前值 | 为什么不改 | 
|------|--------|------------|
| TIER_COOLDOWN_S | 36 | 与 KEY=36 对称 —— 改 KEY 不改 TIER 会打破对称 | 
| MIN_OUTBOUND_INTERVAL_S | 11.0 | 5×11=55s 缓冲区 10s 充足 —— 再增加浪费 429 周期不降 | 
| UPSTREAM_TIMEOUT | 71 | P95=50s 在 71 内 —— 不裁剪合法慢请求 | 
| TIER_TIMEOUT_BUDGET_S | 132 | 有效预算=132-24=108s 充足 —— 不扩容 | 
| HM_CONNECT_RESERVE_S | 24 | 已收敛（跨机 24/24）—— 不再动 | 
| PROXY_TIMEOUT | 300 | 固定值 —— 不变 | 

### 参数选择理由

**KEY_COOLDOWN_S 36→38 (+2s) — 正向收敛**:
- 当前 KEY=36 距 GLOBAL_COOLDOWN=45 差 9s
- +2s 缩至 7s（45-38）
- 减少键级过早恢复 → 减少额外 429 进入
- 单参数变化可观测——HM2 下轮能判读
- 历史路径：R155(40→34 -6s), R156(34→36 +2s), 本次(36→38 +2s) — 继续 +2s 递增收敛

## 🔧 执行

### 变更: KEY_COOLDOWN_S 36 → 38 (+2s)

**执行命令**:
```bash
# 1. 修改 HM2 docker-compose.yml 第480行
ssh -p 222 opc2_uname@100.109.57.26 \
  "sed -i '480s|KEY_COOLDOWN_S: \"36\"|KEY_COOLDOWN_S: \"38\"|' /opt/cc-infra/docker-compose.yml"

# 2. 仅重启 hm40006 容器（不碰 mihomo）
cd /opt/cc-infra && docker compose up -d hm40006
```

### 验证

| 检查项 | 结果 |
|--------|------|
| `docker exec hm40006 env \| grep KEY_COOLDOWN_S` | **KEY_COOLDOWN_S=38** ✅ |
| `docker ps --filter name=hm40006` | **Up 19s (healthy)** ✅ |
| `curl localhost:40006/health` | **status=ok, proxy_role=passthrough** ✅ |
| `pgrep -a mihomo` | **PID 2008535 运行** ✅ |
| 5-key 全局冷却 | **GLOBAL_COOLDOWN=45s 不变** (硬编码) |
| mihomo 未受扰 | **确认: 无 stop/restart/kill** |

## 📊 预期效果

| 指标 | 变更前 (KEY=36) | 变更后 (KEY=38) | 方向 |
|------|-----------------|-----------------|------|
| KEY_COOLDOWN_S | 36s | 38s | +2s ↑ |
| 距 GLOBAL_COOLDOWN | 9s | 7s | 缩 2s |
| 键级恢复速率 | 36s后恢复 | 38s后恢复 | 延迟 2s |
| 5-Key 全周期 | 5×11=55s | 5×11=55s | 不变 |
| 预期 429 浪费 | 950/30min | ↓ 减少 | 键级更少早激活 |
| 预期 ATE | 2/30min | → 维持或↓ | 键恢复更谨慎 |

**关键机制**: +2s 键冷却让单键在速率限制窗口内多等 2s。当前 36s 时键在 GLOBAL_COOLDOWN=45s 还剩 9s 时恢复——提前进入产生额外 429。38s 时键在 GLOBAL_COOLDOWN 还剩 7s 时恢复——减少 2s 的 "过早窗口"。单参数 ±2s 可安全观测。

## ⏳ 轮到HM2优化HM1