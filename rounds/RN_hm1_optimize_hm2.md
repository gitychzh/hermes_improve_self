# R135: HM1→HM2 — HM_CONNECT_RESERVE_S 20→22 (+2s SSL Handshake Reserve)

**角色**: HM1 (opc_uname) 优化执行者  
**变更**: HM_CONNECT_RESERVE_S: 20→22 (+2s)  
**时间**: 2026-06-28 00:36 UTC  
**原则**: 更少报错更快请求超低延迟稳定优先 · 铁律:只改HM2不改HM1 · 单参数每轮

## 1. 数据收集

### 1.1 30-Min 请求统计 (PostgreSQL)

| 指标 | 数值 |
|------|------|
| 总请求数 | 85 (30min), 24 (10min burst) |
| 成功数 | 85 (100%) |
| 失败数 | 0 |
| 回退发生 | 22/86 (25.6%) |
| 默认模型 | glm5.1_hm_nv |

### 1.2 Tier 延迟分布

| Tier | p90 (ms) | p95 (ms) | max (ms) | avg (ms) |
|------|----------|----------|----------|----------|
| deepseek_hm_nv | 54,654 | 129,755 | 129,755 | 23,219 |
| glm5.1_hm_nv | 45,116 | 57,224 | 89,455 | 19,554 |

### 1.3 Key-Level 尝试分解 (30min)

| Tier | 429 | SSLEOF | ConnReset | RemoteDisc | Timeout | 总计 |
|------|-----|--------|-----------|------------|---------|------|
| deepseek_hm_nv | 0 | 1 | 0 | 0 | 0 | 1 |
| glm5.1_hm_nv | 52 | 4 | 4 | 1 | 2 | 65 |

### 1.4 Error Detail JSONL (最近30行)

7个 tier-failure 事件：
- **3个 `all_429: true`** — 纯429风暴, elapsed_ms=1.4s~6.3s
- **4个 `all_429: false`** — 混合错误(429+ConnReset+RemoteDisc+SSLEOF), elapsed_ms=3.5s~12.1s

### 1.5 TIER_TIMEOUT_BUDGET_S 断点分析

**无 `HM-TIER-BUDGET` 断点日志** — 30min内无 `remaining < 10s` 事件。所有 glm5.1 层级失败在 1.4s~12.1s 内完成，远低于 132s 预算。

### 1.6 HM2 运行配置

```
HM_CONNECT_RESERVE_S=20 (变更前) → 22 (变更后)
KEY_COOLDOWN_S=45
TIER_COOLDOWN_S=45
MIN_OUTBOUND_INTERVAL_S=10.0
TIER_TIMEOUT_BUDGET_S=132
UPSTREAM_TIMEOUT=71
PROXY_TIMEOUT=300
```

### 1.7 Mihomo 状态

```
PID: 2008535, 运行正常
```

## 2. 分析

### 2.1 SSLEOF 错误分布

30min 窗口内:
- **deepseek_hm_nv**: 1×SSLEOF (唯一错误)
- **glm5.1_hm_nv**: 4×SSLEOF (在 65 次 key 尝试中)

SSLEOF 是 SSL 握手协议级错误 (`UNEXPECTED_EOF_WHILE_READING`)，表示 mihomo SOCKS5 代理在 SSL/TLS 握手阶段提前关闭连接。每次 SSLEOF 消耗 `HM_CONNECT_RESERVE_S` 预算用于连接建立。

### 2.2 跨机收敛差距

| 机器 | HM_CONNECT_RESERVE_S | 差距 |
|------|---------------------|------|
| HM1 (本地) | 24 | — |
| HM2 (远程) | 20 (变更前) | 差 4s |
| HM2 (远程) | 22 (变更后) | 差 2s (收敛 4s→2s) |

R129 已将差距从 6s 收敛到 4s，本次继续收敛到 2s。

### 2.3 预算验证

```
Effective budget = TIER_TIMEOUT_BUDGET_S - HM_CONNECT_RESERVE_S
变更前: 132 - 20 = 112s
变更后: 132 - 22 = 110s (减少 2s)
```

实际 glm5.1 层级失败在 1.4-12.1s 内完成，112s 预算绰绰有余。-2s 的 effective budget 减少在噪声范围内，不影响层级预算断点。

### 2.4 为什么不是其他参数

| 参数 | 当前 | 不选择的原因 |
|------|------|-------------|
| UPSTREAM_TIMEOUT | 71 | p95 均在预算内，不变 |
| MIN_OUTBOUND_INTERVAL_S | 10.0 | 5×10.0=50.0s 已超 GLOBAL_COOLDOWN=45s，缓冲充分 |
| KEY_COOLDOWN_S | 45 | 已收敛至 GLOBAL_COOLDOWN=45s，不变 |
| TIER_COOLDOWN_S | 45 | 已收敛至 GLOBAL_COOLDOWN=45s，不变 |
| TIER_TIMEOUT_BUDGET_S | 132 | 无预算断点事件，不变 |

## 3. 优化执行

### 参数: HM_CONNECT_RESERVE_S 20→22 (+2s)

**理由**: SSLEOF 错误(deepseek 1×, glm5.1 4×)消耗 SSL 握手预算; 跨机收敛(差 HM1=24 差 4s→2s); 单参数+2s

### 执行步骤

```bash
# 1. 修改 docker-compose.yml 第 510 行
ssh -p 222 opc2_uname@100.109.57.26 \
  'cd /opt/cc-infra && \
   sed -i "510s|HM_CONNECT_RESERVE_S: \\"20\\"|HM_CONNECT_RESERVE_S: \\"22\\"|" \
   docker-compose.yml'

# 2. 更新注释
sed -i '510s|# R113:.*|# R135: HM1→HM2 — 20→22: +2s SSL handshake reserve|' \
  docker-compose.yml

# 3. 重建容器
docker compose up -d --build --force-recreate hm40006
```

### 验证结果

| 检查项 | 结果 |
|--------|------|
| `docker exec hm40006 env \| grep HM_CONNECT_RESERVE_S` | **22** ✅ |
| `docker ps --filter name=hm40006` | "Up (healthy)" ✅ |
| `curl -s http://localhost:40006/health` | 200 OK ✅ |
| `pgrep -a mihomo` | PID 2008535 运行中 ✅ |

## 4. 预期效果

| 指标 | 变更前 (20) | 变更后 (22) | 方向 |
|------|------------|------------|------|
| SSL Handshake Reserve | 20s | 22s | +2s ↑ |
| Effective Tier Budget | 112s | 110s | -2s ↓ |
| Cross-Machine Gap | 差 HM1=4s | 差 HM1=2s | 收敛 2s |
| SSLEOF 吸收能力 | 原 | 增强 | +2s 每 key |

**预期**: 每个 key 的 SSL/TLS 握手机会增加 2s 超时容忍度，deepseek 和 glm5.1 的 SSLEOF 错误将减少; 30min 请求成功率维持 100%; 有效层级预算减少 2s 在噪声范围内，不触发预算断点。

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记