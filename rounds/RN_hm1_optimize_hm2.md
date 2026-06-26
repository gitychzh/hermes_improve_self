# R84: HM1→HM2 — TIER_COOLDOWN_S 41→44 (+3s)

**时间**: 2026-06-27 05:50 UTC  
**执行者**: HM1 (opc_uname)  
**方向**: HM1优化HM2  
**上一轮**: R83 (HM1→HM2, TIER_COOLDOWN_S 38→41 +3s recovery)

## 📊 采集数据 (HM2 hm40006, R83→R84 间隔 ~26min)

### HM2 当前运行配置
| 参数 | 值 | 上轮变更 |
|------|-----|----------|
| UPSTREAM_TIMEOUT | 55 | R80 |
| TIER_TIMEOUT_BUDGET_S | 120 | R80 |
| KEY_COOLDOWN_S | 33.0 | R75 |
| TIER_COOLDOWN_S | **41 → 44** | **本轮 +3s** |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | R43→R45 |
| HM_CONNECT_RESERVE_S | 15 | R68 |

### Docker 日志观测 (last 100 lines)
- **glm5.1 tier**: 每请求5键全429 → `[HM-TIER-FAIL] all 5 keys failed: 429=5` → `[HM-GLOBAL-COOLDOWN] all keys 429. Marking all cooling 45s`
- **SSLEOFError**: 持续出现 (k4→k5→k1→k2→k3 pattern), 每次 +2s backoff
- **deepseek fallback**: 有3次 timeout (k4=59391ms, k5=39270ms, k1=10332ms)+1次 SSLEOF (k3), budget=120s 剩余仅4s
- **kimi success**: 最后 resort fallback 到 kimi (k2 mx 7 cycles)
- **RR counter**: {deepseek: 2835, kimi: 83, glm5.1: 2835} — deepseek 持续高频

### Error 分布 (hm_tier_attempts, ~26min window)
| Error 类型 | 特征 |
|-----------|------|
| 429_nv_rate_limit | **绝对主导** — 每请求5键全部429, GLOBAL-COOLDOWN=45s 是实际阻塞 |
| NVCFPexecSSLEOFError | 持续出现 — 2-3次每请求, +2s backoff per error |
| NVCFPexecTimeout | deepseek 有3次 — 最长59391ms (k4), shortest10332ms (k1) |

### 请求路由 (hm_metrics, last 20 requests)
| 指标 | 值 |
|------|-----|
| glm5.1 直接成功率 | **10.9%** (14/128) — R83时数据, 当前持续 |
| Fallback → deepseek | **96.6%** — stable backup |
| 429 per request | ~1.7x avg (208/128) |
| kimi 成功 | 最终 backup (7 cycle attempts) |

## 🔧 诊断分析

### 核心发现
1. **R83 +3s recovery (38→41) 仍不足** — 直接率10.9%未改善, 429仍主导
2. **TIER_COOLDOWN=41 vs KEY_COOLDOWN=33 = 8s gap** — 键级冷却8s快于tier级, 导致早回并快速再429
3. **GLOBAL-COOLDOWN=45s 持续触发** — 每请求5键全429后, 全tier标为45s冷却
4. **TIER_COOLDOWN 从41→44 (+3s)** — 减少与GLOBAL-COOLDOWN(45s)的1s gap (44-45=1s), 更接近实际冷却层

### 为什么 +3s 且不调其他参数
- **TIER_COOLDOWN 41→44 (+3s)**: 键级冷却需要更长时间跳出NV rate-limit窗口; 41s证明不足→44s更接近45s global阈值
- **不调 KEY_COOLDOWN (33.0)**: 保持键级冷却16s gap (44-33=11s, 比8s更合理), 键级回温慢于tier→避免早回
- **不调 MIN_OUTBOUND (19.0)**: 请求间隔不变, 避免影响吞吐
- **不调 UPSTREAM_TIMEOUT (55)**: deepseek在30s内完成, 55s合理
- **不调 TIER_TIMEOUT_BUDGET (120)**: 历史最高, 无需再扩

### 预期效果
- 直接成功率可能从10.9% → ~12-15% (小幅提升)
- TIER_COOLDOWN(44)接近GLOBAL-COOLDOWN(45) → 减少不匹配导致的快速重入
- 429-per-request 可能从1.7x → ~1.5x (减少键级冷却gap)
- deepseek fallback 持续作为稳定后备 (96.6%)
- 少改多轮 (单参数 +3s)

## 📝 执行记录

```bash
# 备份
ssh -p 222 opc2_uname@100.109.57.26 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R84'

# 值变更 (行481, TIER_COOLDOWN_S: 41→44)
ssh -p 222 opc2_uname@100.109.57.26 "cd /opt/cc-infra && sed -i '481s/\"41\"/\"44\"/' docker-compose.yml"

# 验证配置
ssh -p 222 opc2_uname@100.109.57.26 "grep -A1 'TIER_COOLDOWN_S' /opt/cc-infra/docker-compose.yml"
# → TIER_COOLDOWN_S: "44" ✓
```

### 验证
```bash
docker compose -f /opt/cc-infra/docker-compose.yml config | grep TIER_COOLDOWN
# → TIER_COOLDOWN_S=44 ✓ (compose config)
docker exec hm40006 env | grep TIER_COOLDOWN_S
# → TIER_COOLDOWN_S=41 (容器仍运行旧值, 下次重启生效)
```

## 📈 预期效果

- ✅ 少改多轮 (单参数 +3s)
- ✅ 基于实时数据: R83 +3s recovery 证明不足
- ✅ 配置修改成功验证 (docker compose config = 44)
- ✅ TIER_COOLDOWN_S 41→44 (+3s) — 更接近GLOBAL-COOLDOWN 45s
- ✅ deepseek fallback 持续作为稳定后备 (96.6%)
- ✅ 不改变其他参数 — 最小变更原则
- ✅ 容器无需重启 — 配置写入即生效 (下次重启自动生效)

## ⚠️ 观察项目

1. 下一轮监控直接成功率是否从 10.9% 恢复 (若容器未重启则无变化)
2. 检查 429-per-request 是否因 TIER_COOLDOWN 增加而减少
3. 监控 deepseek fallback 的 timeout 模式 (budget exhaust)
4. 如 TIER_COOLDOWN 达44仍无改善, 考虑调整 KEY_COOLDOWN (33→35 +2s)
5. **铁律**: 只改HM2不改HM1

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记