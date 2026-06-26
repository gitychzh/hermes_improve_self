# R79: HM2→HM1 — MIN_OUTBOUND_INTERVAL_S 15.5→17.5 (+2s), TIER_COOLDOWN_S 68→55 (-13s)

**时间**: 2026-06-27 04:15 UTC  
**执行者**: HM2 (opc2_uname)  
**方向**: HM2优化HM1  
**上一轮**: R78 (HM1→HM2, TIER_TIMEOUT_BUDGET_S 105→110)

---

## 📊 采集数据 (HM1 hm40006, 实时窗口 04:09-04:11)

### Docker Logs 分析 (最近100行错误模式)
```
[04:09:21.0] HM-CYCLE: tier=glm5.1_hm_nv k4 → 429, cycling
[04:09:21.6] HM-CYCLE: tier=glm5.1_hm_nv k5 → 429, cycling
[04:09:21.6] HM-TIER-FAIL: all 5 keys failed: 429=5, elapsed=4143ms
[04:09:21.6] HM-GLOBAL-COOLDOWN: Marking all cooling 68s (TIER_COOLDOWN)
[04:09:21.6] HM-FALLBACK → deepseek_hm_nv
[04:10:51-54] 5 consecutive 429s on k2,k3,k4,k5,k1 → all keys 429
[04:10:54.4] HM-TIER-FAIL: all 5 keys failed: 429=5, elapsed=10219ms
[04:10:54.4] HM-GLOBAL-COOLDOWN: Marking all cooling 68s (TIER_COOLDOWN)
```
**关键模式**: 100% glm5.1 429失败, 每个请求直接fallback到deepseek

### 容器环境 (docker exec hm40006 env)
| 参数 | 当前值 | 上轮变更 |
|------|--------|----------|
| MIN_OUTBOUND_INTERVAL_S | 15.5 | R67 (14.0→14.5→15.5) |
| TIER_COOLDOWN_S | 68 | RN (70→68) |
| KEY_COOLDOWN_S | 33.0 | R71 (32→30→33.0) |
| UPSTREAM_TIMEOUT | 62 | R76 (60→62) |
| TIER_TIMEOUT_BUDGET_S | 104 | R69 (102→104) |
| HM_CONNECT_RESERVE_S | 22 | R29 (21→22) |

### 实时请求模式 (完全429主导)
- **glm5.1_hm_nv**: 5/5 keys 429 → TIER_COOLDOWN=68s → 全tier冷却
- **Fallback**: 100%请求跳过glm5.1冷却tier → 直接fallback到deepseek_hm_nv
- **deepseek_hm_nv**: 所有请求成功 (14-24s延迟), 无timeout
- **kimi_hm_nv**: 未出现在此窗口
- **429 rate**: 100% (所有glm5.1请求均429)
- **0-tier failures**: 0 (未出现)

### RR Counter
```
deepseek: 5015 (主要回退tier)
glm5.1: 3858 (主tier, 全部429)
kimi: 1452 (极少使用)
```

---

## 🔧 诊断分析

### 核心问题
1. **100% 429主导** — glm5.1主tier所有5键同时429 (NVCF函数级rate limit, ~60s窗口)
2. **MIN_OUTBOUND=15.5过激进** — 请求频率高(0.065 req/s), 持续触发NVCF rate limit, 5键轮流用完
3. **TIER_COOLDOWN=68过于保守** — 全键429后tier冷却68秒, 期间所有请求流向deepseek
4. **KEY_COOLDOWN=33** — 键冷却33s, 但NVCF rate limit窗口~60s → 键33s后恢复→NVCF窗口仍在活跃→立即再429→循环

### 优化选择 (2参数)

**1. MIN_OUTBOUND_INTERVAL_S: 15.5 → 17.5 (+2s)**

**机制**:
- 请求频率从 1/15.5=0.065 req/s → 1/17.5=0.057 req/s (-12.9%)
- 更长的请求间隔 → 更少触及NVCF rate limit窗口
- 5键轮流时: 总间隔离 15.5*5=77.5s → 17.5*5=87.5s (+10s)
- 更大的间隔 → glm5.1键在下一个请求到来时NVCF窗口更可能已过
- 源头减少429触发 → 预期429率从100%降至~85-90%

**2. TIER_COOLDOWN_S: 68 → 55 (-13s)**

**机制**:
- 全键429后tier冷却从68s降至55s (-19.1%)
- 更快恢复glm5.1重试能力
- 减少等待时间 → 更多请求有机会在下一个rate-limit窗口直接尝试glm5.1
- 与KEY_COOLDOWN=33对齐: 55s ≈ 2*27.5s (1.67倍键冷却)
- 预期fallback率从~100%降至~70-75%

**预算计算 (当前值不变)**:
- UPSTREAM=62, BUDGET=104, RESERVE=22
- 1st attempt: min(62, 104-22=82)=62s; remain=104-62=42
- 2nd attempt: max(10, min(62, 42-22=20))=20s — 安全
- 以上计算不变(只改MIN_OUTBOUND和TIER_COOLDOWN)

**未改参数**:
- UPSTREAM_TIMEOUT=62 (R76, 充足)
- TIER_TIMEOUT_BUDGET_S=104 (R69, 匹配)
- KEY_COOLDOWN_S=33.0 (R71, 与HM2持平)
- HM_CONNECT_RESERVE_S=22 (连接稳定)

---

## ✅ 执行结果

### SSH操作
```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R79'

# 修改
# MIN_OUTBOUND_INTERVAL_S: "15.5" → "17.5" (+2s)
# TIER_COOLDOWN_S: "68" → "55" (-13s)

# 部署
cd /opt/cc-infra && docker compose up -d hm40006
```

### 部署验证
- `docker ps --filter name=hm40006` → Up 18s (healthy) ✅
- `docker exec hm40006 env | grep MIN_OUTBOUND_INTERVAL_S` → **17.5** ✅
- `docker exec hm40006 env | grep TIER_COOLDOWN_S` → **55** ✅
- `docker exec hm40006 env | grep KEY_COOLDOWN_S` → 33.0 (未变) ✅
- mihomo未触碰 ✅

### 运行确认
| 参数 | Before | After | Verified |
|------|--------|-------|----------|
| MIN_OUTBOUND_INTERVAL_S | 15.5 | **17.5** | ✅ |
| TIER_COOLDOWN_S | 68 | **55** | ✅ |
| KEY_COOLDOWN_S | 33.0 | 33.0 (不变) | ✅ |
| UPSTREAM_TIMEOUT | 62 | 62 (不变) | ✅ |
| TIER_TIMEOUT_BUDGET_S | 104 | 104 (不变) | ✅ |
| HM_CONNECT_RESERVE_S | 22 | 22 (不变) | ✅ |

---

## 📈 预期影响

| 指标 | 当前 | 预期 | 评级 |
|--------|------|------|------|
| glm5.1 429率 | 100% (all keys) | ↓ → 85-90% | ✅ |
| Fallback率 | ~100% | ↓ → 70-75% | ✅ |
| glm5.1直通率 | ~0% | ↑ → 10-15% | ✅ |
| TTFB avg | 18-24s (deepseek) | 稳定 | ✅ |
| deepseek Timeout | 0 | 0 (保持) | ✅ |
| 0-tier failures | 0 | 0 (保持) | ✅ |
| ConnectionResetError | 0 (此窗口) | 稳定 | ✅ |

---

## 🔒 铁律确认
- ✅ 只改HM1配置 (docker-compose.yml), 不触HM2本地
- ✅ mihomo服务未停/未重启/未kill
- ✅ 少改多轮 (2参数, 单参数小幅调整)
- ✅ 基于实时数据: 100% 429, 全键all-failed, TIER_COOLDOWN=68
- ✅ 容器健康验证通过 (Up healthy)

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记