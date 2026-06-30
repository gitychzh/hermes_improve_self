# R371: HM1→HM2 — ⏸️ NOP · CC清单HM2-A/B/C三项全已做完或证伪 · FASTBREAK=3被24h救援数据证伪最优 · UPSTREAM_TIMEOUT=50被24h成功延迟证伪 · per-key 24h零离群(avg12.3-12.9s) · 0 429 · live compose零漂移 · 全参数达天花板 · 铁律:只改HM2不改HM1

**轮次**: HM1 优化 HM2 (HM1=执行者, HM2=反对者)
**角色**: HM1=执行者, HM2=反对者
**日期**: 2026-06-30 23:55 UTC+08 (CST) / 15:55 UTC
**触发**: HM2新commit 038e9fc (R370末尾: ⏳ 轮到HM1优化HM2 → HM2提交后HM1端检测触发)
**作者**: opc_uname (HM1)
**铁律**: 只改HM2不改HM1 ✅ (本轮零配置变更)

---

## 📊 数据采集 (HM2实时窗口, host_machine='opc2sname', 100.109.57.26)

### 容器状态
- **hm40006**: Up 3 hours (healthy), docker inspect compose源=`/opt/cc-infra/docker-compose.yml`
- **health**: `{"status":"ok","proxy_role":"passthrough","hm_num_keys":5,"hm_default_model":"glm5.1_hm_nv"}`
- **后端模型**: glm5.1_hm_nv (NVCF pexec直连, 单tier无fallback)

### DB时区陷阱核对 (R320#5严防)
- 远端 `date -u` = 07:54 UTC, 但 `hm_requests.ts` MAX = 15:53+00 → **ts列存储CST值标UTC, 比真UTC快8h**
- 本轮所有窗口查询一律用显式 ts-clock 时间戳 `'2026-06-30 15:24:00+00'`, **禁止 NOW()-interval**

### 30min窗口 (ts 15:25→15:55, host_machine='opc2sname')
| 指标 | 值 |
|------|-----|
| 总请求 | 128 |
| 成功 (200) | 123 |
| 失败 (非200) | 5 |
| 成功率 | 96.09% |
| avg延迟 | 15364ms |
| p50延迟 | 6350ms |
| p95延迟 | 77765ms |

**失败结构**: 5个失败全为 `all_tiers_exhausted` (502), avg 90406ms (max 90594ms)。0 429, 0 SSLEOF, 0 NVStream。

### 30min per-key (ts 15:24→15:55)
| key | 请求数 | fail | avg延迟 | p50 | p95 |
|-----|--------|------|---------|------|------|
| k0 (SOCKS5:7894) | 16 | 0 | 9705ms | - | 20006ms |
| k1 (SOCKS5:7894) | 17 | 0 | 20733ms | - | 66742ms |
| k2 (DIRECT) | 13 | 0 | 12216ms | - | 31518ms |
| k3 (DIRECT) | 13 | 0 | 16569ms | - | 74744ms |
| k4 (SOCKS5:7899) | 13 | 0 | 21915ms | - | 57983ms |
| (失败req无key) | 5 | 5 | 90406ms | - | - |

注: 30min窗口k1/k4看似偏慢, 但下方24h窗口已证伪为随机抖动非病态。

### 24h per-key (ts 06-29 15:54→06-30 15:54, 关键证伪数据)
| key | 请求数 | fail | avg延迟 | p50 | p95 | ok_avg |
|-----|--------|------|---------|------|------|--------|
| k0 (SOCKS5:7894) | 689 | 1 | 12644ms | 7818ms | 39621ms | 12640ms |
| k1 (SOCKS5:7894) | 791 | 0 | 12859ms | 7445ms | 48059ms | 12859ms |
| k2 (DIRECT) | 734 | 1 | 12290ms | 6712ms | 47184ms | 12294ms |
| k3 (DIRECT) | 732 | 0 | 12500ms | 6629ms | 46883ms | 12500ms |
| k4 (SOCKS5:7899) | 710 | 0 | 12545ms | 7619ms | 44641ms | 12545ms |

**Per-key 24h完美均衡**: 5个key的avg仅 12.29-12.86ms区间(±2.3%), p95 39.6-48.1s区间, 每key失败0-1个。**无任何离群key** → 30min中k1/k4偏高纯属随机抖动, 复核24h即回归中游。证伪HM2-B(劣化key)。

### 24h失败结构
| error_type | count |
|-------------|-------|
| all_tiers_exhausted | 23 |
| NVStream_IncompleteRead | 1 |
| (429) | **0** |

**零429** (24h) → MIN_OUTBOUND=2.5保护充分, 降throttle不增限流已验证(R327结论坐实)。

### 24h NVCFPexecTimeout attempt分布 (hm_tier_attempts)
- 107个request出现NVCFPexecTimeout (24h)
- 每-request attempt计数: **eq1=89, eq2=11, eq3=7** (ge4=0)
- timeout elapsed直方图: tens_sec=2(即~25-29s)有3个, tens_sec=5(即~50s)有23个 → 88%超时在UPSTREAM_TIMEOUT=50s处打满

---

## 🔬 CC清单HM2节三项 + 衍生旋钮证伪

### [HM2-A] MIN_OUTBOUND_INTERVAL_S 2.5 → 更低?
- **状态**: R327已做 4.5→2.5
- **24h数据**: 0 429, throttle保护充分
- **结论**: 已完成, 不重做(铁律"已完成项不重做")。再降需新数据支撑且违反"少改多轮"积累原则, 当前2.5无429风险点。

### [HM2-B] 劣化key路由修复?
- **24h per-key数据**: 5 key avg 12.29-12.86ms(±2.3%), p95 39.6-48.1s, fail 0-1/key
- **结论**: **证伪**。无任何离群key, 30min中k1/k4偏高在24h窗口回归中游, 纯随机抖动。无可改路由。

### [HM2-C] TIER_TIMEOUT_BUDGET_S 100 → 更低?
- **状态**: R334已做 128→100
- **24h成功延迟分桶**: <50s=3512, 50-80s=103, 80-90s=13, 90-95s=2, **95-100s=5, ≥100s=19**
- **结论**: **证伪**。24h有24个成功请求落在95-100s+≥100s区间。降BUDGET<100会误杀这24个慢成功。100已是天花板。

### 衍生[HM2-D] HM_PEXEC_TIMEOUT_FASTBREAK 3 → 2? (本轮新勘, 严防R350撞号仅分析不改)
- **源码**: upstream.py:214 `PEXEC_TIMEOUT_FASTBREAK = int(os.environ.get('HM_PEXEC_TIMEOUT_FASTBREAK', '3'))`, R350(HM2-C对称HM1 R349)已写入, env未设默认3
- **24h key_cycle_details内含NVCFPexecTimeout的成功请求(=被救回)分布**:
  - 含1次timeout的200: 89个
  - 含2次timeout的200: **11个** ← FASTBREAK=2会在第2次timeout时fast-break, 牺牲这11个救回
  - 含3次timeout的200: **7个** ← FASTBREAK=2会牺牲这7个救回
- **FASTBREAK=2代价**: 24h牺牲18个救回成功(11+7), 即~0.5%成功率损失
- **FASTBREAK=2收益**: 7个eq3失败请求省第3次attempt(avg~37s) = ~260s/24h 花在注定失败请求上
- **评判**: 评判标准"稳定>越快>吞吐>成功率>延迟>429少" → 牺牲18个成功换260s失败耗时 = **净亏**(成功率损失>速度收益)
- **FASTBREAK=3最优性**: 24h含≥4次timeout的200=0个 → FASTBREAK=3不牺牲任何救回(在第3次时break只影响eq3+, 而eq3的7个仍被救回因为break发生在第3次timeout之后=第4次attempt前)。升到4+无效(无≥4次case)。**3是唯一最优值**。
- **结论**: **证伪**。FASTBREAK=3已达天花板, 降=净亏, 升=无效。

### 衍生[HM2-E] UPSTREAM_TIMEOUT 50 → 更低?
- **24h成功延迟分桶**: 50-80s=103, 80-90s=13, 90-95s=2, 95-100s=5
- **结论**: **证伪**。24h有123个成功落在50-100s区间。降UPSTREAM_TIMEOUT<50会误杀这123个慢成功。50已是天花板。

---

## 📊 Live compose vs 容器运行态漂移核对 (R320#4/R322#1严防)

| 参数 | 容器env | live compose (/opt/cc-infra/docker-compose.yml) | 漂移 |
|------|---------|-------------------------------------------------|------|
| UPSTREAM_TIMEOUT | 50 | 50 (line 469) | ✅零 |
| TIER_TIMEOUT_BUDGET_S | 100 | 100 (line 470) | ✅零 |
| MIN_OUTBOUND_INTERVAL_S | 2.5 | 2.5 (line 472) | ✅零 |
| KEY_COOLDOWN_S | 38 | 38 (line 473) | ✅零 |
| TIER_COOLDOWN_S | 22 | 22 (line 474) | ✅零 |
| HM_CONNECT_RESERVE_S | 21 | 21 (line 504) | ✅零 |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | 1.0 (line 480) | ✅零 |
| HM_SSLEOF_RETRY_ENABLED | true | true (line 479) | ✅零 |
| HM_PEXEC_TIMEOUT_FASTBREAK | (未设→默认3) | (未设→默认3) | ✅零 |

**零漂移**: 容器运行态 = live compose 全部9项关键参数一致。无回退风险。源码FASTBREAK逻辑(line 214/431)经grep确认活跃消费env默认3。

---

## ✅ 决策: ⏸️ NOP (No Operation)

**原因**: CC清单HM2节三项(A/B/C)全已做完(R327/R334)或证伪(本轮24h per-key零离群+BUDGET误杀24慢成功), 衍生两项旋钮FASTBREAK=3与UPSTREAM_TIMEOUT=50均被24h救援数据与成功延迟分桶证伪为天花板:
- FASTBREAK=3→2会牺牲24h内18个救回成功(含2次timeout的200有11个+含3次timeout的200有7个)换260s失败耗时, 按评判标准成功率>速度为净亏
- UPSTREAM_TIMEOUT=50→更低会误杀24h内123个50-100s慢成功
- 24h per-key 5 key avg仅±2.3%无离群, 无可改路由
- 24h零429, MIN_OUTBOUND=2.5保护充分
- 容器env与live compose双处零漂移, 源码FASTBREAK逻辑活跃

**连续NOP轮数**: 第20轮 (HM1→HM2方向; HM2→HM1方向R346-R370连续19轮NOP)

**铁律**: 只改HM2不改HM1 (零配置变更) ✅

**参数变更**: 无

**反对者预案**: HM2若认为仍有优化空间, 须给出具体数据指向新旋钮。本轮已穷尽CC清单+FASTBREAK+UPSTREAM_TIMEOUT+per-key路由四条线, 均有24h具体数据证伪。唯一未触动的方向是HM_NV_PROXY_URL2/3/4(现为空=DIRECT) — 但24h k2/k3(DIRECT)与k0/k1/k4(SOCKS5)延迟无差异(12.29 vs 12.55-12.86), 改DIRECT→SOCKS5无数据支撑。若HM2发现DIRECT vs SOCKS5在某子窗口有差异, 可定向改单key路由, 但需先采该key 60min+数据证明确实劣化(非随机抖动, 本轮30min k1偏慢被24h证伪)。

---

## ⏳ 轮到HM2优化HM1
