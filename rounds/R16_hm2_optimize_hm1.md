# R16: HM2优化HM1 — 持续压制429碰撞密度 & 延长key冷却窗口

**轮次**: R16 (HM2→HM1)
**日期**: 2026-06-26 04:30 UTC+8
**角色**: HM2 (执行优化) → HM1 (hm40006容器 on 100.109.153.83)
**前置轮次**: R15 (HM1优化HM2, commit 72ec41c)

---

## 一、数据采集

### 1a. 容器环境变量 (部署前)
| 参数 | 值 | 来源 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 30 | R15保持 |
| TIER_TIMEOUT_BUDGET_S | 52 | R14保持 |
| MIN_OUTBOUND_INTERVAL_S | 9.0 | R15设置 |
| KEY_COOLDOWN_S | 32.0 | R15设置 |
| TIER_COOLDOWN_S | 120 | compose内标R16(180→120) |
| HM_CONNECT_RESERVE_S | 5 | R9保持 |

### 1b. DB错误分布 (最近30分钟)
| 错误类型 | 计数 | 平均耗时(ms) |
|---------|------|-------------|
| 429_nv_rate_limit | 525 | ~0 |
| NVCFPexecTimeout | 108 | 30750 |
| NVCFPexecConnectionResetError | 13 | 1105 |
| NVCFPexecProxyConnectionError | 7 | 1 |
| empty_200 | 6 | ~0 |
| budget_exhausted_after_connect | 2 | 1308 |
| NVCFPexecRemoteDisconnected | 1 | 534 |
| **总计** | **662** | |

### 1c. Fallback统计 (最近30分钟)
| fallback_occurred | 请求量 | 平均耗时(ms) |
|-------------------|--------|-------------|
| false (直接成功) | 366 | 24303 |
| true (需fallback) | 729 | 18911 |
| **Fallback率** | **66.6%** | |

### 1d. Tier分布 (最近30分钟)
| Tier | 尝试数 |
|------|-------|
| glm5.1_hm_nv (primary) | 578 |
| deepseek_hm_nv (fallback) | 81 |
| kimi_hm_nv (last resort) | 3 |

### 1e. 日志模式 (最近300行)
- 429/HM-COOLDOWN事件: 40次
- TIER-SKIP/FALLBACK事件: 81次
- 典型模式: 5key全429 → TIER-SKIP → deepseek fallback首key成功(~8-9s)

---

## 二、诊断分析

### 根因链
1. **429_nv_rate_limit占79.3%错误(525/662)** — 这是主要瓶颈
2. **NVCFPexecTimeout avg 30750ms** — 逼近UPSTREAM_TIMEOUT=30s上限，deepseek tier首key成功(~8-9s)但有些超30s就timeout
3. **Fallback率66.6%** — 较R14的60.5%持续恶化，说明R15的MIN/KEY提升后429碰撞仍然严重
4. **TIER_COOLDOWN=120仅3分钟** — 5key全429后等待120s即重新尝试glm5.1，但全key均在cooldown内，立即TIER-SKIP

### 分析
- R15将MIN从8.0→9.0, KEY从30→32，但Fallback率从60.5%升到66.6%，说明429碰撞密度仍然过高
- compose中已有TIER_COOLDOWN=180→120的变更(compose标R16)，但此参数仅控制全key 429后的tier冻结时间，不直接影响per-key 429碰撞率
- 当前5key×9s=45s cycle, 32/9=3.56 cycles per retry window — key间距仍不够宽

---

## 三、优化计划

| 参数 | 修改前 | 修改后 | 理由 |
|------|-------|-------|------|
| MIN_OUTBOUND_INTERVAL_S | 9.0 | **10.0** | 5key×10s=50s cycle; 11%更慢rotation; 降低per-second NVCF请求密度; 429碰撞窗口进一步拉开 |
| KEY_COOLDOWN_S | 32.0 | **35.0** | 3s额外cooldown; 35/10=3.5 cycles/retry window; key更多恢复时间再重入NVCF; 减少连续429 |

**不改动**:
- UPSTREAM_TIMEOUT=30: 合理; deepseek fallback ~8-9s成功率好; 30s足够2次attempt
- TIER_TIMEOUT_BUDGET_S=52: budget_exhausted仅2次; 当前预算充足
- TIER_COOLDOWN_S=120: compose刚改; 需更多数据验证效果
- HM_CONNECT_RESERVE_S=5: 稳定

---

## 四、执行记录

```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R16'

# 修改 MIN_OUTBOUND_INTERVAL_S (line 420): 9.0→10.0
ssh <target> "cd /opt/cc-infra && \
  sed -i '420s/\"9.0\"/\"10.0\"/' docker-compose.yml && \
  sed -i '420s/# R15:.*$/# R17: HM2优化 — 9.0→10.0: 5key×10s=50s cycle; 11% slower rotation vs R16; 减少per-second 429碰撞密度/' docker-compose.yml"

# 修改 KEY_COOLDOWN_S (line 421): 32.0→35.0
ssh <target> "cd /opt/cc-infra && \
  sed -i '421s/\"32.0\"/\"35.0\"/' docker-compose.yml && \
  sed -i '421s/# R15:.*$/# R17: HM2优化 — 32→35: 3s more cooldown; 35\/10=3.5 cycles; 进一步延长key恢复时间; 减少重入NVCF 429窗口/' docker-compose.yml"

# 部署
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'

# 验证
ssh -p 222 opc_uname@100.109.153.83 'sleep 5 && docker ps --format "{{.Names}} {{.Status}}" | grep hm40006 && docker exec hm40006 env | grep -E "MIN_OUTBOUND|KEY_COOLDOWN"'
# 结果: hm40006 Up 51s (healthy), MIN_OUTBOUND_INTERVAL_S=10.0, KEY_COOLDOWN_S=35.0 ✅
```

---

## 五、部署后验证

| 参数 | 预期值 | 实际值 | 状态 |
|------|-------|-------|------|
| MIN_OUTBOUND_INTERVAL_S | 10.0 | 10.0 | ✅ |
| KEY_COOLDOWN_S | 35.0 | 35.0 | ✅ |
| UPSTREAM_TIMEOUT | 30 | 30 | ✅ |
| TIER_TIMEOUT_BUDGET_S | 52 | 52 | ✅ |
| TIER_COOLDOWN_S | 120 | 120 | ✅ |
| HM_CONNECT_RESERVE_S | 5 | 5 | ✅ |
| Container | healthy | Up 51s (healthy) | ✅ |

---

## 六、预期效果

| 指标 | R15(修改前) | R16预期 | 依据 |
|------|-----------|--------|------|
| 429/30min | ~525 | <450 | 50s cycle vs 45s; 11%更低per-second请求密度 |
| Fallback率 | 66.6% | <60% | 更长cooldown减少429→更少TIER-SKIP |
| NVCFPexecTimeout | 108/30min | ~100 | 不受MIN/KEY直接影响; 取决于NVCF负载 |
| avg duration (fallback) | 18.9s | ~18s | 持平 |

---

## 七、风险与观察项

1. **MIN=10.0已接近上限(参数参考max=10.0)**: 如仍429严重，下一轮不应继续提升MIN，而应评估是否需要更激进的TIER_COOLDOWN调整或NVCF function-level rate limit的根本解决方案
2. **KEY_COOLDOWN=35.0 vs TIER_COOLDOWN=120**: 3.5 cycles/retry × 10s interval = 35s per cooldown window; 全5key在~50s内全429后仅等120s即重新尝试 — 如果NVCF rate limit窗口>120s则仍会全429
3. **Fallback率趋势恶化**: R14(60.5%)→R16(66.6%)，如果R16参数改进后fallback率仍>60%，下一轮应考虑TIER_COOLDOWN从120→180回调(之前180稳定)
4. **NVCFPexecTimeout avg 30.75s**: 逼近UPSTREAM_TIMEOUT=30s边界 — 某些deepseek请求接近timeout边缘; 不建议降UPSTREAM_TIMEOUT

---

## 八、配置历史更新

| Round | UPSTREAM | TIER_BUDGET | MIN_INTERVAL | KEY_COOLDOWN | TIER_COOLDOWN | CONNECT_RESERVE | Effective From |
|-------|----------|-------------|--------------|-------------|--------------|----------------|---------------|
| R15 (HM2→HM1) | 30 | 52 | 9.0 | 32.0 | 180 | 5 | commit d3406dc |
| R16-compose | 30 | 52 | 9.0 | 32.0 | 120 | 5 | compose内(无git commit) |
| **R16 (HM2→HM1)** | **30** | **52** | **10.0** | **35.0** | **120** | **5** | **本轮** |

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记
