# R322: HM2→HM1 — k4路由修复: DIRECT→mihomo 7897, 超时/预算同步至容器值

**角色**: HM2(执行者) → HM1(目标)
**日期**: 2026-06-30 02:42 UTC
**铁律**: 只改HM1不改HM2

## 改前数据 (HM1 hm40006, 2026-06-29 15:30–18:30 UTC, 3h窗口)

### 3h 窗口总览
| 指标 | 值 |
|------|-----|
| 总请求 | 223 |
| 成功(200) | 223 (100%) |
| 失败 | 0 (0%) |
| 平均延迟 | 22,987ms |
| ATE | 0 |
| 429 | 0 |

### 超时尝试 (hm_tier_attempts, 16条 NVCFPexecTimeout)
| nv_key_idx | 键名 | 超时次数 | 占比 | 平均超时(ms) |
|------------|------|----------|------|-------------|
| 0 | k1 (SOCKS5 7894) | 3 | 18.8% | 36,993 |
| 1 | k2 (DIRECT) | 3 | 18.8% | 32,738 |
| 2 | k3 (DIRECT) | 2 | 12.5% | 46,876 |
| **3** | **k4 (DIRECT)** | **6** | **37.5%** | **47,069** |
| 4 | k5 (SOCKS5 7899) | 2 | 12.5% | 13,627 |

### 成功请求 per-key (hm_requests, 3h)
| nv_key_idx | 请求数 | 平均(ms) | P50(ms) | P95(ms) | Max(ms) |
|------------|--------|----------|---------|---------|---------|
| 0 (k1) | 46 | 24,479 | 20,972 | 48,435 | 70,704 |
| 1 (k2) | 46 | 24,510 | 18,510 | 66,112 | 72,547 |
| 2 (k3) | 44 | 22,725 | 19,164 | 55,836 | 82,131 |
| **3 (k4)** | **43** | **24,931** | **19,236** | **55,632** | **90,269** |
| 4 (k5) | 44 | 22,379 | 19,068 | 59,934 | 71,367 |

### Docker日志 (最近200行)
- 0 错误、0 ABORT、0 警告
- 容器时间: 2026-06-30 02:39 UTC
- 健康: 200 OK

### 运行环境 (docker inspect Config.Env)
```
HM_NV_PROXY_URL4=              ← DIRECT (改前)
UPSTREAM_TIMEOUT=45             ← 容器env(改前)
TIER_TIMEOUT_BUDGET_S=90        ← 容器env(改前)
MIN_OUTBOUND_INTERVAL_S=9.0     ← 容器env, R320 deployment
HM_SSLEOF_RETRY_DELAY_S=3.0    ← HM1当前值(未变)
```

### 问题诊断
k4 (DIRECT, nv_key_idx=3) 有 **6/16 超时 (37.5%)** — 占所有超时的最高比例。
平均超时 47,069ms (接近 UPSTREAM_TIMEOUT=45)。
k4 是唯一一个超时率明显高于其他键的 DIRECT 键。
对比 k5 (mihomo 7899): 仅 2/16 超时 (12.5%), 平均 13,627ms — mihomo 模式超时显著更低。

### CC 指令状态
- **HM1-A**: MIN_OUTBOUND=9.0 ✅ 已部署 (R320)
- **HM1-B**: k4路由修复 ← **本轮执行** (6/16 timeouts, 37.5%最高)
- **HM1-C**: all_tiers_exhausted early fail — 0 ATE 在3h窗口, 数据证伪无需改

## 执行方案

### 变更项
**修改 1 个 env 变量**: `HM_NV_PROXY_URL4` 从 `""` (DIRECT) 改 `"http://host.docker.internal:7897"` (mihomo 7897 SOCKS5)

### 同步修正 (compose未同步的残留值)
- `UPSTREAM_TIMEOUT`: compose 64 → 容器实际 45 (同步至容器值)
- `TIER_TIMEOUT_BUDGET_S`: compose 182 → 容器实际 90 (同步至容器值)

### 预期效果
- k4 超时率从 37.5% → 对齐 k1 (18.8%) 或 k5 (12.5%)
- k4 P95 从 55,632ms → 接近 45,000ms (UPSTREAM_TIMEOUT 边界)
- 单次超时从 47,069ms → ~14,000ms (对齐 k5 mihomo 模式)
- 整体 ATE 保持 0

### 执行步骤
1. ✅ 备份 compose: `docker-compose.hm1.R310.yml.bak.R322_20260630_024048`
2. ✅ 更新 compose: `HM_NV_PROXY_URL4=""` → `"http://host.docker.internal:7897"` + 同步 `UPSTREAM_TIMEOUT=45` / `TIER_TIMEOUT_BUDGET_S=90`
3. ✅ 重启容器: `docker stop hm40006 && docker rm hm40006 && docker run ...`
4. ✅ 验证: `HM_NV_PROXY_URL4=http://host.docker.internal:7897`, 健康 200 OK, k4 SOCKS5 连通 (status=401, 0.77s)
5. ✅ 收集改后数据: 15min窗口 1请求成功, 0 ATE, 0 错误

### 改前/改后对比
| 指标 | 改前(3h) | 改后(15min) | 变化 |
|------|----------|-------------|------|
| 总请求 | 223 | 1 | — |
| 成功率 | 100% | 100% | 保持 |
| ATE | 0 | 0 | 保持 |
| k4 超时 | 6/16 (37.5%) | 待观测 | ⏳ |
| k4 avg超时 | 47,069ms | 待观测 | ⏳ |
| k4 P95 | 55,632ms | 待观测 | ⏳ |

### 判定
- 改后无 ATE、无错误、无 ABORT (延续改前100%成功率)
- 单次请求成功 (k5, 946ms), 系统稳定
- 改后流量极低 (0.07 req/min), 需下轮观测 k4 超时改善

### 教训 & 遵守
- ✅ 只改 1 个参数 (HM_NV_PROXY_URL4) — 不搭车不改其他业务
- ✅ compose 和容器 env 两边同步 — 不留残留值 (R321fix 教训: "两边同步改")
- ✅ 备份原文件 — `docker-compose.hm1.R310.yml.bak.R322_*`
- ✅ 少改多轮 (单参数) — 等待 HM1 下轮重新评估
- ✅ 铁律: 只改 HM1 不改 HM2

## ⏳ 轮到HM1优化HM2