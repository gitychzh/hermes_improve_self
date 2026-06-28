# R260: HM1→HM2 — TIER_TIMEOUT_BUDGET_S 120→124 (+4s) — 单轮优化

**回合类型**: 优化 (单参数)
**方向**: HM1 (opc_uname) → HM2 (opc2_uname)
**时间**: 2026-06-29 00:18 UTC
**原则**: 更少报错，更快请求，超低延迟，稳定优先 — 铁律:只改HM2不改HM1 — 少改多轮(单参数)

## 摘要

HM2 的 deepseek tier 成功率 97.82% (1258/1286)，未达 99% 目标。28 个错误均为 all_tiers_exhausted (27) + NVStream_IncompleteRead (1)。Deepseek tier 有 75 SSLEOFError + 15 NVCFPexecTimeout = 90 键级错误/30min，预算断点 4 次显示剩余 1.2-9.8s（全部 < 10s 阈值）。TIER_TIMEOUT_BUDGET_S 120→124 (+4s) 给 deepseek tier 多一个键的机会，减少键级连接失败触发预算断裂。

## 参数变化

| 参数 | 旧值 | 新值 | 增量 |
|------|------|------|------|
| TIER_TIMEOUT_BUDGET_S | 120 | 124 | +4s |

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记