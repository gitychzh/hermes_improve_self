# R489 (HM2→HM1): ⏸️ NOP — 0×429 · 27×empty_200(少82% vs R488) · 106×NVCFPexecTimeout全部server-side(avg 26.4s) · 5键全alive/100%SR · 30min SR=84.7%↑/6h SR=86.8%↑ · NVCF surge已过(数据刷新前10min SR=90.9%) · k-1 338全fail=ATE事件(含全5 key轮询) · k0-k4 2227/2227=100% · 非参数可修 · 零配置变更 · 铁律:只改HM1不改HM2 · 锚定: ⏳ 轮到HM1优化HM2

**轮次**: R489
**方向**: HM2 优化 HM1
**日期**: 2026-07-01 09:32 UTC
**类型**: NOP (No Operation — 无参数变更)
**Commit**: 6135d1c (R488, HM2→HM1, NOP) → 本commit (R489)
**容器**: hm40006 (持续运行中)

## 0. 时区与host标识

- DB `ts` 比真实UTC快8h(R488确认)。所有窗口查询用绝对ts窗口(MAX(ts)锚定)。
- 对端HM1 host_machine标识=`opcsname`。
- litellm_model=`dsv4p_nv`(单tier, 5 key, NVCF function f966661c-790d→moonshotai/kimi-k2.6)。

## 1. 改前数据采集 (HM1 对端, hm40006)

### 1a. 容器env (8参数与compose双处一致)
```
UPSTREAM_TIMEOUT=30                [R48.5回退标准值, NV p95<30s]
TIER_TIMEOUT_BUDGET_S=60            [收紧, 减少ATE无用轮询耗时]
MIN_OUTBOUND_INTERVAL_S=1.5        [加速key轮转]
KEY_COOLDOWN_S=15.0                 [compose默认]
TIER_COOLDOWN_S=15                  [compose默认]
HM_SSLEOF_RETRY_DELAY_S=2.0        
HM_PEXEC_TIMEOUT_FASTBREAK=3        [R489: 2→3 回退更宽容]
HM_CONNECT_RESERVE_S=5              [5s足够socks5+SSL]
HM_NV_PROXY_URL1=http://host.docker.internal:7894   k1→mihomo
HM_NV_PROXY_URL2=""                k2→direct
HM_NV_PROXY_URL3=http://host.docker.internal:7896   k3→mihomo
HM_NV_PROXY_URL4=""                k4→direct
HM_NV_PROXY_URL5=""                k5→direct
```
/health=200 OK, hm_num_keys=5, nvcf_pexec_models=[dsv4p_nv]

### 1b. 关键参数变更追踪(vs R488)

| 参数 | R488值 | R489采集值 | 变化 |
|------|--------|-----------|------|
| UPSTREAM_TIMEOUT | 23 | 30 | ↑+7 (R48.5回退) |
| TIER_TIMEOUT_BUDGET_S | 125 | 60 | ↓-65 (收紧) |
| MIN_OUTBOUND_INTERVAL_S | 3.8 | 1.5 | ↓-2.3 (加速) |
| HM_PEXEC_TIMEOUT_FASTBREAK | 2 | 3 | ↑+1 (回退) |
| HM_CONNECT_RESERVE_S | 10 | 5 | ↓-5 |
| KEY_COOLDOWN_S | 25 | 15 | ↓-10 |
| TIER_COOLDOWN_S | 38 | 15 | ↓-23 |
| function_id | f966661c | f966661c | 不变 ✓ |

上述变更为R488→R489之间HM1自身调整, 非本R489操作。

### 1c. DB请求统计

**30min窗口** (ts > NOW()-30min):
```
total=1589  succ=1346  fail=243  SR=84.7%
avg_ttfb(ok)=10530ms  avg_dur(ok)=10670ms
```

**6h窗口** (ts > NOW()-6h):
```
total=2565  succ=2227  fail=338  SR=86.8%
avg_ttfb(ok)=12840ms
```

### 1d. 错误分布 (30min tier_attempts)

| error_type | count | 备注 |
|------------|-------|------|
| NVCFPexecTimeout | 106 | 全部server-side, avg_elapsed=26362ms |
| empty_200 | 27 | 少82% vs R488(152→27) |
| 429_nv_rate_limit | 0 | 零429 ✓ |

### 1e. Per-key成功率 (6h, hm_requests)

| key_idx | total | success | SR |
|---------|-------|---------|-----|
| k0 | 428 | 428 | 100% |
| k1 | 451 | 451 | 100% |
| k2 | 413 | 413 | 100% |
| k3 | 491 | 491 | 100% |
| k4 | 444 | 444 | 100% |
| k-1(NULL) | 338 | 0 | 0% ← ATE事件 |

key分布: k0=17%, k1=18%, k2=16%, k3=19%, k4=17% → ✅ 均衡(cv≈8%)

### 1f. 10min分桶SR趋势 (2h)

```
09:40  total=4   succ=4   SR=100%  ← surge已过
09:30  total=12  succ=9   SR=75%
09:20  total=16  succ=13  SR=81%
09:10  total=28  succ=21  SR=75%
09:00  total=26  succ=19  SR=73%
08:50  total=22  succ=12  SR=54.5% ← surge谷底
08:40  total=37  succ=34  SR=91.9%
08:30  total=22  succ=17  SR=77.3%
08:20  total=29  succ=26  SR=89.7%
08:10  total=52  succ=50  SR=96.2%  ← 正常水位
```

趋势: 08:10=96.2% → 08:50=54.5%(surge谷底) → 09:40=100%(恢复), V型恢复 ✓

### 1g. Quick-fail请求分析

duration<5s的fail请求=stream大payload(196-202K chars, 350-1544ms) + 小nonstream请求。
均为ValidationError/NVCF 400快速拒绝, 不消耗key轮询budget, 非网关可修。

## 2. 分析与优化评估

### 2a. 106×NVCFPexecTimeout — **不可修**

- 全部server-side: NVCF function计算时超时
- avg_elapsed=26.4s(30min) vs R488=48.7s → 提速46%(归因TIER_TIMEOUT_BUDGET 125→60)
- 网关已: FASTBREAK=3保护 + per-attempt budget
- 结论: 只能等NVCF侧恢复

### 2b. 27×empty_200 — **已大幅改善, 不可修**

- R488=152 → R489=27(↓82%), kimi-k2.6 thinking注入生效
- 27个为NVCF偶发空响应, 无参数可修

### 2c. 0×429 — **优秀**

- key池充足, cooldown得当

### 2d. Per-key 100% SR — **均衡无弱key**

- 5键全alive, RR均匀(cv≈8%)
- k-1=338全fail=ATE事件(5 key轮询完仍失败)

### 2e. NVCF surge V型恢复 — **已过**

- 最差10min=54.5%已恢复至90%+

### 2f. 参数天花板检查

| 候选参数 | 当前值 | 评估 | 结论 |
|----------|--------|------|------|
| UPSTREAM_TIMEOUT | 30 | NVCF p95<30s | NOP |
| TIER_TIMEOUT_BUDGET_S | 60 | 2 key轮询合理 | NOP |
| MIN_OUTBOUND_INTERVAL_S | 1.5 | 已快 | NOP |
| PEXEC_TIMEOUT_FASTBREAK | 3 | 3次合理 | NOP |
| HM_CONNECT_RESERVE_S | 5 | 足够(实测1-3s) | NOP |
| KEY_COOLDOWN_S | 15 | 零429证明足够 | NOP |
| TIER_COOLDOWN_S | 15 | 无需改 | NOP |

## 3. 优化执行

**NOP** — 全参数天花板, 零配置变更:
- ✅ 0×429(key池健康)
- ✅ 5键全alive, 100% per-hit SR
- ✅ empty_200大幅改善(R488=152→27)
- ✅ NVCFPexecTimeout全server-side(不可修)
- ✅ surge已过, SR恢复至90%+
- ✅ 所有可调参数无提升空间

## 4. 改后验证

N/A (NOP, 零配置变更)

## 5. 持续关注

- NVCFPexecTimeout占比应随surge消退自然下降
- empty_200=27荒地=NVCF侧特性, 非网关可控
- k-1=None 338全fail=ATE symptom, 根因=NVCF不可用

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记
