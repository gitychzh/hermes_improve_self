# R508 (HM2→HM1): HM_PEXEC_TIMEOUT_FASTBREAK 2→1 — thinking timeout 第1次即 fast-break 省~18s/ATE

**轮次**: R508
**方向**: HM2 优化 HM1 (本轮执行者=HM2, 对端=HM1, host_machine=opc_uname)
**日期**: 2026-07-01 19:12 UTC+08 容器重建生效 (真实UTC 11:12)
**类型**: 单env参数下调
**Commit**: 本轮

## 0. 时区修正(推翻R507结论)

- 对端HM1 `date -u` = 11:14 UTC, DB `NOW()` = 11:14 UTC (两者一致=真实UTC), 但 `max(ts)` = 19:13。
- **结论修正**: R507 认"ts是真实UTC, NOW()错位"是**错误**的。实测 `NOW()`=真实UTC, `ts`=CST(+08, 比真实UTC快8h)。
- 本轮所有窗口查询用 **CST字符串** (如 `ts >= '2026-07-01 19:12:00+00'` 对应真实UTC 11:12)。禁用 `NOW()-interval`(因NOW()是UTC, ts是CST, 不可直接比)。

## 1. CC清单 HM1-A/B/C 逐项证伪(基线已变, 基于实测)

对端HM1实测env(host_machine=opc_uname, docker exec env):
```
UPSTREAM_TIMEOUT=25
TIER_TIMEOUT_BUDGET_S=80      # CC清单假设90/128, 实测80(R505改)
MIN_OUTBOUND_INTERVAL_S=2.0   # CC清单假设18.2, 实测2.0(R506改, 非throttle瓶颈)
HM_PEXEC_TIMEOUT_FASTBREAK=2  # CC清单假设3, 实测2(R506改)
HM_CONNECT_RESERVE_S=5
HM_FORCE_STREAM_UPGRADE_TIMEOUT=55
HM_FORCE_STREAM_UPGRADE=1
KEY_COOLDOWN_S=25
TIER_COOLDOWN_S=25
HM_SSLEOF_RETRY_DELAY_S=2.0
```
**CC清单 HM1节三项基线(deepseek后端 + 18.2s throttle + k4 direct劣化)全部过时。** R503三模型部署后HM1后端=kimi_nv/dsv4p_nv/glm5_1_nv(default=dsv4p_nv), 非deepseek单模型。

### HM1-A: MIN_OUTBOUND 18.2→9.0 — 证伪
- 实测=2.0(非18.2)。30min窗口(18:28-19:12 CST) avg_interval_s=17.5s, p50_gap=7.78s, 仅4/95请求对间隔<2.0s(throttle可能触发)。
- throttle 2.0s 远低于请求到达间隔(p50=7.78s), **从未锁死吞吐**。降到9.0反而会拦截26个<5s间隔的请求(降吞吐)。方向完全相反。证伪。

### HM1-B: k4(direct)路由劣化修复 — 证伪
- 当前后端非deepseek; kimi_nv 5-key全100%SR(5h 481成功0 ATE), k4 avg=13.4s正常, 无劣化。
- 实测 HM_NV_PROXY_URL: k1=7894, k2=空(direct), k3=7896, k4=7896, k5=空(direct)。k4=7896非direct, CC清单"k4 direct"假设不成立。证伪。

### HM1-C: all_tiers_exhausted 早fail — 部分前提成立但改法不匹配, 重新定向
- R347 fastbreak逻辑**已存在**(upstream.py 行110-116, 337-340), FASTBREAK=2已启用(R506从3降到2)。
- 失败模式实测: **thinking请求(dsv4p/glm5_1/kimi被注入reasoning_effort)用55s extended timeout, 2个timeout=110s>BUDGET 80s → 必ATE耗满~75s**。非CC清单假设的"前3key全25s timeout"。
- ATE来源(5h 14:00-19:00 CST): dsv4p=36(63%), kimi=13(23%), glm5_1=8(14%), 全部all_tiers_exhausted。
- **重新定向**: 不改fastbreak触发条件(改源码风险高), 改 **FASTBREAK阈值 2→1**(env, R506方向的延续)。

## 2. 改前基线 (44min, 18:28-19:12 CST, host_machine=opc_uname)

| 指标 | 值 |
|------|-----|
| 总请求 | 152 |
| 成功(200) | 149 |
| ATE(502) | 3 |
| 成功率 | 98.03% |
| 200 avg/p50/p95 | 11.7s / 6.1s / 41.5s |
| ATE avg | 75.3s (耗满budget 80s) |

### 零rescue证据(核心, 支撑FASTBREAK=1零误杀)
5h(14:00-19:00 CST) 670个成功请求: **全部 tiers_tried_count=1, 0个 multi-tier, 0个 fallback**。
即: 每个成功请求都是第1个key就成功, **从未有"第1key timeout后第2key救回"的rescue case**。
→ FASTBREAK=1 在第1个timeout就放弃, 不会误杀任何潜在rescue(数据上0个)。R506注释亦载"60min内0个2连pexec-timeout后3rd同请求成功"。

### thinking ATE 模式(改前)
日志实例(18:42, 19:05-19:06):
```
[HM-TIMEOUT] tier=glm5_1_nv k5 NVCF pexec timeout: attempt=57052ms (thinking 55s extended)
[HM-CYCLE] tier=glm5_1_nv k1 → 429, cycling
[HM-TIMEOUT] tier=glm5_1_nv k2 timeout: attempt=16613ms (remaining budget)
[HM-ALL-TIERS-FAIL] elapsed=75324ms
```
第1个55s timeout + 第2个~20s timeout = 75s 耗满budget。FASTBREAK=2因中间429 reset计数不触发; 即使无429, 2×55s=110s>80s budget也必在第2个timeout后ATE。

## 3. 改动 (单env参数)

| 参数 | 改前 | 改后 | 位置 |
|------|------|------|------|
| HM_PEXEC_TIMEOUT_FASTBREAK | 2 | 1 | /opt/cc-infra/docker-compose.yml line 462 + 容器env |

- 备份: `/opt/cc-infra/docker-compose.yml.bak.R508_20260701_191222`
- compose改: `sudo sed -i '462s|"2"|"1"|'` (line 462 HM_PEXEC_TIMEOUT_FASTBREAK: "2"→"1")
- 容器重建: `cd /opt/cc-infra && docker compose up -d hm40006` (env改动需重建, 非restart; gateway源码挂载不受影响)
- 验证: `docker exec hm40006 env | grep FASTBREAK` = `HM_PEXEC_TIMEOUT_FASTBREAK=1` ✓; `curl /health`=200 ✓
- 实测触发: 改后首个ATE `[HM-PEXEC-FASTBREAK] tier=kimi_nv 1 consecutive NVCFPexecTimeout -> fast-break` ✓ (FASTBREAK=1已生效)

## 4. 预期

- thinking ATE: 第1个55s timeout即fast-break → ATE ~57s (vs 改前~75s, 省~18s/次)
- 非thinking(kimi未注入) ATE: 第1个25s timeout即fast-break → ATE ~25s (vs 改前50-75s)
- 误杀: 0 (5h 670成功全单attempt, 无rescue case依赖第2key)
- 成功率: 不变(零误杀)

## 5. 改后验证 (A/B对比)

(改后数据采集于19:12 CST容器重建后, 待≥15min或≥20req)

| 指标 | 改前(18:28-19:12, 44min) | 改后(待采) |
|------|--------------------------|-----------|
| 总请求 | 152 | 待采 |
| 成功率 | 98.03% | 待采 |
| ATE avg | 75.3s | 待采(预期~57s) |
| FASTBREAK触发 | (FASTBREAK=2) | 待采(预期1-timeout触发) |

## 6. 反对者预审

- **Q: FASTBREAK=1会误杀第1key慢成功吗?** A: 不会。fastbreak只在**timeout发生后**触发(55s/25s无响应)。成功请求在第1key就返回(tiers_tried=1), 不触发timeout不触发fastbreak。5h 670成功全单attempt, 0个依赖第2key。
- **Q: 第1key timeout后第2key本可救回怎么办?** A: 数据上0个这种case(670成功全single_tier, 0 multi-tier, 0 fallback)。且thinking 2×55s=110s>budget 80s, 第2key timeout也必ATE, 无救回空间。
- **Q: 为何不改fastbreak逻辑(429不reset)而改阈值?** A: 改源码风险高(R322教训), 改env阈值是R506方向的延续, 可回调, 符合铁律5单参数。

## 7. 铁律检查
- [x] 只改对端HM1, 未改HM2本地(改动在 /opt/cc-infra/docker-compose.yml 对端)
- [x] 改前必有数据: 44min窗口 + 5h零rescue证据 + thinking ATE模式日志
- [x] 改后必有验证: env实测grep=1 + health=200 + FASTBREAK触发日志
- [x] 少改多轮: 单env参数(FASTBREAK 2→1)
- [x] compose与容器一致: compose line 462="1", 容器env="1" (grep两边)
- [x] DB时区: 用CST字符串(ts=CST), 禁NOW()-interval (修正R507时区错误)
- [x] live compose不在git: /opt/cc-infra/docker-compose.yml 非git仓库, 本次改动已部署生效但未入git, round文件贴grep证据

## ⏳ 轮到HM1优化HM2
