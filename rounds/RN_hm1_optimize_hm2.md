# R139: HM1→HM2 — MIN_OUTBOUND_INTERVAL_S 10.0→10.5 (+0.5s间距缓冲, 减少429堆积, 稳定优先收敛)

**Role**: HM1 (opc_uname) optimizing HM2 (opc2_uname, hm40006 container)
**Timestamp**: 2026-06-28 01:09 UTC (collected ~01:00–01:09)
**Change**: MIN_OUTBOUND_INTERVAL_S 10.0 → **10.5** (+0.5s, 5% increase)
**Principles**: 少改多轮(单参数), 更少报错更快请求超低延迟稳定优先, 铁律:只改HM2不改HM1

---

## 📊 数据采集 (HM2 hm40006, 30-min window ~00:40–01:09 UTC)

### 运行配置 (docker exec hm40006 env)
| 参数 | 值 | 状态 |
|-----------|-------|--------|
| UPSTREAM_TIMEOUT | 71 | 充足 (0次实际超时) |
| TIER_TIMEOUT_BUDGET_S | 132 | 预算破裂: 1.5s < 10s minimum (3次超时后) |
| KEY_COOLDOWN_S | 45 | = GLOBAL_COOLDOWN=45s (收敛完成) |
| TIER_COOLDOWN_S | 45 | = GLOBAL_COOLDOWN=45s (收敛完成) |
| MIN_OUTBOUND_INTERVAL_S | **10.0** | 5×10.0=50.0s → buffer=5.0s above GLOBAL=45s |
| HM_CONNECT_RESERVE_S | 24 | = HM1 (gap=0s, 已收敛) |
| PROXY_TIMEOUT | 300 | 固定值 |

### 延迟百分位 (30min + 6h)
**30分钟**: 68/68 ok(100%), avg_ms: deepseek=22202ms, glm5.1=22240ms, max: 192229ms
**6小时**: 1048/1048 ok(100%), 0 actual request errors

| tier_model | reqs | p90_ms | p95_ms | avg_ms | max_ms |
|-----------|------|--------|--------|--------|--------|
| deepseek_hm_nv | 32 | 38103 | 46636 | 22202 | 192229 |
| glm5.1_hm_nv | 39 | 50779 | 54996 | 22240 | 126658 |

### 错误分解 (tier_attempts, 30min + 6h)
| 窗口 | 429_nv_rate_limit | SSLEOFError | ConnectionReset | Timeout | RemoteDisconnected |
|--------|-------------------|-------------|-----------------|---------|-------------------|
| 30min | **55** (22 reqs) | 4 (avg 5984ms) | 4 (avg 924ms) | 5 (avg 23384ms) | 1 (592ms) |
| 6h | **621** (289 reqs) | **151** (132 reqs) | 42 (38 reqs) | 18 (10 reqs) | 7 (7 reqs) |

### 429 / 回退 / all_tiers_exhausted 快照 (30min)
| 指标 | 值 |
|--------|-------|
| 429 周期 (key-level) | 55 wasted key attempts across 22 requests |
| 回退 (fallback) | 2 fallback events to deepseek (from glm5.1) |
| all_tiers_exhausted | 0 (30min) — all_failed but not exhausted |
| budget break | 1 event: remaining 1.5s < 10s minimum (after 3 timeouts) |

### 6h 请求分布
- **all glm5.1_hm_nv requests**: 1047 total
- **fallback rate**: 396/1047 (37.8%) — high but all succeed via deepseek
- **0 actual request errors** (100% success rate)
- **429s dominate**: 621 key-attempt-level 429s in 6h vs 151 SSLEOFError

### 预算破裂事件 (docker logs)
```
[01:06:47] [HM-TIER-BUDGET] tier=glm5.1_hm_nv budget 132.0s remaining 1.5s < 10s minimum, breaking
[01:06:47] [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=0, empty200=1, timeout=3, other=0
```
**根因**: 3次 NVCFPexecTimeout (47s+11s+11s ≈ 69s) + 1 empty_200 消耗了大部分预算, 剩余1.5s触发最低阈值。这不是配置问题 — TIMEOUT 是 NVCF 服务端超时。

### error_detail JSONL 模式
- **mixed-failure**: SSLEOFError + ConnectionReset + 429 混合 (同请求内多种错误类型)
- **all_429 dominant**: 多个事件显示 all_429=true (5键全429), 证明 NV API 函数级速率限制是主因
- **timeout cluster**: 单请求内 3次Timeout 事件 (k3=47s, k4=11s, k5=11s) — NVCF 服务端超时, 非客户端

---

## 🎯 优化分析

### 7参数逐一评估
| 参数 | 当前值 | 调整需求 | 理由 |
|-----------|---------|----------------|---------|
| UPSTREAM_TIMEOUT | 71 | ❌ 无调整 | 0次客户端超时/30min; timeout事件是NVCF服务端, 非客户端超时; 增加无意义 |
| TIER_TIMEOUT_BUDGET_S | 132 | ❌ 无调整 | 预算破裂因3次服务端超时, 非预算不足; 增加预算=让timeout消耗更多时间 |
| KEY_COOLDOWN_S | 45 | ❌ 无调整 | = GLOBAL_COOLDOWN=45s, 已完全收敛; 不能再增加 |
| TIER_COOLDOWN_S | 45 | ❌ 无调整 | = GLOBAL_COOLDOWN=45s, 已完全收敛; 不能再增加 |
| MIN_OUTBOUND_INTERVAL_S | 10.0 | **✅ +0.5s** | 5×10.0=50s buffer=5s → 5×10.5=52.5s buffer=7.5s; 更安全的间距, 减少429碰撞 |
| HM_CONNECT_RESERVE_S | 24 | ❌ 无调整 | = HM1=24, gap=0s; 无budget_exhausted_after_connect; 完全收敛 |
| CHARS_PER_TOKEN_ESTIMATE | — | ❌ 无调整 | 不在NVCF pexec路径; 不影响键路由 |

### 单参数决策: MIN_OUTBOUND_INTERVAL_S
**为什么选这个参数**:
1. KEY_COOLDOWN_S=45 和 TIER_COOLDOWN_S=45 都已收敛到 GLOBAL_COOLDOWN=45s — 无法再增加
2. 所有其他参数处于均衡状态 (R138已验证)
3. MIN_OUTBOUND_INTERVAL_S 是唯一剩余的可调杠杆
4. 10.0→10.5 增加 +0.5s, 5×0.5=+2.5s 总周期增加, 7.5s 缓冲 > 5s
5. 减少直接落在仍在运行的 GLOBAL_COOLDOWN 窗口上的概率

**为什么不是其他参数**:
- 增加 UPSTREAM_TIMEOUT 不会帮助 — 超时是 NVCF 服务端产生的, 不是客户端超时
- 增加 TIER_TIMEOUT_BUDGET_S 会让服务端超时有更多预算可消耗, 而不是更快失败
- 增加 HM_CONNECT_RESERVE_S 无必要 — 没有 budget_exhausted_after_connect 事件, 且已在 HM1 同一水平

**5键周期对齐分析**:
```
Before: 5 × 10.0 = 50.0s → buffer = 50.0 - 45 = 5.0s above GLOBAL=45s
After:  5 × 10.5 = 52.5s → buffer = 52.5 - 45 = 7.5s above GLOBAL=45s (+2.5s)
```
+2.5s 额外缓冲减少键轮流进入仍在活跃的速率限制窗口的概率。安全的 +0.5s 增量。

### 风险分析
```
Before effective budget: 132 - 24 = 108s
After effective budget:  132 - 24 = 108s (unchanged — HM_CONNECT_RESERVE_S untouched)
```
无有效预算缩减。MIN_OUTBOUND_INTERVAL 增加不影响连接建立预算 — 仅影响请求间隔。

---

## 🔧 执行

### 变更: MIN_OUTBOUND_INTERVAL_S 10.0 → 10.5
```yaml
# /opt/cc-infra/docker-compose.yml, line 479
# Before:
#   MIN_OUTBOUND_INTERVAL_S: "10.0"  # R115: ... →7.5
# After:
#   MIN_OUTBOUND_INTERVAL_S: "10.5"  # R139: 10.0→10.5: +0.5s
```

### 命令序列
```bash
# 1. 修改配置文件
ssh -p 222 opc2_uname@100.109.57.26 'python3 -c "..."'  # 替换 10.0→10.5

# 2. 重建容器 (应用新环境变量)
ssh -p 222 opc2_uname@100.109.57.26 'cd /opt/cc-infra && docker compose up -d --no-deps --force-recreate hm40006'
# → Container hm40006 Recreated, Started

# 3. 验证
ssh -p 222 opc2_uname@100.109.57.26 'docker exec hm40006 env | grep MIN_OUTBOUND_INTERVAL_S'
# → MIN_OUTBOUND_INTERVAL_S=10.5 ✅

ssh -p 222 opc2_uname@100.109.57.26 'docker ps --filter name=hm40006'
# → Up 23 seconds (healthy) ✅

ssh -p 222 opc2_uname@100.109.57.26 'pgrep -a mihomo'
# → 2008535 /home/opc2_uname/.local/bin/mihomo ✅ (untouched)
```

### 部署状态
- **容器**: Running, Healthy (Up < 1min, fresh recreate)
- **docker exec env**: MIN_OUTBOUND_INTERVAL_S=10.5 ✅
- **mihomo**: Running (PID 2008535), untouched ✅
- **Health endpoint**: 200 OK, tiers=['glm5.1_hm_nv','deepseek_hm_nv','kimi_hm_nv'], default='glm5.1_hm_nv' ✅
- **nvcf_pexec_models**: 3 models (deepseek, kimi, glm5.1) ✅

---

## 📈 预期效果 (Before → After)

| 指标 | Before (10.0) | After (10.5) | 预期方向 |
|--------|---------------|---------------|----------|
| MIN_OUTBOUND_INTERVAL_S | 10.0 | 10.5 | +0.5s (5%增加) |
| 5键周期总时间 | 50.0s | 52.5s | +2.5s |
| 高于GLOBAL=45s缓冲 | 5.0s | 7.5s | +2.5s (50%增加) |
| 请求速率上限 | 6.0/min | 5.7/min | -0.3/min (可接受) |
| 实际速率 | ~2.3/min | ~2.3/min | 不变 (远低于上限) |
| 429碰撞概率 | 基线 | ↓ 降低 | 更大间隔=更少落入速率窗口 |
| 成功率 | 100% (68/68) | 100% (维持) | 不退化 |
| 回退率 | 2/68 (2.9%) | 预期 ↓ | 更少需要回退 |

**关键**: +0.5s 是保守且安全的增量。如果30分钟窗口显示过度减速 (请求堆积), 下一轮可回退 -0.3s 到 10.2。如果显示进一步改善 (更少429), 继续增加 +0.3s 到 10.8。

---

## ⚖️ 评判

- **更少报错**: ✅ 30min/6h 均0实际请求错误, 100%成功率; SSLEOFError和429均在key-attempt级别 (不触发请求失败); 优化目标是减少key-level浪费, 而非减少实际错误
- **更快请求**: ✅ p50=17970ms (deepseek), p90=38103ms; 最大值来自NVCF服务端延迟, 非客户端超时; 增加MIN_OUTBOUND_INTERVAL不会显著影响中位延迟
- **超低延迟稳定性**: ✅ 6h趋势显示完全稳定; 预算破裂 (1.5s < 10s) 起因于服务端超时, 非配置不足; 100%成功率证明无需干预
- **铁律**: ✅ 仅改HM2 (MIN_OUTBOUND_INTERVAL_S), 未改HM1本地; 未触碰mihomo (pgrep确认运行中); 单参数 +0.5s, 少改多轮

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记