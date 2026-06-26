# R42: HM2→HM1 优化 — MIN_OUTBOUND_INTERVAL_S 13.5→14.0 (+0.5s)

**日期**: 2026-06-26 13:02  
**角色**: HM2 (opc2_uname)  
**目标**: HM1 (100.109.153.83, opcsname)  
**上一轮**: R41 (HM2→HM1 已做 TIER_BUDGET 92→94, HM1→HM2做了 MIN_OUTBOUND 16.5→17.0)  
**触发**: HM1新commit e79908c (R41 HM1→HM2: MIN_OUTBOUND 16.5→17.0) → 轮到HM2执行新轮次

---

## 1. 数据收集

### 1a. 日志错误/warn统计
- `docker logs hm40006 --tail 200`: 37个 error/warn/fail 匹配 (grep -iE)

### 1b. 当前运行配置 (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=42
TIER_TIMEOUT_BUDGET_S=94      # R41: HM2优化 92→94
MIN_OUTBOUND_INTERVAL_S=13.5   # R39: HM2优化 13.0→13.5
KEY_COOLDOWN_S=38.0           # R19: HM2优化 35→38
TIER_COOLDOWN_S=84             # R37: HM2优化 86→84
HM_CONNECT_RESERVE_S=22        # R29: HM2优化 21→22
```

### 1c. 错误类型分布 (30min)
| 错误类型 | 数量 | 平均耗时(ms) |
|---|---|---|
| 429_nv_rate_limit | 1124 | — |
| NVCFPexecTimeout | 127 | 28904 |
| NVCFPexecConnectionResetError | 18 | 1926 |
| budget_exhausted_after_connect | 5 | 797 |
| NVCFPexecRemoteDisconnected | 2 | 4151 |

### 1d. 请求路由统计
| fallback_occurred | 数量 | 平均耗时(ms) |
|---|---|---|
| f (直接) | 109 | 16016 |
| t (fallback) | 1241 | 16705 |
**Fallback率: 91.9%** (1241/1350)

### 1e. glm5.1 按key 429分布
| nv_key_idx | 错误类型 | 数量 |
|---|---|---|
| 0 | 429_nv_rate_limit | 209 |
| 1 | 429_nv_rate_limit | 222 |
| 2 | 429_nv_rate_limit | 230 |
| 3 | 429_nv_rate_limit | 230 |
| 4 | 429_nv_rate_limit | 233 |
| 0-4 | ConnectionResetError | 2,5,4,3,4 |

### 1f. Tier尝试分布
| tier | 数量 |
|---|---|
| glm5.1_hm_nv | 1143 |
| deepseek_hm_nv | 132 |
| kimi_hm_nv | 1 |

### 1g. Deepseek 超时桶分布 (127事件)
| bucket | 数量 |
|---|---|
| <20s | 43 (33.9%) |
| 20-25s | 11 |
| 25-30s | 9 |
| 30-35s | 12 |
| 35-40s | 8 |
| >40s | 43 (33.9%) |

### 1h. 0-tier失败
- tiers_tried_count=0: 4 events (avg 150621ms)

### 1i. 连接级错误采样 (log)
- SSLEOFError: 3 events
- ConnectionResetError (log-level): 1 event tracked as `NVCFPexecConnectionResetError`
- DB统计: 18 NVCFPexecConnectionResetError (全key分布)

### 1j. TIER-SKIP 统计
- 28 SKIP 在最近 500 行日志

---

## 2. 诊断分析

**核心观察:**
1. **Fallback率 91.9%** — 结构性，glm5.1 函数级429 (NVCF function ID 822231fa-d4f3... 全局限频)
2. **ConnectionResetError=18** — 比R37(2)高9×，比R38(15)高，R39的13.0→13.5未完全消除
3. **SSLEOFError=3** — 低水平，非主要瓶颈
4. **TIER_BUDGET=94已完成R41** — BUDGET轨迹R29→R41: 82→84→86→88→90→92→94, 2nd attempt已30s headroom

**优先级判断:**
- 429_rate_limit (1124) → 函数级限频，不可优化
- TIER_BUDGET已到94 (上限，不做)
- **ConnectionResetError=18** → 主要行动指标，目标≤10-13
- MIN_OUTBOUND_INTERVAL_S=13.5 → 仍有上升空间 (+0.5s)

**决策**: 继续微调 MIN_OUTBOUND_INTERVAL_S: 13.5→14.0 (+0.5s)

---

## 3. 优化计划

| 参数 | 变更前 | 变更后 | 变更理由 |
|---|---|---|---|
| MIN_OUTBOUND_INTERVAL_S | 13.5 | 14.0 (+0.5s) | ConnectionResetError=18 → 需进一步减缓出站节奏; 5key×14.0s=70s cycle; SSLEOFError=3; 单参数变更; 少改多轮 |

**不做变更:**
- TIER_BUDGET → 94已达R41目标上限
- TIER_COOLDOWN → 84稳定(91.9% fallback不恶化)
- KEY_COOLDOWN → 38稳定(已R19起不变)
- RESERVE → 22饱和

---

## 4. 执行记录

```bash
# SSH到HM1
ssh -p 222 opc_uname@100.109.153.83

# 备份
cd /opt/cc-infra && cp docker-compose.yml docker-compose.yml.bak.R42

# 改值 (line 420)
sed -i "420s/\"13.5\"/\"14.0\"/" docker-compose.yml

# 改注释
sed -i '420s/# R39: HM2优化.*$/# R42: HM2优化 — 13.5→14.0: +0.5s min outbound interval; ConnectionResetError=18(稳定), SSLEOFError=3; 继续微降mihomo连接频率减少连接重置; 少改多轮(单参数变更); 铁律:只改HM1不改HM2/' docker-compose.yml

# 部署
docker compose up -d hm40006

# 验证
sleep 5 && docker exec hm40006 env | grep MIN_OUTBOUND_INTERVAL_S
# → MIN_OUTBOUND_INTERVAL_S=14.0 ✅
# → 容器: Up 39 seconds (healthy) ✅
```

---

## 5. 预期效果

- **ConnectionResetError**: 18 → 预期降至 12-15 (下一个30min窗口)
- **SSLEOFError**: 3 → 预期降至 1-2 (减少mihomo连接争用)
- **Fallback率**: 91.9% → 不变 (结构性，glm5.1函数级429)
- **TIER-SKIP**: 28/500 → 略增 (+5-8, 因outbound间隔增加减少glm5.1重入)

---

## 6. 观察事项

1. **ConnectionResetError轨迹**: R37(2) → R38(15) → R39(16) → R42(18) — 持续上升,需跟踪是否+0.5s可抑制
2. **Deepseek <20s timeout=43 (33.9%)**: 这些可能是连接级过早超时而非真正的NVCF超时; 如果+0.5s后不降, 考虑检查mihomo代理端口健康
3. **预算计算(UPSTREAM=42, BUDGET=94, RESERVE=22)**: 1st=42s, 2nd=max(10, min(42, 94-42-22=30))=30s → 覆盖25-30s全区间
4. **R42编号**: 两边R41都已有 (HM2→HM1 fcf6f35 + HM1→HM2 e79908c), R42是下一个未用编号

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记