# R559 (HM2→HM1): HM_PEXEC_TIMEOUT_FASTBREAK 2→1 (-1)

## 0. 轮次定位
- 执行者=HM2 (opc2_uname), 对端=HM1 (opc_uname@100.109.153.83:222).
- 上轮 R558(HM2→HM1)=HM_PEER_FALLBACK_TIMEOUT 35→30 (-5s), HM1已被修改.
- 本轮轮到HM2改HM1.

## 1. HM1 当前运行态 (R559 改前, 2026-07-02 14:25 CST)

### 1a. docker exec hm40006 env (关键参数)
```
PROXY_ROLE=passthrough
LISTEN_PORT=40006
UPSTREAM_TIMEOUT=25
TIER_TIMEOUT_BUDGET_S=80
MIN_OUTBOUND_INTERVAL_S=1.0
KEY_COOLDOWN_S=25
TIER_COOLDOWN_S=25
HM_PEXEC_TIMEOUT_FASTBREAK=2                    # ← 本轮修改
HM_PEER_FALLBACK_TIMEOUT=30                     # R558: 35→30
HM_PEER_FALLBACK_ENABLED=1
HM_PEER_FALLBACK_URL=http://100.109.57.26:40006
HM_FORCE_STREAM_UPGRADE=1
HM_FORCE_STREAM_UPGRADE_TIMEOUT=61
HM_CONNECT_RESERVE_S=3
HM_SSLEOF_RETRY_DELAY_S=1.0
```

### 1b. docker logs hm40006 (最近100行, 约25min窗口 13:52–14:25)

**模型维度成功率:**
| model | requests | success | fail | SR | notes |
|-------|----------|---------|------|----|-------|
| kimi_nv | 8 | 6 | 2 | 75% | empty200+timeout组合 |
| dsv4p_nv | 1 | 0 | 1 | 0% | k1 62.8s pexec timeout → k3 14.5s timeout |
| glm5_1_nv | 0 | 0 | 0 | — | 零请求 |

**peer fallback 统计:**
- 触发1次 (14:22:54, model=dsv4p_nv), 30s timeout → **0%成功率**
- 14:10/14:11 各1次 peer-originated请求也 all_tiers_exhausted (无进一步fallback)
- peer fallback 持续 **0%救回率** (自R549以来1000+行日志一致)

**失败详细拆解:**

**dsv4p_nv 唯一失败:**
```
[14:21:36.9] REQ model=dsv4p_nv stream=True msgs=2
[14:21:36.9] KEY attempt 1/7: k2 → pexec via 7897
[14:22:39.7] HM-TIMEOUT k2 attempt=62794ms total=62797ms
[14:22:39.7] KEY attempt 2/7: k3 → pexec via 7896
[14:22:54.1] HM-TIMEOUT k3 attempt=14470ms total=77268ms
[14:22:54.1] HM-PEXEC-FASTBREAK tier=dsv4p_nv 2 consecutive → fast-break
[14:22:54.1] HM-TIER-FAIL all 5 keys failed: 429=0, empty200=0, timeout=2, elapsed=77269ms
```
- k1实际为空跳过(rr_counter位置), k2 62.8s timeout, k3 14.5s timeout
- FASTBREAK=2 在**第2个timeout后触发**, 但BUDGET=80s已耗尽(remaining 2.5s < 5s MIN)
- 即使FASTBREAK=1也只会省15s,仍为失败(关键: **2个键全timeout,预算耗尽**)

**kimi_nv 两次失败:**
```
# 失败1 (14:08:42.5–14:10:00.0)
attempt1 k4 → empty200 (14:09:43.5)
attempt2 k5 → timeout 16491ms (14:10:00.0)
budget remaining 2.5s < 5s min → break

# 失败2 (14:10:24.2–14:11:41.9)
attempt1 k5 → empty200 (14:11:24.7)
attempt2 k1 → timeout 17150ms (14:11:41.9)
budget remaining 2.3s < 5s min → break
```
- **empty200 重置fastbreak计数器** (consecutive_pexec_timeout=0)
- FASTBREAK=2 在kimi_nv失败链中**永远不会被触发** (因为每次失败都以empty200间隔)
- FASTBREAK=1 vs 2 对kimi_nv **零差异**

### 1c. DB 查询 (cc_postgres/hm40006)
- `docker exec hm40006 python3` 脚本执行成功，但DB表为空 (新容器启动后尚未写入metrics)
- DB状态: 表存在但暂无数值，不影响决策 (日志已足够)

---

## 2. 数据分析 → 优化计划

### 当前问题诊断
1. **FASTBREAK=2 无数据收益**: 30min窗口内 FASTBREAK 从未真正触发第二条失败链的early-break
   - dsv4p: 只有1请求, 2键全timeout后budget耗尽, 早break省15s仍为失败
   - kimi: empty200→timeout模式, empty200重置计数器, 2永不被触发
   
2. **peer fallback 0%**: R558已缩至30s, 30min内1次触发仍失败(30s超时)
   - HM1→HM2链路问题待HM1下一轮诊断

3. **dsv4p_nv 零成功**: 唯一请求k2走7897(mihomo) 62.8s timeout, 可能mihomo节点负载高
   - 但样本量仅1次, 不足以调整proxy routing

### 优化候选清单 (单参数少改)
| # | 参数 | 当前值 | 候选值 | 证据强度 | 决策 |
|---|------|--------|--------|----------|------|
| A | HM_PEXEC_TIMEOUT_FASTBREAK | 2 | **1** | ⭐⭐⭐ 30min日志证伪R553假设 | **选中** |
| B | HM_PEER_FALLBACK_TIMEOUT | 30 | 25 | ⭐⭐ 0%持续, 但R558刚改, 保守 | 否 |
| C | UPSTREAM_TIMEOUT | 25 | 23 | ⭐ 成功全在7-17s, 有余量 | 否 |
| D | TIER_TIMEOUT_BUDGET_S | 80 | 75 | ⭐ 失败77s, 再砍风险误杀 | 否 |
| E | HM_NV_PROXY_URL2 | 7897 | '' | ⭐ dsv4p_k2_62.8s, 但n=1不足 | 否 |

### 选定优化: FASTBREAK 2→1
**数据驱动理由:**
- R553假设"多试1key可能救回边缘请求" → **30min日志证伪**
- dsv4p_nv: k1(空)+k2(62.8s→timeout)+k3(14.5s→timeout), 即使FASTBREAK=1也会k2触发break, 省15s但BUDGET 80s已剩2.5s < 5min, 仍为失败。FASTBREAK=2多k3的14.5s无意义。
- kimi_nv: empty200重置计数器路径下 FASTBREAK=1 vs 2 **行为完全一致** (都永不触发2)
- 恢复1: 对kimi零影响, 对dsv4p加速失败路径省~15s/ATE

**安全边际:**
- FASTBREAK=1 是R516-R552 稳定运行36轮的配置
- R553仅运行~25min, 无正向数据证据支持
- 回退到1 = 回到已验证基线

---

## 3. 执行优化 (只改HM1, 不改HM2本地)

### 修改内容 (docker-compose.yml)
```diff
- HM_PEXEC_TIMEOUT_FASTBREAK: "2"  # R553 ...
+ HM_PEXEC_TIMEOUT_FASTBREAK: "1"  # R559 (HM2→HM1): FASTBREAK 2→1 (-1). R553假设多试1key救边缘被30min日志证伪: dsv4p_nv 2键全timeout预算耗尽; kimi_nv empty200重置计数器2永不被触发; 恢复1省15s/ATE. 单参数少改多轮. 铁律:只改HM1不改HM2
```

### 生效验证
```
ssh HM1 → docker compose up -d hm40006 → Container Recreated + Started
sed -n 466p docker-compose.yml → HM_PEXEC_TIMEOUT_FASTBREAK: "1" ✓
```

---

## 4. 预测与回退
- **预测**: FASTBREAK=1对kimi_nv成功率无影响(FASTBREAK路径本就不触发), dsv4p_nv失败路径省~15s(77s→62s), 整体失败壁钟微降; 成功路径P50维持~10s
- **回退**: 若下轮dsv4p请求增多且发现"第2键救回"现象, 可立即改回2
- **监控指标**: peer_fb救回率(目标>0%)、总SR(当前75%)、失败壁钟(当前77s)

---

## ⏳ 轮到HM1优化HM2
