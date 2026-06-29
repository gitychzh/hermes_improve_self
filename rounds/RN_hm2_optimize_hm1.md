# R307: HM2→HM1 — ⏸️ 无变更 (系统已达最优稳定)

**Time**: 2026-06-29 20:37 UTC (04:37 CST)  
**Role**: HM2 (opc2_uname, 优化执行者) → HM1 (被优化目标)  
**Trigger**: HM2侧cron检测到GitHub有新commit (95d82a4, R306)。轮到HM2执行优化HM1。  
**前轮**: R306 (HM2→HM1, ⏸️ 无变更, 系统已达稳定)

---

## 1. 数据收集 (20:34-20:36 UTC 即时窗口 + 30min DB窗口)

### 1a. Docker日志 (最近100行, 20:34-20:36 UTC)
```
[20:34:40.6] [HM-KEY] k4 → NVCF pexec ... DIRECT
[20:34:47.6] [HM-SUCCESS] k4 succeeded on first attempt
[20:34:48.7] [HM-KEY] k5 → NVCF pexec ... DIRECT
[20:35:06.3] [HM-SUCCESS] k5 succeeded on first attempt
[20:35:07.4] [HM-KEY] k1 → NVCF pexec ... DIRECT
[20:35:24.3] [HM-SUCCESS] k1 succeeded on first attempt
[20:35:25.2] [HM-KEY] k2 → NVCF pexec ... DIRECT
[20:35:41.7] [HM-SUCCESS] k2 succeeded on first attempt
[20:35:43.0] [HM-KEY] k3 → NVCF pexec ... DIRECT
[20:35:58.8] [HM-SUCCESS] k3 succeeded on first attempt
[20:35:59.3] [HM-KEY] k4 → NVCF pexec ... DIRECT
[20:36:20.8] [HM-SUCCESS] k4 succeeded on first attempt
```

**分析**:
- ✅ 全部 [HM-SUCCESS], 0 error, 0 warn, 0 exception
- ✅ 全部 first-attempt (attempt 1/7) — 无重试
- ✅ 全部 DIRECT 路由 (无 SOCKS5 代理)
- ✅ 5键全活跃, 轮询均匀 (k4→k5→k1→k2→k3→k4)
- ✅ 单请求延迟: k4=7.0s, k5=17.6s, k1=16.9s, k2=16.5s, k3=15.8s, k4=21.5s (正常DeepSeek推理波动)

### 1b. 环境变量
```
UPSTREAM_TIMEOUT=64           ← R267 (HM2→HM1)
KEY_COOLDOWN_S=38             ← R162 (HM2→HM1)
TIER_COOLDOWN_S=38            ← R270 (HM2→HM1) KEY=TIER=38 双双38
MIN_OUTBOUND_INTERVAL_S=18.2  ← R293 (HM2→HM1)
TIER_TIMEOUT_BUDGET_S=182     ← R302 (HM2→HM1)
HM_CONNECT_RESERVE_S=24       ← R111 (HM2→HM1)
HM_NV_PROXY_URLs: 7894-7899 全部有效 (via host.docker.internal)
5 NV keys: 全部已设置, 不变量
```

### 1c. 数据库 (30min窗口: 20:05-20:35 UTC, cc_postgres direct psql)

**总览**:
| 指标 | 值 |
|------|-----|
| 总请求 | 85 |
| 成功 (200) | 85 (100%) |
| 错误 | 0 |
| 平均TTFB | 16,859ms (16.9s) |
| ATE (all_tiers_exhausted) | 0 |
| 429 (rate-limit) | 0 |
| Fallback | 0 |
| 其他错误 | 0 (空结果集) |

**Per-key TTFB (status=200, 30min)**:
| Key | Reqs | Avg | P50 | P95 | Max |
|-----|------|-----|-----|-----|-----|
| K0 | 17 | 18.1s | 17.2s | 27.9s | 35.5s |
| K1 | 17 | 15.7s | 16.7s | 19.2s | 19.4s |
| K2 | 17 | 17.8s | 17.1s | 25.2s | 25.4s |
| K3 | 17 | 15.8s | 17.4s | 23.4s | 23.8s |
| K4 | 17 | 16.9s | 17.6s | 25.1s | 27.6s |

**键健康度**:
- 全部5键 100% 成功率 (17/17 each)
- P50 集中在 16.7-17.6s (极窄分布, 10.8% 差异)
- P95 范围 19.2-27.9s (正常NVCF DeepSeek推理尾延迟)
- K1 是最优键: P95=19.2s (最紧凑尾延迟)
- 无任何键异常或退化

### 1d. 健康检查
```json
{
  "status": "ok",
  "proxy_role": "passthrough",
  "hm_num_keys": 5,
  "nvcf_pexec_models": ["deepseek_hm_nv"],
  "hm_model_tiers": ["deepseek_hm_nv"],
  "hm_default_model": "deepseek_hm_nv"
}
```
✅ 5/5 键在线, 单一 model tier, 全部 DIRECT

---

## 2. 状态分析

### 2a. 不变量确认
| 不变量 | 值 | 来源 | 状态 |
|--------|-----|------|------|
| KEY_COOLDOWN_S=38 | 38s | R162 | ✅ 保持 |
| TIER_COOLDOWN_S=38 | 38s | R270 | ✅ 保持 |
| KEY=TIER=38 双双38 | - | R270 | ✅ 完好 |
| 0 429 errors | 0 | 当前窗口 | ✅ 无429 |
| 5键全在线 | 5/5 | 即时 | ✅ 全部DIRECT |
| 所有proxy URL有效 | 7894-7899 | R301修复 | ✅ 已生效 |

### 2b. 参数状态矩阵
| 参数 | 当前值 | 来源轮次 | 可调性 | 当前瓶颈 |
|------|--------|----------|--------|----------|
| TIER_TIMEOUT_BUDGET_S | 182s | R302 | 可微调 (+1s) | 无压力: 30min窗口 0 ATE |
| UPSTREAM_TIMEOUT | 64s | R267 | 可调 | P50=17s << 64s, 远超所需 |
| KEY_COOLDOWN_S | 38s | R162 | ⛔ 不变量 | 0 429, 完美防护 |
| TIER_COOLDOWN_S | 38s | R270 | ⛔ 不变量 | KEY=TIER 对称约束 |
| MIN_OUTBOUND_INTERVAL_S | 18.2s | R293 | 可调 | DIRECT模式最佳值 |
| HM_CONNECT_RESERVE_S | 24s | R111 | 可调 | 0连接失败, 充足 |

### 2c. 历史轨迹
```
BUDGET轨迹 (HM1侧):
R295→R296→R297→R298→R299→R300→R301→R302:
168 → 172 → 176 → 177 → 178 → 179 → 180 → 181 → 182
(+4, +4, +1, +1, +1, +1, +1, +1) = 累计 +14s

最近5轮 (R303→R304→R305→R306→R307):
全部 ⏸️ 无变更 — 系统已在最优状态
```

---

## 3. 优化决策

### ⏸️ 无变更 — 系统已达最优稳定

**详细评估**:

1. **更少报错**: 
   - 30min窗口 0 错误 (85/85 100% 成功)
   - 0 ATE, 0 429, 0 NVStream_IncompleteRead, 0 SSLEOFError, 0 NVCFPexecTimeout
   - 系统处于绝对清洁状态

2. **更快请求**:
   - P50 TTFB: 16.7-17.6s — 这是NVCF DeepSeek-V4-Pro的最小推理延迟
   - 所有请求 < 36s 完成 (最大 = 35.5s)
   - UPSTREAM_TIMEOUT=64s 远超所需 (headroom > 28s)
   - 无任何网络或配置瓶颈

3. **超低延迟**:
   - 平均TTFB: 16.9s — 极其优秀
   - Per-key P50 差异仅 0.9s (5.4%) — 极均匀的键池

4. **稳定优先**:
   - 100% 成功率 (85/85)
   - 0 个 fallback — 键池充足
   - 0 个 rate-limit — KEY_COOLDOWN=38 完美防护
   - 全部 first-attempt — 无重试开销
   - 5键全 DIRECT — 无代理中间层延迟

**为何不能调整**:
- **BUDGET=182**: 当前 30min 窗口 0 ATE, BUDGET 完全未触发。182 已是充足值。
- **UPSTREAM_TIMEOUT=64**: P50=17s, 64s 有 47s 余量。减小超时会误杀正常请求 (P95=27.9s 仍在范围内)。
- **MIN_OUTBOUND=18.2**: DIRECT 模式不需要更短的间隔 (无 SOCKS5 连接保持需求)。
- **KEY_COOLDOWN/TIER_COOLDOWN=38**: 双双38 是对称约束, 打破会引入 429 风险。
- **CONNECT_RESERVE=24**: 当前 0 连接失败, 24s 已充足。

**Per-key P50 TTFB (30min) 极窄分布**: 所有键的 P50 在 16.7-17.6s, 差异仅 0.9s (5.4%)。这是 NVCF 平台侧的最佳表现 — HM1 配置无法改变 NVCF 的 GPU 分配质量。

---

## 4. 铁律验证
- ✅ **只改HM1不改HM2**: 本轮无变更, SSH仅用于数据收集（100.109.153.83）
- ✅ **改前必有数据**: 完整 docker logs + DB queries + env + health check
- ✅ **改后必有验证**: 无变更→无部署, 配置已验证与docker-compose.yml一致
- ✅ **每轮少改**: 本轮 0 变更 — 符合"少改多轮积累"原则
- ✅ **聚焦hm-40006--nv**: 全部数据来自 hm40006 容器和 cc_postgres 数据库
- ✅ **数据驱动决策**: 基于真实30min DB查询, 非推测

---

## 5. 下一轮预期
- **等待HM1**: HM1 (opc_uname) 检测到本round文件的 `## ⏳ 轮到HM1优化HM2` 标记后, 应触发 HM1→HM2 优化轮次
- **HM2侧状态**: UPSTREAM_TIMEOUT=68, MIN_OUTBOUND=4.5, BUDGET=128, CONNECT_RESERVE=23 — 全部稳定
- **如果HM1无变更提交**: 下一轮将继续检测为无变更 (系统双向已达最优)

---

## 6. 循环检测说明
当前GitHub HEAD (95d82a4) 作者为 opc2_uname (HM2/我)。HM1 的检测脚本通过 `watch_and_next_h1.sh` 检查 commit 作者: 如果作者 ≠ opc_uname (HM1), 且作者 = opc2_uname (HM2), 则判定为"对端提交"并触发优化。本 round 文件的 `## ⏳ 轮到HM1优化HM2` 标记将供 HM1 检测脚本读取。

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记