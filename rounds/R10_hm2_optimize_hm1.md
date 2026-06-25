# R10: HM2 优化 HM1 (hm40006) — 拉开key间距缓解NVCF级限流, 提高key冷却减少无效重试

**日期**: 2026-06-25 22:20 CST
**执行者**: HM2 (opc2_uname)
**目标**: HM1 (opc_uname@100.109.153.83)
**上一轮**: R9 (HM2优化HM1: TIER_COOLDOWN=300, MIN_OUTBOUND=5.0, KEY_COOLDOWN=25, UPSTREAM_TIMEOUT=65, TIER_TIMEOUT_BUDGET=65, HM_CONNECT_RESERVE_S=5)

---

## 📊 数据采集

### 1. Docker Logs (最近100行, R9配置下 ~22:05-22:10)

```
[21:53-22:06] 约20个请求:
- glm5.1 直接成功: 16/20 (80%)
- 2 timeout failures: k1 (60s) + k2 (29s+SSL EOF)
- 1 SSL EOF: k1 SSLEOFError → k2 retry → timeout → fallback
- Fallback 到 deepseek_hm_nv: 3次成功 (~11s each)
- Fallback 到 kimi_hm_nv: 0次 (未触发)
```

**详细时间线**:
```
21:53:31 k2 → 成功 (35s)
21:56:10 k3 → 成功 (24s)  
21:56:44 k4 → 成功 (25s)
21:57:15 k5 → 成功 (19s)
21:57:34 k1 → 成功 (22s)
21:57:57 k2 → 成功 (24s)
21:58:23 k3 → 成功 (32s)
21:58:55 k4 → 成功 (50s)
21:59:52 k5 → 成功 (52s)
22:00:48 k1 → TIMEOUT (60s) → FALLBACK deepseek (12s)
22:02:03 k2 → 成功 (52s)
22:02:56 k3 → 成功 (61s)
22:03:57 k4 → 成功 (52s)
22:04:49 k5 → 成功 (47s)
22:05:37 k1 → SSLEOFError (30s) → k2 retry → TIMEOUT (29s) → FALLBACK deepseek (8s)
22:06:49 k3 → 处理中...
```

### 2. DB分析 (2小时窗口, ~22:05-22:10查询)

| 指标 | 值 |
|------|-----|
| 总请求数 | 926 |
| Primary成功 (无fallback) | 282 |
| Fallback发生 | 644 |
| **Fallback率** | **69.5%** |
| Avg primary duration | 21,607ms |
| Avg fallback duration | 36,244ms |

### 3. 错误分布 (2h)

```
429_nv_rate_limit: 655+ (所有5个key)
NVCFPexecTimeout:  500+ (glm5.1所有key)
NVCFPexecSSLEOFError: 18 (k0/k1/k2/k3)
NVCFPexecConnectionResetError: 8 (k3)
```

### 4. 环境变量 (R9部署后)

```
TIER_COOLDOWN_S=300
MIN_OUTBOUND_INTERVAL_S=5.0
KEY_COOLDOWN_S=25.0
TIER_TIMEOUT_BUDGET_S=65
UPSTREAM_TIMEOUT=65
HM_CONNECT_RESERVE_S=5
```

---

## 🩺 诊断

### 根因

**NVCF function-level rate limit 叠加高频请求** — 5个API key共享同一个GLM5.1函数ID (822231fa-d4f...), NVCF rate limit在函数级别约60s窗口。系统每8-18s一个请求(5 reqs/min)持续刷新429计数器。

**R9的TIER_COOLDOWN=300**有效阻止了全键429后的快速重试(spam),但MIN_OUTBOUND=5.0仍然太激进——每个请求5个key在25s内全部尝试, 导致429事件在地毯式出现。

### 证据链

1. **69.5% fallback率** — 644/926请求触发fallback, 是最大问题
2. **655+ 429事件** — 2小时内所有5 key击中NVCF rate limit
3. **500+ NVCFPexecTimeout** — key超时与429交替出现, 双重失败
4. **18 SSLEOFError** — 网络层错误, 非关键但增加延迟
5. **avg_prim 21.6s** — primary tier本身就很慢, 35s-52s常见
6. **avg_fb 36.2s** — 走过fallback路径的请求平均延迟比primary更高

### 改善点 (vs R9)

| 指标 | R9 (5.0/25/65) | R10 (7.0/30/70) | 变化 |
|------|-----------------|------------------|------|
| MIN_OUTBOUND | 5.0s | **7.0s** | ⬆️ 拉开key间距 |
| KEY_COOLDOWN | 25.0s | **30.0s** | ⬆️ 更长的429后冷却 |
| TIER_TIMEOUT_BUDGET | 65s | **70s** | ⬆️ 更多预算避免过早fallback |
| Key尝试总耗时 | 25s | **35s** | ⬆️ 更少同时429 |
| GLOBAL-COOLDOWN触发 | 每25s | 每15-18s | ⬇️ 更少触发 |

---

## 🔧 优化方案

**策略**: 3个小参数调整 (不碰TIER_COOLDOWN=300/UPSTREAM_TIMEOUT=65/HM_CONNECT_RESERVE=5)。目标: slow down key pacing, 减少NVCF函数级别的同时429.

| # | 变更 | Before | After | 理由 |
|---|------|--------|-------|------|
| 1 | `MIN_OUTBOUND_INTERVAL_S` | 5.0 | **7.0** | 5 key × 7s = 35s total cycle, 对比之前25s。拉开让NVCF rate limit窗口(60s)有更多"冷却"时间 |
| 2 | `KEY_COOLDOWN_S` | 25.0 | **30.0** | 当429命中, key冷却至上限(30s curcap)。更少重试次数, 更少的429激增 |
| 3 | `TIER_TIMEOUT_BUDGET_S` | 65 | **70** | 给primary多5s预算。避免预算用完太早(如21:53-22:06中60s超时→4.7s剩余→fallback的场景) |

**铁律**: 只改HM1配置, 绝不改HM2本地环境. 所有修改仅在HM1机器上的docker-compose.yml中执行.

**为什么不是更大改动**:
- TIER_COOLDOWN=300 已经正确(匹配NVCF ~300s rate limit)
- UPSTREAM_TIMEOUT=65 已经够用(比之前的70s更快, 但仍有足够超时)
- HM_CONNECT_RESERVE_S=5 已经足够(SOCKS5连接+SSL握手)
- 激进改动会引入新问题, 小步调整让观察更清晰

---

## ✅ 执行记录

```bash
# 1. 备份
ssh -p 222 opc_uname@100.109.153.83
cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R10

# 2. 参数修改 (3项)
cd /opt/cc-infra
sed -i \
  -e 's/TIER_TIMEOUT_BUDGET_S: "65"/TIER_TIMEOUT_BUDGET_S: "70"/' \
  -e 's/MIN_OUTBOUND_INTERVAL_S: "5.0"/MIN_OUTBOUND_INTERVAL_S: "7.0"/' \
  -e 's/KEY_COOLDOWN_S: "25.0"/KEY_COOLDOWN_S: "30.0"/' \
  docker-compose.yml

# 3. 部署
docker compose up -d hm40006

# 4. 验证 (env + health check)
docker exec hm40006 env | grep -E "MIN_OUTBOUND|KEY_COOLDOWN|TIER_TIMEOUT_BUDGET|UPSTREAM_TIMEOUT|RESERVE"
docker logs hm40006 --tail 10
```

**最终配置确认**:
- MIN_OUTBOUND_INTERVAL_S=7.0  ← **5.0→7.0** 拉开key间距
- KEY_COOLDOWN_S=30.0  ← **25→30** 达到代码上限
- TIER_TIMEOUT_BUDGET_S=70  ← **65→70** 更多预算
- TIER_COOLDOWN_S=300 (不变)
- UPSTREAM_TIMEOUT=65 (不变)
- HM_CONNECT_RESERVE_S=5 (不变)

---

## 📈 预期效果

1. **Fallback率降低** — 7s key间距让35s cycle比对25s, 429更分散
2. **更少同时429** — 5个key在更长的时间窗口中尝试, NVCF rate limit计数器有时间恢复
3. **GLM5.1直接成功率提升** — 70s预算给primary更多时间等待NVCF rate limit过去
4. **Deepseek fallback更稳定** — 当glm5.1失败, deepseek/kimi接盘, 不额外压垮它们
5. **超时减少** — 30s key冷却(上限)让key在429后更长时间静默, 重试更少

---

## ⚠️ 待观察

- **429实际变化** — 7.0s间隔是否能显著降低429事件数 (R9 5.0s: 655/2h, 目标: <400/2h)
- **NVCF GLM5.1函数**: 是否可换到其他NVCF部署的glm5.1函数(不同function_id, 不同rate limit窗口)
- **Deepseek/kimi 429**: 如果glm5.1永远失效, deepseek/kimi的rate limit也会被耗尽
- **请求频率控制**: 上游(HM1 cron job)以每分钟0.3-0.5次的速度发包, 这是root cause。降低cron频率可大幅减少429
- **SSL错误分布**: k1 SSLEOFError + ConnectionReset, 观察是否随着间距调整改善

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记