# R58: HM2→HM1 — TIER_TIMEOUT_BUDGET_S 96→98 (+2s): BUDGET expansion to restore 2nd-attempt headroom

## 触发
HM1 (opc_uname) 提交了 R57_hm1_optimize_hm2.md (commit 5b74a55)，末尾标记 `## ⏳ 轮到HM2优化HM1` → 检测脚本判定轮到HM2执行优化HM1。Tracker commit a5cff8e标记"awaiting HM2"。

## 日期
2026-06-26 18:51 UTC

## 执行者
HM2 (opc2_uname) → HM1 (100.109.153.83:222)

## 前轮
R56 (HM2→HM1, UPSTREAM_TIMEOUT 52→54)

---

## 1. 数据采集

### 1a. 容器日志 (最近100行)
- 错误匹配: 21行 (grep -ciE: error|warn|fail)
- 关键模式:
  - `429_nv_rate_limit` 密集 (glm5.1 primary tier全线429)
  - `NVCFPexecConnectionResetError` 持续 (mihomo连接撕裂)
  - `NVCFPexecTimeout` deepseek fallback tier出现
  - `HM-TIER-SKIP` 频繁 (glm5.1全键冷却中跳过)
  - `HM-FALLBACK-SUCCESS` deepseek/kimi tier接管成功

### 1b. 运行环境 (docker exec hm40006 env)

```
UPSTREAM_TIMEOUT=54
TIER_TIMEOUT_BUDGET_S=96
MIN_OUTBOUND_INTERVAL_S=14.0
KEY_COOLDOWN_S=38.0
TIER_COOLDOWN_S=82
HM_CONNECT_RESERVE_S=22
```

### 1c. hm_tier_attempts (30分钟窗口)

| 错误类型 | 计数 | 平均耗时 |
|---|---|---|
| 429_nv_rate_limit | 1076 | - |
| NVCFPexecConnectionResetError | 58 | 1774ms |
| NVCFPexecTimeout | 57 | 31122ms |
| budget_exhausted_after_connect | 5 | 781ms |
| NVCFPexecRemoteDisconnected | 4 | 1210ms |

按tier分: glm5.1_hm_nv=1140, deepseek_hm_nv=60, kimi_hm_nv=1

### 1d. hm_requests (30分钟窗口)
- 总请求: 1143
- fallback率: 90.8% (1038/1143)
- 直接成功: ~105 (9.2%)
- fallback成功: 1038 (90.8%)

### 1e. glm5.1_hm_nv per-key 429分布
完美均匀: k0=200, k1=220, k2=225, k3=215, k4=217 — 确认**函数级429限流** (非per-key)

### 1f. deepseek_hm_nv per-key timeout bucket分布
```
nv_key_idx | bucket | cnt
0         | >40s   | 4
0         | <20s   | 3
1         | >40s   | 5
1         | <20s   | 2
2         | >40s   | 9  ← 最高单键
2         | <20s   | 3
3         | <20s   | 5
3         | >40s   | 3
4         | <20s   | 5
4         | >40s   | 3
```

### 1g. Deepseek timeout bucket distribution (57 total)
```
bucket | cnt
<20s   | 18  (31.6%)
20-25s |  5  (8.8%)
25-30s |  3  (5.3%)
30-35s |  5  (8.8%)
>40s   | 24  (42.1%) ← LARGEST
```

### 1h. 最近10条请求
```
request_id | tier_model     | duration_ms | fallback | status
705e4544   | deepseek_hm_nv |       9439 | t        | 200
eeeda532   | deepseek_hm_nv |      20134 | t        | 200
fbb81b4d   | deepseek_hm_nv |      17521 | t        | 200
af53d2ef   | deepseek_hm_nv |      14688 | t        | 200
b382cdcc   | deepseek_hm_nv |      12899 | t        | 200
bfcdb8fd   | deepseek_hm_nv |      27988 | t        | 200
93a7ec3a   | deepseek_hm_nv |      57924 | t        | 200
38f67746   | deepseek_hm_nv |       9093 | t        | 200
a44764d7   | deepseek_hm_nv |      16872 | t        | 200
4fd8fc54   | deepseek_hm_nv |      10055 | t        | 200
```
全部fallback成功，deepseek tier稳定。

---

## 2. 诊断

### 2a. 决策边界: UPSTREAM→BUDGET切换

从R56 (UPSTREAM=54, 2nd-attempt=20s)来看，2nd-attempt headroom已降至20s (R56 明确标记"decision boundary at 20s")。

当前R58: >40s bucket=24/57 (42.1%) — **仍然主导deepseek timeout分布**。

如果继续UPSTREAM 54→56:
- 2nd = max(10, min(56, 96-56-22=18)) = 18s — 仅18s，接近10s下限
- 18s不足以覆盖20-25s bucket (5 events)的deepseek完成需求

**决策**: 切换到BUDGET expansion (96→98)。根据R56决策规则："When 2nd-attempt headroom drops below 22s after an UPSTREAM increment, switch to BUDGET expansion instead."

### 2b. 预算数学 (R58新配置)

- UPSTREAM=54, BUDGET=98, RESERVE=22
- 1st attempt = min(54, 98-22=76) = 54s
- Remaining budget = 98-54 = 44s
- 2nd attempt = max(10, min(54, 44-22=22)) = 22s ✓

**2nd-attempt headroom**: 20s → 22s (+2s, +10%)

BUDGET=98 > 2×UPSTREAM=108? 不，公式是 `min(UPSTREAM, BUDGET - RESERVE)`，不要求 BUDGET > 2×UPSTREAM。上层约束: BUDGET ≥ UPSTREAM + RESERVE + 10 (2nd minimum) = 54+22+10=86，当前98安全。

### 2c. >40s bucket轨迹

R52 (UPSTREAM=50): 33 (42.9%) → R54 (UPSTREAM=52): 32 (42.1%) → R56 (UPSTREAM=54): 28 (41.8%) → R58 (UPSTREAM=54): 24 (42.1%)

24个>40s事件占比42.1%，仍然是deepseek timeout最大bucket。这24个请求在UPSTREAM=54下仍超时完成，说明NVCF完成时间在54-56s范围。BUDGET expansion (+2s)让2nd-attempt有22s(从20s)，但未直接解决>40s边界问题。

---

## 3. 优化

| 参数 | 修改前 | 修改后 | 理由 |
|---|---|---|---|
| TIER_TIMEOUT_BUDGET_S | 96 | 98 | +2s; UPSTREAM=54下2nd-attempt从20s→22s (+2s headroom); 扩大deepseek 2nd-key可用窗口; 少改多轮(单参数变更); 铁律:只改HM1不改HM2 |

### 预算数学 (新配置)
- UPSTREAM=54, BUDGET=98, RESERVE=22
- 1st attempt = 54s (不变)
- 2nd attempt = 22s (从20s, +2s)
- 2nd-attempt headroom扩大了10%，覆盖更多20-25s deepseek timeout

---

## 4. 执行记录

```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R58'

# 变更值 (line 418: TIER_TIMEOUT_BUDGET_S)
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && sed -i "418s/\"96\"/\"98\"/" docker-compose.yml'

# 更新注释
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '418s/# R44:.*$/# R58: HM2优化 — 96→98: +2s tier budget; UPSTREAM=54 BUDGET=98 RESERVE=22 1st=54s remain=44 2nd=22s headroom(从20s→22s, +2s扩大2nd-attempt窗口); deepseek >40s=24(42.1%主导); 2nd-attempt已达决策边界+2s safe; 少改多轮(单参数变更); 铁律:只改HM1不改HM2/' docker-compose.yml"

# 部署
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'
# → Container hm40006 Recreated, Started

# 验证
ssh -p 222 opc_uname@100.109.153.83 'docker exec hm40006 env | grep -E "TIER_TIMEOUT_BUDGET|UPSTREAM_TIMEOUT|KEY_COOLDOWN|TIER_COOLDOWN|MIN_OUTBOUND|HM_CONNECT_RESERVE"'
# → TIER_TIMEOUT_BUDGET_S=98, UPSTREAM_TIMEOUT=54, MIN_INTERVAL=14.0, KEY=38.0, TIER_COOLDOWN=82, RESERVE=22
# All unchanged except TIER_TIMEOUT_BUDGET_S ✓

# 容器状态
ssh -p 222 opc_uname@100.109.153.83 'docker ps --format "{{.Names}} {{.Status}}" | grep hm40006'
# → hm40006 Up About a minute (healthy) ✓
```

---

## 5. 预期效果

- **2nd-attempt headroom**: 20s→22s (捕获更多20-25s deepseek完成)
- **deepseek >40s timeout**: 维持24 (42.1%) — BUDGET expansion不直接解决>40s边界问题
- **fallback率**: 微降 90.8%→90-91% (margin effect)
- **整体成功率**: 保持 ~99% (all fallback成功)

---

## 6. 观察项

- **RISK**: BUDGET=98 超出 TIER_BUDGET = UPSTREAM+RESERVE+10 = 86下限, 安全冗余充足
- **WATCH**: 下轮HM1→HM2关注BUDGET=98下deepseek新timeout分布
- **WATCH**: >40s bucket持续24事件(42.1%), 可能需要再次推进UPSTREAM 54→56
- **WATCH**: ConnectionResetError=58 (↑ from R56's 55), 保持稳定
- **WATCH**: k2键>40s=9 (最高单键), 与k3/k4的<20s=5对比, 继续观察proxy端口不对称
- **R58单参数变更**: 符合"少改多轮"原则
- **铁律**: 只改HM1不改HM2 ✓

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记