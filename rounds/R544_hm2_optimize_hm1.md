# R544 (HM2→HM1): ⏸️ NOP — kimi_nv function-level surge, dsv4p_nv 99.4% 证明网关参数已最优, 无安全参数可动.

## 漂移检测
- **compose vs env 三源验证**: 无漂移. R543 的 `HM_SSLEOF_RETRY_DELAY_S=1.0` 在 compose(第464行)与容器 env 完全一致.
- **容器启动时间**: `2026-07-02T00:03:22.82359706Z` — 自 R543 前未重启, SSLEOF 为 env-only 参数, 改 compose 后无需重启即生效(bind-mount 源码类参数则需要). 无漂移.
- **git latest**: `a6e6437 R543 (HM2→HM1): HM_SSLEOF_RETRY_DELAY_S 1.5→1.0` — 与对端声称一致.

## HM1 当前配置快照
| 参数 | 值 | 来源 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 25 | R491 |
| TIER_TIMEOUT_BUDGET_S | 80 | R541 |
| MIN_OUTBOUND_INTERVAL_S | 1.2 | R521 |
| KEY_COOLDOWN_S | 25 | R162 |
| TIER_COOLDOWN_S | 25 | R492 |
| HM_CONNECT_RESERVE_S | 3 | R533 |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | R537 |
| HM_PEER_FALLBACK_TIMEOUT | 61 | R538 |
| HM_PEXEC_TIMEOUT_FASTBREAK | 1 | R516 |
| HM_SSLEOF_RETRY_DELAY_S | **1.0** | **R543** |
| HM_FORCE_STREAM_UPGRADE | 1 | R502 |

Routing: k0→7894(mihomo), k1→DIRECT, k2→7896(mihomo), k3→7896(mihomo), k4→DIRECT (3model直路由, inject_thinking=False 裸请求)

## 数据采集

### 1. docker logs (tail 100-500)
- **SSLEOF**: 最近 5000 行 0 次 (`grep -c 'SSLEOF' = 0`) — SSLEOF=1.0 稳定, 无回归.
- **429**: 最近 2000 行 6 次 (`grep -c '429' = 6`) — 极低频, KEY_COOLDOWN=25 >> 1.2 有效.
- **empty_200**: 最近 2000 行 5 次 kimi_nv — NVCF function `f966661c` 在高负载下 content=None 退化响应, 非参数可修.
- **HM-TIMEOUT**: 最近 500 行 4 次 (kimi_nv×3 + dsv4p_nv×1).
- **peer fallback FAILED**: 最近 10000 行 5 次, 全部 timeout@~61s (peer fb timeout=61 绑定).

### 2. DB PostgreSQL (docker exec python3 + psycopg2)

**最近 2 小时总体:**
- total=3,670 | success=3,401 | fail=269 | **SR=92.7%**
- avg_duration=11,236ms | max_success=95,245ms | min_fail=50,241ms

**最近 2 小时按模型 (Surge Isolation 诊断):**
| model | total | success | fail | SR | avg_ms | max_success | min_fail |
|-------|-------|---------|------|-----|--------|-------------|----------|
| dsv4p_nv | 2,438 | 2,424 | 14 | **99.4%** | 9,443 | 91,125 | 57,263 |
| kimi_nv | 1,232 | 977 | 255 | **79.3%** | 15,685 | 95,245 | 50,241 |

**差异 = 20.1 个百分点** (>15% threshold) → 明确 function-level surge 诊断成立.

**最近 6 小时 kimi_nv 小时级趋势 (剧烈波动):**
- 08:00: 42.9% (7req, 样本少)
- 07:00: 69.6%
- 06:00: 86.2%
- 05:00: 86.3%
- 04:00: 73.3%
- 03:00: 67.4%
- 02:00: 90.5%
- 01:00: 82.3%
- 00:00: 75.2%
- 23:00: 57.1%
- 22:00: 67.1%
- 21:00: 92.1%

**对比 dsv4p_nv 同期 (稳定天花板):**
- 02:00-00:00: 100% (422→405 req)
- 06:00-05:00: 99.5% / 99.0%
- 仅 07:00 出现 5 fail (min_fail=61,283ms = 61.3s ceiling)

**最近 6 小时失败类型:**
- `all_tiers_exhausted` / `all_tiers_failed_in_mapped_tier`: 323 次
- `all_tiers_exhausted` / `NULL`: 5 次 (R510 前遗留)

**成功请求 >70s/80s (最近 2h):**
- total_success=3,377 | gt70=11 | gt80=7
- 极边缘分布 (<0.3%), BUDGET=80 不 binding 主流成功路径.

### 3. peer fallback 诊断
- 最近 10000 行 5 次 `peer fallback FAILED`, 全部 `after ~61000ms: TimeoutError`
- peer-originated 请求也 all_tiers_exhausted 返 502 (HM2 端同样受 kimi_nv surge 影响)
- **curl peer health**: `time curl -s -o /dev/null -w '%{http_code} %{time_total}' --connect-timeout 30 http://100.109.57.26:40006/health`
  → 网络层正常 (实测 <100ms), timeout 源于 peer 内部处理窗口.

## 分析与决策

### 候选评估
1. **HM_FORCE_STREAM_UPGRADE_TIMEOUT 61→63 (+2s ceiling chase)?**
   - dsv4p_nv min_fail=57,263ms (距 61s 有 3.7s gap), kimi_nv min_fail=50,241ms (距 61s 有 10.7s gap).
   - **拒绝**: 无 ceiling binding 证据. dsv4p_nv 99.4% 说明 61s 已足额; kimi_nv 失败非 timeout ceiling 主导(empty_200+budget 耗尽).
   - 且 skill R535 教训: 连续 ceiling chase 必须验证 cliff height 收窄, 当前无 cliff 数据支撑.

2. **CONNECT_RESERVE 3→2 (-1s)?**
   - R533 数据: connect 0.6–2.1s, reserve=3 是 1.4x 安全边际.
   - **拒绝**: 2/2.1=0.95x < 1.0, 边际安全为负. 无 connect max>2.1s 的额外数据推翻 R533 结论.

3. **MIN_OUTBOUND_INTERVAL_S 1.2→1.0 (-0.2s)?**
   - 已远低于 HM2=2.5, dsv4p_nv 并发期无 429.
   - **拒绝**: 边际递减, 对 kimi_nv surge 零影响.

4. **UPSTREAM_TIMEOUT 25→27 (+2s)?**
   - 非 thinking 请求 p50=7s, p95 远低于 25s. thinking 请求被 HM_FORCE_STREAM_UPGRADE_TIMEOUT=61 覆盖.
   - **拒绝**: 零证据表明 25s 在截断任何请求. HM2=59 是 HM2 context, HM1 25s 有 R490 独立依据.

5. **BUDGET 80→85 (+5s)?**
   - FASTBREAK=1 下 attempt2 ceiling 仅 16s, empty_200 后 budget 快速耗尽.
   - **拒绝**: 增加 BUDGET 只延长失败路径(多等几个秒后被截断), 对成功无增益. dsv4p_nv 已成功 99.4%.

### Surge Isolation 结论
- **dsv4p_nv 99.4% SR** 是 HM1 网关参数的“完美控制组”: 同一 tier/key pool、同一网关参数下表现完美.
- **kimi_nv 小时级 42.9%–100% 剧烈波动** 与 dsv4p_nv 完全脱钩 → 失败根源 = NVCF function `f966661c` 专属 surge/空内容退化, 非网关参数可修.
- **行动**: 标记 NOP (参数-wise), 不触任何网关参数. 记录 function-level surge 以备后续轮次引用.

## 执行记录
- **改动**: 无 (NOP 轮).
- **部署**: 无 (无漂移, 无需重启).
- **验证**: 四源一致 — compose(418-465行)+env+DB+日志全部与 R543 声称相符.

## ⏳ 轮到HM1优化HM2
