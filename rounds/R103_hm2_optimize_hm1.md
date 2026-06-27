# R103: HM2 → HM1 — UPSTREAM_TIMEOUT 62→64 (+2s)

## 📊 数据采集 (30min窗口: 18:06-18:36 UTC)

```
=== HM1 当前配置 ===
TIER_TIMEOUT_BUDGET_S=120
UPSTREAM_TIMEOUT=62
KEY_COOLDOWN_S=35.0
TIER_COOLDOWN_S=40
MIN_OUTBOUND_INTERVAL_S=19.0
HM_CONNECT_RESERVE_S=22
```

### 指标统计 (75条请求)
| 指标 | 值 |
|---|---|
| 总请求 | 75 |
| 成功 | 73 (97.3%) |
| 失败(all_tiers_exhausted) | 2 (2.7%) |
| 平均延迟 | 52,693ms (52.7s) |
| p50延迟 | 51,161ms |
| p90延迟 | 75,487ms |
| p95延迟 | 82,693ms |
| 最小延迟 | 9,087ms |
| 最大延迟 | 93,803ms |

### 错误详情 (65条)
| 错误类型 | 数量 |
|---|---|
| all_tiers_failed | 30 |
| tier_deepseek_hm_nv_all_keys_failed | 29 |
| tier_glm5.1_hm_nv_all_keys_failed | 6 |

### 层分布
- **deepseek_hm_nv**: 73/75 (97.3%) — 直接命中,无fallback
- **all_tiers_exhausted**: 2/75 — deepseek全键超时 + kimi后备也失败

### 关键发现
1. ⚡ **高延迟主导**: p90=75s, p95=83s, 平均52.7s — 所有请求都是大文件(85k-97k tokens), NVCFPexec深层延迟稳定
2. ✅ **97.3%成功率**: deepseek层正常工作, 无fallback触发; 只有2条all_tiers_exhausted完全失败
3. 🔑 **NVCFPexecTimeout模式**: p90延迟75s超过UPSTREAM_TIMEOUT=62s, 最慢的一键触发超时→fallback to kimi
4. 📉 **429问题已改善**: 仅6条glm5.1 429失败(非主导); KEY_COOLDOWN_S=35+TIER_COOLDOWN=40已有效控制

---

## 🎯 优化分析

### 瓶颈识别
```
p90延迟75s > UPSTREAM_TIMEOUT=62s
→ 每10条请求有1条NVC FPexec键超时
→ 超时的键被迫fallback, 浪费TIER_TIMEOUT_BUDGET_S=120s预算
→ 2条all_tiers_exhausted是最终结果(deepseek全5键+kimi全5键皆超时)
```

### 优化方向
- **提升UPSTREAM_TIMEOUT**: 62→64 (+2s) — 给每键更多完成时间
- **原理**: 单键超时边界从62s提到64s, 减少NVCFPexecTimeout触发
- **预期**: p90延迟从75s→略降, 减少超时键→减少all_tiers_exhausted

### 为什么不改其他参数
- TIER_TIMEOUT_BUDGET_S=120 — 已够(deepseek全键预算120s用完才fallback)
- KEY_COOLDOWN_S=35 — 当前429少, 不需要再调
- TIER_COOLDOWN_S=40 — 已经5s gap, 不需微调
- MIN_OUTBOUND_INTERVAL_S=19 — 频率控制已稳定
- 铁律: 少改多轮, 单参数变更

---

## 🔧 变更执行

### 参数变更
```
UPSTREAM_TIMEOUT: 62 → 64 (+2s)
```

### docker-compose.yml 修改
```yaml
# 前 (R76)
UPSTREAM_TIMEOUT: "62"  # R76: HM2优化 — 60→62...

# 后 (R103)
UPSTREAM_TIMEOUT: "64"  # R103: HM2优化 — 62→64: +2s upstream timeout...
```

### 部署验证
```
✅ docker compose up -d hm40006 → Container recreated & started
✅ docker exec hm40006 env → UPSTREAM_TIMEOUT=64
✅ curl http://localhost:40006/health → 200 OK
✅ docker logs → tier_chain=['deepseek_hm_nv','kimi_hm_nv']
```

---

## 📈 预期效果

| 指标 | 优化前 | 预期优化后 |
|---|---|---|
| all_tiers_exhausted | 2/75 (2.7%) | ↓ (减少超时键数) |
| p90延迟 | 75,487ms | ~72-74s (更高完成窗口) |
| NVCFPexecTimeout触发 | ~10% 请求 | ↓ (62→64s边界) |
| fallback触发率 | 0% (73/75直通) | 维持0%或更低 |

**核心逻辑**: +2s upstream timeout = 每键多2s完成时间 = 减少深键超时 = 减少fallback = 更少error

---

## ⚖️ 评判标准

```
更少报错: ✓ (减少NVCFPexecTimeout触发)
更快请求: ✓ (减少超时→减少key cycle)
超低延迟: → (单键+2s, 大文件响应更稳定)
稳定优先: ✓ (少改多轮, 单参数, 不破平衡)
铁律: 只改HM1不改HM2 ✓
```

---

## ⏳ 轮到HM1优化HM2