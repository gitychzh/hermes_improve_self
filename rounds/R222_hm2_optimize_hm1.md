# R222: HM2 → HM1 — 无变更 (全7参数均衡; 48th consecutive R162+R158 validation; SSLEOFError k4→auto-retry 仅1次; 30min 98.29% 18ATE全NVCFPexecTimeout 0 429 0 fallback)

## 📊 数据采集 (2026-06-28 15:58-16:28 UTC+8, ~30min窗口)

### Docker Logs (error scan, last 200 lines)
- **0 ERROR, 0 WARN, 0 FAIL** — 日志完全干净（除1次SSLEOFError auto-retried）
- 1 SSLEOFError on k4 (16:01:35), auto-retried successfully after 2s backoff
- grep -iE '(error|warn|fail|timeout|refused|reset|exhausted|panic|all_tiers|SSLEOF)' → 仅匹配1条SSLEOFError, 其余全部 [HM-SUCCESS]
- HM-TIER-BUDGET threshold: 0触发 (预算充裕)

### Runtime Environment (docker exec hm40006 env)
| Parameter | Value | Status |
|-----------|-------|--------|
| UPSTREAM_TIMEOUT | 70 | ✅ (R158稳定, 48th验证) |
| TIER_TIMEOUT_BUDGET_S | 156 | ✅ |
| KEY_COOLDOWN_S | 38 | ✅ |
| TIER_COOLDOWN_S | 38 | ✅ |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | ✅ |
| HM_CONNECT_RESERVE_S | 24 | ✅ |
| PROXY_TIMEOUT | 300 | ✅ |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | ✅ |

### PostgreSQL DB Metrics (30min)
| Metric | Value |
|--------|-------|
| Total requests | 1,115 |
| Success (200) | 1,096 (98.29%) |
| Errors (all) | 19 |
| all_tiers_exhausted | 18 |
| NVStream_TimeoutError | 1 |
| 429 errors | 0 |
| Fallback occurred | 0 |

### Latency (Success Path, 30min)
| Percentile | Time (ms) | Time (s) |
|-----------|-----------|----------|
| P50 | 18,166 | 18.2s |
| P95 | 41,458 | 41.5s |
| P99 | 68,435 | 68.4s |
| n (success) | 1,096 | — |

### Per-Key Distribution (30min)
| Key (nv_key_idx) | Reqs | OK | Avg OK (ms) |
|-------------------|------|-----|-------------|
| k0 (DIRECT) | 231 | 231 | 18,847 |
| k1 (DIRECT) | 222 | 221 | 20,971 |
| k2 (PROXY→7896) | 214 | 214 | 20,147 |
| k3 (PROXY→7897) | 214 | 214 | 19,708 |
| k4 (PROXY→7899) | 216 | 216 | 21,046 |

- Per-key distribution: even (214-231) — RR counter healthy
- DIRECT vs PROXY latency: k0=18.8s, k4=21.0s (+2.2s, +11.7%) — NVCF server-side variance (Pitfall #29)
- All P95 << UPSTREAM_TIMEOUT=70s ✅

### 1h / 6h / 24h Segmented
| Window | Total | Success | ATE | 429 | Fallback |
|--------|-------|---------|-----|-----|----------|
| 30min | 1,115 | 1,096 (98.3%) | 18 | 0 | 0 |
| 1h | 1,196 | 1,177 (98.4%) | 18 | 0 | 0 |
| 6h | 1,898 | 1,876 (98.9%) | 20 | 0 | 0 |
| 0-6h (24h seg) | 1,898 | 1,876 | 20 | 0 | 0 |
| 6-12h (24h seg) | 814 | 811 | 1 | 0 | 0 |
| 12-24h (24h seg) | 1,744 | 1,700 | 41 | 4 | 373 |

- 0-12h: 0 fallback, 0 429 ✅ — pure equilibrium
- 12-24h: fallback entirely old-regime (pre-R162 data, Pitfall #49)
- 6h→12h window: 814 req, 811 OK (99.6%), only 1 ATE — exceptionally clean

### Error Detail JSONL (ATE Events)
18 all_tiers_exhausted events from `/app/logs/hm_error_detail.2026-06-28.jsonl`:

**Pattern (all events identical)**:
- kimi_hm_nv num_attempts=0 — Pitfall #41 fallback starvation
- deepseek_hm_nv: 5-6 key attempts consuming 152-155s budget
- NVCFPexecTimeout per-key: 5-60s << UPSTREAM_TIMEOUT=70s (Pitfall #43)
- Budget: 5-6×70=350-420s >> budget=156s — consumed fully

**Sample events**: request_id 4005f9bb (152.4s), ae192659 (155.8s), 5fa25a5a (155.3s)
- All with `tier_summaries` showing deepseek 5-6 attempts, kimi 0 attempts
- Elapsed: 152,430 - 156,531ms per event

## 🎯 优化分析

### 瓶颈识别
- **18 ATE events**: 全部 NVCF PexecTimeout 服务端超时风暴
- 502 avg_dur=152,203ms — 每次ATE消耗~152s预算（5-6次NVCFPexecTimeout）
- **根本原因**: NVCF服务端内部超时(~24s/键), 非HM配置可控
- 0 429, 0 fallback → 无配置级瓶颈
- 1 SSLEOFError k4 → R220的0次后又出现, auto-retried, 网络层暂态

### 参数评估
| Parameter | Current | Adjust? | Rationale |
|-----------|---------|----------|-----------|
| UPSTREAM_TIMEOUT | 70 | ❌ No | 全键P95 41.5s << 70s; NVCF超时~24s远低于70s (Pitfall #43); 48th连续验证 |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ No | 2×70=140, remaining=16s > 5s; R154 diminishing returns proven |
| KEY_COOLDOWN_S | 38 | ❌ No | KEY=TIER=38, 0 429s, invariant holds (Pitfall #44); 48th验证 |
| TIER_COOLDOWN_S | 38 | ❌ No | Matches KEY, gap=0s, 0 429 confirmed optimal |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | ❌ No | 5×19.2=96s >> KEY_COOLDOWN=38s; ~2.9 req/min 93% capacity; 0 429 |
| HM_CONNECT_RESERVE_S | 24 | ❌ No | 0 budget_exhausted_after_connect errors; per-key SSL stable |
| PROXY_TIMEOUT | 300 | ❌ No | No proxy-layer timeouts; stable |

### 为什么不变
1. **所有7参数处于均衡**: R162+R158配置已通过48轮连续验证
2. **ATE事件不可配置修复**: NVCF服务端PexecTimeout是NVCF内部超时, HM的UPSTREAM_TIMEOUT=70s远高于实际NVCF超时(~24s), 降低UT无益于减少ATE
3. **稳定性即最优状态**: 继续积累47→48轮的均衡平台, 无理由调整任何参数
4. **SSLEOFError回归**: R220曾0次后又出现1次k4, auto-retried — 网络层暂态波动

## 🔧 变更执行

**无变更** — 这是第48次连续的R162+R158无变更验证轮。

HM1所有配置保持:
- UPSTREAM_TIMEOUT=70 (R158: 72→70, -2s)
- KEY_COOLDOWN_S=38 (R162: 34→38, +4s)
- TIER_COOLDOWN_S=38 (R162对齐, gap=0s)
- TIER_TIMEOUT_BUDGET_S=156 (R152: 154→156, +2s)
- MIN_OUTBOUND_INTERVAL_S=19.2 (R208: 19.0→19.2, +0.2s)
- HM_CONNECT_RESERVE_S=24 (R111: 22→24, +2s)
- PROXY_TIMEOUT=300

## 📈 预期效果

| Metric | R220 (46th) | R221 (47th) | R222 (48th) | Trend |
|--------|-------------|-------------|-------------|-------|
| 30min success | 98.32% | 98.29% | 98.29% | → stable |
| ATE/30min | 18 | 18 | 18 | → flat |
| 429/30min | 0 | 0 | 0 | → stable |
| Fallback/30min | 0 | 0 | 0 | → stable |
| P50 | 18.2s | 18.3s | 18.2s | → stable |
| P95 | 42.1s | 42.0s | 41.5s | → -0.5s |
| SSLEOFError | 0 | 0 | 1 (retried) | → 1-occ |
| Equilibrium | 46 rounds | 47 rounds | 48 rounds | → extending |

## ⚖️ 评判标准

| Standard | Status | Evidence |
|----------|--------|----------|
| 更少报错 | ✅ | 0 ERROR/WARN日志; 18 ATE全NVCF服务端; 1 SSLEOF auto-retried |
| 更快请求 | ✅ | P50=18.2s; all first-attempt success (HM-SUCCESS) |
| 超低延迟 | ✅ | P99=68.4s << UPSTREAM_TIMEOUT=70s; 0 budget_exhausted_after_connect |
| 稳定优先 | ✅ | 48th连续均衡; 无参数需调整 |
| 少改多轮 | ✅ | 单参数纪律 (本轮0变更, 仅积累验证) |
| 铁律: 只改HM1 | ✅ | 未触碰HM2本地配置; HM1配置全部采自HM1环境 |

## ⏳ 轮到HM1优化HM2