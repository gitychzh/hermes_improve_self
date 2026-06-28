# R261: HM1→HM2 — MIN_OUTBOUND_INTERVAL_S 15.6→16.0 (+0.4s) — 单轮优化

**回合类型**: 优化 (单参数)
**方向**: HM1 (opc_uname) → HM2 (opc2_uname)
**时间**: 2026-06-29 00:35 UTC
**原则**: 更少报错，更快请求，超低延迟，稳定优先 — 铁律:只改HM2不改HM1 — 少改多轮(单参数)

## 摘要

HM2 的 deepseek tier 30min 成功率 97.36% (1217/1250)，未达 99% 目标。33 个请求错误：32 all_tiers_exhausted + 1 NVStream_IncompleteRead。Deepseek tier 键级错误 88/30min (67 SSLEOFError + 15 NVCFPexecTimeout + 6 empty_200)，NVCFPexecTimeout 消耗 34-40s/键，3-4 次超时级联导致预算 124s 耗尽 (剩余 1.2-8.8s)。R260 刚提 TIER_TIMEOUT_BUDGET_S 120→124，本次继续单参数路径：MIN_OUTBOUND_INTERVAL_S 15.6→16.0 (+0.4s) 减少 SSLEOFError 键碰撞频率，给 deepseek 键更多空间在 SSL 中断后恢复。

## 参数变化

| 参数 | 旧值 | 新值 | 增量 |
|------|------|------|------|
| MIN_OUTBOUND_INTERVAL_S | 15.6 | 16.0 | +0.4s |

## 数据采集

### 30-min 窗口 (ha_requests)
- Total: 1250, Success: 1217 → **97.36%**
- Errors: 33 (32 all_tiers_exhausted + 1 NVStream_IncompleteRead)
- Avg duration: 25916ms

### 10-min 突发窗口
- Total: 1207, Success: 1174 → **97.27%**
- Errors: 33 (32 all_tiers_exhausted + 1 NVStream_IncompleteRead)
- **所有错误都集中在最近 10 分钟** — 前 20 分钟 0 错误 (42 请求)

### 请求级别错误分类 (30min)
| error_type | cnt | avg_ms |
|-----------|-----|--------|
| all_tiers_exhausted | 32 | 148187ms |
| NVStream_IncompleteRead | 1 | 32376ms |

### 键级错误分类 (hm_tier_attempts, 30min)
| tier | error_type | cnt |
|------|-----------|-----|
| deepseek_hm_nv | NVCFPexecSSLEOFError | 67 |
| deepseek_hm_nv | NVCFPexecTimeout | 15 |
| deepseek_hm_nv | empty_200 | 6 |
| glm5.1_hm_nv | NVCFPexecSSLEOFError | 5 |
| glm5.1_hm_nv | 500_nv_error | 2 |
| glm5.1_hm_nv | 429_nv_rate_limit | **1** |
| glm5.1_hm_nv | empty_200 | 1 |

### 预算断裂模式 (最近 4 次)
1. `00:27:17` — k4 连接后剩余 8.8s < 10s, 中止 (elapsed=115192ms)
2. `00:33:08` — 所有键超时/SSL, elapsed=62904ms 
3. `00:36:08` — 预算 124s 剩余 1.2s < 10s, 断裂 (elapsed=122768ms)

### 错误详情 JSONL (最新 20 行)
- 全部 `all_429: false` — NVCFPexecTimeout + SSLEOFError + empty_200, **非功能级 429**
- 每次失败 3-4 个键尝试: NVCFPexecTimeout 34-40s/键 + SSLEOFError 5-7s/键 + empty_200
- 总耗时 110-122s → 预算 124s 几乎耗尽
- 0 个 429 在键级 — 功能级速率限制不是瓶颈

### HM2 运行参数 (docker exec hm40006 env)
| 参数 | 值 |
|------|-----|
| TIER_TIMEOUT_BUDGET_S | 124 (R260: 120→124) |
| TIER_COOLDOWN_S | 45 |
| KEY_COOLDOWN_S | 38 |
| UPSTREAM_TIMEOUT | 63 |
| MIN_OUTBOUND_INTERVAL_S | **15.6→16.0** |
| HM_CONNECT_RESERVE_S | 24 (=HM1, 收敛完成) |
| PROXY_TIMEOUT | 300 |

### 沙箱验证
- mihomo: PID 2008535 ✅ 运行中
- hm40006: Up 30 seconds (healthy) ✅
- /health: 200 ✅
- MIN_OUTBOUND_INTERVAL_S=16.0 ✅ 生效

## 分析

### 为什么选择 MIN_OUTBOUND_INTERVAL_S

1. **Deepseek SSLEOFError 是主导键级浪费**: 67/88 = 76% 的 deepseek 键级错误是 SSLEOFError (SSL 连接中断)
2. **NVCFPexecTimeout 级联**: 每个超时消耗 34-40s, 3-4 个超时 = 110-122s 总预算, 与 124s 预算几乎持平
3. **429 几乎为零**: 仅 1 次 429 (glm5.1 tier) — 功能级 429 不是瓶颈, 不需要调整 KEY_COOLDOWN_S 或 TIER_COOLDOWN_S
4. **R260 刚提 TIER_TIMEOUT_BUDGET_S**: 120→124, 本次继续不同参数以避免双参数同一轮
5. **HM_CONNECT_RESERVE_S 已收敛**: 24=24 (与 HM1 相同) — 无更多头寸可增加

### 为什么不是其他参数

| 参数 | 当前值 | 为什么拒绝 |
|------|--------|----------|
| UPSTREAM_TIMEOUT | 63 | NVCFPexecTimeout 实际 34-40s < 63s 上限 — 增加不会减少超时, 只会让每个键等待更久 |
| TIER_TIMEOUT_BUDGET_S | 124 | 刚在 R260 增加 (120→124), 本次不重复 |
| KEY_COOLDOWN_S | 38 | TIER_COOLDOWN_S=45 > KEY=38, 无反向差距 — 且 429 只有 1 次/30min |
| TIER_COOLDOWN_S | 45 | 已在高位 — 且 429 只有 1 次 (无功能级速率限制信号) |
| HM_CONNECT_RESERVE_S | 24 | 已收敛到 HM1=24, 无更多头寸 |

### 预期效果

增加 MIN_OUTBOUND_INTERVAL_S → 键间间距更大 → SSLEOFError 碰撞概率降低 → 每个请求花更少键在 SSL 中断重试 → 更多预算留给成功的键 → 减少 all_tiers_exhausted

## 执行

```bash
# 1. 修改 compose 文件
ssh HM2 "sed -i 's|MIN_OUTBOUND_INTERVAL_S: \"15.6\"|MIN_OUTBOUND_INTERVAL_S: \"16.0\"|' /opt/cc-infra/docker-compose.yml"

# 2. 验证文件变更
grep -n 'MIN_OUTBOUND_INTERVAL_S' /opt/cc-infra/docker-compose.yml
# → 行 472: MIN_OUTBOUND_INTERVAL_S: "16.0"  (仅 hm40006 变更)

# 3. 重建容器
docker compose up -d --force-recreate --no-deps hm40006

# 4. 验证运行中 env
docker exec hm40006 env | grep MIN_OUTBOUND_INTERVAL_S
# → MIN_OUTBOUND_INTERVAL_S=16.0
```

## 闭环验证

- ✅ MIN_OUTBOUND_INTERVAL_S=16.0 生效
- ✅ hm40006: Up 30 seconds (healthy)
- ✅ mihomo PID 2008535 运行中
- ✅ /health: 200 OK
- ✅ 铁律遵守: 只改 HM2 配置, 未触及 HM1

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记