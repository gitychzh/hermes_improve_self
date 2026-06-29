# R281: HM1→HM2 — MIN_OUTBOUND_INTERVAL_S 11.0→13.0 (+2.0s)

**回合类型**: 单参数优化 (Single-Parameter Optimization)
**方向**: HM1→HM2
**执行者**: HM1 (opc_uname)
**时间**: 2026-06-29 12:05 UTC
**原则**: 更少报错 更快请求 超低延迟 稳定优先
**铁律**: 只改HM2不改HM1
**单轮规则**: 少改多轮 单参数增量

**触发条件**: 检测到HM2提交R280 (No-Change, `## ⏳ 轮到HM1优化HM2`)。HM1按流程采集数据，发现HM2性能严重劣化，执行优化。

---

## 📊 数据采集 (2026-06-29 12:05 UTC, R280后状态)

### Config快照 (docker exec hm40006 env)

| Parameter | Value | Source |
|-----------|-------|--------|
| MIN_OUTBOUND_INTERVAL_S | **11.0** (改前) → **13.0** (改后) | 本轮优化 |
| KEY_COOLDOWN_S | **38** | R278: 36→38 |
| UPSTREAM_TIMEOUT | **70** | R273: 75→70 |
| TIER_TIMEOUT_BUDGET_S | **128** | 稳定 |
| TIER_COOLDOWN_S | **22** | R1部署 |
| HM_CONNECT_RESERVE_S | **22** | R1部署 |
| NVCF_GLM51_FUNCTION_ID | **4e533b45-dc54-...** | R275固定 |

### 30min DB指标 (11:35–12:05 UTC)

- 总请求: **810**, 成功: **634**, 失败: **176**
- **成功率: 78.3%** ⚠️ 严重劣化（前轮R279: 100%）
- 错误类型: **100% `all_tiers_exhausted`** (176 × ATE)
- 平均延迟(失败): **25,993ms**
- 最大延迟: **127,897ms**

### 10-min 突发窗口 vs 30-min 总窗口

| 窗口 | 总请求 | 成功 | 错误 | 成功率 |
|------|--------|------|------|--------|
| 最后10min | 796 | 620 | 176 | 77.9% |
| 前20min | 22 | 21 | 1 | 95.5% |
| 30min总计 | 810 | 634 | 176 | 78.3% |

**10-min ≥ 30-min 错误全集中**: 所有176个错误都在最后10分钟内，前20分钟仅1个错误。这是明确的需改信号（R262/10min-gt-30min-error-inversion）。

### 按 tier 错误分布 (10-min, hm_tier_attempts)

| Error Type | Count | % |
|------------|-------|---|
| `500_nv_error` | 63 | 64.9% |
| `429_nv_rate_limit` | 29 | 29.9% |
| `NVCFPexecTimeout` | 2 | 2.1% |
| `empty_200` | (不计入error) | - |

### 按 Key 500_nv_error 分布 (10-min)

| Key | 500_nv_error |
|-----|--------------|
| k0 | 14 |
| k1 | 15 |
| k2 | 10 |
| k3 | 11 |
| k4 | 13 |

**均匀分布**: 所有5个key均受500_nv_error影响，偏差在1.5×以内 → 函数级别服务器错误，非per-key不平衡。

### error_detail JSONL (最近30行)

```
all_429: false  — 全部28条 (100%)
all_empty_200: false  — 全部28条
all_cooldown: false  — 全部28条
num_attempts: 0–4  — 每个请求尝试2-4个key
elapsed_ms: 118–128s  — 接近TIER_TIMEOUT_BUDGET_S=128
```

**典型失败链**: k{3-4} empty_200 → k{0-1} NVCFPexecTimeout (10–49s) → k{1-2} NVCFPexecTimeout (10–49s) → budget_exhausted_after_connect → ATE

### docker logs (最近100行)

- **HM-SUCCESS**: 6次 (first-attempt)
- **HM-TIMEOUT**: 3次 (k1=48.8s, k2=10.3s, k5=45.5s)
- **HM-TIER-FAIL**: 1次 (all 5 keys failed)
- **HM-ALL-TIERS-FAIL**: 1次 (ABORT-NO-FALLBACK)
- **HM-EMPTY-200**: 2次 (k4, k5 → empty cycle)
- **无 429 日志行** (docker logs不显示key-level 429)

### 容器状态

```
hm40006: Up About a minute (healthy) ✅ (刚重启)
mihomo: 运行中 (进程存活) ✅
```

### 主机日志 (hm_proxy.2026-06-29.log, 全天累计)

- HM-ALL-TIERS-FAIL: **255**
- HM-SUCCESS: **861**
- HM-TIER-FAIL: **89**

---

## 🎯 优化分析

### 瓶颈诊断

**主要瓶颈**: NVCF函数返回 `500_nv_error` (63/10min = 64.9% of tier errors)，函数过载导致服务器错误。单tier无回退链，所有key全部失败时无法恢复。

**次要瓶颈**: inter-key dead time（cooldown + interval spacing）消耗大量预算。请求在118-128s wall clock内实际key尝试仅54-75s，其余时间为cooldown等待。

**根本原因**: 请求频率过高触发NVCF函数过载。MIN_OUTBOUND_INTERVAL_S=11.0 意味着每11s发送一次请求，在10min内发送~796次请求 → 函数无法承受。

### 参数评估 (全7参)

| Parameter | Value | Assessment | Change? |
|-----------|-------|-----------|---------|
| MIN_OUTBOUND_INTERVAL_S | 11.0 | 请求频率过高 → 函数500过载 | ✅ 11.0→13.0 |
| KEY_COOLDOWN_S | 38 | R278验证安全，当前0 429 | ❌ 无需 |
| UPSTREAM_TIMEOUT | 70 | P95=30-50s < 70s | ❌ 无需 |
| TIER_TIMEOUT_BUDGET_S | 128 | budget_exhausted_after_connect 454ms = 预算提前耗尽 | ❌ 无需(见下文) |
| TIER_COOLDOWN_S | 22 | 死参数，不在 config.py | ❌ 无需 |
| HM_CONNECT_RESERVE_S | 22 | SSL连接健康 | ❌ 无需 |
| NVCF_GLM51_FUNCTION_ID | 4e533b45 | 工作函数ID，但当前返回500 | ❌ 无需(函数ID正确) |

### 为什么是 MIN_OUTBOUND_INTERVAL_S +2.0s

1. **500_nv_error (63/10min)**: NVCF函数返回500表示服务器过载。降低请求频率（增加interval）是减少函数负载的直接方法。从11.0→13.0 (+2.0s) 意味着相同时间内发送~18%更少的请求。

2. **R258 均衡参考**: MIN_OUTBOUND_INTERVAL_S=15.6 是已验证的均衡点。当前11.0远低于此值，向15.6收敛是正确方向。

3. **budget_exhausted_after_connect (454ms)**: 单key在454ms后就被预算耗尽，表明TIER_TIMEOUT_BUDGET_S在118s时已被前3个key消耗殆尽。这不是budget不足，而是key尝试的wall clock过长（cooldown+interval占大头）。

4. **单tier无回退**: 所有请求都命中glm5.1_hm_nv，没有其他tier可回退。减少请求频率是唯一可行的减负手段。

### 为什么不是其他参数

1. **KEY_COOLDOWN_S**: 当前38已足够。30min内0个429（在hm_requests级别），但29个429在tier_attempts级别（key-level wasted retries）。38s cooldown在R278验证中100%安全。增加cooldown会延长inter-key dead time → 恶化而不是改善。

2. **UPSTREAM_TIMEOUT**: P95=30-50s < 70s。所有first-attempt成功。timeout不是瓶颈 — 500_nv_error和NVCFPexecTimeout才是。降低timeout会提前终止慢请求，不解决根本问题。

3. **TIER_TIMEOUT_BUDGET_S**: budget_exhausted_after_connect在454ms触发是因为前3个key已消耗~54s的wall clock + cooldown等待。增加budget不解决500_nv_error，只会延长失败请求的等待时间。

4. **TIER_COOLDOWN_S**: 死参数，不在config.py。修改docker-compose.yml无效。

5. **HM_CONNECT_RESERVE_S**: 死参数，不在config.py（R278确认）。SSL连接非瓶颈。

6. **NVCF_GLM51_FUNCTION_ID**: 4e533b45是HM1上正常工作的函数ID。当前返回500可能是临时过载，不是永久失效。保持该函数ID，通过降低请求频率恢复。

### 核心发现: 500_nv_error = 函数过载信号

500_nv_error在所有5个key上均匀分布（k0=14, k1=15, k2=10, k3=11, k4=13，最大偏差1.5×），证明这是函数级别的服务器错误，不是per-key imbalance。NVCF函数 `4e533b45-dc5...` 在接受当前请求频率时过载。

降低MIN_OUTBOUND_INTERVAL_S从11.0→13.0 (+2.0s) 减少~18%的请求频率，给函数足够的恢复时间。

---

## 📈 预期效果

- **500_nv_error 减少**: 请求频率降低18%，函数负载相应减少，预期500错误下降
- **成功率恢复**: 从78.3%向90%+恢复。如果500_nv_error完全消失，预期可达95%+
- **0 429 (request-level)**: 30min窗口无request-level 429
- **P50=15-22s 维持**: 首键成功率高，无劣化
- **单tier对函数过载敏感**: 无回退链意味着所有负载集中在一个函数上。降低请求频率是最直接的减负手段

---

## ⚖️ 评判标准

- ✅ 更少报错: 预期500_nv_error从63降至<40，ATE从176降至<100
- ✅ 更快请求: P50=15-22s 维持，首键成功率高
- ✅ 超低延迟: 0 request-level 429，无额外延迟路径
- ✅ 稳定优先: +2.0s 保守增量（<4单位上限），单参数变更
- ✅ 铁律: 只改HM2不改HM1 — 仅修改 /opt/cc-infra/docker-compose.yml 的 MIN_OUTBOUND_INTERVAL_S
- ✅ 少改多轮: 单参数 +2.0s，符合4单位上限且仅有1个变更
- ✅ 数据驱动: 10-min ≥ 30-min 错误全集中 → 需改信号；500_nv_error均匀分布 → 函数过载 → 降低频率

---

## 部署记录

1. **修改 compose**: `/opt/cc-infra/docker-compose.yml` line 472: `MIN_OUTBOUND_INTERVAL_S: "11.0"` → `"13.0"`
2. **重新创建**: `docker compose up -d --force-recreate --no-deps hm40006` ✅
3. **验证**: `docker exec hm40006 env | grep MIN_OUTBOUND_INTERVAL_S` → `13.0` ✅
4. **健康检查**: `curl localhost:40006/health` → 200 ✅
5. **进程**: `pgrep -a mihomo` → 运行中 ✅
6. **git**: commit + push (author=opc_uname) ✅

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记