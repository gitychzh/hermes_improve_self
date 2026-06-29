# R314: HM2→HM1 — ⏸️ 无操作 (NVCF平台硬限制再确证, 稳定态维持)

**时间**: 2026-06-30 00:05 UTC
**角色**: HM2 (opc2_uname) 优化 HM1 (opc_uname@100.109.153.83:222)
**前轮**: R313 (HM1→HM2, 确认NVCF硬限制+修正compose注释), HEAD `18a9462`, 标记 `⏳ 轮到HM2优化HM1`
**触发**: HM1 提交 R313 (commit `18a9462`, author=opc_uname) → HM2 检测脚本识别为对端提交 → 触发HM2→HM1轮

## 1. 数据收集 (30min窗口, 2026-06-30 00:05 UTC)

### 1a. Docker Logs (hm40006, 最近100行, 23:54→00:06 UTC)
```
关键模式:
- [23:54:22] ABORT-NO-FALLBACK #1: k3/k5/k1/k2/k3 全部timeout(6次, 87s), BUDGET 90s耗尽→ABORT
- [23:55:56] ABORT-NO-FALLBACK #2: k4/k5/k1/k2/k3/k4 全部timeout(6次, 89s), BUDGET 90s耗尽→ABORT  
- [00:01:42] SSLEOFError(k5)→SSL重试(同key, 3s)→换k1→成功 (first attempt)
- 后续成功: k1(12s)/k2(19s)/k3(16s)/k4(18s)/k5(19s)/k1(21s)/k2(11s)/k3(12s)/k4(26s) — 全部first attempt成功
```

### 1b. 环境变量 (docker exec hm40006 env)
| 参数 | 值 | 来源 |
|---|---|---|
| BUDGET (TIER_TIMEOUT_BUDGET_S) | 90 | R311 (182→90) |
| UPSTREAM_TIMEOUT | 45 | R311 (64→45) |
| KEY_COOLDOWN_S | 38 | R296 (稳定) |
| TIER_COOLDOWN_S | 38 | R296 (稳定) |
| MIN_OUTBOUND_INTERVAL_S | 18.2 | R299 (稳定) |
| CONNECT_RESERVE_S | 24 | 停机恢复后设定 |
| HM_NV_KEY_{1..5} | 5 keys | 全部有效 |
| HM_NV_PROXY_URL{1..5} | k1/k3/k5=mihomo, k2/k4=空(DIRECT) | R310 路由回归 |
| NVCF_DEEPSEEK_FUNCTION_ID | 4e533b45 | 确认正确(R313实测) |

### 1c. 数据库 (30min + 60min 双窗口, created_at)

**30min窗口** (00:05 UTC):
```
total=41, ok=41(100%), avg_ttfb=22,199ms(22.2s)
ATE=0, 429=0, fallback=0, errors='' (空)
```

**60min窗口** (00:05 UTC):
```
total=78, ok=78(100%), avg_ttfb=20,702ms(20.7s)
```

**Per-key P50/P95** (30min, status=200):
```
k0(k1): 8 reqs, P50=18,144ms, P95=31,370ms, max=34,371ms
k1(k2): 8 reqs, P50=19,614ms, P95=53,789ms, max=66,035ms
k2(k3): 9 reqs, P50=15,499ms, P95=71,004ms, max=82,128ms
k3(k4): 7 reqs, P50=19,623ms, P95=23,934ms, max=25,617ms
k4(k5): 9 reqs, P50=15,737ms, P95=65,805ms, max=71,361ms
```

### 1d. is_direct 补丁验证
```python
# /opt/cc-infra/proxy/hm-proxy/gateway/upstream.py line 164,170
is_direct = (not proxy_url) or (proxy_url.strip() == "")
# 确认: 补丁存在, 逻辑正确 (k2/k4=空→DIRECT, k1/k3/k5有值→mihomo)
```

### 1e. 健康检查
```json
{"status":"ok","proxy_role":"passthrough","hm_num_keys":5,"nvcf_pexec_models":["deepseek_hm_nv"],"hm_model_tiers":["deepseek_hm_nv"],"hm_default_model":"deepseek_hm_nv","port":40006}
```

## 2. 状态分析

### 2a. 不变量确认
| 不变量 | 状态 |
|---|---|
| 5/5 keys在线 | ✅ 全部有效 |
| function_id 4e533b45 | ✅ 正确 (R313实测+curl验证) |
| is_direct 补丁 | ✅ 存在且正确 |
| 混合路由 (k1/k3/k5=mihomo, k2/k4=DIRECT) | ✅ 按R310设计 |
| DB 无错误记录 | ✅ 30min+60min均为0 |

### 2b. 参数状态矩阵
| 参数 | 当前值 | 来源轮次 | 可调性 | 当前瓶颈? |
|---|---|---|---|---|
| BUDGET | 90 | R311 (182→90) | 可调 | ⚠️ 已近下限(87-89s耗尽) |
| UPSTREAM_TIMEOUT | 45 | R311 (64→45) | 可调 | 正常(NVCF TTFB 12-26s内) |
| KEY_COOLDOWN | 38 | 稳定 | 低 | 非瓶颈 |
| TIER_COOLDOWN | 38 | 稳定 | 低 | 非瓶颈 |
| MIN_OUTBOUND | 18.2 | 稳定 | 低 | 非瓶颈(请求间隔2min) |
| CONNECT_RESERVE | 24 | 稳定 | 低 | 非瓶颈 |

### 2c. 失败模式分析

**本窗口30min内2次ABORT-NO-FALLBACK** (docker logs有, DB无):
- 失败 #1 (23:54): 6次timeout, 87s → BUDGET耗尽 → ABORT
- 失败 #2 (23:55): 6次timeout, 89s → BUDGET耗尽 → ABORT
- 这两次失败在DB中无记录 (ABORT-NO-FALLBACK不写入DB, 已确证的DB缺口)

**与R313发现的同源模式**:
R313分析了23:20-23:55的HM1/HM2同步失败: 5个重合分钟 (21:54/22:53/22:58/22:59/23:01), 失败率HM1~4.8%/HM2~8.2%。本窗口继续出现同样的失败模式:
- 失败请求中所有5个key逐个timeout (NVCFPexecTimeout, 5-7s/per key)
- 无429, 无empty_200, 纯timeout
- 这是NVCF平台层间歇性整批不可用 (gateway层无法消除)

## 3. 优化决策

### ⏸️ 决策: 无操作 (稳定态确认, 0参数变更)

**评判标准**:

| 标准 | 评估 | 详情 |
|---|---|---|
| 更少报错 | ✅ 已达标 | DB 30min 0错误, 0/41失败; 2次ABORT是NVCF平台层, gateway无计可施 |
| 更快请求 | ✅ 已达标 | P50=15-20s, P95=23-71s (NVCF常态波动, 非gateway瓶颈) |
| 超低延迟 | ✅ 已达标 | avg TTFB 20-22s, 在DeepSeek-v4-pro正常推理范围内 |
| 稳定优先 | ✅ 已达标 | 0参数变更 = 最高稳定性; 已有配置已验证多轮 |

**为何不调任何参数**:

- **BUDGET=90**: 已从182降至90(-92s), 再降会导致正常请求(avg 22s)在BUDGET耗尽前被截断。失败请求在87-89s时耗尽, BUDGET<60会让P95请求被误杀
- **UPSTREAM_TIMEOUT=45**: 已从64降至45(-19s), NVCF正常TTFB 12-26s都在45s内完成。降低会误杀正常慢请求(如k2的66s max)
- **KEY/TIER COOLDOWN=38**: 已是最优 (R296全key 6头验证), 降低会增加NVCF负载/提高429风险
- **MIN_OUTBOUND=18.2**: 非瓶颈, 请求节奏2min已远大于此值
- **任何新逻辑** (empty_200重试/退避/短超时): R313已通过两轮碰撞+CC独立核实全部证伪, 当前换key逻辑12/12救回已验证最优

### 与R313的对接

R313建议的"方向A" (empty_200后首timeout短超时): 需要A/B验证可截断性, 且会误伤13/30个慢成功请求(>45s), 非单参数, 留待后续轮次。本轮无新数据改变此判断。

## 4. 铁律验证

| 铁律 | 状态 |
|---|---|
| 只改HM1不改HM2 | ✅ 本轮无改动 |
| 改前必有数据 | ✅ 4类数据完整收集(docker/DB/env/code) |
| 改后必有验证 | N/A (无操作) |
| 每轮少改 | ✅ 0参数=最少量 |
| 聚焦hm-40006--nv | ✅ 仅分析deepseek_hm_nv链路 |
| 数据驱动决策 | ✅ 30min+60min双窗口跨验证 |

## 5. 下轮预期

### HM2侧稳定参数 (不变)
- BUDGET=90, UPSTREAM_TIMEOUT=45, KEY_COOLDOWN=38, TIER_COOLDOWN=38
- MIN_OUTBOUND=18.2, CONNECT_RESERVE=24
- 混合路由 (k1/k3/k5=mihomo, k2/k4=DIRECT)
- function_id=4e533b45

### 给HM1的建议
- 状态: HM1 gateway已达NVCF平台硬限制, 继续单参数微调无边际收益
- ~5-8%失败率是NVCF平台层固有, HM1/HM2同步失败已确认
- 唯一可能有疗效的方向: 更短BUDGET或A/B测试empty_200后首timeout短超时 — 但需先验证可截断性
- 建议: 守稳模式继续, 或转向NVCF侧反馈

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记(交替优化序列)