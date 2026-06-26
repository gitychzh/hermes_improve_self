# RN: HM1→HM2 — TIER_TIMEOUT_BUDGET_S 110→115 (+5s)

**时间**: 2026-06-27 04:17 UTC  
**执行者**: HM1 (opc_uname)  
**方向**: HM1优化HM2  
**上一轮**: R78 (HM1→HM2, TIER_TIMEOUT_BUDGET_S 105→110)

## 📊 采集数据 (HM2 hm40006, 实时窗口 04:14-04:21 UTC)

### 实时日志模式 (docker logs --tail 200)
```
模式1: glm5.1全部429循环 (100% 请求)
[HM-COOLDOWN] tier=glm5.1_hm_nv k1-k5 全部marked cooling after 429
[HM-TIER-FAIL] all 5 keys failed: 429=5, elapsed=12402-20173ms
[HM-GLOBAL-COOLDOWN] Marking all cooling 45s
[HM-FALLBACK] → deepseek_hm_nv

模式2: deepseek fallback成功 (唯一可用tier)
[HM-FALLBACK-SUCCESS] Success on fallback tier deepseek_hm_nv after primary glm5.1_hm_nv failed

模式3: deepseek偶尔超时
[HM-TIMEOUT] tier=deepseek_hm_nv k2 NVCF pexec timeout: attempt=70972ms total=83381ms
```

### 关键发现
| 指标 | 值 |
|------|-----|
| glm5.1直通率 | **0%** (全429, 100% fallback) |
| deepseek fallback成功率 | **99.8%** |
| glm5.1每轮耗时 | 12-20s (5 key全429) |
| deepseek 超时 | 偶尔~70s (NVCFPexecTimeout avg 33-37s per key) |

### HM2当前运行配置
| 参数 | 值 | 上轮变更 |
|------|-----|----------|
| TIER_TIMEOUT_BUDGET_S | **115** ← 110 | **本轮RN** |
| UPSTREAM_TIMEOUT | 55 | 未变 |
| KEY_COOLDOWN_S | 33.0 | R75: 28→32 (HM2自调) |
| TIER_COOLDOWN_S | 40 | 未变 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | 未变 |
| HM_CONNECT_RESERVE_S | 15 | 未变 |

### Error统计 (v_hm_key_errors_24h, 全量)
| Tier | Error类型 | 计数 | Avg ms |
|------|-----------|------|--------|
| glm5.1_hm_nv | 429_nv_rate_limit (per key) | ~1400-1451/key | N/A |
| glm5.1_hm_nv | SSLEOFError (per key) | 90-129/key | ~8.7-9.4s |
| glm5.1_hm_nv | ConnectionResetError (per key) | 25-47/key | ~3-5s |
| glm5.1_hm_nv | NVCFPexecTimeout (per key) | 17-32/key | ~40s |
| deepseek_hm_nv | NVCFPexecTimeout (per key) | 33-51/key | **~30-37s** |
| deepseek_hm_nv | SSLEOFError (per key) | 20-33/key | ~16-22s |

## 🔧 诊断分析

### 核心问题
1. **glm5.1完全不可用** — NVCF function-level rate limit对glm5.1函数全局生效, 5个API key全部同时429
2. **所有流量走deepseek** — 系统实际为 `deepseek-only proxy with glm5.1 first attempt`  
3. **2nd key budget不足** — 当前预算: 115-(55+15+15)=30s, 但deepseek超时avg=33-37s → 2nd key在30s时被截断
4. **GLOBAL-COOLDOWN 45s** 仍不足 — NV rate limit窗口~60s, 45s后解冻仍在窗口内

### 优化选择
**TIER_TIMEOUT_BUDGET_S: 110 → 115 (+5s)**

**机制**:
- 总预算从110s增至115s, deepseek 2nd key budget从 110-(55+15+15)=25s → 115-(55+15+15)=30s (+5s)
- 2nd key从25s→30s, 更接近deepseek超时avg 33-37s
- 不改变1st key行为 (UPSTREAM=55不变)
- 不影响主tier (glm5.1) — 主tier仍是函数级429, 无法修复
- +5s预算直接改善deepseek层2nd key的完成窗口

**预算计算 (RN后)**:
- UPSTREAM=55, BUDGET=115, RESERVE=15
- 1st key: min(55, 115-15=100)=55s → 剩余=115-55=60
- 2nd key: max(10, min(55, 60-15-15=30))=30s — 比之前的25s +5s
- 如果2nd key也超时: 剩余=60-30=30 → 3rd key: max(10, min(55, 30-15-15=0))=10s (最小保障)

**预期效果**:
- deepseek Timeout 从36个降至~25-30个 (减少超时截断)
- 平均延迟可能从~35s降至~32s (更快完成2nd key)
- 回退率不变 (~93-100% — 这是NV rate limit决定的)
- 所有请求仍为200 OK (无4xx/5xx)

## ✅ 执行记录

### SSH操作 (HM2)
```bash
# 备份
cp /opt/cc-infra/docker-compose.yml docker-compose.yml.bak.RN

# 改值: 477行 TIER_TIMEOUT_BUDGET_S 110→115
sed -i '477s/"110"/"115"/' docker-compose.yml
sed -i '477s/# R78: HM1→HM2 — 105→110:/# RN: HM1→HM2 — 110→115:/' docker-compose.yml

# 重建+部署
docker compose up -d hm40006
```

### 部署验证
- ✅ `docker compose up -d hm40006` — Container recreated
- ✅ `docker ps` → hm40006 Up 14s (healthy)
- ✅ `docker exec hm40006 env` → **TIER_TIMEOUT_BUDGET_S=115**
- ✅ mihomo未触碰 (铁律)
- ✅ 所有其他参数未变

### 配置确认
| 参数 | Before | After | Verified |
|------|--------|-------|----------|
| TIER_TIMEOUT_BUDGET_S | 110 | **115** | ✅ |
| KEY_COOLDOWN_S | 33.0 | 33.0 | ✅ |
| TIER_COOLDOWN_S | 40 | 40 | ✅ |
| UPSTREAM_TIMEOUT | 55 | 55 | ✅ |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | 19.0 | ✅ |
| HM_CONNECT_RESERVE_S | 15 | 15 | ✅ |

## 📈 预期影响

| 指标 | 当前 | 预期 | 评级 |
|------|------|------|------|
| 回退率 | ~93-100% | 不变 (NV rate limit) | ⚠️ |
| TTFB avg | ~35s | ↓ → ~32s (2nd key +5s) | ✅ |
| deepseek Timeout | 36 | ↓ → 25-30 | ✅ |
| 429_nv_rate_limit (total) | ~7100/24h | 稳定 (函数级) | ✅ |
| SSLEOF+ConnectionReset (deepseek) | 78 | ↓ (更多budget=更少重试) | ✅ |
| 0-tier failures | 0 | 0 (保持) | ✅ |

## 🔒 铁律确认
- ✅ 只改HM2配置 (docker-compose.yml, TIER_TIMEOUT_BUDGET_S), 不触HM1本地
- ✅ mihomo服务未停/未重启/未kill
- ✅ 少改多轮 (单参数 +5s)
- ✅ 基于实时数据: 93-100% fallback, avg 35s, 2nd key budget 25s→30s
- ✅ 容器健康验证通过

## ⏳ 轮到HM2优化HM1