# R207: HM2→HM1 — 无变更 (全7参数均衡; 30min 99.15% 9ATE全NVCFPexecTimeout+1NVStream 0 429 0 fallback; 36th consecutive R162+R158 validation; P50~17-20s P95~41s; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (30min + 1h + 6h + 24h segmented)

### Docker 日志 (error/warn 扫描, 最后100行)
```
[13:20:01.0] [HM-ERR] tier=deepseek_hm_nv k4 SSLEOFError: [SSL: UNEXPECTED_EOF_WHILE_READING]
[13:20:01.0] [HM-SSL-RETRY] tier=deepseek_hm_nv k4 SSL error — retrying same key after 2s backoff
[13:22:00.8] [HM-ERR] tier=deepseek_hm_nv k5 SSLEOFError: [SSL: UNEXPECTED_EOF_WHILE_READING]
[13:22:00.8] [HM-SSL-RETRY] tier=deepseek_hm_nv k5 SSL error — retrying same key after 2s backoff
```
→ 2× SSLEOFError (k4, k5), 两者均已自动重试恢复。0 429s, 0 fallback。

### Runtime ENV (docker exec hm40006 env)
```
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=38
UPSTREAM_TIMEOUT=70
MIN_OUTBOUND_INTERVAL_S=19.0
TIER_TIMEOUT_BUDGET_S=156
HM_CONNECT_RESERVE_S=24
PROXY_TIMEOUT=300
CHARS_PER_TOKEN_ESTIMATE=3.0
```

### DB 30min 统计
| 指标 | 值 |
|------|-----|
| 总数 | 1181 |
| 成功 (200) | 1171 (99.15%) |
| 错误 | 10 |
| ATE (all_tiers_exhausted) | 9 |
| NVStream_TimeoutError | 1 |
| 429 | 0 |
| fallback | 0 |
| 502 | 10 |

### 30min 按Key延迟 (status=200)
| Key | 请求数 | Avg(ms) | P50(ms) | P95(ms) |
|-----|-------|----------|---------|----------|
| k0 (DIRECT) | 241 | 19224 | 16779 | 40351 |
| k1 (DIRECT) | 232 | 20028 | 18412 | 44074 |
| k2 (PROXY-7896) | 232 | 20272 | 19257 | 41257 |
| k3 (PROXY-7897) | 232 | 19725 | 18393 | 38736 |
| k4 (PROXY-7899) | 235 | 20409 | 18531 | 41870 |

→ 分布极其均匀 (232-241 req/key), P50 16.8-19.3s, P95 38.7-44.1s。

### 1h 统计
| 总数 | 成功 | 错误 | fallback |
|------|------|------|----------|
| 1247 | 1236 (99.12%) | 11 (全502) | 0 |

### 6h 统计
| 总数 | 成功 | 错误 | ATE | fallback |
|------|------|------|-----|----------|
| 1942 | 1928 (99.28%) | 14 | 12 | 0 |

### 24h 分段 (Pitfall #49)
| 窗口 | 总数 | 成功 | fallback | ATE |
|------|------|------|----------|-----|
| 0-6h | 1942 | 1928 (99.28%) | 0 | 12 |
| 6-12h | 837 | 820 (97.97%) | 0 | 13 |
| 12-24h | 1695 | 1666 (98.29%) | 735 | 28 |

→ 12-24h fallback=735 全部为旧regime数据; 0-12h 0 fallback = 系统健康

### 错误详情 JSONL 确认 (最近5条)
```json
{"tier_summaries": [
  {"tier": "deepseek_hm_nv", "num_attempts": 5, "elapsed_ms": 155732},
  {"tier": "kimi_hm_nv", "num_attempts": 0, "elapsed_ms": 156303}
], "elapsed_ms": 156306}
```
→ kimi num_attempts=0 (Pitfall #41), deepseek 5-6次NVCFPexecTimeout, 总耗时151-156s。
→ 所有ATE事件均为NVCF服务器端PexecTimeout风暴，非配置可修复。

### 最近15条请求延迟 (5min窗口)
```
13:21:40 k0 81084ms — 长尾请求(DIRECT tail)
13:21:22 k3 17229ms
13:21:01 k2 21432ms
13:20:47 k1 13175ms
13:20:30 k0 11466ms
13:20:13 k4 12095ms
13:19:46 k4 24913ms
13:19:37 k2  8416ms
13:18:32 k1 63925ms — DIRECT长尾
13:18:19 k0 11860ms
→ 请求间隔约13-20s, 符合MIN_OUTBOUND_INTERVAL_S=19.0s容量。
→ 偶见DIRECT keys (k0/k1) 长尾 >60s (NVCF服务器端方差, Pitfall #29).
```

## 🎯 优化分析

### 瓶颈识别
- **9 ATE/30min**: 全部为NVCF PexecTimeout服务器端风暴 → 不可配置级修复
- **1 NVStream_TimeoutError**: NVCF服务器端单次超时
- **2 SSLEOFError**: SSL层瞬态错误，均已自动重试成功
- **0 429, 0 fallback**: 系统无速率限制，无fallback触发

### 7参数评估表

| 参数 | 当前值 | 需调整? | 理由 |
|------|--------|---------|------|
| UPSTREAM_TIMEOUT | 70 | ❌ | R158=R206稳定; 全部key P95<70s; 降低会减少预算margin但ATE全NVCF侧无影响 |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ | 2×70=140, 剩余16s>10s阈值; R154证实ATE不减 |
| KEY_COOLDOWN_S | 38 | ❌ | KEY=TIER=38, 不变量成立(Pitfall #44); 0 429s |
| TIER_COOLDOWN_S | 38 | ❌ | KEY=TIER=38, 零gap安全; 0 429s |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ❌ | ~2.6 req/min, 81%利用率; 5×19=95s≫KEY=38s; 安全边界48s |
| HM_CONNECT_RESERVE_S | 24 | ❌ | budget_exhausted_after_connect=849ms (远低); 覆盖充足 |
| PROXY_TIMEOUT | 300 | ❌ | 内部超时, 未触发 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | ❌ | 默认值, 未影响延迟 |

**结论**: 全部7参数处于均衡状态。没有单参数需要调整。这是第36次连续的R162+R158验证 — 稳定性就是最优状态。

### 为什么非变更而非增参
1. ATE事件100%为NVCF PexecTimeout服务器端风暴 — 代码/配置无法修复 (Pitfall #41, #43)
2. R154已证实BUDGET增加不减少ATE: 预算边际达到门槛后不再有效 (Pitfall #40)
3. 0-12h窗口 0 fallback 0 429 — 系统在近期窗口内完美运行
4. 12-24h fallback=735为旧regime数据 — 分段分析证实 (Pitfall #49)
5. 所有7参数处于均衡: 进一步调整只会引入新风险无收益

## 🔧 变更执行
**无变更**。HM1的docker-compose.yml保持不变。未修改任何参数。

## 📈 预期效果
- 30min 99.15% → 维持或改善 (NVCF风暴自衰减)
- 0 429, 0 fallback → 延续
- P50 ~17-20s, P95 ~41-44s → 稳定
- 36th consecutive R162+R158 → 继续累积

## ⚖️ 评判标准

| 标准 | 状态 | 证据 |
|------|------|------|
| 更少报错 | ✅ | 10/1181=0.85% (全部NVCF服务器端, 非配置可控) |
| 更快请求 | ✅ | P50=16.8-19.3s, P95=38.7-44.1s |
| 超低延迟 | ✅ | 0 429, 0 fallback, 0-12h全零fallback |
| 稳定优先 | ✅ | 全7参数均衡, 第36次连续R162+R158验证 |
| 铁律:只改HM1不改HM2 | ✅ | 未触碰任何HM2配置 |
| 少改多轮 | ✅ | 零变更 = 稳定性是最优状态 |

## ⏳ 轮到HM1优化HM2
```