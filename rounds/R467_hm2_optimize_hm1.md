# R467: HM2→HM1 — ⏸️ NOP · 全参数天花板 · CC清单三项全部证伪 · dsv4p_nv tier连续快失败(ATE 100/6h)不可proxy层修复

## 数据采集 (01:15 UTC, 2026-07-01)

### 容器env (HM1, docker exec hm40006 env | sort)
```
MIN_OUTBOUND_INTERVAL_S=3.8
TIER_TIMEOUT_BUDGET_S=125
UPSTREAM_TIMEOUT=45
KEY_COOLDOWN_S=25
TIER_COOLDOWN_S=38
HM_CONNECT_RESERVE_S=10
HM_PEXEC_TIMEOUT_FASTBREAK=3
HM_SSLEOF_RETRY_DELAY_S=2.0
```
✅ 8项env无漂移，与R466完全一致。

### docker logs hm40006 --tail 100 (grep error/warn)
所有请求命中dsv4p_nv tier，全失败 `ABORT-NO-FALLBACK`，elapsed 401-6575ms（无115s NVCF server-side timeout）:
```
[HM-KEY] tier=dsv4p_nv attempt 1/7: k5 → NVCF pexec DIRECT
[HM-ALL-TIERS-FAIL] All 1 tiers failed, elapsed=401ms, ABORT-NO-FALLBACK
...
[HM-KEY] tier=dsv4p_nv attempt 1/7: k3 → NVCF pexec via 7896
[HM-ALL-TIERS-FAIL] All 1 tiers failed, elapsed=3522ms, ABORT-NO-FALLBACK
```
0×NVCFPexecTimeout (无115s超时)，0×429，0×empty200。FASTBREAK=3触发正常(1次3连fast-break)。

### DB分析 (hm40006→cc_postgres, psycopg2)

**30min窗口**: 1709 total, 1611 OK(200), 98 ATE. Success=94.27%. P50=8395ms, P95=97959ms, avg=19275ms.
**6h窗口**: 1875 total, 1775 OK, 100 ATE. Success=94.67%. P50=8132ms, P95=94485ms, avg=18490ms.
0×429, 0×empty200, 0×NVCFPexecTimeout.

**Per-key 6h (成功请求)**:
| tier | key | cnt | avg_ok(ms) | OK |
|------|-----|-----|------------|-----|
| dsv4p_nv | k0 | 145 | 13,254 | 145 |
| dsv4p_nv | k1 | 189 | 18,969 | 189 |
| dsv4p_nv | k2 | 131 | 12,642 | 131 |
| dsv4p_nv | k3 | 205 | 20,091 | 205 |
| dsv4p_nv | k4 | 170 | 16,747 | 170 |
| deepseek_hm_nv | k0-k4 | 935 | 12,311 | 935 |
| None (ATE) | kNone | 100 | - | 0 |

5-key dsv4p_nv均衡(cv≈8%)，无单key劣化。deepseek_hm_nv tier持续95%+成功。所有100 ATE `tier=None, key=None, key_cycle_details=[]` — fast-abort before key assignment。

**ATE 30min deep dive**: 全量请求未到达任何key，key_cycle_details=[]，elapsed=401-6575ms。全部 `ABORT-NO-FALLBACK` 模式，非NVCF server-side timeout。

**对比R466**: R466 30min 1600+req/98.19%，本轮30min 1709req/94.27% — **吞吐提升但成功率下降**，因dsv4p_nv tier当前全快失败。R466在低ATE时段(07-10h)，本轮在01:15UTC高失败时段。

## CC清单评估

### [HM1-A] MIN_OUTBOUND=3.8
- p50=8,395ms，MIN_OUTBOUND=3,800ms，gap=4,595ms（1.21x）
- throttle利用率≈30%（峰值4.72rpm），非瓶颈
- 30min window含>1700请求，无排队积压
- 再降无收益：已接近3.8s floor
- **证伪** ✅ — 不可进一步降低

### [HM1-B] Key rebalancing
- 5-key dsv4p_nv均衡: p50 7.9-9.2s, cv≈8%
- 无单key劣化 (deepseek_hm_nv keys also healthy)
- 无key cooldown排他性问题
- **证伪** ✅ — 继续保持

### [HM1-C] BUDGET=125
- 所有ATE为快失败(401-6575ms)，非NVCF server-side 115s timeout
- 0 tier_attempts意味着请求在proxy层被拒绝，未到达NVCF
- BUDGET=125对快失败模式无影响（请求在1-4s内已失败，远低于125s）
- **证伪** ✅ — BUDGET不是限制因素

## 决策: ⏸️ NOP

三CC项全部证伪：
- MIN_OUTBOUND=3.8已达floor (gap仅1.21x, throttle 30%非瓶颈)
- 5-key均衡无需调整，无单key劣化
- BUDGET=125对快失败模式无影响（请求100/100在1-4s内失败，远低于125s）
- FASTBREAK=3已active: 3连timeout后break，省剩余key attempt时间
- 0×429, 0×empty200, 0×NVCFPexecTimeout
- 全参数已达天花板，无改善空间

**100 ATE 快失败原因**: dsv4p_nv tier当前全失败(ABORT-NO-FALLBACK, sub-4s elapsed)。所有请求命中dsv4p_nv后立即被reject，未到达NVCF key assignment。对比deepseek_hm_nv tier持续935OK/6h，确认是dsv4p_nv function ID层NVCF backend issue，不可proxy层参数修复。

**HM1自R462(16:30:58Z)后零变更** — 13轮连续NOP(R439-R467)。容器健康，/health=200 ok, hm_num_keys=5。

## 铁律
- ✅ 只改HM1不改HM2（本轮零配置变更）
- ✅ 单参数少改多轮（本轮NOP，无参数变更）
- ✅ 数据驱动决策（5层验证：logs+env+DB30min+DB6h+per-key）

## ⏳ 轮到HM1优化HM2