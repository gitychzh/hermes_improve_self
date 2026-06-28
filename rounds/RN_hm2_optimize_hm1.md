# R185: HM2 → HM1 — 无变更 (全7参数均衡; 30min 73/73=100% 0ATE 0 429 0 fallback; 1h 139/139=100%; 6h 99.88% 1×502other 0 ATE 0 429 0 fallback; 24h 98.53% 44ATE全NVCF 4×429 272fallback全旧regime; 第19次R162验证+第19次R158验证; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 09:00 UTC, 30min/1h/6h/24h)

### Config Snapshot (HM1 env确认)
| Parameter | Value | Status |
|-----------|-------|--------|
| UPSTREAM_TIMEOUT | 70 | ✅ R158 (18th validation) |
| TIER_TIMEOUT_BUDGET_S | 156 | ✅ R152 |
| KEY_COOLDOWN_S | 38 | ✅ R162 (19th validation) |
| TIER_COOLDOWN_S | 38 | ✅ R156/R162 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ✅ R119 |
| HM_CONNECT_RESERVE_S | 24 | ✅ R111 |
| PROXY_TIMEOUT | 300 | ✅ stable |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | ✅ stable |

### Docker Logs (最近200行)
- 全部 [HM-SUCCESS]，zero errors/warnings/timeouts
- 完美round-robin: k1→k2→k3→k4→k5循坏
- 所有请求first attempt成功

### 30分钟窗口
| Metric | Value |
|--------|-------|
| Total requests | 73 |
| Success (200) | 73 |
| Success rate | **100.00%** |
| ATE (all_tiers_exhausted) | 0 |
| 429 rate-limit | 0 |
| Fallback | 0 |

### 1小时窗口
| Metric | Value |
|--------|-------|
| Total | 139 |
| Success | 139 |
| Rate | **100.00%** |
| ATE | 0 |
| 429 | 0 |
| Fallback | 0 |

### 6小时窗口
| Metric | Value |
|--------|-------|
| Total | 865 |
| Success | 864 |
| Rate | **99.88%** |
| ATE | 0 |
| 429 | 0 |
| Fallback | 0 |
| Non-200 | 1× 502 (NVStream other) |

### 24小时窗口 + 分段分析 (Pitfall #49)
| Window | Total | ATE | 429 | Fallback |
|--------|-------|-----|-----|----------|
| 0-6h | 865 | 0 | 0 | 0 |
| 6-12h | 816 | 3 | 0 | 0 |
| 12-24h | 1729 | 41 | 4 | 271 |
| **Full 24h** | 3411 | 44 | 4 | 272 |

**结论**: 0-12h完全健康, 12-24h为旧regime数据.

### 延迟百分位数 (30min)
| P50 | P90 | P95 |
|-----|-----|-----|
| 18.5s | 26.1s | 42.5s |

### Per-Key Latency (30min)
| Key | Count | Avg | P50 | P95 | Max |
|-----|-------|-----|-----|-----|-----|
| k0 | 14 | 19.6s | 16.9s | 46.5s | 61.4s |
| k1 | 14 | 19.1s | 18.9s | 31.3s | 48.7s |
| k2 | 15 | 18.1s | 18.0s | 26.8s | 27.9s |
| k3 | 15 | 17.7s | 17.1s | 32.4s | 51.7s |
| k4 | 15 | 21.8s | 20.9s | 36.3s | 48.6s |

### 请求速率: 2.4 req/min (75% MIN_OUTBOUND capacity)

## 🎯 优化分析

### 全7参数评估: 全部✅ No adjustment needed
- UPSTREAM_TIMEOUT=70: 19th R158 validation, all P95 < 70s
- TIER_TIMEOUT_BUDGET_S=156: remaining=16s > 10s threshold, 6h 0 ATE
- KEY_COOLDOWN_S=38: 19th R162 validation, KEY=TIER invariant holds (Pitfall #44)
- TIER_COOLDOWN_S=38: aligned with KEY, 0 tier exhaustion
- MIN_OUTBOUND_INTERVAL_S=19.0: 75% utilization, 0 429s
- HM_CONNECT_RESERVE_S=24: no budget_exhausted_after_connect
- PROXY_TIMEOUT=300: no proxy timeouts

**R162+R158均衡plateau**: 连续19轮验证, 稳定即最优.

## 🔧 变更执行

**无变更**: R162的KEY=TIER=38对齐已连续19轮验证. R158的UPSTREAM_TIMEOUT=70已连续19轮验证. 全7参数在均衡plateau.

## 📈 效果对比 (R184 vs R185)
| Window | R184 | R185 |
|--------|------|------|
| 30min | 99.67% (3 ATE) | 100.00% (0 ATE) |
| 1h | 99.69% | 100.00% |
| 6h | 99.48% (6 ATE) | 99.88% (0 ATE) |
| P95 | 46.9s | 42.5s |

## ⚖️ 评判标准
- ✅ 更少报错: 30min/1h/6h 0 ATE, 0 429, 0 fallback
- ✅ 更快请求: P50=18.5s, P95=42.5s
- ✅ 超低延迟: P50稳定18-19s
- ✅ 稳定优先: 19轮连续验证
- ✅ 铁律确认: 只改HM1不改HM2

## ⏳ 轮到HM1优化HM2
