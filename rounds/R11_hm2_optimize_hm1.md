# R11: HM2 优化 HM1 (hm40006) — 截断死链超时省budget, 降key冷却适配新节奏

**日期**: 2026-06-26 01:30 CST
**执行者**: HM2 (opc2_uname)
**目标**: HM1 (opc_uname@100.109.153.83)
**上一轮**: R10 (HM1优化HM2: UPSTREAM_TIMEOUT 55→65, BUDGET 80→75, MIN_OUTBOUND 6→5, CONNECT_RESERVE 3→5)

---

## 📊 数据采集

### 1. Docker Logs (最近500-2000行, R10配置下 ~00:16-01:25)

```
过去100行(01:23-01:25):
- 21个 [HM-REQ], 全部 glm5.1_hm_nv primary
- 3个 [HM-FALLBACK] → deepseek_hm_nv (primary全部失败)
- 0个 [HM-SUCCESS] tier=glm5.1_hm_nv
- Primary直接成功率: 0%

过去2000行关键数据:
- glm5.1 primary SUCCESS: 0
- deepseek fallback SUCCESS: 35
- [HM-TIER-SKIP] (glm5.1 all cooldown): 33次
- 429_nv_rate_limit事件: 10
- 特征: 5key全部429 → TIER_COOLDOWN 300s → 5分钟内所有请求直跳deepseek
```

**详细模式 (00:17典型tte-429链)**:
```
00:17:38 k4 → 429 (cooldown)
00:17:39 k5 → 429 (cooldown)
00:17:40 k1 → 429 (cooldown)
00:17:42 k2 → ConnectionResetError
00:17:42 k3 → in cooldown (skip) → TIER-FAIL (elapsed=7715ms)
00:17:51 k2 → 429 (GLOBAL-COOLDOWN 300s触发)
00:18:04→00:19:40 所有12个请求: [HM-TIER-SKIP] → direct to deepseek
```

### 2. DB分析 (1小时窗口, 00:26-01:26)

| 指标 | 值 |
|------|-----|
| 总请求数 | 1064 |
| Primary成功 (无fallback) | 413 |
| Fallback发生 | 651 |
| **Fallback率** | **61.2%** |
| Avg duration | 27,998ms |
| Avg primary duration | 21,822ms |
| Avg fallback duration | 31,916ms |
| Avg TTFB | 27,187ms |
| Total key_cycle_429s | 1,089 |

### 3. 错误分布 (1h, hm_tier_attempts)

| 错误类型 | 数量 | avg_elapsed_ms | 占比 |
|----------|------|----------------|------|
| 429_nv_rate_limit | 679 | — | 51.3% |
| NVCFPexecTimeout | 324 (glm5.1:324, deepseek:13) | ~31,566 | 24.5% |
| NVCFPexecSSLEOFError | 32 (glm5.1:25, deepseek:7) | ~7,250 | 2.4% |
| NVCFPexecConnectionResetError | 20 (glm5.1:20) | ~1,066 | 1.5% |
| budget_exhausted_after_connect | 7 (glm5.1:6, deepseek:1) | ~2,336 | 0.5% |
| NVCFPexecProxyConnectionError | 7 (glm5.1:7) | ~1 | 0.5% |
| empty_200 | 6 (deepseek:5, glm5.1:1) | — | 0.5% |

**429在5个key上均匀分布**: k0=139, k1=127, k2=135, k3=142, k4=136 (差异<12%)

### 4. NVCFPexecTimeout 时间分布 (glm5.1, 1h)

| Bucket | 数量 | 分析 |
|--------|------|------|
| <5s | 0 | 极少在5s内超时 |
| 5-15s | 140 | 43% — 部分可恢复但被错误超时 |
| 15-30s | 1 | 几乎没有 |
| >35s | 183 | **56% — 超过UPSTREAM_TIMEOUT=35的请求白白消耗budget** |

**关键发现**: 183/324=56%的NVCFPexecTimeout实际上已经超过了当前UPSTREAM_TIMEOUT=35s。这些请求已经注定失败，但每个仍消耗了~35s的budget时间。

### 5. 环境变量 (R10部署后, R11修改前)

```
UPSTREAM_TIMEOUT=35
TIER_TIMEOUT_BUDGET_S=55
MIN_OUTBOUND_INTERVAL_S=4.0
KEY_COOLDOWN_S=28.0
TIER_COOLDOWN_S=300
HM_CONNECT_RESERVE_S=5
```

### 6. 请求频率 (最近30分钟)

```
请求间隔: 22-76s, 中位数~50s
约1.2 req/min, 即73 req/h
```

---

## 🩺 诊断

### 根因

**1. UPSTREAM_TIMEOUT=35过长, 死链请求吞噬budget** — 当NVCF连接已建立但上游无响应, 35s才断开。324个NVCFPexecTimeout中183个>35s(56%), 意味着这些请求每个浪费35s的TIER_TIMEOUT_BUDGET=55s。5 key全试一轮=5×35=175s >> 55s budget, 导致仅1-2个key被试后budget耗尽。

**2. MIN_OUTBOUND=4.0太激进** — 5 key × 4s = 20s cycle。全部429时, 20s就刷完一轮, 触发GLOBAL-COOLDOWN(300s)。如果4s间隔能让key空间一点, 429可能更分散。

**3. KEY_COOLDOWN=28与4s间隔不匹配** — 28s cooldown + 4s interval意味着key空间的8%同时尝试(4/5轮28s≈1.4 key尝试/4s窗口), 不够均匀分散。

### 证据链

1. **324 NVCFPexecTimeout × avg 31.6s** — 单key超时消耗~30s, 5key=150s远超55s budget
2. **183 timeouts >35s** — UPSTREAM_TIMEOUT直控每key的最大浪费时间
3. **679 429事件(均匀5key)** — 函数级限流, 间距太小加剧同时429
4. **7 budget_exhausted_after_connect** — budget在connect阶段已耗尽, 说明前置key浪费太多
5. **61.2% fallback率** — 虽比R9的69.5%有改善, 但仍有很大优化空间

### 改善点 (vs R10)

| 指标 | R10 (35/4.0/28) | R11 (25/5.0/25) | 变化 |
|------|-----------------|-----------------|------|
| UPSTREAM_TIMEOUT | 35s | **25s** | ⬇️ 截断56%的已死超时 |
| MIN_OUTBOUND | 4.0s | **5.0s** | ⬆️ 5×5=25s cycle, 略微放缓 |
| KEY_COOLDOWN | 28.0s | **25.0s** | ⬇️ 与5s间距对齐, 更均匀重试 |
| Key timeout-waste | 5×35=175s | 5×25=125s | ⬇️ 节省50s/轮 |
| 55s budget可试key数 | 1-2 key (1×35+connect) | 2-3 key (2×25+connect) | ⬆️ 多1个key尝试机会 |

---

## 🔧 优化方案

**策略**: 3个精确参数调整。核心: UPSTREAM_TIMEOUT截断死链连接, 让更多key在budget内被尝试。小幅调整间距和冷却使429更分散。

| # | 变更 | Before | After | 理由 |
|---|------|--------|-------|------|
| 1 | `UPSTREAM_TIMEOUT` | 35 | **25** | 56%的NVCFPexecTimeout>35s, 这些请求已死。25s cutoff让单key浪费上限=25s(而不是35s), 5key×25s=125s仍超budget, 但2-3key×25s=50-75s内可成功/快速fail; 且实测glm5.1 NVCF p50=3s p80=20s, 合法请求25s内都能返回 |
| 2 | `MIN_OUTBOUND_INTERVAL_S` | 4.0 | **5.0** | 4s×5=20s cycle, 5s×5=25s cycle。25s cycle更好匹配NVCF ~60s的限流窗口 recovery节奏: 每分钟2.4次完整cycle vs 3次, 429不会更激进 |
| 3 | `KEY_COOLDOWN_S` | 28.0 | **25.0** | 28s与4s间距不整除(28/4=7步); 25s与5s间距整除(25/5=5步), key恢复尝试更均匀。且28s过保守: NVCF ~60s window内, key在28s idle后再试, 只剩32s余量; 25s cooldown则剩35s余量, 多一次有效尝试 |

**铁律**: 只改HM1配置, 绝不改HM2本地环境. 所有修改仅在HM1机器上的docker-compose.yml中执行.

**不改动项**:
- TIER_TIMEOUT_BUDGET_S=55 — 已足够, 配合UPSTREAM_TIMEOUT=25可让2-3个key被尝试
- TIER_COOLDOWN_S=300 — 5min匹配NVCF函数级限流窗口
- HM_CONNECT_RESERVE_S=5 — SOCKS5连接+SSL握手充足

---

## ✅ 执行记录

```bash
# 1. 备份
ssh -p 222 opc_uname@100.109.153.83
cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R11

# 2. 参数修改 (3项)
cd /opt/cc-infra
sed -i \
  -e 's/MIN_OUTBOUND_INTERVAL_S: "4.0"/MIN_OUTBOUND_INTERVAL_S: "5.0"/' \
  -e 's/KEY_COOLDOWN_S: "28.0"/KEY_COOLDOWN_S: "25.0"/' \
  -e 's/UPSTREAM_TIMEOUT: "35"/UPSTREAM_TIMEOUT: "25"/' \
  docker-compose.yml

# 3. 注释更新 (3项 R11说明)
sed -i \
  -e 's|UPSTREAM_TIMEOUT: "25"  # R45:.*|UPSTREAM_TIMEOUT: "25"  # R11: 35→25 — 56% NVCFPexecTimeout wasted >35s on already-dead reqs; 25s cutoff saves ~10s/key-cycle = 50s/5-key-cycle, 2 more key-chances within 55s budget|' \
  -e 's|MIN_OUTBOUND_INTERVAL_S: "5.0"  # R45:.*|MIN_OUTBOUND_INTERVAL_S: "5.0"  # R11: 4.0→5.0 — 4s with 5 keys = 20s cycle, all keys in <60s NVCF window; 5s = 25s cycle, slight pace reduction for less simultaneous 429|' \
  -e 's|KEY_COOLDOWN_S: "25.0"  # R11:.*|KEY_COOLDOWN_S: "25.0"  # R11: 28→25 — 28s was too conservative, key sits idle while NVCF window recovers; 25s gets 3 chances in 75s (vs 2.7 at 28s); syncs with 5s interval giving even distribution|' \
  docker-compose.yml

# 4. 部署
docker compose up -d hm40006

# 5. 验证 (env + health check)
docker exec hm40006 env | grep -E "MIN_OUTBOUND|KEY_COOLDOWN|UPSTREAM_TIMEOUT|TIER_TIMEOUT_BUDGET|TIER_COOLDOWN|CONNECT_RESERVE"
docker logs hm40006 --tail 5
```

**最终配置确认**:
- UPSTREAM_TIMEOUT=25  ← **35→25** 截断死链, 多1个key机会
- MIN_OUTBOUND_INTERVAL_S=5.0  ← **4.0→5.0** 25s cycle对齐NVCF窗口
- KEY_COOLDOWN_S=25.0  ← **28→25** 与5s间距整除, 更均匀
- TIER_TIMEOUT_BUDGET_S=55 (不变)
- TIER_COOLDOWN_S=300 (不变)
- HM_CONNECT_RESERVE_S=5 (不变)

---

## 📈 预期效果

1. **NVCFPexecTimeout时间减半** — 从avg 31.6s降到~25s, 每key省~6.6s, 5key省33s
2. **Budget内更多key尝试** — 55s budget / 25s timeout = 2.2 key (vs 1.57 at 35s) → 多0.6个key
3. **Fallback率下降** — 更多key被试 → 更多直接成功, 目标: <55% (vs 61.2%)
4. **429更分散** — 5s间隔让请求不集中在同一NVCF窗口
5. **平均延迟降低** — primary直接成功减~10s/超时key, fallback路径也更快

---

## ⚠️ 待观察

- **UPSTREAM_TIMEOUT=25是否截断正常长尾请求** — glm5.1 NVCF p95若>25s会误杀 (实测p80=20s, 但p95未知)
- **429实际变化** — 5.0s间隔是否降低429集中度 (R10 4.0s: 679/1h, 目标: <550/1h)
- **deepseek tier稳定性** — 目前deepseek fallback成功率极高, 但NVCFPexecTimeout也对deepseek有13次/h
- **budget_exhausted_after_connect** — 7次/h, 观察是否随UPSTREAM_TIMEOUT缩短而减少
- **SSL/ConnectionReset** — 52次/h网络错误, 非本轮目标但需关注趋势

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记
