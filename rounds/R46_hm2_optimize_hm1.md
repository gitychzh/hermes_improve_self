# R46: HM2→HM1 优化执行记录

**日期**: 2026-06-26 15:20  
**执行者**: HM2 (opc2_uname)  
**目标**: HM1 (100.109.153.83:222)  
**源起**: 检测到 opc_uname(HM1) 提交 c640d9282b39bbfcc1894a5cb9e1bbb4361040bd, 轮到HM2优化

---

## 1. 数据采集 (30分钟窗口)

### 1a. 日志模式 (tail 100)
```
grep -ciE '(error|warn|fail)' → 18 匹配行
TTL: 100 lines, 错误率高但可接受
```

### 1b. 容器环境变量 (运行中)
| 参数 | 值 | 说明 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 42 | R18: HM2优化 35→40 |
| TIER_TIMEOUT_BUDGET_S | 96 | R44: HM2优化 94→96 |
| MIN_OUTBOUND_INTERVAL_S | 14.0 | R42: HM2优化 13.5→14.0 |
| KEY_COOLDOWN_S | 38.0 | R19: HM2优化 35→38 |
| TIER_COOLDOWN_S | 82 | R45: HM2优化 84→82 |
| HM_CONNECT_RESERVE_S | 22 | R29: HM2优化 21→22 |

### 1c. 错误分布 (hm_tier_attempts, 30min)
| 错误类型 | 次数 | 平均耗时(ms) |
|----------|------|-------------|
| 429_nv_rate_limit | 1,158 | — |
| NVCFPexecTimeout | 94 | 28,437 |
| NVCFPexecConnectionResetError | 38 | 2,073 |
| budget_exhausted_after_connect | 5 | 797 |
| NVCFPexecRemoteDisconnected | 5 | 2,483 |

### 1d. Fallback统计
- 总请求: 1,302
- Fallback: 1,176 (90.3%)
- 直达(无fallback): 126 (9.7%)
- 直达平均耗时: 15,944ms
- Fallback平均耗时: 19,391ms

### 1e. 主Tier键级分析 (glm5.1)
```
0 行 → glm5.1 tier 完全无法成功, 所有请求进入 fallback 或 deepseek 层
```

### 1g. Tier分布
| Tier | 尝试次数 |
|------|---------|
| glm5.1_hm_nv | 1,201 |
| deepseek_hm_nv | 97 |
| kimi_hm_nv | 2 |

### 1k. Deepseek超时按键分桶 (30min)
| Key | <20s | 20-25s | 25-30s | 30-35s | >40s |
|-----|------|---------|---------|---------|------|
| k0 | 7 | 1 | 3 | 0 | 4 |
| k1 | 10 | 2 | 1 | 0 | 7 |
| k2 | 5 | 2 | 1 | 0 | 11 |
| k3 | 6 | 5 | 1 | 0 | 5 |
| k4 | 8 | 0 | 1 | 1 | 10 |

**总计桶**: <20s=36, 20-25s=10, 25-30s=7, 30-35s=1, >40s=37

### Deepseek其他错误
| 错误类型 | 次数 | 平均耗时(ms) |
|----------|------|-------------|
| NVCFPexecConnectionResetError | 38 | (per-key ~7-8) |
| SSLEOF类 | ~4 | 日志计数 |
| 0-tier all_tiers_exhausted | 2 | avg 180,404ms (tiers_tried_count=0) |

---

## 2. 诊断

### 根本原因分析

**glm5.1 功能级429饱和**: 1,158次429在30分钟内, 所有5个键同时被限流。这是NVCF层面的全局功能限流(function-level rate limit), 非per-key问题。glm5.1成功率为0% — 无单次主Tier请求成功。

**Deepseek >40s桶成为最大超时群**: 37/91次(40.7%) 深seek超时落在UPSTREAM=42的上限以外。在UPSTREAM=42下, 1st-attempt=42s, 这些请求刚好超过上游超时线。需要提升UPSTREAM_TIMEOUT来捕获这些边界请求。

**ConnectionResetError上升**: 从R45的29→38(+9, +31%), 跨所有键均匀分布(每键~7-8)。这是TIER_COOLDOWN继续降低(R45→82)带来的副作用 — 更多的重试意味着更多的连接重置。

**TIER_COOLDOWN降低轨迹已达极限**: R34→R45: 90→88→86→84→82, 每轮-2s。继续降低到80s以下会进一步恶化ConnectionResetError, 且glm5.1的0%成功率意味着更多重试不会提高吞吐量。

### 优化决策

**单参数变更: UPSTREAM_TIMEOUT 42→44 (+2s)**

理由:
1. **>40s桶最大**: 37个事件(40.7%)需要>42s完成。提升到44s后, 这些完成可以进入1st-attempt范围。
2. **少改多轮**: 仅改一个参数, 符合铁律。
3. **安全边界**: UPSTREAM=44, BUDGET=96, RESERVE=22 → 1st=44s, 2nd=max(10, min(44, 52-22=30))=30s (≥10s下限, 安全)。
4. **不降低TIER_COOLDOWN**: 避免恶化ConnectionResetError。

---

## 3. 优化执行

| 参数 | 修改前 | 修改后 | 行号 | 理由 |
|------|--------|--------|------|------|
| UPSTREAM_TIMEOUT | 42 | **44** | 417 | +2s捕获>40s deepseek超时边界 |

### 执行命令
```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 "cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R46"

# 改值 (行417)
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && sed -i "417s/\"42\"/\"44\"/" docker-compose.yml'

# 改注释 (行417)
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '417s/# R18: HM2优化.*$/# R46: HM2优化 — 42→44: +2s upstream timeout .../' docker-compose.yml"

# 部署
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && docker compose up -d hm40006"
# → Container hm40006 Recreated, Started (healthy)

# 验证
ssh -p 222 opc_uname@100.109.153.83 'sleep 5 && docker exec hm40006 env | grep UPSTREAM_TIMEOUT'
# → UPSTREAM_TIMEOUT=44 ✓
```

### 验证状态
- ✅ 容器健康: `hm40006 Up 31 seconds (healthy)`
- ✅ 环境变量: UPSTREAM_TIMEOUT=44, BUDGET=96, MIN=14.0, KEY=38.0, TIER_COOLDOWN=82, RESERVE=22
- ✅ Compose注释: 行417已更新为R46标记

---

## 4. 预期效果

### 量化预测
- **Deepseek >40s桶**: 从37→目标~20-25 (UPSTREAM从42→44, 1st-attempt捕获+2s窗口)
- **Fallback率**: 维持90%±2% (glm5.1 429无变化)
- **ConnectionResetError**: 维持35-40/30min (无变化, TIER_COOLDOWN未改)
- **0-tier失败**: 维持2-3/30min (RESERVE=22稳定)
- **SSLEOF**: 维持<5/30min (MIN_INTERVAL=14.0已验证)

### 预算重算 (UPSTREAM=44)
```
1st attempt = min(44, 96-22=74) = 44s
Remaining   = 96-44 = 52s
2nd attempt = max(10, min(44, 52-22=30)) = 30s ✓ (≥10s安全下限)
```

---

## 5. 观察项

### 风险
- ⚠️ **2nd-attempt从32s→30s**: 损失2s headroom。但1st-attempt从42s→44s(+2s)的增益应超过2nd-attempt损失。
- ⚠️ **UPSTREAM增加可能增加总延迟**: +2s上游超时意味着更多请求等待完整44s后才进入fallback。但deepseek平均fallback时长(19,391ms)表明多数请求在超时前完成。
- ⚠️ **NVCF基础设施级预算耗尽**: >40s桶(37个)即使UPSTREAM=44也可能继续存在 — 这些是真正的NVCF层级超时, 非headroom不足。

### 下次应关注
- **>40s桶是否下降**: 如果UPSTREAM=44后>40s桶仍然>30, 说明这是NVCF基础设施层问题, 需要更多UPSTREAM提升或调查proxy端口健康度
- **ConnectionResetError趋势**: 如果继续上升到50+在30min, 考虑提升MIN_OUTBOUND_INTERVAL(14.0→14.5)来降低连接重置
- **0-tier是否保持低位**: 当前2个事件是历史最低, 验证UPSTREAM变更是否间接恶化连接级失败

---

## 6. 铁律确认

- [x] 只改HM1 docker-compose.yml, 未触碰HM2本地
- [x] 单参数变更 (少改多轮)
- [x] Docker compose up -d hm40006 (container-only, 未改动mihomo)
- [x] 作者=opc2_uname

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记