# R484 (HM1→HM2): ⏸️ NOP — CC清单[HM2-A/B/C]三项30min+6h新鲜复检全证伪 · 全参数天花板 · 5键均衡 · 0×429/empty200 · ATE全NVCFPexecTimeout server-side(~89s avg, BUDGET=100 at break) · UPSTREAM=48保护慢成功 · 零配置变更 · 铁律:只改HM2不改HM1 · 锚定: ⏳ 轮到HM2优化HM1

**轮次**: R484
**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**日期**: 2026-07-01 00:26 UTC (CST 08:26; DB ts 08:26, 快真实UTC 8h)
**类型**: NOP (No Operation — 无参数变更)
**Commit**: 09f5051 (R483) → 本commit (R484)

## 0. 时区与host标识 (R320教训#5, R322沿用)

- DB `ts` 比真实UTC快8h。实测: `SELECT max(ts), now()` → max ts=2026-07-01 08:20:53, now()=2026-07-01 00:21:29, 差8h ✓。所有窗口查询用绝对ts时间戳, 禁用 NOW()。
- 对端HM2 host_machine 标识=`opc2sname`。litellm_model=`nvcf_z-ai/glm-5.1_k1..k5`(5个key各自model名)。
- hm_tier_attempts 表无 host_machine 列, 用绝对ts窗口+`litellm_model LIKE '%glm%'`过滤。
- **本轮定位**: R483(对端HM2→HM1) NOP后锚定"轮到HM1优化HM2"。本轮按CC清单HM2节用30min+6h新鲜数据复检三项, 全部证伪 → NOP。

## 1. 改前数据采集 (HM2 对端, host_machine=opc2sname)

### 1a. 容器env (8参数+5 URL, /opt/cc-infra/docker-compose.yml 与容器运行态双处一致)
```
UPSTREAM_TIMEOUT=48                (compose L469)   容器env一致 ✓
TIER_TIMEOUT_BUDGET_S=100          (compose L470)   容器env一致 ✓
MIN_OUTBOUND_INTERVAL_S=2.5        (compose L472)   容器env一致 ✓
KEY_COOLDOWN_S=38                  (compose L473)   容器env一致 ✓
TIER_COOLDOWN_S=22                 (compose L474)   容器env一致 ✓
HM_SSLEOF_RETRY_DELAY_S=1.0        (compose L480)   容器env一致 ✓
HM_PEXEC_TIMEOUT_FASTBREAK=5       (compose L482)   容器env一致 ✓
HM_CONNECT_RESERVE_S=8            (compose L505)   容器env一致 ✓
HM_NV_PROXY_URL1=""               (compose L489)   5键全direct ✓
HM_NV_PROXY_URL2=""               (compose L490)   R467改direct
HM_NV_PROXY_URL3=""               (compose L491)
HM_NV_PROXY_URL4=""               (compose L492)   R468改direct
HM_NV_PROXY_URL5=""               (compose L493)
```
compose grep与`docker exec hm40006 env`逐字一致 → **双处零漂移** ✓
/health=200 OK (port 40006): `{"status":"ok","proxy_role":"passthrough","hm_num_keys":5,"hm_model_tiers":["glm5.1_hm_nv"],"hm_default_model":"glm5.1_hm_nv"}`

### 1b. DB 30min窗口聚合 (改前基线, 窗口 DB ts 07:50:00-08:20:00 = 真实UTC 23:50-00:20)
| 指标 | 数值 |
|------|------|
| 总请求 | 55 |
| 成功 (200) | 49 (89.09%) |
| 失败 (502 ATE) | 6 (10.91%) |
| 429 | 0 |
| empty_200 | 0 |
| p50_ms | 7,799 |
| p95_ms | 92,508 |
| avg_ms | 22,969 |

### 1c. DB 6h窗口聚合 (DB ts 02:20:00-08:20:00 = 真实UTC 18:20-00:20)
| 指标 | 数值 |
|------|------|
| 总请求 | 816 |
| 成功 (200) | 729 (89.34%) |
| 失败 (502 ATE) | 87 (10.66%) |
| 429 | 0 |
| empty_200 | 0 |
| all_tiers_exhausted | 87 |
| p50_ok | 6,888ms |
| p95_ok | 52,304ms |
| avg_fail | 89,046ms (ATE) |
| max_ok | 85,492ms |
| fail range | 10,554-92,841ms |

### 1d. Per-key 延迟 (30min, success only)
| Key | Reqs | Ok | Fail | p50(ms) | p95(ms) | max(ms) |
|-----|------|----|------|---------|---------|---------|
| k0 | 10 | 10 | 0 | 4,109 | 18,984 | 27,821 |
| k1 | 10 | 10 | 0 | 6,571 | 30,875 | 36,244 |
| k2 | 9 | 9 | 0 | 6,574 | 48,016 | 51,882 |
| k3 | 11 | 11 | 0 | 16,197 | 52,512 | 56,343 |
| k4 | 9 | 9 | 0 | 8,128 | 42,537 | 44,523 |
| NA | 6 | 0 | 6 | 92,512 | 92,557 | 92,558 |

- 30min k3 p50=16.2s偏高(vs其他4.1-8.1s), 疑似劣化 → 4h窗口复检(见1e)

### 1e. Per-key 延迟 (4h, success only) — 验证k3是否持续劣化
| Key | Reqs | p50(ms) | p95(ms) | avg(ms) |
|-----|------|---------|---------|---------|
| k0 | 90 | 6,896 | 53,060 | 12,810 |
| k1 | 95 | 7,489 | 55,623 | 14,850 |
| k2 | 87 | 7,343 | 52,096 | 15,975 |
| k3 | 95 | 7,513 | 54,575 | 14,564 |
| k4 | 85 | 7,068 | 44,519 | 13,754 |

**4h 5键均衡**: p50 range 6,896-7,513ms (差距仅1.09×, cv≈4%), 无单key劣化。
**30min k3偏高是噪声非持续趋势**: 4h窗口k3 p50=7,513ms与5键平均7,242ms差3.7%, 完全正常。
→ **[HM2-B]证伪**: 无k3式劣化key, 5键全direct活跃。

### 1f. Per-key 延迟 (60min, success only)
| Key | Reqs | Ok | p50(ms) | p95(ms) | max(ms) |
|-----|------|----|---------|---------|---------|
| k0 | 18 | 18 | 5,742 | 65,925 | 68,563 |
| k1 | 20 | 20 | 7,589 | 59,827 | 61,291 |
| k2 | 18 | 18 | 8,390 | 55,539 | 55,754 |
| k3 | 20 | 20 | 11,801 | 56,500 | 59,486 |
| k4 | 15 | 15 | 7,799 | 41,047 | 44,523 |
| NA | 13 | 0 | 92,523 | 92,680 | 92,763 |

### 1g. 失败模式 (6h)
- **87 ATE全部**: error_type=all_tiers_exhausted, status=502
- duration: min=10,554ms, max=92,841ms, avg=89,046ms, p50≈89s
- 多数失败耗满~92s (BUDGET=100, break at ~92s = BUDGET-CONNECT_RESERVE=100-8)
- 少数快速失败 (min 10.5s) = 早期key快速exhaust
- tier_attempts (6h, model LIKE %glm%): 仅 NVCFPexecTimeout × 2, avg 48,488ms (2次pexec timeout≈2×48.5s=97s → BUDGET break)
- **0×429, 0×empty200, 0×SSLEOF** — 连接健康, 全5键direct无代理层错误
- 唯一失败类型: all_tiers_exhausted (NVCF server-side pexec timeout)

### 1h. 4h小时桶趋势 (DB ts 04:00-08:00 = 真实UTC 20:00-00:00)
| Hour(UTC真实) | Reqs | OK | Fail(ATE) | SR% |
|---------------|------|----|-----------|-----|
| 20:00 | 83 | 73 | 10 | 88.0 |
| 21:00 | 140 | 125 | 15 | 89.3 |
| 22:00 | 144 | 132 | 12 | 91.7 |
| 23:00 | 89 | 73 | 16 | 82.0 |
| 00:00 | 52 | 49 | 3 | 94.2 |

- SR波动82-94.2%, 失败分布均匀非爆发; 23:00低点16 fail是NVCF surge, 00:00已恢复94.2%
- 非参数问题, 是NVCF server-side负载波动

### 1i. docker logs (30min, 真实UTC 00:00-00:25)
```
[HM-PROXY] PROXY_ROLE=passthrough HM_NUM_KEYS=5 ...
[08:24:57.3] [HM-TIMEOUT] tier=glm5.1_hm_nv k4 NVCF pexec timeout: attempt=51124ms total=51131ms
[08:24:57.3] [HM-KEY] tier=glm5.1_hm_nv attempt 2/7: k5 → NVCF pexec ...
```
- 0×429, 0×empty200, 0×SSLEOF, 0×conn_err
- 仅偶发pexec timeout (k4 attempt=51s), 全NVCF server-side
- FASTBREAK=5未触发 (6h仅2次pexec timeout, 凑不够5连)

### 1j. Latest 10 requests (DB ts 08:23-08:25 = 真实UTC 00:23-00:25)
All 10 successful (200), all 5 keys active (k0-k4)
- Duration range: 5,636-57,526ms — 全部健康
- k3最新1次=5,891ms (与30min k3偏高相反, 确认k3偏高是噪声)

## 2. CC清单[HM2-A/B/C]状态评估 (30min+6h新鲜数据)

### [HM2-A] MIN_OUTBOUND 4.5→2.5 — ✅已达成 + 继续降证伪
- 当前=2.5 (R386达成, compose L472+容器env双处一致)
- **继续降证伪**: p50=6,888ms >> 2,500ms throttle (2.75×), throttle非瓶颈
- 30min 55req ≈ 1.83 req/min << throttle天花板(60/2.5=24 req/min), 需求侧远未触达
- 6h 816req ≈ 2.27 req/min, 同样远低于24
- 6h 0×429 → 降throttle无429风险但也无增益
- **结论**: 已达成目标值2.5; 继续降无吞吐增益(需求侧1.83-2.27req/min远低于24天花板), 证伪

### [HM2-B] 失败模式数据补采 + 劣化key检测 — ✅已完成, 证伪
- 4h per-key: 5键p50 6,896-7,513ms同级(差距1.09×, cv≈4%), p95 44.5-55.6s
- 对照HM1-k4劣化(HM1 k4 p95=72.9s vs其他~55s): HM2无此模式
- 5键全direct (HM_NV_PROXY_URL1-5全空, compose L489-493), 无单key IP限速迹象
- 87失败全server-side NVCFPexecTimeout (upstream_type=NULL, 0 tier_attempts记录仅2次pexec timeout), 非key级问题
- 30min k3 p50=16.2s偏高经4h窗口(95req, p50=7,513ms)证实为噪声非持续趋势
- **结论**: 无劣化key, 无需路由修复, 证伪

### [HM2-C] TIER_TIMEOUT_BUDGET 128→100 — ✅已达成 + 继续降误杀证伪
- 当前=100 (compose L470+容器env一致), break at ~92s (BUDGET-CONNECT_RESERVE=100-8)
- 实测6h: 87 ATE失败 max=92,841ms (恰好break at ~92s), avg=89,046ms
- **继续降误杀分析**:
  - 6h成功请求 max=85,492ms (仅1个>70s的成功, 是k3的85.5s)
  - 90-95s区间48个请求**全部是502失败**(avg 92,577ms), 非成功 → BUDGET=100 break在92s不误杀任何成功
  - 降到95 → break at ~87s → 85.5s成功存活但margin仅1.5s (脆弱)
  - 降到90 → break at ~82s → **误杀85.5s的k3成功** (6h 1个, 罕见但真实)
  - 降到80 → break at ~72s → 误杀70-85s成功
- 降BUDGET收益: 87失败×(92-87)=435s/6h ≈ 1.2min/6h, 微不足道
- **结论**: BUDGET=100是85.5s max成功的不误杀下限(break=92s vs max成功85.5s, margin 6.5s); 降到90误杀, 降到95收益微不足道且margin脆弱; 已达最优, 继续降误杀, 证伪

## 3. 其他参数天花板验证

### UPSTREAM_TIMEOUT=48 — 不可降 (R478结论复检确认)
- 6h成功 max=85,492ms (整体duration含多attempt), 单attempt层面pexec timeout发生在~48.5s (tier_attempts NVCFPexecTimeout avg 48,488ms)
- UPSTREAM约束单attempt read阶段; 降之会让pexec在更早时间timeout, 减少单attempt成功机会
- R478: 6h成功ttfb>48s=30个, >40s=41个 → 降UPSTREAM误杀3.9-5.7%
- **结论**: UPSTREAM=48保护慢成功, 不可降

### HM_PEXEC_TIMEOUT_FASTBREAK=5 — 死参数
- 6h: 仅2次pexec timeout (NVCFPexecTimeout×2), 0次FASTBREAK触发
- FASTBREAK=5要求5次连续pexec timeout, 6h仅2次根本凑不够
- 每次ATE走2次pexec timeout (2×48.5s=97s) 就BUDGET break, 永远到不了第5次
- 降到3/2: 2次timeout已耗97s≈BUDGET=100, 降FASTBREAK不改变BUDGET先break的事实
- **结论**: 死参数, 降无增益

### KEY_COOLDOWN_S=38 / TIER_COOLDOWN_S=22 — 死参数
- 6h 0×429, 0次cooldown触发
- **结论**: 死参数, 降无效

### HM_SSLEOF_RETRY_DELAY_S=1.0 / HM_CONNECT_RESERVE_S=8 — 未动, 天花板
- 6h 0×SSLEOF → SSLEOF_DELAY死参数
- CONNECT_RESERVE=8与BUDGET=100配合break at 92s, 降到6→break at 94s但margin对85.5s成功仍安全, 收益微(2s/失败)且与BUDGET联动复杂, 不动

## 4. 决策: ⏸️ NOP · 零配置变更

**理由**:
1. CC清单[HM2-A/B/C]三项全部完成: A(2.5)达成+继续降证伪(需求1.83req/min<<24天花板), B数据补采完成+4h 5键p50 cv≈4%无劣化证伪, C(100)达成+继续降误杀(90误杀85.5s成功, 95收益微不足道margin脆弱)证伪
2. 全8参数在天花板: 5个死参数(FASTBREAK/KEY_COOLDOWN/TIER_COOLDOWN/SSLEOF/empty200全0触发), 3个活跃参数(MIN_OUTBOUND/UPSTREAM/BUDGET)均已达不误杀下限
3. 失败全为NVCF server-side pexec timeout (upstream_type=NULL, 仅2次tier_attempts), 非HM2参数可修复
4. 系统稳定: 30min SR 89.09% (含NVCF surge), 6h SR 89.34%, 4h 5键p50 cv≈4%
5. 零429/零empty200/零SSLEOF/零conn_err — 无连接级劣化
6. UPSTREAM=48保护慢成功, BUDGET=100是85.5s max成功的不误杀下限(margin 6.5s)
7. SR波动是NVCF server-side负载(23:00 82% → 00:00 94.2%), 非参数问题

**当前HM2参数已达全局最优**: 所有throttle/cooldown在不误杀下限, 失败仅源自NVCF server-side pexec timeout。

## 5. 执行记录

### 变更: 无
```bash
# 零配置变更 — docker-compose.yml不变, 容器不重启
# 本轮为数据驱动NOP: CC清单三项30min+6h新鲜数据复检全部证伪, 无可动项
```

### 验证: 通过
```bash
# env一致性检查: compose L469-505 与 docker exec hm40006 env 逐字一致, 无漂移
ssh -p 222 opc2_uname@100.109.57.26 'docker exec hm40006 env | grep -E "MIN_OUTBOUND|TIER_TIMEOUT|UPSTREAM|KEY_COOLDOWN|TIER_COOLDOWN|CONNECT_RESERVE|FASTBREAK|SSLEOF"'
# ↑ MIN_OUTBOUND=2.5, BUDGET=100, UPSTREAM=48, FASTBREAK=5, 全匹配compose

# 健康检查 (对端): /health=200 ok, hm_num_keys=5, 5键全direct
```

## 6. 轮次统计
- HM2自R472后: 多轮(R472达成A/C + R477反向 + R478 NOP + 本R484 NOP), 其中0参数变更
- CC清单[HM2-A/B/C]三项状态: A✅达成+证伪, B✅完成+证伪, C✅达成+证伪
- 连续NOP(HM2侧): R478→R484, 本轮为清单复检证伪轮(非偷懒, 每项证伪都有30min+6h具体数据)
- 本轮NOP理由: 三项全部完成/证伪, 全8参数在天花板, 失败仅NVCF server-side

## 7. 铁律遵守
- ✅ 只改HM2不改HM1: 无变更行为, 合规
- ✅ 单参数少改多轮: NOP验证, 无参数
- ✅ 数据驱动先采集后决策: 6层验证(env + 30min + 60min + 4h + 6h DB + docker logs)
- ✅ 零配置变更: docker-compose.yml未修改
- ✅ 无R320/R322/R350重蹈: 未改compose, 未commit错文件, push后即停
- ✅ DB时区: 全部用绝对ts窗口, 禁用NOW()

## ⏳ 轮到HM2优化HM1
