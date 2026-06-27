# R135: HM2 → HM1 — 无变更 (验证R134: 30min 72/72 ok(100%), 0 all_tiers_exhausted; 6h仅4次avg=131.9s; 24h deepseek keys NVCFPexecTimeout 22+18+16+15+15均<68s; 7参数均衡→稳定优先不追加)

## 📊 数据采集 (2026-06-28 00:30 UTC, 30min窗口)

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

### Request Stats (30min, deepseek_hm_nv)
| Metric | Value |
|--------|-------|
| Total | 72 |
| Success | 72 (100%) |
| Fail | 0 |
| Avg | 20931ms |
| p50 | 18207ms |
| p90 | 34852ms |
| p95 | 43475ms |
| p99 | 78184ms |

### Error Breakdown (30min)
- **0 errors** — clean window

### Fallback Rate (30min)
- 0/72 = 0.00%

### Per-minute Rate (deepseek, 60min)
- Range: 1-4 req/min
- Average: ~2.8 req/min
- MIN_OUTBOUND_INTERVAL_S=19.0 → capacity: 3.16 req/min per key × 5 keys = 15.8 req/min → 18% utilization

### Key Errors 24h (deepseek only)
| Key | Error | Count | Avg Elapsed |
|-----|-------|-------|-------------|
| K1 | NVCFPexecTimeout | 22 | 28791ms |
| K2 | NVCFPexecTimeout | 18 | 15119ms |
| K0 | NVCFPexecTimeout | 16 | 16070ms |
| K3 | NVCFPexecTimeout | 15 | 30258ms |
| K4 | NVCFPexecTimeout | 15 | 14869ms |
| K0 | empty_200 | 8 | - |

### all_tiers_exhausted (6h)
- 4 events (avg=131856ms, 131.9s)
- min=127700ms, max=140282ms
- Budget consumed per event: ~131.9s out of 146s = 90.3%
- Remaining after 2×68=136s: 10s (exactly at threshold, confirmed R133)

### Docker Logs (last 100 lines)
- **0 errors, 0 warnings** — all [HM-SUCCESS] lines

## 🎯 优化分析

### 瓶颈评估
1. **30min窗口**: 72/72 100%成功, 0 errors, 0 fallbacks → ❌ 无瓶颈
2. **all_tiers_exhausted**: 6h仅4次, avg=131.9s → 低频, 非紧急瓶颈
3. **Deepseek key timeouts**: 所有timeout avg < 30s, 远低于UPSTREAM_TIMEOUT=68s → NVCF侧超时, 非我方瓶颈
4. **Per-minute rate**: 2.8 req/min vs 19s间隔容量 15.8 req/min → 18%利用率 → 无压力

### 为什么不改任何参数

| Parameter | Current | 评估 | 理由 |
|-----------|---------|------|------|
| UPSTREAM_TIMEOUT | 68 | ✅ 不变 | 所有NVCFPexecTimeout avg < 30s, NVCF侧超时非我方控制; 提高不解决NVCF超时 |
| TIER_TIMEOUT_BUDGET_S | 146 | ✅ 不变 | 2×68=136, remaining=10s (=min threshold, R133 validated pass); 30min内0 all_tiers_exhausted → 无需追加 |
| KEY_COOLDOWN_S | 38.0 | ✅ 不变 | deepseek keys 0 429s in 24h → 冷却足够; 缩短只会引发更多429 |
| TIER_COOLDOWN_S | 42 | ✅ 不变 | deepseek仅4次tier级exhaustion/6h → 冷却频率极低 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ✅ 不变 | 实际2.8 req/min vs 容量15.8 req/min (18%利用率); 降低虽可但无必要 |
| HM_CONNECT_RESERVE_S | 24 | ✅ 不变 | 0 budget_exhausted_after_connect → 连接预算充足 |
| PROXY_TIMEOUT | 300 | ✅ 不变 | 无proxy timeout事件; 300s足够 |

### 评判
- **更少报错** ✅: 30min 0 errors, 6h仅4次all_tiers_exhausted
- **更快请求** ✅: p50=18207ms, p90=34852ms — NVCF模型调用延迟(非HM配置可控)
- **超低延迟** ✅: avg=20931ms — deepseek-v4-pro正常延迟范围
- **稳定优先** ✅: 100%成功率, 0 fallbacks, 0 429s — 系统已达均衡

## 🔧 变更执行

**无变更** — 本轮验证R134以来的稳定性:
- R134: HM2→HM1 无变更 (验证R133)
- R135: HM2→HM1 无变更 (延续验证)

## 📈 预期效果

| 指标 | R134前 | R135(当前) | 趋势 |
|------|--------|------------|------|
| 30min成功率 | 100% | 100% | → |
| all_tiers_exhausted/6h | 0 | 4 | → (低频, 6h内4次) |
| Fallback率 | 0% | 0% | → |
| 429 rate | 0 | 0 | → |
| Deepseek timeout | ~86/24h | ~86/24h | → |

## ⚖️ 评判标准

- ✅ 更少报错: 30min 0 errors, 6h仅4次all_tiers_exhausted (无429, 无ConnectionReset)
- ✅ 更快请求: p50=18207ms, 所有NVCFPexecTimeout < 30s — 非我方控制范围
- ✅ 超低延迟: avg=20931ms, p95=43475ms — deepseek-v4-pro正常水平
- ✅ 稳定优先: 100%成功率, 0 fallbacks, 系统均衡 — **不追加, 不降低, 不动任何参数**

## 🔨 铁律确认
- **只改HM1** ✅: 本轮无变更, 未动HM1任何参数
- **未改HM2** ✅: 全程仅分析HM1数据, 未触碰HM2本地docker-compose.yml

## ⏳ 轮到HM1优化HM2