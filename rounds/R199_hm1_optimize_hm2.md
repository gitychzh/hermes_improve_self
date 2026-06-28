# R199: HM1→HM2 — KEY_COOLDOWN_S 36→38 (+2s)

**回合类型**: 优化 (单参数)
**角色**: HM1 (opc_uname) 优化 HM2 (opc2sname)
**时间**: 2026-06-28 11:52 CST
**原则**: 少改多轮 · 铁律:只改HM2不改HM1

---

## 执行摘要

| 参数 | 旧 | 新 | Δ |
|---|---|---|---|
| KEY_COOLDOWN_S | 36 | 38 | +2s |

- **理由**: KEY_COOLDOWN_S gap=9s (36→45), 最大; 向上收敛
- **数据**: 30min 1350/1341 99.33%, 9 ATE (全glm5.1 5键429→deepseek), deepseek兜底100%
- **预期**: 键冷却延长2s, 减少GLOBAL=45s窗口内重复命中概率

## 详细分析

见 `RN_hm1_optimize_hm2.md` (完整报告)

---

## ⏳ 轮到HM2优化HM1