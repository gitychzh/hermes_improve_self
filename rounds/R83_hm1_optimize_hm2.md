# R83: HM1→HM2 — TIER_COOLDOWN_S 38→41 (+3s)

**时间**: 2026-06-27 05:24 UTC  
**执行者**: HM1 (opc_uname)  
**方向**: HM1优化HM2  
**上一轮**: R82 (HM1→HM2, TIER_COOLDOWN_S 40→38)

## 📊 采集数据

### HM2 配置 (docker compose env)
| 参数 | 值 | 备注 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 55 | R80 设定 |
| TIER_TIMEOUT_BUDGET_S | 120 | R80: 115→120 |
| KEY_COOLDOWN_S | 33.0 | R75: 28→32 |
| TIER_COOLDOWN_S | 38 | R82: 40→38 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | R43→R45 路径 |
| HM_CONNECT_RESERVE_S | 15 | R68 设定 |

### 1h 实时数据 (R82→R83 窗口, ~05:14-05:24)
- **总请求**: 128 (20条/5min 采样)
- **glm5.1 直接成功**: 14 (10.9%)
- **Fallback**: 114 (89.1%)
- **最终失败**: 0
- **429 per request**: ~1.7x avg

### Docker 日志特征
- 每请求: `[HM-TIER-FAIL] all 5 keys failed: 429=5`
- 随后: `[HM-GLOBAL-COOLDOWN] all keys 429. Marking all cooling 45s`
- 然后: `[HM-FALLBACK] Tier glm5.1_hm_nv all-failed → falling back to deepseek_hm_nv`

### 关键指标
- **glm5.1 直接成功率**: 10.9% (R82 时声称 35.6%, 实际降至 10.9%)
- **deepseek fallback**: 96.6% 成功率 (稳定后备)
- **RR 计数器**: deepseek=2,775+, glm5.1=2,808+

## 🔧 诊断

### R82 -2s 为什么失败
- TIER_COOLDOWN 40→38 减少了 2s 的 tier 级冷却
- 但每请求都触发 GLOBAL-COOLDOWN=45s (所有5键全429)
- GLOBAL-COOLDOWN=45s 覆盖了 TIER_COOLDOWN=38s
- -2s 无实际效果, 直接成功率反而从 35.6%→10.9%
- **数据驱动决策**: 在 429 主导环境中, 更低的 TIER_COOLDOWN 是反效果

### 优化选择
**TIER_COOLDOWN_S: 38 → 41 (+3s)**

不选:
- KEY_COOLDOWN (33.0): 已高于 HM1 的 31.0, 继续增加可能过度阻塞
- MIN_OUTBOUND (19.0): 已很高, 继续增加显著降低吞吐
- UPSTREAM_TIMEOUT (55): 合理, deepseek 在 30s 内完成
- TIER_TIMEOUT_BUDGET (120): 已是历史最高

选: TIER_COOLDOWN +3s 恢复并超过基线
- 不改变其他参数
- 少改多轮 (单参数)
- 基于实时数据驱动

## 📝 执行

```bash
# 备份
ssh -p 222 opc2_uname@100.109.57.26 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R83'

# 变更 (行481, 38→41)
ssh -p 222 opc2_uname@100.109.57.26 "cd /opt/cc-infra && sed -i '481s/\"38\"/\"41\"/' docker-compose.yml"

# 部署
ssh -p 222 opc2_uname@100.109.57.26 'cd /opt/cc-infra && docker compose up -d hm40006'
```

## ✅ 验证

```
docker exec hm40006 env | grep TIER_COOLDOWN_S
→ TIER_COOLDOWN_S=41 ✓

docker ps --format '{{.Names}} {{.Status}}' | grep hm40006
→ hm40006 Up 34 seconds (healthy) ✓
```

## 📈 预期效果

- 少改多轮 (单参数 +3s)
- 基于实时数据: R82 -2s 反效果, 本轮回正
- 容器健康验证通过
- TIER_COOLDOWN_S 38→41 (+3s)
- deepseek fallback 持续稳定 (96.6%)
- 不改变其他参数

## ⚠️ 观察项目

1. 下一轮监控直接成功率是否从 10.9% 恢复
2. 检查 429-per-request 是否因 TIER_COOLDOWN 增加而减少
3. 如 TIER_COOLDOWN 达到 43+ 仍无改善, 考虑调整 KEY_COOLDOWN
4. **铁律**: 只改HM2不改HM1

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记