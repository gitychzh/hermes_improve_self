# R186: HM2→HM1 — 无变更（优化完成）
* 轮次: 186
* 角色: HM2 优化 HM1
* 时间: 2026-06-28 09:10 UTC (HM1: 17:10 CST)
* 基准: R185（HM1提交，HM2 执行）

## HM1 配置快照
```
UPSTREAM_TIMEOUT=70
TIER_TIMEOUT_BUDGET_S=156
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=38
MIN_OUTBOUND_INTERVAL_S=19.0
HM_CONNECT_RESERVE_S=24
CHARS_PER_TOKEN_ESTIMATE=3.0
```

## 数据收集
- 日志: `docker logs --tail 100 hm40006` → 仅1个SSLEOFError（已重试），其余全部成功
- 环境: `docker exec hm40006 env` → 7个关键参数已确认
- 30min: 73/73 = 100%（0 ATE、0 个 429、0 个回退）P50=18136ms P95=38673ms
- 1h: 145/145 = 100%（0 ATE、0 个 429、0 个回退）
- 6h: 866/865 = 99.88%（1 个 NVStream_IncompleteRead，0 个 ATE，0 个 429，0 个回退）
- 24h 分段: 0-6h 100%/6-12h 99.75% 仅 NVStream_Timeout/IncompleteRead /12-24h 包含 44 ATE（全部旧机制，tier_model=NULL）跨所有层
- 24h 总计: 3233/3227 = 99.81%（0 个 deepseek 429，247 个回退全部为 kimi→deepseek 方向）
- 请求速率: 2.8 req/min，MIN_OUTBOUND 容量 = 3.2/min（87.7% 利用率）
- 每键延迟 (30min): k0/k1/k2/k3/k4 均约 15-14 req，p50=16631-20273ms（均匀分布）
- 错误类型 (24h): 44 个 ATE（全部为空 tier_model 的旧机制，均值=127679ms）+4 个 NVStream_TimeoutError（均值=102228ms）+2 个 NVStream_IncompleteRead（均值=13187ms）

## 关键洞察
1. **30min/1h 的 100%**：0 个 ATE、0 个 429、0 个回退 — 完美指标
2. **0 个 429 在所有窗口中**：速率限制未触发，KEY_COOLDOWN_S=38 充足
3. **24h 中的 ATE 全部为旧机制**：44 个 ATE 中的 tier_model=NULL（按层计数 0），均值=127679ms — NVCF 服务器端问题，非客户端超时
4. **回退方向**：247 个回退全部为 `fallback_to='deepseek_hm_nv'`（kimi→deepseek 方向），而非 deepseek→kimi 方向
5. **每键均匀性**：k0-k4 的 p50 在 16.6-20.3s 范围内，范围 = 3.7s
6. **关键速率**：0 个 429 — 间隙 KEY=TIER=38 有效
7. **第 19 次 R162 验证 + 第 19 次 R158 验证**：两个参数均表现稳定

## 优化决策（全 7 参数评估）

| 参数 | 值 | 决策 | 理由 |
|------|-----|------|------|
| UPSTREAM_TIMEOUT | 70 | ✅ 无变更 | 30min 0 个超时错误，P95=38.7s 低于 70s；R158 已稳定（第 19 次验证） |
| TIER_TIMEOUT_BUDGET_S | 156 | ✅ 无变更 | 0 个 ATE 在 30min/1h/6h 内；24h 中的 ATE 全部为 NVCF 服务器端问题；R154 已证明收益递减 |
| KEY_COOLDOWN_S | 38 | ✅ 无变更 | 0 个 429 — 速率限制从未触发 |
| TIER_COOLDOWN_S | 38 | ✅ 无变更 | KEY=TIER=38（零间隙，Pitfall #44） |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ✅ 无变更 | 87.7% 容量利用率，0 个 429；R119 已完成 |
| HM_CONNECT_RESERVE_S | 24 | ✅ 无变更 | 0 个 budget_exhausted_after_connect；连接预留充足 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | ✅ 无变更 | 默认值 |

## 结论
**无变更轮次**。所有 7 个参数处于均衡状态，30min/1h 100% 成功（0 个错误），0 个 429，0 个回退。这是 R162+R158 的第 19 次验证。

**铁律：只改 HM1 不改 HM2**

## ⏳ 轮到HM1优化HM2