# R568 (HM1+HM2 自改) 优化报告 — 全直连 + 多候选function + 思考修正

## 📅 执行时间
2026-07-02 20:00–20:50 (UTC+8)

## 🎯 本轮目标
1. 两机 hm40006 全去 mihomo, 3 模型全直连 (用户授权两机自改)
2. dsv4p 换 function (8915fd28 sglang 挂死 → 74f02205 ai-deepseek 中国直连秒回)
3. 每模型多候选 function + func_health 自动切换 (根治 surge/EOL/失效)
4. 三模型思考模式全打开 (dsv4p 修正触发参数)
5. 三 agent 配置精简: openclaw=dsv4p / hermes=kimi / opencode=glm5.1
6. peer fallback 仅两机互备 (不跨模型), 已确认配置正确

---

## 🔍 根因抓包 (dsv4p 8915fd28 挂死)

### 现象
openclaw 飞书 agent 卡死, hm40006 dsv4p_nv 5 key 全 61s timeout, peer fallback 到 HM2 也 25s timeout.

### 抓包对照矩阵 (同 key1, 同时刻)
| 路径 | dsv4p 8915fd28 | kimi f966661c | glm5.1 |
|------|----------------|--------------|--------|
| 真直连(--noproxy, 中国出口218.93.x) | ❌ 25s 0字节超时 | ✅ 秒回 | 410 EOL (integrate API) |
| 经 mihomo 7880 日本节点(103.62.x) | ✅ 秒回 (间歇) | ✅ 秒回 | — |
| 经 mihomo 7894-7899 美国节点(134.195.x) | ❌ 25s 0字节超时 | ✅ 秒回 | — |

### 关键结论
1. **不是账号风控**: 同 key1 kimi 秒回 200; dsv4p 挂死是"0字节超时"非 429/403
2. **不是代理全坏**: kimi 经同节点秒回; 仅 dsv4p 8915fd28 经美国节点/中国直连挂死
3. **8915fd28 (sglang) 是 NVCF 平台间歇 surge 故障**: 对中国出口+美国代理出口都挂, 仅日本出口间歇能通
4. **74f02205 (ai-deepseek-v4-pro) 中国真直连秒回稳定**: 跨 key1/key2/key4/key5 全通

### 7880 vs NV 5 节点出口 IP 差异
| 端口 | 出口 IP | 地区 |
|------|---------|------|
| 真直连 | 218.93.250.242 | 中国江苏 |
| 7880 mixed-port | 103.62.49.138 | 日本 (mihomo默认规则) |
| 7894 NV-K1 | 134.195.101.194 | 美国 |
| 7895-7899 NV-K2..K5 | 134.195.101.x | 美国 |

**本质**: 7880 走日本出口, 7894-7899 走美国出口. dsv4p 8915fd28 对美国出口挂死, 对日本出口间歇能通. 之前"假直连能通"是 curl 偷走 7880 日本代理的假象.

### glm5.1 EOL 发现
- integrate API (`integrate.api.nvidia.com`): `z-ai/glm-5.1` 返 410 Gone (2026-07-02 EOL)
- **pexec endpoint** (`api.nvcf.nvidia.com/v2/nvcf/pexec/functions/{id}`): 6155636e 仍秒回 ✅
- hm40006 走 pexec 不走 integrate, 故 glm5.1 经 hm40006 仍可用

---

## 🔧 改动详情

### 1. 两机 docker-compose.yml (hm40006 env)
| 参数 | 改前 | 改后 |
|------|------|------|
| NVCF_DEEPSEEK_FUNCTION_ID | 8915fd28 (sglang, 挂死) | **74f02205 (ai-deepseek, 直连秒回)** |
| HM_NV_PROXY_URL1..5 | 4个走mihomo美国节点+1直连 | **全空 (全直连去mihomo)** |
| NVCF_KIMI_FUNCTION_ID | f966661c-790d... | 不变 (已验证直连秒回) |
| NVCF_GLM51_FUNCTION_ID | 6155636e | 不变 (pexec 不受 EOL) |

备份: `docker-compose.yml.bak.R_direct_20260702_195808` (HM1) / `_200035` (HM2)

### 2. 两机 gateway 源码 (bind-mount, restart 即生效)

#### config.py — NVCF_PEXEC_MODELS 多候选 + dsv4p 思考修正
```python
# function_id (单值) → function_ids (有序候选列表)
"kimi_nv":   function_ids=[f966661c...],  inject={"reasoning_effort":"low"}
"dsv4p_nv":  function_ids=[74f02205..., 8915fd28...],  inject={"thinking":{"type":"enabled"}}
"glm5_1_nv": function_ids=[6155636e..., af904f0c...],  inject={"chat_template_kwargs":{"enable_thinking":True}}
# 向后兼容: nvcf_cfg["function_id"] = 候选[0]
```
**dsv4p 思考触发参数修正** (抓包实测 74f02205 ai-deepseek):
- `reasoning_effort=high/max` → 200 但 rc=None (无效)
- **`thinking:{type:enabled}` → rc 非空 ✅** (与 8915fd28 sglang 用 reasoning_effort 不同)
- 每个function触发参数各不相同, 不能假设统一 (见 memory dsv4p-thinking-real-trigger)

#### func_health.py — per-model → per-function 健康度
- 健康度按 function_id 分桶记录 (不是按 model)
- 新增 `select_healthy_function(model, candidates)`: 返回首个健康候选, surge 的自动跳过
- 冷启动 (样本<5) 视为健康 → 返回候选[0]
- 全部不健康 → 仍返回候选[0] 让调用方尝试 (失败后 record 进一步降健康度)

#### upstream.py — 集成 function 候选选择
- `_try_tier_keys`: `function_id = func_health.select_healthy_function(tier_model, candidates)`
- UpstreamResult 加 `function_id` 字段, 带回本次选中的 function_id
- `record_result(tier_result.function_id, success)` 按function记录 (原为 tier_model)
- FALLBACK_GRAPH is_healthy(alt) → 检查 alt 首选function健康 (原传model名已失效)
- HM2 保留 R560 (slow empty_200 fastbreak) 逻辑, R_multi 改动叠加不覆盖

### 3. 三 agent 配置 (两机, 已确认无需改动)
| Agent | 模型 | HM1 | HM2 |
|-------|------|-----|-----|
| openclaw | dsv4p_nv | ✅ primary + 单model | ✅ |
| hermes | kimi_nv | ✅ default + 单model | ✅ |
| opencode | glm5_1_nv | ✅ model + 单model | ✅ |

三 agent 配置已整洁, 无残留旧模型名 (deepseek_hm_nv/dsv4p_hm 等已清). 跨模型 fallback (FALLBACK_GRAPH) 默认空, 不跨模型. peer fallback 两机互指 (HM1→HM2, HM2→HM1), 仅不同IP间互备.

---

## ✅ 验证结果

### HM1 (20:47)
| 模型 | function | 路径 | 思考 | 结果 |
|------|----------|------|------|------|
| dsv4p_nv | 74f02205 | DIRECT | ✅ rc非空 | HM-SUCCESS first attempt |
| kimi_nv | f966661c | DIRECT | ✅ rc非空 | HM-SUCCESS first attempt |
| glm5_1_nv | 6155636e | DIRECT | ✅ rc非空 | HM-SUCCESS first attempt |

openclaw(→dsv4p)/hermes(→kimi)/opencode(→glm5.1) 三 agent 真实流量全 HM-SUCCESS, 思考全 True.

### HM2 (20:48)
三模型全 HM-SUCCESS, DIRECT, 思考全 True. (20:46:55 kimi 冷启动 timeout 1次, 之后恢复)

### 两机均无错误日志
- `HM-THINKING-TIMEOUT` 是思考请求正常超时延长提示, 非错误
- openclaw 无 stalled 诊断 (之前卡死已解)

---

## 📌 根治机制: 多候选 function 自动切换

### NVCF function 风险三类
| 风险 | 案例 | 应对 |
|------|------|------|
| 平台 surge 故障 | 8915fd28 间歇挂死 | 多候选 + func_health 自动切 |
| EOL 下架 | integrate API glm5.1 410 | 走 pexec endpoint (已做) |
| status 降级 | 52e1ddb6 DEGRADING | 候选列表只放 ACTIVE |

### 自动切换流程
1. 请求来 → `_try_tier_keys` 读 `function_ids` 候选列表
2. `func_health.select_healthy_function` 返回首个健康候选 (滑动窗口20次, 阈值0.8)
3. surge 中的 function 健康度 <0.8 → 自动跳到下一候选
4. 恢复后健康度回升 → 自动回切首选
5. 冷启动 (样本<5) 视为健康, 不误杀

### 当前候选配置
- dsv4p: [74f02205(首选,直连秒回), 8915fd28(备选,surge恢复时可用)]
- glm5.1: [6155636e(首选), af904f0c(备选 dynamo)]
- kimi: [f966661c(单元素, 无其他 ACTIVE 候选)]

---

## ⚠️ 注意事项
1. **铁律破例自改**: 用户授权两机自改 (去mihomo + 换function + 源码改动). 非 alternating 优化轮, 是用户直接授权的架构级改动.
2. **失去mihomo退路**: 若将来 NVCF 对中国IP屏蔽或 74f02205 也 surge, 无代理可绕. 但实测美国代理对dsv4p反挂死, mihomo对dsv4p退路价值本就有限.
3. **kimi 无备选**: NVCF 列表里 kimi-k2.6 只有 f966661c 一个 ACTIVE function, 无法多候选. surge 时只能靠 peer fallback.
4. **dsv4p 备选 8915fd28 触发参数不同**: 8915fd28 用 reasoning_effort, 74f02205 用 thinking:{type:enabled}. inject 只能设一个, 当前配 74f02205 的 thinking. 若自动切到 8915fd28, 思考可能不生效 (但 8915fd28 当前 surge 挂死, 切过去概率低). 后续可考虑 per-function inject.

---

### 追加验证 (21:20, compact 续轮)
- **func_health 故障切换实测**: HM1 容器内对 dsv4p 首选 74f02205 连灌 8 次 record_result(False) → 健康度降到 0.0 → `select_healthy_function` 自动返回备选 8915fd28 ✅ (日志 `[HM-FUNC-HEALTH] model=dsv4p_nv primary=74f02205... unhealthy → switched to 8915fd28...`). 之后 `docker compose restart hm40006` 清掉测试污染, snapshot 归 {}.
- **多候选当前选择**: kimi→f966661c / dsv4p→74f02205(备8915fd28) / glm5.1→6155636e(备af904f0c).
- **openclaw name 字段清理**: 两机 openclaw.json 的 dsv4p_nv.name 旧文案 "sglang 8915fd28" → "ai-deepseek 74f02205" (仅显示名, 不影响路由). 备份 `.bak.cleanup_20260702`.
- **三 agent 配置整洁确认**: hermes 两机 default=kimi_nv 无 providers/aliases; opencode 两机只 glm5_1_nv 无 kimi/dsv4p/deepseek 残留; openclaw 两机只 dsv4p_nv.
- **peer fallback 范围确认**: HM1→http://100.109.57.26:40006, HM2→http://100.109.153.83:40006 (仅两机互指); FALLBACK_GRAPH 默认空 (不跨模型). 符合"fallback只在两台设备不同IP间"要求.
- **HM1 重启后 health**: `{"status":"ok","nvcf_pexec_models":["kimi_nv","dsv4p_nv","glm5_1_nv"],"hm_default_model":"dsv4p_nv"}`.

---

## ⏳ 轮到HM2优化HM1
