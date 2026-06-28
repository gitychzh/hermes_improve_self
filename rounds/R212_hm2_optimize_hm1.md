# R212: HM2→HM1 — 无变更 (全7参数均衡; 38th consecutive R162+R158 validation; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 14:11-14:22 UTC)

### Docker Logs (最近100行 error/warn扫描)
```
[14:11:29.7] [HM-ERR] tier=deepseek_hm_nv k5 SSLEOFError: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol
[14:11:29.7] [HM-SSL-RETRY] tier=deepseek_hm_nv k5 SSL error — retrying same key after 2s backoff
```
- 仅1条SSLEOFError(k5) → 自动重试成功; 其余全部[HM-SUCCESS] first-attempt (确认日志尾30行: 6/6 SUCCESS)
- 0 error/warn/panic 以外 — grep返回exit code 1 = 无匹配 = 干净系统

### Runtime Env (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=70
TIER_TIMEOUT_BUDGET_S=156
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=38
MIN_OUTBOUND_INTERVAL_S=19.2   ← R208: 19.0→19.2 (+0.2s)
HM_CONNECT_RESERVE_S=24
PROXY_TIMEOUT=300
CHARS_PER_TOKEN_ESTIMATE=3.0
```

### DB Metrics (30min / 1h / 6h / 24h segmented)
| Window | Total | 200 | Fail | ATE | 429 | Fallback | P50_success |
|--------|-------|-----|------|-----|-----|----------|-------------|
| 30min | 1198 | 1188 | 10 | 9 | 0 | 0 | — |
| 1h | 1269 | 1259 | 10 | 9 | 0 | 0 | — |
| 6h | 1966 | 1952 | 14 | 12 | 0 | 0 | 20503ms |
| 0-6h | 1966 | 1952 | 14 | 12 | 0 | 0 | 20503ms |
| 6-12h | 785 | 778 | 7 | 4 | 0 | 0 | 24631ms |
| 12-24h | 1753 | 1714 | 39 | 37 | 4 | 613 | 33917ms |

- 30min success: 1188/1198 = 99.16% (10 fail: 9×ATE全NVCFPexecTimeout + 1×NVStream_TimeoutError)
- 1h success: 1259/1269 = 99.21%
- 6h success: 1952/1966 = 99.29%
- 24h total: 4504 req, 4445=200 (98.69%), 53 ATE + 4×429 + 613 fallback (all 12-24h old-regime)
- 0-12h all windows: **0 fallback, 0 429** — 实时状态完美
- Per-key distribution even (231-247 req/key, 5-key round-robin)

### Per-Key Latency (30min)
| Key (nv_key_idx) | Reqs | P50(ms) | P95(ms) | Errors |
|-------------------|------|---------|---------|--------|
| k0 (DIRECT) | 247 | 16669 | 41342 | 0 |
| k1 (DIRECT) | 236 | 18667 | 48342 | 1 |
| k2 (PROXY→7896) | 231 | 18964 | 37146 | 0 |
| k3 (PROXY→7897) | 236 | 18771 | 40900 | 0 |
| k4 (PROXY→7899) | 238 | 18516 | 39760 | 0 |

- P50 range: 16.7-18.7s (tight, all keys consistent)
- P95 range: 37.1-48.3s
- k1 (DIRECT) 1 error = NVStream_TimeoutError (single event)

### Error Detail JSONL (最近3条ATE事件)
所有ATE事件均为NVCF PexecTimeout server-side, kimi num_attempts=0 (Pitfall #41):
- `d5a65afe`: deepseek 5 key attempts, elapsed=155.7s; kimi 0→no budget left
- `ada77d8a`: deepseek 5 key attempts, elapsed=152.9s; kimi 0
- `6bf209ab`: deepseek 6 key attempts, elapsed=151.2s; kimi 0; **含1次 budget_exhausted_after_connect k5 (849ms)** — CONNECT_RESERVE=24s已覆盖849ms, 但NVCFPexecTimeout风暴下k5连接时间被计入budget

### 24h Failure Path Latency (by status)
| Status | Count | Avg(ms) | Min(ms) | Max(ms) |
|--------|-------|---------|---------|---------|
| 502 | 56 | 123371 | 6827 | 166774 |
| 429 | 4 | 161389 | 138762 | 189745 |

### 最近10条请求延迟 (实时)
```
k4→200 11347ms | k3→200 21643ms | k2→200 9545ms | k1→200 60745ms | k0→200 13888ms |
k4→200 45711ms | k3→200 11099ms | k2→200 31390ms | k1→200 11890ms | k0→200 18483ms
```
平均~21.7s, 全部200成功, 0 fallback, RR counter 完美轮转(k0→k4→k3→k2→k1→k0→k4→k3→k2→k1)

## 🎯 优化分析

### 参数均衡评估 (7参数, 全均衡)
| Parameter | Value | Status | Reason |
|-----------|-------|--------|--------|
| UPSTREAM_TIMEOUT | 70 | ✅ 不动 | P95=44.2s << 70s. 减少无法阻止NVCF server-side ATE (Pitfall #43). 所有key p95均低于70s |
| TIER_TIMEOUT_BUDGET_S | 156 | ✅ 不动 | 2×70=140, remaining=16s > 10s threshold (Pitfall #23). R154已证实增加budget不减少ATE (diminishing returns) |
| KEY_COOLDOWN_S | 38 | ✅ 不动 | KEY=TIER=38 invariant holds (Pitfall #44). 0 429s确认无需要提高 |
| TIER_COOLDOWN_S | 38 | ✅ 不动 | 与KEY对齐=38. 当前值为最优 |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | ✅ 不动 | R208刚改为19.2(+0.2s), 需要更多验证时间 (<6h). 0 back-to-back RR counter完美 |
| HM_CONNECT_RESERVE_S | 24 | ✅ 不动 | budget_exhausted_after_connect仅1次(k5, 849ms << 24s). 不做过度优化 |
| PROXY_TIMEOUT | 300 | ✅ 不动 | 无proxy层超时 |

### ATE事件特征
所有9+12个ATE事件均为NVCF PexecTimeout server-side, kimi fallback tier num_attempts=0 (Pitfall #41). 深层次原因: deepseek tier的NVCFPexecTimeout风暴消耗全部budget, kimi没有机会尝试。这是NVCF server-side问题, proxy配置无法解决(R154已确认budget增加<=10s threshold后ATE不减)。接受此现实。

### 稳定性指标
- 30min 99.16% (略低于R211的99.17%, 本质一致)
- 1h 99.21% (vs R211: 99.21%, 完全一致)
- 6h 99.29% (vs R211: 99.29%, 完全一致)
- 0-12h: **0 fallback + 0 429** — 实时状态完全健康
- Per-key P50 16.7-18.7s, P95 37.1-48.3s — 稳定低延迟
- RR counter: 完美轮转, 0 back-to-back
- 38th consecutive R162+R158 validation — R162的KEY_COOLDOWN=38和R158的UPSTREAM_TIMEOUT=70已经被验证38轮, 稳定性之最

### 为什么是no-change round (不是over-optimization)
R208的MIN_OUTBOUND_INTERVAL_S 19.0→19.2刚变更(<6h), 尚未充分验证。其余6个参数全部在最优均衡点。降低任何一个参数会打破当前平衡而不会改善任何metric。**稳定性IS最优状态** — 这是R162以来第38个连续验证。

## 📈 预期效果

| Metric | R211 (前轮) | R212 (本轮) | 趋势 |
|--------|------------|------------|------|
| 30min success | 99.17% (1197/1207) | 99.16% (1188/1198) | → 持平 |
| 1h success | 99.21% (1258/1268) | 99.21% (1259/1269) | → 持平 |
| 6h success | 99.29% (1957/1971) | 99.29% (1952/1966) | → 持平 |
| 0-12h fallback | 0 | 0 | ✅ 完美 |
| 0-12h 429 | 0 | 0 | ✅ 完美 |
| Per-key P50 | 16.7-18.7s | 16.7-18.7s | → 持平 |

## ⚖️ 评判标准

- ✅ **更少报错**: 30min仅10 errors (9 ATE NVCF server-side + 1 NVStream_TimeoutError), 0 429, 0 fallback — 代理层零自伤错误
- ✅ **更快请求**: P50=18.2s, P95=44.2s — 稳定低延迟
- ✅ **超低延迟**: 所有key P50<19s, P95<49s — 全部在UPSTREAM_TIMEOUT=70s安全范围内
- ✅ **稳定优先**: 38th consecutive R162+R158 validation — 稳定性之巅; R208 MIN_OUTBOUND=19.2 需更多验证; 不做过度优化; 全7参数均衡
- ✅ **铁律**: 仅分析HM1数据, 绝不修改HM2本地配置; 所有变更仅作用于HM1

## ⏳ 轮到HM1优化HM2