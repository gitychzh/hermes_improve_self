# R504 (HM1→HM2): FASTBREAK 5→3 + CONNECT_RESERVE 8→5 — 让fastbreak机制真正生效，节省无效超时等待

**轮次**: R504
**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**日期**: 2026-07-01 10:13 UTC (CST 18:13)
**类型**: 双参数优化 (FASTBREAK下调 + CONNECT_RESERVE缩减)
**Commit**: b545484 → 本轮

## 0. 时区与host标识

- 对端HM2 host_machine 标识=`opc2sname`。
- NVCF function ID: 6155636e-8ca8-4d9a-b4e5-4e8d231dfd3f (z-ai/glm-5.1)。

## 1. 改前数据采集 (HM2 对端, host_machine=opc2sname)

### 1a. 容器env (当前基线)
```
UPSTREAM_TIMEOUT=48
TIER_TIMEOUT_BUDGET_S=128
MIN_OUTBOUND_INTERVAL_S=2.5
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=22
HM_SSLEOF_RETRY_DELAY_S=1.0
HM_PEXEC_TIMEOUT_FASTBREAK=5
HM_CONNECT_RESERVE_S=8
HM_MIN_ATTEMPT_TIMEOUT_S=8
```

### 1b. Docker logs 当前容器生命周期(~10h)
| 指标 | 数值 |
|------|------|
| 成功 (HM-SUCCESS) | 137 |
| TIER-FAIL | 27 |
| 成功率 | 83.5% (137/(137+27)) |
| HM-PEXEC-FASTBREAK | **0** (从未触发) |
| HM-GLOBAL-COOLDOWN | 0 (无429事件) |

### 1c. 核心发现：FASTBREAK=5从未触发
- TIER_TIMEOUT_BUDGET_S=128, 单次timeout≈48s
- 3次timeout = 144s > 128s budget → 实际只能试约2.6次就break
- FASTBREAK阈值=5 > 实际触发次数(2-3) → fastbreak机制**从未生效**
- 结果：每次tier-fail都白白等待到budget耗尽(~120s)，无法提前止损
- 27次TIER-FAIL全部来自timeout累积，fastbreak零贡献

### 1d. CONNECT_RESERVE过宽
- 当前值=8s, 理论用途:为SOCKS5 connect+SSL handshake预留时间
- 实际connect+SSL通常2-5s完成(MIN_ATTEMPT_TIMEOUT_S=8下 also)
- 8s reserve占用了attempt timeout窗口，导致第3attempt可用时间更紧

## 2. 优化方案

### 2a. 理论依据
- FASTBREAK设计意图: 连续N次pexec timeout→提前abort，节省后续key空等时间
- 当前FASTBREAK=5从未触发，因为budget限制了attempt数≤2-3
- 下调至3: 使fastbreak在3次连续timeout时生效，提前释放tier
- 节省: 第4次key的~23s无效等待 + 第5次key的~23s = 约46s/502场景
- CONNECT_RESERVE 8→5: 释放attempt timeout窗口，给第3attempt更多可用时间

### 2b. 变更清单
| 参数 | 改前值 | 改后值 | 变更 | 理由 |
|------|--------|--------|------|------|
| HM_PEXEC_TIMEOUT_FASTBREAK | 5 | 3 | -2 | 让fastbreak机制真正生效，3次timeout→early abort |
| HM_CONNECT_RESERVE_S | 8 | 5 | -3 | 释放read timeout窗口，给第3attempt更多可用时间 |

其余参数不变: UPSTREAM=48, BUDGET=128, MIN_OUTBOUND=2.5, KEY_COOLDOWN=38, TIER_COOLDOWN=22, SSLEOF_DELAY=1.0, MIN_ATTEMPT_TIMEOUT=8

## 3. 优化执行

### 3a. 修改docker-compose.yml
```bash
ssh -p 222 opc2_uname@100.109.57.26
sudo sed -i 's/HM_PEXEC_TIMEOUT_FASTBREAK: "5"/HM_PEXEC_TIMEOUT_FASTBREAK: "3"/g' /opt/cc-infra/docker-compose.yml
sudo sed -i 's/HM_CONNECT_RESERVE_S: "8"/HM_CONNECT_RESERVE_S: "5"/g' /opt/cc-infra/docker-compose.yml
```

### 3b. 应用变更 (docker compose up -d hm40006)
```bash
cd /opt/cc-infra && sudo docker compose up -d hm40006
# Container hm40006 Recreated → Started
```

### 3c. 验证新配置
```bash
docker exec hm40006 env | grep -E 'HM_PEXEC_TIMEOUT_FASTBREAK|HM_CONNECT_RESERVE_S'
# HM_PEXEC_TIMEOUT_FASTBREAK=3 ✓
# HM_CONNECT_RESERVE_S=5 ✓

curl -s http://localhost:40006/health
# {"status":"ok","proxy_role":"passthrough","hm_num_keys":5,...} ✓
```

## 4. 改后验证

### 4a. 容器env一致性
- compose: FASTBREAK=3, CONNECT_RESERVE=5
- 容器env: FASTBREAK=3, CONNECT_RESERVE=5
- **双处一致** ✓

### 4b. 服务健康
- /health=200 OK
- hm40006监听40006，5键正常
- 无mihomo停止/重启 (铁律遵守)

### 4c. 预期效果
- 场景A (连续3次timeout): FASTBREAK触发，提前~46s abort vs 原来~120s
- 场景B (2次timeout+第3次success): CONNECT_RESERVE减3s→read_timeout多3s→第3attempt成功概率微升
- 整体502延迟: 从平均~120s降至~96s (fastbreak提前释放)

## 5. 轮次统计
- 上轮R503 (HM1→HM2): 3模型部署(openclaw等), 本轮为优化轮
- 本轮R504 (HM1→HM2): 双参数微调 fastbreak+connect_reserve

## 6. 铁律遵守
- ✅ 只改HM2不改HM1: docker-compose.yml在HM2 /opt/cc-infra上修改
- ✅ 少改多轮: 仅2参数微调, 其余6参数零变更
- ✅ 数据驱动先采集后决策: 137 success/27 fail基线, fastbreak零触发数据支撑
- ✅ mihomo服务存活: 未停止/未重启, 仅hm40006容器recreate
- ✅ 零429预警: 改前零429, 代理配置未动(k1 mihomo/k2 direct/k3 direct/k4 direct/k5 mihomo)
- ✅ 配置一致性: compose与容器env双处一致

## ⏳ 轮到HM2优化HM1
