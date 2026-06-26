# R80: HM2→HM1 — KEY_COOLDOWN_S 33.0→31.0 (-2s), 键冷却加速429恢复

**时间**: 2026-06-27 04:35 UTC  
**执行者**: HM2 (opc2_uname)  
**方向**: HM2优化HM1  
**上一轮**: R79 (HM2→HM1, MIN_OUTBOUND_INTERVAL_S 15.5→17.5, TIER_COOLDOWN_S 68→55)  
**响应**: R13 (HM1→HM2, KEY_COOLDOWN_S 35.0→33.0, 收敛HM1基线)

---

## 📊 采集数据 (HM1 hm40006, 30-min窗口 04:04-04:35 CST)

### 1. 日志模式 (100行采样)

| 模式 | 出现频率 |
|---|---|  
| HM-TIER-SKIP (all keys in cooldown) | ~每请求都触发 |
| HM-FALLBACK (glm5.1→deepseek) | ~每请求都触发 |
| HM-COOLDOWN (429标记) | 所有5键均匀 |
| HM-CYCLE (429 cycle) | 每请求5键全失败 |
| HM-SUCCESS (deepseek直通) | 大部分成功 |
| SSLEOFError (SSL) | 偶尔出现 |
| HM-GLOBAL-COOLDOWN (55s) | 每429循环后触发 |

### 2. 容器环境变量 (hm40006, 部署前)

| 参数 | 值 |
|---|---|  
| UPSTREAM_TIMEOUT | 62 |
| TIER_TIMEOUT_BUDGET_S | 104 |
| MIN_OUTBOUND_INTERVAL_S | 17.5 |
| KEY_COOLDOWN_S | 33.0 |
| TIER_COOLDOWN_S | 55 |
| HM_CONNECT_RESERVE_S | 22 |

### 3. DB错误分布 (hm_tier_attempts, 30min)

| 错误类型 | 计数 | 平均耗时(ms) |
|---|---|---| 
| 429_nv_rate_limit | 1,053 | — |
| NVCFPexecTimeout | 120 | 25,291 |
| NVCFPexecConnectionResetError | 48 | 3,251 |
| empty_200 | 10 | — |
| budget_exhausted_after_connect | 7 | 2,270 |
| NVCFPexecRemoteDisconnected | 5 | 2,566 |

### 4. 请求成功率 (hm_requests, 30min)

- 总请求: 1,267
- Fallback: 876 (69.1%)
- 直接成功 (glm5.1): 391 (30.9%)

### 5. 429周期分布

| 429周期 | 请求数 |
|---|---|  
| 0 | 883 (69.7%) |
| 1 | 129 (10.2%) |
| 2 | 41 (3.2%) |
| 3 | 26 (2.1%) |
| 4 | 46 (3.6%) |
| 5 | 119 (9.4%) |
| 6+ | 23 (1.8%) |

429周期率: 384/1267 = 30.3%

### 6. Deepseek超时桶分布 (NVCFPexecTimeout)

| 桶 | 计数 |
|---|---|  
| <20s | 47 |
| 20-25s | 4 |
| 50-55s | 1 |
| 55-60s | 2 |
| >60s | 9 |

### 7. 按键429分布 (glm5.1)

k0=243, k1=214, k2=204, k3=200, k4=189 → 均匀函数级速率限制

### 8. 最近请求 (10条抽样)

deepseek avg ~21s, glm5.1->deepseek fallback dominant

---

## 🔍 诊断

**根本原因**: 429函数级速率限制 → glm5.1全键429 → 键恢复慢(33s) → 30.3%周期率

**优化向量**: KEY_COOLDOWN_S降低(-2s) → 键恢复更快 → 更多glm5.1直通尝试

**预算**: UPSTREAM=62, BUDGET=104, RESERVE=22 → 1st=62s, 2nd=20s (决策边界,安全)

---

## ⚙️ 优化执行

| 参数 | 前值 | 后值 | 变化 | 理由 |
|---|---|---|---|---|
| KEY_COOLDOWN_S | 33.0 | 31.0 | -2s | 加速键429恢复; 429周期率30.3%→预计~27-28% |

### 执行

```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 "cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R80"
# 值变更 (行421)
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '421s/\"33.0\"/\"31.0\"/' docker-compose.yml"
# 注释更新
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '421s/# R71:.*$/# R80: .../' docker-compose.yml"
# 部署
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && docker compose up -d hm40006"
```

### 验证

```
KEY_COOLDOWN_S=31.0 ✓
Container: hm40006 Up (healthy) ✓
```

---

## 📈 预期效果

- 429周期率: 30.3% → ~27-28%
- glm5.1直通: 30.9% → ~32-33%
- Fallback: 69.1% → ~66-68%

## ⚠️ 观察项

- 键冷却下界: 31s距R12最低30s仅1s缓冲
- 监控ConnectionResetError: >60需MIN升高
- SSLEOFError: 偶尔出现
- 预算已满连接后=7 → 不显著
- empty_200=10 → NVCF级低频

## ✅ 合规性

- ✅ 少改多轮(单参数 -2s)
- ✅ 铁律:只改HM1不改HM2

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记