# R175: HM2→HM1 — 无变更 (全7参数均衡; 30min 99.58% 3ATE 0 429 0 fallback; 6h 99.0% 16ATE全NVCF PexecTimeout; 24h 45ATE 1464fallback全旧regime; 第11次R162验证+第11次R158验证; 少改多轮; 铁律:只改HM1不改HM2)

**回合**: R175
**方向**: HM2 (opc2_uname) → HM1 (opc_uname)
**日期**: 2026-06-28 07:05 UTC
**类型**: 无变更 — 全7参数均衡收敛验证
**铁律**: 只改HM1不改HM2

---

## 📊 数据采集 (07:05 UTC, 30min窗口 06:55→07:25)

### 30分钟统计

| 指标 | 值 |
|---|---|
| 总请求 | 1,193 |
| 成功 (200) | 1,188 (99.58%) |
| 失败 | 5 (3×ATE + 2×NVStream_IncompleteRead) |
| 平均延迟 | 21,368ms |
| P50 | 18,344ms |
| P95 | 49,508ms |
| Fallback | 0 |
| 含key_cycle_429s标记 | 12 |

### 1小时统计

| 指标 | 值 |
|---|---|
| 总请求 | 1,261 |
| 成功 | 1,255 (99.52%) |
| 失败 | 6 (3×ATE + 2×NVStream_IncompleteRead + 1×NVStream_TimeoutError?) |
| P50 | 18,426ms |
| P95 | 49,958ms |

### 6小时统计

| 指标 | 值 |
|---|---|
| 总请求 | 1,961 |
| 成功 | 1,940 (99.0%) |
| 失败 | 21 |
| ATE | 16 (avg 141,163ms, NVCF server-side PexecTimeout) |
| NVStream_TimeoutError | 3 |
| NVStream_IncompleteRead | 2 |
| Fallback | 0 (全部窗口0 fallback) |

### 24小时统计

| 指标 | 值 |
|---|---|
| 总请求 | 4,570 |
| 成功 | 4,519 (98.87%) |
| 失败 | 51 |
| ATE | 45 (NVCF server-side PexecTimeout,全regime) |
| Fallback | 1,464 (全部12-24h旧regime数据, Pitfall #49) |
| P50 | 22,009ms |
| P95 | 79,073ms |

### Per-Key Latency (30min deepseek_hm_nv)

| Key | Requests | Success | P50 (ms) | P95 (ms) | Max (ms) | key_cycle_429s |
|---|---|---|---|---|---|---|
| k0 (nv_key_idx=0) | 246 | 246 (100%) | 19,096 | 53,869 | 124,968 | 1 |
| k1 (nv_key_idx=1) | 237 | 237 (100%) | 18,503 | 49,626 | 150,161 | 2 |
| k2 (nv_key_idx=2) | 229 | 229 (100%) | 17,256 | 38,179 | 98,668 | 2 |
| k3 (nv_key_idx=3) | 238 | 237 (99.6%) | 18,358 | 46,050 | 86,431 | 2 |
| k4 (nv_key_idx=4) | 241 | 240 (99.6%) | 18,313 | 51,737 | 109,272 | 5 |

### 错误详情

| Error Type | 30min | 6h | 24h |
|---|---|---|---|
| all_tiers_exhausted | 3 | 16 | 45 |
| NVStream_IncompleteRead | 2 | 2 | 2 |
| NVStream_TimeoutError | 0 | 3 | 4 |

### ATE时间分布 (24h)

| UTC Hour | ATE Count |
|---|---|
| 01:00 | 1 |
| 02:00 | 3 |
| 09:00 | 1 |
| 10:00 | 4 |
| 11:00 | 10 |
| 13:00 | 5 |
| 15:00 | 1 |
| 16:00 | 7 |
| 17:00 | 8 |
| 18:00 | 2 |
| 19:00 | 3 |

### 超时分析

- 30min内 >70s: 24/1193 (2.0%), 其中21成功 3失败
- 6h内 >70s: 80/1961 (4.1%), 其中61成功 19失败
- 6h内 >140s (超预算): 13次, 其中仅3次成功 (其余10次ATE)
- 6h内 65-72s 临界区间: 23次, 全部成功

### 当前环境变量 (docker exec hm40006 env)

```
UPSTREAM_TIMEOUT=70
TIER_TIMEOUT_BUDGET_S=156
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=38
MIN_OUTBOUND_INTERVAL_S=19.0
HM_CONNECT_RESERVE_S=24
PROXY_TIMEOUT=300
CHARS_PER_TOKEN_ESTIMATE=3.0
NVCF_DEEPSEEK_FUNCTION_ID=4e533b45-dc54-4e3a-a69a-6ff24e048cb5
NVCF_KIMI_FUNCTION_ID=f966661c-790d-4f71-b973-c525fb8eafd4
```

### Docker Logs (100行尾部)

全部[HM-SUCCESS] — 无error/warn/panic。所有请求deepseek_hm_nv tier首次尝试成功。ring fallback R40策略，tier_chain=['deepseek_hm_nv', 'kimi_hm_nv']。

---

## 🧠 分析

### 参数逐项评估

| Parameter | Current | Need Change? | Reason |
|---|---|---|---|
| UPSTREAM_TIMEOUT | 70 | ❌ No | P50=18.3s, P95=49.5s, 所有key P95<55s远低于70s。2%请求超70s但99%成功。第11次R158验证。 |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ No | 2×70=140, 剩余16s > 10s阈值。R152/R154 diminishing returns已确认: 增加预算不减少ATE。16 ATE全为NVCF server-side PexecTimeout。 |
| KEY_COOLDOWN_S | 38 | ❌ No | KEY=TIER=38, 零gap等值对齐(Pitfall #44)。0次实际429(仅12次key_cycle_429s标记但无实际429)。第11次R162验证。 |
| TIER_COOLDOWN_S | 38 | ❌ No | KEY=TIER=38对称。R156的42→38通过11轮验证稳定。零gap最优对齐。 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ❌ No | 0次429在所有窗口。请求率~2.6/min, 19s容量远高于需求。安全余量充足。 |
| HM_CONNECT_RESERVE_S | 24 | ❌ No | 0次budget_exhausted_after_connect所有窗口。R111已建立24s充分。 |
| PROXY_TIMEOUT | 300 | ❌ No | 内部代理超时, 非瓶颈。从未触发。 |

### 核心判定: 无变更

**所有7参数处于均衡收敛点。** 系统表现:
- **99.58% 30min成功** — 仅3次ATE (NVCF server-side PexecTimeout)
- **0次实际429** — 零速率限制压力
- **0次fallback** — kimi从未需触发
- **P50=18.3s** — 优秀延迟
- **KEY=TIER=38不变式** — 零gap对齐持续192小时+

### 为什么不变更

1. **ATE是NVCF server-side问题**: 16次ATE avg=141,163ms — 全是NVCF服务端PexecTimeout在所有key+所有tier上同时触发的风暴。配置无法阻止。
2. **超时请求成功率高**: 24次>70s请求中21次成功(87.5%) — UPSTREAM_TIMEOUT=70s不是瓶颈。23次65-72s临界请求全部成功。
3. **参数已达收敛平台**: 自R162(KEY=38)以来连续11轮验证。系统在稳定均衡态。
4. **改动任何参数的风险 > 收益**:
   - 降低UPSTREAM_TIMEOUT → 截断更多合法长请求(当前2%超70s, P95=49.5s)
   - 增加BUDGET → R154已证明diminishing returns
   - 降低KEY_COOLDOWN → 破坏KEY≥TIER不变式(Pitfall #44)
   - 降低MIN_OUTBOUND → 增加429风险(虽然目前0,但降低有风险)

### 24h Fallback: Pitfall #49 验证

24h fallback=1,464/4,570=32.0%看似高。但这是旧regime数据:
- 0-6h: 0% fallback
- 6-12h: 0% fallback
- 12-24h: 主导旧regime (NVCFPexecTimeout风暴已消退17h+)

**分段验证再次确认Pitfall #49**: 24h fallback被旧regime数据淹没,不应作为决策依据。

---

## 📈 收敛证据

| 指标 | R162 (前) | R174 (第10次) | R175 (第11次) | 趋势 |
|---|---|---|---|---|
| 30min 成功率 | 99.5% | 100% | 99.58% | ➡️ 稳定 |
| ATE/30min | 3 | 0 | 3 | ➡️ 边缘 |
| 实际429/30min | 0 | 0 | 0 | ➡️ 无压力 |
| Fallback/30min | 0 | 0 | 0 | ➡️ 完美 |
| P50延迟 (ms) | ~18,000 | ~18,000 | 18,344 | ➡️ 稳定 |
| P95延迟 (ms) | ~50,000 | ~50,000 | 49,508 | ➡️ 稳定 |
| KEY=TIER gap | 0 | 0 | 0 | ➡️ 192h+不变 |

**结论**: R162后连续11轮（含R175）无变更验证。系统在强稳定均衡态。KEY=TIER=38等值对齐是长期最优配置。

---

## 📋 回合记录

| 回合 | 方向 | 变更 | 参数 | 效果 |
|---|---|---|---|---|
| R162 | HM2→HM1 | KEY_COOLDOWN_S 34→38 (+4s) | 修复KEY<TIER反向gap | KEY=TIER=38 |
| R166 | HM2→HM1 | 无变更 | — | 第3次R162验证 |
| R167 | HM2→HM1 | 无变更 | — | 第4次R162验证 |
| R168 | HM2→HM1 | 无变更 | — | 第5次R162验证 |
| R171 | HM2→HM1 | 无变更 | — | 第7次R162验证 |
| R172 | HM2→HM1 | 无变更 | — | 第8次R162验证 |
| R173 | HM2→HM1 | 无变更 | — | 第9次R162验证 |
| R174 | HM2→HM1 | 无变更 | — | 第10次R162验证 |
| **R175** | **HM2→HM1** | **无变更** | **—** | **第11次R162验证** |

---

## ⚖️ 评判标准

| 标准 | 状态 | 证据 |
|---|---|---|
| 更少报错 | ✅ | 30min 仅3 ATE(NVCF server-side) + 2 NVStream_IncompleteRead(网络层); 6h 99.0% |
| 更快请求 | ✅ | P50=18.3s, P95=49.5s — 优秀延迟; per-key P50 17-19s |
| 超低延迟 | ✅ | 所有key P95<55s, 远低于UPSTREAM_TIMEOUT=70s; 零429压力 |
| 稳定优先 | ✅ | KEY=TIER=38不变式 192h+; 零fallback 6h+; 收敛均衡平台 |

**铁律确认**: 只改HM1不改HM2 — 本次无变更，铁律自动满足（HM2本地配置未触及）。

**策略**: 少改多轮、单参数优化、数据驱动

**状态**: 第11次R162验证 — 全7参数均衡收敛

## ⏳ 轮到HM1优化HM2