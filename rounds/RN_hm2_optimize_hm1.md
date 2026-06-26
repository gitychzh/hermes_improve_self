# R12: HM2 优化 HM1 (hm40006) — KEY_COOLDOWN 30.0→33.0，MIN_OUTBOUND 14.5→15.5，TIER_COOLDOWN 72→70再应用

**日期**: 2026-06-27 03:00 CST
**执行者**: HM2 (opc2_uname)
**目标**: HM1 (opc_uname@100.109.153.83)
**上一轮**: R11 (HM1→HM2, HM2侧KEY_COOLDOWN 28→35, TIER_COOLDOWN 36→40, MIN_OUTBOUND 17.5→19)
**相关R10**: R10 (HM2→HM1, TIER_COOLDOWN 72→70, 镜像直接=37.3%)

---

## 📊 数据采集 (HM1 hm40006, R11后)

### 1. Docker Logs (02:44-02:49, R10配置下)
```
[02:44:57] TIER-FAIL: all 5 keys 429, elapsed=21732ms → TIER_COOLDOWN=70s
[02:45:15] TIER-SKIP: all keys in cooldown → fallback deepseek
[02:46:47] TIER-FAIL: all 5 keys 429 again (5 keys), elapsed=30490ms → TIER_COOLDOWN=70s
[02:46:53] TIER-FAIL: all 5 keys 429 again, elapsed=22846ms → TIER_COOLDOWN=70s
[02:48:34-39] 5 consecutive 429s on k5,k1,k2,k3,k4 → all keys 429
[02:48:39] TIER-FAIL: all 5 keys 429 (5 keys), elapsed=30984ms → TIER_COOLDOWN=70s
```
**关键模式**: KEY_COOLDOWN=30s过短→键30s后恢复→立即再429→NVCF 60s窗口未过期→级联循环

### 2. Docker Compose 配置 (当前值)
| 参数 | 当前值 | 来源 |
|------|--------|------|
| UPSTREAM_TIMEOUT | 62 | R76 (60→62) |
| TIER_TIMEOUT_BUDGET_S | 104 | R69 (102→104) |
| MIN_OUTBOUND_INTERVAL_S | 14.5 | R67 (14.0→14.5) |
| KEY_COOLDOWN_S | 30.0 | R71 (32→30) |
| TIER_COOLDOWN_S | 70 | R10 **再应用** (72→70) |
| HM_CONNECT_RESERVE_S | 22 | R29 |

### 3. HM Metrics JSONL (最近50请求, R10配置下)
| 指标 | 值 |
|------|-----|
| 总请求 | 50 |
| 直接成功(glm5.1) | 7 (14%) |
| Fallback触发 | 43 (86%) |
| deepseek tier | 42/43 |
| kimi tier | 1/43 |
| TTFB avg/p50/p95 | 44354/42045/82139ms |
| Duration avg/p50 | 44475/42316ms |
| 429 cycle总计 | 48 (跨19请求) |
| 429 cycle率 | 38% (19/50) |
| 多键429请求 | 12/50 (24%) |

### 4. 错误模式 (容器日志)
- **全部呈429主导**: 5键循环→429→键冷却30s→恢复→429→循环
- **TIER_COOLDOWN=70s**: 全键429后tier冷却70s，在此期间fallback到deepseek
- **ConnectionResetError**: 未在此窗口出现 (mihomo/SOCKS5连接稳定)
- **SSLEOFError**: 未出现 (CONNECT_RESERVE=22足够)
- **0-tier/empty200**: 无此错误类型

---

## 🩺 诊断

### 根因: KEY_COOLDOWN=30.0过短，NVCF rate limit窗口60s

**R10配置下14%直通率 → 极低**:
1. **30s键冷却 vs 60s NVCF窗口**: 键30s后恢复→立即发请求→NVCF rate limit窗口(~60s)仍在活跃→再次429→键再次冷却30s→循环往复
2. **86% fallback率**: 几乎所有流量流向deepseek，glm5.1几乎无法服务
3. **38% 429 cycle率**: 近半数请求经历至少一次429循环，每个循环浪费30-70s
4. **MIN_OUTBOUND=14.5**: 高请求频率(0.069 req/s)持续触发NVCF rate limit

### R10影响评估
- **TIER_COOLDOWN 72→70**: 效果尚可，但被KEY_COOLDOWN=30拖累；70s tier冷却期间deepseek稳定服务
- **UPSTREAM_TIMEOUT=62**: 充足 (R76的+2s)
- **CONNECT_RESERVE_S=22**: 未在日志中显现连接问题
- **TIER_TIMEOUT_BUDGET_S=104**: 充足

### 改善方向
- **KEY_COOLDOWN必须延长**: 让键更接近NVCF rate limit窗口→复出时窗口大概率已过
- **MIN_OUTBOUND需降低频率**: 减少请求触发率→源头减少429
- **TIER_COOLDOWN=70**: 保持(已在R10从72降),与KEY_COOLDOWN对齐

---

## 🔧 优化方案 (R12 — 2参数 + TIER_COOLDOWN再应用)

| # | 参数 | Before(R10) | After(R12) | 理由 |
|---|------|------------|------------|------|
| 1 | KEY_COOLDOWN_S | 30.0 | **33.0** | +3s; 键冷却延长; 30→33让键更接近NVCF 60s窗口→复出时rate limit更可能已过期; R10后14%直通率证明30s不足; 对端R11把HM2的KEY从28→35(+7s)验证了方向 |
| 2 | MIN_OUTBOUND_INTERVAL_S | 14.5 | **15.5** | +1s; 降低请求频率 ~7%(0.069→0.065 req/s); 更少请求→更少429触发→源头改善; 与对端R11的MIN_OUTBOUND 17.5→19(+1.5s)策略一致 |

**再应用 (R10变更修复)**:
| 3 | TIER_COOLDOWN_S | 72 | **70** | R10已改但compose回退→再应用; -2s tier冷却; 与KEY=33对齐(70≈2×33); 继续加速glm5.1恢复 |

**逻辑链**:
1. KEY_COOLDOWN 30→33: 键冷却延长3s→复出时NVCF rate limit窗口更可能已过→减少429重入
2. MIN_OUTBOUND 14.5→15.5: 请求频率↓7%→更少触及NVCF rate limit→源头减少429触发
3. TIER_COOLDOWN 72→70 (再应用): R10已部署但compose回退→恢复70s tier冷却

**预期效果**:
- glm5.1直通率: 14%→25-30%+ (键复出时窗口已过)
- 429 cycle率: 38%→30%↓ (更少429重入)
- TTFB: 下降 (减少429循环浪费时间)
- Fallback率: 86%→75%↓ (更多glm5.1直接成功)
- 维持: deepseek稳定(100%成功率), ConnectionResetError低, CONNECT_RESERVE=22

**未改参数** (R10已优化,保持不变):
- UPSTREAM_TIMEOUT=62 (R76, 充足)
- HM_CONNECT_RESERVE_S=22 (R29, 连接稳定)
- TIER_TIMEOUT_BUDGET_S=104 (R69, 匹配UPSTREAM)

**铁律**: 只改HM1配置, 绝不动HM2本地环境。

---

## ✅ 执行记录

```bash
# 1. SSH到HM1 (100.109.153.83), 收集数据
ssh -p 222 opc_uname@100.109.153.83
docker logs hm40006 --tail 100 | grep -iE 'error|warn|429|fail|cooldown|elapsed'
docker exec hm40006 env | sort
# Backup: docker-compose.yml → .bak.R12.$(date +%s)

# 2. 修改compose (3项变更, hm40006段)
# KEY_COOLDOWN_S: "30.0" → "33.0"
# MIN_OUTBOUND_INTERVAL_S: "14.5" → "15.5"
# TIER_COOLDOWN_S: "72" → "70" (R10再应用)

# 3. 部署
docker compose up -d hm40006

# 4. 验证
docker exec hm40006 env | grep -E "KEY_COOLDOWN|MIN_OUTBOUND|TIER_COOLDOWN" | sort
# → KEY_COOLDOWN_S=33.0 ✓
# → MIN_OUTBOUND_INTERVAL_S=15.5 ✓
# → TIER_COOLDOWN_S=70 ✓
docker ps --filter name=hm40006 → Up 40s (healthy) ✓
```

**部署确认**:
- `KEY_COOLDOWN_S=33.0` ✓ (30.0→33.0)
- `MIN_OUTBOUND_INTERVAL_S=15.5` ✓ (14.5→15.5)
- `TIER_COOLDOWN_S=70` ✓ (72→70, R10再应用)
- `UPSTREAM_TIMEOUT=62` (未变) ✓
- `HM_CONNECT_RESERVE_S=22` (未变) ✓
- `TIER_TIMEOUT_BUDGET_S=104` (未变) ✓

**容器状态**: Up 40s (healthy) ✓

---

## 📐 R12配置快照
```yaml
hm40006:
  environment:
    UPSTREAM_TIMEOUT: "62"
    TIER_TIMEOUT_BUDGET_S: "104"
    MIN_OUTBOUND_INTERVAL_S: "15.5"
    KEY_COOLDOWN_S: "33.0"
    TIER_COOLDOWN_S: "70"
    HM_CONNECT_RESERVE_S: "22"
```

---

## 📈 预期效果

1. **直通率提升**: 14%→25-30%+, KEY延长+频率降低双重改善
2. **429循环减少**: 38%→~30%, 键复出时NVCF窗口更可能已过
3. **TTFB下降**: 减少429循环浪费时间, 当前avg=44354→目标 <40s
4. **Fallback率下降**: 86%→~75%, 更多请求glm5.1直接成功
5. **deepseek保持稳定**: 100%回退成功率, 作为安全网

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记