# R509 (HM1→HM2): HM_PEXEC_TIMEOUT_FASTBREAK 2→3 — 拥塞期多给1个key尝试机会, 降低 correlated failure 触发的 fast-break 率

**轮次**: R509
**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**日期**: 2026-07-01 19:19 UTC (CST 03:19 次日)
**类型**: 单参数收紧 (FASTBREAK +1)
**Commit**: 本commit

## 0. 时区与host标识

- 对端HM2 host_machine标识=`opc2sname`。
- NVCF function ID: 6155636e-8ca8-4d9a-b4e5-4e8d231dfd3f (z-ai/glm-5.1)。

## 1. 改前基线 (HM2 对端, R508后, host_machine=opc2sname)

### 1a. 容器env (8参数+5 URL, 实测grep)
```
UPSTREAM_TIMEOUT=48
TIER_TIMEOUT_BUDGET_S=110
MIN_OUTBOUND_INTERVAL_S=1.5
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=22
HM_SSLEOF_RETRY_DELAY_S=1.0
HM_PEXEC_TIMEOUT_FASTBREAK=2   # ← 改前
HM_CONNECT_RESERVE_S=5
HM_MIN_ATTEMPT_TIMEOUT_S=8
HM_NV_PROXY_URL1=http://host.docker.internal:7894
HM_NV_PROXY_URL2=http://host.docker.internal:7894  # R508已改
HM_NV_PROXY_URL3=
HM_NV_PROXY_URL4=
HM_NV_PROXY_URL5=http://host.docker.internal:7896
```

### 1b. restart后7min窗口基线 (docker logs since ~19:11 restart)

| 指标 | 数值 |
|------|------|
| 总请求 (HM-REQ) | 17 |
| 成功 (HM-SUCCESS) | 14 |
| 请求级失败 (502/ALL-TIERS-FAIL) | 3 |
| 成功率 | 82.4% |

### 1c. 3次 all-tiers-fail 的根因 (tail 200 逐条溯源)

| 时间 | 第1attempt | 第2attempt | fast-break | 触发elapsed |
|------|-----------|-----------|------------|-------------|
| 19:13:03 | k1(timeout@7894, 49s) | k2(timeout@7894, 25s) | 2 consecutive NVCFPexecTimeout | 105s |
| 19:15:06 | k1(timeout@7894, 48s) | k2(timeout@7894, 49s) | 2 consecutive NVCFPexecTimeout | 97s |
| 19:16:44 | k2(timeout@7894, 48s) | k3(timeout@直连, 48s) | 2 consecutive NVCFPexecTimeout | 97s |

**核心发现: 100% 的 all-tiers-fail 由 FASTBREAK=2 触发**。非 budget break（BUDGET=110, 2×48=96, 剩余14s>MIN_ATTEMPT=8，budget 本可放行第3 attempt）。

19:16 的 case 尤为关键：k2@7894 timeout 后 k3@直连也 timeout，但 **同时间段后续请求 k3@直连成功**（19:17:28），说明 NVCF 拥塞是瞬时的，第3 attempt 本有机会把时间错开从而成功。

### 1d. 代理拥塞时段 (19:12–19:16) vs 恢复期 (19:17+)

- **拥塞期**: k1@7894 连续 timeout, k2@7894 连续 timeout, k3@直连 偶发 timeout, k5@7896 SSLEOF→retry timeout。
- **恢复期**: k3@直连 (19:17:28, ~44s first attempt → SUCCESS), k4@直连 (19:17:53, ~23s), k5@7896 (19:18:03, ~9s), k2@7894 (19:18:41, ~9s), k1@7894 ongoing。

**这表明 19:12–19:16 是 NVCF function 侧的临时性 pexec 拥塞窗口（服务器端，非代理独有）**。Correlation: k1/k2 共走 7894 时 correlated failure 概率高，但即使 k3 直连也在 19:16 被波及。

## 2. 优化计划

### 2a. 候选方案评估

| 候选 | 数据支撑 | 风险 | 裁决 |
|------|----------|------|------|
| FASTBREAK 2→3 | 3/3 all-fail 由 2-consecutive-timeout 触发; 恢复期 per-key 成功率高; 第3 attempt 延时>10s 可触发 | 失败请求多等~48s(但总时间仍在BUDGET=110内) | **执行** |
| FASTBREAK 2→5 | R384曾3→5但被打回; 5次连续timeout会让失败请求等~240s, 违背"更快请求" | 高(浪费严重, 与R506反向) | 不执行 |
| k1/k2 分代理 | 7894+7896是仅有的端口; k5已占7896 | 无可用新端口 | 不可行 |
| k2→直连 | R508刚把k2从直连→7894解决429; 回退会复现429 | 中(429劣化) | 不执行 |
| UPSTREAM 48→42 | 拥塞期是真慢(~48s卡边), 收紧只会增加timeout, 不减少拥塞 | 高(误杀慢成功) | 不执行 |

### 2b. 最终计划

只做 **1 个参数改动**：

```yaml
HM_PEXEC_TIMEOUT_FASTBREAK: "2" → "3"
```

- 核心理由: 当前所有 all-tiers-fail 由 FASTBREAK=2 触发，非 budget/timeout 耗尽。多给 1 个 key 尝试机会，可将 correlated/瞬时拥塞下的 "必败" 转为 "有机会翻盘的边缘 case"。
- 风险对冲: fast-break 是 safety valve，3 仍能在 3×48s=144s 前截断（但在 BUDGET=110 下 3×48s>110，实际 budget 会先截断；fast-break 从 2→3 仅影响 "2 次 timeout 且 budget 仍够" 的场景，即当前所有失败场景）。
- 对"更快请求"的影响: 失败请求 release 时间从 ~96s→~144s（若第 3 attempt 也 timeout）。但若第 3 attempt 成功，则总时间 96+~10s=106s，远低于重新发起整个新请求（等 MIN_OUTBOUND 1.5s + 新请求流程）。

## 3. 改前改后实测

### 3a. 执行

```bash
# HM2 (opc2sname) 执行 — 仅改 hm40006 compose, 未碰 mihomo
sudo sed -i 's/HM_PEXEC_TIMEOUT_FASTBREAK: "2"/HM_PEXEC_TIMEOUT_FASTBREAK: "3"/g' /opt/cc-infra/docker-compose.yml
cd /opt/cc-infra && sudo docker compose up -d hm40006
# Output: Container hm40006 Recreated/Started
```

### 3b. 改后验证

- env 确认: `HM_PEXEC_TIMEOUT_FASTBREAK=3` ✓
- /health=200 OK, hm_num_keys=5 ✓
- 改后即时 success (容器启动后 1min 内):
  - `[19:19:40.0] k2@7894 → SUCCESS on first attempt (3.6s)` ✓
  - `[19:19:44.5] k3@直连 → SUCCESS on first attempt` ✓
- mihomo 进程未中断 (`pid=24528`, uptime 无变化) ✓

## 4. 数据诚实与局限

- 本轮回的改后数据窗口太短（~2min），不足以做统计结论。FASTBREAK=3 的长期效果（all-fail 率是否下降）需下轮（HM2 优化 HM1）复核 30min+ 窗口。
- 拥塞期 k3@直连 也 timeout，说明 19:12–19:16 的问题有 NVCF server-side 因素；FASTBREAK=3 只能让系统在 server-side 瞬时拥塞时多 1 次救命机会，不能根除 server-side 拥塞。
- 若下轮数据中出现 "3 consecutive timeout → fast-break" 频繁触发（暗示第 3 attempt 也必败），则 fast-break=3 的收益有限，应考虑回调到 2 或尝试其他方向（如 tier budget 调整）。

## 5. 铁律检查

- [x] 只改 HM2 对端配置 (`/opt/cc-infra/docker-compose.yml` 第 482 行), 未改 HM1 本地源码/配置
- [x] 未停止/重启/kill mihomo 服务 (`pid=24528` 持续运行; 仅 `docker compose up -d hm40006` recreate 代理容器)
- [x] 改前必有数据: restart 后 7min docker logs + 3 次 all-fail 逐条溯源 + 拥塞/恢复两段对比
- [x] 少改多轮: 仅改 FASTBREAK 1 个参数
- [x] 每句可溯源: 全部来自 `docker logs hm40006` 和 `docker exec hm40006 env` 实测, 无编造
- [x] 改后重启 + /health + env 三重验证
- [x] 不跨 profile 操作 (技能/插件/cron/memories 均未触碰)

## 6. 给下轮 (HM2 优化 HM1) 的接力信息

- HM2 当前配置: BUDGET=110 / UPSTREAM=48 / FASTBREAK=3 / MIN_OUTBOUND=1.5 / RESERVE=5 / MIN_ATTEMPT=8 / KEY_CD=38 / TIER_CD=22。
- **验证重点**: 采 30min+ 窗口统计 `PEXEC-FASTBREAK` 触发次数; 改前是 3 次/7min(≈43% 失败由 fast-break 贡献)，改后看此比例是否下降。
- **另一关注点**: k1+k2 共走 7894，若 7894 拥塞 correlated failure 持续，可分 proxy 方案缺失(仅 7894/7896 两端口)。如果 429 不是问题，建议评估把 k1 或 k2 之一改直连或均改 7896，但需监测 429 率。
- mihomo (7894/7896) 健康度需观察: 拥塞期 k5@7896 也有 SSLEOF+timeout，说明代理层在拥塞期同样受压。
- HM1 侧 (deepseek) 请按 CC 清单 HM1 节执行; HM2 侧当前所有单参数已进入微调阶段。

## ⏳ 轮到HM2优化HM1
