# R349: HM2优化HM1 — ⏸️ 无操作 · 全参数均衡 · 零错误全成功

**日期**: 2026-06-30 11:44-11:50 UTC
**执行者**: HM2 (opc2_uname)
**目标**: HM1 (100.109.153.83:222)
**前轮**: R348 (HM1→HM2, 三项清单复核证伪)

---

## 1. 数据采集

### 1a. 容器日志 (最近100行, 总128行)
- 错误匹配: 21行 grep -ciE (全为 HM-ERR/HM-TIER 信息行, 非实际错误)
- 关键模式:
  - `SSLEOFError` 仅2次 (k1 port 7894, SSL读取EOF)
  - `HM-SSL-RETRY` 3.0s backoff 重试成功
  - 全为 `deepseek_hm_nv` tier, `tier_chain=['deepseek_hm_nv']` (ring fallback R40)
  - 无 timeout/429/empty200/all_tiers_exhausted 等错误

### 1b. 运行环境 (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=45
TIER_TIMEOUT_BUDGET_S=100
MIN_OUTBOUND_INTERVAL_S=6.0
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=38
HM_CONNECT_RESERVE_S=10
HM_SSLEOF_RETRY_DELAY_S=3.0
PROXY_TIMEOUT=300
```

### 1c. hm_requests (2小时窗口, created_at)
- 总请求: 22
- 成功: 22 (100.0%)
- 失败: 0
- R429: 0
- SSLEOF: 0
- ATE (all_tiers_exhausted): 0
- NVCFPexecTimeout: 0
- avg TTFB: 6603ms

### 1d. 延迟分布 (2小时, status=200)
- P50=6032ms, P95=13986ms, P99=31241ms
- 全键均匀: k0=4261ms(3reqs), k1=8783ms(7reqs), k2=4625ms(4reqs), k3=6393ms(4reqs), k4=6732ms(4reqs)
- k1 有一个 outlier (35748ms), 其余正常

### 1e. 错误详情 (hm_error_detail.2026-06-30.jsonl, 4条)
- 2条 ATE 事件 (00:11-00:28 UTC, 容器重启前)
  - 第一条: 3 attempts (k1=76.5s + k2=5.4s + k3=6.1s) = 88s total
  - 第二条: 6 attempts (k4=57s + k0=9.3s + k1=5.8s + k2=5.8s + k3=5.7s + k4=budget_exhausted_after_connect) = 85.8s total
- 均为 **容器重启前** 事件 (重启于 09:32 UTC)
- 重启后: 零错误, 全成功

### 1f. 最近10条请求 (DB created_at)
```
03:44:16 | 6238ms | k1 | success
03:44:10 | 6354ms | k0 | success
03:44:03 | 5426ms | k4 | success
03:43:58 | 6081ms | k3 | success
03:43:52 | 6092ms | k2 | success
03:43:46 | 1592ms | k1 | success
03:43:44 | 14287ms | k1 | success
03:43:30 | 5982ms | k4 | success
03:43:24 | 6332ms | k3 | success
03:43:18 | 1113ms | k2 | success
```

---

## 2. 诊断

### 2a. 当前状态
HM1 容器重启后 (09:32 UTC) 运行 ~2h18min, 全参数均衡, 零错误, 100%成功率。
所有参数已达优化天花板:
- BUDGET=100 (2×UPSTREAM=90 → 10s headroom, R18耦合满足)
- UPSTREAM=45 (P95=13,986ms ≪ 45,000ms, 内存充分)
- KEY=TIER=38 (等值不变量满足, R341修复后稳定)
- RESERVE=10 (已达底限, 前轮24→16→10逐步回收)
- MIN_OUTBOUND=6.0 (HM2的2.4倍, 梯度保持)
- SSLEOF_RETRY=3.0 (2次SSL重试均成功)

### 2b. 唯一微弱模式
k1 (SOCKS5 port 7894) 有略高延迟 (8783ms vs 4261-6732ms) 和2次 SSLEOF 事件。
但延迟仍在 BUDGET=100s 安全范围内 (最长35,748ms=35.7s ≪ 100s),
且 SSLEOF 被 3.0s 重试机制覆盖, 全成功。
**此模式不构成优化目标** — 属 NVCF 基础设施噪声, 非可调参数范围。

### 2c. 策略选择
- ⏸️ 无参数变更: 全参数已达均衡, 单次变更无边际改善
- ⏸️ 无容器重启: 当前运行稳定, 重启会破坏 2h+ 连续运行状态
- ⏸️ 无 RESERVE 调整: 已至底限 10s
- ⏸️ 无 BUDGET 调整: 已超过 2×UPSTREAM=90
- ⏸️ 无 COOLDOWN 调整: KEY=TIER=38 等值不变量稳定

**本回合: 无操作 (nop) — 全参数均衡, 零错误, 零变更。**

---

## 3. 预期效果 (维持)

- **成功率**: 维持 100% (当前 22/22)
- **延迟分布**: 维持 P50~6s, P95~14s, P99~31s
- **错误率**: 维持 0% (R429/SSLEOF/ATE/empty200)
- **全参数均衡**: 维持不变

---

## 4. 观察项

- **WATCH**: k1 port 7894 SSLEOF 频率 (当前 2次/128行, 低)
- **WATCH**: 下轮 HM1 若有新流量高峰, 重新评估 BUDGET/RESERVE
- **WATCH**: NVCF 上游 502 时段 (05-06 UTC) — 当前窗口无此模式
- **CONFIRMED**: 铁律: 只改HM1不改HM2 ✓ (本回合零变更)
- **CONFIRMED**: 少改多轮 ✓ (本回合零参数变更)

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记