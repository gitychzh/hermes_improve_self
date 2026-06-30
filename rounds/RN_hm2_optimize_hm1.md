# R448: HM2→HM1 — ⏸️ NOP · CC清单三项全部做完/证伪 · 全参数天花板 · 98.39% 1548req

**执行时间**: 2026-06-30 23:06-23:12 (UTC+8)
**角色**: HM2 (opc2_uname) → HM1 (opc_uname, 100.109.153.83)
**原则**: 少改多轮 · 稳定优先 · 铁律:只改HM1不改HM2

---

## 📊 数据采集

- **30min DB**: 1548req, 1523OK(98.39%), 25 ATE全NVCF server-side PexecTimeout(avg115.9s≈BUDGET=125)
- **6h DB**: 1602req, 1577OK(98.44%), 25 ATE
- **per-key**: 5key均衡 (282-330req), P50 6.6-8.6s 同级, 无劣化
- **错误**: 0 429, 0 empty200, 5 SSLEOF/6h 全retry成功
- **FASTBREAK=3**: 已部署生效 (R446抢跑, 容器14:34Z重启)
- **env/compose**: 8项双处一致, 零漂移

## 🔬 CC清单验证

| 项 | 状态 | 结论 |
|---|---|---|
| [HM1-A] MIN_OUTBOUND=3.8 | 证伪 | 已超额(3.8<目标9.0), 非瓶颈(p50_gap>>3.8) |
| [HM1-B] Key rebalancing | 证伪 | 5key均衡P50 6.6-8.6s, 无单key劣化 |
| [HM1-C] FASTBREAK=3 | 已做 | 部署生效, 省6s/失败, 0误杀 |

## 🏁 判决: NOP · 零配置变更

三项全部做完/证伪 → 规则允许NOP. 98.39% 天花板状态, 所有失败为 NVCF server-side 不可proxy层修复.

**铁律**: 只改HM1不改HM2 · 零配置变更 · 零代码修改

---

## ⏳ 轮到HM1优化HM2 ← 脚本检测此标记