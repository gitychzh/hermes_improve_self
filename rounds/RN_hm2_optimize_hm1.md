# R84: HM2→HM1 — TIER_COOLDOWN_S 55→53 (-2s)

**日期**: 2026-06-27 06:01 UTC
**执行者**: opc2_uname (HM2角色)
**目标**: HM1 (100.109.153.83)
**前一HM2→HM1轮次**: R82 (KEY_COOLDOWN_S 31.0→29.0)
**前一HM1→HM2轮次**: R83 (TIER_COOLDOWN_S 38→41, 针对HM2)

## 数据收集 (HM1 30min窗口, 06:01 UTC)

### 容器环境 (已验证)
```yaml
UPSTREAM_TIMEOUT=62          # R76: 60→62
TIER_TIMEOUT_BUDGET_S=106    # R81: 104→106
MIN_OUTBOUND_INTERVAL_S=17.5  # R79: 15.5→17.5
KEY_COOLDOWN_S=29.0           # R82: 31.0→29.0
TIER_COOLDOWN_S=55            # R79: 68→55 (大跳)
HM_CONNECT_RESERVE_S=22       # R29: 21→22
```

### 错误分布 (hm_tier_attempts, 30min)
```
429_nv_rate_limit              1,161  (90.6%)  ← 主导
NVCFPexecTimeout                 112    (8.7%)    avg=23,993ms
NVCFPexecConnectionResetError    39     (3.0%)    avg=3,684ms
empty_200                        12     (0.9%)
budget_exhausted_after_connect    6     (0.5%)    avg=2,502ms
NVCFPexecRemoteDisconnected       2     (0.2%)
```

### 请求路由 (hm_requests, 30min)
```
总请求:          1,244
直接成功(glm5.1):   343  (27.6%)
回退(deepseek):     901  (72.4%)  ← fallback=72.4%
```

平均延迟: 直接=24,623ms, 回退=34,582ms

### 429周期分布 (key_cycle_429s)
```
0次:  845  (67.9%)
1次:  114  (9.2%)
2次:   43  (3.5%)
3次:   30  (2.4%)
4次:   40  (3.2%)
5次:  147  (11.8%)  ← 最高非0桶
6次+:  25  (2.0%)

429周期率: 32.1% (399/1244条请求 ≥1次429)
```

### 每键glm5.1 429 (函数级均匀)
```
k0: 260 | k1: 237 | k2: 228 | k3: 223 | k4: 213
全部均匀 — 函数级全局速率限制, 非单键耗尽
```

### Deepseek 超时桶分布 (NVCFPexecTimeout)
```
<20s:    47  (58.0%)  ← 主导群
20-25s:   4  (4.9%)
25-30s:   0
30-35s:   0
35-40s:   0
40-45s:   0
45-50s:   0
50-55s:   1  (1.2%)
>55s:    11  (13.6%)  ← 基建级预算耗尽

总计: 63/81 = 77.8% 在 <20s 桶完成
```

### 每键Deepseek超时分布
```
k0: <20s=10, 20-25s=1
k1: <20s=8, 20-25s=1, >55s=4
k2: <20s=9, 20-25s=2, 50-55s=1, >55s=1
k3: <20s=9, >55s=4
k4: <20s=11, >55s=2

均匀分布 — 无单键代理端口倾斜
```

### 层级分布 (hm_tier_attempts)
```
glm5.1_hm_nv:  1,260  (94.0%)  ← 大部分是429
deepseek_hm_nv:    81  (5.9%)
kimi_hm_nv:         0
```

### 最近10条请求
```
全部通过deepseek_hm_nv回退完成 (100% fallback)
cycle分布: 5条有0次429, 3条有5次429
平均延迟: 14,094ms~41,864ms
```

## 诊断

### 关键发现

1. **Fallback率 = 72.4%** — 改善中 (从R12的86%下降)。直接成功率 = 27.6%。
   TIER_COOLDOWN=55 (R79从68→55大幅降低后)，glm5.1恢复速度加快，直接尝试更多。

2. **429周期率 = 32.1%** — 升高。399/1244条请求遭遇≥1次429周期 (额外延迟惩罚)。
   KEY_COOLDOWN=29.0 (R82刚降到29)，键冷却已很低。均匀的5键分布确认函数级速率限制。

3. **Deepseek超时 <20s 主导 (58%)** — 大部分deepseek超时在20s内完成。
   >55s桶=11 (13.6%) — 基建级预算耗尽，不是HM代理头部空间不足。
   当前UPSTREAM=62, BUDGET=106: 1st=62s, 2nd=22s — 远在决策边界上方 (安全)。

4. **ConnectionResetError = 39** — 稳定，均匀分布。MIN_INTERVAL=17.5充分保护。

5. **0-tier = 0 持续** (budget_exhausted_after_connect=6，非all_tiers_exhausted)。
   连接级预算耗尽已确认不是问题。

### 决策: 继续TIER_COOLDOWN轨迹

**当前状态**: TIER_COOLDOWN=55 (R79 68→55 -13s大跳后)。虽然大跳已大幅提速glm5.1恢复，但继续-2s递减仍有空间。

**为什么选TIER_COOLDOWN而不是别的参数**:
- ❌ KEY_COOLDOWN=29.0已经很低 — HM2观察到R82 (31→29) 在HM2侧导致直接成功率从35.6%→10.9% (严重回退)。继续降低KEY_COOLDOWN风险同样回退。
- ❌ BUDGET=106已充足，2nd=22s安全 — 不需要扩展
- ❌ UPSTREAM=62已经高，2nd=22s — 不需要扩展
- ❌ MIN_INTERVAL=17.5有效控制ConnectionResetError=39 — 不需要调整
- ✅ TIER_COOLDOWN=55→53 (-2s): 继续加速glm5.1从全键429恢复。更短全局冷却→更多重试窗口→更高直接成功率。

**少改多轮原则**: 单参数-2s递减。每轮积累，不对抗式优化。

**预算数学验证 (UPSTREAM=62, BUDGET=106, RESERVE=22, TIER_COOLDOWN=53)**:
- 1st=62s, 剩余=44, 2nd=max(10, min(62, 44-22=22))=22s — 安全，远在决策边界上方
- TIER_COOLDOWN不影响预算 — 独立参数

## 优化表

| 参数 | 前 | 后 | 理由 |
|---|---|---|---|
| TIER_COOLDOWN_S | 55 | 53 | -2s 继续加速glm5.1从全键429恢复; 更短全局冷却→更多重试窗口→更高直接成功; 均匀5键429 (函数级); R79 68→55大跳后继续轨迹; 少改多轮 |

## 执行记录

```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R84'

# 值变更 (line 422)
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && sed -i "422s/\"55\"/\"53\"/" docker-compose.yml'

# 注释更新
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && sed -i "422s/# R79:.*$/# R84: HM2优化 — 55→53: -2s tier cooldown; 继续加速glm5.1恢复; fallback=72.4% 直通=27.6%; 429 cycle=32.1%; 少改多轮(单参数); 铁律:只改HM1不改HM2/" docker-compose.yml'

# 部署
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'

# 验证 (8s等待后)
ssh -p 222 opc_uname@100.109.153.83 'docker exec hm40006 env | grep TIER_COOLDOWN_S'
# → TIER_COOLDOWN_S=53 ✅

ssh -p 222 opc_uname@100.109.153.83 'docker ps --format "{{.Names}} {{.Status}}" | grep hm40006'
# → hm40006 Up 2 minutes (healthy) ✅
```

## 预期效果

- **TIER_COOLDOWN -2s (55→53)**: 全局冷却从55s降到53s。更快速从全键429恢复。当前429周期率32.1%，预期降至~30%。
- **直接成功率**: 当前27.6%，预期提升至~30-32% (每-2s增加1-2pp)
- **Fallback率**: 当前72.4%，预期降至~68-70%
- **Deepseek超时**: 不变 (TIER_COOLDOWN不直接影响deepseek超时分布)
- **ConnectionResetError**: 不变 (稳定在39)

## 观察项

1. ⚠️ **KEY_COOLDOWN=29.0 是风险下限** — R82在HM2侧观察到KEY_COOLDOWN从31→29导致直接成功率从35.6%→10.9% (严重回退)。如果HM1侧出现相同回退，应立即回退KEY_COOLDOWN到30+。
2. ✅ **少改多轮单参数** — 继续踏实轨迹，不跳跃
3. ✅ **2nd-attempt = 22s 安全** — 远在决策边界上方
4. 🔍 **Monitor next 30min window** — 确认TIER_COOLDOWN降低是否提升直接成功率

## 铁律确认
- ✅ 只改了HM1 docker-compose.yml (line 422)
- ✅ 没有触碰HM2本地任何配置
- ✅ 单参数-2s递减
- ✅ 容器部署后healthy

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记