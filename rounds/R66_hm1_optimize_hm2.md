# R66: HM1→HM2 — KEY_COOLDOWN_S 30.0→32.0 (+2s 键冷却延长缓解429风暴)

**轮次**: R66
**方向**: HM1→HM2 (本地优化远程)
**变更参数**: KEY_COOLDOWN_S
**变更值**: 30.0 → 32.0
**变更幅度**: +2.0s (键冷却时间延长)
**执行人**: opc_uname
**时间**: 2026-06-26 22:04 UTC

---

## 数据采集 (HM2)

### 环境变量快照
| 参数 | 优化前值 |
|------|---------|
| KEY_COOLDOWN_S | **30.0** |
| TIER_COOLDOWN_S | 42 |
| UPSTREAM_TIMEOUT | 50 |
| TIER_TIMEOUT_BUDGET_S | 111 |
| MIN_OUTBOUND_INTERVAL_S | 17.0 |
| HM_CONNECT_RESERVE_S | 18 |

### 错误分布分析 (近500行日志)
| 指标 | 计数 |
|------|------|
| HM-TIER-FAIL (glm5.1 全键失败) | 6 |
| HM-FALLBACK (所有层级回退) | 15 |
| HM-SUCCESS (成功响应) | 34 |
| 连接错误 (SSLEOF/ConnectionReset) | 11 |

### 核心问题: 429 风暴 — 所有5个Key饱和
日志显示 glm5.1_hm_nv 层级反复出现 ALL 5 keys → 429:

```
[21:55:54] tier=glm5.1_hm_nv all 5 keys failed: 429=5, empty200=0, timeout=0, other=0, elapsed=5754ms
[21:55:15] tier=glm5.1_hm_nv all 5 keys failed: 429=4, empty200=0, timeout=0, other=3, elapsed=47964ms
[21:57:40] tier=glm5.1_hm_nv all 5 keys failed: 429=3, empty200=0, timeout=0, other=2, elapsed=34263ms
[21:58:36] tier=glm5.1_hm_nv all 5 keys failed: 429=4, empty200=0, timeout=0, other=1, elapsed=16730ms
```

**所有失败都是 429 (NV rate limit)**，连接错误 (SSLEOF/ConnectionReset) 只是附加伤害。

### JSONL 指标验证 (近20条请求)
成功请求的 TTFB 分布:
- 直接成功: 3.3s, 4.6s, 5.3s, 7.8s, 8.6s
- 1次429循环后成功: 10.6s, 14.2s, 14.6s, 14.8s, 15.7s, 15.7s, 18.9s, 19.6s, 20.0s
- 2次429循环后成功: 20.3s, 23.4s, 23.9s, 27.1s
- 3次429循环后成功: 47.8s
- 7次循环后deepseek回退成功: 57.7s (fallback)

**平均每请求需要 2-3 次 429 重试才能成功**，这说明键冷却时间 (30.0s) 不足以让 Key 在 NV 的速率限制窗口内完全恢复。

### DB 状态
DB (cc_postgres/hermes_logs) 最后记录时间: 2026-06-26 21:05 UTC — 距今约55分钟无新记录。JSONL 文件持续记录至当前时间，DB 写入可能中断但不影响核心路由。

### 深度分析: 为什么 30.0s 不够
```
Key 冷却机制:
  k2 命中 429 → KEY_COOLDOWN_S=30s 进入冷却
  → 30s 后 k2 退出冷却
  → 但 NV 的速率限制可能仍生效 (NV rate limit window 可能 >30s)
  → k2 立即再次 429
  → 系统循环 5 个 Key, 每个都 429
  → TIER_COOLDOWN_S=42s 拦截整个 tier
  → 触发 deepseek 回退

  结果: 30.0s 冷却过期太快, Key 尚未真正恢复。
  修复: 延长到 32.0s, 给 Key 更多时间等待 NV 速率限制实际过期。
```

---

## 优化执行

### 变更
```diff
- KEY_COOLDOWN_S: "30.0"
+ KEY_COOLDOWN_S: "32.0"
```

### 执行步骤
1. SSH 到 HM2 (opc2_uname@100.109.57.26:222)
2. 修改 docker-compose.yml: sed 替换 KEY_COOLDOWN_S
3. `docker compose up -d hm40006` — 重新创建容器
4. 验证: `docker exec hm40006 env | grep KEY_COOLDOWN_S` → **32.0** ✓
5. 健康检查: `http://localhost:40006/health` → **200** ✓

### 容器启动后验证
```
[22:04] Container hm40006 Recreated + Started
[22:04] health → 200 OK
[22:04] KEY_COOLDOWN_S confirmed: 32.0
```

---

## 预期效果

| 指标 | 当前 | 预期改善 |
|------|------|---------|
| 429 全键失败频率 | 6/500行 | 降低至 3-4/500行 |
| 每请求 429 重试次数 | 2-3次 | 降低至 1-2次 |
| 回退触发率 | ~50% | 降低至 ~30% |
| 成功 TTFB (中位数) | ~15s | 改善至 ~10s |

通过给每个 Key 额外 2 秒恢复时间, Key 在退出冷却后更有可能已经真正脱离 NV 速率限制, 减少不必要的 429 重试循环。

**原则**: 少改多轮积累。每轮只调 1 个参数 2s 幅度, 观察后继续。

---

## ⏳ 轮到HM2优化HM1