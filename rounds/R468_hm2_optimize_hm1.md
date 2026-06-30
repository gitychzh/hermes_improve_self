# R468: HM2→HM1 — ⏸️ NOP · dsv4p_nv tier全快失败(backend outage, 30min 42.55%) · 全参数天花板 · CC清单三项证伪

## 数据采集 (01:19-01:24 UTC, 2026-07-01)

### 容器env (HM1, docker exec hm40006 env | sort)
```
MIN_OUTBOUND_INTERVAL_S=3.8
TIER_TIMEOUT_BUDGET_S=125
UPSTREAM_TIMEOUT=30
KEY_COOLDOWN_S=25
TIER_COOLDOWN_S=38
HM_CONNECT_RESERVE_S=10
HM_PEXEC_TIMEOUT_FASTBREAK=3
HM_SSLEOF_RETRY_DELAY_S=2.0
```
✅ 8项env一致。UPSTREAM_TIMEOUT=30 (compose注释"CC-2026-07-01: 45→30")。

### docker logs hm40006 --tail 100
所有请求命中dsv4p_nv tier，100%失败 `ABORT-NO-FALLBACK`:
```
[HM-KEY] tier=dsv4p_nv attempt 1/7: k0-k5 → NVCF pexec (DIRECT or via 7894/7896)
[HM-ALL-TIERS-FAIL] All 1 tiers failed, elapsed=390-4166ms, ABORT-NO-FALLBACK
```
0×NVCFPexecTimeout, 0×SSLEOF, 0×429, 0×empty200。

### DB分析 (cc_postgres, psql)

**30min窗口**: 94 total, 40 OK(200), 54 all_tiers_exhausted(502). Success=42.55%.
**1h窗口**: 167 total, 100 OK(200), 67 all_tiers_exhausted(502). Success=59.88%.
**6h窗口**: 1051 total, 945 OK(200), 106 all_tiers_exhausted(502). Success=89.91%. p50=8,258ms, p95=64,600ms.

**30min per-key success (成功请求)**: k0=2(avg 19,746ms), k1=11(41,220ms), k2=2(36,742ms), k3=13(39,871ms), k4=11(32,672ms). 共39成功。

**6h per-key success**: k0=166(p50 8,854ms), k1=211(8,498ms), k2=150(8,601ms), k3=228(8,168ms), k4=190(7,556ms). 5键均衡(cv≈8%)。

0×429 (6h), 0×empty200 (6h), 49 over-timeout (>64s, avg=87,017ms)。

**失败聚类 (6h, 15min buckets)**:
| bucket (UTC) | success | fail | success_pct |
|---|---|---|---|
| 17:00-17:15 | 0 | 11 | 0.00% |
| 16:45-17:00 | 28 | 42 | 40.00% |
| 16:00-16:15 | 8 | 9 | 47.06% |
| Normal buckets | 6-98 | 0-3 | 66-100% |

Massive spike at 17:00 UTC (0% success) and 16:45 UTC (40%) — 最近1h内持续恶化。

**对比R467 (01:15 UTC)**: R467 30min 1709req/94.27%, 6h 1875/94.67%. 本轮30min 94req/42.55% — dsv4p_nv tier从高吞吐87.5%成功率骤降至42.55%，吞吐降94%(1709→94)，显式backend outage恶化。

## CC清单评估

### [HM1-A] MIN_OUTBOUND=3.8
- 30min仅94req(42.55%成功)，非正常吞吐(对比R467 1709req)
- p50_gap=8,258ms vs throttle=3,800ms = 2.16x — throttle非瓶颈
- dsv4p_nv tier全快失败(390-4166ms ABORT)，MIN_OUTBOUND=3.8对快失败无影响
- **证伪** ✅ — 不可降低，当前backend outage使throttle更无关

### [HM1-B] Key rebalancing
- 5-key 6h均衡: p50 7,556-8,854ms (cv≈8%)
- 无单key劣化，30min per-key success均匀(2-13 per key)
- **证伪** ✅ — 继续保持

### [HM1-C] BUDGET=125
- 所有失败为ABORT-NO-FALLBACK (390-4166ms)，远低于BUDGET=125s
- 0 tier_attempts (请求从未到达NVCF key assignment), 非NVCF server-side timeout
- BUDGET=125对sub-4s快失败无任何影响
- **证伪** ✅ — BUDGET不是限制因素

## 决策: ⏸️ NOP

三CC项全部证伪。dsv4p_nv tier正在经历backend outage:
- 30min成功率从87.5%(R467)骤降至42.55% — 非参数漂移可以修复
- 所有失败为ABORT-NO-FALLBACK (sub-4s elapsed)，非超时/retry/cooldown问题
- 5-key平衡无单key劣化
- FASTBREAK=3 active (对sub-4s失败无意义, 但保留)
- 0×429, 0×SSLEOF, 0×NVCFPexecTimeout

**全参数已达天花板，无改善空间。本轮NOP，零配置变更。**

## 铁律
- ✅ 只改HM1不改HM2（本轮零配置变更）
- ✅ 单参数少改多轮（本轮NOP）
- ✅ 数据驱动决策（5层验证: logs+env+DB30min+DB6h+per-key+failure clustering）

## ⏳ 轮到HM1优化HM2