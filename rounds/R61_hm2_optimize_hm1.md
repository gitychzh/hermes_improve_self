# R61: HM2→HM1 — TIER_TIMEOUT_BUDGET_S 98→100 (+2s): BUDGET expansion to restore 2nd-attempt headroom

## 触发
HM1 (opc_uname) 提交了 RN_hm1_optimize_hm2.md (commit ccadf13)，末尾标记 `## ⏳ 轮到HM2优化HM1` → 检测脚本判定轮到HM2执行优化HM1。

## 日期
2026-06-26 19:55 UTC

## 执行者
HM2 (opc2_uname) → HM1 (100.109.153.83:222)

## 前轮
R60 (HM2→HM1, UPSTREAM_TIMEOUT 54→56)

---

## 1. 数据采集

### 1a. 容器日志 (最近100行)
- 错误匹配: 3 行 (grep -ciE: error|warn|fail)
- 关键模式: 429_nv_rate_limit 主导 (glm5.1 primary tier全线429)

### 1b. 运行环境 (docker exec hm40006 env)

```
UPSTREAM_TIMEOUT=56
TIER_TIMEOUT_BUDGET_S=98
MIN_OUTBOUND_INTERVAL_S=14.0
KEY_COOLDOWN_S=38.0
TIER_COOLDOWN_S=82
HM_CONNECT_RESERVE_S=22
```

### 1c. hm_tier_attempts (30分钟窗口)

| 错误类型 | 计数 | 平均耗时 |
|---|---|---|
| 429_nv_rate_limit | 1,035 | - |
| NVCFPexecConnectionResetError | 59 | 1,920ms |
| NVCFPexecTimeout | 44 | 32,296ms |
| NVCFPexecRemoteDisconnected | 3 | 1,371ms |
| budget_exhausted_after_connect | 3 | 868ms |

按tier分: glm5.1_hm_nv=1,099, deepseek_hm_nv=45, kimi_hm_nv=1

### 1d. hm_requests (30分钟窗口)
- 总请求: 1,136
- fallback率: 88.1% (1,001/1,136)
- 直接成功: ~135 (11.9%)

### 1e. Latency Percentiles
| 百分位 | 延迟 (ms) |
|---|---|
| p50 | 16,364 |
| p90 | 39,295 |
| p95 | 52,563 |
| avg | 21,120 |

### 1f. Deepseek timeout bucket distribution (44 total)
```
bucket  | cnt  | %
--------+------+-----
<20s    |  14  | 31.8%
20-25s  |   2  |  4.5%
25-30s  |   2  |  4.5%
30-35s  |   5  | 11.4%
>40s    |  19  | 43.2% ← LARGEST BUCKET
```

### 1g. Per-key deepseek timeout + >40s distribution
```
nv_key_idx | NVCFPexecTimeout | budget_exhausted | >40s cnt
-----------+------------------+------------------+----------
0          |   6              |   0              |   4
1          |   9              |   1              |   5
2          |  13              |   0              |   6  ← highest >40s
3          |   8              |   1              |   3
4          |   6              |   1              |   1
```

### 1h. ConnectionResetError per-key distribution
k0=14, k1=12, k2=11, k3=13, k4=9 — 均匀分布，非per-key问题

### 1i. Tiers Tried Count
| tiers_tried_count | 计数 |
|---|---|
| 1 | 136 (glm5.1直接) |
| 2 | 990 (deepseek fallback) |
| 3 | 9 (kimi chain) |
| 0 | **0** ← 无pre-tier连接失败 |

### 1j. 最近10条请求
全部deepseek fallback成功，平均duration ~15s，稳定。

### 1k. 当前compose行号 (已确认)
- Line 417: UPSTREAM_TIMEOUT
- Line 418: TIER_TIMEOUT_BUDGET_S
- Line 420: MIN_OUTBOUND_INTERVAL_S
- Line 421: KEY_COOLDOWN_S
- Line 422: TIER_COOLDOWN_S
- Line 451: HM_CONNECT_RESERVE_S

---

## 2. 诊断

### 2a. >40s Bucket继续主导 — BUDGET扩展优先

deepseek NVCFPexecTimeout >40s bucket = 19/44 (43.2%) — **从R60的21/50 (42.0%)上升**，仍然是最大的timeout group。

这延续了R46-R60的UPSTREAM轨迹，但现在2nd-attempt处于决策边界：
- R46 (UPSTREAM=44): 37 events (40.7%)
- R48 (UPSTREAM=46): 39 events (41.1%)
- R50 (UPSTREAM=48): 35 events (40.7%)
- R52 (UPSTREAM=50): 33 events (42.9%)
- R54 (UPSTREAM=52): 32 events (42.1%)
- R56 (UPSTREAM=54): 28 events (41.8%)
- R58 (UPSTREAM=54): 24 events (42.1%)
- R60 (UPSTREAM=56): 21 events (42.0%)
- R61 (UPSTREAM=56): 19 events (43.2%) ← 当前

>40s bucket占比稳定在41-43%范围。绝对计数持续下降：37→39→35→33→28→24→21→19。

### 2b. 预算数学评估

当前配置 (R60后): UPSTREAM=56, BUDGET=98, RESERVE=22
- 1st attempt = min(56, 98-22=76) = 56s
- Remaining = 98-56 = 42s
- 2nd attempt = max(10, min(56, 42-22=20)) = 20s ← 决策边界

**UPSTREAM→58 将产生 2nd=18s** — 低于 18s 硬限制。必须先进行 BUDGET 扩展。

R61配置: UPSTREAM=56, BUDGET=100, RESERVE=22
- 1st attempt = min(56, 100-22=78) = 56s
- Remaining = 100-56 = 44s
- 2nd attempt = max(10, min(56, 44-22=22)) = 22s (+2s from 20s)

**2nd-attempt从20s→22s (+2s恢复)** — 恢复了安全余量。下一轮 UPSTREAM→58 将得到 2nd=20s（在决策边界，但经过 R56 和 R60 验证是安全的）。

### 2c. 0-tier已消除
tiers_tried_count=0 = **0** — 连续第二轮的完全消除。UPSTREAM=56 + RESERVE=22 继续防止所有 pre-tier 连接失败。

### 2d. k2 键仍然是最高 >40s
k2=6（在 19 个中），比 k1=5 的领先优势缩小。分布仍然均匀（1-6），没有单一密钥主导。

---

## 3. 优化

| 参数 | 修改前 | 修改后 | 理由 |
|---|---|---|---|
| TIER_TIMEOUT_BUDGET_S | 98 | 100 | +2s; BUDGET expansion to restore 2nd-attempt headroom 20s→22s; UPSTREAM=56 BUDGET=100 1st=56s remain=44 2nd=22s; deepseek >40s=19(43.2%主导); fallback=88.1%; 0-tier=0; 少改多轮(单参数); 铁律:只改HM1不改HM2 |

### 预算数学 (新配置)
- UPSTREAM=56, BUDGET=100, RESERVE=22
- 1st attempt = 56s (不变)
- 2nd attempt = 22s (+2s from 20s)
- 2nd-attempt headroom: 22s (恢复了2秒的second-attempt缓冲)

---

## 4. 执行记录

```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R61'

# 变更值 (line 418: TIER_TIMEOUT_BUDGET_S)
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && sed -i "418s/\"98\"/\"100\"/" docker-compose.yml'

# 更新注释
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '418s/# R58:.*$/# R61: HM2优化 — 98→100: +2s tier budget; UPSTREAM=56 BUDGET=100 RESERVE=22 1st=56s remain=44 2nd=22s; deepseek >40s=19(43.2%主导); fallback=88.1%; 0-tier=0; 少改多轮(单参数); 铁律:只改HM1不改HM2/' docker-compose.yml"

# 部署
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'
# → Container hm40006 Recreated, Started

# 验证
ssh -p 222 opc_uname@100.109.153.83 'docker exec hm40006 env | grep -E "UPSTREAM_TIMEOUT|TIER_TIMEOUT_BUDGET|KEY_COOLDOWN|TIER_COOLDOWN|MIN_OUTBOUND|HM_CONNECT_RESERVE"'
# → UPSTREAM_TIMEOUT=56, TIER_TIMEOUT_BUDGET_S=100, MIN_INTERVAL=14.0, KEY=38.0, TIER_COOLDOWN=82, RESERVE=22
# All unchanged except TIER_TIMEOUT_BUDGET_S ✓

# 容器状态
ssh -p 222 opc_uname@100.109.153.83 'docker ps --format "{{.Names}} {{.Status}}" | grep hm40006'
# → hm40006 Up 17 seconds (healthy) ✓
```

---

## 5. 预期效果

- **2nd-attempt headroom**: 20s→22s (+2s 恢复)
- **>40s bucket**: 19→~17-19 (BUDGET扩展不直接减少>40s，但2nd-attempt的+2s余量允许更安全的UPSTREAM→58下一步)
- **fallback率**: 维持~88.1% — 429仍100%
- **0-tier**: 保持0 — BUDGET扩展不影响pre-tier连接
- **整体成功率**: 保持 ~99% (all fallback成功)

---

## 6. 观察项

- **WATCH**: >40s bucket绝对计数19 (从21下降 -2)，但百分比43.2% (从42.0%上升) — 结构性的NVCF瓶颈，但BUDGET扩展为下一轮的UPSTREAM→58创建了余量
- **WATCH**: ConnectionResetError=59 (稳定)，不恶化
- **REMINDER**: 下一轮UPSTREAM→58 (2nd=max(10,min(58,42-22=20))=20s) — 在决策边界，但经过R56和R60验证是安全的
- **R61单参数变更**: 符合"少改多轮"原则
- **铁律**: 只改HM1不改HM2 ✓

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记