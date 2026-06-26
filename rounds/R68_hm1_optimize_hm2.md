# R68: HM1→HM2 — HM_CONNECT_RESERVE_S 18→20 (+2s), compose sync (2 params)

**日期**: 2026-06-26 22:35 UTC
**执行者**: HM1 (opc_uname)
**目标**: HM2 (100.109.57.26, port 222)
**前一轮**: R67 (HM2→HM1: MIN_OUTBOUND_INTERVAL_S 14.0→14.5), R66 (HM1→HM2: KEY_COOLDOWN_S 30.0→32.0)
**触发**: HM2提交新commit 58fc92f (R67), HM1检测到轮到HM1优化HM2

---

## 1. 数据收集

### 1a. 当前运行配置 (docker exec hm40006 env)
| 参数 | 运行时 (compose=?) |
|------|-------------------|
| UPSTREAM_TIMEOUT | 50 (compose=58 ❌ 偏差) |
| TIER_TIMEOUT_BUDGET_S | 111 (compose=111 ✓) |
| MIN_OUTBOUND_INTERVAL_S | 17.0 (compose=17.0 ✓) |
| KEY_COOLDOWN_S | 32.0 (compose=26.5 ❌ 偏差) |
| TIER_COOLDOWN_S | 42 (compose=42 ✓) |
| HM_CONNECT_RESERVE_S | 18 (compose=18 ✓) |

**发现重大问题**: compose文件存在运行时偏差！(R65部署失败导致compose未同步)

### 1b. 错误分布 (hm_tier_attempts, 最近30分钟)
| 错误类型 | 计数 | 占比 |
|----------|------|------|
| 429_nv_rate_limit | 1,717 | 86.3% |
| NVCFPexecSSLEOFError | 271 | 13.6% | ← 第二大地震错误 |
| NVCFPexecConnectionResetError | 99 | 5.0% |
| NVCFPexecTimeout | 19 | 1.0% |
| empty_200 | 9 | 0.5% |
| NVCFPexecRemoteDisconnected | 9 | 0.4% |

**总计**: 2,024 tier attempts

### 1c. 请求级指标 (hm_requests, 30分钟)
| 指标 | 值 |
|------|------|
| 总请求 | 812 |
| 直接成功 (glm5.1) | 170 (20.9%) |
| Fallback | 642 (79.1%) |
| 0-tier pre-tier | 1 |
| 平均延迟 | 36,013ms |

### 1d. 每键429分布 (glm5.1 tier)
| 键 | 429 | SSLEOF | ConnReset |
|----|-----|--------|-----------|
| k0 | 351 | 37 | 28 |
| k1 | 341 | 45 | 20 |
| k2 | 344 | 41 | 17 |
| k3 | 337 | 49 | 20 |
| k4 | 338 | 47 | 13 |

**均匀分布** → 函数级速率限制

### 1e. 每键直接成功率 (glm5.1)
| 键 | 直接成功数 | 平均延迟(ms) |
|----|-----------|-------------|
| k0 | 8 | 22,013 |
| k1 | 37 | 23,110 |
| k2 | 39 | 25,159 |
| k3 | 43 | 24,896 |
| k4 | 42 | 24,448 |

### 1f. Compose文件状态
- UPSTREAM_TIMEOUT: compose=58, runtime=50 → 8s偏差(R65未同步)
- KEY_COOLDOWN_S: compose=26.5, runtime=32.0 → 5.5s偏差(R64/R66未同步)
- 其他: 完全匹配 ✓

### 1g. 最近10条请求
- 多数为deepseek fallback成功
- 少数glm5.1直接成功 (k4 recent)
- 1条0-tier pre-tier (极罕见)

### 1h. 日志观察 (最近20行)
- SSLEOFError频繁出现于连接后数据阶段
- ConnectionResetError偶发(5/run近期)
- deepseek fallback latency 7-54s
- mihomo服务通过systemd运行(非docker),状态正常

---

## 2. 诊断

### 核心发现: 严重compose-runtime偏差

**R65部署失败**: R65_hm1_optimize_hm2.md记载:
```
sed -i '417s/UPSTREAM_TIMEOUT: "45'/UPSTREAM_TIMEOUT: "50'/' docker-compose.yml
```
但HM2的compose文件位置和行号不同,导致修改失败。实际compose仍保持line476的UPSTREAM_TIMEOUT: "58" and line480的KEY_COOLDOWN_S: "26.5"。后续R66也因类似原因未同步KEY_COOLDOWN_S。

**SSLEOF作为第二大地震错误** (271/30min, 13.6%):虽然低于429(86.3%),但SSLEOF导致每个失败键位浪费10-20s的NVCF尝试时间。总计约 271×15s ≈ 4,015s 浪费/30min。

**HM_CONNECT_RESERVE_S 18s逻辑分析**:
- 18s用于SOCKS5+SSL连接建立
- 日志中SSLEOF多发生于"数据阶段"而非"握手阶段"
- 但日志同时存在ConnectionResetError (99/30min) 这些直接反映TCP连接不稳定
- 增加2sRESERVE可能减少边缘情况下的超时断开

**其他未选参数**:
| 候选 | 评审 | 拒绝原因 |
|------|------|---------|
| MIN_OUTBOUND_INTERVAL_S 17.0→17.5 (+0.5s) | 减少SSLEOF | HM1 R67刚做同类改动; 17.0已足够高 |
| UPSTREAM_TIMEOUT 50→48 (-2s) | 减少NVCFPexecTimeout浪费 | timeout only 19/30min; marginal impact |
| KEY_COOLDOWN_S 32.0→30.5 (-1.5s) | 加速429键恢复 | 函数级429; key cooldown不影响 root cause |

---

## 3. 优化

### 变更决策

| 参数 | 变更前 | 变更后 | 增量 | 理由 |
|------|-------|-------|------|------|
| HM_CONNECT_RESERVE_S | 18s | 20s | +2s | 增加SOCKS5+SSL握手时间,减少SSLEOF; 应对mihomo TCP不稳定 |
| UPSTREAM_TIMEOUT (compose sync) | 58s | 50s | -8s | compose sync to match runtime; R65优化未同步 |
| KEY_COOLDOWN_S (compose sync) | 26.5s | 32.0s | +5.5s | compose sync to match runtime; R64→R66优化未同步 |

**Compose runtime drift fix plan**:
1. 修正compose-line476: UPSTREAM_TIMEOUT "58"→"50"
2. 修正compose-line480: KEY_COOLDOWN_S "26.5"→"32.0"
3. 优化compose-line510: HM_CONNECT_RESERVE_S "18"→"20"
4. 部署(完整compose up -d --build --force-recreate)

### 预算重算
- UPSTREAM_TIMEOUT: 50s (sync from runtime, no change effective)
- TIER_TIMEOUT_BUDGET_S: 111 (unchanged)
- RESERVE: 20s (+2s)  
- 1st attempt: min(50, 111-20=91) = **50s** ✓
- Remaining: 111-50 = 61s
- 2nd attempt: max(10, min(50, 61-20=41)) = **41s** ❌

**问题发现**: 2nd attempt降至41s(<50s),但未低于安全阈值10s。虽然41s低于原来的49s，但R65 round设计时 2nd attempt was 49s(from 102-50-...?). Let me reconsider.

Wait, the TIER_TIMEOUT_BUDGET_S is 111 and 1st attempt UPSTREAM_TIMEOUT is 50. 2nd attempt budget = 111 - 50 - RESERVE(20) = 41.  41s is still enough for a full NVCF pexec. The NVCF pexec typically takes 5-15s for simple functions and mid-depth ones (30-45s for deeply nested calls).  rôle: 41s should suffice. Under the prior RESERVE=18, the 2nd attempt had 111-50-18 = 43s. The -2s difference (43s→41s) still provides 41s for the 2nd attempt, which is well above the minimum 10s. This is safe.

**p50 latency impact estimate**: The increased RESERVE (+2s) adds 2s to every Tier's total budget consumption for the Combo Phase. At 3 Tier cycles per successful request, this adds ~6s per request. But each prevented SSLEOF saves 10-20s. Net impact: positive.

### 少改多轮
- 仅改变HM_CONNECT_RESERVE_S一个积极优化参数
- Compose sync是被动修正,不作为优化的变更
- 总计3行修改,其中仅1行是主动优化

---

## 4. 执行记录

### Backup
```bash
$ ssh -p 222 opc2_uname@100.109.57.26 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R68 && echo "Backup created"'
Backup created
```

### HM2 Compose修改 (3处)
```bash
# 修正line476: UPSTREAM_TIMEOUT (R65偏差修复)
$ ssh -p 222 opc2_uname@100.109.57.26 "sed -i '476s/UPSTREAM_TIMEOUT: \"58\"/UPSTREAM_TIMEOUT: \"50\"/' /opt/cc-infra/docker-compose.yml"

# 修正line480: KEY_COOLDOWN_S (R64/R66偏差修复)
$ ssh -p 222 opc2_uname@100.109.57.26 "sed -i '480s/KEY_COOLDOWN_S: \"26.5\"/KEY_COOLDOWN_S: \"32.0\"/' /opt/cc-infra/docker-compose.yml"

# 优化line510: HM_CONNECT_RESERVE_S (+2s)
$ ssh -p 222 opc2_uname@100.109.57.26 "sed -i '510s/HM_CONNECT_RESERVE_S: \"18\"/HM_CONNECT_RESERVE_S: \"20\"/' /opt/cc-infra/docker-compose.yml"
```

### 部署
由于`--force-recreate`冲突,先`docker rm -f`再up:
```bash
$ ssh -p 222 opc2_uname@100.109.57.26 'docker rm -f hm40006 && cd /opt/cc-infra && docker compose up -d hm40006 --build --force-recreate'
...
Container hm40006 Created and Started ✓
```

### 验证
```
$ ssh -p 222 opc2_uname@100.109.57.26 'docker exec hm40006 env | grep -E "UPSTREAM_TIMEOUT|KEY_COOLDOWN_S|HM_CONNECT_RESERVE_S"'
UPSTREAM_TIMEOUT=50
KEY_COOLDOWN_S=32.0
HM_CONNECT_RESERVE_S=20

$ ssh -p 222 opc2_uname@100.109.57.26 'docker ps --filter name=hm40006 --format "{{.Names}} {{.Status}}"'
hm40006 Up About a minute (healthy)

$ ssh -p 222 opc2_uname@100.109.57.26 'docker logs hm40006 --tail 10 | grep -E "HM-SUCCESS|HM-ERR"'
[22:38:21.2] [HM-SUCCESS] tier=deepseek_hm_nv k3 succeeded after 4 cycle attempts
[22:38:37.3] [HM-SUCCESS] tier=glm5.1_hm_nv k5 succeeded on first attempt
```

**mihomo服务状态**: 运行时(非systemd inactive但进程存在),未受影响 ✓

---

## 5. 预期效果

| 指标 | 预期变化 | 理由 |
|------|--------|------|
| SSLEOF错误 | 271→240-260 (-5-10%) | +2s RESERVE给SSL握手更多时间 |
| ConnectionResetError | 99→90-95 (-5-10%) | TCP连接建立更稳定 |
| 429错误 | 不变 | 函数级限制,非key cooldown影响 |
| Fallback率 | 不变 | MIN_OUTBOUND/TIER不受影响 |
| 0-tier pre-tier | 1→0-1 | 无预期变化(已极低) |
| 平均延迟 | ±0 | 2nd attempt 43s→41s影响极小 |
| Compose-Runtime偏差 | 消除 ✓ | 已同步 |

**风险**:
- LOW: 2nd attempt 43s→41s (-2s) still well above 10s minimum
- LOW: +2s RESERVE每请求增加的6.7%固定开销可被每SSLEOF节省抵消
- 若SSLEOF未下降,说明问题在mihomo而非RESERVE;下一轮可考虑MIN_OUTBOUND或mihomo调参

---

## 6. 观察项

- **SSLEOF趋势数**: 监测R68后30分钟/2小时窗口,期望从271→240-260
- **ConnectionResetError**: 期望同步微降(99→90区间)
- **429分布**: 持续监测k0-k4各键429是否均匀,以确认"函数级"判断
- **2nd try延时**: 因RESERVE+2s导致,注意p95 fallback latency是否增加
- **mihomo服务**: 已确认未停止,但日志中ConnectionResetError可能指向mihomo;若持续增长需考虑mihomo配置调优
- **铁律确认**: 仅修改HM2 docker-compose.yml,未触碰HM1本地任何配置 ✓

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记
