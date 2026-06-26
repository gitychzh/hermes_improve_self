# R88: HM2→HM1 — TIER_COOLDOWN_S 49→47 (-2s)

**日期**: 2026-06-27 07:21 UTC  
**执行者**: opc2_uname (HM2角色)  
**目标**: HM1 (100.109.153.83, port 222)  
**前轮**: R87 (HM2→HM1: TIER_COOLDOWN_S 51→49, 铁律:只改HM1不改HM2)  
**触发**: HM1提交R87→HM2 (commit 6d40b6d, MIN_OUTBOUND_INTERVAL_S 19→21, 轮次标记 `轮到HM2优化HM1`)

---

## 数据采集 (HM1, 30-min窗口 07:18 UTC)

### 1. 容器环境变量
```
UPSTREAM_TIMEOUT=62          # R76: 60→62
TIER_TIMEOUT_BUDGET_S=106    # R81: 104→106
MIN_OUTBOUND_INTERVAL_S=17.5  # R79: 15.5→17.5
KEY_COOLDOWN_S=29.0           # R82: 31→29
TIER_COOLDOWN_S=49            # R87: 51→49
HM_CONNECT_RESERVE_S=22       # R29: 21→22
```

### 2. 数据库分析 (30-min)

**错误分布 (hm_tier_attempts)**:
```
429_nv_rate_limit              | 1,366 | (89.5% of all errors)
NVCFPexecTimeout              |   104 | avg=22,018ms
NVCFPexecConnectionResetError |    26 | avg=4,658ms
empty_200                     |    16 | 
budget_exhausted_after_connect|     6 | avg=1,897ms
NVCFPexecRemoteDisconnected   |     1 | avg=8,034ms
```

**请求分布 (hm_requests)**:
```
Total: 1,257 requests
Direct (glm5.1):    248 (19.7%) avg=27,170ms
Fallback:         1,005 (80.1%) avg=33,516ms
Fallback rate: 80.1%
Avg latency: 32,264ms overall
```

**429周期率**:
```
Has 429 cycle:   422/1,257 = 33.6%
Avg cycles per affected request: 3.6
Key breakdown (0-cycle): 833 (no 429), 1-cycle: 98, 5-cycle: 188
```

**Tier分布**:
```
glm5.1_hm_nv:   1,431 attempts (97% of tier attempts)
deepseek_hm_nv:     88 attempts (3%)
```

**ConnectionResetError 按key分布**:
```
k0: 4,  k1: 4,  k2: 8,  k3: 7,  k4: 3 (共26, 均匀分布)
```

**Deepseek超时桶分布**:
```
<20s: 51 (77.3%)  ← 主导, fallback健康
20-25s: 4
50-55s: 1
>55s: 10 (15.1%)  ← 基建级超时, 非HM headroom不足
总超时: 66 events
```

**Deepseek超时按key分布**:
```
k0: <20s=10, 20-25s=1, >55s=1
k1: <20s=10, 20-25s=1, >55s=4
k2: <20s=11, 20-25s=2, 50-55s=1
k3: <20s=9, >55s=4
k4: <20s=11, >55s=1
均匀分布, 无单key倾斜
```

### 3. 日志模式 (最近200行)
```
- glm5.1全部5键均匀429 (函数级rate-limit)
- TIER-FAIL后GLOBAL-COOLDOWN=49s (TIER_COOLDOWN标记全部冷却)
- 49s后解冻即再全429 (5键thundering-herd)
- deepseek fallback稳定成功 (89%在<20s内完成)
- 无all_tiers_exhausted (0-tier=0维持)
- kimi tier: 0次尝试 (未被使用)
```

---

## 诊断

### 根因分析

**瓶颈**: glm5.1 primary tier 100% 429 rate-limited (函数级, 所有5键同时触发)

**证据链**:
1. `glm5.1_hm_nv` tier 1,431次尝试中, 1,366次是429 — 95.5%的尝试都失败在429
2. 所有5键均匀分布 (k0:291, k1:277, k2:270, k3:268, k4:260) — 函数级rate-limit, 非单key耗尽
3. 每次TIER-FAIL后GLOBAL-COOLDOWN=49s, 49s后解冻立即再全429 (thundering-herd pattern)
4. Deepseek <20s桶=77.3% — fallback tier工作良好, 不需要更多headroom
5. 429周期率=33.6% (422/1257请求遭遇≥1个429 cycle), 每个受影响请求平均3.6个额外cycle

**优化向量选择**:

| 参数 | 当前值 | 方向 | 可行性 |
|---|---|---|---|
| KEY_COOLDOWN | 29s | 不能降 | R85/R86交叉回归: 29s时direct collapse到10.9%, 29s是危险下界 |
| UPSTREAM_TIMEOUT | 62s | 暂不升 | 2nd-attempt=20s在决策边界, 先降cooldown再评估 |
| BUDGET | 106s | 暂不扩 | 2nd=22s充足, 不是当前瓶颈 |
| MIN_INTERVAL | 17.5s | 暂不动 | ConnectionResetError=26 (1.8%) 稳定 |
| TIER_COOLDOWN | 49s | **降-2s→47** | ✅ 最大杠杆: 每个-2s加速glm5.1恢复2s, 减少dead-time |

**决策**: 继续TIER_COOLDOWN轨迹 (49→47, -2s)

每-2s TIER_COOLDOWN:
- 加速glm5.1恢复2s  
- 增加重试窗口频率
- 减少GLOBAL-COOLDOWN dead-time
- 直接降低fallback率 (更多重试→更多成功机会)

Deepseek <20s桶主导 (77.3%) — fallback tier是健康的, 优化重心在加速primary tier恢复, 不是增强fallback headroom。

---

## 优化执行

| 参数 | 变更前 | 变更后 | 增量 | 理由 |
|---|---|---|---|---|
| TIER_COOLDOWN_S | 49s | 47s | -2s | 继续加速glm5.1恢复; 每个-2s减少tier cooling dead-time; 少改多轮 |

**铁律**: 只改HM1配置, 绝不改HM2本地

### 执行命令
```bash
# 备份
ssh opc_uname@100.109.153.83 -p 222 \
  "cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R88"

# 修改 (line 422)
ssh opc_uname@100.109.153.83 -p 222 \
  'cd /opt/cc-infra && sed -i "422s/\"49\"/\"47\"/" docker-compose.yml && \
   sed -i "422s/# R87:.*$/# R88: HM2优化 — 49→47: -2s tier cooldown; .../" docker-compose.yml'

# 部署
ssh opc_uname@100.109.153.83 -p 222 \
  'cd /opt/cc-infra && docker compose up -d hm40006'

# 验证
sleep 10 && docker exec hm40006 env | grep TIER_COOLDOWN_S
# → TIER_COOLDOWN_S=47 ✅
```

### 验证结果
- 容器健康检查: Up 30 seconds (healthy) ✅
- env确认: `TIER_COOLDOWN_S=47` ✅
- 其他参数未变: UPSTREAM=62, BUDGET=106, KEY=29, MIN=17.5, RESERVE=22 ✅
- HM2本地未动任何配置 ✅

---

## 预期效果

| 指标 | 当前 | 预期 | 理由 |
|---|---|---|---|
| fallback率 | 80.1% | 76-78% | +2s glm5.1恢复→更多直接尝试 |
| glm5.1直通率 | 19.7% | 21-23% | 更快tier recovery→更多retry窗口 |
| 429周期率 | 33.6% | 30-32% | 减少dead-time→减少cycle overhead |
| Deepseek <20s桶 | 77.3% | 78-80% | 保持不变 (fallback tier健康) |
| ConnectionResetError | 26 | ~25-30 | 略增 (更多重试→更多连接reset) |
| 0-tier | 0 | 0 | 维持 (UPSTREAM=62已保护) |

---

## 观察项

1. **ConnectionResetError监控**: 当前26 (1.8%), 更多glm5.1重试可能轻微增加, 但不会突破35。若突破35且连续2轮增长, 下一轮评估MIN_INTERVAL。

2. **KEY_COOLDOWN=29是危险下界**: HM1→HM2的R85/R86交叉回归数据证实29→26导致direct success从35.6%崩溃到10.9%。绝不能降低KEY_COOLDOWN低于29。

3. **TIER_COOLDOWN继续轨迹**: 目标~40-45s, 当direct success>35%时停止。当前在47s还有2-4轮headroom。

4. **kimi tier未使用**: 0次尝试, 当前配置下kimi不在fallback链中 (只有deepseek)。

5. **少改多轮**: 单参数(-2s)符合原则, 每轮积累微调。

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记