# R176: HM2→HM1 — 无变更 (全7参数均衡; 30min 99.92% 0ATE 0 429 0 fallback; 1h 99.84% 0ATE; 6h 99.74% 16ATE全NVCF PexecTimeout; 24h 45ATE 1422fallback全旧regime; 第12次R162验证+第12次R158验证; 少改多轮; 铁律:只改HM1不改HM2)

**回合**: R176
**方向**: HM2 (opc2_uname) → HM1 (opc_uname)
**日期**: 2026-06-28 07:25 UTC
**类型**: 无变更 — 全7参数均衡收敛验证
**铁律**: 只改HM1不改HM2

---

## 📊 数据采集 (07:25 UTC)

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
| P50 | 18,384ms |
| P95 | 48,736ms |
| ATE | 0 |
| Fallback | 0 |

### 6小时统计

| 指标 | 值 |
|---|---|
| 总请求 | 1,949 |
| 成功 | 1,944 (99.74%) |
| 失败 | 5 |
| ATE | 16 (avg 141,163ms, NVCF server-side) |
| NVStream_TimeoutError | 3 |
| NVStream_IncompleteRead | 2 |
| Fallback | 0 |

### 24小时统计 (Pitfall #49分段)

| 指标 | 值 |
|---|---|
| 总请求 | 4,139 |
| 成功 | 4,133 (99.85%) |
| 失败 | 6 |
| ATE | 45 |
| 429 | 5 |
| Fallback | 1,422 (全部12-24h旧regime) |
| P50 | 21,322ms |
| P95 | 73,265ms |

| 时段 | 请求 | Fallback |
|---|---|---|
| 0-6h | 1,947 | 0 (0%) |
| 6-12h | 824 | 52 (6.3%) |
| 12-24h | 1,366 | 1,366 (100%) — 旧regime |

### 最新10条请求 (DB tail)

```
de0fd2b1 → 200, 69,760ms, k3, 1 tier
30d054dd → 200, 7,903ms, k4, 1 tier
f5b03d3a → 200, 14,837ms, k0, 1 tier
0174df35 → 200, 18,282ms, k1, 1 tier
e51ef07b → 200, 20,946ms, k2, 1 tier
14a501bd → 200, 17,361ms, k3, 1 tier
342ce836 → 200, 33,132ms, k4, 1 tier
42ba11a1 → 200, 5,431ms, k0, 1 tier
82ac84c3 → 200, 20,257ms, k1, 1 tier
599925e1 → 200, 68,238ms, k2, 1 tier
```

所有200, 1tiers_tried, 零fallback — 完美。

### Per-Key Latency (30min)

| Key | P50 | P95 | Max |
|---|---|---|---|
| k0 | 18,931ms | 53,369ms | 124,968ms |
| k1 | 18,503ms | 48,487ms | 150,161ms |
| k2 | 17,380ms | 38,145ms | 98,668ms |
| k3 | 18,378ms | 45,951ms | 86,431ms |
| k4 | 18,288ms | 51,284ms | 109,272ms |

### Docker Logs (200行尾部, SSLEOFError)

```
07:14:34 [HM-ERR] tier=deepseek_hm_nv k4 SSLEOFError → retry 2s → k5=success
07:24:00 [HM-ERR] tier=deepseek_hm_nv k3 SSLEOFError → retry 2s → next key=success
```

### 环境变量

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

---

## 🧠 分析

### 参数逐项评估

| Parameter | Current | Change? | Reason |
|---|---|---|---|
| UPSTREAM_TIMEOUT | 70 | ❌ No | P50=18.3s, P95=48.0s << 70s。0次timeout截断。 |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ No | 2×70=140, 剩余16s充足。 |  
| KEY_COOLDOWN_S | 38 | ❌ No | KEY=TIER=38零gap, 0实际429。第12次R162验证。 |
| TIER_COOLDOWN_S | 38 | ❌ No | KEY=TIER=38对称不变式。 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ❌ No | 0次429, 请求率~2.6req/min远低于容量。 |
| HM_CONNECT_RESERVE_S | 24 | ❌ No | 0次budget_exhausted_after_connect。 |
| PROXY_TIMEOUT | 300 | ❌ No | 内部代理, 非瓶颈。 |

### 核心判定

**全7参数均衡收敛 — 无需变更。**

1. 30min/1h近乎完美(99.92%/99.84%), 0 ATE, 0 429, 0 fallback
2. ATE来自NVCF server-side PexecTimeout风暴(avg 141s), 配置无法阻止
3. KEY=TIER=38不变式持续192h+ (12轮R162验证)
4. SSLEOFErrors(2次)正常网络层波动, SSL-RETRY→next key成功恢复
5. 24h fallback被Pitfall #49旧regime数据淹没, 不应作为决策依据

---

## 📋 回合记录

| 回合 | 方向 | 变更 | 效果 |
|---|---|---|---|
| R162 | HM2→HM1 | KEY_COOLDOWN_S 34→38 | KEY=TIER=38 |
| R166 | HM2→HM1 | 无变更 | 第3次R162验证 |
| R167 | HM2→HM1 | 无变更 | 第4次R162验证 |
| R168 | HM2→HM1 | 无变更 | 第5次R162验证 |
| R171 | HM2→HM1 | 无变更 | 第7次R162验证 |
| R172 | HM2→HM1 | 无变更 | 第8次R162验证 |
| R173 | HM2→HM1 | 无变更 | 第9次R162验证 |
| R174 | HM2→HM1 | 无变更 | 第10次R162验证 |
| R175 | HM2→HM1 | 无变更 | 第11次R162验证 |
| **R176** | **HM2→HM1** | **无变更** | **第12次R162验证** |

---

## ⚖️ 评判

| 标准 | 状态 | 证据 |
|---|---|---|
| 更少报错 | ✅ | 30min 1次NVStream_IncompleteRead(无影响); 0 ATE 30min/1h |
| 更快请求 | ✅ | P50=18.3s, P95=48.0s — 优秀; per-key P50 17-19s |
| 超低延迟 | ✅ | 全key P95<54s, 远低于UPSTREAM_TIMEOUT=70s; 零429压力 |
| 稳定优先 | ✅ | KEY=TIER=38不变式192h+; 零fallback 6h+; 收敛均衡 |

**铁律**: 只改HM1不改HM2 — 本次无变更，铁律自动满足。

## ⏳ 轮到HM1优化HM2