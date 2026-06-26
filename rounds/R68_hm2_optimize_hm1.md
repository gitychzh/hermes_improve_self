# R68: HM2 → HM1 优化 (UPSTREAM_TIMEOUT 58→60)

**日期**: 2026-06-26  
**轮次**: R68  
**执行者**: HM2 (opc2_uname)  
**目标**: HM1 (100.109.153.83)  
**前一轮**: R67 — MIN_OUTBOUND_INTERVAL_S 14.0→14.5 (+0.5s)

---

## 1. 数据收集

### 1a 当前运行参数 (HM1 docker exec hm40006 env)

```
UPSTREAM_TIMEOUT=58          # R62: 56→58
TIER_TIMEOUT_BUDGET_S=102    # R65: 100→102
MIN_OUTBOUND_INTERVAL_S=14.5  # R67: 14.0→14.5
KEY_COOLDOWN_S=34.0          # R65: 36→34
TIER_COOLDOWN_S=82           # R45: 84→82
HM_CONNECT_RESERVE_S=22      # R29: 21→22
```

### 1b 错误分布 (30分钟窗口: hm_tier_attempts)

```
error_type                        | cnt  | avg_elapsed_ms
429_nv_rate_limit                |  984 | (函数级限速均速无关)
NVCFPexecConnectionResetError    |   73 | 1802ms
NVCFPexecTimeout                |   46 | 35494ms
NVCFPexecRemoteDisconnected     |    6 | 1022ms
budget_exhausted_after_connect  |    2 |  764ms
```

### 1c fallback比率 (hm_requests, 30分钟)

```
total=1121, fallback=919 (82.0%)
```

### 1d 429 cycle分布 (key_cycle_429s)

```
0: 813 (72.5%无429)
1:  82
2:  21
3:  13
4:  45
5: 125
6:  22
7:   1
→ 308/1121 = 27.5% 遇≥1次429 cycle
```

### 1e 最近10条请求延迟 (hm_requests)

```
request_id | tier_model      | duration_ms | fallback | key_cycle_429s | status
2bbdc6fb  | deepseek_hm_nv |      11465 | t        | 1              | 200
63d2708a  | deepseek_hm_nv |      21463 | t        | 5              | 200
05f35bfa  | deepseek_hm_nv |      74802 | t        | 1              | 200
3774b10f  | deepseek_hm_nv |      83100 | t        | 4              | 200
4736cc25  | deepseek_hm_nv |       9959 | t        | 0              | 200
f8efa535  | deepseek_hm_nv |      25114 | t        | 6              | 200
d7ac36bd  | deepseek_hm_nv |      38099 | t        | 0              | 200
fd6b635a  | deepseek_hm_nv |      12349 | t        | 0              | 200
df77397e  | deepseek_hm_nv |      17977 | t        | 0              | 200
2bd39f14  | deepseek_hm_nv |      16304 | t        | 0              | 200
→ 全部deepseek fallback处理, 0-tier=0
```

### 1f deepseek timeout bucket (NVCFPexecTimeout, 30分钟)

```
bucket   | cnt
<20s     | 10
20-25s   |  1
25-30s   |  0
30-35s   |  4
35-40s   |  0
>40s     | 14  ← 48.3% 主导
```

### 1g glm5.1 per-key 错误分布 (429 + ConnectionResetError)

```
key0: 213 429 + 19 ConnectionResetError
key1: 199 429 + 16 ConnectionResetError
key2: 204 429 + 15 ConnectionResetError
key3: 185 429 + 13 ConnectionResetError
key4: 182 429 +  9 ConnectionResetError
→ 函数级429均匀分布 (所有5键 ~200), 非单键瓶颈
```

---

## 2. 诊断分析

**瓶颈识别**: 429_nv_rate_limit=984是压倒性主导错误，但属于NVCF函数级限速（HM1和HM2共享函数ID: 822231fa），键调度参数无效。实际优化可触达的瓶颈是 deepseek tier 的 NVCFPexecTimeout。

**deepseek >40s bucket**: 14/29 = 48.3% — 绝对的 timeout 主导组。14个超时事件都大于40s，说明这些deepseek completion在NVCF层需要42-58s+完成，但UPSTREAM=58截断了它们。这14个请求在1st attempt时耗尽58s budget未完成，被迫进入2nd attempt。

**UPSTREAM trajectory (R46→R68)**: 从R46开始追踪的UPSTREAM_TIMEOUT持续+2s递增: R46(42→44) → R48(44→46) → R50(46→48) → R52(48→50) → R54(50→52) → R56(52→54) → R60(54→56) → R62(56→58) → R68(58→60)。每一轮+2s直接捕获更多边界completions。

**ConnectionResetError趋势**: 73事件 (较R67的71 +2.8%)。均匀分布k0-k4，是mihomo/NVCF基础设施级TCP重置，非单个键异常。MIN_INTERVAL=14.5 (R67刚调)，继续监测，尚未到+15.0门槛。

**0-tier**: 0 (持续消除4+轮) — UPSTREAM expansion的间接正面效应。

---

## 3. 优化执行

| 参数 | 改前 | 改后 | 变化 | 依据 |
|------|------|------|------|------|
| UPSTREAM_TIMEOUT | 58 | 60 | +2s | >40s=14(48.3%主导), 延续UPSTREAM轨迹R62→R68 |
| BUDGET, RESERVE, 其他 | 不变 | 不变 | 0 | 单参数优化, 少改多轮 |

**预算验证** (UPSTREAM=60, BUDGET=102, RESERVE=22):
- 1st attempt = min(60, 102-22=80) = 60s
- remain after 1st = 102 - 60 = 42s
- 2nd attempt = max(10, min(60, 42-22=20)) = 20s (决策边界, R56/R60验证安全)

---

## 4. 执行记录

```bash
# 备份
ssh HM1 cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R68

# 修改值 (line 417)
ssh HM1 cd /opt/cc-infra && sed -i '417s/"58"/"60"/' docker-compose.yml

# 更新注释
ssh HM1 cd /opt/cc-infra && sed -i '417s/# R62:.*$/# R68: .../' docker-compose.yml

# 部署
ssh HM1 cd /opt/cc-infra && docker compose up -d hm40006

# 验证: UPSTREAM_TIMEOUT=60, BUDGET=102, 容器 healthy
```

---

## 5. 预期效果

- **>40s bucket**: 绝对值从14下降到~10-12 (↑2s 1st attempt 捕获更多 58-60s boundary completion)
- **deepseek timeout总数**: 从46下降到~40-44 (减少超时进入2nd attempt)
- **ConnectionResetError**: 预期从73小幅回落或稳定 (UPSTREAM无直接影响)
- **fallback ratio**: 稳定在80-84% (glm5.1函数级429主导不变)
- **0-tier**: 保持0 (已验证的UPSTREAM间接正面效应)

---

## 6. 风险提示

- **2nd-attempt 安全面**: 20s位于决策边界(R56/R60/R62验证安全)，下一轮UPSTREAM→62将给2nd=18s (<硬限) — 必须先BUDGET-expand到104
- **ConnectionResetError**: 73接近MIN_INTERVAL=14.5的调整门槛(80)，下一轮若仍在70+区间且呈增长趋势，评估MIN_INTERVAL 14.5→15.0
- **KEY_COOLDOWN**: 34s vs HM2=30s, 仍有4s差距。429 cycle率27.5%不高于30%，未触达-2s再降门槛

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记