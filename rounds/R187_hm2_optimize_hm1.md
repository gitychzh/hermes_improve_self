# R187: HM2→HM1 — 无变更 (全7参数均衡; 第20次R162验证+第20次R158验证; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 09:15-09:45 UTC)

### 30min 窗口 (1224 total, 99.67% 成功率)
| 指标 | 值 |
|------|-----|
| 总请求 | 1224 |
| 成功 (status=200) | 1220 |
| 错误 | 4 (3 ATE + 1 NVStream_IncompleteRead) |
| 429 错误 | 0 |
| 回退 (fallback_occurred) | 0 |
| P50 延迟 | 18.3s |
| P90 延迟 | 35.0s |
| P95 延迟 | 46.9s |
| P99 延迟 | 74.8s |
| 平均延迟 | 20.7s |

### 1h 窗口 (1291 total, 99.69% 成功率)
- **成功**: 1287/1291, ATE: 3, 其他错误: 1, Fallback: 0, 429: 0

### 6h 分割窗口 (Pitfall #49 — 24h fallback 被旧 regime 数据支配)
| 窗口 | 总数 | 成功 | ATE | Fallback |
|------|------|------|-----|----------|
| 0-6h | 1923 | 1913 (99.48%) | 6 | 0 |
| 6-12h | 995 | 973 (97.79%) | 20 | 0 |
| 12-24h | 1701 | 1682 (98.88%) | 19 | 1292 (旧 regime) |

### 24h 总体
- **总计**: 4619, OK: 4568 (98.86%), ATE: 45, HTTP 429: 5, FB: 1291
- **Fallback 来源**: glm5.1_hm_nv→deepseek_hm_nv (1274, 旧 regime), deepseek→kimi (15), kimi→deepseek (2)
- **ATE 全为 NVCF 服务器侧** (Pitfall #30/Pitfall #41): 所有 45 个 ATE 都有 kimi num_attempts=0

### 错误详情 (30min)
```
all_tiers_exhausted: 3 次, avg=145.2s → NVCF PexecTimeout 风暴
NVStream_IncompleteRead: 1 次, 6.8s → 网络瞬断
```
JSONL 确认：deepseek_hm_nv 消耗 141-146s 跨越 6 次 key 尝试，kimi_hm_nv num_attempts=0 (Pitfall #41)

### 每 Key 延迟分布 (30min, deepseek_hm_nv)
| Key | 请求数 | P95 成功延迟 | 错误 |
|-----|--------|-------------|------|
| k0 (DIRECT) | 245 | 47.6s | 0 |
| k1 (DIRECT) | 243 | 48.4s | 0 |
| k2 (PROXY 7896) | 239 | 41.1s | 0 |
| k3 (PROXY 7897) | 243 | 50.3s | 1 (NVStream) |
| k4 (PROXY 7899) | 252 | 47.1s | 0 |

✅ 所有 key P95 都远低于 UPSTREAM_TIMEOUT=70s (安全余量 19-29s)

### 请求速率 (~2.5 req/min, 75% MIN_OUTBOUND 容量)
- 每分钟 1-4 请求，平均 ~2.5 req/min
- MIN_OUTBOUND_INTERVAL_S=19.0 → 理论容量 3.2 req/min
- 实际利用率 75% — 充足余量

### Docker 日志 (最近 30 行)
```
[09:19-09:21] 全部 [HM-SUCCESS] — k1, k2, k3, k4, k5 轮转正常
无 error/warn/fail/timeout/exhausted 输出
```
✅ 零错误日志 (Pitfall #21 确认：grep exit code 1 = 无匹配)

### 运行时 Env
```
UPSTREAM_TIMEOUT=70             (R158, 第 20 次验证)
TIER_TIMEOUT_BUDGET_S=156       (R152, 验证)
KEY_COOLDOWN_S=38               (R162, KEY=TIER=38 对齐)
TIER_COOLDOWN_S=38              (KEY≥TIER 不变量成立)
MIN_OUTBOUND_INTERVAL_S=19.0    (R119, 验证)
HM_CONNECT_RESERVE_S=24         (R111, 验证)
PROXY_TIMEOUT=300                (固定)
CHARS_PER_TOKEN_ESTIMATE=3.0    (固定)
```

## 🎯 优化分析

### 全 7 参数均衡评估

| 参数 | 当前值 | 评估 | 结论 |
|------|--------|------|------|
| UPSTREAM_TIMEOUT | 70 | ✅ P95 全 key < 50s, 远低于 70s; 0 429; 0 fallback 在 0-12h | 无需调整 |
| TIER_TIMEOUT_BUDGET_S | 156 | ✅ 2×70=140, 余量=16s > 10s 阈值; 0 ATE 由预算不足引起 | 无需调整 |
| KEY_COOLDOWN_S | 38 | ✅ KEY=TIER=38 (零 gap, 不变量成立; Pitfall #44) | 无需调整 |
| TIER_COOLDOWN_S | 38 | ✅ = KEY (同步恢复, 无浪费尝试) | 无需调整 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ✅ 0 429s; 75% 容量利用率; 5-key 周期 95s >> KEY=38s | 无需调整 |
| HM_CONNECT_RESERVE_S | 24 | ✅ 无 budget_exhausted_after_connect; 覆盖所有 key | 无需调整 |
| PROXY_TIMEOUT | 300 | ✅ 固定值, 无超时相关错误 | 无需调整 |

### 为什么不调整任何参数

1. **R162 (KEY_COOLDOWN=38) 已验证 19 次连续轮次** → R187 是第 20 次: KEY=TIER=38 的对齐是长期正确配置
2. **R158 (UPSTREAM_TIMEOUT=70) 已验证 19 次连续轮次** → 70s 在 0-12h 窗口产生 0 fallback, 0 429
3. **3 个 ATE/30min 全部是 NVCF 服务器侧** → 无法通过配置修复 (Pitfall #30, #41)
4. **24h fallback (1292) 完全集中在 12-24h 旧 regime 窗口** → Pitfall #49 证实: 分割窗口显示 0-12h 零 fallback
5. **稳定性本身就是最优状态** → 过度优化会引入新风险

### 预算数学验证
- 2×70=140, BUDGET=156, 余量=16s > 10s 阈值 ✅
- KEY=TIER=38 不变量: KEY ≥ TIER (38 ≥ 38) ✅
- 5-key 周期: 5×19.0=95s >> KEY_COOLDOWN=38s ✅
- 实际 ATE 全部是 NVCF 服务器侧 PexecTimeout, 非 HM 配置可防 ✅

## 🔧 变更执行

**无变更** — 全 7 参数保持当前值。

### HM1 docker-compose.yml 确认 (hm40006 段)
```
UPSTREAM_TIMEOUT: "70"
TIER_TIMEOUT_BUDGET_S: "156"
KEY_COOLDOWN_S: "38"
TIER_COOLDOWN_S: "38"
MIN_OUTBOUND_INTERVAL_S: "19.0"
HM_CONNECT_RESERVE_S: "24"
PROXY_TIMEOUT: "300"
```

## 📈 预期效果

R187 延续 R186 的稳定轨迹：
- 30min: 维持 99.5-100% 成功率
- 1h: 维持 99.5-100% 成功率
- 0 429s, 0 预算引起的 ATE
- NVCF 服务器侧 ATE 持续存在但不可防

## ⚖️ 评判标准

| 标准 | 状态 | 证据 |
|------|------|------|
| 更少报错 | ✅ | 30min 4 错误 (3 ATE NVCF 服务器侧 + 1 网络瞬断) |
| 更快请求 | ✅ | P50=18.3s, P95=46.9s — 全部在健康范围 |
| 超低延迟 | ✅ | P50 持续 ~18s, 无退化 |
| 稳定优先 | ✅ | 20 次连续 R162+R158 验证 — 均衡平稳 |

**铁律确认**: ✅ 只改 HM1 不改 HM2 — 本回合无变更 (HM1 配置未动, HM2 本地配置完全未接触)

## 📝 回合号与 Git 历史

- **R186** (前轮): HM2→HM1 无变更 (第 19 次 R162+R158 验证)
- **R185**: HM2→HM1 无变更 (第 19 次 R162+R158 验证)
- **R187** (本轮): HM2→HM1 无变更 — 第 20 次 R162+R158 验证
- **`cbaf3e7`**: HM1→HM2 — MIN_OUTBOUND_INTERVAL_S 13.8→14.2 (HM1 优化 HM2, 已响应)

## ⏳ 轮到HM1优化HM2