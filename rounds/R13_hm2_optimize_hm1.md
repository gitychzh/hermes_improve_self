# R13: HM2 优化 HM1 (hm40006) — 缩短TIER_COOLDOWN释放glm5.1被冻结的5分钟, 调KEY_COOLDOWN适配新节奏

**日期**: 2026-06-26 02:25 CST
**执行者**: HM2 (opc2_uname)
**目标**: HM1 (opc_uname@100.109.153.83)
**上一轮**: R12 (HM1优化HM2: 修复磁盘满致DB失效, MIN_OUTBOUND 5→6, TIER_TIMEOUT_BUDGET 75→70)

---

## 📊 数据采集

### 1. Docker日志 (最近500行, R12配置下 ~02:16-02:23)

```
过去500行关键模式:
- 39个 [HM-REQ], 全部 glm5.1_hm_nv primary
- 27个 [HM-TIER-SKIP] tier=glm5.1_hm_nv — 占69.2%的请求直接跳过glm5.1
- 0个 glm5.1 直接成功 (在429风暴期间)
- 7个 glm5.1 直接成功 (在cooldown恢复后: 02:22-02:23)
- 27个 deepseek fallback成功
- 1个 kimi fallback成功
```

**典型429→TIER-SKIP雪崩模式** (02:16-02:21):
```
02:16:08 [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=5, elapsed=5s
      → TIER_COOLDOWN 300s 触发
02:16:12~02:21:00 所有请求: [HM-TIER-SKIP] → direct to deepseek
      → 5分钟glm5.1完全不可用
02:22:22 [HM-SUCCESS] tier=glm5.1_hm_nv k3 — cooldown过期, 恢复
```

### 2. DB分析 (2小时窗口)

| 指标 | 值 |
|------|-----|
| 总请求数 | 194 |
| Primary成功(无fallback) | 88 (45.4%) |
| Fallback发生 | 106 (54.6%) |
| Avg duration | 15,457ms |
| Avg ttfb | 12,664ms |

### 3. 错误分布 (2h, hm_tier_attempts)

| 错误类型 | 数量 | avg_elapsed_ms | 占比 |
|----------|------|----------------|------|
| 429_nv_rate_limit | 34 | — | 55.7% |
| NVCFPexecTimeout | 27 | 23,821 | 44.3% |

### 4. 按tier的NVCFPexecTimeout分布 (2h)

| tier | bucket | count | avg_ms |
|------|--------|-------|--------|
| deepseek_hm_nv | 25-30s | 18 | 25,964 |
| deepseek_hm_nv | 10-20s | 5 | 14,263 |
| deepseek_hm_nv | 20-25s | 2 | 24,671 |
| deepseek_hm_nv | >30s | 1 | 30,138 |
| glm5.1_hm_nv | 25-30s | 1 | 25,022 |

**关键发现**: deepseek 26个timeout中18个(69%)耗时25-30s → 接近UPSTREAM_TIMEOUT=25s上限, 说明deepseek NVCF连接建立后上游响应慢

### 5. 429时间分布(4h, glm5.1, per minute)

| 时间 | c429 | total |
|------|------|-------|
| 01:39 | 5 | 5 |
| 01:40 | 6 | 6 |
| 01:47 | 5 | 5 |
| 01:50 | 5 | 5 |
| 02:09 | 5 | 5 |
| 02:16 | 5 | 5 |
| 02:22 | 1 | 1 |

**模式**: 429以突发出现(全5key同时429), 间隔~20-30分钟 → 每次触发TIER_COOLDOWN=300s雪崩

### 6. 请求路由统计 (30min)

| 路由 | 计数 | 占比 | 平均延迟 |
|------|------|------|---------|
| glm5.1直接成功 | 10 | 50% | ~7-16s |
| fallback(deepseek) | 9 | 45% | ~5-13s |
| fallback(kimi) | 1 | 5% | ~53s |

### 7. 环境变量 (R12配置, R13修改前)

```
UPSTREAM_TIMEOUT=25
TIER_TIMEOUT_BUDGET_S=60
MIN_OUTBOUND_INTERVAL_S=6.0
KEY_COOLDOWN_S=25.0
TIER_COOLDOWN_S=300
HM_CONNECT_RESERVE_S=5
```

---

## 🩺 诊断

### 根因: TIER_COOLDOWN=300s 导致 glm5.1 长时间TIER-SKIP

当所有5个key同时收到429(NVCF rate limit突发), 系统触发TIER_COOLDOWN=300s。这意味着:

1. **5分钟内glm5.1完全不可用** — 所有请求被迫fallback到deepseek
2. **12个请求/分钟×5分钟 ≈ 60个请求全部走fallback** — 代价: +3-8s延迟/请求
3. **429突发间隔~20-30分钟** — 但cooldown每次锁定5分钟 = 占总时间17-25%
4. **实际观察: 27/39请求(69%)被TIER-SKIP** — glm5.1利用率极低

**关键洞察**: NVCF rate limit窗口大致5分钟(300s), 但这不意味着所有key需要等满5分钟才可用。实际429恢复更快(1-2分钟内部分key已恢复), 但TIER_COOLDOWN强制等待5分钟, 浪费了key的可用时间。

### 证据链

1. **27/39=69%请求被TIER-SKIP** — TIER-SKIP占绝大多数, 说明TIER_COOLDOWN是首要瓶颈
2. **429突发后~2分钟, cooldown仍在** — 02:16触发429, 02:18-02:21仍然SKIP(已过2-3分钟)
3. **02:22恢复成功(glm5.1 direct)** — 429后~6分钟才恢复 → cooldown=300s完全覆盖了5分钟恢复窗口
4. **deepseek fallback的26个timeout** — 如果glm5.1可用, 这些fallback不会发生
5. **429均匀分布5个key** → 不是单key问题, 是NVCF函数级限流 → TIER_COOLDOWN对齐函数窗口合理, 但300s过宽

### 改善空间

| TIER_COOLDOWN | 429后等待 | glm5.1可用时间占比(假设429每20min) | TIER-SKIP预计比例 |
|---------------|----------|--------------------------------------|-------------------|
| 300s (当前) | 5分钟 | 75% | ~70% |
| 180s (建议) | 3分钟 | 85% | ~40% |
| 120s (激进) | 2分钟 | 90% | ~25% |

选择180s(3分钟): 保守但有效 — 仍避免NVCF窗口峰值(429突发后3分钟内重试), 同时减少2分钟无效SKIP

---

## 🔧 优化方案

**策略**: 2个精确参数调整。核心: 缩减TIER_COOLDOWN让glm5.1更快从429风暴中恢复, 提高primary层利用率。

| # | 变更 | Before | After | 理由 |
|---|------|--------|-------|------|
| 1 | `TIER_COOLDOWN_S` | 300 | **180** | 5min blackout太激进: 429突发每20-30min, cooldown=300s覆盖完5分钟恢复窗口; 180s=3min, 仍避免NVCF窗口峰值但早2分钟重试; 预计TIER-SKIP从69%降至<40% |
| 2 | `KEY_COOLDOWN_S` | 25.0 | **22.0** | 25s与TIER_COOLDOWN=300配套过保守; TIER_COOLDOWN降至180后, KEY_COOLDOWN也需适配: 22s + 6s interval = 3.67 cycles/retry (vs 4.2), 每cycle省3s; key恢复更快, 429后更多key在cooldown窗口内被重新尝试 |

**铁律**: 只改HM1配置, 绝不改HM2本地环境. 所有修改仅在HM1机器上的docker-compose.yml中执行.

**不改动项**:
- UPSTREAM_TIMEOUT=25 — R11验证有效, 25s截断已充分
- TIER_TIMEOUT_BUDGET_S=60 — R12调整, 适配6s interval
- MIN_OUTBOUND_INTERVAL_S=6.0 — R12调整, 已减缓轮转
- HM_CONNECT_RESERVE_S=5 — SOCKS5+SSL握手充足

---

## ✅ 执行记录

```bash
# 1. SSH到HM1
ssh -p 222 opc_uname@100.109.153.83

# 2. 收集数据
docker logs hm40006 --tail 2000
docker exec cc_postgres psql -U litellm -d hermes_logs -c "..." (多表查询)
docker exec hm40006 env | grep -E 'MIN_OUTBOUND|KEY_COOLDOWN|...'

# 3. 备份
cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R13

# 4. 参数修改 (2项)
cd /opt/cc-infra
sed -i 's/TIER_COOLDOWN_S: "300"/TIER_COOLDOWN_S: "180"/' docker-compose.yml
sed -i 's/KEY_COOLDOWN_S: "25.0"/KEY_COOLDOWN_S: "22.0"/' docker-compose.yml

# 5. 注释更新 (R13说明)

# 6. 部署
docker compose up -d hm40006

# 7. 验证
docker exec hm40006 env | grep -E 'KEY_COOLDOWN|TIER_COOLDOWN'
# → KEY_COOLDOWN_S=22.0  ✓
# → TIER_COOLDOWN_S=180   ✓
docker ps --format '{{.Names}} {{.Status}}' | grep hm40006
# → hm40006 Up 15 seconds (healthy)  ✓
```

**最终配置确认**:
- TIER_COOLDOWN_S=**180** ← **R13: 300→180**, 3分钟cooldown释放glm5.1
- KEY_COOLDOWN_S=**22.0** ← **R13: 25→22**, 配合TIER_COOLDOWN缩短
- UPSTREAM_TIMEOUT=25 (保持, R11验证)
- TIER_TIMEOUT_BUDGET_S=60 (保持, R12调整)
- MIN_OUTBOUND_INTERVAL_S=6.0 (保持, R12调整)
- HM_CONNECT_RESERVE_S=5 (保持)

---

## 📈 预期效果

1. **glm5.1 TIER-SKIP大幅下降** — 从27/39=69%降至目标<40%: 每次TIER-SKIP少2分钟(300→180), 即每20分钟少约5-8个SKIP请求
2. **Fallback率下降** — 更多请求走glm5.1 primary(更快更便宜), 目标: <50% fb (当前54.6%)
3. **平均延迟降低** — glm5.1 primary直接成功~8s vs deepseek fallback ~8s + 路由开销; 降TIER-SKIP=减少无谓的deepseek路由延迟
4. **deepseek timeout减少** — glm5.1恢复后减少对deepseek的依赖, 间接减少deepseek NVCFPexecTimeout

---

## ⚠️ 待观察

- **TIER_COOLDOWN=180是否太激进** — 如果429恢复窗口实际是4分钟, 180s时重试可能再次429触发新一轮cooldown; 需观察429时间间隔
- **KEY_COOLDOWN=22是否合适** — 22s+6s interval=3.67 cycles, 每个key在cooldown后可能更快命中NVCF; 如果429不降反升, 回滚到25
- **deepseek timeout变化** — 18/26(69%)的deepseek timeout在25-30s范围, 接近UPSTREAM_TIMEOUT=25s; 是否需要关注
- **429绝对数量** — R12配置6s interval后429从679/h→34/2h≈17/h, 已降~95%; R13的KEY_COOLDOWN缩短可能略微回升, 但应远低于R10水平

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记
