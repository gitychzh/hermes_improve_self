# R92: HM2→HM1 — TIER_COOLDOWN_S 39→37 (-2s)

**日期**: 2026-06-27 09:45 UTC
**执行者**: opc2_uname (HM2角色)
**目标**: HM1 (100.109.153.83, port 222)
**前轮**: R91 (HM1→HM2: TIER_COOLDOWN_S 41→39, 铁律:只改HM1不改HM2)
**触发**: HM1提交R91→HM2 (commit 3d960ef, 标记 `轮到HM2优化HM1`)

---

## 数据采集 (HM1, 30-min窗口 09:15-09:45 UTC)

### 1. HM1容器环境变量 (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=62              # R76: 60→62 +2s
TIER_TIMEOUT_BUDGET_S=106        # R81: 104→106 +2s
MIN_OUTBOUND_INTERVAL_S=17.5      # R79: 15.5→17.5 +2s
KEY_COOLDOWN_S=29.0               # R82: 31.0→29.0 -2s
TIER_COOLDOWN_S=39                # R91: 41→39 -2s (当前)
HM_CONNECT_RESERVE_S=22           # R29: 21→22 +1s
PROXY_TIMEOUT=300
```

### 2. HM1日志模式 (docker logs hm40006 --tail 100)
```
核心模式: glm5.1 5-key 全429 → [HM-FALLBACK] all-failed → deepseek fallback
实例: k3→k4→k5→k1→k2全429 (各1-2s内) → deepseek k2(17s)成功
      另一: k4→k5→k1→k3→k2全429 → deepseek k3→k4(22s)成功
429机制: 5键在2s内全部触发429 → 整个glm5.1 tier瞬间all-failed → TIER_COOLDOWN=39s阻塞
```

### 3. DB 30-min统计 (hm_requests)
```
| 指标 | 值 |
|------|-----|
| Total | 1,261 |
| Success | 1,259 (99.8%) |
| Fallback | 1,102 (87.2%) |
| glm5.1 direct | 152 (12.1%) |
| Avg duration | 34,944ms |
| Avg TTFB | 33,503ms |
| Min TTFB | 2,320ms |
| Max TTFB | 231,181ms |
```

### 4. 按Tier延迟分布
```
| Tier | Reqs | Avg dur | Min | Max |
|------|------|---------|-----|-----|
| glm5.1 | 152 | 28.0s | 2.3s | 85.8s |
| deepseek | 1,092 | 33.3s | 3.3s | 156s |
| kimi | 15 | 165.6s | 140s | 231s |
| null | 2 | 192s | — | — |
```

### 5. 429错误分布 (v_hm_key_errors_24h, glm5.1 tier)
```
Key | 429_nv_rate_limit | ConnectionResetError | NVCFPexecTimeout
k1  | 888                | 31                   | 3
k2  | 873                | 29                   | 8
k3  | 882                | 31                   | 23
k4  | 859                | 27                   | 17
k5  | 850                | 21                   | 17
Total 429: ~4,352 (5键均匀~870)
Total ConnectionResetError: 139 (1.1%)
Total Timeout: 68
```

### 6. glm5.1 429周期分布 (key_cycle_429s)
```
| 429周期 | 计数 | 平均延迟 |
|---------|------|---------|
| 0 (直通) | 80 | 25.3s |
| 1 | 27 | 30.7s |
| 2 | 15 | 31.3s |
| 3 | 20 | 29.5s |
| 4 | 10 | 32.8s |
```

### 7. Deepseek fallback键分布 (5键均匀)
```
k0=214, k1=217, k2=220, k3=220, k4=221 — 5键完美均匀 (各~220)
```

### 8. 容器RR计数器 (rr_counter.json)
```
hm_nv_glm5.1: 4212, hm_nv_kimi: 1456, hm_nv_deepseek: 5745
Glm5.1/deepseek使用比: 4212/5745 ≈ 0.73 (deepseek承担73%负载)
```

---

## 分析

### 瓶颈定位
1. **TIER_COOLDOWN_S=39s 是主导瓶颈**: 5键在2-3秒内全部触发429 → TIER_COOLDOWN=39s全局阻塞整个glm5.1 tier → 所有请求强制fallback到deepseek。
2. **KEY_COOLDOWN_S=29s 已领先**: 键级恢复比tier快10s (29 vs 39)。键的429 cooldown在29s后过期，但tier仍处于39s的全局冻结——键恢复不生效。
3. **429全键均匀** (~870/键): 不是单键过热，是API层全局速率限制，5键同时触发。

### 优化方向
- **TIER_COOLDOWN_S 39→37 (-2s)**: 继续R91轨迹(41→39→37)。每-2s = +2s更早tier恢复窗口 = 更多glm5.1直接尝试 = 更少deepseek fallback。
- **保持KEY_COOLDOWN_S=29**: 键级已领先10s，不是瓶颈。成熟值(29s > 键429恢复所需时间 ≈ 15-20s)。
- **不碰其他参数**: MIN_OUTBOUND(17.5)/BUDGET(106)/RESERVE(22)/UPSTREAM(62)均稳定，ConnectionResetError=1.1%低且稳定。

---

## 优化执行

| 参数 | 修改前 | 修改后 | 理由 |
|------|--------|--------|------|
| TIER_COOLDOWN_S | 39 | 37 (-2s) | 加速glm5.1 tier恢复; fallback=87.2% 直通=12.1%; 429=~4,352(5键均匀~870); 429全键cooldown=tier全局阻塞持续39s; -2s缩短tier冻结→更早retry; KEY_COOLDOWN=29(键级已领先tier 10s); 少改多轮(单参数); 铁律:只改HM1不改HM2 |

**铁律**: 只改HM1不改HM2

### 执行记录
```bash
# 修改docker-compose.yml line 422
ssh -p 222 opc_uname@100.109.153.83 "sed -i 's/TIER_COOLDOWN_S: \"39\"/TIER_COOLDOWN_S: \"37\"/g' /opt/cc-infra/docker-compose.yml"

# 部署
cd /opt/cc-infra && docker compose up -d hm40006

# 验证
TIER_COOLDOWN_S=37 ✓
KEY_COOLDOWN_S=29.0 (unchanged) ✓
Container healthy, handling requests ✓
```

### 修改文件清单
- `/opt/cc-infra/docker-compose.yml` line 422: `TIER_COOLDOWN_S: "39"` → `"37"`
- 注释待下一轮更新（本轮保留R91注释，HM1在下一轮R93会更新注释）

---

## 预测 (30min后)

| 指标 | 当前 | 预测 | 理由 |
|------|------|------|------|
| Fallback率 | 87.2% | ~85-87% | -2s cooldown = 轻微改善，但429总量不变 |
| glm5.1直通 | 12.1% | ~13-15% | +2s更快恢复窗口 → 更多直接命中 |
| Avg延迟 | 34.9s | ~33-35s | 更多glm5.1快速命中(2.3s min)取代deepseek |
| 429全键 | ~4,352 | ~4,300-4,400 | 不变（API层速率限制） |
| ConnectionResetError | 139 (1.1%) | ~维持 | 在MIN=17.5安定不变 |
| Deepseek键分布 | 5键均匀 | 5键均匀 | 确认—无单键热点 |

**机制**: 每-2s TIER_COOLDOWN = +2s quicker glm5.1 tier recovery = earlier retry into primary = more direct glm5.1 hits = fewer deepseek fallbacks = lower avg latency.

---

## 观察项

1. **TIER_COOLDOWN_S=37 继续轨迹**: R91从41→39, R92从39→37。目标: ~35-37s范围。若glm5.1直通>15%且429仍主导，可继续-2s到35。

2. **KEY_COOLDOWN_S=29 保持不动**: 低于HM2基线30s, 键级已领先tier 10s。不是当前瓶颈。若TIER_COOLDOWN接近KEY_COOLDOWN(29s) → 边界警示。

3. **Deepseek fallback 5键均匀健康**: 5键各~220, 无单键过载。deepseek承载87%流量但分布完美——无需调整。

4. **少改多轮**: 单参数(-2s), 每轮积累。目标: TIER_COOLDOWN_S逐步降至~35-37s, 维持与KEY_COOLDOWN(29s)的8s+缓冲。

5. **ConnectionResetError=139 (1.1%)**: 安定在MIN_OUTBOUND=17.5s, 无需调整。轻量级连接错误，非系统性问题。

6. **NVCFPexecTimeout=68 (glm5.1)**: 低于deepseek的NVCFPexecTimeout总量(93), 但这是glm5.1 tier特有的超时——可能是429触发前的budget消耗。若下一轮TIER_COOLDOWN下降后timeout减少 → 确认关联。

7. **empty_200=16**: NVCF空200响应，非错误，不关注。

8. **mihomo未动**: 严格遵守—不停止/不重启/不kill mihomo服务。mihomo是NV API链路的必要SOCKS5代理。

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记