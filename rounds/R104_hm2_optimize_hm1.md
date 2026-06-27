# R104: HM2 → HM1 — TIER_TIMEOUT_BUDGET_S 120→124 (+4s)

## 📊 数据采集 (30min窗口: 18:25-18:57 UTC)

```
=== HM1 当前配置 ===
TIER_TIMEOUT_BUDGET_S=120
UPSTREAM_TIMEOUT=64
KEY_COOLDOWN_S=35.0
TIER_COOLDOWN_S=40
MIN_OUTBOUND_INTERVAL_S=19.0
HM_CONNECT_RESERVE_S=22
```

### 指标统计 (82条请求, 30min)
| 指标 | 值 |
|---|---|
| 总请求 | 82 |
| 成功 | 81 (98.8%) |
| 失败(all_tiers_exhausted) | 1 (1.2%) |
| 平均延迟 | 38,387ms |
| p50延迟 | 36,008ms |
| p90延迟 | 59,292ms |
| p95延迟 | 77,727ms |
| 最小延迟 | 3,524ms |
| 最大延迟(成功) | 112,000ms |
| 最大延迟(失败) | 140,282ms |
| fallback触发 | 0 |
| fallback实际尝试 | 0 |

### 1h窗口 (175条)
| 指标 | 值 |
|---|---|
| 总请求 | 175 |
| 成功 | 171 (97.7%) |
| 失败(all_tiers_exhausted) | 4 (2.3%) |
| 平均成功延迟 | 46,231ms |
| 最大延迟(成功) | 112,000ms |
| 最大延迟(失败) | 166,774ms |

### 键级延迟分布 (1h成功请求)
| 键 | 请求数 | 平均延迟 | 最大延迟 |
|---|---|---|---|
| k0 (DIRECT) | 37 | 49,428ms | 112,000ms |
| k1 (DIRECT) | 35 | 43,273ms | 75,363ms |
| k2 (DIRECT) | 29 | 40,311ms | 83,944ms |
| k3 (proxy) | 36 | 50,127ms | 94,964ms |
| k4 (proxy) | 33 | 47,333ms | 89,255ms |
| k5 (proxy) | — | — | — |

### 错误详情 (30min)
| 错误类型 | 数量 |
|---|---|
| SSLEOFError (k4, recovered) | 1 |
| all_tiers_exhausted | 1 |

### 关键发现
1. ✅ **98.8%直通成功**: 所有deepseek请求首键命中, 无fallback触发; 只有1条all_tiers_exhausted
2. ⚡ **p95=77.7s**: 5%请求>77s, 成功边界在112s→仍低于TIER_TIMEOUT_BUDGET=120s
3. 🔑 **1h 4条all_tiers_exhausted**: 失败延迟 133-167s 全部 >120s tier budget; budget耗尽后无余量
4. 📉 **键级差异**: k3/k0 proxy键平均延迟最高(50s/49s), k2 DIRECT键最快(40s); 大文件45k-53k tokens输出均稳定
5. ✅ **SSL恢复**: 仅1条SSLEOFError(k4)自动重试恢复; SSL状态总体良好
6. 🔄 **ring fallback R40**: tier_chain=['deepseek_hm_nv','kimi_hm_nv'], 但deepseek全键未触发fallback

---

## 🎯 优化分析

### 瓶颈识别
```
4条all_tiers_exhausted在1h (2.3%):
  → 失败延迟 133s, 149s, 167s, 140s 全部 > TIER_TIMEOUT_BUDGET_S=120s
  → deepseek+kimi全部键超时/预算耗尽
  → 当前120s预算不足以覆盖最坏情况(多键全慢)
  
p95成功=77.7s, 最大成功=112s:
  → 成功仍在120s预算内, 但112s逼近边界
  → 每次all_tiers_exhausted前, 至少1键在~120s处预算耗尽
```

### 优化方向
- **提升TIER_TIMEOUT_BUDGET_S**: 120→124 (+4s) — 给首层键更多完成时间
- **原理**: 每+4s预算 = 深键第一尝试键多4s = 减少budget_exhausted_after_connect触发
- **预期**: 4条/1h all_tiers_exhausted → 2-3条或更少; +4s=3.3%余量增加
- **不改变其他参数原因**: 所有键已正常工作, UPSTREAM=64已足够(刚+2s), 键冷却已优化

### 为什么不改其他参数
- UPSTREAM_TIMEOUT=64 — 刚+2s到64(R103), 当前p90=59s在边界内, 不重复调
- KEY_COOLDOWN_S=35 — 429已有效控制, 键冷却gap=5s稳定
- TIER_COOLDOWN_S=40 — 已40s, 不需微调
- MIN_OUTBOUND_INTERVAL_S=19 — 频率已稳定, 98.8%成功率无需加速
- HM_CONNECT_RESERVE_S=22 — 连接预留已优化
- 铁律: 少改多轮, 单参数变更

---

## 🔧 变更执行

### 参数变更
```
TIER_TIMEOUT_BUDGET_S: 120 → 124 (+4s)
```

### docker-compose.yml 修改
```yaml
# 前 (R100→R103)
      TIER_TIMEOUT_BUDGET_S: "120"  # R100: HM2优化 — 112→116: +4s...

# 后 (R104)
      TIER_TIMEOUT_BUDGET_S: "124"  # R104: HM2优化 — 120→124: +4s tier budget;
        # 1h: 175req/4all_tiers_exhausted(2.3%), max fail 167s>120s;
        # +4s给首层键更多完成时间, 减少budget_exhausted_after_connect;
        # p95=77.7s→余量增加; 少改多轮(单参数); 铁律:只改HM1不改HM2
```

### 部署验证
```
✅ cp docker-compose.yml → docker-compose.yml.bak.R104_hm2
✅ docker compose up -d hm40006 → Container recreated & started
✅ docker exec hm40006 env → TIER_TIMEOUT_BUDGET_S=124
✅ curl http://localhost:40006/health → 200 OK
✅ docker logs → tier_chain=['deepseek_hm_nv','kimi_hm_nv']
```

---

## 📈 预期效果

| 指标 | 优化前 | 预期优化后 |
|---|---|---|
| all_tiers_exhausted (1h) | 4/175 (2.3%) | ↓ 1-2/175 (减少预算耗尽) |
| p95延迟 | 77,727ms | ~75-78s (不变, 键行为未变) |
| budget_exhausted触发 | ~3-5/h | ↓ (124s>120s) |
| fallback触发率 | 0% (175/175直通) | 维持0% |

**核心逻辑**: +4s tier budget = 首层键多4s完成窗口 = 减少budget_exhausted_after_connect = 更少all_tiers_exhausted = 更高成功率

---

## ⚖️ 评判标准

```
更少报错: ✓ (减少all_tiers_exhausted, 4→预期2-3/1h)
更快请求: → (键延迟未变, 但减少深键超时→减少key retry)
超低延迟: → (p95=77.7s稳定, 大文件延迟主要由NVCF决定)
稳定优先: ✓ (少改多轮, 单参数, 不破平衡)
铁律: 只改HM1不改HM2 ✓
```

---

## ⏳ 轮到HM1优化HM2