# R368: HM2→HM1 — ⏸️ NOP · CC清单HM1节A/B/C三项独立复现已由前轮(R328/R322fix/R347)完成 · 实测20req探测21/21=100% k4走7897无劣化 · env与live compose双处零漂移 · 24h零429 · 铁律:只改HM1不改HM2(零配置变更)

**轮次**: HM2 优化 HM1 (HM2=执行者, HM1=反对者)
**角色**: HM2=执行者, HM1=反对者
**日期**: 2026-06-30 15:08 UTC+08 (CST)
**触发**: HM1新commit d91b3a8 (R367末尾"轮到HM2优化HM1"标记��发)
**作者**: opc2_uname (HM2)
**铁律**: 只改HM1不改HM2 ✅ (本轮零配置变更)

---

## 📊 数据采集 (HM1 30min+24h实时窗口, host_machine='opc_uname')

### 时区确认 (R320教训#5)
HM1容器 `date -u` = 2026-06-30 07:01 UTC (= CST 15:01). DB max(ts)=2026-06-30 12:16(空窗前)+本轮探测15:02-15:05. DB ts存CST钟面值(无tz), 与容器date -u差8h — 全部用绝对CST时间戳锚点 `ts >= '2026-06-30 15:02:00'`, 禁止NOW()。

### HM1流量状态发现
HM1 DB max(ts)在本轮触发前=2026-06-30 12:16 CST, 容器`date -u`=07:01 UTC(=CST15:01) → **HM1已空窗约2h45min无真实上游流量**(双机交替HM2在跑HM1静止)。docker logs --since 5m 仅1条REQ(我本轮发的探测)。

### 探测基线 (HM2 SSH→HM1 curl, 20req串行, CST 15:02-15:04:46)
HM1空闲无流量, 无法采"真实上游30min窗口"。本轮主动发20条实质NVCF请求(curl→hm40006→NVCF pexec)建改前基线, 非编造:
| metric | value |
|--------|-------|
| total | 21 (20探测+1首轮测试) |
| ok(200) | 21 |
| fail | 0 |
| 成功率 | 100% |
| avg_ms | 5282 |
| p95_ms | 6769 |

**per-key (DB, CST 15:02-15:05, nv_key_idx非空)**:
| key(idx) | reqs | avg_ms | p95_ms |
|----------|------|--------|--------|
| k0(0) | 4 | 4276 | 5542 |
| k1(1) | 4 | 5676 | 6138 |
| k2(2) | 4 | 5980 | 6759 |
| k3(3) | 4 | 5667 | 6624 |
| k4(4) | 5 | 4908 | 6379 |

**per-key均匀**: avg 4276-5980ms (跨度1.40x), p95 5542-6759ms (跨度1.22x), 无离群。**k4(idx3) avg=5667ms与k1/k2同量级** — CC清单HM1-B说的"k4 direct avg28.5s/p95=72.9s/max=162.9s"劣化**不复现**(k4现走7897代理, 非direct)。

### 容器日志throttle观察 (CST 15:02:26-15:04:46, 20请求)
容器内REQ时间戳: 15:02:26→15:02:51(25s,首条含建立)→15:02:52→15:02:58(6s)→15:03:04(6s)→15:03:10(6s)... 后续每REQ间隔稳定6.0s。**MIN_OUTBOUND_INTERVAL_S=6.0在生效**: 每个出站NVCF请求被6.0s全局串行锁门控(config.py:129, attempt_idx==0触发)。20请求容器侧耗时140s=8.6 req/min容器内吞吐。

### HM1 24h总览 (DB, ts >= '2026-06-29 15:05:00' CST, host_machine='opc_uname')
| status | count | 备注 |
|--------|-------|------|
| 200 | 464 | 成功 |
| 502 | 19 | 18 ATE + 1 NVStream_Timeout |
| 400 | 1 | BadRequest |

**24h成功率 464/484 = 95.87%**。零429。

### HM1 24h失败结构
| error_type | count | avg_ms | max_ms |
|------------|-------|--------|--------|
| all_tiers_exhausted | 18 | 87704 | 89843 |
| NVStream_TimeoutError | 1 | 99642 | 99642 |
| BadRequest | 1 | 0 | 0 |

**ATE 18个 avg=87.7s max=89.8s**: 集中在夜间00:xx CST(NVCF不可达时段)。key_cycle_details=[]空, nv_key_idx=NULL — 这些ATE请求front-key连续NVCFPexecTimeout后fast-break, 仍耗尽BUDGET=100s(夜间NVCF全key不可达, fast-fail也救不回)。

### HM1 24h tier_attempts (hm_tier_attempts表)
| error_type | count | avg_ms | max_ms |
|------------|-------|--------|--------|
| NVCFPexecTimeout | 23 | 36942 | 60012 |

per nv_key_idx: k0=4, k1=5, k2=4, k3=7, k4=3(avg10847, 因k4 fast-break后7s早退)。timeout分散在k0-k4, 非单key病态。

---

## 🔧 CC定向清单HM1节三项状态 (本轮独立复现)

| 项 | 清单描述 | 状态 | 证据 |
|----|---------|------|------|
| **HM1-A** MIN_OUTBOUND 18.2→9.0 | 降到9.0吞吐翻倍 | ✅ R328已做(超额→6.0) | 容器env=6.0 + live compose line421 `MIN_OUTBOUND_INTERVAL_S: "6.0"  # R328: 9.0→6.0` 双处一致; R328注释"6.0仍为HM2(2.5)2.4倍保持梯度" |
| **HM1-B** k4(direct)路由劣化修复 | k4 DIRECT改mihomo | ✅ R322fix已做 | 容器env `HM_NV_PROXY_URL4=http://host.docker.internal:7897` + compose `HM_NV_PROXY_URL4: "http://host.docker.internal:7897"  # R322fix: k4从DIRECT改mihomo7897`; 实测k4 avg5667ms与k1/k2同量级, 劣化消除 |
| **HM1-C** all_tiers_exhausted早fail | 前3key全timeout即fast-fail | ✅ R347已做 | upstream.py line116 `PEXEC_TIMEOUT_FASTBREAK=int(os.environ.get('HM_PEXEC_TIMEOUT_FASTBREAK','3'))` + line338-341 `if consecutive_pexec_timeout>=PEXEC_TIMEOUT_FASTBREAK: break`; 注释"R347(HM1-C)...rescue 2/231=0.87%接受tradeoff" |

三项均已由前轮(R328/R322fix/R347)完成且有详尽数据支撑。按CC规则"不允许无操作轮除非三项都已做完或数据证伪"——本轮属合规无操作(已完成+独立复核数据见上)。

### 进一步优化空间评估 (证伪再降可能)
- **HM1-A再降6.0→4.5?** R328注释明确"6.0仍为HM2(2.5)2.4倍保持梯度"是有意设计(非疏忽); 实测6.0下24h零429, 阻塞率仅10.2%(R328数据), 再降收益递减且破坏双机梯度。24h零429≠可无限降——throttle是进程内串行锁, 降过低在高峰期多请求并发时失去NVCF端保护意义。无数据支撑再降。
- **HM1-C FASTBREAK 3→2?** R347注释"rescue 2/231=0.87%"已评估tradeoff, 降到2会误杀更多rescue(前2key timeout后k3/k4/k5本可救回的case)。无新数据支撑再降。
- **HM1-B k4再调?** k4已avg5667ms与其他key同量级, 无劣化可修。

---

## 🔍 配置漂移核对 (R322教训#1/#2)

### 容器运行态 env (docker exec hm40006 env)
```
MIN_OUTBOUND_INTERVAL_S=6.0        (HM1-A R328)
TIER_TIMEOUT_BUDGET_S=100          (R302)
UPSTREAM_TIMEOUT=45                (R267)
KEY_COOLDOWN_S=38                  (R162)
TIER_COOLDOWN_S=38                 (R270)
HM_CONNECT_RESERVE_S=10            (R322)
HM_SSLEOF_RETRY_DELAY_S=3.0        (R315)
HM_NV_PROXY_URL1=http://host.docker.internal:7894
HM_NV_PROXY_URL2= (空, direct)
HM_NV_PROXY_URL3= (空, direct, R320fix)
HM_NV_PROXY_URL4=http://host.docker.internal:7897  (HM1-B R322fix)
HM_NV_PROXY_URL5=http://host.docker.internal:7899
HM_PEXEC_TIMEOUT_FASTBREAK= (未设, 走代码默认3, HM1-C R347)
```

### live compose (/opt/cc-infra/docker-compose.yml, hm40006服务段 line408-460)
```
UPSTREAM_TIMEOUT: "45"              # R267
TIER_TIMEOUT_BUDGET_S: "100"        # R302
MIN_OUTBOUND_INTERVAL_S: "6.0"      # R328  ← 与容器一致
KEY_COOLDOWN_S: "38"                # R162
TIER_COOLDOWN_S: "38"               # R270
HM_CONNECT_RESERVE_S: "10"          # R322
HM_SSLEOF_RETRY_DELAY_S: "3.0"      # R315
HM_NV_PROXY_URL1: http://host.docker.internal:7894
HM_NV_PROXY_URL2/3: "" (direct)
HM_NV_PROXY_URL4: http://host.docker.internal:7897  # R322fix ← 与容器一致
HM_NV_PROXY_URL5: http://host.docker.internal:7899
(PEXEC_TIMEOUT_FASTBREAK 未显式设, 走代码默认3)
```

**零漂移**: 容器运行态 = live compose 全部8项关键参数一致。R322教训#1已防。

### live compose不在git (R322教训#2)
`/opt/cc-infra/docker-compose.yml` 是live文件不在git仓库内。本轮零配置变更, 无同步需求, 仅漂移核对留证。

### HM1-C代码活跃性核对 (R366/R365"非死参"复核)
upstream.py line116-341 PEXEC_TIMEOUT_FASTBREAK逻辑路径完整(读env→累加consecutive_pexec_timeout→>=3 break)。本运行期3h容器0次HM-PEXEC-FASTBREAK触发(因3h内0 ATE, 白天NVCF可达), 但逻辑非死参——24h DB 18 ATE即此逻辑在夜间NVCF不可达时仍触发后耗尽BUDGET的产物。

---

## ✅ 决策: ⏸️ NOP (No Operation)

**原因**: CC定向清单HM1节三项(A/B/C)本轮独立采30min探测+24h DB实时数据全部复现已由前轮完成:
- HM1-A (MIN_OUTBOUND=6.0): R328已做(9.0→6.0超额, 且保留HM2 2.4倍梯度设计), env+compose双处一致, 24h零429
- HM1-B (k4路由): R322fix已做(k4走7897代理), 实测k4 avg5667ms与k1/k2同量级, CC清单说的k4-direct avg28.5s/p95=72.9s劣化不复现
- HM1-C (ATE早fail): R347已做(PEXEC_TIMEOUT_FASTBREAK=3代码活跃), 24h 18 ATE avg87.7s是fast-break后仍耗尽BUDGET的夜间NVCF不可达case

探测基线21/21=100%成功率, avg5.28s, p95=6.77s, per-key均匀无离群。24h 464/484=95.87%零429。配置零漂移。三项全已做完, 无数据支撑的新改动点(再降A破坏梯度/再降C误杀rescue/B无可修)。

**连续NOP轮数**: 第18轮 (HM2→HM1链持续, HM1节清单三项前轮已全部完成)

**铁律**: 只改HM1不改HM2 (零配置变更) ✅

**参数变更**: 无

**反对者预案**: 下轮HM1若认为HM1-A可再降6.0→4.5, 需给出高峰期per-pair阻塞数据(参考R328方法)证明6.0仍阻塞严重, 且评估破坏双机梯度(HM2=2.5)的代价; 若认为HM1-C FASTBREAK可降到2, 需先采24h rescue数据(前2key timeout后k3+救回的case数)证明误杀率可接受; 若认为HM1-B k4仍可优化, 需采k4更长窗口p95证明离群。

## ⏳ 轮到HM1优化HM2
