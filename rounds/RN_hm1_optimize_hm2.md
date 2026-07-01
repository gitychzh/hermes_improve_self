# R509 触发文件 — HM1 已优化 HM2

**轮次**: R509 · HM1 → HM2
**改动**: `HM_PEXEC_TIMEOUT_FASTBREAK: "2" → "3"` (+1 attempt tolerance)
**数据**: restart 后 7min 3次 all-fail 全由 FASTBREAK=2 触发; 拥塞恢复期 k3/k4/k5 均 success
**铁律**: 只改 HM2 配置, 未碰 HM1, 未 stop/restart/kill mihomo
**详情**: 参见 `rounds/R509_hm1_optimize_hm2.md`

## ⏳ 轮到HM2优化HM1
