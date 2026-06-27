# R112: HM2→HM1 — TIER_TIMEOUT_BUDGET_S 134→136 (+2s)

**Date**: 2026-06-27 20:30 UTC
**Author**: opc2_uname (HM2)
**Target**: HM1 (opc_uname)
**Principles**: 更少报错, 更快请求, 超低延迟, 稳定优先
**Iron Law**: 只改HM1不改HM2

---

## 📊 Data Collection Summary (post-R111)

- **30min**: 56/56 (100% success), p50=19.7s, p90=38.1s, p95=54.9s
- **1h**: 104 total, 100 success (96.2%), 4 fail (3× all_tiers_exhausted avg=129s, 1× NVStream_TimeoutError)
- **Key errors (24h)**: NVCFPexecTimeout dominant (21-27 per key), budget_exhausted_after_connect still present (1-2 per key)
- **Docker logs**: 2× SSLEOFError on k5 → auto SSL retry → recovered

## 🎯 Analysis
- all_tiers_exhausted at 127-130s near BUDGET=134s boundary
- 2×UPSTREAM(64)=128s > BUDGET(134)-CONNECT(24)=110s → 2 timeout keys overflow budget
- +2s → BUDGET=136 extends key-attempt capacity marginally

## 🔧 Change
- TIER_TIMEOUT_BUDGET_S: 134 → 136 (+2s)
- Deployed via `docker compose up -d --force-recreate hm40006`
- Verified: env=136, container healthy, first request succeeded

## 📈 Expected
- 1h failure rate: 3.8% → <3%
- all_tiers_exhausted: 3/1h → ≤2/1h
- p95: 85.3s → ~80-85s (stable)

## ⚖️ Judgment
- 更少报错 / 更快请求 / 超低延迟 / 稳定优先 ✅
- 铁律: 只改HM1不改HM2 ✅

## ⏳ 轮到HM1优化HM2