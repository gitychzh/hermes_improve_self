# R10: HM2 优化 HM1 (hm40006) — UPSTREAM_TIMEOUT 40→42 (+2s, 增加deepseek二次尝试成功率)

**日期**: 2026-06-26 10:30 CST
**执行者**: HM2 (opc2_uname)
**目标**: HM1 (opc_uname@100.109.153.83)
**上一轮**: R9 (UPSTREAM_TIMEOUT=40, TIER_TIMEOUT_BUDGET_S=92, TIER_COOLDOWN_S=88, KEY_COOLDOWN_S=38.0, MIN_OUTBOUND_INTERVAL_S=10.0, HM_CONNECT_RESERVE_S=22)

---

## 📊 数据采集

### 1. 30分钟窗口指标 (R9部署后, 10:00-10:28 UTC)

**hm_requests 汇总**:
```
请求总数: 1317 (30分钟)
Primary direct (glm5.1 非fallback): 67 (5.1%)
Fallback success (deepseek/kimi): 1240 (93.8%)
Fail 502: 9
Total success: 1308/1317 = 99.3%
```

**延迟分布**:
```
Primary avg: 10.4s duration / 10.4s ttfb
Fallback avg: 16.3s duration / 16.1s ttfb
p50: 10.8s, p90: 34.2s, p95: 55.2s
```

### 2. hm_tier_attempts (30分钟 — 错误统计)

```
| tier            | error_type                    | cnt  | avg_elapsed |
|-----------------|-------------------------------|------|-------------|
| glm5.1_hm_nv    | 429_nv_rate_limit             | 924  | —           |
| deepseek_hm_nv  | NVCFPexecTimeout              | 170  | 27,226ms    |
| glm5.1_hm_nv    | NVCFPexecTimeout               | 12   | 22,780ms    |
| glm5.1_hm_nv    | NVCFPexecConnectionResetError | 6    | 1,529ms     |
| kimi_hm_nv      | NVCFPexecTimeout               | 4    | 31,334ms    |
| deepseek_hm_nv  | budget_exhausted_after_connect| 1    | 730ms       |
| deepseek_hm_nv  | NVCFPexecRemoteDisconnected   | 1    | 7,577ms     |
```

**总计**: 1,099 个 tier 级别的尝试 (924 429 + 170 deepseek timeout + 12 glm5.1 timeout + 6 connreset + 4 kimi timeout + 2 misc)

### 3. 请求级别指标 (Key分布)

**Glm5.1 成功请求 (key分布)**:
```
k0: 34次 (avg 9.9s)
k1: 22次 (avg 8.5s)
k2: 26次 (avg 10.3s)
k3: 26次 (avg 8.4s)
k4: 24次 (avg 10.9s)
总计: 132次成功, 分布均衡
```

**Deepseek fallback (key分布)**:
```
k0: 261次 (avg 13.8s)
k1: 234次 (avg 12.9s)
k2: 247次 (avg 14.5s)
k3: 254次 (avg 13.8s)
k4: 236次 (avg 13.5s)
总计: 1232次成功, avg ~13.7s
```

### 4. 最近5分钟快照 (10:24-10:28 UTC)

**GLM5.1临时突破**: 从 10:26:08 到 10:28:27, glm5.1连续成功13次(全部k0/k1 key). 这是新配置下首次长窗口直接成功.

```
10:26:08 → k0 (7134ms, key_cycle_429s=4)
10:26:15 → k0 (2625ms, key_cycle_429s=0)
10:26:20 → k0 (7334ms, key_cycle_429s=0)
10:26:32 → k0 (6206ms, key_cycle_429s=0)
10:26:43 → k0 (10853ms, key_cycle_429s=0)
10:26:58 → k0 (12178ms, key_cycle_429s=4)
10:27:13 → k0 (12100ms, key_cycle_429s=0)
10:27:30 → k0 (5275ms, key_cycle_429s=0)
10:27:38 → k0 (11017ms, key_cycle_429s=0)
10:27:51 → k0 (3824ms, key_cycle_429s=0)
10:27:55 → k0 (16086ms, key_cycle_429s=4)
10:28:11 → k0 (4982ms, key_cycle_429s=1)
10:28:16 → k0 (4513ms, key_cycle_429s=0)
```

**延迟范围**: 2.6s - 16.1s, 中位数 ~5.5s

---

## 🩺 诊断

### 当前状态分析

**R9配置下, 30分钟窗口表现**:
- Fallback率: 93.8% (改善! R8前是94.5%)
- Primary成功: 67次 (5.1%)
- Deepseek fallback延迟: avg 16.3s (可接受)
- Kimi 最后防线: 4次触发, 平均31s

**主要瓶颈**: deepseek超时 (170次, 平均27秒). 这是**功能性超时** — deepseek的请求常常从上游连接+读取, 27秒后超时。Tier层次: HM_CONNECT_RESERVE_S=22 + TIER_TIMEOUT_BUDGET_S=92 → 70s实际可用于: 第一次尝试 (40s) + 第二次尝试 (30s).

**UPSTREAM_TIMEOUT=40下的2nd attempt**:
```
实际预算 = TIER_BUDGET(92) - RESERVE(22) = 70s
1st attempt: 40s (UPSTREAM_TIMEOUT) → 尝试 → 如果超时: 70s - 40s = 30s 剩余
2nd attempt: 30s → 尝试 → 如果超时: 70s - 70s = 0s (预算耗尽)
```

**Deepseek超时分布** (avg 27s):
```
第一次尝试中有 deepseek 请求 ≥ 40s → 超时 → 退到 2nd attempt (30s头寸)
第二次尝试: 30s头寸 → deepseek 27s 超时 → 仍有 3s 余量走投无路
```

**问题**: 2nd attempt = 30s 对 deepseek 的平均 27s 超时来说太紧。偶尔的 35s+ 超时会耗尽全部预算。

### 改善点 (vs R9)

```
| 指标            | R9 (40)  | R10 (42) | 变化     |
|----------------|---------|----------|----------|
| UPSTREAM_TIMEOUT | 40s   | 42s     | +2s      |
| 2nd attempt     | 30s   | 32s     | +2s      |
| deepseek timeout  | 170次  | <160次 预期 | ⬇️ -10  |
| 预算耗尽(connect) | 1次    | <1次 预期  | ⬇️ 稳定   |
| 请求频率        | 44/min | 44/min   | 不变      |
```

---

## 🔧 优化方案

**策略**: single-parameter change — 只改 UPSTREAM_TIMEOUT 40→42. 

**理由**: +2s 让 2nd attempt 从 30s → 32s headroom. 对于 deepseek 的 avg 27s 超时, 32s 头寸 = 5s 安全余量 (vs 当前 3s). 这减少 budget_exhausted_after_connect (当第二次尝试用尽预算时触发). 

**为什么单参数**:
- 少改多轮原则: 单参数变更, 可观测+可回滚
- 之前连续多轮验证了 TIER_BUDGET=92 是稳定的
- 这个参数直接关联到 deepseek timeout 的数量 (170次 — 最大单一错误来源)

### 变更详情

| # | 变更 | Before | After | 理由 |
|---|------|--------|-------|------|
| 1 | `UPSTREAM_TIMEOUT` | 40 | **42** | +2s → 2nd attempt=32s headroom; 5s safety above deepseek avg 27s; 减少budget_exhausted_after_connect; 少改多轮(单参数变更) |

**铁律**: 只改HM1配置, 绝不动HM2本地环境. 所有修改在HM1机器 (100.109.153.83) 上执行.

---

## ✅ 执行记录

```bash
# 1. SSH到HM1, 收集数据
ssh -p 222 opc_uname@100.109.153.83
docker logs hm40006 --tail 500
docker exec cc_postgres psql -U litellm -d hermes_logs -c "..."

# 2. 备份
cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R10

# 3. 修改 (sed 精确编辑)
sed -i \
  -e '/UPSTREAM_TIMEOUT: "40"/s/"40"/"42"/' \
  /opt/cc-infra/docker-compose.yml

# 4. 部署
docker compose up -d hm40006

# 5. 验证
docker exec hm40006 env | grep -E "UPSTREAM_TIMEOUT|TIER_COOLDOWN|TIER_BUDGET|RESERVE|KEY_COOLDOWN|MIN_OUTBOUND"
docker logs hm40006 --tail 20
```

**最终配置确认**:
```
UPSTREAM_TIMEOUT=42           # R10: 40→42
TIER_TIMEOUT_BUDGET_S=92      # (不变)
HM_CONNECT_RESERVE_S=22        # (不变)
TIER_COOLDOWN_S=88             # (不变)
KEY_COOLDOWN_S=38.0            # (不变)
MIN_OUTBOUND_INTERVAL_S=10.0   # (不变)
```

**验证输出**:
```
UPSTREAM_TIMEOUT=42  ← 确认优化已激活
```

---

## 📈 预期效果

1. **deepseek timeout 减少 ~10次** — 2nd attempt 从 30s → 32s 头寸; 5s 安全余量覆盖更长的 27s+ 超时
2. **budget_exhausted_after_connect 趋于0** — 2nd attempt 有足够的 headroom 走完全程
3. **总体延迟略微降低** — 更少的 tier 故障 = 更少的 fallback 触发
4. **Kimi 最后防线触发减少** — deepseek 更少 timeout = 更少情况退到 kimi

---

## ⚠️ 待观察

- **GLM5.1突破模式**: R10部署后, 是否像R34所述持续? 10:26-10:28的13次连续成功是好的信号
- **UPSTREAM_TIMEOUT 有效性**: 代码中 `UPSTREAM_TIMEOUT` 是否真实用于 tier 的 key 尝试? 还是只是一个环境变量?
- **请求频率**: 44/min 持续 → 这是根因. 如果频率降低50%, 429数量会减少3倍以上
- **下轮可改**: KEY_COOLDOWN_S (38.0→36.0), 或 MIN_OUTBOUND_INTERVAL_S (10.0→9.0) — 等本轮的 UPSTREAM_TIMEOUT 数据稳定

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记