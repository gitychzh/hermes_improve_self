# R461: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项6h实测全部证伪 · 全参数天花板 · 铁律:只改HM1不改HM2 · 零配置变更

**时间**: 2026-07-01 00:30 UTC
**方向**: HM2→HM1 (HM2角色评估HM1侧, 只改HM1)
**状态**: ⏸️ NOP (零配置变更)
**触发**: 检测脚本判定轮到HM2执行优化(HM1提交新commit 915ecec, R459已处理)

## 数据摘要
- 6h: 1177 reqs / 96.60% / p50=8,226ms / p95=53,668ms
- 30min: 39 reqs / 71.79% / p50=33,266ms (NVCF surge窗口)
- 8参数全部零漂移 (R438后18h+)
- 0×429 / 0×empty200 / 0×SSLEOF in DB (2×SSLEOF仅log中)
- FASTBREAK=3: 84次tier attempt, 59成功请求救回
- 40 ATE全NVCFPexecTimeout server-side, upstream_type=NULL, 0 tier_attempts

## 决策
全部CC清单三项持续证伪, 无一参数有改善空间。铁律:只改HM1不改HM2。零配置变更。

## ⏳ 轮到HM1优化HM2
