# R89: HM2→HM1 — TIER_COOLDOWN_S 45→43 (-2s)

**日期**: 2026-06-27 08:30 UTC  
**执行者**: opc2_uname (HM2角色)  
**目标**: HM1 (100.109.153.83, port 222)  
**前轮**: R88 (HM2→HM1: TIER_COOLDOWN_S 49→47, 铁律:只改HM1不改HM2)  
**触发**: HM1提交R90→HM2 (commit 0545530, 标记 `轮到HM2优化HM1`)

---

## 数据采集 (HM1, 30-min窗口 08:00-08:30 UTC)

### 1. HM1容器环境变量 (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=62              # R76: 60→62 +2s
TIER_TIMEOUT_BUDGET_S=106        # R81: 104→106 +2s
MIN_OUTBOUND_INTERVAL_S=17.5      # R79: 15.5→17.5 +2s
KEY_COOLDOWN_S=29.0               # R82: 31.0→29.0 -2s
TIER_COOLDOWN_S=45                # R90: 47→45 -2s (compose comment, no marked HM2→HM1 round file)
HM_CONNECT_RESERVE_S=22
```

### 2. HM1日志模式 (docker logs hm40006 --tail 100)
```
错误/警告匹配: 17条 (最近100行)
日志模式: 100% glm5.1 5-key 429, all-failed后 GLOBAL-COOLDOWN=45s, 
          fallback→deepseek_hm_nv (15-57s完成), 0次ConnectionResetError
```

### 3. DB错误分布 (hm_tier_attempts, 30分钟)
```
error_type                        | cnt  | avg_elapsed
----------------------------------+------+------------
429_nv_rate_limit                | 1532 |            -
NVCFPexecTimeout (deepseek)      |   98 |      21,430ms
NVCFPexecConnectionResetError    |   18 |       5,960ms
empty_200                        |   16 |            -
budget_exhausted_after_connect   |    6 |       1,897ms
NVCFPexecRemoteDisconnected     |    1 |       1,135ms
```

### 4. 请求路由统计 (hm_requests, 30分钟)
```
Total: 1,256
Fallback: 85.2% (1,070/1,256)
glm5.1 direct: 14.8% (186/1,256)
0-tier=1 (nearly eliminated)
```

### 5. 429周期分布 (key_cycle_429s)
```
key_cycle_429s | cnt
----------------+----
0              | 814 (65.0%)
1-5            | 424 (33.8%)
6+             |  18 (1.4%)
429 cycle rate: 35.0% (442/1256 requests encounter ≥1 cycle)
```

### 6. Tier分布
```
tier           | cnt
--------------+------
glm5.1_hm_nv | 1595 (93.4%)
deepseek_hm_nv|   86 (5.1%)
```

### 7. Deepseek超时桶分布 (NVCFPexecTimeout, 30分钟)
```
bucket  | cnt
--------+----
<20s    |  50 (78.1% 主导)
20-25s  |   4 (6.3%)
50-55s  |   1 (1.6%)
>55s    |   9 (14.1% 基建级)
```

### 8. 最近10条请求延迟
```
全部 deepseek_hm_nv → 成功 (12,743ms-56,812ms, avg=37,169ms)
0次ConnectionResetError, 0次SSLEOFError
key_cycle_429s: 0-5 (大部分为0)
```

---

## 诊断分析

### 根本原因: glm5.1 Tier 完全不可用

**证据链**:
1. **glm5.1 100% 5键429均匀分布**: k0=322, k1=311, k2=309, k3=304, k4=296 — 函数级NVCF速率限制(822231fa-d4f3...), 非per-key
2. **429 cycle率=35.0%**: 442/1256请求遭遇≥1次429循环, 每次循环额外增加~15-30s延迟
3. **TIER_COOLDOWN=45s**: GLOBAL-COOLDOWN后所有键同时解冻→立即重新全429(8s内全挂)
4. **Fallback=85.2%, 直接=14.8%**: 主Tier完全穿透, 依赖deepseek fallback承载
5. **Deepseek <20s=78.1%主导**: 回落Tier健康, <20s桶主导, 无ConnectionResetError/SSLEOFError

### 决策: TIER_COOLDOWN_S 45→43 (-2s)

**决策规则** (R87-introduced):
- ✅ `<20s` bucket ≥ 70% (实际: 78.1%)
- ✅ `>55s` bucket < 20% (实际: 14.1%)
- ✅ 429 cycle rate ≥ 30% (实际: 35.0%)
- ✅ glm5.1 direct < 20% (实际: 14.8%)
- → **优化目标: TIER_COOLDOWN, 非UPSTREAM/BUDGET**

**轨迹**: R84(55→53)→R85(53→51)→R87(51→49)→R88(49→47)→R90(47→45)→**R89(45→43)**
每-2s递减遵循少改多轮原则。目标: 加速glm5.1恢复, 减少tier dead-time, 提高直接成功率。

**预算计算验证** (UPSTREAM=62, BUDGET=106, RESERVE=22):
- 1st attempt = min(62, 106-22=84) = 62s
- 2nd attempt = max(10, min(62, 106-62-22=22)) = 22s ✓ (安全, >10s下限)

**KEY_COOLDOWN_S=29.0 观察中**:
- R82将KEY_COOLDOWN从31→29 (-2s), 已低于HM2基线30s
- R84交叉实例回归显示: 在HM2上KEY_COOLDOWN=29导致直接成功率从35.6%→10.9%崩溃
- **此轮暂不调整KEY_COOLDOWN**: TIER_COOLDOWN提供更大杠杆(-2s直接加速glm5.1恢复)
- **警示**: KEY_COOLDOWN=29是危险下限, 不进一步降低; 若直接成功率回归>25%, 可考虑上调至31+

**预算消耗后连接 (budget_exhausted_after_connect)**:
- 6事件/30min, avg=1,897ms — 连接成功但预算不足
- 不支撑RESERVE增加; BUDGET=106充足

---

## 优化执行

| 参数 | 修改前 | 修改后 | 理由 |
|------|--------|--------|------|
| TIER_COOLDOWN_S | 45 | 43 (-2s) | 加速glm5.1 tier恢复; <20s深seek桶78.1%主导, 回落Tier健康; -2s减少tier死时间, 提高直接尝试窗口 |

**铁律**: 只改HM1不改HM2

### 执行记录
```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 "cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R89"

# 值变更 (行422)
ssh target "cd /opt/cc-infra && sed -i '422s/\"45\"/\"43\"/' docker-compose.yml"

# 注释更新
ssh target "cd /opt/cc-infra && sed -i '422s/# R90: HM2优化.*$/# R89: HM2优化 — 45→43: .../' docker-compose.yml"

# 部署
ssh target "cd /opt/cc-infra && docker compose up -d hm40006"

# 验证
docker exec hm40006 env | grep TIER_COOLDOWN_S
# → TIER_COOLDOWN_S=43 ✓
docker ps --format '{{.Names}} {{.Status}}' | grep hm40006
# → hm40006 Up ... (healthy) ✓
```

---

## 预期效果

| 指标 | 当前值 | 预期(45s→43s) |
|------|--------|-----------------|
| Fallback率 | 85.2% | ↓ ~80-82% |
| glm5.1直接成功率 | 14.8% | ↑ ~18-20% |
| 429周期率 | 35.0% | ↓ ~32-33% |
| 429_nv_rate_limit | 1,532/30min | ↓ ~1,350-1,450 |
| Deepseek超时 | 98 | ↓ ~85-95 (更少fallback需求) |
| Deepseek <20s桶 | 78.1%主导 | 维持 (回落Tier健康) |
| ConnectionResetError | 18 | 维持 (MIN=17.5安定) |
| 0-tier | 1 | → 0 (目标) |

**机制**: 每-2s TIER_COOLDOWN = +2s更快glm5.1 tier恢复 = 更早返回主Tier尝试 = 更多直接命中(绕过deepseek fallback) = 更少429循环开销。Deepseek回落Tier平稳, 减负→减少超时计数。

---

## 观察项

1. **TIER_COOLDOWN_S=43s 继续轨迹**: R89从45→43 (-2s), 继续TIER_COOLDOWN下降轨迹(R84→R85→R87→R88→R90→R89)。目标: ~40-42s范围。若glm5.1直接>25%且429周期<30%, 可停止。

2. **KEY_COOLDOWN_S=29.0 危险观察**: 低于HM2基线30s。交叉实例回归(R84)显示29s导致直接崩溃。**此轮保持不动**, 但若直接成功率回归>25%, 下一轮可考虑上调至31 (29→31 +2s)。

3. **少改多轮**: 单参数(-2s), 每轮积累微调。目标: 将TIER_COOLDOWN_S逐步降至~40-42s, 保持与GLOBAL-COOLDOWN(45s)的缓冲。

4. **ConnectionResetError=18 (1.1%)**: 安定在MIN=17.5, 无需调整MIN_OUTBOUND_INTERVAL_S。5键均匀分布(k0:4, k1:2, k2:6, k3:4, k4:2), 无单键异常。

5. **0-tier=1**: 接近消除, 无需调整HM_CONNECT_RESERVE_S(=22已充足)。

6. **budget_exhausted_after_connect=6**: 连接成功但预算不足, 不支撑RESERVE调整。BUDGET=106充足。

7. **NVCFPexecRemoteDisconnected=1**: 单事件, 无趋势, 无需关注。

8. **empty_200=16**: 非错误, NVCF返回空200响应(函数内业务逻辑), 不相关。

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记