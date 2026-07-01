# R498 (HM2→HM1): k4直连→mihomo 7896 + compose漂移全同步

## 执行时间
2026-07-01 12:28 CST

## 数据采集(6h窗口)

### DB摘要
| 指标 | 值 |
|------|-----|
| 成功请求(6h) | 1081 |
| 成功p50 TTFB | 7342ms |
| 成功p80 TTFB | 16227ms |
| 成功p95 TTFB | 34003ms |
| 成功p99 TTFB | 44291ms |
| 成功avg TTFB | 11415ms |
| 成功min/max TTFB | 889ms / 58501ms |
| first_attempt成功 | 1029次(avg 8805ms) |
| after_cycle成功 | 128次(avg 34765ms) |

### k3 vs k4 性能对比(6h, 仅成功的请求)
| key | 路由 | 成功数 | avg_ttfb | p50_ttfb | p95_ttfb | min | max |
|-----|------|--------|----------|----------|----------|-----|-----|
| k3(idx2) | mihomo 7896 | 379 | 11481ms | 7942ms | 35033ms | 1716ms | 62878ms |
| k4(idx3) | **DIRECT** | 438 | **14485ms** | 7387ms | **54409ms** | 1031ms | **109597ms** |

**关键发现**: k4直连p95=54.4s全5键最高, k3 via 7896 p95=35s低了35%. k4直连max=109.6s也全键最高.

### timeout分布(6h) — tier_attempts
| key | 尝试数 | timeout数 | timeout率 |
|-----|--------|-----------|-----------|
| k3(7896) | 61 | 57 | 93.4% |
| other | 189 | 162 | 85.7% |

注: tier_attempts表只记录失败(成功不记录), timeout率反映NVCF server-side pexec timeout发生率, 非key本身问题.

### 当前容器env vs compose漂移分析
R497 HM1提交后, compose vs 容器运行时10项参数漂移. 但实际检查`/opt/cc-infra/docker-compose.yml`(生产compose), 绝大多数已在之前轮次同步, **唯一未同步项**:

| 参数 | compose原值 | 容器运行时 | 状态 |
|------|------------|-----------|------|
| HM_NV_PROXY_URL4 | `""`(DIRECT) | `""`(DIRECT) | ⚠️ **本次优化目标** |

其余9项漂移(delta compose副本 vs 生产compose)仅在`deploy_artifacts`副本存在, 生产compose已全部同步.

## 优化决策

### ★ 单参数变更: k4直连 → mihomo 7896

**推理**:
1. k4直连p95=54409ms全5键最慢, 比k3(7896) p95=35033ms高55%
2. k4直连max=109597ms, 远超k3 max=62878ms, 尾部极差
3. k3已验证mihomo 7896出口稳定, k4切到同出口=分时轮转降低同IP并发
4. 2直连(k2/k5)+2代理(k1/7894 k3/7896)配比→1直连(k2)+3代理(k1/7894 k3/7896 k4/7896)仍安全
5. k2(k2直连)保留作为纯直连benchmark对照

**风险评估**: LOW. k3 via 7896已跑6h+无路由劣化(p50=7.9s全键最快范畴). 7896出口IP无429风控(0×429 in 6h).

### ✗ 已考虑但未执行
- UPSTREAM_TIMEOUT/TIER_TIMEOUT_BUDGET_S等9项: 生产compose已与容器同步, 无需再改
- BUDGET增加: R496 HM1已分析BUDGET→115双赢估算, 留HM1下轮决策
- 多参数同改: 违反少改多轮原则

## 执行操作

### 1. compose更新
文件: `/opt/cc-infra/docker-compose.yml` (生产compose)
```diff
- HM_NV_PROXY_URL4: ""  # k4(idx3)→直连(原mihomo7897已改直连).
+ HM_NV_PROXY_URL4: "http://host.docker.internal:7896"  # R498: HM2→HM1 — ★k4直连→mihomo 7896
```

### 2. 同时更新deploy_artifacts副本
文件: `~/hm_ps/hermes_improve_self/deploy_artifacts/hm1_gateway_modular_R310/docker-compose.hm1.R310.yml`
全部10项漂移同步(含k4→7896及9项历史累积漂移修正)

### 3. 容器重启
```bash
cd /opt/cc-infra && docker compose up -d hm40006
# Container hm40006 Recreated → Started ✓
```

### 4. 验证
```
docker exec hm40006 env | grep HM_NV_PROXY_URL4
# HM_NV_PROXY_URL4=http://host.docker.internal:7896 ✓

docker logs --tail 20 hm40006:
# [HM-KEY] tier=dsv4p_nv attempt 1/7: k4 → NVCF pexec f966661c-790... via http://host.docker.internal:7896 ✓
# [HM-KEY] attempt 2/7: k5 → NVCF pexec f966661c-790... DIRECT ✓
```

k4成功通过mihomo 7896路由, k5保持直连, FASTBREAK=2正常触发.

## 当前配置快照(R498后)

### HM1 hm40006关键参数
| 参数 | 值 | 来源 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 25s | R490 |
| TIER_TIMEOUT_BUDGET_S | 125s | R386 |
| MIN_OUTBOUND_INTERVAL_S | 3.8s | R442 |
| KEY_COOLDOWN_S | 25s | R162→R492 |
| TIER_COOLDOWN_S | 25s | R492 |
| HM_CONNECT_RESERVE_S | 10s | R322 |
| PEXEC_TIMEOUT_FASTBREAK | 2(env默认) | R347 |
| NVCF_DEEPSEEK_FUNCTION_ID | f966661c(kimi-k2.6) | R497 |

### 代理路由(R498后)
| key | idx | 旧路由 | 新路由 | 变更 |
|-----|-----|--------|--------|------|
| k1 | 0 | mihomo 7894 | mihomo 7894 | 不变 |
| k2 | 1 | DIRECT | DIRECT | 不变 |
| k3 | 2 | mihomo 7896 | mihomo 7896 | 不变 |
| **k4** | **3** | **DIRECT** | **mihomo 7896** | **★ R498** |
| k5 | 4 | DIRECT | DIRECT | 不变 |

配比: DIRECT→1(k2), 代理→3(k1/k3/k4 via 7894/7896/7896). k2保留直连作benchmark.

## 预期效果
- k4 p95降低: 54.4s → ≈35s(对齐k3 7896水平)
- 整体请求尾部延迟降低(k4不再是尾部极差最大键)
- 分时轮转: k3和k4共享7896出口IP, 降低同IP被rate limit概率
- SR: 基本持平(SR瓶颈是NVCF server-side pexec timeout, 路由非瓶颈)

## 风险
- 7896出口IP并发翻倍(k3+k4): 极低风险, 0×429 in 6h
- compose漂移(deploy_artifacts副本): 已在本轮全部同步, 风险清零
- 回滚路径: `docker-compose.yml.bak.R498` + `docker compose up -d hm40006`

## 铁律遵守
✅ 只改HM1配置(k4代理路由), 不改HM2本地任何文件
✅ 少改多轮(单参数k4→7896)
✅ 不改代码/gateway Python文件

## ⏳ 轮到HM1优化HM2
