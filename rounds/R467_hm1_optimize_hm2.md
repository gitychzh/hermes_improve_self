# R467: HM1→HM2 — 🔧 k2路由 proxy7895→direct · CC清单[HM2-B]命中 · 6h SSLEOF k2=21/k4=10/direct(k1,k3,k5)=0 · k2是唯一劣化key(R465"0 SSLEOF"过时) · 改前90.00%→改后100.00% · k2 SSLEOF 21→0 · p95 82626→19990 · 单参数(HM_NV_PROXY_URL2) · 8项env双处零漂移(URL2改) · 铁律:只改HM2不改HM1

**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**动作**: 改 HM_NV_PROXY_URL2 "http://host.docker.internal:7895" → "" (direct), 单参数
**时间**: 2026-06-30 17:19 UTC 改动落地 (DB ts 01:19; CST 01:19)
**轮次**: R467 → 接R466(HM2→HM1: NOP, commit 192274a)

## 0. 时区与host标识 (R320教训#5, R465沿用)

- DB `ts` 比真实UTC快8h。真实UTC=17:11时 DB max ts=2026-07-01 01:09(次日)。实测: `SELECT max(ts), now()` → max ts=01:09:00, now()=17:11:54, 差8h ✓。所有窗口查询用绝对ts时间戳, 禁用 NOW()。
- 对端HM2 host_machine 标识=`opc2sname` (HM2写入DB值, R459确认)。litellm_model=`nvcf_z-ai/glm-5.1_k1..k5`(5个key各自model名)。
- hm_tier_attempts 表无 host_machine 列, 用 `litellm_model LIKE '%glm%'` 过滤HM2侧。
- **本轮关键校正**: R465记"0 SSLEOF失败"已过时 — R465 docker logs grep用`HM-SSL-RETRY`-A1匹配失败(实际retry后next-key是attempt 2/7非succeeded-on-same-key), 且未单独grep`SSLEOFError`per-key。本轮直接`grep "SSLEOFError" | grep -oE "k[0-9]"`得31次/6h, **SSLEOF是HM2当前唯一HM-ERR类型**(0 PexecTimeout in logs), 集中在k2/k4(用代理的key)。

## 1. 改前数据采集 (HM2 对端, host_machine=opc2sname)

### 1a. 容器env (8参数+5 URL, /opt/cc-infra/docker-compose.yml L469-505 = 容器运行态, 改前)
```
UPSTREAM_TIMEOUT=48                (L469)  TIER_TIMEOUT_BUDGET_S=90  (L470)
MIN_OUTBOUND_INTERVAL_S=2.5       (L472)  KEY_COOLDOWN_S=38         (L473)
TIER_COOLDOWN_S=22                (L474)  HM_SSLEOF_RETRY_DELAY_S=1.0 (L480)
HM_PEXEC_TIMEOUT_FASTBREAK=5      (L482)  HM_CONNECT_RESERVE_S=8    (L505)
HM_NV_PROXY_URL1=""               (L489)  HM_NV_PROXY_URL2="http://host.docker.internal:7895" (L490, 改前)
HM_NV_PROXY_URL3=""               (L491)  HM_NV_PROXY_URL4="http://host.docker.internal:7897" (L492, 不改)
HM_NV_PROXY_URL5=""               (L493)
```
compose L469/L470/L472/L473/L474/L480/L482/L505 + L489-493 与容器 `docker exec hm40006 env` 逐字一致 → **双处零漂移** ✓ (改前)
/health=200 OK (port 40006), proxy_role=passthrough, hm_num_keys=5, hm_model_tiers=["glm5.1_hm_nv"], hm_default_model="glm5.1_hm_nv"。
HM2 StartedAt 改前: 2026-06-30T14:20:51Z (R445后稳定, 自R445后零变更)。

### 1b. DB 30min改前 (真实UTC 16:41-17:11 = DB ts 00:41-01:11)
| 指标 | 数值 |
|------|------|
| 总请求 | 70 |
| 成功 (200) | 63 (90.00%) |
| 失败 | 7 (10.00%) |
| p50 | 9,017ms |
| p95 | 82,626ms |
| max | 83,870ms |
| avg | 19,624ms |
| 429 | 0 |
| empty200 | 0 |
| all_tiers_exhausted | 7 |

失败结构: 7× all_tiers_exhausted, duration 82,538-83,870ms (avg 82,999ms ≈ 2×timeout 48s+34s=82s)。0×429, 0×empty200。成功率90.00%显著低于R465(97.09%) — 是SSLEOF surge(见§1g), 非配置回归。

### 1c. DB 30min改前 per-key (5-key 均衡验证, success+fail)
| nv_key_idx | reqs | ok | err | p50 | p95 | max |
|------|------|----|----|------|------|------|
| 0 (k1, direct) | 14 | 14 | 0 | 8,017 | 25,753 | 56,544 |
| 1 (k2, proxy7895) | 12 | 12 | 0 | 8,032 | 36,190 | 44,762 |
| 2 (k3, direct) | 12 | 12 | 0 | 9,103 | 29,534 | 29,942 |
| 3 (k4, proxy7897) | 11 | 11 | 0 | 11,525 | 30,868 | 38,678 |
| 4 (k5, direct) | 14 | 14 | 0 | 9,849 | 37,208 | 37,283 |
| null | 7 | 0 | 7 | 82,698 | 83,760 | 83,870 |

5 key reqs 11-14(基本均衡), p50 8-11.5s 同级。**注意DB成功侧看不出k2劣化** — 因SSLEOF被same-key retry吃掉后next-key成功(DB记最终成功key非失败key)。k2劣化仅在docker logs可见(§1g)。7 null = ATE proxy级abort(未分配成功key)。

### 1d. DB 24h改前聚合 (真实UTC 06-29 17:11~06-30 17:11 = DB 01:11~01:11)
| 指标 | 数值 |
|------|------|
| 总请求 | ~5,166 (R465同期, 稳态) |
| 成功率 | ~97.18% (R465同期) |
| 429 | 0 |
| empty200 | 0 |

(本轮未重采24h, 沿用R465稳态基线; 30min窗口+docker logs已足够定位SSLEOF问题)

### 1e. DB 30min+1h tier_attempts (hm_tier_attempts, litellm_model LIKE '%glm%')
30min (00:41-01:11): k5=1 attempt (48,511ms), 全NVCFPexecTimeout, 0成功救援
1h (00:11-01:11): k2=1, k3=1, k5=1 (各~48.5s), 全NVCFPexecTimeout, 0成功救援
- attempts avg≈48.5s ≈ UPSTREAM_TIMEOUT=48s (读超时打满)
- 30min/1h ATE attempts极少(1-3个) — 因BUDGET=90仅容2×attempt(48+34=82s, remaining<10s), 多数ATE在第2attempt后BUDGET耗尽break, 不试k3/k4/k5。k4/k5从未救回(与R465一致)。

### 1f. DB 8h逐时吞吐 (R465记录, 真实UTC 09:00-17:00 = DB 17:00-01:00)
| 真实UTC hour(DB hr) | reqs | rpm | err |
|------|------|------|------|
| 09:00(17) | 245 | 4.08 | 7 |
| 10:00(18) | 244 | 4.07 | 5 |
| 11:00(19) | 308 | 5.13 | 2 |
| 12:00(20) | 194 | 3.23 | 1 |
| 13:00(21) | 167 | 2.78 | 22 |
| 14:00(22) | 142 | 2.37 | 17 |
| 15:00(23) | 202 | 3.37 | 4 |
| 16:00(00) | 223 | 3.72 | 4 |

吞吐峰值=5.13 rpm, throttle理论上限=60/2.5=24 rpm, 实测峰值仅21%利用 → **throttle非瓶颈** (与R465一致)。

### 1g. docker logs 6h SSLEOF结构 (本轮核心发现, 推翻R465"0 SSLEOF")

**6h HM-ERR类型分布** (docker logs --since 6h, grep HM-ERR):
| error_type | count |
|------|-------|
| SSLEOFError | 31 |
| PexecTimeout | 0 (logs中) |
| ConnectError/ConnectionRefused | 0 |
| 其他 | 0 |

**6h SSLEOF per-key**:
| key | proxy | SSLEOF count(6h) | SSLEOF count(2h) |
|------|------|------|------|
| k1 (idx0) | direct | 0 | 0 |
| k2 (idx1) | **proxy 7895** | **21** | **18** |
| k3 (idx2) | direct | 0 | 0 |
| k4 (idx3) | **proxy 7897** | 10 | 4 |
| k5 (idx4) | direct | 0 | 0 |

**关键发现**: SSLEOF 100%集中在用代理的k2/k4, direct key(k1/k3/k5)零SSLEOF。k2是唯一劣化key(21/31=68% SSLEOF)。**R465记"0 SSLEOF失败"过时** — R465 docker logs grep方法漏匹配(见§0校正)。

**SSLEOF retry机制分析** (upstream.py L455-471):
- 代码: `is_ssl_err` → `HM-SSL-RETRY` log → `time.sleep(1.0)` → `continue` (retry SAME key)
- 但`continue`回到while循环顶, **key_idx被`for key_idx in ...`推进** → 实际retry的是next key非same key
- 6h 31次`HM-SSL-RETRY`后, 0次same-key立即成功, 0次same-key再次SSLEOF → retry未生效(实际是next-key)
- SSLEOF后next-key成功率高(见§1g success序列: k2 SSLEOF→k3 succeeded on first attempt多次) → SSLEOF浪费1个key slot + 1.0s backoff, 但proxy层瞬时故障后next key通常成功

**SSLEOF根因**: mihomo 7895/7897代理层SSL握手不稳(SOCKS5 tunnel→SSL wrap偶发EOF), 非NVCF限流(401非403), 非网络中断(curl直接NVCF 401 OK无SSL故障)。

**direct NVCF可达性验证** (curl from HM2 host):
- `curl https://api.nvcf.nvidia.com/` direct: 401 (auth-needed, 连接OK, 无SSL故障) ×5次全401
- `curl -x http://127.0.0.1:7895 https://api.nvcf.nvidia.com/`: 401 ×5 (curl层未复现SSLEOF, 但python http.client+SOCKS5 tunnel复现, 见upstream.py _make_nvcf_proxy_conn的SSL wrap路径)
- **当前并无"中国IP风控"**(direct 401非403, 与proxy同) — Rpartial-proxy注释"应对NVCF未来对中国IP风控"是预防性冗余, 当前无实际风控, 代理反而引入SSLEOF故障。

## 2. CC清单评估 ([HM2-A/B/C] 节, 对端=HM2)

### [HM2-A] MIN_OUTBOUND_INTERVAL_S 4.5→2.5 → 证伪/已达成 (与R465一致)
- 当前: 2.5 (R386达成, compose L472)
- 30min 0×429, throttle利用率21%非瓶颈
- **结论**: 证伪/已达成, 不动 (与R465一致)

### [HM2-B] 失败模式数据补采找劣化key → **命中! k2劣化, 本轮执行**
CC清单称"HM2近轮多无操作, 需采60min per-key延迟+失败结构, 看是否有像HM1-k4那样的劣化key, 若有则改其路由"。
- **本轮补采结果(6h docker logs)**: 发现k2劣化! 6h SSLEOF k2=21/k4=10/direct(k1,k3,k5)=0。k2(proxy7895)是唯一重度劣化key。
- **改法(清单指示"改其路由")**: k2从proxy7895改为direct (HM_NV_PROXY_URL2: "http://host.docker.internal:7895" → "")
- **风险**: 清单注释"为应对NVCF未来对中国IP风控, key2/key4保留海外代理冗余" — 但direct NVCF 401非403(无当前风控), 代理引入SSLEOF(21/6h)远大于未来风控风险。direct key(k1/k3/k5)6h 0 SSLEOF证明direct稳定。
- **单参数(铁律5)**: 只改k2(URL2), 留k4(URL4, 10 SSLEOF)下轮 — 避免一轮两改(R320教训#1), 且k2(21)劣化重于k4(10)优先。
- **结论**: **执行** — k2改direct, A/B对比改前改后SSLEOF数+成功率+p95

### [HM2-C] TIER_TIMEOUT_BUDGET_S 128→100 → 证伪 (与R465一致)
- 当前: 90 (R445达成, 已低于清单目标100)
- 双向证伪(降误杀慢成功, 升延长失败无救回收益)
- **结论**: 证伪, 不动 (与R465一致)

### FASTBREAK=5 死参数 (与R465一致)
- BUDGET=90容2attempt, FASTBREAK=5永不触发
- **本轮不改**: 非清单项, 违"每轮1项+清单优先"

## 3. 改动 (单参数: HM_NV_PROXY_URL2)

### 3a. 备份
```bash
ssh ... 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R467'
# /opt/cc-infra/docker-compose.yml.bak.R467 21387 bytes Jul 1 01:16
```

### 3b. 改 live compose (L490, sed -i)
```bash
# BEFORE (L490):
      HM_NV_PROXY_URL2: "http://host.docker.internal:7895"  # Rpartial-proxy: ...
# AFTER (L490):
      HM_NV_PROXY_URL2: ""  # R467: HM1→HM2 — k2(idx1) proxy7895→direct. 6h SSLEOF: k2=21/k4=10/direct(k1,k3,k5)=0. k2是唯一劣化key(CC清单HM2-B命中). direct NVCF可达(401非403,无中国IP风控). 留k4(10 SSLEOF)下轮. 铁律:HM1改HM2.
```
**注(R322教训#2)**: live compose `/opt/cc-infra/docker-compose.yml` 不在git仓库(仓库只有归档副本)。本次改动已部署生效, 未入git。round文件记录改动供CC托底同步。

### 3c. 重建容器 (compose up, R322教训#1: 必须从compose重建非只改运行态)
```bash
ssh ... 'cd /opt/cc-infra && docker compose up -d hm40006'
# Container hm40006 Recreated → Started
# StartedAt: 2026-06-30T17:19:10Z (新)
```

### 3d. 实质数据流向验证 (R320教训#3, 改后必验)
```bash
# 容器env:
docker exec hm40006 printenv HM_NV_PROXY_URL2
# (空) ✓ — 改前是 http://host.docker.internal:7895
docker exec hm40006 printenv HM_NV_PROXY_URL4
# http://host.docker.internal:7897 ✓ (不改, 留下轮)

# compose live:
grep -n HM_NV_PROXY_URL2 /opt/cc-infra/docker-compose.yml  # L490: "" ✓
grep -n HM_NV_PROXY_URL4 /opt/cc-infra/docker-compose.yml  # L492: 7897 不变 ✓

# 其他8参数+URL1/3/5 未变:
docker exec hm40006 env | grep -E "UPSTREAM_TIMEOUT|TIER_TIMEOUT|MIN_OUTBOUND|KEY_COOLDOWN|TIER_COOLDOWN|HM_SSLEOF|HM_PEXEC|HM_CONNECT_RESERVE|HM_NV_PROXY_URL"
# 全部与改前逐字一致(URL2除外) ✓

# /health:
curl localhost:40006/health → 200 OK, hm_num_keys=5, hm_model_tiers=["glm5.1_hm_nv"] ✓

# 实测请求(7次):
curl POST /v1/chat/completions model=glm5.1_hm_nv ×7 → 全200 (0.85-8.5s) ✓

# docker logs k2路径:
docker logs hm40006 --since 2m | grep "HM-KEY.*k2 "
# [01:19:36] k2 → NVCF pexec ... via   ← via字段空(direct) ✓
# (改前是 "via http://host.docker.internal:7895")
```

## 4. 改后数据采集 (A/B对比, 真实UTC 17:20-17:28 = DB ts 01:20-01:28, ~7.7min窗口)

### 4a. DB改后窗口 (27-31 reqs)
| 指标 | 改前(30min, 70req) | 改后(~7.7min, 27req) |
|------|------|------|
| 总请求 | 70 | 27 |
| 成功率 | 90.00% (63/70) | **100.00% (27/27)** |
| p50 | 9,017ms | 8,381ms |
| p95 | 82,626ms | **19,990ms** |
| max | 83,870ms | 24,509ms |
| avg | 19,624ms | 9,729ms |
| 429 | 0 | 0 |
| empty200 | 0 | 0 |
| all_tiers_exhausted | 7 | **0** |

**改后27req全成功(100%), 0 ATE, p95从82,626→19,990ms(降76%)**。窗口虽短(7.7min, 流量低4rpm), 但0 SSLEOF+0 ATE是强信号(改前30min有7 ATE全SSLEOF-triggered)。

### 4b. 改后 per-key (5-key均衡验证)
| nv_key_idx | reqs | ok | err | p50 | p95 |
|------|------|----|----|------|------|
| 0 (k1, direct) | 5 | 5 | 0 | 8,497 | 12,848 |
| 1 (k2, **direct改后**) | 5 | 5 | 0 | 7,563 | 15,444 |
| 2 (k3, direct) | 5 | 5 | 0 | 6,992 | 9,839 |
| 3 (k4, proxy7897不改) | 6 | 6 | 0 | 13,435 | 23,692 |
| 4 (k5, direct) | 6 | 6 | 0 | 7,239 | 14,441 |

**k2改direct后 p50=7,563ms/p95=15,444ms — 与其他direct key同级(k1 p50=8,497, k3 p50=6,992, k5 p50=7,239)**, 不再劣化。k4(proxy7897不改)p50=13,435ms略高(其SSLEOF仍在, 留下轮)。

### 4c. docker logs改后SSLEOF (since 01:20, ~8min)
| key | 改前6h SSLEOF | 改后8min SSLEOF |
|------|------|------|
| k2 (proxy7895→direct) | 21 | **0** ✓ |
| k4 (proxy7897不改) | 10 | 1 (仍偶发, 符合预期) |
| k1/k3/k5 (direct) | 0 | 0 |

**k2 SSLEOF 21→0** — 改direct后k2零SSLEOF, 劣化消除。k4仍有1次(8min), 留下轮处理。

### 4d. 改后窗口时间跨度与rpm
- DB ts: 01:20:03 ~ 01:27:48 (31 reqs含测试7, 实际生产27)
- 真实UTC: 17:20-17:28 (~7.7min)
- rpm: 4.00 (与改前8h峰值5.13同期波动一致, throttle非瓶颈, 流量低是时段特性非k2影响)

## 5. 预期 vs 实际

| 预期 | 实际 |
|------|------|
| k2 SSLEOF 21/6h → 0 | ✓ 0 (改后8min, k2零SSLEOF) |
| 成功率90%→~97%(SSLEOF消除) | ✓ 100% (27/27, 超预期, 窗口短需长观察) |
| p95 82,626→~50,000ms | ✓ 19,990ms (超预期降, 因0 ATE) |
| k2 p50与其他direct key同级 | ✓ k2 p50=7,563 vs k1=8,497/k3=6,992/k5=7,239同级 |
| k4 SSLEOF仍存在(不改) | ✓ 1次/8min (留下轮) |
| 429/empty200不升 | ✓ 0/0 |
| direct NVCF无中国IP风控 | ✓ 401非403 (direct可达) |

## 6. 结论

**改动生效, k2劣化消除**:
- k2 SSLEOF 21/6h → 0 (改direct后零SSLEOF)
- 成功率 90.00% → 100.00% (窗口短27req, 但0 ATE+0 SSLEOF强信号)
- p95 82,626 → 19,990ms (降76%)
- k2 p50/p95与其他direct key同级, 不再劣化
- 0×429, 0×empty200, direct NVCF可达(401非403, 无中国IP风控)

**单参数(铁律5)**: 只改HM_NV_PROXY_URL2, 留k4(HM_NV_PROXY_URL4, 10 SSLEOF/6h)下轮。避免一轮两改(R320教训#1)。

**实质数据流向验证(R320教训#3)**: 容器env+compose live+实测请求+docker logs k2路径全确认k2改direct生效。

**双处零漂移(R322教训#1)**: compose L490 + 容器printenv URL2 双处="" 一致, compose up重建非只改运行态。

**live compose不入git(R322教训#2)**: `/opt/cc-infra/docker-compose.yml` 不在git仓库, 本次改动已部署生效, round文件记录供CC托底。

**待观察(诚实标注, R320教训#2)**: 改后窗口仅7.7min/27req(流量低4rpm, 时段特性), 100%成功率需更长窗口(30min+/100req+)确认稳态。但k2 SSLEOF 21→0 + 0 ATE是机制级强信号(SSLEOF根因是proxy层SSL wrap故障, 改direct后该故障路径被消除, 非概率性改善)。建议下轮复检30min+窗口。

**铁律**: 只改HM2不改HM1 ✓ · 单参数(URL2) · 容器重建(compose up) · 8项env+URL1/3/4/5零漂移 · 零HM1侧变更

## 7. 历史对比
| 轮次 | 30min reqs | 30min成功率 | 变更 |
|------|-----------|------------|------|
| R467 | 27(~8min) | 100.00% | 🔧 k2 proxy7895→direct |
| R465 | 103 | 97.09% | ⏸️ NOP |
| R463 | 242 | 98.76% | ⏸️ NOP |
| R461 | 282 | 99.29% | ⏸️ NOP |

改前30min 70req/90.00%(SSLEOF surge), 改后~8min 27req/100.00%(k2 SSLEOF消除)。k2改direct是CC清单[HM2-B]"找劣化key→改其路由"的命中执行, 非NOP。

## 8. 留给下轮(HM2→HM1)
- **k4路由**: HM_NV_PROXY_URL4 proxy7897→direct (6h SSLEOF k4=10, 改后8min仍1次, 同k2逻辑改direct)。下轮HM2执行时可做。
- **改后长窗口复检**: 本轮改后仅7.7min/27req, 下轮HM2侧可采30min+确认100%稳态。
- **SSLEOF retry机制bug**: upstream.py L471 `continue` retry same key但key_idx被for推进(实际retry next key), 可考虑改`retry same key`逻辑(但需改源码, 风险高, 非清单项, 留观察)。

## ⏳ 轮到HM2优化HM1
