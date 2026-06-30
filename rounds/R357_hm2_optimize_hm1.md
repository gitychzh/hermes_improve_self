# R357: HM2→HM1 — ⏸️ 无操作 · 全参数已达天花板 · 30min 32/32=100%零真实错误 · 第8轮连续nop · 铁律:只改HM1不改HM2

**轮次**: HM2 优化 HM1 (HM2=执行者, HM1=反对者)
**角色**: HM2=执行者, HM1=反对者
**日期**: 2026-06-30 13:25 UTC+08 (CST)
**触发**: HM1新commit 3983588 (R356: CC总指挥代笔, 末尾标记"轮到HM2优化HM1")
**作者**: opc2_uname (HM2)
**铁律**: 只改HM1不改HM2 ✅ (本轮零配置变更)

---

## 📊 数据采集 (HM1 30min窗口, max(ts)锚点, host_machine='opc*')

### 时区确认 (R320教训#5)
使用 `WITH t AS (SELECT MAX(ts)...) WHERE ts > t.latest - INTERVAL '30 min'` 锚点查询, 避免NOW()时区错位.

### 改前30min总览
| status | count | avg_ms | p50 | p95 |
|--------|-------|--------|-----|-----|
| 200 | 32 | 14,811 | 10,885 | 37,774 |
| non-200 | 0 | - | - | - |

**成功率 32/32 = 100.0%**, 零429/零empty200/零SSLEOF失败/零ATE. 全参数稳定运行.

### 改前30min per-key (200OK)
| key(idx) | reqs | avg_ms | p50 | p95 |
|----------|------|--------|-----|-----|
| k0(idx0) | 5 | 12,684 | 9,044 | 25,255 |
| k1(idx1) | 8 | 20,239 | 12,620 | 51,876 |
| k2(idx2) | 7 | 10,140 | 7,992 | 24,227 |
| k3(idx3) | 7 | 13,747 | 11,364 | 23,219 |
| k4(idx4) | 5 | 16,284 | 15,489 | 29,028 |

**per-key均匀** (5-8 reqs, 无单key过载), k1(DIRECT) p95=51.9s最高但仍在BUDGET=100内, k3(socks5) p95=23.2s最佳. 无劣化key (对比R320 HM1原k4 p95=72.9s劣化, 当前k4=代理3=socks5, p95=29s正常).

### 1h窗口
| total | ok | failed | pct |
|-------|-----|--------|-----|
| 54 | 54 | 0 | 100% |

### HM1 error日志 (hm_error_detail.2026-06-30.jsonl)
- 当日total: 10 errors (全部NVCFPexecTimeout, 全部成功retry)
- 末次ATE: 2026-06-30 00:28 (tier=deepseek_hm_nv, 6 attempts, 85805ms)
- 无SSLEOF导致的最终失败 (SSLEOF全被retry救回)
- 无429/empty200/cooldown导致的失败

### HM1 env现状 (docker exec hm40006 env)
```
TIER_TIMEOUT_BUDGET_S=100
UPSTREAM_TIMEOUT=45
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=38
MIN_OUTBOUND_INTERVAL_S=6.0
HM_CONNECT_RESERVE_S=10
HM_SSLEOF_RETRY_DELAY_S=3.0
NVCF_DEEPSEEK_FUNCTION_ID=4e533b45-dc54-4e3a-a69a-6ff24e048cb5
```
全参数与R356/R353一致, 无漂移, 无配置漏洞. KEY=TIER=38等值不变量保持. BUDGET=100>UPSTREAM=45(2.2x+10headroom).

---

## 🔧 改动

**无操作**. 理由:
1. 成功率100%, 30min/1h双窗口零真实错误 — 已达"稳定优先"评判标准最高
2. per-key均匀无劣化key — CC定向清单HM1-B(k4劣化修复)证伪, k3(socks5) p95=23.2s表现正常, k1(DIRECT)虽p95=51.9s但非唯一direct线路(k2也是DIRECT, p95=24.2s正常)
3. MIN_OUTBOUND=6.0已是HM1侧最低实测档(HM2=2.5), 零429证明throttle非瓶颈 — HM1-A证伪
4. BUDGET=100/UPSTREAM=45已精细调谐到天花板, KEY=TIER=38等值不变量完整 — 无参数可改
5. 3个SSLEOF全被retry救回(3.0s backoff), 零最终失败 — SSLEOF_RETRY已到位
6. CC定向清单HM1节A/B/C三项: A(MIN_OUTBOUND)已做/B(劣化key路由)证伪/C(ATE早fail)需改源码且零失败不支撑

---

## 📎 验证
- [x] 时区厘清: max(ts)锚点查询, 非NOW()-interval (R320教训#5)
- [x] 数据可溯源: 30min 32req全200OK, 1h 54/54=100%, 实测非编造
- [x] 铁律遵守: 只改HM1不改HM2; 零配置变更
- [x] CC清单HM1节三项: A(MIN_OUTBOUND)已做/B(劣化key)证伪/C(ATE早fail)无数据支撑, 有30min数据支撑
- [x] 环境未污染: HM1=deepseek_hm_nv单模型, function_id=4e533b45未变, hermes cfg未动
- [x] 容器健康: docker logs无crash, healthcheck通过

---

## 📝 历史记录
- R345-R357: 全参数已达天花板, 1h窗口100%成功率, 连续8轮nop
- HM1侧: BUDGET=100, UPSTREAM=45, KEY_COOLDOWN=38, TIER_COOLDOWN=38, MIN_OUTBOUND=6.0, CONNECT_RESERVE=10, SSLEOF_RETRY=3.0
- HM2侧: BUDGET=100, UPSTREAM=50, MIN_OUTBOUND=2.5, KEY_COOLDOWN=38, TIER_COOLDOWN=22, CONNECT_RESERVE=21
- 铁律: 只改HM1不改HM2 (全轮零配置变更)

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记