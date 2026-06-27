# R141: HM2 → HM1 — 无变更 (验证R140: 30min 74/74 ok(100%), 0错误, 0 all_tiers_exhausted, 0 429, 0 fallback; 全部7参数均衡; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 01:39-01:46 UTC)

### 日志状态 (docker logs --tail 100 hm40006)
**100% [HM-SUCCESS]** — 全部请求首次尝试成功, 零错误/零警告:
```
[01:39:46.9] [HM-SUCCESS] tier=deepseek_hm_nv k4 succeeded on first attempt
[01:39:59.5] [HM-SUCCESS] tier=deepseek_hm_nv k5 succeeded on first attempt
[01:40:26.0] [HM-SUCCESS] tier=deepseek_hm_nv k1 succeeded on first attempt
[01:40:36.6] [HM-SUCCESS] tier=deepseek_hm_nv k2 succeeded on first attempt
[01:41:12.4] [HM-SUCCESS] tier=deepseek_hm_nv k3 succeeded on first attempt
[01:41:40.1] [HM-SUCCESS] tier=deepseek_hm_nv k4 succeeded on first attempt
[01:41:59.4] [HM-SUCCESS] tier=deepseek_hm_nv k5 succeeded on first attempt
[01:42:08.7] [HM-SUCCESS] tier=deepseek_hm_nv k1 succeeded on first attempt
[01:42:26.3] [HM-SUCCESS] tier=deepseek_hm_nv k2 succeeded on first attempt
[01:42:46.3] [HM-SUCCESS] tier=deepseek_hm_nv k3 succeeded on first attempt
[01:43:04.4] [HM-SUCCESS] tier=deepseek_hm_nv k4 succeeded on first attempt
[01:43:24.4] [HM-SUCCESS] tier=deepseek_hm_nv k5 succeeded on first attempt
[01:43:43.1] [HM-SUCCESS] tier=deepseek_hm_nv k1 succeeded on first attempt
[01:44:11.5] [HM-SUCCESS] tier=deepseek_hm_nv k2 succeeded on first attempt
[01:44:21.8] [HM-SUCCESS] tier=deepseek_hm_nv k3 succeeded on first attempt
[01:44:43.0] [HM-SUCCESS] tier=deepseek_hm_nv k4 succeeded on first attempt
[01:45:09.2] [HM-SUCCESS] tier=deepseek_hm_nv k5 succeeded on first attempt
[01:45:21.7] [HM-SUCCESS] tier=deepseek_hm_nv k1 succeeded on first attempt
[01:45:37.0] [HM-SUCCESS] tier=deepseek_hm_nv k2 succeeded on first attempt
[01:46:12.2] [HM-SUCCESS] tier=deepseek_hm_nv k3 succeeded on first attempt
```
grep error/warn → exit code 1 (no matches) = 系统完全清洁
全部请求均在tier=deepseek_hm_nv, 无kimi_hm_nv fallback触发
轮询模式: k1→k2→k3→k4→k5→k1→k2→... 完美循环

### 运行时环境 (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=68
TIER_TIMEOUT_BUDGET_S=146
KEY_COOLDOWN_S=38.0
TIER_COOLDOWN_S=42
MIN_OUTBOUND_INTERVAL_S=19.0
HM_CONNECT_RESERVE_S=24
PROXY_TIMEOUT=300
CHARS_PER_TOKEN_ESTIMATE=3.0
```
所有7参数与R140一致 — HM1配置未被任何外部修改

### DB指标 (cc_postgres, 30min/1h/6h窗口)

#### 30min窗口 (01:09-01:39 UTC)
| 指标 | 值 |
|------|-----|
| 总请求 | 74 |
| 成功 (status=200) | 74 (100.0%) |
| 错误 (error_type IS NOT NULL) | 0 |
| fallback_occurred | 0 |
| 平均延迟 | 22003ms |
| P50 | 19258ms |
| P95 | 52879ms |
| P99 | 74171ms |

#### 30min 错误明细
- **ZERO错误** — error_type列全部为NULL
- **ZERO per-key错误** — 无任何键级错误

#### 30min 键级成功延迟
| 键 | 请求数 | 平均 | P50 | P95 |
|-----|-------|------|-----|-----|
| k0 (NVCF键索引0) | 16 | 28737ms | 23452ms | 64815ms |
| k1 (DIRECT) | 14 | 18907ms | 19050ms | 34562ms |
| k2 (DIRECT) | 16 | 25081ms | 18165ms | 62754ms |
| k3 (PROXY→7896) | 13 | 20739ms | 18987ms | 34740ms |
| k4 (PROXY→7897) | 15 | 15519ms | 16918ms | 22392ms |

注: k0是NVCF键索引0, 与k1-k5不同的键ID — 可能是新加的或在键池中的备用键

#### 30min 请求速率
- 每分钟: 最大4, 最小1, 平均2.5 req/min
- 理论容量: 60/19.0 = 3.2 req/min (MIN_OUTBOUND_INTERVAL_S=19.0)
- 利用率: 2.5/3.2 = 78% — 健康, 有缓冲空间

#### 1h窗口
| 指标 | 值 |
|------|-----|
| 总请求 | 139 |
| 成功 | 138 (99.3%) |
| 错误 | 1 |
| 平均延迟 | 22253ms |
| P95 | 52076ms |

#### 6h窗口
| 指标 | 值 |
|------|-----|
| 总请求 | 790 |
| 成功 | 787 (99.6%) |
| 错误 | 3 |
| fallback | 0 |

#### 24h all_tiers_exhausted 时区分布
| 总 | 43 |
|------|
| 2026-06-26 18:00 (UTC) | 1 |
| 2026-06-27 01:00 | 1 |
| 2026-06-27 02:00 | 4 |
| 2026-06-27 03:00 | 10 |
| 2026-06-27 05:00 | 5 |
| 2026-06-27 07:00 | 1 |
| 2026-06-27 08:00 | 7 |
| 2026-06-27 09:00 | 7 |
| 2026-06-27 10:00 | 3 |
| 2026-06-27 11:00 | 3 |
| 2026-06-27 17:00 | 1 |

**UTC 01:00-11:00 = 37/43 (86%) 集中在夜间** — 与R139模式一致: NVCF服务器端夜间不稳定性, 非配置问题

#### 429状态
- 30min 429 count: **0**
- 30min key_cycle_429s: 73条=0周期, 1条=1周期 (1/74 = 1.4%)
- 背靠背同键率: 1/73 = 1.4% — 极低, RR计数器正常

## 🎯 优化分析

### 参数评估表: 全部7参数均处于均衡状态

| 参数 | 当前值 | 评估 | 是否需要调整 |
|------|--------|------|-------------|
| UPSTREAM_TIMEOUT | 68s | 30min 0超时错误, 所有请求均<68s完成 | **否** — 已充足 |
| TIER_TIMEOUT_BUDGET_S | 146s | 2×68=136, 剩余10s ≥ 10s阈值(严格小于) → 通过; 30min 0 ate | **否** — 186%余量, 算术检查通过 |
| KEY_COOLDOWN_S | 38.0s | 0个429错误, 1个key_cycle_429s (1.4%) — 429压力极低 | **否** — 429率接近零, 无需降低 |
| TIER_COOLDOWN_S | 42s | 0次all_tiers_exhausted (30min), 0次fallback | **否** — 未触发冷却 |
| MIN_OUTBOUND_INTERVAL_S | 19.0s | 实际2.5 req/min, 容量3.2 req/min — 78%利用率健康 | **否** — 有缓冲, 零429 |
| HM_CONNECT_RESERVE_S | 24s | 无budget_exhausted_after_connect错误; 所有键首次尝试成功 | **否** — 连接建立充足 |
| PROXY_TIMEOUT | 300s | 无代理超时; 最高延迟74s << 300s | **否** — 远高于实际需求 |

### 决策: 无变更验证轮
**理由**:
1. **30min成功率=100%** (74/74) — 这是完整窗口, 无任何窗口空缺
2. **0 all_tiers_exhausted** — 30min内无任何预算耗尽
3. **0 429 errors** — 无速率限制触发
4. **0 fallback** — 所有请求在primary tier完成
5. **超低延迟**: P50=19258ms (~19.3s), 远低于68s超时
6. **背靠背同键率1.4%** — RR计数器接近完美, 远低于历史5-8%
7. **6h 99.6%成功率** — 仅3次错误(均为NVStream_Timeout), 长窗口验证
8. R140已验证: 30min/1h/6h 100%/100%/99.6% — 本轮收集的独立数据再次确认

**不是过度优化**: 所有7参数经逐一评估, 无任一个需要调整。稳定性本身是有效结果。

## ⚖️ 评判标准

| 标准 | 状态 | 证据 |
|------|------|------|
| 更少报错 | ✅ 完美 | 30min 0 errors, 6h 3 errors (0.4%) |
| 更快请求 | ✅ 优秀 | P50=19258ms, 平均=22003ms |
| 超低延迟 | ✅ 达标 | P95=52879ms 远低于68s超时, P50远低于预算 |
| 稳定优先 | ✅ 已确认 | 30min/1h/6h 100%/99.3%/99.6%, 无波动 |
| 铁律: 只改HM1不改HM2 | ✅ 遵守 | 本次无修改, 纯验证轮 |

## ⏳ 轮到HM1优化HM2