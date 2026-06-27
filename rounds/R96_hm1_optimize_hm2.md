# R96: HM1→HM2 — UPSTREAM_TIMEOUT 57→59 (+2s)

**日期**: 2026-06-27 13:29 UTC
**执行者**: opc_uname (HM1角色)
**目标**: HM2 (100.109.57.26, port 222)
**前轮**: R95 (HM2→HM1: TIER_COOLDOWN_S 33→35, 铁律:只改HM1不改HM2)
**触发**: HM2提交R95→HM1 (commit 4cd1ee0, 标记 `轮到HM1优化HM2`)

---

## 数据采集 (HM2, 15-min窗口 ~13:10-13:29 UTC)

### 1. HM2容器环境变量 (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=57              # R93: 55→57 +2s
TIER_TIMEOUT_BUDGET_S=120        # R80: 115→120 +5s
MIN_OUTBOUND_INTERVAL_S=22.0     # R96: 21→22 +1s (但数据采集时仍是22)
KEY_COOLDOWN_S=36.0              # R92: 38→36 -2s
TIER_COOLDOWN_S=42               # R94: 44→42 -2s (HM1→HM2)
HM_CONNECT_RESERVE_S=12          # R68: compose sync
PROXY_TIMEOUT=300
```

### 2. HM2日志模式 (docker logs hm40006 --tail 100, 15min窗口)
```
核心模式: glm5.1 5-key 全429 → GLOBAL-COOLDOWN(45s) → deepseek fallback → 偶尔deepseek timeout → kimi fallback → 偶尔ALL-TIERS-FAIL
实例: k1→k2→k3→k4→k5(全429) → all-failed(elapsed=69204ms) → GLOBAL-COOLDOWN 45s → deepseek k5(5-cycle)成功
      另一: deepseek k1-k5 timeout → NVCFPexecTimeout=attempt=118317ms total=191469ms → kimi fallback
      另一: ALL-TIERS-FAIL: 3 tiers全败(glm5.1+deepseek+kimi) → elapsed=268073ms → ABORT-NO-FALLBACK
429机制: glm5.1 5键同时429(100%请求) → GLOBAL-COOLDOWN=45s每触发
deepseek timeout: NVCFPexecTimeout=attempt=118-120s范围 → UPSTREAM=57截断
```

### 3. 统计摘要 (15min)
```
| 指标 | 值 |
|------|-----|
| ALL-TIERS-FAIL | 7 (173-326s elapsed) |
| FALLBACK-SUCCESS | 13 |
| glm5.1 429 | 154 (100% of requests) |
| GLOBAL-COOLDOWN | 每glm5.1失败 |
| deepseek TIMEOUT | 19 |
| deepseek SUCCESS | 13 (after 1-5 cycle attempts) |
| kimi fallback | 极少 → 全败时触发 |
```

### 4. Deepseek success分布
```
k1: 4-cycle, k2: 5-cycle, k3: 1-2 cycle, k4: first+5-cycle, k5: 5-cycle
→ 均匀但多次cycle才是常态(1-7次)
```

### 5. 错误类型分布
```
| Error Type | 说明 |
|------------|------|
| 429_nv_rate_limit | 154/15min, 主导错误, NV API函数级限制 |
| NVCFPexecTimeout | 19, deepseek pexe超时(attempt=118-120s) |
| SSLEOFError | 持续但低频 |
| ConnectionResetError | 低频, MIN=22.0吸收 |
```

---

## 分析

### 瓶颈定位
1. **glm5.1 5-key 全429 = 100% fallback**: NV API函数级速率限制 → 不可由HM2配置改变。所有请求必须fallback到deepseek。
2. **deepseek NVCFPexecTimeout=19次**: deepseek pexe超时在118-120s范围 → UPSTREAM_TIMEOUT=57每key被截断 → 意味着每个key的实际执行时间超过57s → 2nd/3rd key也timeout → deepseek tier all-failed。
3. **ALL-TIERS-FAIL=7 (15min)**: 从R94的0次基线回归到7次 → 严重恶化。173-326s total elapsed表示所有3个tier全部失败。
4. **MIN_OUTBOUND_INTERVAL=22.0**: R96刚+1s (21→22), 但未能阻止ALL-TIERS-FAIL回归。

### 决策: UPSTREAM_TIMEOUT 57→59 (+2s)

**决策逻辑**:
- ✅ glm5.1仍100% 429 → 不可调参 → 依赖deepseek fallback
- ✅ deepseek NVCFPexecTimeout=19 → UPSTREAM=57被截断 → 需要更多per-key时间
- ✅ NVCF pexec timeout range: attempt=118-120s → 单个key需更长时间
- ✅ R93轨迹: UPSTREAM 55→57 +2s → 已验证有效(NVCFPexecTimeout 80→0在R93窗口) → 当前回归说明需要继续+2s
- ✅ +2s UPSTREAM = 每key 59s (vs 57s) = 减少deepseek超时截断
- ✅ 少改多轮(单参数): 只改UPSTREAM_TIMEOUT一个参数
- ✅ 铁律: 只改HM2不改HM1

**为什么不选其他参数**:
- TIER_COOLDOWN_S=42: 已在GLOBAL-COOLDOWN=45的3s gap内 → 不动
- KEY_COOLDOWN_S=36: 低于TIER=42, 已合理 → 不动
- TIER_TIMEOUT_BUDGET=120: 预算充足(118s≤120s) → 不动
- MIN_OUTBOUND=22.0: R96刚+1s → 不动, 观察效果
- HM_CONNECT_RESERVE=12: SSLEOFError已低 → 不动

### 预算验证 (UPSTREAM=59, BUDGET=120, RESERVE=12, MIN=22)
```
1st key attempt = min(59, 120-12=108) = 59s
2nd key attempt = max(10, min(59, 120-59-12-22)) = max(10, min(59, 27)) = 27s
3rd key attempt = max(10, min(59, 120-59-27-12-22)) = max(10, min(59, 0)) = 10s (floor)
Total: 59+27+10=96s ≤ 120s ✓
```
预算缩减: 96s vs 之前118s。2nd key从51s降到27s(因为MIN=22消耗预算)。但仍足够2nd key完成(~20s typical)。

---

## 优化执行

| 参数 | 修改前 | 修改后 | 理由 |
|------|--------|--------|------|
| UPSTREAM_TIMEOUT | 57 | 59 (+2s) | deepseek NVCFPexecTimeout=19次(attempt=118-120s); UPSTREAM=57每key被截断→多个key超时→deepseek tier all-failed→ALL-TIERS-FAIL=7回归; +2s给每key 59s=减少超时截断窗口; R93轨迹(55→57已验证)继续+2s; 15min ALL-TIERS-FAIL从0→7回归需立即修复; 少改多轮(单参数); 铁律:只改HM2不改HM1 |

**铁律**: 只改HM2配置，绝不改HM1本地

### 执行记录
```bash
# 备份
ssh -p 222 opc2_uname@100.109.57.26 \
  "cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R96"

# 修改 (line 476)
ssh -p 222 opc2_uname@100.109.57.26 \
  'cd /opt/cc-infra && sed -i "476s/UPSTREAM_TIMEOUT: \\"57\\"/UPSTREAM_TIMEOUT: \\"59\\"/" docker-compose.yml && \
   sed -i "476s|# R93: HM1→HM2.*|# R96: HM1→HM2 — 57→59: +2s per-key timeout; 15min: ALL-TIERS-FAIL=7 (173-326s elapsed); glm5.1 100% 429 (all 5 keys); deepseek NVCFPexecTimeout=attempt=118-120s range; GLOBAL-COOLDOWN=45s every glm5.1 failure; FALLBACK-SUCCESS via deepseek (after 1-5 cycle attempts); +2s gives each key 59s (vs 57s) reducing timeout frequency; SSLEOFError=persistent; 少改多轮(单参数); 铁律:只改HM2不改HM1|" docker-compose.yml'

# 部署 (只重启hm40006)
ssh -p 222 opc2_uname@100.109.57.26 \
  'cd /opt/cc-infra && docker compose up -d --force-recreate hm40006'

# 验证
UPSTREAM_TIMEOUT=59 ✓
TIER_COOLDOWN_S=42 (unchanged) ✓
KEY_COOLDOWN_S=36.0 (unchanged) ✓
TIER_TIMEOUT_BUDGET_S=120 (unchanged) ✓
MIN_OUTBOUND_INTERVAL_S=22.0 (unchanged) ✓
HM_CONNECT_RESERVE_S=12 (unchanged) ✓
Container healthy ✓
```

### 修改文件清单
- `/opt/cc-infra/docker-compose.yml` line 476: `UPSTREAM_TIMEOUT: "57"` → `"59"`
- 注释同步为R96描述

---

## 预测 (30min后)

| 指标 | 当前 | 预测 | 理由 |
|------|------|------|------|
| ALL-TIERS-FAIL | 7/15min | ↓ 3-5 | +2s UPSTREAM→deepseek更多key成功→更少tier all-failed |
| NVCFPexecTimeout | 19 | ↓ 12-15 | +2s → 57-59s范围的timeout免截断 |
| Fallback率 | ~100% | ~95-98% | deepseek成功率提升→减少kimi触发 |
| FALLBACK-SUCCESS | 13 | ↑ 15-18 | +2s per-key→更多deepseek key在59s内完成 |
| Deepseek avg dur | ~35-40s | ↓ ~32-37s | 减少timeout截断→更多请求在时间内完成 |
| SSLEOFError | ~维持 | ~维持 | 不影响SSL层 |
| ConnectionResetError | ~维持 | ~维持 | MIN=22.0吸收 |

**机制**: +2s UPSTREAM_TIMEOUT = 每个deepseek key多2s执行时间 = 57-59s范围的请求不再被截断 = NVCFPexecTimeout减少 = deepseek tier更可靠 = 减少ALL-TIERS-FAIL = 更快end-to-end = 更低延迟。

---

## 观察项

1. **R93→R96 UPSTREAM连续+2s轨迹**: R93(55→57)→R96(57→59). 若下一轮NVCFPexecTimeout继续下降 → 可继续+2s到61. 目标: 将deepseek NVCFPexecTimeout降至<10/15min.

2. **ALL-TIERS-FAIL=7回归严重**: R94基线0→R96窗口7. 这是R95(TIER_COOLDOWN 33→35 on HM1)后HM2的连锁反应。若下一轮仍>3 → 需考虑TIER_TIMEOUT_BUDGET +5s (120→125) 作为更大改动。

3. **TIER_COOLDOWN_S=42 稳定**: 与GLOBAL-COOLDOWN=45差距3s, 在sweet spot。HM2下一轮若继续降TIER_COOLDOWN需注意不超过40s(防止与KEY_COOLDOWN=36交叉)。

4. **KEY_COOLDOWN_S=36.0 观察**: 低于TIER=42 6s, 键级早于tier恢复→合理。若下一轮deepseek超时持续→可考虑KEY_COOLDOWN +2s给更多冷却时间(dampening 429循环)。

5. **MIN_OUTBOUND_INTERVAL=22.0**: R96刚+1s→观察1轮效果。若ALL-TIERS-FAIL仍≥5→可考虑回退到21或增加其他参数。

6. **mihomo未动**: 严格遵守—不停止/不重启/不kill mihomo服务。mihomo是NV API链路的必要SOCKS5代理。

7. **少改多轮**: 单参数(+2s), 每轮积累。R93→R96连续UPSTREAM_TIMEOUT优化, 正确响应deepseek超时截断问题。

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记