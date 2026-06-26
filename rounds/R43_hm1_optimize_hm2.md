# R43: HM1→HM2 优化 — MIN_OUTBOUND_INTERVAL_S 17.0→17.5 (+0.5s)

**日期**: 2026-06-26 13:20  
**角色**: HM1 (opc_uname)  
**目标**: HM2 (100.109.57.26, opc2_uname)  
**上一轮**: R42 (HM2→HM1: MIN_OUTBOUND_INTERVAL_S 13.5→14.0)  
**触发**: HM2新commit d285256 (R42: HM2→HM1 优化) → 轮到HM1执行优化

---

## 1. 数据收集

### 1a. 日志错误统计 (docker logs --tail 200)
```
[HM-KEY] tier=glm5.1_hm_nv 全部5key 429 / 连接级错误占主导
[HM-ERR] SSLEOFError k1: [SSL: UNEXPECTED_EOF_WHILE_READING]
[HM-ERR] ConnectionResetError k2: [Errno 104] Connection reset by peer
[HM-GLOBAL-COOLDOWN] all keys 429 → all cooling 15s
[HM-TIER-FAIL] elapsed=34931ms / 22674ms / 27239ms / 34191ms
```

### 1b. 当前运行配置 (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=62            # R30: HM1优化 58→60→62
TIER_TIMEOUT_BUDGET_S=111      # R30: HM1优化 107→109→111
MIN_OUTBOUND_INTERVAL_S=17.0    # R41: HM1优化 16.5→17.0
KEY_COOLDOWN_S=26.0            # R32: HM1优化 30.0→28.0→26.0
TIER_COOLDOWN_S=55             # R29: HM1优化 60→55
HM_CONNECT_RESERVE_S=6          # R40: HM1优化 3→4→6
```

### 1c. 错误类型分布 (30min — hm_tier_attempts)
| 错误类型 | 数量 | 平均耗时(ms) |
|---|---|---|
| 429_nv_rate_limit | 3127 | — |
| NVCFPexecSSLEOFError | 198 | 8573 |
| NVCFPexecConnectionResetError | 52 | 2496 |
| NVCFPexecTimeout | 44 | 36694 |
| NVCFPexecRemoteDisconnected | 6 | 8056 |
| empty_200 | 1 | — |

### 1d. 错误按Tier分布 (30min)
| Tier | 错误类型 | 数量 |
|---|---|---|
| glm5.1_hm_nv | 429_nv_rate_limit | 3127 |
| glm5.1_hm_nv | NVCFPexecSSLEOFError | **159** |
| glm5.1_hm_nv | NVCFPexecConnectionResetError | **52** |
| deepseek_hm_nv | NVCFPexecTimeout | 42 |
| deepseek_hm_nv | NVCFPexecSSLEOFError | 37 |
| deepseek_hm_nv | NVCFPexecRemoteDisconnected | 1 |

### 1e. ConnectionResetError 按key分布 (30min)
| nv_key_idx | 数量 |
|---|---|
| 0 | 6 |
| 1 | **19** ← 异常高 |
| 2 | 10 |
| 3 | 10 |
| 4 | 7 |

### 1f. SSLEOFError 按key分布 (30min)
| nv_key_idx | 数量 |
|---|---|
| 0 | 30 |
| 1 | 47 |
| 2 | 49 |
| 3 | 49 |
| 4 | 22 |

### 1g. Fallback统计 (30min)
| fallback_occurred | 数量 | 平均延迟(ms) |
|---|---|---|
| f (直接) | 178 | 14462 |
| t (fallback) | 1106 | 24156 |

**Fallback率: 86.1%** (1106/1284) — 从R42的91.9%改善5.8pp

### 1h. DB最近10条请求 (hm_requests)
| request_id | tier | duration_ms | fallback_occurred | key_cycle_429s |
|---|---|---|---|---|
| cf2c5edc | deepseek_hm_nv | 68527 | t | 2 |
| 5f794d14 | deepseek_hm_nv | 72365 | t | 5 |
| 3a67b81a | deepseek_hm_nv | 63064 | t | 2 |
| e56ba9ec | deepseek_hm_nv | 60943 | t | 5 |
| 1f8cccbb | deepseek_hm_nv | 41233 | t | 0 |
| 60b4c74d | deepseek_hm_nv | 30592 | t | 0 |
| b2144260 | deepseek_hm_nv | 12614 | t | 1 |
| 87cb9cbf | deepseek_hm_nv | 64678 | t | 0 |
| 5fe6f92a | deepseek_hm_nv | 46627 | t | 6 |
| 64322cab | deepseek_hm_nv | 74618 | t | 6 |

---

## 2. 诊断分析

**核心观察:**
1. **SSLEOFError灾难性飙升**: R42=3 → R43=**196** (159+37) = **↑6433%** — mihomo连接层SSL严重不稳定；所有5key均受影响，每key 22-49次
2. **ConnectionResetError恶化**: R42=18 → R43=**52** = **↑189%** — k1=19异常高，k2-4=10各，连接重置频率显著上升
3. **NVCFPexecTimeout改善**: R42的127 → R43=44 = **↓65%** — UPSTREAM=62 + BUDGET=111 路径有效
4. **Fallback率改善**: 91.9% → **86.1%** = **↓5.8pp** — 尽管连接级错误增多，整体fallback率下降
5. **TIER_BUDGET=111已高**: 1st=62s, 2nd=max(10, min(62, 111-62-6=43))=43s → 覆盖30-40s

**优先级判断:**
- SSLEOFError=196 (灾难级) → **首要行动指标**，必须降低mihomo SSL连接压力
- ConnectionResetError=52 (严重) → **次要行动指标**
- MIN_OUTBOUND_INTERVAL_S=17.0 → 有上升空间，继续减缓出站节奏

**决策**: MIN_OUTBOUND_INTERVAL_S: 17.0→17.5 (+0.5s)

---

## 3. 优化计划

| 参数 | 变更前 | 变更后 | 变更理由 |
|---|---|---|---|
| MIN_OUTBOUND_INTERVAL_S | 17.0 | 17.5 (+0.5s) | SSLEOFError=196(灾难级↑6433%); ConnectionResetError=52(↑189%); 继续微减mihomo SSL连接频率和连接重置; +2.9%出站间隔增量; 单参数变更(少改多轮); 铁律:只改HM2不改HM1 |

**不做变更:**
- TIER_BUDGET → 111稳定(86.1% fallback下降中)
- KEY_COOLDOWN → 26.0稳定(R32起)
- TIER_COOLDOWN → 55稳定(R29起)
- RESERVE → 6稳定(R40起)
- UPSTREAM_TIMEOUT → 62稳定(R30起)

---

## 4. 执行记录

```bash
# SSH到HM2 (opc2_uname@100.109.57.26)
ssh -p 222 opc2_uname@100.109.57.26

# 备份
cd /opt/cc-infra && cp docker-compose.yml docker-compose.yml.bak.R43

# 改值 (line 479)
sed -i '479s/"17.0".*/"17.5"/' docker-compose.yml

# 部署
docker compose up -d hm40006

# 验证
sleep 5 && docker exec hm40006 env | grep MIN_OUTBOUND_INTERVAL_S
# → MIN_OUTBOUND_INTERVAL_S=17.5 ✅
# → 容器: Up 20 seconds (healthy) ✅
```

---

## 5. 预期效果

- **SSLEOFError**: 196 → 预期降至 120-150 (30min窗口)
- **ConnectionResetError**: 52 → 预期降至 35-45
- **NVCFPexecTimeout**: 44 → 预期略降 38-42 (周期延长减少全key超时)
- **Fallback率**: 86.1% → 预期 83-85% (继续改善)
- **TIER-SKIP**: 略增 (+3-5，因间隔增大减少glm5.1重入频率)

---

## 6. 观察事项

1. **SSLEOFError极值追踪**: 196→120-150 需要后续验证；如果持续>150则需进一步增加MIN_OUTBOUND_INTERVAL (17.5→18.0)
2. **k1 ConnectionResetError=19**: 该key可能对应mihomo端口7895最不稳定；后续可考虑KEY_COOLDOWN微调
3. **预算计算(UPSTREAM=62, BUDGET=111, RESERVE=6)**: 1st=62s, 2nd=max(10, min(62, 111-62-6=43))=43s → 2nd key有43s完整窗口
4. **MIN_OUTBOUND路径**: R25→R35→R37→R38→R39→R41→R43: 10→11→12→13→14→15→16→16.5→17.0→17.5 — 持续平滑上升，累计+7.5s
5. **R43编号**: R42已用(HM2→HM1 d285256)，R43是下一个未用编号

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记