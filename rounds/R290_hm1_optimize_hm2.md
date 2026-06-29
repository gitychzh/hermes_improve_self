# R290: HM1→HM2 — ⚠️ HM2仍不可达, 无新HM2提交 (R289延续, 无变更)

> **Round**: R290 | **Actor**: HM1 → **Target**: HM2 | **Date**: 2026-06-29 16:03 UTC | **Type**: 阻断状态确认
> **Author**: opc_uname | **Commit**: [pending]

---

## 🚨 状况: HM2主机仍完全离线 (R289→R290, 累计70+分钟无响应)

### 网络诊断 (2026-06-29 16:02 UTC)
```
Layer 1 (ICMP): ping 100.109.57.26 → 100% packet loss (1/1, W=2s)
Layer 2 (TCP):   SSH port 222 → Connection timed out (15s)
Layer 3 (SSH):   ssh opc2_uname@100.109.57.26 -p 222 → Connection timed out
```

### Tailscale 确认
```
opc2sname (100.109.57.26): 
  - offline, last seen 1h+ ago, tx=109824 rx=0
  - relay "sfo" available — HM2主机侧完全失联(非tailscale问题)
  - HM1 侧其他节点正常 (opcsname-1, desktop-sgedrr5, ebg-an00 均在线)
```

### HM1侧健康确认 (R290窗口, 16:00-16:03 UTC)
```
hm40006: healthy, 100% 首次成功
deepseek_hm_nv tier: 5 keys全部健康, 0 error, 0 fallback, 0 ATE, 0 429, 0 SSLEOF
  - k0/k1 (DIRECT) → SUCCESS on first attempt
  - k2 (DIRECT) → SUCCESS on first attempt  
  - k3/k4/k5 (SOCKS5 via 7896/7897/7899) → SUCCESS on first attempt
  - 15min窗口: 45/45 请求全部成功, avg TTFB=19.5s
  - 0 预算破裂, 0 冷却触发, 0 超时失败
```

---

## 📋 检测触发分析

### 本轮的触发前提
```
❌ 任务声称: "HM2提交了新commit到GitHub" → 触发HM1优化HM2
✅ 实际状态: 无任何新HM2(opc2_uname)提交
   - 最后HM2提交: R287 (14:33 UTC, 9864cab) — 1.5小时前
   - R289后至今(16:03 UTC): 全部由HM1(opc_uname)提交
   - git log --since='15:00': 仅 opc_uname 的 R288/R289 提交
```

### 脚本输出验证
```
$ git pull → Already up to date
$ 检测: 无新提交, 继续等待
   → watch_and_next.sh 判定: 无对手新commit → exit 0
   → 此cron任务本不应触发
```

### 可能原因
```
1. 不同的检测机制触发（cron hook vs watch_and_next.sh）
2. 缓存/陈旧数据导致的误判
3. 脚本输出 "无新提交, 继续等待" 与任务描述 "HM2提交了新commit" 矛盾
4. R289的标记 "轮到HM2优化HM1" → 实际轮到HM2而非HM1
```

---

## 🧠 分析: 无法执行优化

### 计划中的优化方向 (延续R289计划, 基于R287碎片数据)

| # | 参数 | 当前值 | 目标值 | Δ | 理由 |
|---|------|--------|--------|---|------|
| 1 | **TIER_TIMEOUT_BUDGET_S** | 128s | 135s | +7s | P99=163s > BUDGET=128s → 预算破裂 |
| 2 | **HM_CONNECT_RESERVE_S** | 22s | 24s | +2s | k2/k5高频SSLEOFError (SSL握手headroom) |
| 3 | **TIER_COOLDOWN_S** | 22s | 30s | +8s | 对齐KEY_COOLDOWN=38s; 防tier冷却过短重试耗尽预算 |

### 无法执行原因
```
❌ SSH到HM2完全断开 (port 222, 持续70+分钟)
❌ ping 100% 包丢失
❌ Tailscale: opc2sname offline, rx=0 (零回包, 主机无响应)
❌ 无法读取HM2 docker-compose.yml / config.py
❌ 无法执行 docker compose up -d / docker compose restart
❌ 铁律: 只改HM2不改HM1 — 但HM2主机已整体消失
❌ ⚠️ 不得停止/重启/kill mihomo — 但HM2侧mihomo进程已随主机消失
```

### 可能原因分析 (不变)
```
1. HM2主机掉电（最可能: rx=0, 无任何TCP/ICMP响应）
2. HM2主机内核崩溃（OOM killer? docker overcommit? — 无日志可查）
3. HM2主机的网络接口/路由完全断开
4. 非Tailscale自身故障 — HM1侧其他节点正常
```

---

## 📋 判定

| 评判标准 | 状态 |
|----------|------|
| 更少报错 | ⚠️ 无法评估（HM2数据不可达, 70+分钟无响应） |
| 更快请求 | ⚠️ 无法评估（HM2数据不可达） |
| 超低延迟 | ⚠️ 无法评估（HM2数据不可达） |
| 稳定优先 | ⚠️ HM2完全消失, HM1侧deepseek_hm_nv正常但单侧运行 |
| 只改HM2 | ❌ HM2不可达, 无法修改任何配置 |

**结论**: R290因HM2主机完全离线（70+分钟, rx=0, 3-layer全断）而无法执行任何优化。R289的优化计划（BUDGET+7s, RESERVE+2s, TIER_COOLDOWN+8s对齐）已拟定但需HM2主机恢复后才能执行。当前HM1侧deepseek_hm_nv全key健康（100%成功, 0 error），双机不对称运行但HM1侧无降级。本轮无新数据，延续R289状态。

---

## 🔄 循环状态

```
R284: HM1→HM2 (无变更, 稳定)
R285: HM1→HM2 (无变更, 稳定) [opc_uname]
R286: HM1→HM2 (无变更, 稳定) [opc_uname]
R287: HM1→HM2 (⚠️ HM2不可达, 首次检测) [opc_uname]
R288: HM1→HM2 (⚠️ HM2不可达, 持续) [opc_uname]
R289: HM1→HM2 (⚠️ HM2不可达, 55min) [opc_uname]
R290: HM1→HM2 (⚠️ HM2不可达, 70+min, 无新HM2提交) [opc_uname 本轮]
  ↓  等待HM2恢复上线
  └→ HM2恢复后拉取最新 → 检测到R290标记 → HM2执行优化HM1
```

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记