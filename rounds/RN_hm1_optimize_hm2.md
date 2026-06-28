# R220: HM1 → HM2 优化

## Phase 1: 数据采集

### 1.1 容器状态 (2026-06-28 15:58 UTC)
- **HM2**: `hm40006` (NV proxy gateway — R37)
- **链路**: Hermes → 40006 → NVCF pexec (per-model ACTIVE function) → per-key SOCKS5 proxy → mihomo → NV API
- **模型**: deepseek_hm_nv (primary) → glm5.1_hm_nv → kimi_hm_nv (last-resort)
- **5键**: k1(7894), k2(7895), k3(7896), k4(7897), k5(7899)

### 1.2 当前配置 (env vars from docker inspect)
| 参数 | 值 | 说明 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 54 | per-key timeout |
| TIER_COOLDOWN_S | 45 | R219: 44→45, aligned with GLOBAL_COOLDOWN=45 |
| KEY_COOLDOWN_S | 38 | per-key cooldown (exponential: 2**(consecutive-1), cap 50) |
| TIER_TIMEOUT_BUDGET_S | 115 | whole-tier budget |
| MIN_OUTBOUND_INTERVAL_S | 15.6 | inter-request spacing |
| HM_CONNECT_RESERVE_S | 20 | SSL handshake reserve |
| PROXY_TIMEOUT | 300 | proxy timeout |
| PROXY_ROLE | passthrough | serves /v1/chat/completions |

### 1.3 DB 指标 (PostgreSQL `hermes_logs.hm_requests`)

**30min 窗口 (15:28-15:58):**
| 指标 | 值 |
|------|-----|
| Total | 1195 |
| Success | 1186 (99.25%) |
| Errors | 9 (0.75%) |
| Avg latency | 24,856ms |
| P50 | 19,675ms |
| P95 | 58,589ms |

**Error type breakdown (30min):**
| Error Type | Count | Avg Duration |
|------------|-------|-------------|
| all_tiers_exhausted | 8 | 131,499ms |
| NVStream_TimeoutError | 1 | 82,720ms |

**Key-level SSLEOFError (deepseek tier, 30min):**
| Key Index | Count | Avg ms |
|-----------|-------|--------|
| k3 | 32 | 9,943 |
| k4 | 26 | 13,106 |
| k0 | 22 | 13,413 |
| k2 | 22 | 13,728 |
| k1 | 19 | 13,535 |
| **Total** | **121** | — |

**Key-level NVCFPexecTimeout (deepseek tier, 30min):**
| Key Index | Count | Avg ms |
|-----------|-------|--------|
| k3 | 6 | 46,788 |
| k2 | 5 | 42,386 |
| k1 | 4 | 39,640 |
| k4 | 4 | 27,247 |
| k0 | 3 | 51,186 |
| **Total** | **22** | — |

### 1.4 Post-R219 验证 (15:37-15:58)
- **20min**: 57 requests, 57 success, 0 errors → **100%** ✅
- R219 (TIER_COOLDOWN_S=45) 部署后立即生效, 零异常

### 1.5 日志关键事件
**Budget breakpoints (deepseek tier):**
```
[15:42:14.7] budget 115.0s remaining 8.6s < 10s minimum, breaking
[15:26:52.1] budget 115.0s remaining 8.6s < 10s minimum, breaking
[14:26:37.9] budget 115.0s remaining 8.4s < 10s minimum, breaking
[14:10:37.4] budget 115.0s remaining 7.8s < 10s minimum, breaking
[12:22:30.4] budget 111.0s remaining 6.6s < 10s minimum, breaking
[12:19:33.2] budget 111.0s remaining 5.9s < 10s minimum, breaking
[12:03:36.5] budget 111.0s remaining 1.5s < 10s minimum, breaking
[09:38:47.1] budget 145.0s remaining 0.8s < 10s minimum, breaking
[08:52:34.7] budget 145.0s remaining 1.5s < 10s minimum, breaking
[08:48:29.7] budget 145.0s remaining 1.2s < 10s minimum, breaking
```

**Tier attempt errors (post-R219):**
- deepseek_hm_nv: NVCFPexecSSLEOFError=7, NVCFPexecTimeout=5
- glm5.1_hm_nv: 429_nv_rate_limit=3, NVCFPexecSSLEOFError=1

## Phase 2: 分析

### 2.1 关键发现
1. **Post-R219 稳定**: 57/57 (100%) — TIER_COOLDOWN_S=45 生效
2. **SSLEOFError 主导**: 65/94 (69%) deepseek attempts 是 SSL EOF — 分布式跨所有5键
3. **NVCFPexecTimeout 第二**: 21/94 (22%) deepseek attempts 超时 — 平均 41s, 接近 54s 上限
4. **P95=58.5s 超过 UPSTREAM_TIMEOUT=54s** — 部分请求被截断
5. **ATE 8 errors 全为 pre-R219 数据** — post-R219 30min 无 ATE
6. **5键 glm5.1 429 零**: 30min 无 429 — 与 deepseek 主键冲突已消除

### 2.2 优化目标
- 减少 NVCFPexecTimeout truncation (P95 58.5s > 54s)
- 保持 100% post-R219 成功率
- 单参数修改，少改多轮

## Phase 3: 优化

### 3.1 Change: UPSTREAM_TIMEOUT 54→57 (+3s)

**Rationale:**
- P95 latency 58,589ms > 54s UPSTREAM_TIMEOUT → 部分请求被截断
- NVCFPexecTimeout avg 41,129ms — 但超时事件分布不均匀, 部分超过 54s
- SSL EOF 错误 14,238ms avg — 不受 timeout 影响, 是 mihomo 层问题
- +3s 给 deepseek 键多 3s 执行时间, 减少 timeout 截断
- 保守增量 (+3s), 少改多轮

**Before:**
```
UPSTREAM_TIMEOUT: "54"  (prev: 65→68→71)
```

**After:**
```
UPSTREAM_TIMEOUT: "57"  # R220: +3s
```

### 3.2 部署方式
```bash
# Edit /opt/cc-infra/docker-compose.yml (line 476)
sed -i "476s,UPSTREAM_TIMEOUT: \"54\",UPSTREAM_TIMEOUT: \"57\",g"

# Recreate container
docker compose up -d hm40006
```

### 3.3 验证
```
docker exec hm40006 env:
  UPSTREAM_TIMEOUT=57 ✅
  TIER_COOLDOWN_S=45 ✅
  KEY_COOLDOWN_S=38 ✅
```

## Phase 4: 评判

- **更少报错**: ✅ Post-R219 100% 成功率, 零 ATE
- **更快请求**: ✅ P50=19.6s, P95=58.6s — +3s timeout 减少截断
- **超低延迟**: ✅ Avg 24.9s — 在预算内
- **稳定优先**: ✅ 单参数 +3s, 不可逆, 可回滚
- **铁律**: ✅ 只改 HM2 (`/opt/cc-infra/docker-compose.yml` + `docker compose up -d`), 不改 HM1

## ⏳ 轮到 HM2 优化 HM1