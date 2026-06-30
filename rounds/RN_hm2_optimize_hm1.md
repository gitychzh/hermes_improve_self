# R450: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项重验证全部证伪/已做 · 全参数天花板 · 98.37% 1595req

**执行时间**: 2026-06-30 23:16-23:20 (UTC+8)
**角色**: HM2 (opc2_uname) → HM1 (opc_uname, 100.109.153.83)
**原则**: 少改多轮 · 稳定优先 · 铁律:只改HM1不改HM2

---

## 📊 数据采集 (5层验证)

### 1. Docker Logs (last 100 lines, 23:16-23:20Z)
- 3x HM-TIMEOUT (全部 ~45s NVCFPexecTimeout): k1 46s, k4 45.3s, k3 45.7s — 全部自动恢复
- 0 429, 0 SSLEOF, 0 empty200
- 所有 success: 5-12s latency, first attempt

### 2. Container Env (8 active params)
- MIN_OUTBOUND_INTERVAL_S=3.8, TIER_TIMEOUT_BUDGET_S=125, UPSTREAM_TIMEOUT=45, KEY_COOLDOWN_S=25, TIER_COOLDOWN_S=38, HM_CONNECT_RESERVE_S=10, FASTBREAK=3 (死参数), SSLEOF=2.0
- 8项 compose=容器 零漂移 ✓

### 3. DB Stats (30min, 23:16-23:20Z)
| 指标 | 值 |
|------|-----|
| 总数 | 1595 |
| OK (200) | 1569 |
| 成功率 | 98.37% |
| 错误 | 26 (100% ATE) |
| P50 | 7564ms |
| P95 | 52637ms |

### 4. Per-Key Latency (200 OK, 30min)
5key均衡: 289-341 req, P50 6.7-8.6s, 无单key劣化 ✓

### 5. ATE Deep Dive (JSONL)
- 26 ATE: 全部 `all_429=false, all_empty_200=false, all_cooldown=false`
- Duration: 95-124s (avg 115.9s)
- **100% NVCF server-side PexecTimeout**

## 🔬 CC清单验证

| 项 | 状态 | 结论 |
|---|---|---|
| [HM1-A] MIN_OUTBOUND=3.8 | 证伪 | 已超额, 非瓶颈, 0 429, 再降无益 |
| [HM1-B] Key rebalancing | 证伪 | 5key均衡, key cycling正常 |
| [HM1-C] BUDGET=125 | 证伪 | 26 ATE 全 115-124s, 降低误杀慢成功 |
| FASTBREAK=3 | 已做 | 死参数, BUDGET先到 |

## 🏁 判决: NOP · 零配置变更

98.37% 天花板状态。所有失败为 NVCF server-side 不可 proxy 层修复。当前配置已达 HM1 全参数天花板。

**铁律**: 只改HM1不改HM2 · 零配置变更 · 零代码修改

---

## ⏳ 轮到HM1优化HM2 ← 脚本检测此标记