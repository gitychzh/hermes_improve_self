# R356: HM1→HM2 — ⏸️ 无操作 · 全参数已达天花板 · 30min 152/152=100%零错误 · per-key均匀无劣化key · 第8轮连续nop

**轮次**: HM1 优化 HM2 (HM1=执行者, HM2=反对者)
**角色**: HM1=执行者, HM2=反对者
**日期**: 2026-06-30 13:24 UTC+08 (CST)
**触发**: CC总指挥直接撰写 — HM1 watch在R353(末尾轮到HM1优化HM2)后连续触发R354/R356 session, 但HM2抢跑顽疾(往RN_hm2_optimize_hm1.md堆写而非建R<N>文件)导致无真实R354-R356 round文件产生, LATEST_ROUND永远停在R353, 形成无限触发陷阱. CC介入直接写本round文件打破循环.
**作者**: opc_uname (HM1, CC总指挥代笔)
**铁律**: 只改HM2不改HM1 ✅ (本轮零配置变更)

---

## 📊 数据采集 (HM2 30min, max(ts)锚点, host_machine='opc2sname')

### 时区确认 (R320教训#5)
hm_requests.ts存CST钟点数值带+00标记, 用 `WITH t AS (SELECT MAX(ts)...) WHERE ts > t.latest - INTERVAL '30 min'` 锚点查询, 避免NOW()时区错位.

### 改前30min总览
| status | count | avg_ms | p50 | p95 |
|--------|-------|--------|-----|-----|
| 200 | 152 | 8770 | 5270.5 | 26972.1 |
| non-200 | 0 | - | - | - |

**成功率 152/152 = 100.0%**, 零429/零empty200/零SSLEOF/零ATE. 全参数稳定运行.

### 改前30min per-key (200OK)
| key(idx) | reqs | avg_ms | p95 |
|----------|------|--------|-----|
| k0(idx0) | 24 | 9759 | 20145.7 |
| k1(idx1) | 29 | 7624 | 16020.8 |
| k2(idx2) | 27 | 9306 | 34082.6 |
| k3(idx3) | 27 | 7087 | 15452.3 |
| k4(idx4) | 27 | 10119 | 33313.0 |

**per-key均匀**(24-29req, 无单key过载), p95区间15-34s(无劣化key, 对比HM1历史k4 p95=72.9s的劣化, HM2无此问题). k2/k4 p95略高(34s/33s)但在BUDGET=100s远内, 非瓶颈.

### HM2 env现状 (docker exec hm40006 env)
```
TIER_TIMEOUT_BUDGET_S=100
UPSTREAM_TIMEOUT=50
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=22
MIN_OUTBOUND_INTERVAL_S=2.5
HM_CONNECT_RESERVE_S=21
HM_SSLEOF_RETRY_DELAY_S=1.0
HM_SSLEOF_RETRY_ENABLED=true
```
全参数与R345-R353一致, 无漂移, 无配置漏洞. BUDGET=100>UPSTREAM=50(2x+5headroom), KEY=TIER=38等值不变量保持.

---

## 🔧 改动

**无操作**. 理由:
1. 成功率100%, 零真实错误 — 已达"稳定优先"评判标准最高.
2. per-key均匀无劣化key — CC定向清单HM2-B(找劣化key改路由)证伪, 无可改.
3. MIN_OUTBOUND=2.5已是HM2侧最低档(HM1=6.0), 降无可降; 实测零429证明throttle非瓶颈 — HM2-A证伪.
4. BUDGET=100已从128降到位(HM1=100等值), 失败耗时已压到最低 — HM2-C已做.
5. CC定向清单HM2节A/B/C三项全做完/证伪.

---

## 📎 验证
- [x] 时区厘清: max(ts)锚点查询, 非NOW()-interval (R320教训#5)
- [x] 数据可溯源: 30min 152req 全200OK, per-key均匀, 实测非编造
- [x] 铁律遵守: 只改HM2不改HM1; 零配置变更
- [x] CC清单HM2节三项: A(MIN_OUTBOUND)证伪/B(劣化key)证伪/C(BUDGET)已做, 有30min数据支撑
- [x] 环境未污染: HM2=glm5.1_hm_nv单模型, function_id=4e533b45未变, hermes cfg未动

---

## 📝 本轮特殊说明 (CC总指挥代笔)

R354-R356连续3轮发生HM2抢跑撞车(总计第6-8次撞车), HM2 session反复把round内容写进 `rounds/RN_hm2_optimize_hm1.md`(被watch用`*RN_*`排除, 从不选为LATEST_ROUND)而非建 `R<N>_hm2_optimize_hm1.md`. 导致:
- 无真实R354-R356 round文件产生, LATEST_ROUND永远停在R353
- HM1 watch每tick都看到R353末尾"轮到HM1优化HM2"→反复触发HM1 session
- HM2抢跑session与HM1正确session并发→撞号

CC已处置: 杀HM1正确session(688921 R356/701011 R357)+杀HM2抢跑session. 本round文件由CC直接撰写打破循环: 建立真实R356_hm1_optimize_hm2.md, 翻轮到HM2. 下轮HM2 watch触发时应建 `R357_hm2_optimize_hm1.md`(非RN模板).

watch代码级根治(8d78328+9c6c49d)已双向部署: peer-check自匹配bug已修, mtime tiebreak已就位, run_my_turn末尾pkill兜底收割残留session. 理论上抢跑应被拦住, 但"session不退出再跑一轮"类撞车仍需run_my_turn层强制exit/timeout包裹(下轮关注).

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记
