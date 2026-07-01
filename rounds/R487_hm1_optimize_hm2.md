# R487 (HM1→HM2): 🚨 NOP-REVEALS-INCIDENT — CC清单[HM2-A/B/C]三项6h+30min新鲜复检全证伪(同R485) · 全参数天花板 · 5键均衡 · **但08:40后HM2突发SR=0%硬故障(NVCF function 4e533b45→pexec 404, 函数已被NVCF下架, 非参数可修)** · 直连实测pexec POST/GED=404(0.5-0.8s稳定), chat/completions v1=200(模型仍存活) · 失败耗时~600ms(direct 404非循环error→immediate ALL-TIERS-FAIL, tiers_tried_count=0) · 零配置变更 · 铁律:只改HM2不改HM1 · 锚定: ⏳ 轮到HM2优化HM1

**轮次**: R487
**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**日期**: 2026-07-01 00:47 UTC (CST 08:47; DB ts 08:47, 快真实UTC 8h)
**类型**: NOP (No Operation — 无参数变更) + 🔴 重大发现(对端HM2当前处于SR=0%硬故障, 非参数可修)
**Commit**: 58d485a (R486, HM2→HM1, NOP, 锚定"轮到HM1优化HM2") → 本commit (R487)

## 0. 时区与host标识 (R320教训#5, R322沿用)

- DB `ts` 比真实UTC快8h。实测: `SELECT now(), max(ts)` → db_now=2026-07-01 00:44:46 UTC, max_ts=2026-07-01 08:40:47, 差8h ✓。所有窗口查询用绝对ts时间戳, 禁用 NOW()。
- 对端HM2 host_machine 标识=`opc2sname`。litellm_model=`nvcf_z-ai/glm-5.1_k1..k5`(5个key各自model名)。
- hm_tier_attempts 表无 host_machine 列, 用绝对ts窗口+`litellm_model LIKE '%glm%'`过滤。
- **本轮定位**: R486(对端HM2→HM1) NOP锚定"轮到HM1优化HM2"。本轮按CC清单HM2节, 用30min+6h新鲜数据复检三项, **三项全证伪(同R485)**, 但本轮数据采集过程中发现HM2自08:40(DB ts)=真实UTC 00:40起突发SR=0%硬故障, 根因非参数(详见§4), 记录供CC紧急勘定。

## 1. 改前数据采集 (HM2 对端, host_machine=opc2sname)

### 1a. 容器env (8参数+5 URL, /opt/cc-infra/docker-compose.yml L469-505 与容器运行态双处一致)
```
UPSTREAM_TIMEOUT=48                (compose L469)   容器env一致 ✓
TIER_TIMEOUT_BUDGET_S=100          (compose L470)   容器env一致 ✓
MIN_OUTBOUND_INTERVAL_S=2.5        (compose L472)   容器env一致 ✓
KEY_COOLDOWN_S=38                  (compose L473)   容器env一致 ✓
TIER_COOLDOWN_S=22                 (compose L474)   容器env一致 ✓
HM_SSLEOF_RETRY_DELAY_S=1.0        (compose L480)   容器env一致 ✓
HM_PEXEC_TIMEOUT_FASTBREAK=5       (compose L482)   容器env一致 ✓
HM_CONNECT_RESERVE_S=8             (compose L505)   容器env一致 ✓
HM_MIN_ATTEMPT_TIMEOUT_S=8         (compose未列, 容器env设置, R434引入可配置)
HM_NV_PROXY_URL1=""               (compose L489)   5键全direct ✓
HM_NV_PROXY_URL2=""               (compose L490)   R467改direct
HM_NV_PROXY_URL3=""               (compose L491)
HM_NV_PROXY_URL4=""               (compose L492)   R468改direct
HM_NV_PROXY_URL5=""               (compose L493)
NVCF_GLM51_FUNCTION_ID=4e533b45-dc54-4e3a-a69a-6ff24e048cb5  (compose L478, R313确定)
```
compose grep与`docker exec hm40006 env`逐字一致 → **双处零漂移** ✓
/health=200 OK (port 40006): `{"status":"ok","proxy_role":"passthrough","hm_num_keys":5,"nvcf_pexec_models":["glm5.1_hm_nv"],"hm_model_tiers":["glm5.1_hm_nv"],"hm_default_model":"glm5.1_hm_nv"}`
(注: /health=ok仅表proxy进程存活, 不代表pexec后端可用 — 见§4)

### 1b. DB 30min窗口聚合 (改前基线, DB ts 08:10-08:40 = 真实UTC 00:10-00:40, 硬故障前稳态)
| 指标 | 数值 |
|------|------|
| 总请求 | 85 |
| 成功 (200) | 71 (83.53%) |
| 失败 (502 ATE) | 14 (16.47%) |
| 429 | 0 |
| empty_200 | 0 |
| p50_ms | 7,300 |
| p95_ms | 55,451 |
| avg_ms | 15,769 |
| max_ms | 92,534 |

### 1c. DB 6h窗口聚合 (DB ts 02:40-08:40 = 真实UTC 18:40-00:40, 含稳态期)
| 指标 | 数值 |
|------|------|
| 总请求 | 841 |
| 成功 (200) | 749 (89.06%) |
| 失败 (502 ATE) | 92 (10.94%) |
| 429 | 0 |
| empty_200 | 0 |
| all_tiers_exhausted | 92 (100% of fails) |
| p50_ok | 7,026ms (5键聚合) |
| p95_ok | 51,510ms |
| avg_fail | 80,618ms (ATE) |
| max_ok | 85,492ms (k3) |
| max_fail | 92,841ms |

### 1d. Per-key 延迟 (6h, success only) — 验证无劣化key([HM2-B]复检)
| Key | Reqs(OK) | p50(ms) | p95(ms) | avg_ok | max_ok |
|-----|----------|---------|---------|--------|--------|
| k0 | 151 | 6,407 | 44,741 | 11,489 | 68,563 |
| k1 | 156 | 7,087 | 52,533 | 13,894 | 61,375 |
| k2 | 150 | 7,061 | 51,995 | 14,037 | 58,082 |
| k3 | 150 | 7,110 | 51,510 | 13,218 | 85,492 |
| k4 | 142 | 6,605 | 44,522 | 12,586 | 60,871 |
| NA | 92(fail) | — | — | — | — |

**6h 5键均衡**: p50 range 6,407-7,110ms (差距仅1.11×, cv≈4%), p95 range 44.5-52.5s, max range 58-85s。
无单key劣化(对照HM1-k4式IP限速不存在), k3 max=85.5s是个别长救援成功非持续趋势。
→ **[HM2-B]证伪**: 无劣化key, 5键全direct活跃。

### 1e. Per-key 延迟 (30min稳态, success only)
| Key | Reqs | Ok | p50(ms) | p95(ms) | max(ms) |
|-----|------|----|---------|---------|---------|
| k0 | 15 | 15 | 7,288 | 33,373 | 46,327 |
| k1 | 13 | 13 | 7,489 | 26,712 | 33,883 |
| k2 | 14 | 14 | 10,805 | 44,691 | 51,882 |
| k3 | 14 | 14 | 6,596 | 51,362 | 56,343 |
| k4 | 15 | 15 | 7,353 | 27,446 | 57,526 |
| NA | 14 | 0 | — | — | — |

30min 5键p50 6.6-10.8s, 全级正常, 与6h一致确认无劣化key。

### 1f. 失败模式 (6h, 02:40-08:40稳态期)
- **92 ATE全部**: error_type=all_tiers_exhausted, status=502, key_cycle_details非空
- **失败耗时分布**:
  - ���速<5s: 8 (8.7%) — 集中在08:34-08:36(硬故障前兆, 见§4), 非稳态
  - 中速5-80s: 4 (4.3%) avg=39,810ms
  - 80-90s: 31 (33.7%) avg=87,560ms — 2×pexec timeout(48.5s)+BUDGET残量
  - 90-93s(break): 49 (53.3%) avg=92,576ms — break at BUDGET-CONNECT_RESERVE=100-8=92s
- **tier_attempts (6h, model LIKE %glm%)**: 38次 NVCFPexecTimeout, avg 48,752ms, p50 48,529ms (单attempt pexec timeout≈48.5s=UPSTREAM)
- **0×429, 0×empty200, 0×SSLEOF** — 连接健康, 全5键direct无代理层错误
- 稳态期失败类型: all_tiers_exhausted (NVCF server-side pexec timeout, 2连~97s≈BUDGET break)

### 1g. 成功请求延迟桶 (6h)
| 桶 | 数量 | 占比 |
|----|------|------|
| <10s | 503 | 67.2% |
| 10-30s | 147 | 19.6% |
| 30-50s | 61 | 8.1% |
| 50-70s | 37 | 4.9% |
| ≥85s | 1 | 0.13% |

max成功=85.5s(k3), 仅1个>70s的成功。BUDGET=100对85.5s成功margin=6.5s(不误杀下限)。

### 1h. 4h小时桶趋势 (DB ts 04:00-08:00 = 真实UTC 20:00-00:00)
| Hour(UTC真实) | Reqs | OK | Fail(ATE) | SR% |
|---------------|------|----|-----------|-----|
| 18:00 | 82 | 80 | 2 | 97.6 |
| 19:00 | 148 | 131 | 17 | 88.5 |
| 20:00 | 129 | 114 | 15 | 88.4 |
| 21:00 | 140 | 125 | 15 | 89.3 |
| 22:00 | 144 | 132 | 12 | 91.7 |
| 23:00 | 89 | 73 | 16 | 82.0 |
| 00:00 | 109 | 94 | 15 | 86.2 |

SR波动82-97.6% (NVCF server-side负载波动, 23:00低点82%已恢复), 失败分布均匀非爆发, 非参数问题。

### 1i. docker logs (稳态期, 真实UTC ~00:24-00:36)
```
[08:24:57.3] [HM-TIMEOUT] tier=glm5.1_hm_nv k4 NVCF pexec timeout: attempt=51124ms total=51131ms
[08:33:50.1] [HM-TIMEOUT] tier=glm5.1_hm_nv k4 NVCF pexec timeout: attempt=48535ms total=48539ms
[08:34:34.1] [HM-TIMEOUT] tier=glm5.1_hm_nv k5 NVCF pexec timeout: attempt=43987ms total=92527ms
[08:34:34.1] [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=0, empty200=0, timeout=2, other=0, elapsed=92528ms
[08:35:46.5] [HM-TIMEOUT] tier=glm5.1_hm_nv k2 NVCF pexec timeout: attempt=48690ms total=48702ms
[08:36:30.0] [HM-TIMEOUT] tier=glm5.1_hm_nv k4 NVCF pexec timeout: attempt=48407ms total=48410ms
[08:36:38.7] [HM-TIMEOUT] tier=glm5.1_hm_nv k1 NVCF pexec timeout: attempt=49707ms total=49720ms
```
- 稳态期失败=2×pexec timeout(48.5s)≈97s=BUDGET break, 0×429/empty200/SSLEOF, 连接健康

## 2. CC清单[HM2-A/B/C]状态评估 (30min+6h新鲜数据, 同R485结论复检)

### [HM2-A] MIN_OUTBOUND 4.5→2.5 — ✅已达成 + 继续降证伪
- 当前=2.5 (R386达成, compose L472+容器env双处一致)
- **继续降证伪**: p50=7,300ms >> 2,500ms throttle (2.92×), throttle非瓶颈
- 30min 85req ≈ 2.83 req/min << throttle天花板(60/2.5=24 req/min), 需求侧远未触达
- 6h 841req ≈ 2.34 req/min, 同样远低于24
- 6h 0×429 → 降throttle无429风险但也无增益
- **结论**: 已达成目标值2.5; 继续降无吞吐增益(需求侧2.34-2.83req/min远低于24天花板), 证伪

### [HM2-B] 失败模式数据补采 + 劣化key检测 — ✅已完成, 证伪
- 6h per-key: 5键p50 6,407-7,110ms同级(差距1.11×, cv≈4%), p95 44.5-52.5s, max 58-85s
- 对照HM1-k4劣化模式(HM1 k4 p95=72.9s vs其他~55s): HM2无此模式
- 5键全direct (HM_NV_PROXY_URL1-5全空, compose L489-493), 无单key IP限速迹象
- 92失败稳态期全server-side NVCFPexecTimeout (tier_attempts 38次avg 48,752ms), 非key级问题
- **结论**: 无劣化key, 无需路由修复, 证伪

### [HM2-C] TIER_TIMEOUT_BUDGET 128→100 — ✅已达成 + 继续降误杀证伪
- 当前=100 (compose L470+容器env一致), break at ~92s (BUDGET-CONNECT_RESERVE=100-8)
- 实测6h: 92 ATE失败 max=92,841ms (恰好break at ~92s), avg=80,618ms
- **继续降误杀分析**:
  - 6h成功请求 max=85,492ms (仅1个>70s的成功, 是k3的85.5s)
  - 80-93s区间80个请求: 31个在80-90s(全是502失败), 49个在90-93s(全是502失败) → BUDGET=100 break在92s不误杀任何成功
  - 降到95 → break at ~87s → 85.5s成功存活但margin仅1.5s (脆弱)
  - 降到90 → break at ~82s → **误杀85.5s的k3成功** (6h 1个, 罕见但真实)
  - 降到80 → break at ~72s → 误杀70-85s成功
- 降BUDGET收益: 92失败×(92-87)=460s/6h ≈ 1.3min/6h, 微不足道
- **结论**: BUDGET=100是85.5s max成功的不误杀下限(break=92s vs max成功85.5s, margin 6.5s); 降到90误杀, 降到95收益微不足道且margin脆弱; 已达最优, 继续降误杀, 证伪

## 3. 其他参数天花板验证 (同R485, 复检确认)

### UPSTREAM_TIMEOUT=48 — 不可降
- 6h成功 max=85,492ms (整体duration含多attempt), 单attempt层面pexec timeout发生在~48.5s (tier_attempts NVCFPexecTimeout avg 48,752ms)
- 降UPSTREAM会让pexec在更早时间timeout, 减少单attempt成功机会; R478论证降误杀3.9-5.7%
- **结论**: UPSTREAM=48保护慢成功, 不可降

### HM_PEXEC_TIMEOUT_FASTBREAK=5 — 死参数
- 6h稳态期: 38次pexec timeout, 但每次ATE走2次pexec timeout(2×48.5s=97s)就BUDGET break, 永远到不了第5次
- 降到3/2: 2次timeout已耗97s≈BUDGET=100, 降FASTBREAK不改变BUDGET先break的事实
- **结论**: 死参数, 降无增益 (注: §4硬故障期此参数同样无关, 404在600ms即return不走timeout路径)

### KEY_COOLDOWN_S=38 / TIER_COOLDOWN_S=22 / HM_SSLEOF_RETRY_DELAY_S=1.0 / HM_CONNECT_RESERVE_S=8 / HM_MIN_ATTEMPT_TIMEOUT_S=8 — 死参数
- 6h 0×429, 0×SSLEOF, 0次cooldown触发, break点115s远未触达CONNECT_RESERVE
- **结论**: 死参数, 全8参数在天花板

## 4. 🔴 重大发现: HM2 自08:40(DB ts)突发SR=0%硬故障 (NVCF function 4e533b45→pexec 404)

### 4a. 事件发现
- 本轮§1数据采集(6h窗口02:40-08:40)显示稳态SR=89.06%, 与R485一致, 三项清单全证伪。
- 但采集过程中实时观察发现: 自DB ts 08:40:39起, HM2所有请求100%失败, SR=0%。

### 4b. 事件窗口数据 (DB ts 08:40-08:47, 真实UTC 00:40-00:47, 7min)
| 指标 | 数值 |
|------|------|
| 总请求 | 6 |
| 成功 (200) | 0 (0.0%) |
| 失败 (502 ATE) | 6 (100%) |
| 快速失败(<5s) | 6 (100%) |
| avg_ms | 1,259 |
| max_ms | 4,539 |

扩展窗口(DB ts 08:35-08:47, 12min): 14req, 0 OK, 14 ATE, **SR=0%** — 持续硬故障。

### 4c. 失败特征 (与稳态期完全不同)
- DB字段: status=502, error_type=all_tiers_exhausted, **tiers_tried_count=0**, **nv_key_idx=NULL**, **key_cycle_details=[]**, tier_model=NULL, error_message=NULL, error_subcategory=NULL
- 稳态期ATE: tiers_tried_count≥1, nv_key_idx有值, key_cycle_details非空(含pexec timeout记录)
- 硬故障期ATE: **tiers_tried_count=0** = proxy未完成任何key的完整尝试即返回
- 失败耗时: 526-4539ms (avg 1259ms), 远低于稳态期ATE的80s+ → 非timeout类失败, 是快速error return

### 4d. docker logs 实证 (硬故障期, /app/logs/hm_proxy.2026-07-01.log L7506-7535)
```
[08:40:39.6] [REQ] model=glm5.1_hm_nv→glm5.1_hm_nv→tier_idx=0 stream=True msgs=2 agent=_hm_nv
[08:40:39.6] [HM-REQ] mapped_model=glm5.1_hm_nv start_tier=glm5.1_hm_nv stream=True tier_chain=['glm5.1_hm_nv']
[08:40:39.6] [HM-TIER] Starting tier=glm5.1_hm_nv model=z-ai/glm-5.1 func=4e533b45-dc5...
[08:40:39.6] [HM-KEY] tier=glm5.1_hm_nv attempt 1/7: k1 → NVCF pexec 4e533b45-dc5... via 
[08:40:40.2] [HM-ALL-TIERS-FAIL] All 1 tiers failed (ring tiers tried: ['glm5.1_hm_nv']), elapsed=624ms, ABORT-NO-FALLBACK
```
- 关键: `HM-KEY`行(via空=direct)之后**直接**`HM-ALL-TIERS-FAIL`, **中间无任何**`HM-TIMEOUT`/`HM-CYCLE`/`HM-CONN`/`HM-ERR`/`HM-TIER-FAIL`日志行
- 6次硬故障请求全部此模式(k1→k2→k3→k4→k5轮转, 每次只试1个key即ALL-TIERS-FAIL)
- 无`HM-TIER-FAIL`行 = `_try_tier_keys`未走完正常return路径, 而是从"Non-cycling error → report"路径提前return(source: upstream.py L~355, resp.status≥400且∉(429,408,500,502))
- 该路径设result.final_resp_status后return, key_cycle_attempts为空(第一次attempt未append即return) → 与DB tiers_tried_count=0/key_cycle_details=[]完全吻合

### 4e. 根因定位: NVCF pexec function 4e533b45 → HTTP 404 (直连实测)
- proxy对端HM2容器env: NVCF_GLM51_FUNCTION_ID=4e533b45-dc54-4e3a-a69a-6ff24e048cb5 (compose L478一致)
- HM2代码pexec路径: `POST https://integrate.api.nvidia.com/v2/nvcf/pexec/functions/{function_id}` (source: upstream.py L194 `nvcf_path = f"/v2/nvcf/pexec/functions/{function_id}"`)
- **直连实测(对端HM2主机, 用NV key1)**:
  ```
  curl -X POST "https://integrate.api.nvidia.com/v2/nvcf/pexec/functions/4e533b45-dc54-4e3a-a69a-6ff24e048cb5" ... 
  → http=404 t=0.618s  (重复3次: 404/0.566s, 404/0.759s, 404/0.508s — 稳定404)
  curl "https://integrate.api.nvidia.com/v2/nvcf/functions/4e533b45-..." (GET)
  → http=404 t=0.542s  (function本身已不存在)
  ```
- 404耗时0.5-0.8s与HM2硬故障ATE的526-4539ms(avg 1259ms)量级吻合(含throttle/connect overhead)
- **404 ∉ (429,408,500,502) → Non-cycling error → immediate return → ALL-TIERS-FAIL** (source逻辑闭环)

### 4f. 对比验证: 模型本身仍存活 (chat/completions v1 = 200)
- **直连实测(对端HM2主机, 同NV key1)**:
  ```
  curl "https://integrate.api.nvidia.com/v1/chat/completions" -d '{"model":"z-ai/glm-5.1",...}'
  → http=200 t=1.06s  (正常返回glm5.1响应: "Hi there! How can")
  curl "https://integrate.api.nvidia.com/v1/models" → 含 "z-ai/glm-5.1" (模型在目录中)
  ```
- 模型z-ai/glm-5.1 + NV key均存活, **仅pexec function 4e533b45被NVCF下架**
- 容器内python urllib可达NVCF /v1/models=200 (网络层正常, 非连接问题)

### 4g. 历史对照 (R313曾处理同类事件)
- R313(2026-06-29)记录: 旧function_id `822231fa`曾404下架, 当时切换到`4e533b45`解决(R313原话: "822231fa已404下架(非SSLEOF); 4e533b45配z-ai/glm-5.1正确返回glm5.1响应; 无更好可换")
- R320/R365/R370/R371/R374等多轮确认4e533b45为ACTIVE直至R485(2026-07-01 00:26 UTC)
- **本轮发现**: 4e533b45自08:40(DB ts)=真实UTC 00:40起同样404下架 (R485数据窗口08:20 cutoff之后发生)
- R313结论"无更好可换"基于06-29状态, 本轮需CC重新勘定当前可用function_id

### 4h. 根因结论
- **HM2硬故障SR=0%根因 = NVCF pexec function 4e533b45被NVCF侧下架(404), 非HM2参数问题**
- CC清单[HM2-A/B/C]三项均为throttle/cooldown/budget参数, 无法修复function 404(function_id是配置值非清单项)
- 修复需: (a)查询用户NVCF账户当前可用的z-ai/glm-5.1 custom function_id并替换NVCF_GLM51_FUNCTION_ID; 或(b)改source从pexec路径切换到chat/completions v1路径。两者均非本轮CC清单项, 且(b)属source改动风险高, 不在本轮工程师权限内。
- 本轮严格只做CC清单1项, 三项全证伪, 且发现清单外阻塞事件 → NOP + 上报CC

## 5. 决策: ⏸️ NOP · 零配置变更 · 🔴上报硬故障

**理由**:
1. CC清单[HM2-A/B/C]三项全部完成/证伪(同R485, 30min+6h新鲜数据复检):
   - A(2.5)达成+继续降证伪(需求2.34-2.83req/min<<24天花板), B数据补采完成+6h 5键p50 cv≈4%无劣化证伪, C(100)达成+继续降误杀(90误杀85.5s成功, 95收益微不足道margin脆弱)证伪
2. 全8参数在天花板: 5个死参数(FASTBREAK/KEY_COOLDOWN/TIER_COOLDOWN/SSLEOF/MIN_ATTEMPT全0触发或不起作用), 3个活跃参数(MIN_OUTBOUND/UPSTREAM/BUDGET)均已达不误杀下限
3. 稳态期(02:40-08:40)失败全为NVCF server-side pexec timeout (2连~97s≈BUDGET break), 非HM2参数可修复
4. 系统稳态: 30min SR 83.53%, 6h SR 89.06%, 4h 5键p50 cv≈4%
5. 零429/零empty200/零SSLEOF — 无连接级劣化
6. UPSTREAM=48保护慢成功, BUDGET=100是85.5s max成功的不误杀下限(margin 6.5s)
7. **🔴新增**: 自08:40(DB ts)起HM2硬故障SR=0%, 根因NVCF function 4e533b45→pexec 404(直连3次实测404+GET 404+模型chat/completions=200交叉验证), 非参数可修, 需CC勘定新function_id或路径切换

**当前HM2参数(稳态期)已达全局最优**: 所有throttle/cooldown在不误杀下限, 失败仅源自NVCF server-side pexec timeout。但当前实际不可用(function 404), 非参数问题。

**🔴 供CC紧急勘定(非本轮可修)**:
- HM2自真实UTC 00:40起SR=0%, 根因NVCF_GLM51_FUNCTION_ID=4e533b45被NVCF下架(pexec POST/GED=404, 模型chat/completions=200)
- 修复路径A: 查询用户NVCF账户当前可用z-ai/glm-5.1 custom function_id, 替换compose L478 NVCF_GLM51_FUNCTION_ID + 容器env + restart
- 修复路径B: 改source upstream.py从pexec路径(`/v2/nvcf/pexec/functions/{id}`)切换到chat/completions v1路径(模型仍存活), 风险较高需source改动+rebuild
- 本轮严格不越权做清单外改动(铁律5: 每轮1项清单; 反对者机制: 不猜测function_id)

## 6. 执行记录

### 变更: 无
```bash
# 零配置变更 — docker-compose.yml不变, 容器不重启
# 本轮为数据驱动NOP: CC清单三项30min+6h新鲜数据复检全部证伪(同R485), 无可动项
# 本轮额外发现HM2硬故障(function 404), 已在§4详述供CC, 本轮不修(非清单项)
```

### 验证: 通过
```bash
# env一致性检查: compose L469-505 与 docker exec hm40006 env 逐字一致, 无漂移
# UPSTREAM=48, BUDGET=100, MIN_OUTBOUND=2.5, FASTBREAK=5, KEY_COOLDOWN=38, TIER_COOLDOWN=22, CONNECT_RESERVE=8, MIN_ATTEMPT=8, 5 URL全空, FUNCTION_ID=4e533b45
# 健康检查 (对端): /health=200 ok (仅表proxy进程存活, pexec后端404不可用, 见§4)
# 直连实测: pexec POST 4e533b45=404×3, GET=404, chat/completions v1=200 (根因锁定)
```

## 7. 轮次统计
- HM2近轮: R472(达成A/C)→R477反向→R478 NOP→R485(对端HM1 NOP复检)→R486(对端HM2 NOP复检)→本R487(NOP+硬故障发现)
- CC清单[HM2-A/B/C]三项状态: A✅达成+证伪, B✅完成+证伪, C✅达成+证伪
- 连续NOP(HM2侧): R478→R487, 每轮证伪都有6h+30min+docker logs具体数据
- **本轮新增**: HM2硬故障SR=0%(function 404), 非参数可修, 已上报CC

## 8. 铁律遵守
- ✅ 只改HM2不改HM1: 无变更行为(NOP), 合规
- ✅ 单参数少改多轮: NOP验证, 无参数
- ✅ 数据驱动先采集后决策: 8层验证(env + 30min + 6h DB + per-key 6h/30min + 失败桶 + tier_attempts + docker logs + 直连pexec/chat实测交叉验证)
- ✅ 零配置变更: docker-compose.yml未修改
- ✅ 无R320/R322/R350重蹈: 未改compose, 未commit错文件, push后即停
- ✅ DB时区: 全部用绝对ts窗口, 禁用NOW()
- ✅ 反对者机制: 每项证伪有具体数据, 硬故障根因有直连实测3次404+GET 404+chat 200交叉验证, 逻辑严密
- ✅ 不越权: 硬故障修复(function_id替换/路径切换)非CC清单项, 严格不猜测不改动, 上报CC

## ⏳ 轮到HM2优化HM1
