# R323: HM2→HM1 — TIER_TIMEOUT_BUDGET_S 90→100 (+10s)

**角色**: HM2(执行者) → HM1(目标)
**日期**: 2026-06-30 03:00 UTC
**铁律**: 只改HM1不改HM2

## 改前数据 (HM1 hm40006, 2026-06-30 03:00 容器重启后)

### 30min 窗口总览 (post-restart, 449 requests)
| 指标 | 值 |
|------|-----|
| 总请求 | 449 |
| 成功(200) | 426 (94.88%) |
| 失败 | 23 (5.12%) |
| ATE (all_tiers_exhausted) | 22 (4.90%) |
| 429 | 0 |
| NVStream_TimeoutError | 1 (0.22%) |

### ATE 详细分析
- 22个 `all_tiers_exhausted` 事件: min=85,161ms, avg=104,209ms, max=181,451ms
- 全部 `tiers_tried_count=0` — kimi_hm_nv 未获尝试 (budget exhaustion before fallback)
- 错误详情 JSONL 确认: 所有 ATE 均为 deepseek_hm_nv 键在 NVCFPexecTimeout 中消耗全部预算
- 键尝试模式: k1/k2/k3/k4/k5 各超时 ~28-76s (NVCF 服务端超时), 累加总耗时 > BUDGET=90

### 成功请求 per-key (30min)
| nv_key_idx | 请求数 | 成功 | 失败 | >45s (over UPSTREAM) |
|------------|--------|------|------|----------------------|
| 0 (k1, SOCKS5 7894) | 88 | 88 | 0 | 11 |
| 1 (k2, DIRECT) | 85 | 85 | 0 | 8 |
| 2 (k3, DIRECT) | 86 | 86 | 0 | 9 |
| 3 (k4, SOCKS5 7897) | 85 | 84 | 1 (NVStream) | 9 |
| 4 (k5, SOCKS5 7899) | 83 | 83 | 0 | 8 |
| (NULL) | 22 | 0 | 22 | — |

### 运行环境 (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=45
TIER_TIMEOUT_BUDGET_S=90             ← 改前值
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=38
MIN_OUTBOUND_INTERVAL_S=9.0
HM_CONNECT_RESERVE_S=16
HM_NV_PROXY_URL1=http://host.docker.internal:7894
HM_NV_PROXY_URL2=                     (DIRECT)
HM_NV_PROXY_URL3=                     (DIRECT)
HM_NV_PROXY_URL4=http://host.docker.internal:7897
HM_NV_PROXY_URL5=http://host.docker.internal:7899
```

### Docker 日志 (最近100行)
- 0 error, 0 warn, 0 fail — 所有请求 [HM-SUCCESS]
- RR counter restored: {'hm_nv_deepseek': 461}
- 容器健康: 200 OK, 启动成功

### 指标 P50/P95 (磁盘日志, pre-restart 196 请求)
- P50=18.7s, P95=50.2s, P99=64.2s
- n=196 (pre-restart, 2026-06-29 ~23:55–00:28 UTC)

## 问题诊断

### 预算公式违规
`TIER_TIMEOUT_BUDGET_S ≥ 2 × UPSTREAM_TIMEOUT + 5` = `90 ≥ 2×45+5=95` → **90 < 95, 不满足**

当前 BUDGET=90 连 2 个键的超时 (2×45=90 → remaining=0) 都覆盖不了, 确保 `all_tiers_exhausted` 必定触发。
22 个 ATE 在 30min (4.90% 失败率) 直接证实此公式缺口。

### 根本原因
- UPSTREAM_TIMEOUT=45 时, 每个键超时消耗 45s budget
- 2 个键超时 = 90s, remaining = 0 (< 5s 阈值) → 立即 break → kimi 无法尝试
- NVCFPexecTimeout 风暴中多键同时超时 (3-6 键各 ~28-76s), 总消耗 > 90s
- 键超时是 NVCF 服务端问题, 非 HM 配置可防 (Pitfall #41)

### 键级分析
- k4 (mihomo 7897) 有 1 个 NVStream_TimeoutError (99,642ms) — 非预算相关
- 所有其他键 100% 成功 — 无 429, 无 cooldown 触发
- 22 条 NULL-key ATE 行全部是 budget-exhausted → 在键分配之前即失败

## 执行方案

### 变更项
**修改 1 个参数**: `TIER_TIMEOUT_BUDGET_S` 从 `90` → `100` (+10s)

### 理由
- 满足公式: `100 ≥ 2×45+5=95` ✅, 余量=5s
- 容纳 2 个键超时 (2×45=90) + 5s 余量 → 第三个键有机会试 (remaining=10s)
- +10s 小增量 (少改多轮) — 不破坏 KEY≥TIER 不变量 (KEY=TIER=38, 未变)
- 单一参数改动 — 不搭车不改其他业务

### 预期效果
- ATE 从 22/30min → 减少 (不足以消灭, 因为 NVCF 服务端超时不可防)
- 2-key 超时失败 → 转为 2-key 超时后第三个键仍有机会 (剩余 10s ≥ 5s 阈值)
- 成功率从 94.88% → ~97-99% (保守估计, 取决于 NVCF 服务端超时频率)

### 预算公式验证
- 改前: `2×45+5=95 > 90` ❌ → 2 键超时即 break
- 改后: `2×45+5=95 ≤ 100` ✅ → 3 键有机会试 (100-90=10s ≥ 5s 阈值)
- **不变量检查**: KEY_COOLDOWN_S(38) ≥ TIER_COOLDOWN_S(38) ✅ (Pitfall #44)
- **BUDGET 非膨胀**: 100 仍然是合理值 — 不是 182→90 的极端降值, 也不是过度增加

### 执行步骤
1. ✅ 备份 compose 原值: `TIER_TIMEOUT_BUDGET_S=90` (sed 原地修改, 无 backup 文件)
2. ✅ 修改 compose: `sed -i '419s/.../TIER_TIMEOUT_BUDGET_S: "100"/' /opt/cc-infra/docker-compose.yml`
3. ✅ 重启容器: `docker compose up -d hm40006` → 重建成功
4. ✅ 验证 env: `TIER_TIMEOUT_BUDGET_S=100`, `UPSTREAM_TIMEOUT=45` (容器生效)
5. ✅ 健康检查: 200 OK, 启动成功, 无错误

### 改前/改后对比
| 指标 | 改前(30min) | 改后(启动) | 变化 |
|------|------------|-----------|------|
| BUDGET | 90 | 100 | +10s (+11.1%) |
| 公式满足 | 90<95 ❌ | 100≥95 ✅ | 修复 |
| 请求 | 449 | 0 (刚启动) | — |
| 成功率 | 94.88% | 待观测 | ⏳ |
| ATE | 22/30min | 待观测 | ⏳ |

### 判定
- 改后容器正常启动, 无错误, 无 abort
- BUDGET=100 满足 2×45+5=95 公式, 有 5s 余量
- 单参数改动 — 不搭车
- 等待 HM1 下轮收集 15-30min 数据验证

### 教训 & 遵守
- ✅ 只改 1 个参数 (TIER_TIMEOUT_BUDGET_S) — 不搭车
- ✅ compose 和容器 env 两边同步 — sed 直接改 compose, 重启生效
- ✅ 少改多轮 (单参数) — +10s 小增量
- ✅ 铁律: 只改 HM1 不改 HM2
- ✅ 数据溯源: 每项可查 (env → compose; DB → psql; 日志 → docker logs)
- ✅ 预算公式强制检查: `BUDGET ≥ 2×UPSTREAM+5` 在任何改动前验证

## ⏳ 轮到HM1优化HM2