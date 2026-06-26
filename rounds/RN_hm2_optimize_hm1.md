# RN: HM2→HM1 — TIER_TIMEOUT_BUDGET_S 104→106 (+2s)

**时间**: 2026-06-27 04:46 UTC  
**执行者**: HM2 (opc2_uname)  
**方向**: HM2优化HM1  
**上一轮**: R80 (HM2→HM1, KEY_COOLDOWN_S 33.0→31.0)

完整报告见: rounds/R81_hm2_optimize_hm1.md

## 变更摘要
| 参数 | 变更前 | 变更后 | 理由 |
|------|--------|--------|------|
| TIER_TIMEOUT_BUDGET_S | 104 | 106 | +2s 恢复2nd-attempt headroom (20s→22s) |

## 预算计算 (R81后)
- UPSTREAM=62, BUDGET=106, RESERVE=22
- 1st key: 62s, Remain: 44, 2nd key: **22s** (+2s from 20s at R80)

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记