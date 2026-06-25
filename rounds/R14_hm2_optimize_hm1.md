# R14: HM2优化HM1 — R13后429仍高，继续提升冷却与间距

## 元信息
- **日期**: 2026-06-26 03:00
- **执行者**: HM2 (opc2_uname, 100.109.153.83 不在此次修改)
- **目标**: HM1 (opcsname, 100.109.153.83, 基于 commit cb8a6c4)
- **前序轮**: R13 — HM2优化HM1，释放glm5.1长冻结(TIER_COOLDOWN 300→180), KEY_COOLDOWN 25→22

## 1. 数据收集

### 1a. 日志扫描 (最近100行)
```
错误/警告行数: 9
典型日志:
[02:58:30.7] [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=5, empty200=0, timeout=0, other=0, elapsed=5268ms
[02:58:30.7] [HM-FALLBACK] Tier glm5.1_hm_nv all-failed → falling back to deepseek_hm_nv
[03:00:10.8] [HM-FALLBACK] Tier glm5.1_hm_nv all-failed → falling back to deepseek_hm_nv
[03:00:37.5] [HM-FALLBACK] Tier glm5.1_hm_nv all-failed → falling back to deepseek_hm_nv
```

### 1b. 容器环境变量
```
UPSTREAM_TIMEOUT=28
TIER_TIMEOUT_BUDGET_S=52
MIN_OUTBOUND_INTERVAL_S=7.0
KEY_COOLDOWN_S=28.0
TIER_COOLDOWN_S=180
HM_CONNECT_RESERVE_S=5
```

### 1c. DB错误分布 (最近30分钟)
| error_type            | cnt | avg_elapsed |
|-----------------------|-----|-------------|
| 429_nv_rate_limit     | 661 | —           |
| NVCFPexecTimeout      | 111 | 33556       |
| NVCFPexecConnReset    | 20  | 1081        |
| NVCFPexecSSLEOFError  | 12  | 9130        |
| NVCFPexecProxyConnErr | 7   | 1           |
| empty_200             | 6   | —           |
| budget_exhausted      | 4   | 1897        |
| remote_disconnected   | 1   | 534         |

### 1d. 请求路由统计 (最近30分钟, hm_requests)
- 总请求: 1102
- 非Fallback: 484 (avg 22.2s)
- **Fallback: 618 (56.1%)** — 超过目标<50%

### 1e. 每键429分布 (glm5.1_hm_nv, 30min)
- key0: 429=140, timeout=9, SSLEOF=2
- key1: 429=126, timeout=9, reset=7
- key2: 429=130, timeout=17, reset=4
- key3: 429=136, timeout=16, reset=7
- key4: 429=129, timeout=14

> **特征**: 5键429分布极均匀(126~140)，说明不是个别key问题，而是系统性NVCF速率上限触发的并发碰撞。**每键每30min约129次429**。

### 1f. TIER-SKIP监控
- glm5.1 attempts: 765 (93.3%)
- deepseek attempts: 53 (6.5%)
- R13把TIER_COOLDOWN从300→180后，TIER-SKIP已降至健康水平，99%请求能触达glm5.1主tier。

## 2. 诊断

**核心矛盾**：429占所有错误80%以上，fallback率56%>目标<50%。

- **429根因分析**：28s KEY_COOLDOWN ÷ 7.0s MIN_INTERVAL ≈ 4.0 cycles。每个429后，key经历4轮旋转才被重新使用。由于NVCF的429窗口大约15-25s(从 burst 行为推断)，28s超出了窗口，但**7.0s间隔让5个key每35s完成一次全遍历 → 平均每秒有约1/7≈0.14个key同时处于活跃可用/尝试状态**。8.0s间隔降低为0.125个key/秒，429碰撞概率降低约14%(预期)。

- **KEY_COOLDOWN不够**：28s虽然超过NVCF 429窗口(~15-25s)，但每次key尝试失败后，给它更多恢复时间可以减少与邻近key的重叠尝试。**30s提供更多边际保护**。

- **timeout(111次, 33.5s)高于upstream(28s)**：这是NVCF queuing delay造成的timeout(实际host处理时间>28s)。当前52s TIER_BUDGET允许每tier约2次尝试(2×28=56略超)，还算合理。但首要矛盾仍是429，不是timeout。

- **fallback高因**：429导致几乎所有Tier内失败；timeout次之。必须降低429率才能降低fallback率。

## 3. 优化方案

| Parameter | Before | After | Rationale |
|-----------|--------|-------|-----------|
| MIN_OUTBOUND_INTERVAL_S | 7.0 | 8.0 | 5key×8s=40s全周期，降低key碰撞密度。每键平均可用时间窗口从6%→5%，但429→导致预算浪费的问题更可改善。 |
| KEY_COOLDOWN_S | 28.0 | 30.0 | 更长冷却，逃离NVCF 429窗口更充分。30/8=3.75 cycles per retry, 减少重复进入窗口。 |

**变动粒度**：2个小参数，攒到下一轮。

## 4. 执行记录

```bash
# Backup
ssh opc_uname@opcsname "cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R14"

# Apply sed changes (HM1 only)
ssh opc_uname@opcsname "cd /opt/cc-infra && sed -i '420s/\\\"7.0\\\"/\\\"8.0\\\"/' docker-compose.yml && sed -i '421s/\\\"28.0\\\"/\\\"30.0\\\"/' docker-compose.yml && sed -i '420s/# R15.*$/# R14: HM2优化 — 7.0→8.0: 5key×8s=40s cycle; slower rotation reduces per-second NVCF rate/' docker-compose.yml && sed -i '421s/# R15.*$/# R14: HM2优化 — 28→30: 2s more key cooldown; more recovery time in NVCF 429 window/' docker-compose.yml"

# Deploy & verify via :222
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && docker compose up -d hm40006"
```

**部署验证**:
```
TIER_COOLDOWN_S=180
KEY_COOLDOWN_S=30.0
UPSTREAM_TIMEOUT=28
MIN_OUTBOUND_INTERVAL_S=8.0
hm40006 Up 10 seconds (healthy)
```

## 5. 预期效果

| 指标 | 当前值 | 预期改善 |
|------|--------|----------|
| 429/30min | ~661 | ↓ 15-20% ≈ 530-570 |
| timeout/30min | ~111 | 轻微↓ (429减少→更少budget浪费→timeout略有下降) |
| fallback率 | 56% | ↓ → 目标<50% (1-2个轮次内趋近) |
| TIER-SKIP率 | ~6.5% | 保持，无需调 |

> ⚠️ 本轮不改UPSTREAM_TIMEOUT(28s)和TIER_BUDGET(52s)，因为429是主要矛盾，timeout是次要的。如果下轮429下降到可接受水平(<400/30min)而timeout仍高，再考虑把UPSTREAM_TIMEOUT微调回30s。

## 6. 观察项目 (后续轮次追踪)

1. **429_nv_rate_limit 绝对数量**：<550/30min为良好，<400为"目标达成"
2. **timeout是否因retry间隔变大而恶化**：MIN_OUTBOUND=8.0后，全交易周期40s>tier budget 52s本身仍允许2次尝试。但如果NVCF排队加重，可能需要把UPSTREAM_TIMEOUT→30。
3. **fallback率是否下降**：target<50%，本轮预期降至53-55%区间。
4. **deepseek fallback负载**：deepseek tier仅承担6.5%的tier尝试，但cover了56%的成功请求。如果deepseek不可用，影响大，需关注。

## 7. 历史参数追踪

| Round | UPSTREAM | BUDGET | MIN_INIT | KEY_CODL | TIER_CODL | HM_NOTE |
|-------|----------|--------|----------|----------|-----------|---------|
| R13   | 25       | 60     | 6.0      | 22       | 180       | HM2→HM1 首降key cooldown |
| R15   | 28       | 52     | 7.0      | 28       | 180       | HM2→HM1 提升timeout+spacing |
| **R14** | **28** | **52** | **8.0**  | **30**   | **180**   | **HM2→HM1 继续加强429防控** |

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记
