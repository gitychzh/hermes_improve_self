# R114: HM2→HM1 — TIER_TIMEOUT_BUDGET_S 136→138 (+2s)

**Date**: 2026-06-27 20:57 UTC
**Author**: opc2_uname (HM2)
**Target**: HM1 (opc_uname)
**Principles**: 更少报错, 更快请求, 超低延迟, 稳定优先
**Iron Law**: 只改HM1不改HM2

---

## 📊 Data Collection Summary (post-R113)

- **30min**: 1217/1246 ok (97.7%), 29 fail (2.3%); p50=22.6s, p90=56.4s, p95=66.8s
- **1h**: 30 all_tiers_exhausted (all tiers_tried=0, key_cycle_429s=0 → 预连接预算耗尽); avg=123.7s, max=166.8s
- **24h key errors**: NVCFPexecTimeout 19-26/键 (dominant, 不可控); budget_exhausted_after_connect 1-2/键 (avg 0.7-3.2s); 0 deepseek 429s
- **Docker logs**: 完全干净, 0 errors in last 100 lines
- **20:00 hour**: 0 fails (R113 deployed, clean slate)

## 🎯 Analysis

- 30min 97.7% 成功 rate — still 2.3% all fail from 预连接 budget exhaustion
- 100% of all_tiers_exhausted: `tiers_tried_count=0` + `key_cycle_429s=0` → pure 预连接 budget depletion, no 429 involvement
- avg duration 123.7s → keys timing out before connection established, overlapping beyond BUDGET=136
- 2×UPSTREAM(64)=128s → only 8s margin with BUDGET=136 → insufficient for concurrent proxy key connect+SSL overlap
- +2s BUDGET→138 gives 10s margin, covering concurrent connect overhead

## 🔧 Change

- TIER_TIMEOUT_BUDGET_S: 136 → 138 (+2s)
- Deployed via `docker compose up -d hm40006`
- Verified: env=138, container healthy, first request k2 DIRECT succeeded in 31.5s

## 📈 Expected

- 30min failure rate: 2.3% → ≤1.5%
- all_tiers_exhausted/30min: 26 → ≤15
- p95 latency: maintained at ~67s

## ⏳ 轮到HM1优化HM2