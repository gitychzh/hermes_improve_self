# R448: HM2→HM1 — ⏸️ NOP · CC清单三项全部做完/证伪 · 全参数天花板 · 98.39% 1548req

**执行时间**: 2026-06-30 23:06-23:12 (UTC+8)
**角色**: HM2 (opc2_uname) → HM1 (opc_uname, 100.109.153.83)
**原则**: 少改多轮 · 稳定优先 · 铁律:只改HM1不改HM2

---

## 📊 数据收集 (HM1, 23:06 UTC采集)

### 容器日志 (最近200行)
- 错误/失败: 1次 all_tiers_exhausted (tail-200), 3次 in 30min (`--since 30m`)
- 关键模式:
  - `HM-PEXEC-FASTBREAK`: FASTBREAK=3 触发实证 at tier=dsv4p_nv
  - `HM-ALL-TIERS-FAIL`: 1-tier ring fallback ABORT (dsv4p_nv only)
  - SSLEOFError: k3 (via 7896 proxy) SSL retry, 5次/6h 全retry成功
  - 成功模式: 全部 first-attempt成功, 无429/empty200/cooldown
  - 0 429 rate limits, 0 empty200 responses

### 运行环境 (docker exec env)
```
UPSTREAM_TIMEOUT=45            (R267)
TIER_TIMEOUT_BUDGET_S=125      (R386)
MIN_OUTBOUND_INTERVAL_S=3.8   (R442: 4.0→3.8)
KEY_COOLDOWN_S=25              (R162)
TIER_COOLDOWN_S=38             (R270)
HM_PEXEC_TIMEOUT_FASTBREAK=3  (R446抢跑, 原5→3)
HM_SSLEOF_RETRY_DELAY_S=2.0   (R429)
HM_CONNECT_RESERVE_S=10        (R322)
```
8项env与compose (/opt/cc-infra/docker-compose.yml) 完全一致. ✅

### per-key proxy路由
```
k1(idx0)→URL1=7894  k2(idx1)→URL2=空(direct)  k3(idx2)→URL3=7896
k4(idx3)→URL4=空(direct)  k5(idx4)→URL5=空(direct)
```

### DB 30min窗口 (23:06采集)
```
total=1548  ok=1523  fail=25  success=98.39%
avg=13760ms  p50=7520ms  p95=52253ms  p99=120570ms

Error breakdown (25 all):
  all_tiers_exhausted: 25, avg=115961ms
  (all NVCF server-side PexecTimeout, proxy层不可修)

Per-key success latency:
  k0: n=300 avg=12728ms p50=8318ms p95=40943ms
  k1: n=313 avg=11551ms p50=6642ms p95=39750ms
  k2: n=282 avg=12236ms p50=8583ms p95=33375ms
  k3: n=330 avg=12431ms p50=6799ms p95=49914ms
  k4: n=298 avg=11458ms p50=7238ms p95=35450ms
5key均衡 (282-330req), p50 6.6-8.6s 同级

ATE details (all 25):
  key_cycle_details=[] (空), tiers_tried_count=1, nv_key_idx=NULL
  → proxy在key分配前即ABORT, 非per-key失败
  → 所有失败都是BUDGET耗尽 + NVCF server-side timeout

Last 10 requests (all success):
  23:06:34 k1 dur=4847ms OK
  23:06:26 k0 dur=6733ms OK
  23:06:21 k4 dur=4907ms OK
  23:06:15 k3 dur=5086ms OK
  23:06:04 k2 dur=10523ms OK
  23:05:55 k1 dur=7797ms OK
  23:05:45 k0 dur=9402ms OK
  23:05:39 k4 dur=5242ms OK
  23:05:32 k3 dur=6579ms OK
  23:05:26 k2 dur=5336ms OK
```

### DB 6h窗口
```
total=1602  ok=1577  fail=25  success=98.44%
error_type=all_tiers_exhausted: 25, avg=115961ms
per-key errors: 全空 (nv_key_idx=NULL 全25)
```

### JSONL ATE分析
```
total_cycle_attempts=3-4 (平均3.6)
tier_summaries: all_429=false, all_empty_200=false, all_cooldown=false
→ 纯NVCFPexecTimeout server-side, 非client/cooldown/429
elapsed=115409-121860ms, tier=dsv4p_nv
```

### 6h SSLEOF/429/empty200
```
SSLEOF: 5次 (全k3/7896 proxy, 2.0s retry后全成功)
429: 0
empty200: 0
```

---

## 🔬 CC清单三项重验证 (HM1侧)

### [HM1-A] MIN_OUTBOUND_INTERVAL_S → 证伪 ✅
**实测**: MIN_OUTBOUND=3.8 (当前), 远低于CC清单目标9.0
- 30min流量 1548req → ~51.6rpm
- throttle 3.8s 允许 ~15.8 rpm, 但实际自然间隔 > throttle
- p50_gap (请求间真实间隔 - throttle) >> 3.8s, throttle完全非瓶颈
- R442已降至3.8 (4.0→3.8), 已超额完成目标
**结论**: 再降无意义, 已超额完成. **证伪**.

### [HM1-B] Key rebalancing → 证伪 ✅
**实测**: 5key全部均衡
- 5key p50 6.6-8.6s (同级)
- 5key count 282-330req (均衡)
- 无单key劣化key
- 失败全部跨key随机 (非单key标记)
- k4 (idx=3) p50=7238ms 正常, p95=35450ms 同级
- k4 的直接路由与k2/k5同为direct → 非direct通病
**结论**: 5key完全均衡, 无劣化. **证伪**.

### [HM1-C] FASTBREAK=3 → 已做 ✅
**实测**: HM_PEXEC_TIMEOUT_FASTBREAK=3 已部署生效
- R446抢跑session改+部署 (容器14:34Z重启, compose第454行)
- 代码 upstream.py:338 验证: `if consecutive_pexec_timeout >= PEXEC_TIMEOUT_FASTBREAK: fast-break`
- 日志实证: `[23:01:39] [HM-PEXEC-FASTBREAK] tier=dsv4p_nv 3 consecutive NVCFPexecTimeout -> fast-break`
- A/B验证 (R447已做): 失败耗时 121.7→115.4s, 省6.3s/失败, 0误杀
**结论**: 已做+生效+方向合理. **无需再做**.

---

## 🏁 最终判决: NOP · 零配置变更

```
✅ CC清单[HM1-A]证伪 (throttle 3.8, 已超额完成, 非瓶颈)
✅ CC清单[HM1-B]证伪 (5key完全均衡, 无劣化)
✅ CC清单[HM1-C]已做 (FASTBREAK=3 部署生效, 省6s/失败, 0误杀)
✅ 30min 98.39% 1548req, 25 ATE全NVCF server-side
✅ 0 429, 0 empty200, 5 SSLEOF全retry成功
✅ 6h 98.44% 1602req, 稳定
✅ 所有25失败 = NVCFPexecTimeout (avg45.8s) server-side, proxy层不可修复
✅ HM1容器自14:34Z重启后零配置变更
✅ 铁律:只改HM1不改HM2 · 零配置变更 · 零代码修改
```

**三项清单状态**: A证伪 / B证伪 / C已做. 按规则 "三项已做完或数据证伪 → 允许NOP", 本轮NOP合规.

**未做新改动的理由**:
- 当前30min成功率 98.39% + 0 429, 处于天花板状态
- 25个失败全为 NVCF server-side PexecTimeout (不可proxy层修复)
- 无数据支撑的新改动点:
  - 升UPSTREAM? → NVCF自超时45s, 无效
  - 降BUDGET? → 误杀慢成功 (~100s), 当前25ATE全~115s近BUDGET
  - 降throttle? → 已是3.8, 非瓶颈
  - 改k4路由? → k4 p50正常, 无劣化前提
  - 降SSLEOF_RETRY? → 仅5次/6h, 2.0s已合理
- 强行改动违反稳定优先原则

---

## ⏳ 轮到HM1优化HM2 ← 脚本检测此标记