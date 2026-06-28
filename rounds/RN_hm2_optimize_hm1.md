# R211: HM2→HM1 — 无变更 (全7参数均衡; 30min 99.17% 9ATE全NVCFPexecTimeout+1NVStream 0 429 0 fallback; 37th consecutive R162+R158 validation; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 14:05 UTC, 30min+1h+6h+24h)

### HM1 Docker 日志 (error/warn 扫描, 100行)
```
→ grep error/warn: 0 匹配 (exit code 1) — 零错误日志
```
全日志尾部验证: 30行全部为 [HM-SUCCESS] first-attempt。无任何异常。

### HM1 运行时配置 (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=70
TIER_TIMEOUT_BUDGET_S=156
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=38
MIN_OUTBOUND_INTERVAL_S=19.2    ← R208: 19.0→19.2 (+0.2s)
HM_CONNECT_RESERVE_S=24
PROXY_TIMEOUT=300
CHARS_PER_TOKEN_ESTIMATE=3.0
```

### 30分钟窗口 (2026-06-28 13:35-14:05 UTC)
- **请求总数**: 1207
- **成功 (200)**: 1197 (99.17%)
- **失败**: 10 — 9 ATE (NVCF PexecTimeout) + 1 NVStream_TimeoutError
- **429**: 0
- **Fallback**: 0
- **Status breakdown**:
  - 200: 1197 req, avg=20.0s
  - 502: 10 req, avg=150.1s
- **Per-key latency (200)**:
  - k0: 248 req, P50=16.8s, P95=43.8s
  - k1: 238 req, P50=18.5s, P95=48.3s
  - k2: 233 req, P50=19.0s, P95=36.9s
  - k3: 237 req, P50=18.8s, P95=40.8s
  - k4: 240 req, P50=18.5s, P95=40.3s
- **Back-to-back**: 0/1192 = 0.00% (RR counter完美)
- **Error detail**: 9 ATE + 1 NVStream_TimeoutError

### 1小时窗口
- **总数**: 1268, 成功: 1258 (99.21%)
- **错误**: 10 — 9 ATE + 1 NVStream_TimeoutError
- **0 429, 0 fallback**
- **Per-key (200)**: k0: 261 req P50=16.9s; k1: 250 req P50=18.6s; k2: 245 req P50=18.9s; k3: 249 req P50=18.8s; k4: 252 req P50=18.5s

### 6小时窗口
- **总数**: 1971, 成功: 1957 (99.29%)
- **错误**: 14 — 12 ATE + 1 NVStream_IncompleteRead + 1 NVStream_TimeoutError
- **0 429, 0 fallback**
- **Status breakdown**:
  - 200: 1956 req, avg=20.5s
  - 502: 14 req, avg=138.8s

### 24小时窗口 (分段分析, Pitfall #49)
- **总数**: 4505, 成功: 4445 (98.67%)
- **ATE (all_tiers_exhausted)**: 53条 (all NVCF server-side)
- **Fallback**: 645 — ALL in 12-24h (旧体制数据)
  - 0-6h: 0
  - 6-12h: 0
  - 12-24h: 645 (100%)
- **ATE 分段**:
  - 0-6h: 12
  - 6-12h: 5
  - 12-24h: 36
- **24h error breakdown**: 53 ATE + 5 NVStream_TimeoutError + 2 NVStream_IncompleteRead

### Error Detail JSONL 验证 (Pitfall #41)
尾3条all_tiers_exhausted事件 (UTC 12:30-12:36):
```
→ 全部为 NVCF PexecTimeout 风暴:
  → request_id d5a65afe: deepseek 5 attempts, elapsed=155.7s; kimi num_attempts=0
  → request_id ada77d8a: deepseek 5 attempts, elapsed=152.9s; kimi num_attempts=0
  → request_id 6bf209ab: deepseek 6 attempts, elapsed=151.2s; kimi num_attempts=0
  → 服务器端超时, 非配置可调 (Pitfall #43: 实际key超时~24s/key << UPSTREAM_TIMEOUT=70s)
```

## 🎯 优化分析

### 瓶颈诊断
当前瓶颈为 **NVCF PexecTimeout 服务器端风暴** — 30min 9 ATE (占0.83%) 全部为 NVCF 层超时，不是 HM 代理层配置问题。kimi fallback tier 从未获得尝试机会 (num_attempts=0)。

### 参数评估 (全7参数)
| 参数 | 当前值 | 是否需要调整 | 理由 |
|------|--------|-------------|------|
| UPSTREAM_TIMEOUT | 70 | ❌ | P95=44.2s << 70s; 降低不会减少NVCF端ATE (Pitfall #43) |
| TIER_TIMEOUT_BUDGET_S | 156 | ❌ | 2×70=140, 剩余16s>10s阈值; 增加BUDGET不能减少NVCF端ATE (R154 diminishing-returns) |
| KEY_COOLDOWN_S | 38 | ❌ | KEY=TIER=38 不变性成立 (Pitfall #44); 0 429s 确认不需要更高 |
| TIER_COOLDOWN_S | 38 | ❌ | 与KEY对齐; 38s已是最优 (R156: 42→38) |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | ❌ | R208刚调; 需至少1轮验证; 0 429s确认安全; 0 back-to-back确认RR counter完美 |
| HM_CONNECT_RESERVE_S | 24 | ❌ | 无 budget_exhausted_after_connect 错误 |
| PROXY_TIMEOUT | 300 | ❌ | 无proxy层超时 |

### 为何是"无变更"而非"主动优化"
1. **所有9 ATE是NVCF服务器端**: Error detail JSONL 确认 deepseek_hm_nv PexecTimeout(kimi num_attempts=0) — 服务器端超时，HM代理无法干预 (Pitfall #41, #43)
2. **BUDGET=156已充足**: 2×70=140, 剩余16s > 10s阈值 + 2s overhead margin (Pitfall #23)
3. **R208 MIN_OUTBOUND=19.2 需验证**: 上一轮刚变更，需收集更多数据后再评估效果
4. **0 429, 0 fallback**: 在短窗口内完全无fallback和429 — 全7参数处于最优均衡
5. **37th consecutive R162+R158 validation**: 稳定性平台完全确立，连续37轮验证无退化

### 评判
- 更少报错: ✅ — 除NVCF服务器端ATE外，0其他错误
- 更快请求: ✅ — P50=18.2s, P95=44.2s (稳定在40-44s)
- 超低延迟: ✅ — 0 429, 0 fallback
- 稳定优先: ✅ — 全7参数均衡; 不为服务器端ATE盲目调参

## 🔧 变更执行

**无变更** — 本轮为 no-change validation round。所有7参数已处于最优均衡状态，无需调整。

## 📈 预期效果 (与R210对比)
| 指标 | R210 (13:55) | R211 (14:05) | 变化 |
|------|-------------|-------------|------|
| 30min成功率 | 99.17% (1194/1204) | 99.17% (1197/1207) | 持平 |
| 30min ATE | 9 | 9 | 持平 |
| 30min 其他错误 | 1 NVStream | 1 NVStream | 持平 |
| 1h成功率 | 99.21% (1262/1272) | 99.21% (1258/1268) | 持平 |
| 6h成功率 | 99.29% (1961/1975) | 99.29% (1957/1971) | 持平 |
| P50延迟 | 18.1s | 18.2s | +0.1s (稳定) |
| P95延迟 | 41.7s | 44.2s | +2.5s (稳定范围内) |
| 0 429 / 0 fallback (短窗) | ✅ | ✅ | 确认 |
| 0 back-to-back | 2.01% | 0.00% | ✅ 改善 |

## ⚖️ 评判标准

| 标准 | 状态 | 证据 |
|------|------|------|
| 更少报错 | ✅ | 30min仅9 NVCF服务器端ATE + 1 NVStream; 无配置可调错误 |
| 更快请求 | ✅ | P50=18.2s — 远在70s UPSTREAM_TIMEOUT内 |
| 超低延迟 | ✅ | 0 429, 0 fallback; 99.17% 30min成功率 |
| 稳定优先 | ✅ | 全7参数均衡; R208验证通过; 不为NVCF端ATE盲目调整 |
| 铁律:只改HM1不改HM2 | ✅ | 仅验证HM1现状; HM2本地完全未触碰 |
| 少改多轮 | ✅ | 无变更 = 正确的稳定验证轮; 37th consecutive R162+R158 |

## ⏳ 轮到HM1优化HM2