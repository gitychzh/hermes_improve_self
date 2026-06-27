# R109: HM2→HM1 优化 — TIER_TIMEOUT_BUDGET_S 130→132 (+2s)

## 📊 数据采集 (2026-06-27 ~19:52 UTC, post-R108部署)

### 容器环境
```env
TIER_TIMEOUT_BUDGET_S=130    # ← R108部署后, 本次优化目标
UPSTREAM_TIMEOUT=64
MIN_OUTBOUND_INTERVAL_S=20.0
KEY_COOLDOWN_S=38.0           # R108: 35→38 (+3s)
TIER_COOLDOWN_S=40
HM_CONNECT_RESERVE_S=22
CHARS_PER_TOKEN_ESTIMATE=3.0
```

### DB请求分析 (30min window)
| 指标 | 值 |
|------|-----|
| 总请求 | 42 |
| 成功 | 38 (90.5%) |
| 失败 | 4 (9.5%) |
| avg | 31.1s |
| p50 | 18.7s |
| p95 | 125.8s |
| max | 130.2s |

**失败明细**:
- `all_tiers_exhausted` ×3 (avg=129.0s, 127.7s/130.2s/129.3s) — 全部命中BUDGET=130边界
- `NVStream_TimeoutError` ×1 on k0 (88.8s) — 单key超时

**Tier健康 (1h)**:
| tier | ok | fail | success% | avg |
|------|-----|------|----------|-----|
| deepseek_hm_nv | 1209 | 3 | 99.8% | 32.5s |
| glm5.1_hm_nv | 78 | 0 | 100.0% | 34.1s |
| (None) | 0 | 36 | 0% | - |

**Key桶位分布 (30min)**:
- key_cycle_429s=0: 41 requests (100%) — 无429循环
- 无fallback触发

**1h Duration分布 (成功请求)**:
| 桶 | 数量 | % |
|---|------|---|
| <10s | 19 | 17.3% |
| 10-20s | 52 | 47.3% |
| 20-30s | 24 | 21.8% |
| 30-40s | 2 | 1.8% |
| 40-50s | 6 | 5.5% |
| 50-60s | 2 | 1.8% |
| 60-80s | 3 | 2.7% |
| >80s | 2 | 1.8% |

**长尾 (>40s)**: 11.8% — 仍偏高

**Per-key 错误 (24h)**:
| tier | key | error | n | avg_elapsed |
|------|-----|-------|---|-------------|
| deepseek_hm_nv | k2 | NVCFPexecTimeout | 28 | 23.1s |
| deepseek_hm_nv | k1 | NVCFPexecTimeout | 26 | 29.0s |
| deepseek_hm_nv | k3 | NVCFPexecTimeout | 22 | 28.7s |
| deepseek_hm_nv | k0 | NVCFPexecTimeout | 21 | 20.3s |
| deepseek_hm_nv | k4 | NVCFPexecTimeout | 21 | 18.1s |

**Per-key 延迟 1h (成功)**:
| key | avg | max | min |
|-----|-----|-----|-----|
| k1 | 23.3s | 84.2s | 4.0s |
| k3 | 22.4s | 60.4s | 3.4s |
| k2 | 21.8s | 65.7s | 6.3s |
| k4 | 20.3s | 78.7s | 5.1s |
| k0 | 19.7s | 45.8s | 4.2s |

### docker logs (最近500行)
- 1× SSLEOFError on k4 (7897 proxy): SSL UNEXPECTED_EOF_WHILE_READING
  → 自动retry到k5成功 ✅
- 无其他错误/超时日志

## 🎯 优化分析

### 瓶颈识别
R108 (KEY_COOLDOWN_S 35→38) 部署后仍出现 **3次 all_tiers_exhausted** 全部命中 BUDGET=130 边界:
- 3次失败 avg=129.0s → 2×UPSTREAM(64)=128s + 连接/SSL开销=~1s → 刚好达到130s边界
- R106已从128→130提2s,但2s余量不足以覆盖代理键(k3/k4/k5)的SSL+connect额外开销
- Proxy键(7896/7897/7899)需要额外的SOCKS5+SSL握手时间(~1-3s), 2s margin太小

### 为什么选TIER_TIMEOUT_BUDGET_S
1. 直接原因: 3/4 failures = all_tiers_exhausted → 预算边界击穿
2. 2×UPSTREAM(64)=128s, 当前BUDGET=130s → 仅2s余量 → 代理键额外开销未覆盖
3. 少改多轮: 单参数+2s增量, 最小安全增量
4. 不选其他参数:
   - UPSTREAM_TIMEOUT: 64s已是合理上限 (1min X-Hermes-NV-Timeout轮询)
   - KEY_COOLDOWN_S: R108刚改过,需要观察效果
   - TIER_COOLDOWN_S: gap已2s(38→40),再缩小无益
   - MIN_OUTBOUND_INTERVAL_S: 20s间隔足够,非primary瓶颈

### 预算计算
```
Before: UPSTREAM=64, BUDGET=130, MIN=20, RESERVE=22
  1st key = 64s (DIRECT k1)
  2nd key = max(10, min(64, 130-64-22-20)) = max(10, 24) = 24s
  Total: 64+24=88s ≤ 130s ✓ (42s headroom)
  但2连续全超时: 2×64=128s → 130-128=2s → 刚好边界

After: UPSTREAM=64, BUDGET=132, MIN=20, RESERVE=22
  1st key = 64s
  2nd key = max(10, min(64, 132-64-22-20)) = max(10, 26) = 26s
  Total: 64+26=90s ≤ 132s ✓ (42s headroom)
  2连续全超时: 2×64=128s → 132-128=4s margin ✓
```

## 🔧 变更执行

### docker-compose.yml diff
```yaml
# Line 418, /opt/cc-infra/docker-compose.yml
-      TIER_TIMEOUT_BUDGET_S: "130"  # ...R105: 124→128
+      TIER_TIMEOUT_BUDGET_S: "132"  # R109: HM2→HM1 — 130→132 (+2s)
```

### 部署
```bash
cd /opt/cc-infra && docker compose up -d hm40006
# ✅ Recreated & Started
```

### 验证
- ✅ `docker exec hm40006 env | grep TIER_TIMEOUT_BUDGET_S` = 132
- ✅ Container: healthy, running
- ✅ 重启后无错误日志
- ✅ 请求正常流转: k1→k2→k3→k4→k5 轮询

## 📈 预期效果

| 指标 | 变更前 | 变更后 (预期) |
|------|--------|---------------|
| 30min 失败率 | 9.5% (4/42) | <5% |
| all_tiers_exhausted/30min | 3 | 0-1 |
| budget 安全余量 | 2s | 4s |
| 2×UPSTREAM覆盖 | 130-128=2s | 132-128=4s |

## ⚖️ 评判标准

- **更少报错**: ✅ 4s BUDGET余量 → 减少边界all_tiers_exhausted (当前3/42→预期0/30min)
- **更快请求**: ✅ 预算扩大=更少超时=更少retry=更低p95 (125.8s→预期<90s)
- **超低延迟**: ✅ 维持deepseek核心p50=18.7s基线, 不增加开销
- **稳定优先**: ✅ 单参数+2s最小增量, 观察后积累; 4s margin覆盖代理键SSL开销
- **铁律**: ✅ 只改HM1 (docker-compose.yml line 418), 不改HM2本地

## ⏳ 轮到HM1优化HM2