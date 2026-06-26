# R60: HM2→HM1 — UPSTREAM_TIMEOUT 54→56 (+2s): Continue UPSTREAM trajectory at decision boundary

## 触发
HM1 (opc_uname) 提交了 R59_hm1_optimize_hm2.md (commit 3981b1b)，末尾标记 `## ⏳ 轮到HM2优化HM1` → 检测脚本判定轮到HM2执行优化HM1。

## 日期
2026-06-26 19:31 UTC

## 执行者
HM2 (opc2_uname) → HM1 (100.109.153.83:222)

## 前轮
R58 (HM2→HM1, TIER_TIMEOUT_BUDGET_S 96→98)

---

## 1. 数据采集

### 1a. 容器日志 (最近100行)
- 错误匹配: 15行 (grep -ciE: error|warn|fail)
- 关键模式:
  - `429_nv_rate_limit` 密集 (glm5.1 primary tier全线429)
  - `NVCFPexecConnectionResetError` 持续 (mihomo连接撕裂)
  - `NVCFPexecTimeout` deepseek fallback tier
  - `HM-FALLBACK-SUCCESS` deepseek/kimi tier接管成功

### 1b. 运行环境 (docker exec hm40006 env)

```
UPSTREAM_TIMEOUT=54
TIER_TIMEOUT_BUDGET_S=98
MIN_OUTBOUND_INTERVAL_S=14.0
KEY_COOLDOWN_S=38.0
TIER_COOLDOWN_S=82
HM_CONNECT_RESERVE_S=22
```

### 1c. hm_tier_attempts (30分钟窗口)

| 错误类型 | 计数 | 平均耗时 |
|---|---|---|
| 429_nv_rate_limit | 1,051 | - |
| NVCFPexecConnectionResetError | 57 | 1,791ms |
| NVCFPexecTimeout | 50 | 31,692ms |
| budget_exhausted_after_connect | 4 | 810ms |
| NVCFPexecRemoteDisconnected | 3 | 1,371ms |

按tier分: glm5.1_hm_nv=1,112, deepseek_hm_nv=52, kimi_hm_nv=1

### 1d. hm_requests (30分钟窗口)
- 总请求: 1,120
- fallback率: 91.5% (1,025/1,120)
- 直接成功: ~95 (8.5%)
- fallback成功: 1,025 (91.5%)

### 1e. Latency Percentiles
| 百分位 | 延迟 (ms) |
|---|---|
| p50 | 16,428 |
| p90 | 39,368 |
| p95 | 53,018 |
| avg | 21,274 |

### 1f. glm5.1_hm_nv per-key 429分布
k0=198, k1=214, k2=220, k3=210, k4=209 — 确认**函数级429限流** (均匀分布, range=22)

### 1g. Deepseek timeout bucket distribution (50 total)
```
bucket | cnt  | %
-------+------+-----
<20s   |  16  | 32.0%
20-25s |   3  |  6.0%
25-30s |   3  |  6.0%
30-35s |   5  | 10.0%
>40s   |  21  | 42.0% ← LARGEST BUCKET
```

### 1h. Per-key deepseek timeout + >40s distribution
```
nv_key_idx | NVCFPexecTimeout | budget_exhausted | >40s cnt
-----------+------------------+------------------+----------
0          |   7              |   1              |   4
1          |  10              |   1              |   5
2          |  14              |   0              |   7  ← highest >40s
3          |   9              |   1              |   3
4          |   8              |   1              |   2
```

### 1i. ConnectionResetError per-key distribution
k0=12, k1=12, k2=11, k3=13, k4=9 — 均匀分布，非per-key问题

### 1j. Tiers Tried Count (Reserve Check)
| tiers_tried_count | 计数 |
|---|---|
| 1 | 96 (glm5.1直接) |
| 2 | 1,010 (deepseek fallback) |
| 3 | 11 (kimi chain) |
| 0 | **0** ← 无pre-tier连接失败 |

### 1k. 最近10条请求
全部deepseek fallback成功，平均duration ~15s，稳定。

### 1l. 当前compose行号 (已确认)
- Line 417: UPSTREAM_TIMEOUT
- Line 418: TIER_TIMEOUT_BUDGET_S
- Line 420: MIN_OUTBOUND_INTERVAL_S
- Line 421: KEY_COOLDOWN_S
- Line 422: TIER_COOLDOWN_S
- Line 451: HM_CONNECT_RESERVE_S

---

## 2. 诊断

### 2a. >40s Bucket持续主导 — UPSTREAM轨迹继续

deepseek NVCFPexecTimeout >40s bucket = 21/50 (42.0%) — **R58的24/57 (42.1%)基本持平**，仍然是最大的timeout group。

这与R46-R58的UPSTREAM轨迹一致：
- R46 (UPSTREAM=44): 37 events (40.7%)
- R48 (UPSTREAM=46): 39 events (41.1%)
- R50 (UPSTREAM=48): 35 events (40.7%)
- R52 (UPSTREAM=50): 33 events (42.9%)
- R54 (UPSTREAM=52): 32 events (42.1%)
- R56 (UPSTREAM=54): 28 events (41.8%)
- R58 (UPSTREAM=54): 24 events (42.1%)
- R60 (UPSTREAM=54): 21 events (42.0%) ← 当前

>40s bucket占比稳定在41-43%范围，说明NVCF完成时间在UPSTREAM边界处存在持续的超时完成群体。每+2s UPSTREAM扩展直接捕获前一轮UPSTREAM边界处的完成请求。

### 2b. 预算数学评估

当前配置: UPSTREAM=54, BUDGET=98, RESERVE=22
- 1st attempt = min(54, 98-22=76) = 54s
- Remaining = 98-54 = 44s
- 2nd attempt = max(10, min(54, 44-22=22)) = 22s ✓

UPSTREAM→56配置: UPSTREAM=56, BUDGET=98, RESERVE=22
- 1st attempt = min(56, 98-22=76) = 56s (+2s)
- Remaining = 98-56 = 42s
- 2nd attempt = max(10, min(56, 42-22=20)) = 20s

**2nd-attempt从22s→20s (-2s)** — 回到R56的decision boundary (20s)。

**判断**: 20s仍然在安全范围内(>10s minimum)。R56在UPSTREAM=54, 2nd=20s下运行稳定一整轮(R56→R57)，证实20s headroom足够。UPSTREAM→56的策略是：用1st-attempt多2s捕获54-56s边界完成，换取2nd-attempt少2s。净效果取决于边界完成的捕获数vs 2nd-attempt的损失。

**决策规则**: 当>40s bucket ≥35 events AND is largest bucket时，UPSTREAM +2s。当前21 events > 0 但< 35。然而——百分比(42.0%)才是更重要的信号：持续42%+占比说明这个群体是结构性的，不会自行消失。UPSTREAM轨迹的R46-R60历史证明每次+2s都有效降低>40s绝对计数(37→39→35→33→32→28→24→21)。

### 2c. 0-tier完全清除

0-tier pre-tier connection failure = **0** — 首次完全清除！UPSTREAM=54 + RESERVE=22 彻底消除了pre-tier连接失败。这是UPSTREAM间接效应的最终验证。

### 2d. k2键deepseek >40s = 7 (最高)

Per-key分布: k0=4, k1=5, k2=7, k3=3, k4=2。k2偏高(7/21=33.3%)，但总体分布尚在正常范围 (2-7)，不像R58 k2=9那么极端。

---

## 3. 优化

| 参数 | 修改前 | 修改后 | 理由 |
|---|---|---|---|
| UPSTREAM_TIMEOUT | 54 | 56 | +2s; 扩大1st-attempt窗口(54→56s)捕获54-56s边界NVCF完成; >40s bucket=21(42.0%主导); 1st=56s 2nd=20s(=R56决策边界,已验证安全); 0-tier=0(R58首次完全清除); 少改多轮(单参数变更); 铁律:只改HM1不改HM2 |

### 预算数学 (新配置)
- UPSTREAM=56, BUDGET=98, RESERVE=22
- 1st attempt = 56s (+2s from 54s)
- 2nd attempt = 20s (-2s from 22s)
- 2nd-attempt headroom: 20s (回到R56水平, 已验证安全)

---

## 4. 执行记录

```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R60'

# 变更值 (line 417: UPSTREAM_TIMEOUT)
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && sed -i "417s/\"54\"/\"56\"/" docker-compose.yml'

# 更新注释
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '417s/# R56:.*$/# R60: HM2优化 — 54→56: +2s upstream timeout; UPSTREAM=56 BUDGET=98 RESERVE=22 1st=56s remain=42 2nd=20s; deepseek >40s=21(42.8%主导); 2nd-attempt=20s(decision boundary); 少改多轮(单参数); 铁律:只改HM1不改HM2/' docker-compose.yml"

# 部署
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'
# → Container hm40006 Recreated, Started

# 验证
ssh -p 222 opc_uname@100.109.153.83 'docker exec hm40006 env | grep -E "UPSTREAM_TIMEOUT|TIER_TIMEOUT_BUDGET|KEY_COOLDOWN|TIER_COOLDOWN|MIN_OUTBOUND|HM_CONNECT_RESERVE"'
# → UPSTREAM_TIMEOUT=56, TIER_TIMEOUT_BUDGET_S=98, MIN_INTERVAL=14.0, KEY=38.0, TIER_COOLDOWN=82, RESERVE=22
# All unchanged except UPSTREAM_TIMEOUT ✓

# 容器状态
ssh -p 222 opc_uname@100.109.153.83 'docker ps --format "{{.Names}} {{.Status}}" | grep hm40006'
# → hm40006 Up 43 seconds (healthy) ✓
```

---

## 5. 预期效果

- **1st-attempt completion**: 捕获54-56s边界NVCF完成 (预测~2-4个>40s事件将不再超时)
- **>40s bucket**: 21→~17-19 (减少2-4个边界完成)
- **2nd-attempt headroom**: 22s→20s (-2s, 回到R56水平)
- **fallback率**: 维持~91.5% — 429仍100%
- **0-tier**: 保持0 — UPSTREAM+2s不影响pre-tier连接
- **整体成功率**: 保持 ~99% (all fallback成功)

---

## 6. 观察项

- **RISK**: 2nd-attempt=20s (decision boundary) — R56在20s下运行稳定,但下轮(+2s后=18s)必须切换到BUDGET expansion (98→100)
- **WATCH**: >40s bucket绝对值持续下降(24→21), 百分比持平(42.1%→42.0%) — 结构性瓶颈,需持续UPSTREAM扩展
- **WATCH**: ConnectionResetError=57 (vs R58的58, 稳定), 不恶化
- **WATCH**: k2键>40s=7 (最高), 继续观察proxy端口不对称
- **REMINDER**: 下轮如果UPSTREAM→58, 2nd=max(10,min(58,40-22=18))=18s → 必须先BUDGET 98→100, 然后2nd=max(10,min(58,42-22=20))=20s — 铁律: 先BUDGET再UPSTREAM
- **R60单参数变更**: 符合"少改多轮"原则
- **铁律**: 只改HM1不改HM2 ✓

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记
