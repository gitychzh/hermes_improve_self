# R249: HM2→HM1 — 无变更 (74th no-change validation; 全7参数均衡; 30min 98.80% 1 NVStream_IncompleteRead k3; 0 429 0 fallback; 0 ATE across ALL windows; 24h 0-24h=0fb+0 429; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 20:38-21:08 UTC)

### Docker Logs (最近100行)
- `[20:59:50.7] [HM-ERR] tier=deepseek_hm_nv k5 SSLEOFError: [SSL: UNEXPECTED_EOF_WHILE_READING]` — auto-retried same key after 2s backoff
- `[20:59:50.7] [HM-SSL-RETRY] tier=deepseek_hm_nv k5 SSL error — retrying same key after 2s backoff`
- 仅1条SSLEOFError (k5, 20:59:50) → 自动重试成功
- 其余日志全部为 [HM-SUCCESS] 或 [HM-RR-COUNTER] 正常轮询
- 0 HM-TIER-BUDGET threshold breaks, 0 fallback triggers

### Config Snapshot (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=70
TIER_TIMEOUT_BUDGET_S=156
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=38
MIN_OUTBOUND_INTERVAL_S=19.2
HM_CONNECT_RESERVE_S=24
PROXY_TIMEOUT=300
CHARS_PER_TOKEN_ESTIMATE=3.0
```

### DB Metrics (30min, 20:38-21:08 UTC, deepseek_hm_nv)
| Metric | Value |
|--------|-------|
| Total requests | 83 |
| Success (status=200) | 82 (98.80%) |
| all_tiers_exhausted | 0 |
| NVStream_IncompleteRead | 1 (k3) |
| 429 errors | 0 |
| Fallback | 0 |
| P50 latency | 18,645ms (18.6s) |
| P95 latency | 40,319ms (40.3s) |

### Per-Key Distribution (30min, deepseek_hm_nv)
| Key | Reqs | Avg | P95 |
|-----|------|-----|-----|
| k0 | 18 | 17.6s | 26.5s |
| k1 | 16 | 23.0s | 48.0s |
| k2 | 18 | 25.8s | 68.6s |
| k3 | 17 | 22.7s | 40.7s |
| k4 | 15 | 17.3s | 25.2s |
| **Even distribution** (15-18 req/key, RR counter healthy) |

### Extended Windows
| Window | Total | Success | ATE | 429 | Fallback | Rate |
|--------|-------|---------|-----|-----|----------|------|
| 30min | 83 | 82 | 0 | 0 | 0 | 98.80% |
| 1h | 143 | 142 | 0 | 0 | 0 | 99.30% |
| 3h | 396 | 395 | 0 | 0 | 0 | 99.75% |
| 6h | 739 | 738 | 0 | 0 | 0 | 99.86% |
| 24h (0-6h) | 825 | 824 | 0 | 0 | 0 | 99.88% |
| 24h (6-12h) | 1675 | 1673 | 0 | 0 | 0 | 99.88% |
| 24h (12-24h) | 3394 | 3387 | 0 | 0 | 0 | 99.79% |

### Error Detail JSONL
- 30min window: 1 error — NVStream_IncompleteRead on k3 (request `e787624b`, 22,616ms, 20:41:32 UTC)
- 6h window: 1 error total (same NVStream_IncompleteRead) — zero additional errors
- 24h: zero ATE across ALL windows (0-6h, 6-12h, 12-24h all show 0 ATE)

## 🎯 优化分析

### 参数评估表
| Parameter | Current | Evaluation | Action |
|-----------|---------|------------|--------|
| UPSTREAM_TIMEOUT | 70 | All key P95 < 70s (max k2=68.6s); success-path safe; 0 timeout triggers | 无调整 |
| TIER_TIMEOUT_BUDGET_S | 156 | 2×70=140, remaining=16s > 5s threshold; 0 ATE across ALL windows; budget fully sufficient | 无调整 |
| KEY_COOLDOWN_S | 38 | KEY=TIER=38 (零gap, Pitfall #44 invariant); 0 429 across all windows; R162 validated 74th time | 无调整 |
| TIER_COOLDOWN_S | 38 | KEY≥TIER invariant holds (38=38); 0 tier-cooldown triggers; optimal | 无调整 |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | 5×19.2=96s cycle >> KEY=38s; ~83 req/30min = low traffic; 0 429s | 无调整 |
| HM_CONNECT_RESERVE_S | 24 | 24s covers all key SOCKS5+SSL setup; 0 budget_exhausted_after_connect; sufficient | 无调整 |
| PROXY_TIMEOUT | 300 | Internal proxy timeout — not relevant to NVCF tier chain | 无调整 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | Token estimation — no impact on request success/failure | 无调整 |

### 瓶颈分析
- **Zero ATE across ALL windows (30min→24h)**: 这是R249最显著的特征。R248仍有1条SSLEOFError + 2条NVStream (共3条error)，且R248的30min有16 ATE。R249的30min窗口为0 ATE — NVCF PexecTimeout风暴未进入当前窗口。实际请求量偏低(83 req/30min vs R248的1043)，低流量窗口更易保持零错误。
- **1 NVStream_IncompleteRead (k3)**: NVCF网络层读取不完整 — server-side, 22.6s恢复正常。这是NVCF网络层偶发错误。
- **1 SSLEOFError (k5)**: SSL层连接错误，自动重试成功 — 不是配置问题
- **Zero 429 + Zero fallback + Zero ATE across ALL windows**: 全7参数处于均衡点。74th consecutive R162+R158 no-change validation — 稳定性高原延续。
- **低流量窗口特性**: 83 req/30min vs capacity ~96 req/30min (19.2s×5 keys) — 86% utilization in a low-traffic period

## 🔧 变更执行
**无变更** — 所有7个参数均处于均衡点，无需调整。

### 铁律验证
- ✅ 只改HM1, 绝不改HM2本地 — 本次无变更, 铁律自然满足
- ✅ KEY≥TIER invariant (38=38) — 保持
- ✅ Budget math: 2×70=140, remaining=16s > 5s — 安全
- ✅ Zero ATE, zero 429, zero fallback across all windows — 最优状态

## 📈 预期效果
R249延续R248的稳定性高原 — 74th consecutive R162+R158 no-change validation。预期:
- 30min success rate: ~98-100% (取决于NVCF网络状态)
- Zero 429, zero fallback — 持续
- P50: ~18s, P95: ~40-55s — 稳定
- ATE事件: 0 ATE在近期窗口 — NVCF PexecTimeout风暴已平息

## ⚖️ 评判标准
- **更少报错**: ✅ 0 429, 0 fallback, 0 ATE — 零报错(1 NVStream server-side)
- **更快请求**: ✅ P50=18.6s — 低延迟稳定
- **超低延迟**: ✅ P95=40.3s — 所有key p95 < UPSTREAM_TIMEOUT=70s
- **稳定优先**: ✅ 74th consecutive R162+R158 validation — 稳定性高原完全确认
- **铁律**: ✅ 只改HM1不改HM2 — 自然满足

## ⏳ 轮到HM1优化HM2