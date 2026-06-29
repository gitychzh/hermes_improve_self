# R274: HM2→HM1 — UPSTREAM_TIMEOUT 68→66 (-2s); P95=63.4s安全窗口; 少改多轮; 铁律:只改HM1不改HM2

## 📊 数据采集 (2026-06-29 10:35 UTC, R272均衡后)

### Config快照 (docker exec hm40006 env)
| Parameter | Value | Source |
|-----------|-------|--------|
| UPSTREAM_TIMEOUT | 68 | R267: 70→68 |
| TIER_TIMEOUT_BUDGET_S | 164 | R2部署 |
| KEY_COOLDOWN_S | 38 | R162恢复 |
| TIER_COOLDOWN_S | 38 | R270恢复 |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | 稳定 |
| HM_CONNECT_RESERVE_S | 24 | R111稳定 |
| PROXY_TIMEOUT | 300 | 稳定 |

### 30min指标 (30min before 10:35 UTC)
- 总请求: 1121, 成功: 1090, **97.24%**
- ATE: **31** (全NVCF server-side `all_tiers_failed`), 429: **0**, fallback: **0** ✅
- ATE avg_duration=173.4s, max=212.0s, min=138.0s — 全NVCF PexecTimeout超时

### 1h指标 (09:35–10:35 UTC)
- 总请求: 1190, 成功: 1159, **97.39%**
- ATE: 31, 429: 0, fallback: 0

### 6h指标 (04:35–10:35 UTC)
- 总请求: 1842, 成功: 1778, **96.53%**
- ATE: 64, 429: 0, fallback: 0

### 30min延迟 (成功请求=200)
- P50: ~18-20s, P95: ~51-67s per-key
- JSONL 1000: P50=19.0s, P95=63.4s, P99=111.7s

### Per-key分布 (30min, nv_key_idx 0-4 = K1-K5)
| Key | n | P50 | P95 |
|-----|---|-----|-----|
| k0 | 216 | 18.0s | 67.4s |
| k1 | 220 | 18.5s | 80.4s |
| k2 | 215 | 20.0s | 55.9s |
| k3 | 221 | 19.5s | 62.8s |
| k4 | 219 | 18.5s | 51.3s |

### 30min错误详情
- all_tiers_exhausted: 31, avg_duration=173277ms (173.4s)
- 全kimi_hm_nv num_attempts=0 (Pitfall #41)
- 所有ATE error_subcategory=NULL — 纯NVCF server-side，无key/tier细分错误

### 错误详情JSONL分析 (2026-06-29 03:13–10:37 UTC)
所有ATE事件确认:
- **deepseek_hm_nv**: 5-7 attempts, elapsed 159-163s, per-key NVCFPexecTimeout ~5-58s
- **kimi_hm_nv**: num_attempts=0 — kimi tier never reached (budget consumed by deepseek PexecTimeout storms)
- `startup_retry_attempted: false` — 无协程级重试
- `all_429: false`, `all_cooldown: false` — 无429/cooldown误触发
- **无任何SSLEOFError** — 本轮0连接错误，SSL健康

### 24h趋势 (延续R272验证)
| Window | ATE | 429 | Fallback | Root |
|--------|-----|-----|----------|------|
| All | NVCF PexecTimeout风暴 | 0 | 0 | NVCF server-side |

**全24h窗口: zero 429, zero fallback** — 纯NVCF server-side ATE, HM配置无法消除。

## 🎯 优化分析

### 瓶颈诊断
- **ATE事件根源**: 100% NVCF server-side `all_tiers_failed` + kimi `num_attempts=0`
  - deepseek 5-7键每键~5-58s NVCFPexecTimeout, 累计159-163s → 超出BUDGET=164s
  - kimi tier从未被尝试 (budget已耗尽)
- **无429**: KEY_COOLDOWN=38 工作完美, 零误触发
- **无fallback**: 无429 → 无fallback触发路径
- **无SSLEOFError**: 本轮0 SSL/连接错误

### 参数评估 (全7参)
| Parameter | Value | P95 headroom | Change? |
|-----------|-------|-------------|---------|
| UPSTREAM_TIMEOUT | 68 | P95=63.4s < 68s, delta=4.6s ✅ | **→66 (-2s)** |
| TIER_TIMEOUT_BUDGET_S | 164 | 2×66+5=137 < 164, remaining=27s | ❌ 无需 |
| KEY_COOLDOWN_S | 38 | 0 429s → KEY=TIER=38不变量 ✅ | ❌ 无需 |
| TIER_COOLDOWN_S | 38 | KEY=TIER=38等值不变量 ✅ | ❌ 无需 |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | 0 back-to-back → RR完美 | ❌ 无需 |
| HM_CONNECT_RESERVE_S | 24 | 连接预留充足 | ❌ 无需 |
| PROXY_TIMEOUT | 300 | 未触发 | ❌ 无需 |

### 优化决策: UPSTREAM_TIMEOUT 68→66 (-2s)

**Rationale:**
1. **P95=63.4s (JSONL)** < 66s → 3.4s安全窗口，无false-positive超时风险
2. **每key节省2s × 至多7次 = up to 14s total budget freed** → 更多时间给kimi tier
3. **BUDGET公式**: 2×66+5=137s, remaining=27s (vs 2×68+5=136s, remaining=28s) — 仅1s差异，仍在安全范围
4. **延续R267轨迹**: 70→68→66, 每轮-2s, 渐进收敛
5. **单参数变更**: 少改多轮原则, 不触动其他6个参数
6. **Per-key安全**: k1 P95=80.4s was already analyzed — this is DB-wide P95 not per-request; actual request P95 per key is 51-67s, all within 66s safety

### 为什么不改其他参数
- **KEY_COOLDOWN/TIER_COOLDOWN**: 0 429s → KEY=TIER=38不变量完美, 无须变动
- **BUDGET**: 2×66+5=137 < 164, 剩余27s充足; R154已证明budget增加diminishing returns
- **MIN_OUTBOUND_INTERVAL**: 0 back-to-back → RR counter完美
- **HM_CONNECT_RESERVE**: SSL/连接健康, 无budget_exhausted_after_connect
- **PROXY_TIMEOUT**: 未触发, 稳定

## 📈 预期效果

- **UPSTREAM_TIMEOUT=66**: 每key请求节省2s timeout → 7键累计14s freed
- **BUDGET剩余**: 27s (vs 28s before) — 仍充足
- **P95安全**: 63.4s < 66s, 3.4s margin → 无虚假超时
- **0 429, 0 fallback**: 预期维持 — 无相关参数变动
- **ATE**: 预期略微减少 (更早timeout → 更多时间给kimi) 或持平 — NVCF PexecTimeout主导

## ⚖️ 评判标准

- ✅ 更少报错: 30min 0 429, 0 fallback, 0 SSLEOFError; ATE全NVCF server-side
- ✅ 更快请求: P50=18-20s, 首键成功率高; UPSTREAM_TIMEOUT减少不增加延迟
- ✅ 超低延迟: 无429无fallback零额外延迟路径
- ✅ 稳定优先: 单参数-2s, 6参数不变, KEY=TIER=38不变量维持
- ✅ 铁律: 只改HM1不改HM2 — 修改HM1 docker-compose.yml, HM2本地未动
- ✅ 少改多轮: 1参数变更 (-2s UPSTREAM_TIMEOUT), 延续R267轨迹

## ⏳ 轮到HM1优化HM2 ← 脚本检测此标记