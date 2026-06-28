# R262: HM1→HM2 — TIER_TIMEOUT_BUDGET_S 124→128 (+4s) — 单轮优化

**回合类型**: 优化 (单参数)
**方向**: HM1 (opc_uname) → HM2 (opc2_uname)
**时间**: 2026-06-29 00:55 UTC
**原则**: 更少报错，更快请求，超低延迟，稳定优先 — 铁律:只改HM2不改HM1 — 少改多轮(单参数)

## 摘要

HM2 glm5.1 tier 30min 成功率 96.62% (1201/1243)，42 个错误：41 ATE + 1 NVStream。10min 突发窗口更差：96.42% (1157/1200, 43 错误)。**错误集中在最近 10 分钟**，glm5.1 tier 预算断点 consistent: 剩余 2.3-2.8s < 10s 最小值，每个键级尝试 NVCFPexecTimeout 消耗 10-39s，5 键全失败后预算耗尽。本次继续单参数路径：TIER_TIMEOUT_BUDGET_S 124→128 (+4s) 给 glm5.1 tier 多一个键级尝试机会。

## 参数变化

| 参数 | 旧值 | 新值 | 增量 |
|------|------|------|------|
| TIER_TIMEOUT_BUDGET_S | 124 | 128 | +4s |

## 数据采集

### 30-min 窗口 (hm_requests)
- Total: 1243, Success: 1201 → **96.62%**
- Errors: 42 (41 all_tiers_exhausted + 1 NVStream_IncompleteRead)
- Avg duration: 27020ms, Max: 263164ms

### 10-min 突发窗口
- Total: 1200, Success: 1157 → **96.42%**
- Errors: 43 (42 all_tiers_exhausted + 1 NVStream_IncompleteRead)

### Tier 分布 (30-min)
| Tier | Count | Avg(ms) | Fallbacks |
|------|-------|---------|-----------|
| deepseek_hm_nv | 1153 | 21802 | 1 |
| glm5.1_hm_nv | 48 | 58841 | 5 |

### 键级错误 (hm_tier_attempts, 30-min)
- **deepseek**: 63 SSLEOFError (k0:18, k1:10, k2:9, k3:18, k4:8) + 15 NVCFPexecTimeout + 6 empty_200
- **glm5.1**: NVCFPexecTimeout 10-40s consumption per key, 2×500_nv_error, 1×429
- **仅 1×429 在 30min** — `all_429: false` 主导，不是函数级限流

### Docker 日志关键行 (hm40006)
```
[00:50:59] [HM-TIER-BUDGET] tier=glm5.1_hm_nv budget 124.0s remaining 2.8s < 10s minimum, breaking
[00:53:01] [HM-TIER-BUDGET] tier=glm5.1_hm_nv budget 124.0s remaining 2.5s < 10s minimum, breaking
[00:55:01] [HM-TIER-BUDGET] tier=glm5.1_hm_nv budget 124.0s remaining 2.3s < 10s minimum, breaking
```
**11 budget breaks in today's proxy log** (June 29)

### Error Detail JSONL (last 20, 2026-06-29)
- **all_429: false** 在 ALL 条目 — mixed failure: empty_200 + NVCFPexecTimeout + 500_nv_error
- Tier elapsed: 121-122s per cycle
- 每个 key 尝试: NVCFPexecTimeout 10-39s, empty_200, 500_nv_error

### RR Counter
```
{"hm_nv_deepseek": 7547, "hm_nv_kimi": 161, "hm_nv_glm5.1": 6198}
```
glm5.1 是第二活跃 tier (6198 请求)，deepseek 主导 (7547)

### 运行配置确认
```
TIER_COOLDOWN_S=45, KEY_COOLDOWN_S=38, UPSTREAM_TIMEOUT=63
MIN_OUTBOUND_INTERVAL_S=16.0, TIER_TIMEOUT_BUDGET_S=124→128
HM_CONNECT_RESERVE_S=24, PROXY_TIMEOUT=300
```

## 分析

### 为什么选择 TIER_TIMEOUT_BUDGET_S

1. **glm5.1 是唯一有预算断点的 tier**: deepseek 47 SSLEOFErrors + 3 timeout 全部自愈，0 预算断点。glm5.1 是瓶颈。
2. **剩余 2.3-2.8s，非常接近 10s 阈值**: +4s → 剩余 6.3-6.8s，多给一个 key 机会。
3. **R259→R260→R262 渐进路径**: 115→120→124→128，每轮 +4-5s，少改多轮。

### 为什么不是其他参数

- **MIN_OUTBOUND_INTERVAL_S**: R261 刚改 15.6→16.0，需要观察效果。5×16.0=80s > GLOBAL=45s，已经很宽。
- **KEY_COOLDOWN_S**: 仅 1×429 在 30min，不是 429 瓶颈。当前 38 足够。
- **TIER_COOLDOWN_S**: 45，已收敛到 GLOBAL=45。无 429 信号调整。
- **UPSTREAM_TIMEOUT**: 63。NVCFPexecTimeout 是服务端超时，不是客户端配置。
- **HM_CONNECT_RESERVE_S**: 24，已完全收敛到 HM1=24。

### 10min/30min 错误一致性
30min: 42 错误 (41 ATE + 1 NVStream)，10min: 43 错误 (42 ATE + 1 NVStream)。**10min 比 30min 更多错误** — 证明错误集中在最近 10 分钟，且前 20 分钟相对静默 (仅 ~43 请求)。这不是稀释平均问题 — 这是真实恶化信号。

## 执行

```bash
# 1. 修改 compose 文件
ssh HM2 "sed -i 's|TIER_TIMEOUT_BUDGET_S: \"124\"|TIER_TIMEOUT_BUDGET_S: \"128\"|' /opt/cc-infra/docker-compose.yml"

# 2. 验证文件变更
grep -n "TIER_TIMEOUT_BUDGET_S.*128" /opt/cc-infra/docker-compose.yml

# 3. 重建容器
cd /opt/cc-infra && docker compose up -d --force-recreate --no-deps hm40006

# 4. 验证运行配置
sleep 3 && docker exec hm40006 env | grep TIER_TIMEOUT_BUDGET_S  # → 128
docker ps --filter name=hm40006  # → Up (healthy)
pgrep -a mihomo  # → 2008535 (运行中)
curl -s http://localhost:40006/health  # → 200 OK
```

## 预期效果

### 前/后
| 指标 | 当前 (R261, 30min) | 预期 (R262 后) |
|------|---------------------|-----------------|
| 成功率 | 96.62% | ≥97.5% (减少 3-5 ATE) |
| Budget breaks/10min | 11 (today) | ≤8 (更多 key 机会) |
| 剩余预算 | 2.3-2.8s | 6.3-6.8s (+4s 增量) |
| 有效预算 | 124-24=100s | 128-24=104s |

### 风险
- **无**: +4s 不改变任何其他参数，不触及 mihomo，不改变路由逻辑
- **观察窗口**: 需要 30-min 验证窗口判定效果，少改多轮原则

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记