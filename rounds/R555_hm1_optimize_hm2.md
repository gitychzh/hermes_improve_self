# R555 (HM1→HM2): NOP — CC清单HM2-A/B/C三项前提全数据证伪 + 清单外6项env候选全否决; empty200-fastbreak源码改动列为下轮候选(样本不足)

## 0. 轮次定位
- 本轮执行者=HM1, 对端=HM2(opc2_uname@100.109.57.26:222).
- 上轮 R554(HM2→HM1)=HM_PEER_FALLBACK_TIMEOUT 50→40 对称对齐HM1.
- 本轮按CC定向清单执行HM2侧(HM2-A/B/C). 经实测, 三项前提数值与清单假设不符(均已被前轮改过), 全部证伪.
- 清单外6项env候选逐一数据否决. 唯一剩余有数据支撑的empty200-fastbreak为源码改动, 当前10min容器样本不足以排除非surge期cycling rescue误杀, 列为下轮候选待更长样本.
- 本轮合规依据铁律: "不允许无操作轮, 除非三项都已做完或数据证伪(证伪需给出具体数据)" — 本轮给出每项具体证伪数据.

## 1. 漂移检测 (每轮起始铁律)

| 参数 | 容器env | live compose | 一致? | 来源 |
|------|---------|--------------|-------|------|
| TIER_TIMEOUT_BUDGET_S | 70 | 70 | ✅ | R554 (80→70) |
| UPSTREAM_TIMEOUT | 52 | 52 | ✅ | R554 (61→52) |
| HM_PEER_FALLBACK_TIMEOUT | 40 | 40 | ✅ | R553 (50→40) |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | 61 | ✅ | R534 |
| MIN_OUTBOUND_INTERVAL_S | 1.0 | 1.0 | ✅ | R518 |
| HM_PEXEC_TIMEOUT_FASTBREAK | 1 | 1 | ✅ | R536 |
| HM_CONNECT_RESERVE_S | 3 | 3 | ✅ | R533 |
| KEY_COOLDOWN_S | 38 | 38 | ✅ | R538 |

**漂移结论**: 无漂移. R554参数(UPSTREAM=52/BUDGET=70)与R553(peer_fb=40)均正确部署且compose与运行态一致.

**注**: R554 round文件只记录了peer_fb 50→40一项, 但live compose注释显示R554实际还改了UPSTREAM 61→52和BUDGET 80→70(容器env确认已生效). 这是R554的记录不全(违反R322教训#4"中途改动未记录"), 但属上轮事项, 本轮不追溯, 仅如实记录当前态.

## 2. CC清单HM2-A/B/C 证伪 (实测数据)

### [HM2-A] MIN_OUTBOUND_INTERVAL_S 4.5→2.5 — 前提证伪 ❌
- 清单假设: HM2 MIN_OUTBOUND=4.5, 降到2.5吞吐+80%.
- **实测**: 容器env `MIN_OUTBOUND_INTERVAL_S=1.0`, live compose=1.0 (R518已从1.2→1.0, R517已从1.5→1.2, R386从5.0→2.5...多轮逐步降到1.0).
- 证伪: 当前1.0已远低于清单假设的4.5; 2.5是R386的旧值, 后续多轮已降至1.0. 降到2.5反而是回退. 1.0下60min零429(见§3), 无降空间.
- **结论: 前提证伪, 不执行.**

### [HM2-B] HM2失败模式数据补采 — 已完成, 5key全均匀无劣化key ❌(无路由可改)
- 清单假设: HM2可能有像HM1-k4那样的劣化key, 若有则改其路由.
- **实测per-key延迟 (60min, 02:31-03:31 UTC, hm_requests WHERE host_machine='opc2sname')**:

| nv_key_idx | cnt | avg_ms | p50_ms | p95_ms | max_ms |
|------------|-----|--------|--------|--------|--------|
| 0 | 253 | 16933 | 10837 | 53285 | 72020 |
| 1 | 247 | 16065 | 9533 | 55208 | 77603 |
| 2 | 244 | 16655 | 10141 | 51637 | 73954 |
| 3 | 241 | 16155 | 10326 | 52738 | 72766 |
| 4 | 242 | 16584 | 10428 | 50274 | 120264 |
| (null=502) | 289 | 65387 | 77292 | 97385 | 97869 |

- 5 key全均匀: avg 16.1-16.9s(±5%), p95 50-55s, max 72-77s(k4的120264是单次NVStream_IncompleteRead异常). 无HM1-k4那样的劣化key(idx=3 avg 16.2s, 非劣化).
- tier_attempts per-key empty_200分布(60min): k0=6,k1=4,k2=4,k3=1,k4=5, 共20条, 均匀.
- 失败结构(status=502): 254×all_tiers_exhausted + 1×NVStream_IncompleteRead. 100% NVCF surge型(empty200+timeout 5key全挂).
- **结论: 5key全均匀, 无劣化key, 无路由可改. 前提证伪(补采完成, 结论无操作).**

### [HM2-C] TIER_TIMEOUT_BUDGET_S 128→100 — 前提证伪 ❌
- 清单假设: HM2 BUDGET=128偏大, 降到100失败早结束28s.
- **实测**: 容器env `TIER_TIMEOUT_BUDGET_S=70`, live compose=70 (R554刚从80→70, R538从100→80, R504从115→128...多轮逐步降到70).
- 证伪: 当前70已远低于清单假设的128; 100是R500/R504的旧值, 后续多轮已降至70. 降到100反而是回退.
- 70是否还能降? 实测成功请求有17个duration在60-70s区间(§3.3), 降BUDGET会误杀这些慢成功. 70下失败路径本地tier在67s fastbreak自然结束(见§4), 无空等.
- **结论: 前提证伪, 不执行.**

## 3. HM2 稳态数据 (60min窗口, 02:31-03:33 UTC)

### 3.1 整体
| total | ok | f502 | e429 | sr% | avg_ms | p50 | p95 |
|-------|-----|------|------|-----|--------|------|------|
| 1572 | 1307 | 265 | 0 | 83.1 | 25775 | 13508 | 77499 |

- SR=83.1%, 零429, 零SSLEOF.
- 失败100% NVCF surge型(all_tiers_exhausted, 265/266; 1×IncompleteRead异常).

### 3.2 502双峰分布 (peer_fb是否触发)
| duration_ms | cnt | 含义 |
|-------------|-----|------|
| <75000 | 112 | tier_fail ~67s + overhead, **未走peer_fb timeout** |
| 75000-100000 | 149 | tier_fail ~67s + **peer_fb 40s timeout** |
| 100000-115000 | 0 | — |
| >115000 | 1 | 异常(IncompleteRead) |

- **149/262=57%的502走了peer_fb 40s空等timeout**(57%触发率).
- peer_fb 60min触发11次: 1成功(ttfb=4ms), 8 timeout(40s), 2 peer-originated即时失败(对端也surge). 成功率9%.
- 112个<75s的502是fastbreak在67s自然break后直接返回(未触发peer_fb或peer_fb即时失败).

### 3.3 成功请求duration分布
| 区间 | cnt | 说明 |
|------|-----|------|
| <5s | 278 | 快成功(first attempt, NVCF idle) |
| 5-30s | 774 | 主力(glm5.1 thinking正常耗时) |
| 30-60s | 189 | 慢thinking |
| 60-70s | 17 | 接近BUDGET的慢成功(降BUDGET会误杀) |
| >70s | 10 | peer_fb救回或边界 |

- 成功ttfb分布: <5s=317, 5-15s=529, 15-30s=250, >30s=208. 连续无显著双峰(无法干净区分first-attempt vs cycling-rescue).

## 4. 失败路径wall-clock解剖 (docker logs hm40006)

典型surge期失败链(11:31:14 TIER-FAIL, elapsed=67828ms):
- 5 key各试1次: 4×empty_200(NVCF surge空返, 每个~13s) + 1×pexec_timeout(~7s, attempt=6979ms)
- empty_200不触发fastbreak(源码: `consecutive_pexec_timeout=0` reset on empty_200), cycling到下key
- 第1个pexec_timeout触发FASTBREAK=1 → break, elapsed≈67s < BUDGET=70s 自然break
- → peer_fb触发 → 对端也surge → 40s timeout → 502 (总~107s)

**关键源码确认** (upstream.py:292):
```python
if is_empty:
    _log("HM-EMPTY-CYCLE", f"tier={tier_model} k{key_idx+1} empty 200, cycling")
    consecutive_pexec_timeout = 0  # R347: reset (empty_200 != timeout)
    continue  # ← 不fastbreak, 继续试下个key
```

- empty_200主导的surge期, FASTBREAK=1几乎不省时间(因timeout出现在最后, 前面4个empty_200已耗~52s).
- BUDGET=70下本地tier fail在67s break, 无额外空等(R554的BUDGET=70已生效).

## 5. 清单外6项env候选逐一否决

| 候选 | 当前值 | 否决理由(数据) |
|------|--------|----------------|
| MIN_OUTBOUND 1.0→更低 | 1.0 | 60min零429, throttle已非瓶颈(失败100%NVCF surge非限流) |
| TIER_TIMEOUT_BUDGET 70→更低 | 70 | 成功有17个在60-70s, 降会误杀慢成功; 失败路径已67s fastbreak无空等 |
| UPSTREAM_TIMEOUT 52→更低 | 52 | R554刚降; thinking请求实际用FORCE_STREAM_UPGRADE_TIMEOUT=61 override, UPSTREAM仅影响非thinking(极少) |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT 61→更低 | 61 | glm5.1 thinking实测16-63s; 成功ttfb 50-61s有55个, 30-50s有133个, 降会误杀thinking慢成功 |
| HM_PEER_FALLBACK_TIMEOUT 40→更低 | 40 | R553刚降(50→40); 历史最慢peer_fb成功实例24s(R553记录), 40→30余量仅1.25x偏紧; 连续两轮动同参数违反少改多轮 |
| HM_PEXEC_TIMEOUT_FASTBREAK 1→更高 | 1 | 当前empty_200不触发fastbreak, 调高FASTBREAK只影响pexec_timeout计数, empty_200主导路径无变化 |

## 6. 唯一剩余候选: empty200-fastbreak (源码改动, 列为下轮, 本轮不执行)

### 6.1 改动设想
upstream.py 加 `consecutive_empty_200` 计数器, 连续N个empty_200即fastbreak(类比R347的pexec_timeout fastbreak). surge期4×empty_200耗~52s, 若连续2个empty_200即break, 省~39s/次.

### 6.2 数据支撑(强)
- 容器生命周期(03:22启动, 10min)内46个SUCCESS**全部first attempt**, 0个cycling-rescue.
- 60min 14次EMPTY-CYCLE, 0次后续key救回成功.
- R549 NOP轮历史结论: "失败100%kimi_nv surge(empty200+timeout@77s)", 多轮7h+peer_fb 0成功.

### 6.3 风险(为何本轮不执行)
- 10min容器样本太短, 无法排除**非surge期偶发empty_200后cycling rescue**的存在.
- 源码改动(非env)风险高于env; 铁律5"单参数少改多轮"倾向env优先.
- 若误杀非surge期cycling rescue → SR下降, 违反"稳定优先".
- 需更长样本(数小时跨surge/非surge周期)证明cycling rescue率≈0, 或结合R551 func_health surge状态门控(架构级, 超单参数).

### 6.4 下轮建议
- HM2侧采更长窗口(4h+)的EMPTY-CYCLE→SUCCESS后继率, 若确实≈0, 可实施empty200-fastbreak(源码, N=2或3).
- 或结合func_health surge状态: 仅在surge标志位时empty_200 fastbreak, 非surge期仍cycling(架构级, 需用户授权).

## 7. 铁律检查

| 铁律 | 状态 | 说明 |
|------|------|------|
| 只改HM2, 不改HM1 | ✅ | 本轮NOP, HM1/HM2均未改 |
| 单参数少改多轮 | ✅ | NOP, 无参数变动 |
| 数据驱动 | ✅ | A/B/C三项+清单外6项全有实测数据证伪 |
| 漂移检测 | ✅ | §1确认8项env无漂移 |
| 改后验证 | N/A | NOP无改动, 无需改后验证 |
| 不允许无操作轮(例外: 三项证伪) | ✅ | A/B/C三项前提全证伪+具体数据, 符合例外条款 |

## 8. CC清单更新

- [HM2-A] MIN_OUTBOUND 4.5→2.5: ❌ 前提证伪(实=1.0, 已低于2.5)
- [HM2-B] 失败模式补采+劣化key路由: ❌ 补采完成, 5key全均匀无劣化
- [HM2-C] BUDGET 128→100: ❌ 前提证伪(实=70, 已低于100)
- **清单外候选**: 6项env全否决; empty200-fastbreak源码改动列为下轮候选(待更长样本)

## 9. 本轮稳态确认(无回归)
- SR 83.1%(60min) / 82.3%(最近15min), 与R554后稳态一致, 无回归.
- 零429, 零SSLEOF, 失败100%NVCF surge型.
- 5key全均匀, peer_fb 40s已生效(R553), BUDGET=70/UPSTREAM=52已生效(R554).

---

*单参数少改多轮. 铁律:只改HM2不改HM1. 本轮NOP依据CC清单HM2-A/B/C三项前提全数据证伪+清单外6项env候选全否决; empty200-fastbreak源码改动列为下轮候选(当前样本不足).*

## ⏳ 轮到HM2优化HM1
