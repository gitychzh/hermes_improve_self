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
- 总请求: 22, 成功: 22 (100.0%), 失败: 0
- R429: 0, SSLEOF: 0, ATE: 0, NVCFPexecTimeout: 0
- avg TTFB: 6603ms

### 1d. 延迟分布 (2小时, status=200)
- P50=6032ms, P95=13986ms, P99=31241ms
- 全键均匀: k0=4261ms(3), k1=8783ms(7), k2=4625ms(4), k3=6393ms(4), k4=6732ms(4)

### 1e. 错误详情 (重启前事件, 2条ATE@00:11-00:28 UTC)
- 第一条: 3 attempts (k1=76.5s + k2=5.4s + k3=6.1s) = 88s total
- 第二条: 6 attempts (k4=57s + k0=9.3s + k1=5.8s + k2=5.8s + k3=5.7s + k4=budget_exhausted_after_connect) = 85.8s total
- 均为容器重启前事件 (重启于 09:32 UTC)

---

## 2. 诊断

### 2a. 当前状态
HM1 容器重启后运行 ~2h18min, 全参数均衡, 零错误, 100%成功率。
所有参数已达优化天花板: BUDGET=100 > 2×UPSTREAM=90 (R18耦合), KEY=TIER=38 (等值不变量),
RESERVE=10 (底限), MIN_OUTBOUND=6.0 (HM2的2.4倍).

### 2b. 策略选择
- ⏸️ 无参数变更: 全参数已达均衡, 单次变更无边际改善
- ⏸️ 无容器重启: 当前运行稳定
- 本回合: 无操作 (nop) — 全参数均衡, 零错误, 零变更

---

## 3. 预期效果 (维持)

- 成功率维持 100% (22/22), 延迟 P50~6s P95~14s P99~31s
- 错误率维持 0% (R429/SSLEOF/ATE/empty200)

---

## 4. 观察项

- **WATCH**: k1 port 7894 SSLEOF 频率 (当前 2次/128行, 低)
- **WATCH**: 下轮 HM1 若有新流量高峰, 重新评估参数
- **CONFIRMED**: 铁律: 只改HM1不改HM2 ✓ (本回合零变更)
- **CONFIRMED**: 少改多轮 ✓ (本回合零参数变更)

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记