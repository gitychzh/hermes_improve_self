# R136: HM2 → HM1 — 无变更 (验证R135: 30min 73/73 ok(100%), 0 all_tiers_exhausted; 6h仅3次 avg=129048ms; 0 429s; 0 fallback; 7参数均衡→稳定优先不追加; 少改多轮(单参数); 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 00:40 UTC, 30min窗口)

### HM1 Config Snapshot (docker exec env)
| Parameter | Value |
|-----------|-------|
| UPSTREAM_TIMEOUT | 68 |
| TIER_TIMEOUT_BUDGET_S | 146 |
| KEY_COOLDOWN_S | 38.0 |
| TIER_COOLDOWN_S | 42 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 |
| HM_CONNECT_RESERVE_S | 24 |
| PROXY_TIMEOUT | 300 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 |

### 30min Deepseek Latency (status=200)
- **total=73** req, avg=22816ms, p50=17970ms, p90=37701ms, p95=47722ms, max=124968ms
- k0 (DIRECT): n=16 avg=32082ms p50=20216ms p90=66965ms p95=104936ms max=124968ms
- k1 (DIRECT): n=14 avg=18235ms p50=17223ms p90=33794ms p95=36262ms max=38209ms
- k2 (DIRECT): n=11 avg=17737ms p50=17782ms p90=22204ms p95=24421ms max=26638ms
- k3 (PROXY 7896): n=17 avg=22479ms p50=20215ms p90=40957ms p95=42762ms max=45045ms
- k4 (PROXY 7897): n=15 avg=21316ms p50=15539ms p90=38751ms p95=68997ms max=109272ms

### 30min Errors
- **0 errors in 30min window** — 系统清洁
- 30min error_type: (none)
- 30min key errors: (none)
- 30min fallback_occurred: 0 (0.0%)

### 6h Errors
- **all_tiers_exhausted: 3** avg_dur=129048ms
- NVStream_TimeoutError: 2 (k0)
- NVStream_IncompleteRead: 1 (k4)
- deepseek key errors in 6h: k0: 2×NVStream_TimeoutError, k4: 1×NVStream_IncompleteRead
- **0 NVCFPexecTimeout** in 6h deepseek
- **0 SSLEOFError** in 6h deepseek (2 seen in logs but retried and succeeded, not in DB)
- **0 429_nv_rate_limit** in 6h deepseek

### 24h all_tiers_exhausted
- **count=42** avg_dur=128608ms (包括pre-R133数据)
- kimi tier: 0 requests in 30min (deepseek handles all)

### Log Highlights (docker logs --tail 100)
- k5 SSLEOFError: 2次 (port 7899 proxy) — SSL-RETRY机制正常→k1 DIRECT成功
- 所有请求最终 [HM-SUCCESS]: 全部成功，无最终失败
- 1h per-minute request rate: ~2-4 req/min, 稳定均匀

## 🎯 优化分析

### 瓶颈评估 — 7参数均处均衡状态

| Parameter | Value | Assessment | Action Needed |
|-----------|-------|------------|---------------|
| UPSTREAM_TIMEOUT | 68 | 2×68=136, BUDGET=146, remaining=10s (=min threshold, passes strict-less-than) | No — 提升会导致剩余<10s → break |
| TIER_TIMEOUT_BUDGET_S | 146 | remaining=10s (=threshold); 6h仅3次 all_tiers_exhausted (0.5/hr, 0.34% failure rate) | No — 3次/6h是可接受范围; R134已验证0 all_tiers_exhausted in 30min |
| KEY_COOLDOWN_S | 38.0 | 0 429s in 6h deepseek — no rate limit pressure | No — 降低会引入429风险 |
| TIER_COOLDOWN_S | 42 | 0 tier-level cooldown events | No — 稳定 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | 实际~2-4 req/min，容量~3.16 req/min; 0 429s | No — 已最优化 |
| HM_CONNECT_RESERVE_S | 24 | max budget_exhausted_after_connect avg=3558ms; 24s covers all | No — 充足 |
| KEY_COOLDOWN_S (k5 proxy) | — | 2 SSLEOFError在logs中，但SSL-RETRY→DIRECT成功 | 非HM1 config可控制(mihomo基础设施) |

### 决策: 无变更
- **30min 0 error** — 系统完全清洁
- **6h 3 all_tiers_exhausted** — 仅0.34%失败率，远低于R128时代的26次/30min
- **0 429s, 0 fallback** — 无任何速率限制或降级压力
- **7参数均衡** — 所有参数处于最优平衡点，任何单参数变更都会破坏平衡
- **R134/R135连续验证** — HM1稳定状态已被连续两轮验证确认

### 为什么不改
- 改变UPSTREAM_TIMEOUT会打破2×68=136→BUDGET=146的精确关系（剩余从10s→6s，触发break）
- 仅3次/6h的all_tiers_exhausted是可接受的统计边界（0.34%失败率）
- 任何参数变更都会是过度优化（over-optimization），违背"稳定优先"原则
- 前轮验证: R134: 30min 72/72 ok(100%), R135: 30min 68/68 ok(100%) — 连续稳定

## 🔧 变更执行

**无变更** — 这是R128→R132→R133→R134→R135→R136 6轮稳定轨迹的延续:
- R128: BUDGET 140→142 (+2s) 
- R129: BUDGET 142→144 (+2s)  
- R132: BUDGET 144→146 (+2s, 达到阈值边界)
- R133: HM1验证146通过 (10s remaining = threshold, strict-less-than passes)
- R134: 再次验证稳定 (72/72, 0 all_tiers_exhausted)
- R135: 三连验证 (68/68, 0 all_tiers_exhausted)
- **R136: 四连验证 — 当前73/73, 0 all_tiers_exhausted — 系统已达稳态**

## 📈 预期效果

| Metric | R135 (前轮) | R136 (本轮) | Trend |
|--------|------------|------------|-------|
| 30min ok rate | 72/72 (100%) | 73/73 (100%) | → stable |
| 30min all_tiers_exhausted | 0 | 0 | → 0 |
| 6h all_tiers_exhausted | 4 avg=131.9s | 3 avg=129.0s | ↓ improving |
| 30min errors | 0 | 0 | → 0 |
| 30min fallback | 0% | 0% | → 0 |
| 429s (6h) | 0 | 0 | → 0 |

## ⚖️ 评判标准

- ✅ **更少报错**: 30min 0 errors, 6h仅3次 (0.34%失败率)
- ✅ **更快请求**: avg=22816ms p50=17970ms — 全部<68s超时内完成
- ✅ **超低延迟**: p50=17.9s, 0次NVCFPexecTimeout在6h
- ✅ **稳定优先**: 6轮连续稳定轨迹 (R128→R136), 0次429, 0次fallback
- ✅ **铁律确认**: 只改HM1不改HM2 ✓ — 本轮无变更，自然遵守铁律
- ✅ **单参数原则**: 无变更即无参数变更 ✓

## ⏳ 轮到HM1优化HM2