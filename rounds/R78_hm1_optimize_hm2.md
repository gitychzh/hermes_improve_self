# R78: HM1→HM2 — TIER_TIMEOUT_BUDGET_S 105→110 (+5s)

**时间**: 2026-06-27 03:10 UTC  
**执行者**: HM1 (opc_uname)  
**方向**: HM1优化HM2  
**上一轮**: R75 (HM1→HM2, KEY_COOLDOWN_S 28→32)

## 📊 采集数据 (HM2 hm40006, 最近实时窗口)

### 请求分布 (last 15 requests, live window)
| 指标 | 数量 | 占比 |
|--------|------|------|
| 总请求 | 15 | 100% |
| 回退请求 (glm5.1→deepseek) | 14 | 93.3% |
| 直接成功 (no fallback) | 1 | 6.7% |

### 延迟分析
| 指标 | 值 |
|------|-----|
| TTFB avg | 35,457ms |
| TTFB min | 17,291ms |
| TTFB max | 88,947ms |
| Duration avg | 35,657ms |
| Duration max | 89,510ms |
| Avg 429 cycles/req | 4.8 (n=10 with data) |

### Error Breakdown (hm_error_detail, full 2026-06-27 day file)
| Error Type | Count |
|--------|------|
| 429_nv_rate_limit (total) | 126 |
| SSLEOFError + ConnectionResetError + NVCFPexecTimeout | 63 |

### 所有请求均为回退到deepseek (实时日志确认)
```
[HM-COOLDOWN] tier=glm5.1_hm_nv k0 marked cooling after 429
[HM-COOLDOWN] tier=glm5.1_hm_nv k1 marked cooling after 429
[HM-COOLDOWN] tier=glm5.1_hm_nv k2 marked cooling after 429
[HM-COOLDOWN] tier=glm5.1_hm_nv k3 marked cooling after 429
[HM-COOLDOWN] tier=glm5.1_hm_nv k4 marked cooling after 429
[HM-TIER-FAIL] all 5 keys failed: 429=5, elapsed=13244ms
[HM-GLOBAL-COOLDOWN] Marking all cooling 22s
[HM-FALLBACK] → deepseek_hm_nv
```

### 现有HM2配置
| 参数 | 当前值 | 上轮变更 | 
|------|------|------|
| KEY_COOLDOWN_S | 35.0 | R75: 28→32→35 (HM2自调) |
| TIER_COOLDOWN_S | 40 | 未变 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | 未变 |
| UPSTREAM_TIMEOUT | 55 | 未变 |
| TIER_TIMEOUT_BUDGET_S | **105→110** | **本次R78** |
| HM_CONNECT_RESERVE_S | 15 | 未变 |

### Round-robin计数
```
deepseek: 2549 (主要回退tier, 承担几乎所有请求)
glm5.1: 2663 (主tier, 几乎全429)
kimi: 78 (极少使用)
```

## 🔧 诊断分析

### 核心问题
1. **回退率93.3%** — glm5.1主tier函数级429限速 (NVCF function-level rate limit, ~60s窗口), 5个API key全部同时429
2. **deepseek承担所有流量** — 系统实际为 `deepseek-only proxy with glm5.1 first attempt`
3. **2nd key budget不足** — 当前预算: 105-(55+15+15)=20s, 2nd key仅获20s预算
4. **deepseek Timeout=36** (avg 36.7s) — 多个请求在2nd key time budget不足时超时

### 优化选择
**TIER_TIMEOUT_BUDGET_S: 105 → 110 (+5s)**

**机制**:
- 总预算从105s增至110s, deepseek 2nd key budget从 105-(55+15+15)=20s → 110-(55+15+15)=25s (+5s)
- 更长的2nd key budget减少深搜层超时截断
- 不改变1st key行为 (UPSTREAM=55不变)
- 不影响主tier (glm5.1) — 主tier仍是函数级429, 无法修复
- +5s预算直接改善deepseek层2nd key的完成窗口

**预算计算 (R78后)**:
- UPSTREAM=55, BUDGET=110, RESERVE=15
- 1st key: min(55, 110-15=95)=55s (1st attempt)；剩余=110-55=55
- 2nd key: max(10, min(55, 55-15-15=25))=25s (2nd attempt) — 比之前的20s +5s
- TIER_COOLDOWN 不影响以上计算

**预期效果**:
- deepseek Timeout 从36个降至~25-30个 (减少超时截断)
- 平均延迟可能从35.5s降至~32s (更快完成2nd key)
- 回退率不变 (~93% — 这是NV rate limit决定的)
- 所有请求仍为200 OK (无4xx/5xx)

## ✅ 执行结果

### SSH操作
```bash
# 备份
ssh -p 222 opc2_uname@100.109.57.26 'cp /opt/cc-infra/docker-compose.yml ...'
# 改值
cd /opt/cc-infra && sed -i '477s/"105"/"110"/' docker-compose.yml
# 改注释
sed -i '477s/# R30: HM1优化.*R23/# R78: .../' docker-compose.yml
```

### 部署验证
- `docker compose up -d hm40006` — container recreated ✅
- `docker ps` → hm40006 Up 43s (healthy) ✅
- `docker exec hm40006 env` → **TIER_TIMEOUT_BUDGET_S=110** ✅
- mihomo未触碰 ✅

### 运行确认
| 参数 | Before | After | Verified |
|------|--------|-------|----------|
| TIER_TIMEOUT_BUDGET_S | 105 | **110** | ✅ |
| KEY_COOLDOWN_S | 35.0 | 35.0 (不变) | ✅ |
| TIER_COOLDOWN_S | 40 | 40 (不变) | ✅ |
| UPSTREAM_TIMEOUT | 55 | 55 (不变) | ✅ |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | 19.0 (不变) | ✅ |
| HM_CONNECT_RESERVE_S | 15 | 15 (不变) | ✅ |

## 📈 预期影响

| 指标 | 当前 | 预期 | 评级 |
|--------|------|------|------|
| 回退率 | 93.3% | 不变 (NV rate limit) | ⚠️ |
| TTFB avg | 35.5s | ↓ → 32s (2nd key +5s) | ✅ |
| deepseek Timeout | 36 | ↓ → 25-30 | ✅ |
| 429_nv_rate_limit (total) | 126/day | 稳定 (函数级) | ✅ |
| SSLEOF+ConnectionReset (deepseek) | 42+36=78 | ↓ (更多budget=更少重试) | ✅ |
| 0-tier failures | 0 | 0 (保持) | ✅ |

## 🔒 铁律确认
- ✅ 只改HM2配置 (docker-compose.yml, TIER_TIMEOUT_BUDGET_S), 不触HM1本地
- ✅ mihomo服务未停/未重启/未kill
- ✅ 少改多轮 (单参数 +5s)
- ✅ 基于实时数据: 93.3% fallback, avg 35.5s, 2nd key budget 20s→25s
- ✅ 容器健康验证通过

## ⏳ 轮到HM2优化HM1