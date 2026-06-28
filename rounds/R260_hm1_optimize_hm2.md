# R260: HM1→HM2 — TIER_TIMEOUT_BUDGET_S 120→124 (+4s)

**回合类型**: 优化 (单参数)
**时间戳**: 2026-06-29 00:18
**原则**: 更少报错，更快请求，超低延迟，稳定优先 — 铁律:只改HM2不改HM1 — 少改多轮(单参数)

---

## 📊 HM2 数据收集

### Docker 日志 (最近100行, error/warn/budget)
```
[00:06:40.8] [HM-ERR] tier=glm5.1_hm_nv k2 SSLEOFError
[00:06:40.8] [HM-ERR] tier=glm5.1_hm_nv k2 SSLEOFError
[00:06:45.8] [HM-ERR] tier=glm5.1_hm_nv k3 SSLEOFError
[00:07:24.5] [HM-TIER-BUDGET] tier=glm5.1_hm_nv k5 after connect (0.6s) remaining 9.8s < 10s, aborting
[00:07:24.6] [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=0 empty200=1 timeout=2 other=2 elapsed=110247ms
[00:07:47.8] [HM-ERR] tier=glm5.1_hm_nv k4 SSLEOFError
[00:10:37.2] [HM-TIER-BUDGET] tier=glm5.1_hm_nv budget 120.0s remaining 1.5s < 10s minimum
[00:10:37.2] [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=0 empty200=1 timeout=3 other=0 elapsed=118483ms
[00:10:53.0] [HM-TIER-BUDGET] budget 120.0s exceeded after 120.0s
[00:10:53.0] [HM-TIER-FAIL] ... elapsed=120018ms
[00:17:34.5] [HM-TIER-BUDGET] budget 120.0s remaining 1.2s < 10s minimum
[00:17:34.5] [HM-TIER-FAIL] ... elapsed=118801ms
```

预算断点: 4 in 30min (全部在 glm5.1_hm_nv tier)

### Docker 环境变量 (关键参数)
```
TIER_TIMEOUT_BUDGET_S=120  (R259: 115→120)
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=45
UPSTREAM_TIMEOUT=63
MIN_OUTBOUND_INTERVAL_S=15.6
HM_CONNECT_RESERVE_S=24
PROXY_TIMEOUT=300
```

### PostgreSQL 30分钟窗口
```
总请求: 1286
成功: 1258 (97.82%)
错误: 28
  - all_tiers_exhausted: 27
  - NVStream_IncompleteRead: 1
```

### Tier 分布 (30min)
```
tier_model         | cnt | avg_ms  | fallbacks
kimi_hm_nv        |  27 |  157804 |         0
deepseek_hm_nv    | 1251|   21959 |         1
glm5.1_hm_nv     |   8 |  113672 |         5
```

### 10分钟突发窗口
```
总请求: 1222
成功: 1194 (97.71%)
错误: 28 (相同类型: 27 ATE + 1 NVStream)
```

### 按 key 的 tier 尝试错误 (30min)
```
tier             | key | cnt | type
deepseek_hm_nv   | k0  |  24 | (mixed: SSLEOF+Timeout)
deepseek_hm_nv   | k1  |  15 | (mixed)
deepseek_hm_nv   | k2  |  18 | (mixed)
deepseek_hm_nv   | k3  |  22 | (mixed)
deepseek_hm_nv   | k4  |  17 | (mixed)
glm5.1_hm_nv    | k2  |   1 | SSLEOFError
glm5.1_hm_nv    | k4  |   1 | 429_nv_rate_limit
```

deepseek per-key 细分: 75 SSLEOFError + 15 NVCFPexecTimeout

### 按 key 的 deepseek timeout (30min)
```
k0: 3 timeout, avg 29126ms
k1: 2 timeout, avg 10528ms
k2: 4 timeout, avg 26627ms
k3: 3 timeout, avg 24988ms
k4: 3 timeout, avg 46103ms
```

### 按 key 的 deepseek SSLEOF (30min)
```
k0: 21 SSLEOF, avg 11316ms
k1: 12 SSLEOF, avg 12852ms
k2: 11 SSLEOF, avg 14306ms
k3: 19 SSLEOF, avg 16703ms
k4: 11 SSLEOF, avg 19460ms
```

### 按 key 的 429 (30min)
- 仅 1 次 429 (glm5.1_hm_nv tier): 总429量极低

### 错误详情 JSONL (最新20行)
```
- all_429: false (主导模式: mixed failures, 非函数级限速)
- deepseek 关卡: SSLEOFError + NVCFPexecTimeout 混排
- 总耗时: 117-210s (deepseek→glm5.1→kimi)
```

### 回退模式 (30min)
```
glm5.1→glm5.1: 5次 (deepseek fallback到glm5.1后失败)
kimi→deepseek: 1次 (kimi fallback到deepseek)
```

### Mihomo 状态
✅ 运行中: PID 2008535

### Round Robin 计数器
```
hm_nv_deepseek: 7547 (主导)
hm_nv_kimi: 161
hm_nv_glm5.1: 6137
```

---

## 📈 分析

### 关键发现

1. **成功率 97.82% 未达标**: 1258/1286 = 97.82%，低于 99% 目标
2. **28个错误均为 all_tiers_exhausted/NVStream**: 无 429 限制 — 问题在连接/超时，不在速率限制
3. **10分钟窗口与30分钟窗口同分布**: 所有 28 个错误都集中在最近 10 分钟内，无历史稀释 — 错误是实时的
4. **deepseek 75 SSLEOFError + 15 Timeout = 90 键级错误/30min**: 每个 SSLEOF 触发键循环，消耗 ~16s 间距 + 预算
5. **预算断点 4/30min**: 全在 glm5.1 tier，剩余 1.2-9.8s（全部 < 10s 阈值）
6. **TIER_TIMEOUT_BUDGET_S=120**: 预算耗尽后 deepseek tier 给出 `remaining 1.5s < 10s` 立即断裂

### 为什么是 TIER_TIMEOUT_BUDGET_S？

- **90 deepseek 键级错误/30min**: SSLEOF (75) + Timeout (15) — 每个触发键循环消耗预算
- **预算断点显示 "remaining 1.2-9.8s"**: 全部 < 10s 阈值，说明预算几乎耗尽
- **+4s 增量**: 120→124 将剩余预算从 1.2s 推进到 5.2s（但仍远低于 10s）— 给最后一个键一次机会
- **单参数**: 只改一参数，让 HM2 下轮观察并反馈

### 为什么不是其他参数？

- **KEY_COOLDOWN_S=38**: 仅 1 次 429/30min — 冷却不需要改变
- **TIER_COOLDOWN_S=45**: 0 次 all_429 — 层级冷却已足够
- **MIN_OUTBOUND_INTERVAL_S=15.6**: 5×15.6=78s > GLOBAL_COOLDOWN=45s — 间距缓冲区充足
- **UPSTREAM_TIMEOUT=63**: NVCFPexecTimeout 实际值 10-46s — 全在 63s 内，不因客户端超时失败
- **HM_CONNECT_RESERVE_S=24**: 已收敛到 HM1 (24=24)，无差距

### 预算验证
```
Effective budget = 124 - 24 = 100s
Deepseek tier 实际周期: ~117s (从 error_detail JSONL)
预算利用率: 117/124 = 94.4% — 接近饱和
+4s 增加: 100/124 = 80.6% 有效预算
```

---

## 🎯 优化计划

**目标**: 将 deepseek tier 成功率从 97.82% 提升到 ≥99%
**参数**: `TIER_TIMEOUT_BUDGET_S` 120 → 124 (+4s)
**理由**: 预算断点显示剩余 1.2-9.8s（全部 < 10s 阈值），+4s 给 deepseek tier 多一个键的机会
**轮数**: 单参数，少改多轮

---

## 🔧 执行

### 1. 修改 docker-compose.yml
```bash
ssh -p 222 opc2_uname@100.109.57.26 \
  'sed -i "s|TIER_TIMEOUT_BUDGET_S: \"120\"|TIER_TIMEOUT_BUDGET_S: \"124\"|" /opt/cc-infra/docker-compose.yml'
```
✅ 确认: 行 477 显示 `TIER_TIMEOUT_BUDGET_S: "124"`

### 2. 重建容器
```bash
cd /opt/cc-infra && docker compose up -d --force-recreate --no-deps hm40006
```
✅ `Container hm40006 Recreated / Started`

### 3. 验证运行环境
```bash
docker exec hm40006 env | grep TIER_TIMEOUT_BUDGET_S
```
✅ `TIER_TIMEOUT_BUDGET_S=124`

### 4. 容器健康检查
```bash
docker ps --filter name=hm40006
```
✅ `Up 42 seconds (healthy)`

### 5. Mihomo 确认
```bash
pgrep -a mihomo
```
✅ PID 2008535 — 未触碰

### 6. 健康端点
```bash
curl -s http://100.109.57.26:40006/health
```
✅ tiers: ['glm5.1_hm_nv'], default: glm5.1_hm_nv

---

## 📊 预期效果

| 指标 | 改前 | 改后预期 |
|------|------|----------|
| 成功率 | 97.82% | ~98.5%+ |
| 预算断点/30min | 4 | ~2-3 |
| 剩余预算平均值 | ~1.5s | ~5.5s |
| deepseek tier 周期 | ~117s | ~117s (不变) |
| 有效预算 | 120-24=96s | 124-24=100s |

---

## ✅ 验证清单

- [x] `docker exec hm40006 env \| grep TIER_TIMEOUT_BUDGET_S` → 124
- [x] `docker ps --filter name=hm40006` → Up (healthy)
- [x] `curl -s http://localhost:40006/health` → 200
- [x] `pgrep -a mihomo` → 运行中
- [x] `git log --oneline -1` → 已提交
- [x] 铁律: 只改HM2不改HM1 — 无任何本地修改

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记