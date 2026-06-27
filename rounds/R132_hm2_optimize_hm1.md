# R132: HM2→HM1 — TIER_TIMEOUT_BUDGET_S 144→146 (+2s)

## 📊 数据采集 (30min + 1h + 6h + 24h)

### Config Snapshot (HM1 hm40006)
| Parameter | Value |
|-----------|-------|
| UPSTREAM_TIMEOUT | 68 |
| TIER_TIMEOUT_BUDGET_S | 144 (→146) |
| KEY_COOLDOWN_S | 38.0 |
| TIER_COOLDOWN_S | 42 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 |
| HM_CONNECT_RESERVE_S | 24 |
| PROXY_TIMEOUT | 300 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 |

### 30min Window
- **Requests**: 60/60 ok (100%)
- **all_tiers_exhausted**: 0
- **Fallback**: 0 (0%)
- **Latency**: p50=17747ms, p90=38774ms, p95=59154ms, avg=21090ms, max=75154ms
- **429s on deepseek**: 0

### 1h Window
- **Requests**: 132/132 ok (100%)
- **all_tiers_exhausted**: 0
- **Latency**: p50=18307ms, p90=37697ms, p95=58722ms, avg=21283ms

### 6h Window
- **all_tiers_exhausted**: 5 (avg_dur=138840ms, max_dur=166774ms)

### 24h Key Errors (deepseek_hm_nv only)
- NVCFPexecTimeout: k1=22, k2=18, k0=16, k3=15, k4=15 (total=86, 均匀5键)
- empty_200: k0=8
- 429_nv_rate_limit: 0 on deepseek

### 1h Tier Health
- deepseek_hm_nv: 1308/1313=99.6% ok, 5 fail

### Docker Logs (last 100 lines)
- 1× SSLEOFError on k5 → auto-retry → HM-SUCCESS on k1
- All other entries: HM-SUCCESS first attempt

### Per-Key Latency (30min, success only)
| Key | n | avg_ms | p50_ms |
|-----|---|--------|--------|
| k0 | 15 | 25128 | 18425 |
| k1 | 11 | 26284 | 20541 |
| k2 | 11 | 13576 | 15586 |
| k3 | 14 | 20611 | 14685 |
| k4 | 9 | 17940 | 20052 |

### Request Rate
- ~2 req/min average (low load)

## 🎯 优化分析

### 瓶颈识别
6h窗口有5次all_tiers_exhausted事件，avg_dur=138.8s。这接近`2 × UPSTREAM_TIMEOUT(68) = 136s`的预算耗尽线。

当前算术:
- BUDGET=144, 2×68=136, remaining=8s
- **8s < 10s minimum threshold** → 2个连续timeout后tier仍会break

### 参数选择: 为什么TIER_TIMEOUT_BUDGET_S而非其他

| Parameter | Current | Status | Rationale |
|-----------|---------|--------|-----------|
| UPSTREAM_TIMEOUT | 68 | ✅ 不改 | p95=59.2s vs 68s有9s余量; max=75s是单次长尾不需整体提升 |
| TIER_TIMEOUT_BUDGET_S | 144 | ❌ **需改** | 2×68=136, remaining=8s<10s min threshold → 5× all_tiers_exhausted/6h |
| KEY_COOLDOWN_S | 38.0 | ✅ 不改 | 0 429s/30min, 无触发 |
| TIER_COOLDOWN_S | 42 | ✅ 不改 | 无tier exhaustion循环信号 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ✅ 不改 | ~2 req/min vs 3.2 req/min capacity (19s×5=95s cycle), 充裕 |
| HM_CONNECT_RESERVE_S | 24 | ✅ 不改 | 0 budget_exhausted_after_connect错误 |
| PROXY_TIMEOUT | 300 | ✅ 不改 | 远高于任何请求时长 |

### 根因
R129将BUDGET从142→144 (+2s)，剩余从6s→8s。8s仍低于10s minimum threshold，6h内仍有5次all_tiers_exhausted。需要再+2s使remaining=10s，刚好达到minimum threshold，应能消除2-consecutive-timeout导致的budget break。

### 预期影响
- remaining预算: 8s → 10s (=minimum threshold)
- 2个连续NVCFPexecTimeout后：remaining从8s→10s，刚好通过≥10s检查
- all_tiers_exhausted频率：预计5/6h → 接近0

## 🔧 变更执行

### Parameter Diff
```
TIER_TIMEOUT_BUDGET_S: 144 → 146 (+2s)
```

### docker-compose.yml change
```yaml
# Before
TIER_TIMEOUT_BUDGET_S: "144"
# After
TIER_TIMEOUT_BUDGET_S: "146"
```

### Deployment
```bash
cd /opt/cc-infra
sudo docker compose up -d hm40006
# Container hm40006 Recreated → Started
```

### Verification
- ✅ `docker exec hm40006 env | grep TIER_TIMEOUT_BUDGET` → `TIER_TIMEOUT_BUDGET_S=146`
- ✅ Startup log: `NVCF_pexec_models=['deepseek_hm_nv', 'kimi_hm_nv'] tiers=['deepseek_hm_nv', 'kimi_hm_nv'] default=deepseek_hm_nv`
- ✅ `/v1/models` returns `deepseek_hm_nv`, `kimi_hm_nv`
- ✅ First request after restart: k4 succeeded first attempt

## 📈 预期效果

| Metric | Before (R131) | Expected After (R132) |
|--------|--------------|----------------------|
| 30min success rate | 100% (60/60) | 100% |
| 6h all_tiers_exhausted | 5 | ≈0 |
| 30min p50 | 17747ms | ~same |
| 30min p95 | 59154ms | ~same |
| Remaining budget after 2×timeout | 8s (< 10s threshold) | 10s (= 10s threshold) |

## ⚖️ 评判标准
- ✅ 更少报错: 6h all_tiers_exhausted预期5→0
- ✅ 更快请求: latency不受影响(仅扩大budget上限)
- ✅ 超低延迟: p50/p95不变
- ✅ 稳定优先: +2s保守增量，消除remaining<10s的脆弱边界
- ✅ 铁律: 只改HM1不改HM2

## ⏳ 轮到HM1优化HM2