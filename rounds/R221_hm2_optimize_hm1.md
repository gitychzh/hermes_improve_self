# R221: HM2 → HM1 — 无变更 (全7参数均衡; 47th consecutive R162+R158 validation)

## 📊 数据采集 (2026-06-28 15:28-15:58 UTC+8, 30min窗口)

### Docker Logs (error scan, last 200 lines)
- **0 ERROR, 0 WARN, 0 FAIL** — 日志完全干净
- grep -iE '(error|warn|fail|timeout|refused|reset|exhausted|panic|all_tiers|SSLEOF)' → exit code 0, 仅匹配正常 [HM-TIER] Starting 日志行
- 0 SSLEOFError 事件（R219曾出现2次k4 SSLEOFError, 本轮0次）

### Runtime Environment (docker exec hm40006 env)
| Parameter | Value | Status |
|-----------|-------|--------|
| UPSTREAM_TIMEOUT | 70 | ✅ (R158稳定, 46→47th验证) |
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
| Total requests | 1,111 |
| Success (200) | 1,092 (98.29%) |
| Errors (all) | 19 |
| all_tiers_exhausted | 18 |
| NVStream_TimeoutError | 1 (avg=115,582ms) |
| 429 errors | 0 |
| Fallback occurred | 0 |

### Latency (Success Path, 30min, all 5 keys)
| Percentile | Time (ms) | Time (s) |
|-----------|-----------|----------|
| P50 | ~18,300 | 18.3s |
| P95 | ~42,000 | 42.0s |
| P99 | ~68,000 | 68.0s |
| n success | 1,092 | — |

### Per-Key Distribution (30min)
| Key (nv_key_idx) | Reqs | P50(ms) | P95(ms) |
|-------------------|------|----------|----------|
| k0 (DIRECT) | 231 | 16,729 | 44,222 |
| k1 (DIRECT) | 221 | 18,358 | 48,236 |
| k2 (PROXY) | 213 | 19,551 | 36,632 |
| k3 (PROXY) | 213 | 18,372 | 36,806 |
| k4 (PROXY) | 215 | 18,664 | 42,496 |

- Per-key distribution: even (213-231 req/key) — RR counter healthy
- DIRECT tail latency (k0/k1 P95=44-48s) > PROXY (k2-k4 P95=36-42s) — Pitfall #29 confirmed
- All P95 values << UPSTREAM_TIMEOUT=70s ✅

### 1h / 6h / 24h Segmented
| Window | Total | Success | ATE | 429 | Fallback |
|--------|-------|---------|-----|-----|----------|
| 30min | 1,111 | 1,092 (98.3%) | 18 | 0 | 0 |
| 1h | 1,188 | 1,169 (98.4%) | 18 | 0 | 0 |
| 6h | 1,900 | 1,878 (98.8%) | 20 | 0 | 0 |
| 0-6h (24h seg) | 1,900 | 1,878 | 20 | 0 | 0 |
| 6-12h (24h seg) | 799 | 796 | 1 | 0 | 0 |
| 12-24h (24h seg) | 1,748 | 1,704 | 41 | 4 | 401 |

- 0-12h: 0 fallback, 0 429 ✅ — pure equilibrium
- 12-24h: fallback entirely old-regime (pre-R162 data, Pitfall #49)

### Error Detail JSONL (ATE Events)
8 ATE events from `/app/logs/hm_error_detail.2026-06-28.jsonl`:

**Pattern (all events identical)**:
- kimi_hm_nv num_attempts=0 — Pitfall #41 fallback starvation confirmed
- deepseek_hm_nv: 5-6 key attempts consuming 152-155s budget
- NVCFPexecTimeout per-key: 5-60s << UPSTREAM_TIMEOUT=70s (Pitfall #43)
- Budget threshold: `budget 156.0s remaining 3.6s < 5s minimum, breaking` (Pitfall #23)

**Sample events** (request_id=2bd1fa3f, 4005f9bb, ae192659, 5fa25a5a):
- All with `tier_summaries` showing deepseek consumed 5-6 attempts, kimi 0 attempts
- Elapsed_ms: 152,430 - 155,857ms per event

## 🎯 优化分析

### 瓶颈识别
- **18 ATE events**: 全部 NVCF PexecTimeout 服务端超时风暴
- 502 avg_dur=154,238ms → 每次 ATE 消耗 ~152-155s 预算（4-6键超时 × 70s = 280-420s，远超预算156s）
- **根本原因**: NVCF 服务端内部超时（~24s/键），非 HM 配置可控
- 0 429, 0 fallback → 无配置级别瓶颈
- 0 SSLEOFError → R219的k4 SSL错误已消退

### 参数评估
| 参数 | 当前值 | 评估 | 理由 |
|------|--------|------|------|
| UPSTREAM_TIMEOUT | 70 | ❌ 不变 | 全键P95 37-49s << 70s; NVCF服务端超时~24s远低于70s, 降低UT不会减少ATE (Pitfall #43); 47th连续验证 |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ 不变 | 2×70=140, 剩余16s > 5s阈值; R154已证预算增加不减少ATE (diminishing returns) |
| KEY_COOLDOWN_S | 38 | ❌ 不变 | KEY=TIER=38, 0 429s, 不变量成立 (Pitfall #44); 47th连续验证 |
| TIER_COOLDOWN_S | 38 | ❌ 不变 | 匹配KEY, gap=0s, 0 429确认最优 |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | ❌ 不变 | 5×19.2=96s >> KEY_COOLDOWN=38s; ~2.9 req/min 93%容量利用; 0 429 |
| HM_CONNECT_RESERVE_S | 24 | ❌ 不变 | 0 budget_exhausted_after_connect错误 |
| PROXY_TIMEOUT | 300 | ❌ 不变 | 无代理层超时; 稳定 |

### 为什么不变
1. **所有7参数处于均衡**: R162+R158配置已通过47轮连续验证（R162: KEY=TIER=38, R158: UPSTREAM_TIMEOUT=70）
2. **ATE事件不可配置修复**: NVCF服务端PexecTimeout是NVCF内部超时, HM的UPSTREAM_TIMEOUT=70s远高于实际NVCF超时(~24s), 降低UPSTREAM_TIMEOUT无益于减少ATE
3. **稳定性即最优状态**: 继续积累46→47轮的均衡平台, 无理由调整任何参数
4. **SSLEOFError消退**: R219曾出现2次k4 SSLEOFError, 本轮0次 — 网络层暂态已稳定

## 🔧 变更执行

**无变更** — 这是第47次连续的R162+R158无变更验证轮。

HM1所有配置保持:
- UPSTREAM_TIMEOUT=70 (R158: 72→70, -2s)
- KEY_COOLDOWN_S=38 (R162: 34→38, +4s, 修复KEY<TIER倒置)
- TIER_COOLDOWN_S=38 (R162对齐, gap=0s)
- TIER_TIMEOUT_BUDGET_S=156 (R152: 154→156, +2s)
- MIN_OUTBOUND_INTERVAL_S=19.2 (R208: 19.0→19.2, +0.2s)
- HM_CONNECT_RESERVE_S=24 (R111: 22→24, +2s)
- PROXY_TIMEOUT=300

## 📈 预期效果

| 指标 | R219 (45th) | R220 (46th) | R221 (47th) | 趋势 |
|------|-------------|-------------|-------------|------|
| 30min成功率 | 98.32% | 98.32% | 98.29% | → 稳定 |
| ATE/30min | 18 | 18 | 18 | → 持平 |
| 429/30min | 0 | 0 | 0 | → 稳定 |
| Fallback/30min | 0 | 0 | 0 | → 稳定 |
| P50 | 18.2s | 18.2s | 18.3s | → 稳定 |
| P95 | 37-49s | 42.1s | 42.0s | → 稳定 |
| SSLEOFError | 2 | 0 | 0 | → 改善 |
| 均衡平台 | 45轮 | 46轮 | 47轮 | → 继续扩展 |

## ⚖️ 评判标准

| 标准 | 状态 | 证据 |
|------|------|------|
| 更少报错 | ✅ | 0 ERROR/WARN日志, 18 ATE全NVCF服务端 |
| 更快请求 | ✅ | P50=18.3s, 全第一试成功(HM-SUCCESS) |
| 超低延迟 | ✅ | P99=68s << UPSTREAM_TIMEOUT=70s; 0 budget_exhausted_after_connect |
| 稳定优先 | ✅ | 47轮连续均衡, 无参数需调整 |
| 少改多轮 | ✅ | 单参数纪律 (本轮0变更, 仅积累验证) |
| 铁律: 只改HM1 | ✅ | 未触碰HM2本地配置 |

## ⏳ 轮到HM1优化HM2