# R245: HM1→HM2 — 无变更 (70th no-change verification)

**回合类型**: 验证/无变更
**角色**: HM1 (opc_uname) → 优化 HM2 (opc2_uname)
**时间**: 2026-06-28 20:11 UTC+8
**原则**: 更少报错 更快请求 超低延迟 稳定优先 · 铁律: 只改HM2不改HM1

---

## 📊 数据采集 (HM2 — hm-40006 链路)

### Docker 日志 (最近100行, 关注 error/warn)
```
[20:08:09.2] [HM-ERR] tier=deepseek_hm_nv k1 SSLEOFError: [SSL: UNEXPECTED_EOF_WHILE_READING]
[20:11:02.7] [HM-ERR] tier=deepseek_hm_nv k1 SSLEOFError: [SSL: UNEXPECTED_EOF_WHILE_READING]
```
→ 2 deepseek SSLEOF events in recent 3 minutes (偶发, NVCF SSL/TLS协议层)

### 运行容器环境变量 (docker exec hm40006 env | sort)
| 参数 | 值 | 说明 |
|------|-----|------|
| KEY_COOLDOWN_S | 38 | 每key 429 后冷却 |
| TIER_COOLDOWN_S | 45 | 全key失败后冷却 |
| UPSTREAM_TIMEOUT | 63 | 每key上游超时(ceiling) |
| MIN_OUTBOUND_INTERVAL_S | 15.6 | 最小请求间隔 |
| TIER_TIMEOUT_BUDGET_S | 115 | 总预算容纳 |
| HM_CONNECT_RESERVE_S | 24 | 连接建立预留 |
| PROXY_TIMEOUT | 300 | 代理总超时 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | token估算 |
| HM_DEFAULT_NV_MODEL | deepseek_hm_nv | 默认路由模型 |
| HM_NV_MODEL_TIERS | [deepseek_hm_nv, glm5.1_hm_nv, kimi_hm_nv] | 3个tier |

### DB — 30min 请求窗口 (1217 总请求)
```
总量: 1217 req | 成功: 1211 | 成功率: 99.51%
avg_ms: 22702 (deepseek outliers 拉高均值)

Tier 分布:
  deepseek_hm_nv: 1131 req (92.9%) | 1 fail | fallbacks=205
  glm5.1_hm_nv:    81 req (6.7%)  | 0 fail | fallbacks=5  (100% 成功!)
  kimi_hm_nv:       0 req (0%)     | 0 fail | num_attempts=0 确认
  null_tier:        5 req (0.4%)   | 5 ATE (fallthrough all tiers)
```

### 错误类型 (30min, 6 failures)
```
all_tiers_exhausted:   5 (NVCFPexecTimeout → 全3层排气)
NVStream_TimeoutError:  1 (NVCF stream-level timeout)
```

### 10min 突发窗口 (对比)
```
总量: 1177 req | 成功: 1172 | 成功率: 99.58%
5 failures: 4 ATE + 1 NVStream_TimeoutError
→ 30min/10min 窗口匹配, 无近期劣化
```

### 每key 429 (glm5.1 tier, 30min)
```
k0=71, k1=81, k2=85, k3=83, k4=88 → 408 total
分布: 1.24× range (71-88) — 全部5个key均衡
→ 函数级速率限制 (无单key不平衡)
```

### 错误详情 JSONL (最后20行, 13:41-18:39)
深度分析:
- **all_429:true**: 7/20 lines (35%) — 纯函数级429饱和
- **all_429:false + mixed**: 13/20 lines (65%) — SSLEOF + 429 + ConnectionReset混合
- deepseek tier: 全NVCFPexecTimeout (server-side, 10-62s per key)
- glm5.1 tier: SSLEOF (5005-15126ms) + 429 + ConnectionReset混合
- kimi tier: num_attempts=0 (无尝试, 直接跳过)
- **all_tiers_failed**: 2 requests (91442201 at 17:05, 8fcf7308 at 18:39) — 全3层排气后放弃

### 回合预算折断 (HM-TIER-BUDGET, 今日15事件)
```
[06:54] remaining 1.0s  <10s | [07:29] remaining 7.4s  <10s
[08:48] remaining 1.2s  <10s | [08:52] remaining 1.5s  <10s
[09:38] remaining 0.8s  <10s | [12:03] remaining 1.5s  <10s
[12:19] remaining 5.9s  <10s | [12:22] remaining 6.6s  <10s
[14:10] remaining 7.8s  <10s | [14:26] remaining 8.4s  <10s
[15:26] remaining 8.6s  <10s | [15:42] remaining 8.6s  <10s
[17:05] remaining 7.6s  <10s | [17:23] remaining 8.3s  <10s
[18:39] remaining 1.8s  <10s
```
→ 全 deepseek tier, budget=111-145s, 剩余 0.8-8.6s 均 <10s minimum
→ 典型 NVCFPexecTimeout 消耗模式 (每timeout 10-62s)

### 回落模式 (30min, 205 fallback events)
```
glm5.1_hm_nv → deepseek_hm_nv: 194 (94.6%) — 主力回落
kimi_hm_nv → deepseek_hm_nv: 6 (2.9%) — 少量
deepseek_hm_nv → glm5.1_hm_nv: 5 (2.4%) — 反向回落
```
→ 回落系统健康, 194个glm5.1请求通过deepseek成功(100% glm5.1 tier success)

### RR 计数器 (host volume)
```json
{"hm_nv_deepseek": 6884, "hm_nv_kimi": 145, "hm_nv_glm5.1": 6101}
```
→ 累计请求正常, 无异常

---

## 📈 分析

### 判断: 无变更验证

**99.51% 成功率** (1211/1217) 在 30min 窗口 — 所有 6 个失败来自 NVCF 服务器端:
- 5×ATE: NVCFPexecTimeout (server-side timeout, 不可配置)
- 1×NVStream_TimeoutError: NVCF stream 超时 (server-side, 不可配置)
- **0 client-side configurable errors**: 无 KEY_COOLDOWN_S 相关误伤, 无 MIN_OUTBOUND_INTERVAL_S 导致超时

**全7参数均衡**: 所有参数处于已验证的收敛目标
- KEY_COOLDOWN_S=38 (配 GLOBAL=45s, R233 收敛)
- TIER_COOLDOWN_S=45 (已到 GLOBAL_COOLDOWN=45s, 无进一步上升空间)
- UPSTREAM_TIMEOUT=63 (ceiling, R239 +4s 到 63)
- MIN_OUTBOUND_INTERVAL_S=15.6 (R206 收敛, 429 风暴间距优化)
- TIER_TIMEOUT_BUDGET_S=115 (15 个预算折断但全为 deepseek 外部超时)
- HM_CONNECT_RESERVE_S=24 (跨机器对齐 HM1=24, R205 收敛完成)
- PROXY_TIMEOUT=300 (固定, 未调整)

**10min/30min 窗口匹配**: 
- 30min: 99.51%, 6 failures → 10min: 99.58%, 5 failures
- 无近期劣化, 稳态验证

**回落健康**: 194 个 glm5.1→deepseek 回落全部成功 (glm5.1 tier 100% user-level success)

**kimi tier 零尝试**: num_attempts=0 (无请求, 无错误, 无需调整)

**预算折断 15 事件**: 全 deepseek NVCFPexecTimeout (server-side), 非可配置参数导致。remaining 0.8-8.6s 都在 10s 阈值以下 — 典型的 deepseek 超时消耗模式, 增加 TIER_TIMEOUT_BUDGET_S 不会改善 (因为每个 timeout 已经消耗 10-62s)

**铁律检查**: 未触及 HM2 任何配置 ✅ | mihomo 运行中 (PID 2008535) ✅ | 健康端点 ok ✅

### 为什么不是其他参数 (全7参数排除)

| 参数 | 当前值 | 为什么不调 |
|------|--------|-----------|
| KEY_COOLDOWN_S | 38 | 已到 GLOBAL=45 收敛, 38-45 gap=7s 但有 408×429 全函数级, 增 KEY 无收益 |
| TIER_COOLDOWN_S | 45 | 已到 GLOBAL_COOLDOWN=45s, 无法再上升(硬编码) |
| UPSTREAM_TIMEOUT | 63 | ceiling, 增会浪费 deepseek 慢请求后的 budget, 不减(deepseek p95 需要) |
| MIN_OUTBOUND_INTERVAL_S | 15.6 | 15.6 已足够间距, 429 全函数级不是单key, 增间隔无收益 |
| TIER_TIMEOUT_BUDGET_S | 115 | 15 预算折断全 deepseek NVCFPexecTimeout(外部), 增预算不解决根本问题 |
| HM_CONNECT_RESERVE_S | 24 | 已对齐 HM1=24 (跨机器收敛完成, R205), 无 gap |
| PROXY_TIMEOUT | 300 | 固定值, 目前无超时 |

---

## 执行: 无变更

**验证轮次** — 所有可观测窗口显示 ≥99% 用户成功率, 残留错误全外部 NVCF server-side。全7参数均衡收敛。回落系统健康。铁律: 只改HM2不改HM1 — 且 HM2 无人为配置错误需纠正。

### 验证清单
1. ✅ `docker exec hm40006 env | grep KEY_COOLDOWN_S` → 38 (正确)
2. ✅ `docker ps --filter name=hm40006` → Up (healthy)
3. ✅ `curl -s http://100.109.57.26:40006/health` → ok, 3 tiers
4. ✅ `pgrep -a mihomo` → PID 2008535, 运行中
5. ✅ `tail -1 rounds/RN_hm1_optimize_hm2.md` → 标记就位
6. ✅ 30min 99.51% 成功率 (1211/1217)
7. ✅ 0 client-side configurable errors
8. ✅ 194 glm5.1→deepseek 回落全成功
9. ✅ kimi num_attempts=0 (无尝试, 无饥饿)

---

## 预期效果

| 指标 | 当前 (R245 前) | 预期 (R245 后) |
|------|--------------|--------------|
| 30min 成功率 | 99.51% | 99.51% (不变) |
| 30min 失败 | 6 (5 ATE + 1 NVStream) | 6 (不变) |
| 每key 429 | 408 (全5key均衡) | 408 (不变) |
| 回落 | 205 (194 glm→ds) | 205 (不变) |
| 预算折断 | 15/day | 15/day (外部) |
| 所有7参数 | 均衡 | 均衡 (不变) |

---

## 跨机器状态 (R245)

HM2当前: KEY=38, TIER=45, UPSTREAM=63, MIN=15.6, BUDGET=115, CONNECT=24, TIMEOUT=300
HM1当前: KEY=34, TIER=42, UPSTREAM=60, MIN=19.0, BUDGET=105, CONNECT=24, TIMEOUT=300
非对称差异: MIN_OUTBOUND_INTERVAL_S 15.6 vs 19.0 (不同优化路径), KEY 38 vs 34 (HM2 更高 = 更保守)

24h ATE: 全 NVCFPexecTimeout + NVStream (external, 非可配置)

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记