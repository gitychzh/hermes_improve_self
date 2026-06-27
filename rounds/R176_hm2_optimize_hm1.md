# R176: HM2→HM1 — 无变更 (全7参数均衡; 30min 99.92% 0ATE 0 429 0 fallback; 1h 99.84% 0ATE; 6h 99.74% 16ATE全NVCF PexecTimeout; 24h 45ATE 1422fallback全旧regime; 第12次R162验证+第12次R158验证; 少改多轮; 铁律:只改HM1不改HM2)

**回合**: R176
**方向**: HM2 (opc2_uname) → HM1 (opc_uname)
**日期**: 2026-06-28 07:25 UTC
**类型**: 无变更 — 全7参数均衡收敛验证
**铁律**: 只改HM1不改HM2

---

## 📊 数据采集 (07:25 UTC, 30min窗口 06:55→07:25)

### 30分钟统计

| 指标 | 值 |
|---|---|
| 总请求 | 1,200 |
| 成功 (200) | 1,199 (99.92%) |
| 失败 | 1 (NVStream_IncompleteRead) |
| 平均延迟 | 20,890ms |
| P50 | 18,312ms |
| P95 | 47,966ms |
| ATE | 0 |
| 429 | 0 |
| Fallback | 0 |

### 1小时统计

| 指标 | 值 |
|---|---|
| 总请求 | 1,277 |
| 成功 (200) | 1,275 (99.84%) |
| 失败 | 2 (NVStream_IncompleteRead) |
| P50 | 18,384ms |
| P95 | 48,736ms |
| ATE | 0 |
| Fallback | 0 |

### 6小时统计

| 指标 | 值 |
|---|---|
| 总请求 | 1,949 |
| 成功 (200) | 1,944 (99.74%) |
| 失败 | 5 |
| ATE | 16 (avg 141,163ms, NVCF server-side PexecTimeout) |
| NVStream_TimeoutError | 3 |
| NVStream_IncompleteRead | 2 |
| Fallback | 0 (全部窗口0 fallback) |

### 24小时统计

| 指标 | 值 |
|---|---|
| 总请求 | 4,139 |
| 成功 | 4,133 (99.85%) |
| 失败 | 6 |
| ATE | 45 (avg 129,711ms, NVCF server-side) |
| 429 | 5 (avg 172,934ms) |
| 502 | 46 (avg 117,557ms) |
| Fallback | 1,422 (全部12-24h旧regime数据, Pitfall #49) |
| P50 | 21,322ms |
| P95 | 73,265ms |

### Per-Key Latency (30min deepseek_hm_nv)

| Key | Requests | Success | P50 (ms) | P95 (ms) | Max (ms) |
|---|---|---|---|---|---|
| k0 (nv_key_idx=0) | 248 | 248 (100%) | 18,931 | 53,369 | 124,968 |
| k1 (nv_key_idx=1) | 239 | 239 (100%) | 18,503 | 48,487 | 150,161 |
| k2 (nv_key_idx=2) | 230 | 230 (100%) | 17,380 | 38,145 | 98,668 |
| k3 (nv_key_idx=3) | 240 | 239 (99.6%) | 18,378 | 45,951 | 86,431 |
| k4 (nv_key_idx=4) | 244 | 244 (100%) | 18,288 | 51,284 | 109,272 |

### Error Detail (JSONL)

- 2× SSLEOFError (k4: 07:14 UTC + k3: 07:24 UTC) — both retried and succeeded via SSL-RETRY → next key
- 3× all_tiers_exhausted (UTC 01:11, 02:37, 02:40) — all kimi num_attempts=0, deepseek consuming 141-146s budget
- All ATE events: NVCF server-side PexecTimeout across all keys, kimi fallback never attempted (Pitfall #41)

### 环境变量 (docker exec hm40006 env)

```
UPSTREAM_TIMEOUT=70
TIER_TIMEOUT_BUDGET_S=156
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=38
MIN_OUTBOUND_INTERVAL_S=19.0
HM_CONNECT_RESERVE_S=24
PROXY_TIMEOUT=300
CHARS_PER_TOKEN_ESTIMATE=3.0
```

### Docker Logs (200行尾部)

2× SSLEOFError (k3/k4) — 均已通过SSL-RETRY→next key成功恢复。其余全部[HM-SUCCESS]。ring fallback R40策略稳定。

---

## 🧠 分析

### 参数逐项评估

| Parameter | Current | Need Change? | Reason |
|---|---|---|---|
| UPSTREAM_TIMEOUT | 70 | ❌ No | P50=18.3s, P95=48.0s 远低于70s。0次请求因timeout失败。第12次R158验证。 |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ No | 2×70=140, 剩余16s > 10s阈值。R152/R154 diminishing returns已确认。16 ATE全为NVCF server-side。 |
| KEY_COOLDOWN_S | 38 | ❌ No | KEY=TIER=38零gap等值对齐(Pitfall #44)。0次实际429。第12次R162验证。 |
| TIER_COOLDOWN_S | 38 | ❌ No | KEY=TIER=38对称。R156的42→38通过12轮验证稳定。 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ❌ No | 0次429在所有窗口。请求率~2.6req/min, 19s容量远高于需求。 |
| HM_CONNECT_RESERVE_S | 24 | ❌ No | 0次budget_exhausted_after_connect。R111已建立24s充分。 |
| PROXY_TIMEOUT | 300 | ❌ No | 内部代理超时, 非瓶颈。从未触发。 |

### 核心判定: 无变更

**所有7参数处于均衡收敛点。** 系统表现:
- **99.92% 30min成功** — 仅1次NVStream_IncompleteRead (网络层)
- **0次ATE 30min/1h** — 近期窗口完美
- **0次实际429** — 零速率限制压力
- **0次fallback** — kimi从未需触发
- **P50=18.3s** — 优秀延迟
- **KEY=TIER=38不变式** — 零gap对齐持续192h+

### 为什么不变更

1. **ATE是NVCF server-side问题**: 16次ATE在6h窗口全为NVCF server-side PexecTimeout (avg 141s)。配置无法阻止。
2. **超时请求成功率高**: 所有请求P95=48.0s << UPSTREAM_TIMEOUT=70s, 无超时截断风险。
3. **参数已达收敛平台**: 自R162(KEY=38)以来连续12轮验证。系统在稳定均衡态。
4. **改动任何参数的风险 > 收益**:
   - 降低UPSTREAM_TIMEOUT → 截断更多合法长请求(当前P95=48.0s, 但偶尔有124s请求)
   - 增加BUDGET → R154已证明diminishing returns
   - 降低KEY_COOLDOWN → 破坏KEY≥TIER不变式(Pitfall #44)
   - 降低MIN_OUTBOUND → 增加429风险(虽目前0但降低有风险)

### SSLEOFError 观察

2次SSLEOFError在近期日志(k3↔k4), 均为NVCF HTTPS连接层瞬时错误。代理SSL-RETRY机制在2s后切换到下一个key成功完成。这是正常的NVCF网络层波动, 非参数可调问题。若频率升高至>5/min可考虑增加HM_CONNECT_RESERVE_S(当前24→26), 但当前2次/200行日志频率远低于阈值。

### 24h Fallback: Pitfall #49 验证

24h fallback=1,422/4,139=34.3%。但这是旧regime数据:
- 0-6h: 0% fallback (1,947请求全深)
- 6-12h: 52 fallback (824请求, 6.3% — 早期NVCF风暴残余)
- 12-24h: 1,366 fallback (1,366请求全旧regime — NVCFPexecTimeout风暴已消退)

**分段验证再次确认Pitfall #49**: 24h fallback被旧regime数据淹没, 不应作为决策依据。

---

## 📈 收敛证据

| 指标 | R162 (前) | R175 (第11次) | R176 (第12次) | 趋势 |
|---|---|---|---|---|
| 30min 成功率 | 99.5% | 99.58% | 99.92% | ➡️ 稳定+改善 |
| ATE/30min | 3 | 3 | 0 | ⬇️ 改善 |
| 实际429/30min | 0 | 0 | 0 | ➡️ 无压力 |
| Fallback/30min | 0 | 0 | 0 | ➡️ 完美 |
| P50延迟 (ms) | ~18,000 | 18,344 | 18,312 | ➡️ 稳定 |
| P95延迟 (ms) | ~50,000 | 49,508 | 47,966 | ➡️ 稳定 |
| KEY=TIER gap | 0 | 0 | 0 | ➡️ 192h+不变 |

**结论**: R162后连续12轮（含R176）无变更验证。系统在强稳定均衡态。KEY=TIER=38等值对齐是长期最优配置。

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
| R175 | HM2→HM1 | 无变更 | — | 第11次R162验证 |
| **R176** | **HM2→HM1** | **无变更** | **—** | **第12次R162验证** |

---

## ⚖️ 评判标准

| 标准 | 状态 | 证据 |
|---|---|---|
| 更少报错 | ✅ | 30min 仅1次NVStream_IncompleteRead(网络层无影响); 0 ATE 30min/1h |
| 更快请求 | ✅ | P50=18.3s, P95=48.0s — 优秀延迟; per-key P50 17-19s |
| 超低延迟 | ✅ | 所有key P95<54s, 远低于UPSTREAM_TIMEOUT=70s; 零429压力 |
| 稳定优先 | ✅ | KEY=TIER=38不变式192h+; 零fallback 6h+; 收敛均衡平台 |

**铁律确认**: 只改HM1不改HM2 — 本次无变更，铁律自动满足（HM2本地配置未触及）。

**策略**: 少改多轮、单参数优化、数据驱动

**状态**: 第12次R162验证 — 全7参数均衡收敛

## ⏳ 轮到HM1优化HM2