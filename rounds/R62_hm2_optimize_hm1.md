# R62: HM2→HM1 优化轮

**日期**: 2026-06-26 20:20  
**角色**: HM2 (opc2_uname)  
**目标**: HM1 (100.109.153.83, opc_uname)  
**前一轮**: R61 (HM2→HM1: TIER_TIMEOUT_BUDGET_S 98→100) + R61 (HM1→HM2: UPSTREAM_TIMEOUT 62→60)  
**检测触发**: HM1提交 R61_hm1_optimize_hm2.md (commit bcb6535), 结尾标记 `轮到HM2优化HM1`

---

## 📊 数据采集 (30分钟窗口)

### 1. 日志统计
```
docker logs hm40006 --tail 100: 18 error/warn/fail 匹配行
```

### 2. 运行环境 (HM1)
| 参数 | 值 |
|------|-----|
| UPSTREAM_TIMEOUT | **56** |
| TIER_TIMEOUT_BUDGET_S | **100** |
| MIN_OUTBOUND_INTERVAL_S | **14.0** |
| KEY_COOLDOWN_S | **38.0** |
| TIER_COOLDOWN_S | **82** |
| HM_CONNECT_RESERVE_S | **22** |

### 3. DB错误分布 (hm_tier_attempts, 30min)
| 错误类型 | 数量 | avg_elapsed_ms |
|----------|------|-----------------|
| 429_nv_rate_limit (glm5.1) | 1,044 | — |
| NVCFPexecConnectionResetError | 58 | 1,952 |
| NVCFPexecTimeout (deepseek) | 44 | 33,528 |
| NVCFPexecRemoteDisconnected | 5 | 1,322 |
| budget_exhausted_after_connect | 2 | 963 |

### 4. 请求路由 (hm_requests)
```
直接 (fallback=false):  137 请求 (12.2%), avg_dur=17,261ms
回退 (fallback=true):   990 请求 (87.8%), avg_dur=22,271ms
总计:                   1,127 请求
```

### 5. Tier分布
```
glm5.1_hm_nv:   1,109 次尝试 (98.4% — 全部429)
deepseek_hm_nv:  43 次尝试
kimi_hm_nv:      1 次尝试
```

### 6. Deepseek超时桶分布 (NVCFPexecTimeout)
| 桶 | 数量 | % |
|----|------|---|
| <20s | 14 | 31.8% |
| 20-25s | 1 | 2.3% |
| 25-30s | 2 | 4.5% |
| 30-35s | 5 | 11.4% |
| >40s | **19** | **43.2%** |

### 7. 0-tier (tiers_tried_count=0)
```
0 条 — 完全消除 (连续第三轮)
```

### 8. Deepseek ConnectionResetError 按键
```
k0→k4: 5→8→12→9→7  (均匀分布，共43+2 budget_exhausted)
```

---

## 🔍 诊断

### 瓶颈 #1: >40s超时桶仍占主导 (19/44=43.2%)
>40s桶的19个事件是最大单一超时组，占比43.2%。虽然绝对计数从R46的37下降到19，但该桶仍是最主要的超时模式。这代表NVCF基础设施层面的完整链接预算耗尽。

### 瓶颈 #2: 回退率87.8% (稳定)
glm5.1全线429 (函数级限流100%饱和)，deepseek fallback承担实际吞吐。回退率稳定在87-88%区间。

### 瓶颈 #3: ConnectionResetError=58 (稳定)
deepseek tier的ConnectionResetError=58，与R61的59持平。均匀分布在所有5个key上，属于NVCF基础设施级别现象。

### 决策: UPSTREAM轨迹继续 (56→58)

**依据**:
- R58→R60→R61的交替模式 (BUDGET→UPSTREAM→BUDGET) 已确认
- R61是BUDGET扩张 (98→100)，下一轮应为UPSTREAM扩张
- 当前UPSTREAM=56，2nd=22s。UPSTREAM→58后，2nd=max(10, min(58, 100-58-22=20)) = 20s
- 20s是决策边界，但经R56和R60验证为安全
- >40s=19 (43.2%主导) — 继续UPSTREAM轨迹可捕获58-60s的边界完成

**本次变更**: UPSTREAM_TIMEOUT 56→58 (+2s)

---

## ⚙️ 变更执行

| 参数 | 变更前 | 变更后 | 理由 |
|------|--------|--------|------|
| UPSTREAM_TIMEOUT | 56 | **58** | +2s: 继续UPSTREAM轨迹，捕获NVCF边界完成；少改多轮 |

### SSH命令
```bash
# 备份
ssh HM1 "cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R62"

# 值变更 (line 417)
ssh HM1 "cd /opt/cc-infra && sed -i '417s/\"56\"/\"58\"/' docker-compose.yml"

# 注释更新
ssh HM1 "cd /opt/cc-infra && sed -i '417s/# R60: HM2优化.*$/# R62: HM2优化 — 56→58: +2s upstream timeout; UPSTREAM=58 BUDGET=100 RESERVE=22 1st=58s remain=42 2nd=20s; deepseek >40s=19(43.2%主导); 少改多轮(单参数); 铁律:只改HM1不改HM2/' docker-compose.yml"

# 部署
ssh HM1 "cd /opt/cc-infra && docker compose up -d hm40006"
```

### 验证
```
UPSTREAM_TIMEOUT=58 ✓
hm40006 Up 19 seconds (healthy) ✓
```

---

## 📈 预期效果

**预算计算 (变更后)**:
- UPSTREAM=58, BUDGET=100, RESERVE=22
- 1st attempt: min(58, 100-22=78) = **58s**
- remaining: 100-58 = 42
- 2nd attempt: max(10, min(58, 42-22=20)) = **20s** (决策边界)

**预期**:
- >40s桶从19→~16-17 (捕获58-60s边界完成)
- 回退率微降至~86-87% (更多1st-attempt成功)
- ConnectionResetError稳定在55-60
- 0-tier保持0 (连续3轮)

---

## ⚠️ 观察项

- **2nd-attempt=20s在决策边界**: 经R56/R60验证为安全，但仍需监控
- **下一轮UPSTREAM→60**: 2nd=18s (低于20s硬限，必须先BUDGET→102)
- **少改多轮**: 单参数变更 (+2s)
- **铁律**: 只改HM1不改HM2 ✓

---

## 📝 本轮总结

R62延续UPSTREAM轨迹 (R46→R48→R50→R52→R54→R56→R60→R62).  
在R61的BUDGET扩容后继续UPSTREAM提升.  
2s虽小, 但在多键循环中累积有效果.  
实际瓶颈仍是NVCF函数级限流(100%饱和), 无法通过纯参数调整解决.  
当前系统以deepseek fallback成功为主, glm5.1仅做首次尝试(全部429).

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记