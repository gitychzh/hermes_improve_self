# RN: HM1 → HM2 优化 — 第N轮 (少改多轮)

**日期**: 2026-06-28  
**触发**: HM2 提交 R187 (HM2→HM1 全7参数均衡检出无变更)  
**规则**: 只改HM2配置, 绝不改HM1本地  
**评判标准**: 更少报错, 更快请求, 超低延迟, 稳定优先  

---

## 1. 数据采集 (HM2 30min窗口)

| 指标 | 值 | 评判 |
|------|----|------|
| 总请求 | 1465 | 高吞吐 |
| 成功 | 1459 (99.59%) | ✅ 良好 |
| all_tiers_exhausted | 6 (0.41%) | ⚠️ 需优化 |
| avg_ms | 18129 | |
| p50 | 13390 | |
| p95 | 50887 | |

**1h窗口**: 1535总请求, 1529成功 (99.61%) — 同样6 ATE  
**6h窗口**: 2411总请求, 2405成功 (99.75%) — 无额外积累

**错误详情**:
- 6 ATE 全为 `all_tiers_exhausted` + 全glm5.1_hm_nv 5键429
- Error detail JSONL: 70% `all_429: true` (function-level), 30% 含SSLEOFError混入
- 0 NVCFPexecTimeout, 0 NVCFPexecConnectionReset, 0 NVStream_IncompleteRead
- 73 SSLEOFError (key级, 非请求级), 9 empty_200
- 705 fallback: 全部 glm5.1_hm_nv → deepseek_hm_nv (0个到kimi)
- Key级429: k0=324, k1=258, k2=242, k3=242, k4=213 = 1279 total
- RR counter: deepseek=5619, glm5.1=5816, kimi=132

**HM2 当前配置** (R186确认):
```
MIN_OUTBOUND_INTERVAL_S: 14.2
KEY_COOLDOWN_S: 45
TIER_COOLDOWN_S: 45
TIER_TIMEOUT_BUDGET_S: 145
UPSTREAM_TIMEOUT: 71
HM_CONNECT_RESERVE_S: 24
```

**HM1 均衡配置** (基准, 不变):
```
MIN_OUTBOUND_INTERVAL_S: 19.0
KEY_COOLDOWN_S: 38
TIER_COOLDOWN_S: 38
TIER_TIMEOUT_BUDGET_S: 156
UPSTREAM_TIMEOUT: 70
HM_CONNECT_RESERVE_S: 24
```

---

## 2. 分析

**6 ATE 根因**: NVCF 端 5 键同时 429 率限制 (glm5.1_hm_nv)。30min 窗口内 99.59% 成功说明其余请求均通过 glm5.1→deepseek fallback 链处理。但 6 次 ATE 是当 NVCF 429 率限制完全饱和时，所有键同时进入 429 状态。

**429 机制**: 
- `KEY_COOLDOWN_S=45` — 每键 429 后 45s 冷却 (=== GLOBAL_COOLDOWN=45)
- `MIN_OUTBOUND_INTERVAL_S=14.2` — 5 键 × 14.2 = 71s 全键循环
- 当高负载时, 5 键 71s 内循环完毕, 但 45s 冷却让键在 429 后不可用
- 71s - 45s = 26s 安全窗口: 键在 45s 冷却后可立即重试 → 大概率再次 429

**与 HM1 对比**:
- HM1 `MIN_OUTBOUND_INTERVAL_S=19.0` → 5×19=95s cycle → 95s-38s=57s 安全窗口 → 0 ATE, 0 429, 0 fallback
- HM2 `MIN_OUTBOUND_INTERVAL_S=14.2` → 5×14.2=71s cycle → 71s-45s=26s 安全窗口 → 6 ATE

**结论**: HM2 的 71s 键循环比 HM1 的 95s 快 34%, 但安全窗口只有 26s (HM1 有 57s)。需要略微增加 `MIN_OUTBOUND_INTERVAL_S` 以扩大安全窗口。KEY_COOLDOWN_S=45 和 TIER_COOLDOWN_S=45 已收敛至GLOBAL=45s, 唯一的活动参数是 MIN_OUTBOUND_INTERVAL_S。

---

## 3. 优化 (第N轮, 单参数变更)

### 决策: 增加 `MIN_OUTBOUND_INTERVAL_S` 14.2 → 14.6 (+0.4s) → 5×14.6=73.0s

| 参数 | 旧值 | 新值 | 变化 | 理由 |
|------|------|------|------|------|
| **MIN_OUTBOUND_INTERVAL_S** | 14.2 | **14.6** | +0.4s (+2.8%) | 增加 5-key 间隔: 71s→73s (+2s). 安全窗口: 26s→28s (+7.7%). 减少 429 同时命中概率. |
| KEY_COOLDOWN_S | 45 | 45 | 不变 | 已收敛至GLOBAL=45 |
| TIER_COOLDOWN_S | 45 | 45 | 不变 | 已收敛至GLOBAL=45 |
| TIER_TIMEOUT_BUDGET_S | 145 | 145 | 不变 | 145s 充足, 无预算断裂事件 |
| UPSTREAM_TIMEOUT | 71 | 71 | 不变 | p95=50.9s < 71s, 充足 |
| HM_CONNECT_RESERVE_S | 24 | 24 | 不变 | 已匹配 HM1=24 |

**计算**:
- 5 键 × 14.6 = 73.0s 全键循环 (+2s from 71s)
- 安全窗口: 73s - 45s = 28s (+2s, +7.7%)
- 有效请求率: 1/14.6 = 4.11 req/s (vs 1/14.2=4.23, -2.8%)
- 给 NVCF 429 率限制引擎更多 refill 时间

**风险评估**: 极低。+0.4s 是 2.8% 增量, 对 99.59% 成功率的影响微乎其微。6个ATE在6h窗口中保持不变。

**少改多轮原则**: 单参数变更 (MIN_OUTBOUND_INTERVAL_S), 其余6参数不变。第N轮积累 → 等待HM2下一轮数据反馈。

---

## 4. 执行 (已完成)

1. ✅ **docker-compose.yml** 更新: `MIN_OUTBOUND_INTERVAL_S: "14.2"` → `"14.6"`
2. ✅ **docker compose up -d hm40006** — 容器已重建, 新配置生效
3. ✅ **健康检查**: HTTP 200, tiers: ['glm5.1_hm_nv', 'deepseek_hm_nv', 'kimi_hm_nv'], default: glm5.1_hm_nv
4. ✅ **验证**: `MIN_OUTBOUND_INTERVAL_S=14.6` (运行时确认)
5. ✅ **mihomo**: PID 2008535, 持续运行

---

## 5. 验证

| 参数 | 期望 | 实际 | 状态 |
|------|------|------|------|
| MIN_OUTBOUND_INTERVAL_S | 14.6 | 14.6 | ✅ |
| KEY_COOLDOWN_S | 45 | 45 | ✅ |
| TIER_COOLDOWN_S | 45 | 45 | ✅ |
| TIER_TIMEOUT_BUDGET_S | 145 | 145 | ✅ |
| UPSTREAM_TIMEOUT | 71 | 71 | ✅ |
| HM_CONNECT_RESERVE_S | 24 | 24 | ✅ |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | 3.0 | ✅ |

---

## 6. 铁律

| 规则 | 遵守 |
|------|------|
| 只改 HM2 配置 | ✅ 1 参数变更 |
| 绝不改 HM1 本地 | ✅ HM1 配置不变 |
| 不得停止 mihomo | ✅ mihomo 持续运行 (PID 2008535) |
| 少改多轮 | ✅ 单参数, +0.4s |
| 数据驱动 | ✅ 30min DB, docker logs, host logs, env vars |

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记