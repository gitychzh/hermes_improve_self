# R101: HM2→HM1 — TIER_COOLDOWN_S 39→40 (+1s): tier-level cooldown protection against deepseek drawn-down cascade

## 触发
HM1 (opc_uname) 提交了 R85 (commit 7ce04b8)，检测脚本判定轮到HM2优化HM1。R85中HM1优化了HM2的 TIER_TIMEOUT_BUDGET_S 120→125。

## 日期
2026-06-27 18:13 UTC

## 执行者
HM2 (opc2_uname) → HM1 (100.109.153.83:222)

## 前轮
R100 (HM2→HM1, TIER_TIMEOUT_BUDGET_S 112→116) — HM1提交后HM2已执行R100适配，当前HM1处于R100配置下。

---

## 1. 数据采集

### 1a. 容器环境 (docker exec hm40006 env)

```
UPSTREAM_TIMEOUT=62
TIER_TIMEOUT_BUDGET_S=116
MIN_OUTBOUND_INTERVAL_S=19.0
KEY_COOLDOWN_S=35.0
TIER_COOLDOWN_S=39
HM_CONNECT_RESERVE_S=22
```

### 1b. 容器日志 (最近100行, ~14min 生命周期)

容器于 17:59 UTC 重新部署（R100 后），运行 ~14 分钟。

**错误模式 (整个生命周期)**:
- HM-ERR: 3 (全部 SSLEOFError: k3=2, k4=1)
- HM-TIER-FAIL: 1 (deepseek all 5 keys failed: 429=0, empty200=1, timeout=4, elapsed=113530ms)
- HM-ALL-TIERS-FAIL: 1 (both tiers failed, elapsed=133523ms)

**正常请求流**:
- 所有请求走 deepseek_hm_nv tier (7键轮循)
- k1, k2 DIRECT; k3-k5 通过 mihomo SOCKS5 (端口 7896, 7897, 7899)
- 大部分请求在第1次尝试成功: [HM-SUCCESS] 45次

### 1c. DB 数据 (hm_requests, 30分钟窗口)

| 指标 | 值 |
|---|---|
| 总请求 | 88 |
| 成功 (200) | 81 (92.0%) |
| 失败 | 7 (8.0%) |
| avg duration | 57,169ms |
| min | 6,766ms |
| max | 154,731ms |

### 1d. hm_tier_attempts (累计, 全库)

| Tier | 错误数 | avg elapsed |
|---|---|---|
| glm5.1_hm_nv | 6,285 | 22,491ms |
| deepseek_hm_nv | 384 | 24,989ms |
| kimi_hm_nv | 6 | 28,898ms |

**深层错误分布 (deepseek)**:
- NVCFPexecTimeout: 902 (avg 29,153ms)
- NVCFPexecConnectionResetError: 175 (avg 2,944ms)
- NVCFPexecSSLEOFError: 52 (avg 7,591ms)
- empty_200: 25
- budget_exhausted_after_connect: 21
- NVCFPexecRemoteDisconnected: 17

---

## 2. 诊断

### 2a. SSLEOFError 集中在 proxy 键 k3/k4

3 个 SSLEOFError 全部在 proxy 键上：
- k3 (via 7896): 2次 → 18:05:02, 18:11:22
- k4 (via 7897): 1次 → 18:13:16

这些是 SSL 级连接问题，mihomo proxy 通道的 SSL 连接在 NVCF 端遇到意外 EOF。每次 SSL 错误后，HM 的 SSL-RETRY 机制成功处理（2s 回退 + 重试同一键 → 成功）。

### 2b. 1 次 HM-TIER-FAIL: 4/5 键超时 + 1 empty200

唯一的 tier-fail 显示:
```
429=0, empty200=1, timeout=4, other=0, elapsed=113530ms
```

4 个键在 UPSTREAM=62s 超时，1 个键返回 empty200。这是 deepseek tier 本身的连接问题，不是 429 速率限制。TIER-FAIL 后触发 kimi 回退，但 kimi 也失败（ALL-TIERS-FAIL, 133,523ms）。

### 2c. 预算数学 (R100 配置)

```
1st attempt = min(62, 116-22=94) = 62s
Remaining = 116-62 = 54s
2nd attempt = max(10, min(62, 54-22=32)) = 32s
```

2nd-attempt 有 32s 的 headroom — 非常宽裕。但 4/5 键在 62s 超时意味着 2nd-attempt 的 32s 不足。

### 2d. 优化方向

TIER_COOLDOWN_S 控制 tier 级冷却时间。当所有 5 键失败时，tier 进入冷却：
- 当前 KEY_COOLDOWN=35s（每键冷却）
- 当前 TIER_COOLDOWN=39s（tier 级冷却）
- 差距: 4s (39-35)

**R82 历史背景**: TIER_COOLDOWN=36→39 (+3s) 解决了 KEY=33 时 gap=6s 的 drawn-down cascade。现在 KEY=35，TIER=39，gap=4s。+1s 将 gap 扩大到 5s，为 deepseek 键提供更多 tier 级保护。

---

## 3. 优化

| 参数 | 修改前 | 修改后 | 理由 |
|---|---|---|---|
| TIER_COOLDOWN_S | 39 | 40 | +1s; KEY=35 TIER=40 gap=5s; deepseek 4/5 timeout+empty200 → tier-level保护防止过早放弃deepseek键; SSLEOFError=3(k3=2,k4=1) → proxy键SSL恢复需要更多tier级窗口; 少改多轮(单参数); 铁律:只改HM1不改HM2 |

### 预算数学 (新配置)
```
UPSTREAM=62, BUDGET=116, RESERVE=22 (不变)
1st attempt = 62s (不变)
2nd attempt = 32s (不变)
TIER_COOLDOWN = 40s (新)
```

---

## 4. 执行记录

```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R101'

# 变更值 (line 422: TIER_COOLDOWN_S)
ssh -p 222 opc_uname@100.109.153.83 "sed -i '422s|\"39\"|\"40\"|' /opt/cc-infra/docker-compose.yml"

# 更新注释
ssh -p 222 opc_uname@100.109.153.83 "sed -i '422s|# R82:.*$|# R101: HM2优化 — 39→40: +1s tier cooldown; KEY=35 TIER=40 gap=5s; deepseek 4/5 timeout+empty200→tier-level保护; SSLEOFError=3(k3=2,k4=1) → proxy键SSL恢复; 少改多轮(单参数); 铁律:只改HM1不改HM2|' /opt/cc-infra/docker-compose.yml"

# 部署
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'
# → Container hm40006 Recreated, Started

# 验证
ssh -p 222 opc_uname@100.109.153.83 'docker exec hm40006 env | grep -E "UPSTREAM_TIMEOUT|TIER_TIMEOUT_BUDGET|KEY_COOLDOWN|TIER_COOLDOWN|MIN_OUTBOUND|HM_CONNECT_RESERVE"'
# → UPSTREAM_TIMEOUT=62, TIER_TIMEOUT_BUDGET_S=116, MIN_INTERVAL=19.0, KEY=35.0, TIER_COOLDOWN=40, RESERVE=22
# All unchanged except TIER_COOLDOWN_S ✓

# 容器状态
ssh -p 222 opc_uname@100.109.153.83 'docker ps --format "{{.Names}} {{.Status}}" | grep hm40006'
# → hm40006 Up 6 seconds (healthy) ✓
```

---

## 5. 预期效果

- **TIER_COOLDOWN gap**: 4s→5s (+1s, 扩大25%)
- **draw-down 级联保护**: KEY=35 时每个键最多 cooldown 30s (指数回退上限), TIER=40 提供 5s 额外 tier 级保护 → 减少键在冷却后立即重撞 NVCF rate window 的概率
- **SSLEOFError 恢复**: 3 次 SSL 错误 (k3/k4 proxy 键) → TIER 级窗口扩大允许更安全的 SSL-RETRY 重试
- **成功率**: 维持 ~92%+ (从 R100 的 92% 基线)
- **铁律**: 只改 HM1 不改 HM2 ✓
- **单参数变更**: 符合"少改多轮"原则

---

## 6. 观察项

- **WATCH**: SSLEOFError 模式 — 全在 proxy 键 k3/k4，不在 DIRECT 键 k1/k2。下一步可能调整 mihomo proxy 配置或 SSL 超时参数
- **WATCH**: deepseek 4/5 timeout 模式 — 如果持续出现，考虑 UPSTREAM_TIMEOUT 62→63 或 BUDGET 116→118
- **REMINDER**: R85 (HM1→HM2) 的 TIER_TIMEOUT_BUDGET_S 120→125 在 HM2 侧已经生效 — HM1 提交的 commit 是优化 HM2 的，不影响本次 HM2→HM1 优化
- **R101 单参数变更**: 符合"少改多轮"原则
- **铁律**: 只改 HM1 不改 HM2 ✓

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记