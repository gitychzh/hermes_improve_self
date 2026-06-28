# RN: HM1 → HM2 优化 — 第N轮 (少改多轮)

**日期**: 2026-06-28  
**触发**: HM2 提交 R185 (HM2→HM1 全7参数均衡检出无变更)  
**规则**: 只改HM2配置, 绝不改HM1本地  
**评判标准**: 更少报错, 更快请求, 超低延迟, 稳定优先  

---

## 1. 数据采集 (HM2 30min窗口)

| 指标 | 值 | 评判 |
|------|----|------|
| 总请求 | 1468 | 高吞吐 |
| 成功 | 1462 (99.59%) | ✅ 良好 |
| all_tiers_exhausted | 6 (0.41%) | ⚠️ 需优化 |
| avg_ms | 18111 | |
| p50 | 13214 | |
| p95 | 50867 | |
| max | 192229 | |

**6h窗口**: 2449总请求, 2443成功 (同样6 ATE) — 确认无额外错误积累

**错误详情**:
- 6 ATE 全为 `all_tiers_exhausted` + `all_429=True` — glm5.1_hm_nv 5键全429
- 1 个 deepseek_hm_nv NVCFPexecTimeout: 860d1b9e, elapsed=145194ms (145.2s) — 精准命中 TIER_TIMEOUT_BUDGET_S=145
- kimi_hm_nv 也尝试了 (145190ms) 但亦超时
- RR counter: deepseek=5565, glm5.1=5776, kimi=132 (极小使用)

**HM2 当前配置** (第19轮验证):
```
MIN_OUTBOUND_INTERVAL_S: 13.8  # 5×13.8=69.0s cycle
KEY_COOLDOWN_S: 45
TIER_COOLDOWN_S: 45
TIER_TIMEOUT_BUDGET_S: 145
UPSTREAM_TIMEOUT: 71
HM_CONNECT_RESERVE_S: 24
```

**HM1 均衡配置** (基准, 不变):
```
MIN_OUTBOUND_INTERVAL_S: 19.0  # 5×19.0=95.0s cycle
KEY_COOLDOWN_S: 38
TIER_COOLDOWN_S: 38
TIER_TIMEOUT_BUDGET_S: 156
UPSTREAM_TIMEOUT: 70
HM_CONNECT_RESERVE_S: 24
```

---

## 2. 分析

**6 ATE 根因**: NVCF 端 5 键同时 429 率限制 (glm5.1_hm_nv)。30min 窗口内 99.59% 成功说明其余请求均通过 glm5.1→deepseek→kimi fallback 链处理。但 6 次 ATE 是当 NVCF 429 率限制完全饱和时，所有键同时进入 429 状态。

**429 机制**: 
- `KEY_COOLDOWN_S=45` — 每键 429 后 45s 冷却
- `MIN_OUTBOUND_INTERVAL_S=13.8` — 5 键 × 13.8 = 69s 全键循环
- 当高负载时, 5 键 69s 内循环完毕, 但 45s 冷却让键在 429 后不可用
- 69s - 45s = 24s 窗口: 键在 45s 冷却后可立即重试 → 大概率再次 429

**与 HM1 对比**:
- HM1 `MIN_OUTBOUND_INTERVAL_S=19.0` → 5×19=95s cycle → 95s-38s=57s 安全窗口 → 0 ATE, 0 429, 0 fallback
- HM2 `MIN_OUTBOUND_INTERVAL_S=13.8` → 5×13.8=69s cycle → 69s-45s=24s 安全窗口 → 6 ATE

**结论**: HM2 的 69s 键循环比 HM1 的 95s 快 37.7%, 但安全窗口只有 24s (HM1 有 57s)。需要略微增加 `MIN_OUTBOUND_INTERVAL_S` 以扩大安全窗口。

---

## 3. 优化 (第N轮, 单参数变更)

### 决策: 增加 `MIN_OUTBOUND_INTERVAL_S` 13.8 → 14.2 (+0.4s) → 5×14.2=71.0s

| 参数 | 旧值 | 新值 | 变化 | 理由 |
|------|------|------|------|------|
| **MIN_OUTBOUND_INTERVAL_S** | 13.8 | **14.2** | +0.4s (+2.9%) | 增加 5-key 间隔: 69s→71s (+2s). 安全窗口: 24s→26s (+8%). 减少 429 同时命中概率. |
| KEY_COOLDOWN_S | 45 | 45 | 不变 | 已对齐 TIER=45 |
| TIER_COOLDOWN_S | 45 | 45 | 不变 | 已收敛 |
| TIER_TIMEOUT_BUDGET_S | 145 | 145 | 不变 | 6 ATE 在 6h 窗口内不变, 145s 充足 |
| UPSTREAM_TIMEOUT | 71 | 71 | 不变 | 已匹配 HM1=70 |
| HM_CONNECT_RESERVE_S | 24 | 24 | 不变 | 已匹配 HM1=24 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | 3.0 | 不变 | 已匹配 HM1=3.0 |

**计算**:
- 5 键 × 14.2 = 71.0s 全键循环 (+2s)
- 安全窗口: 71s - 45s = 26s (+2s, +8.3%)
- 有效请求率降低: 1/14.2 = 4.23 req/min (vs 1/13.8=4.35, -2.9%)
- 给 NVCF 429 率限制引擎更多 refill 时间

**风险评估**: 极低。+0.4s 是 2.9% 增量, 对 99.59% 成功率的影响微乎其微。tier 失败率 (6/1468=0.41%) 在 6h 窗口内保持不变。

**少改多轮原则**: 单参数变更 (MIN_OUTBOUND_INTERVAL_S), 其余 6 参数不变。第 N 轮积累 → 等待 HM2 下一轮数据反馈。

---

## 4. 执行 (已完成)

1. ✅ **docker-compose.yml** 更新: `MIN_OUTBOUND_INTERVAL_S: "13.8"` → `"14.2"`
2. ✅ **docker compose up -d hm40006** — 容器已重建, 新配置生效
3. ✅ **健康检查**: HTTP 200
4. ✅ **验证**: `MIN_OUTBOUND_INTERVAL_S=14.2` (运行时确认)

---

## 5. 验证

| 参数 | 期望 | 实际 | 状态 |
|------|------|------|------|
| MIN_OUTBOUND_INTERVAL_S | 14.2 | 14.2 | ✅ |
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
| 数据驱动 | ✅ 30min DB, docker logs, env vars |

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记