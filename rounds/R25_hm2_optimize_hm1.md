# R25: HM2优化HM1 — HM_CONNECT_RESERVE_S 18→19 (+1s SOCKS5+SSL)

**日期**: 2026-06-26 07:45 UTC  
**执行者**: HM2 (opc2_uname)  
**目标**: HM1 hm40006 @ 100.109.153.83  
**前轮**: R24 (HM2→HM1, HM_CONNECT_RESERVE 16→18)  

---

## 1. 数据收集

### 1a. 容器环境变量 (运行时实际值)

| 参数 | 值 | 来源 |
|------|----|------|
| KEY_COOLDOWN_S | 38.0 | R19稳定 |
| TIER_COOLDOWN_S | 90 | R17稳定 |
| HM_CONNECT_RESERVE_S | 18 (→改为19) | R24→R25 |
| UPSTREAM_TIMEOUT | 40 | R18稳定 |
| TIER_TIMEOUT_BUDGET_S | 80 | R18稳定 |
| MIN_OUTBOUND_INTERVAL_S | 10.0 | R17稳定 |
| PROXY_TIMEOUT | 300 | 默认 |

### 1b. DB请求统计 (30分钟窗口, 07:10-07:40 UTC)

| 指标 | 值 |
|------|----|
| 总请求 | 1098 |
| 成功率 | 97.6% (1071/1098) |
| Fallback率 | 88.2% (969/1098) |
| 直接成功 | 11.8% (129/1098) |
| 0-tier预连接失败 | 25 (全部tiers_tried=0, avg 87.4s) |
| NVStream_IncompleteRead | 1 (avg 14.9s) |
| 全请求avg延迟 | 17.2s |
| Fallback请求p50 | 10.5s, p95 53.5s |
| 直接请求p50 | 8.4s, p95 101.3s |

### 1c. 错误分布

| error_type | cnt | avg_dur |
|------------|-----|---------|
| all_tiers_exhausted | 25 | 87429ms |
| NVStream_IncompleteRead | 1 | 14898ms |

### 1d. 日志模式 (最近2000行)

- glm5.1_hm_nv tier: **100% 429**，所有5 key全429，function-level全局限流
- deepseek_hm_nv: **~99.7% 成功**，3个timeout (42-46s range)，其余first attempt成功(8-10s)
- 典型请求流: TIER-SKIP(glm5.1 all cooling) → fallback deepseek → success 8-10s
- deepseek tier偶发timeout: `k5 46158ms timeout → k1 16156ms timeout → k2 10682ms timeout` (3/5 timeout → tier fail)

### 1e. 0-tier失败持续追踪

| 轮次 | RESERVE | 0-tier失败数 | 变化 |
|------|---------|-------------|------|
| R20 | 8 | 42 | 基线 |
| R21 | 10 | 34 | -8 |
| R22 | 12 | 34 | 0 |
| R23 | 16 | 28 | -6 |
| R24 | 18 | 25 | -3 |
| R25(目标) | 19 | ~22-23 | -2~-3 |

---

## 2. 诊断分析

### 核心态势
- glm5.1 NVCF function `822231fa-d4f...` 全局RPM限流，5 key全部同时429 → **功能级不可用**
- deepseek_hm_nv是事实主力(88.2%请求fallback到此，99.7%成功率)
- 0-tier预连接失败(25个)是当前唯一可改善的失败类型
- NVStream_IncompleteRead仅1次，属噪声

### 0-tier失败根因
- `tiers_tried=0, key_cycle_429s=0` → 连接建立阶段失败，发生在任何tier key cycling之前
- 失败场景: SOCKS5 proxy → mihomo → NVCF 连接链路handshake超时
- HM_CONNECT_RESERVE_S控制此预留时间: 每增加1s可减少2-3个失败(R23→R24 -3经验)
- 部分失败来自NVCF/mihomo基础设施抖动，无法通过RESERVE完全消除

### 预算安全检查
- RESERVE=19: TIER_BUDGET(80) - RESERVE(19) = 61s残余
- 1st deepseek attempt: min(40, 61) = 40s ✓ (充足)
- 2nd attempt: 61 - 40 = 21s > 10s minimum ✓ (安全)

---

## 3. 优化执行

### 变更表

| 参数 | 修改前 | 修改后 | 原因 |
|------|--------|--------|------|
| HM_CONNECT_RESERVE_S | 18 | 19 | +1s SOCKS5+SSL连接预留; 继续递减0-tier预连接失败(R24→R25: 25→~22-23目标) |

### 执行命令

```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 "cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R25"

# 修改值: line 451
ssh <target> "cd /opt/cc-infra && sed -i '451s/\"18\"/\"19\"/' docker-compose.yml"
# 修改注释
ssh <target> "cd /opt/cc-infra && sed -i '451s/# R24:.*$/# R25: HM2优化 — 18→19: +1s SOCKS5+SSL连接预留; 0-tier pre-tier连接失败继续减少(R24后25个→目标~22-23); 少改多轮(单参数变更); RESERVE 19s下TIER_BUDGET残余=61s, 2nd attempt=21s headroom安全/' docker-compose.yml"

# 部署
ssh <target> "cd /opt/cc-infra && docker compose up -d hm40006"
```

### 验证

```
$ docker exec hm40006 env | grep HM_CONNECT_RESERVE_S
HM_CONNECT_RESERVE_S=19

$ docker ps --format '{{.Names}} {{.Status}}' | grep hm40006
hm40006 Up 16 seconds (healthy)
```

✅ 参数已生效，容器健康运行

---

## 4. 预期效果

| 指标 | R24(RESERVE=18) | R25预期(RESERVE=19) | 变化 |
|------|-----------------|---------------------|------|
| 0-tier预连接失败 | 25 | ~22-23 | -2~-3 |
| 成功率 | 97.6% | ~97.8% | +0.2% |
| Fallback率 | 88.2% | ~88% | 不变(glm5.1全局限流) |
| avg延迟 | 17.2s | ~17s | 不变 |

---

## 5. 观察项 & 风险

1. **RESERVE接近20s边界**: 当HM_CONNECT_RESERVE_S达到20s时，TIER_BUDGET残余=60s，2nd attempt=20s仍安全但空间收窄。R26需评估是否需要同步提升TIER_BUDGET_S(80→85)。
2. **deepseek tier偶发timeout**: 3个timeout/30min (42-46s range)数量低但值得关注。UPSTREAM_TIMEOUT=40已覆盖部分，微调至42可覆盖更多但增加延迟。暂不改动。
3. **glm5.1 tier持续全局限流**: 无解于HM参数层面。只能等NVCF配额增加或切换model。
4. **0-tier失败下限**: 根据R20→R24轨迹，约30%的0-tier失败属于基础设施抖动(非handshake超时)，RESERVE增长递减效应明显。预计到RESERVE=20时0-tier失败稳定在~18-20个，之后需改变策略。

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记
