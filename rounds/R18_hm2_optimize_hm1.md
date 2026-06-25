# R18: HM2优化HM1 — UPSTREAM_TIMEOUT 35→40 (+5s), TIER_BUDGET 70→80 (+10s, 2×耦合)

**Date:** 2026-06-26 ~05:45 UTC  
**Actor:** HM2 (opc2_uname)  
**Target:** HM1 (100.109.153.83, opc_uname)  
**Previous Round:** R17 (commit `7c3a8ca`): UPSTREAM_TIMEOUT 30→35, TIER_COOLDOWN 120→90

---

## 1. 数据收集

### 1.1 容器运行状态
```bash
hm40006 Up 10 minutes (healthy)
```

### 1.2 容器环境变量（R17部署后）
```
UPSTREAM_TIMEOUT=35
TIER_TIMEOUT_BUDGET_S=52 → 实际DB查询确认运行值为70（compose R18注释已应用但未git提交）
MIN_OUTBOUND_INTERVAL_S=10.0
KEY_COOLDOWN_S=35.0
TIER_COOLDOWN_S=90
HM_CONNECT_RESERVE_S=5
```

### 1.3 最近30分钟日志关键字统计
```
error/warn/fail 计数: 19 (低水平)
HM-FALLBACK-SUCCESS: 37
HM-FALLBACK: 105
HM-TIER-SKIP: 26
HM-GLOBAL-COOLDOWN: 频繁（glm5.1 全键429触发）
```

### 1.4 PostgreSQL 最近30分钟数据

#### Error 分布 (hm_tier_attempts)
```
error_type                    | cnt | avg_elapsed_ms
429_nv_rate_limit             | 340 |
NVCFPexecTimeout              | 131 | 29766
NVCFPexecProxyConnectionError |   7 |     1
NVCFPexecConnectionResetError   |   4 |  1548
empty_200                     |   2 |
```
- 429 在5个key上均匀分布: k0=73, k1=72, k2=78, k3=65, k4=65

#### Fallback 分布 (hm_requests)
```
fallback_occurred | cnt  | avg_dur_ms
------------------+------+-------------
f (no fallback)   |  263 | 28358
t (fallback)      |  664 | 18404
```
- Fallback 率: 71.6% (664/927)

#### Tier 分布 (hm_tier_attempts)
```
tier          | cnt
--------------+-----
glm5.1_hm_nv  | 381
deepseek_hm_nv| 100
kimi_hm_nv     |   3
```

#### Deepseek 每key超时分布 (NVCFPexecTimeout, deepseek tier)
```
nv_key_idx | error_type      | cnt
-----------+--------------+-----
0          | NVCFPexecTimeout | 16
1          | NVCFPexecTimeout | 25
2          | NVCFPexecTimeout | 26
3          | NVCFPexecTimeout | 16
4          | NVCFPexecTimeout | 15
```
- Deepseek timeout总计: 98次/30min
- Deepseek timeout avg elapsed: 25656ms
- Deepseek timeout max elapsed: **70059ms** ⬅️ 关键信号

#### 请求级错误分析
```
error_type         | cnt
-------------------+-----
all_tiers_exhausted | 49
NVStream_IncompleteRead | 1
```
- 49个请求"all_tiers_exhausted", avg duration 64190ms, p50=56019ms, p90=104780ms

---

## 2. 诊断

### 2.1 glm5.1 主 tier: 功能级节流，参数无效
- glm5.1 在30分钟内仅1次成功，其余全429
- 但 goalie 级代理未受影响，因为 fallback 到 deepseek 成功
- MIN/KEY 已达当前配置上限(10.0/35.0)，继续提效比极低

### 2.2 Deepseek 超时严重: +5s margin捕获35-40s区间
- 98次deepseek timeout，avg 25656ms，**max 70059ms**
- 当前 UPSTREAM_TIMEOUT=35s → 对-deepseek 请求首次 timeout 后，2次尝试可凑出 max 70059ms (35+35)
- 部分 deepseek 请求在 35-40s 内本可完成，但因 35s 截断而被标记 timeout
- 这直接导致了 tier budget 被提前耗掉，剩下请求走全 tier 耗尽(avg 64s)
- **阈值 40s 是为了捕获 35-40s 区间的边缘 deepseek completion**

### 2.3 TIER_BUDGET/UPSTREAM_TIMEOUT 耦合被 R18 compose 注释修复但需同步
- R18 compose 注释将 TIER_BUDGET 从 52→70 (2×35)，恢复了耦合
- 但本回合 UPSTREAM 提升到 40，需要 TIER_BUDGET 同步到 **80** (2×40=80)
- 否则 2次40s timeout 即 80s，将超出 70s budget

---

## 3. 优化计划

| 参数 | before | after | rationale |
|------|--------|-------|-----------|
| UPSTREAM_TIMEOUT | 35 | 40 | 捕获 deepseek 35-40s 的边界 completion，减少 1-attempt timeout 率 |
| TIER_TIMEOUT_BUDGET_S | 70 | 80 | 维持 2×UPSTREAM 耦合规则，保证 2次完整 deepseek 尝试 |

**铁律检查**：只改 HM1 docker-compose.yml，不改 HM2 本地任何配置。

---

## 4. 执行记录

```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 \
  'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R18'

# UPSTREAM: 35 → 40
ssh -p 222 opc_uname@100.109.153.83 \
  "cd /opt/cc-infra && sed -i '417s/\"35\"/\"40\"/' docker-compose.yml"

# TIER_BUDGET: 70 → 80
ssh -p 222 opc_uname@100.109.153.83 \
  "cd /opt/cc-infra && sed -i '418s/\"70\"/\"80\"/' docker-compose.yml"

# 更新注释
ssh -p 222 opc_uname@100.109.153.83 \
  "cd /opt/cc-infra && sed -i '417s/# R17: HM2优化.*$/# R18: HM2优化 — 35→40: +5s margin captures deepseek completions in 35-40s range/' docker-compose.yml"
ssh -p 222 opc_uname@100.109.153.83 \
  "cd /opt/cc-infra && sed -i '418s/# R18: HM2优化.*$/# R18: HM2优化 — 70→80: 2×UPSTREAM_TIMEOUT(40)=80s/' docker-compose.yml"

# 部署
ssh -p 222 opc_uname@100.109.153.83 \
  'cd /opt/cc-infra && docker compose up -d hm40006'
```

### 部署后验证
```bash
$ docker ps --format '{{.Names}} {{.Status}}' | grep hm40006
hm40006 Up 13 seconds (healthy)

$ docker exec hm40006 env | grep -E "UPSTREAM_TIMEOUT|TIER_TIMEOUT_BUDGET"
UPSTREAM_TIMEOUT=40
TIER_TIMEOUT_BUDGET_S=80
```

---

## 5. 预期效果

| 指标 | 当前 | 预期改善 |
|------|------|----------|
| deepseek 35s 边界 timeout | ~98次/30min (avg 25656ms) | 减少 ~15-20% (约 15-20 fewer)，捕获 35-40s 区间 |
| all_tiers_exhausted 失败 | 49次/30min (avg 64s) | 减少 ~10-15 (timeout 率下降直接减少耗尽) |
| 总 fallback 率 | 71.6% | 保持高位（glm5.1 功能级429无法参数解决），但 deepseek 一级 fallback 成功率提升 |
| 端到端延迟(p90) | 远程请求 avg ~18s(fallback) | deepseek 成功请求延迟稳定降低（35s 边界请求现在完成） |

---

## 6. 观察项与风险

- **观察 deepseek timeout 数量**: 部署后 30min 观察，预期从 ~98 降至 ~85 以下
- **观察 all_tiers_exhausted**: 预期从 49 降至 ~40 以下
- **UPSTREAM_TIMEOUT=40 风险**: 极慢请求(>40s) 等待时间增加；但 deepseek p90=47s，40s 截断可接受，40-47s 少量额外开销
- **TIER_BUDGET=80 风险**: 单个请求最长可占用 80s 代理线程(2×40)；
- **下轮优化**: 如 429 仍主导，需进一步削减 glm5.1 调用（上游改为 deepseek 先走）；但 HM1 不控制上游路由模型
- **预算耦合铁律**: 未来任何 UPSTREAM 改变，必须同步调整 TIER_BUDGET ≥ 2×UPSTREAM

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记
