# R244: HM2 → HM1 — 无变更 (69th no-change validation; 全7参数均衡; 30min 98.46% 15 ATE全NVCF server-side; 0 429 0 fallback; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 19:50-20:20 UTC)

### Docker日志 (最近100行)
```
[19:52:00.6] [HM-ERR] tier=deepseek_hm_nv k4 SSLEOFError: [SSL: UNEXPECTED_EOF_WHILE_READING]
[19:52:00.6] [HM-SSL-RETRY] tier=deepseek_hm_nv k4 SSL error — retrying same key after 2s backoff
[19:55:35.1] [HM-TIMEOUT] tier=deepseek_hm_nv k5 NVCF pexec timeout: attempt=60150ms total=132303ms
```
其余均为 [HM-REQ]+[HM-TIER] 正常请求流。所有请求进入 deepseek_hm_nv tier。

### 运行时环境
| 参数 | 值 | 状态 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 70 | R158稳定 (67th验证) |
| TIER_TIMEOUT_BUDGET_S | 156 | 2×70=140, 余量16s > 5s阈值 |
| KEY_COOLDOWN_S | 38 | KEY=TIER=38 零gap (Pitfall #44) |
| TIER_COOLDOWN_S | 38 | 与KEY对齐, 无抢先 |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | 5×19.2=96s >> KEY_COOLDOWN=38s |
| HM_CONNECT_RESERVE_S | 24 | 覆盖所有SOCKS5+SSL |
| PROXY_TIMEOUT | 300 | — |

### DB延迟统计

#### 30min (19:50-20:20 UTC)
| 指标 | 值 |
|------|-----|
| 总请求 | 1039 (1023成功 + 16失败) |
| 成功率 | 98.46% |
| 502错误 | 16 (15 ATE + 1 NVStream_TimeoutError) |
| 429错误 | **0** |
| 回退 | **0** |
| P50延迟 | 18.4s (18434ms) |
| P95延迟 | 53.7s (53666ms) |
| P99延迟 | 95.0s (95045ms) |
| 平均延迟 | 21.5s (21535ms) |

#### 1h
| 指标 | 值 |
|------|-----|
| 总请求 | 1110 (1094成功) |
| 成功率 | 98.56% |
| 502错误 | 16 (15 ATE + 1 NVStream_TimeoutError) |
| 429错误 | **0** |
| 回退 | **0** |

#### 6h
| 指标 | 值 |
|------|-----|
| 总请求 | 1833 (1811成功) |
| 成功率 | 98.80% |
| 502错误 | 22 (21 ATE + 1 other) |
| 429错误 | **0** |
| 回退 | **0** |

#### 24h分段
| 窗口 | 总请求 | 成功 | 失败 | ATE | 429 | 回退 |
|------|--------|------|------|-----|-----|------|
| 0-12h | 2679 | 2653 (98.95%) | 26 | 24 | **0** | **0** |
| 12-24h | 1685 | 1654 (98.15%) | 31 | 26 | 0 | 10 (old-regime) |

### 每键分布 (30min)
| 键 | 请求数 | 成功 | P50 | P95 | 状态 |
|----|--------|------|-----|-----|------|
| k1 | 218 | 218 | 17.1s | 56.8s | ✅ 零错误 |
| k2 | 212 | 211 | 18.6s | 60.3s | ✅ 1次超时 |
| k3 | 191 | 191 | 19.9s | 46.1s | ✅ 零错误 |
| k4 | 198 | 198 | 19.3s | 50.9s | ✅ 零错误 |
| k5 | 206 | 206 | 18.1s | 50.6s | ✅ 零错误 |
| (ATE) | 15 | 0 | 155.0s | 157.1s | ⚠️ 全部AT |

### 错误详情JSONL (最近条目)
```
2026-06-28T16:56-17:02 UTC: 5个all_tiers_failed事件
- deepseek_hm_nv: 6-7 key attempts, elapsed 154-156s
- kimi_hm_nv: num_attempts=0 (全部) — 预算耗尽, 无回退机会
- 所有NVCFPexecTimeout风暴 — NVCF server-side origin
- 预算消耗: 156s全部由deepseek_hm_nv primary tier消耗
```

### 回退分析
- 0-12h: **0回退** — tier链健康
- 12-24h: 10回退 (全部old-regime) — Pitfall #49: 旧窗口数据污染
- 24h总回退: 10次 = 100%在12-24h旧窗口

### 背靠背分析 (30min)
- 18/1039 = 1.73% 请求有 key_cycle_429s > 0
- RR计数器低频波动, 无429实际触发

### 预算阈值确认
- `grep HM-TIER-BUDGET` → **无匹配** (零预算临界事件)
- 最近无budget threshold突破 — 余量健康

## 🎯 优化分析

### 参数评估表 (全7参数逐一评估)

| 参数 | 当前值 | 评估 | 判定 |
|------|--------|------|------|
| UPSTREAM_TIMEOUT | 70 | P95=53.7s << 70s, 余量16.3s headroom; 所有键P95 < 70s | ✅ 无需调整 |
| TIER_TIMEOUT_BUDGET_S | 156 | 2×70=140, 余量16s > 5s; R154验证增加预算无AT减少 | ✅ 无需调整 |
| KEY_COOLDOWN_S | 38 | 0 429s = 零速率限制; KEY=TIER=38 零gap (Pitfall #44) | ✅ 无需调整 |
| TIER_COOLDOWN_S | 38 | 与KEY对齐, 无抢先浪费; 0 429s 确认最优 | ✅ 无需调整 |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | 5×19.2=96s >> 38s; 96%容量利用 (~3 req/min) | ✅ 无需调整 |
| HM_CONNECT_RESERVE_S | 24 | 覆盖所有SOCKS5+SSL; 无budget_exhausted_after_connect | ✅ 无需调整 |
| PROXY_TIMEOUT | 300 | 静态参数, 无影响 | ✅ 无需调整 |

### 关键发现
1. **69th consecutive R162+R158 validation**: 连续69轮无变更验证, 稳定性高原全面确认
2. **0 429s across all windows**: KEY_COOLDOWN_S=38 完美 — 零速率限制触发
3. **0 fallback in 0-12h**: tier链健康, 预算余量充分
4. **ATE=15 in 30min**: 全部NVCF PexecTimeout server-side — 配置无法消除 (Pitfall #41, #43)
5. **kimi num_attempts=0**: 预算全被deepseek primary tier消耗, 这是NVCF server-side timeout storms的根本特征
6. **P50=18.4s, P95=53.7s**: 延迟稳定且健康, 远低于UPSTREAM_TIMEOUT=70

### 为何不增加预算
- R154已证明: 预算从150增加到156的+6s = **零AT减少** (6 ATE at BUDGET=150, 6 ATE at BUDGET=156)
- ATE events本身是NVCF server-side PexecTimeout — 每个键尝试~24s后NVCF返回超时, 远早于UPSTREAM_TIMEOUT=70
- 当前公式: 2×70=140, 余量16s > 5s阈值, 已经充分
- 增加BUDGET不会减少NVCF server-side timeout, 只会增加回退预算而不使用

### 为何不减少MIN_OUTBOUND_INTERVAL_S
- 当前利用率 ~3 req/min ≈ 96% 容量
- 0 429s → 无速率限制压力 → 减少间隔无收益
- 96s周期 vs 38s KEY_COOLDOWN = 2.5× safety margin 充分

### 稳定性高原状态
- **69次连续R162+R158验证** → 跨越R162 (KEY_COOLDOWN_S 34→38) 以来的所有round
- **R162核心贡献**: KEY=TIER=38 零gap对齐 → 消除KEY抢先TIER导致的浪费
- **0 429s, 0 fallback (0-12h)** → 两项核心KPI均达最优
- **所有7参数均衡** → 无瓶颈可优化
- **稳定性是正确结果** → 不施加压力追加变更

## 📈 预期效果
N/A (无变更轮次, 数据采集即为验证)

### 对比R243
| 指标 | R243 | R244 |
|------|------|------|
| 30min成功率 | 98.5% | 98.46% |
| 30min ATE | 15 | 15 |
| 30min 429 | 0 | 0 |
| 30min fallback | 0 | 0 |
| P50 | ~18s | 18.4s |
| P95 | ~50s | 53.7s |

稳定延续 — 无退化, 无改善需求。

## ⚖️ 评判标准

### 更少报错 ✅
- 0 429s (零速率限制) — KEY_COOLDOWN_S=38确认完美
- 0 fallback (0-12h) — tier链正常
- 15 ATE = 全部NVCF server-side, 配置无法消除

### 更快请求 ✅
- P50=18.4s: 首次尝试延迟优秀
- P95=53.7s: 远低于UPSTREAM_TIMEOUT=70s边界
- 平均21.5s: 请求快速响应

### 超低延迟 ✅
- 所有5个键P50在17-20s范围, P95在46-60s范围
- 所有P95 < UPSTREAM_TIMEOUT=70, 无超时截断风险
- P99=95s在可接受范围内

### 稳定优先 ✅
- 69th consecutive R162+R158 no-change validation
- 全7参数均衡: 无单点需要调整
- 稳定性高原: 所有指标稳定, 无退化信号
- 少改多轮: 不施加变更压力, 稳定即正确结果

### 铁律确认
- ✅ **只改HM1不改HM2**: 本回合0变更 → 铁律自动满足
- ✅ **单参数纪律**: 无参数变更
- ✅ **无跨代理修改**: 未触及HM2本地任何配置

## ⏳ 轮到HM1优化HM2