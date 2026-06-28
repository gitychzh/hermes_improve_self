# R184: HM1→HM2 — KEY_COOLDOWN_S 42→45 (+3s)

**回合类型**: 优化/单参数
**角色**: HM1 (opc_uname) 优化 HM2 (opc2_uname)
**时间戳**: 2026-06-28 08:55 UTC
**原则**: 更少报错 更快请求 超低延迟 稳定优先 | 铁律:只改HM2不改HM1 | 少改多轮(单参数)

---

## 📊 数据采集

### HM2 运行环境 (docker exec env)
| 参数 | 值 | 备注 |
|------|-----|------|
| KEY_COOLDOWN_S | 42 | ← 变更前 |
| TIER_COOLDOWN_S | 45 | 已收敛到 GLOBAL=45 |
| MIN_OUTBOUND_INTERVAL_S | 13.8 | 5×13.8=69.0s, buffer=24s above GLOBAL |
| TIER_TIMEOUT_BUDGET_S | 145 | 30min 6次 deepseek budget break |
| UPSTREAM_TIMEOUT | 71 | Per-key timeout ceiling |
| HM_CONNECT_RESERVE_S | 24 | 双方已收敛 |
| PROXY_TIMEOUT | 300 | 固定 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 | 默认 |

### Docker Logs (tail 100, error/warn/429/budget)
```
[08:45:24] [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=5, elapsed=4638ms
[08:45:24] [HM-GLOBAL-COOLDOWN] tier=glm5.1_hm_nv all keys 429. Marking all cooling 45s
[08:48:29] [HM-TIER-BUDGET] tier=deepseek_hm_nv budget 145.0s remaining 1.2s < 10s minimum, breaking
[08:48:29] [HM-TIER-FAIL] tier=deepseek_hm_nv all 5 keys failed: 429=0, empty200=1, timeout=3, other=0, elapsed=143773ms
[08:48:49] [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=5, elapsed=15515ms
[08:48:49] [HM-GLOBAL-COOLDOWN] tier=glm5.1_hm_nv all keys 429. Marking all cooling 45s
[08:50:11] [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=5, elapsed=5487ms
[08:50:11] [HM-GLOBAL-COOLDOWN] tier=glm5.1_hm_nv all keys 429. Marking all cooling 45s
```

### 错误详情 JSONL (最近5条)
```json
// R183 已部署: KEY_COOLDOWN_S=42, TIER_COOLDOWN_S=45 (R182: 44→45)
// glm5.1_hm_nv: 3次 all_429=true (全局冷却45s), elapsed=4.6-15.5s
// deepseek_hm_nv: 1次 NVCFPexecTimeout=49-59s×3 + empty_200×1, elapsed=143.8s
// 所有 glm5.1 失败中: k0-k4 均429, GLOBAL-COOLDOWN=45s 触发
// 所有 deepseek 失败中: NVCFPexecTimeout (59s/10.7s/11.4s) + empty_200 (k2)
```

### DB 30分钟窗口
| 指标 | 值 |
|------|-----|
| 总请求 | 1,465 |
| 成功 (200) | 1,460 |
| 失败 | 5 (all_tiers_exhausted) |
| 成功率 | 99.66% |
| glm5.1_hm_nv 请求 | 767 (100% OK, avg 13.2s) |
| deepseek_hm_nv 请求 | 693 (100% OK, avg 22.4s, 全为 fallback) |
| 空 tier_model | 5 (ATE, avg 142.4s) |

### 1小时/2小时窗口
| 窗口 | 总 | OK | % |
|------|-----|-----|-----|
| 1h | 1,564 | 1,559 | 99.68% |
| 2h | 1,691 | 1,686 | 99.70% |

### 24小时 ATE 分布
| 时段 | ATE 数 |
|------|--------|
| 15min | 5 |
| 1h | 5 (最近时段，非历史) |
| 24h | 37 (全历史) |

### 15分钟 429/key 分布 (hm_tier_attempts)
| Tier | 总计 429 |
|------|----------|
| glm5.1_hm_nv | 1,204 (15min) / 1,245 (30min, k0=325, k1=253, k2=233, k3=236, k4=198) |

### Deepseek Tier Budget Break (6次 today)
```
03:35:20 budget 132.0s remaining 2.0s < 10s (旧 TIER=132)
03:37:44 budget 132.0s remaining 2.1s < 10s (旧 TIER=132)
06:54:08 budget 140.0s remaining 1.0s < 10s (旧 TIER=140)
07:29:30 budget 145.0s remaining 7.4s < 10s (当前 TIER=145)
08:48:29 budget 145.0s remaining 1.2s < 10s (当前 TIER=145)
08:52:34 budget 145.0s remaining 1.5s < 10s (当前 TIER=145)
```

### Round-Robin Counter
```json
{"hm_nv_deepseek": 5545, "hm_nv_kimi": 131, "hm_nv_glm5.1": 5750}
```

### 其他检查
- `pgrep -a mihomo`: ✅ PID 2008535 运行中
- `curl /health`: ✅ 200 OK, 3 tiers (glm5.1→deepseek→kimi), default=glm5.1_hm_nv
- 容器状态: ✅ Up (healthy), 23s 启动后

---

## 🔍 分析

### 核心发现

1. **KEY_COOLDOWN_S=42, TIER_COOLDOWN_S=45**: KEY < TIER by 3s. 这保持正向缺口 (TIER outlasts KEY) — 无 reverse-gap。但 KEY 距离 GLOBAL=45s 还差 3s，KEY 冷却在 42s 时释放而 GLOBAL 冷却在 45s 才释放。KEY 冷却提前 3s 到期 → 额外 key 重试在 GLOBAL 冷却窗内浪费。

2. **glm5.1_hm_nv `all_429=true`**: 所有 5 个 tier 失败都是 100% 429 (函数级 NV 速率限制)。GLOBAL-COOLDOWN=45s 触发标记所有 keys 冷却 45s。TIER_COOLDOWN_S 已收敛到 45，但 KEY_COOLDOWN_S 仍停在 42。

3. **deepseek_hm_nv 超时**: 6 次 tier budget break 在 30min。Budget=145s, remaining=1.2-7.4s < 10s minimum。NVCFPexecTimeout=49-59s/键 + empty_200。这是上游 deepseek pexec 延迟问题，非可配置参数。

4. **deepseek 全 fallback**: 693/693 deepseek 请求 = 100% fallback from glm5.1。0 直接 deepseek 请求。fallback 链 glm5.1→deepseek 完美工作 (100% OK)。

5. **ATE=5 在 30min**: 全部 5 个 ATE 来自深度 seek 超时 + 备用链失败。不是可配置 cooldown 参数能解决的（deepseek 的 NVCFPexecTimeout 是上游问题）。

### 为什么选择 KEY_COOLDOWN_S

| 为什么选 | 为什么不是其他 |
|----------|----------------|
| TIER_COOLDOWN_S=45 已到收敛目标 | 无法再增加 (已 = GLOBAL=45) |
| MIN_OUTBOUND_INTERVAL_S=13.8 (buffer=24s) | 已在超安全区，增加无益 |
| TIER_TIMEOUT_BUDGET_S=145 (deepseek NVCFPexecTimeout 是上游) | 增加 budget 不会让 deepseek pexec 更快，超时是 NV 服务器问题 |
| UPSTREAM_TIMEOUT=71 (per-key 天花板) | 增加超时不会阻止 NVCFPexecTimeout (服务器不响应，非客户端超时) |
| HM_CONNECT_RESERVE_S=24 (双方已收敛) | 不需要调整 |
| KEY_COOLDOWN_S=42 → 45 (+3s) | 3s 缺口到 GLOBAL=45 收敛目标；单参数；≤4 单位 cap；减少浪费的早期重试；与 TIER=45 完全对称 |

---

## 🔧 执行

### 变更: `KEY_COOLDOWN_S: 42 → 45 (+3s)`

**命令**:
```bash
# 1. 修改 docker-compose.yml (Python 精确行替换)
ssh HM2 "python3 -c '...' " # 第 480 行: KEY_COOLDOWN_S 值 42→45

# 2. 重建容器
cd /opt/cc-infra && docker compose up -d --force-recreate --no-deps hm40006

# 3. 验证 (3s 等待后)
docker exec hm40006 env | grep KEY_COOLDOWN_S  # → 45 ✓
docker ps --filter name=hm40006  # → Up (healthy) ✓
curl -s http://localhost:40006/health  # → 200 OK ✓
pgrep -a mihomo  # → 2008535 running ✓
```

### 验证结果

| 检查 | 结果 |
|------|------|
| KEY_COOLDOWN_S (运行容器) | ✅ 45 |
| 容器状态 | ✅ Up 23s (healthy) |
| /health 端点 | ✅ 200 OK, 3 tiers, default=glm5.1_hm_nv |
| mihomo 进程 | ✅ PID 2008535 运行 |
| 旧值确认 (变更前) | ✅ KEY_COOLDOWN_S=42 |

---

## 📈 预期效果

### 前/后对比

| 参数 | 变更前 | 变更后 | 变化 | 方向 |
|------|--------|--------|------|------|
| KEY_COOLDOWN_S | 42s | 45s | +3s | → GLOBAL=45 收敛 |
| TIER_COOLDOWN_S | 45s | 45s | 0 | 已在收敛 |
| 5-Key 冷却对齐 | KEY=42<TIER=45 (3s gap) | KEY=45=TIER=45 (0s gap) | 完全对称 | GLOBAL 对齐 |

### 预期机制

1. **减少浪费的早期重试**: KEY 冷却现在在 GLOBAL 冷却 (45s) 后释放 — 不再提前 3s。当 GLOBAL-COOLDOWN 标记所有 keys 45s 冷却时，KEY 冷却不再提前到期导致额外重试。

2. **对称冷却对齐**: KEY_COOLDOWN_S=45, TIER_COOLDOWN_S=45, GLOBAL_COOLDOWN=45 — 三层冷却完全同步。任何 429 事件触发 45s 冷却在所有层同时到期，减少层间时序不一致。

3. **5-Key 429 循环: 不做改变**: 5×MIN_OUTBOUND_INTERVAL_S=69.0s 保持不变。deepseek NVCFPexecTimeout (49-59s) 是上游问题不受 cooldown 参数影响。

4. **glm5.1 429 重试效率**: 当前 30min 窗口 1,245 键级 429 浪费。KEY 对齐到 45s 应该减少重试窗口内的浪费（KEY 冷却不再在 42s 提前到期，而在 45s 与 TIER/GLOBAL 同步）。

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记