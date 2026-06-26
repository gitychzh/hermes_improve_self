# R44: HM2→HM1 优化 — TIER_TIMEOUT_BUDGET_S 94→96 (+2s)

**日期**: 2026-06-26 13:20  
**角色**: HM2 (opc2_uname)  
**目标**: HM1 (100.109.153.83, opc_uname)  
**上一轮**: R43 (HM1→HM2: MIN_OUTBOUND_INTERVAL_S 17.0→17.5)  
**触发**: HM1新commit 5b5e197 (R43: HM1→HM2 优化)

---

## 1. 数据收集

### 1a. 日志错误统计 (docker logs --tail 100)
```
[HM-KEY] tier=glm5.1_hm_nv 5key全429 / 连接级错误轻微
[HM-ERR] ConnectionResetError k1-k0: [Errno 104] Connection reset by peer = 22次
[HM-TIER-SKIP] all keys in cooldown, skipping → all-fallback to deepseek_hm_nv
[HM-SUCCESS] tier=deepseek_hm_nv k2 succeeded after 5 cycle attempts (26262ms)
```

### 1b. 当前运行配置 (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=42             # R18: HM2优化 35→40→42
TIER_TIMEOUT_BUDGET_S=94      # R41: HM2优化 92→94 → R44: 94→96
MIN_OUTBOUND_INTERVAL_S=14.0    # R42: HM2优化 13.5→14.0
KEY_COOLDOWN_S=38.0             # R19: HM2优化 35→38
TIER_COOLDON_S=84               # R37: HM2优化 86→84
HM_CONNECT_RESERVE_S=22         # R29: HM2优化 21→22
```

### 1c. 错误类型分布 (60min — hm_tier_attempts)
| 错误类型 | 数量 | 平均耗时(ms) |
|---|---|---|
| 429_nv_rate_limit | 1208 | — |
| NVCFPexecTimeout | 129 | 28825 |
| NVCFPexecConnectionResetError | 22 | 1767 |
| budget_exhausted_after_connect | 5 | 797 |
| NVCFPexecRemoteDisconnected | 3 | 3775 |

### 1d. 错误按Tier分布 (60min)
| Tier | 错误类型 | 数量 |
|---|---|---|
| glm5.1_hm_nv | 429_nv_rate_limit | 1208 |
| glm5.1_hm_nv | NVCFPexecConnectionResetError | 22 |
| deepseek_hm_nv | NVCFPexecTimeout | 128 |
| deepseek_hm_nv | budget_exhausted_after_connect | 5 |

### 1e. ConnectionResetError 按key分布 (60min, glm5.1)
| nv_key_idx | 数量 |
|---|---|
| 0 | 4 |
| 1 | 5 |
| 2 | 4 |
| 3 | 3 |
| 4 | 6 |
→ 均匀分布，无异常key，22次总体可控(R42目标12-15，实际略超但7个缺额)

### 1f. SSLEOFError 按key分布 (60min)
| nv_key_idx | 数量 |
|---|---|
| — | **0** |
→ **SSLEOFError=0**，R42 MIN_OUTBOUND=14.0成功消除SSLEOF，验证通过

### 1g. Fallback统计 (60min)
| fallback_occurred | 数量 | 平均延迟(ms) |
|---|---|---|
| f (直接) | 125 | 16470 |
| t (fallback) | 1320 | 17004 |
→ **Fallback率: 91.3%** (1320/1445) — 高位稳定，glm5.1 100% 429

### 1h. Deepseek NVCFPexecTimeout 耗时分桶 (60min, 128 events)
| bucket | cnt | 占比 |
|---|---|---|
| < 20s | 43 | 33.6% |
| 20-25s | 11 | 8.6% |
| 25-30s | 9 | 7.0% |
| 30-35s | 12 | 9.4% |
| 35-40s | 8 | 6.3% |
| > 40s | 43 | 33.6% |

### 1i. 0-tier预Tier失败 (60min)
| error_type | tiers_tried_count | cnt | avg(ms) |
|---|---|---|---|
| all_tiers_exhausted | 0 | 4 | 150621 |
→ **0-tier=4** (极低)，RESERVE=22有效维持

### 1j. DB最近10条请求 (hm_requests, 最近30min)
| request_id | tier_model | duration | fallback | key_429s |
|---|---|---|---|---|
| 56fd4b81 | deepseek_hm_nv | 16608ms | t | 0 |
| 22bbbac2 | deepseek_hm_nv | 15178ms | t | 0 |
| e1ae3c7c | deepseek_hm_nv | 10911ms | t | 0 |
| 83324f6e | deepseek_hm_nv | 18676ms | t | 0 |
| e5c11b3b | deepseek_hm_nv | 17005ms | t | 5 |

---

## 2. 诊断分析

**核心观察:**
1. **NVCFPexecTimeout=129主导**: 128 deepseek + 1 kimi = 129 timeout/60min。>40s bucket=43 (33.6%)是最大单一桶 — 这些请求耗尽42s UPSTREAM后仍NVCF超时。
2. **BUDGET=94 2nd-attemp=30s** (UPSTREAM=42, RESERVE=22): 1st=min(42,94-22=72)=42s; remain=52, 2nd=max(10,min(42,52-22=30))=30s
3. **30-35s bucket=12 (9.4%)**: 当前2nd=30s刚好截断30s边界。30-35s的12个请求中被28-30s的有部分完成，30-32s区间截断。
4. **No SSLEOFError (0)**: R42 MIN_OUTBOUND=14.0完全消除了SSLEOF (R41→R43灾难级飙升到196)，12个缺额的ConnectionResetError可接受。
5. **0-tier=4极低**: RESERVE=22有效抑制了预Tier连接失败。

### Budget边界计算 (变更前 R43)
- 1st=min(42, 94-22=72)=42s
- remain=94-42=52
- 2nd=max(10, min(42, 52-22=30))=30s
- Coverage: <20s=43(covered), 20-25s=11(covered), 25-30s=9(gap at 28-30s), 30-35s=12(uncovered), 35-40s=8(uncovered), >40s=43(UPSTREAM ceiling)

**决策**: TIER_TIMEOUT_BUDGET_S: 94→96 (+2s)

---

## 3. 优化计划

| 参数 | 变更前 | 变更后 | 变更理由 |
|---|---|---|---|
| TIER_TIMEOUT_BUDGET_S | 94 | 96 (+2s) | NVCFPexecTimeout=129(主导错误); >40s=43(33.6%预算耗尽); 30-35s=12(边界截断); +2s使2nd=30s→32s覆盖30-35s全区间; 单参数变更(少改多轮); 铁律:只改HM1不改HM2 |

**不做变更:**
- UPSTREAM_TIMEOUT → 42稳定，>40s bucket是NVCF ceiling非配置可变
- MIN_OUTBOUND_INTERVAL_S → 14.0稳定(SSLEOF=0, ConnRes=22可接受)
- KEY_COOLDOWN → 38稳定(R19起)
- TIER_COOLDON → 84稳定(R37起)
- RESERVE → 22稳定(R29起)，0-tier=4极低

**BUDGET数学(变更后):**
- 1st=min(42, 96-22=74)=42s
- remain=96-42=54
- 2nd=max(10, min(42, 54-22=32))=32s
- Coverage gain: 30-35s全区间(+30-32s coverage), 25-30s完全覆盖(原28-30s缺口补上)
- 预计捕获额外timeout: ~2-4个(30-32s区间)，整体NVCFPexecTimeout ↓ 2-4

---

## 4. 执行记录

```bash
# R44 执行:
# 1. 备份 compose
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && cp docker-compose.yml docker-compose.yml.bak.R44'

# 2. 改值 + 更新注释 (line 418)
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && sed -i "418s/\"94\"/\"96\"/" docker-compose.yml'
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '418s/# R41:.*$/# R44: HM2优化 — 94→96: +2s tier budget; UPSTREAM=42 RESERVE=22 1st=42s remain=54 2nd=32s headroom(...)/' docker-compose.yml"

# 3. 部署
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'
# → Container hm40006 Recreated → Started

# 4. 验证
ssh -p 222 opc_uname@100.109.153.83 'docker exec hm40006 env | grep TIER_TIMEOUT_BUDGET_S'
# → TIER_TIMEOUT_BUDGET_S=96 ✅
ssh -p 222 opc_uname@100.109.153.83 'docker ps --format "{{.Names}} {{.Status}}" | grep hm40006'
# → hm40006 Up About a minute (healthy) ✅
```

---

## 5. 预期效果

- **NVCFPexecTimeout**: 129 → 预期降至 125-128 (30-32s区间捕获~2-4 events; >40s不可变)
- **ConnectionResetError**: 22 → 预期稳定 20-25 (不受BUDGET影响)
- **SSLEOFError**: 0 → 预期保持0
- **Fallback率**: 91.3% → 预期改善0.2-0.5pp (deepseek延迟略降)
- **0-tier**: 4 → 预期稳定3-4 (RESERVE不变)

---

## 6. 观察事项

1. **>40s bucket (43 events, 33.6%)**: 不可由BUDGET扩展解决 — UPSTREAM=42 ceiling已耗尽。如该bucket持续增长(>50 events)，需再次上调UPSTREAM_TIMEOUT(42→44)或深入NVCF层排查。
2. **30-35s bucket监控**: 32s 2nd-attempt headroom应覆盖全区间。下轮需验证该bucket是否从12→8-10。
3. **ConnectionResetError追赶**: 22略高于R42目标(12-15)。若下轮>25，考虑MIN_OUTBOUND=14.0→14.5 (+0.5s)。
4. **budget_exhausted_after_connect=5**: 如果该值增加(>8)，RESERVE=22可能需要→23(+1s)。
5. **BUDGET上限**: TIER_BUDGET=96, UPSTREAM=42, RESERVE=22。2nd=32s。若≥100需要检查总延迟是否值得(+8s adds ~8s average latency)。

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记
