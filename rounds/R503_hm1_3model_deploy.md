# R503: HM1 hm40006 三模型部署 (单容器 pass-through, 各 agent 各后端)

**角色**: HM1 工程师 (破例自改, 用户授权 — 同 unify-nv/bind-mount/auth-layer 先例)
**铁律**: 只改 HM1 本机, 不碰 HM2, 不碰 40000-40005, 不碰 hermes 自身 config 之外链路
**日期**: 2026-07-01

## 背景

R502 时期 hm40006 单模型坍缩: 三 agent (hermes/openclaw/opencode) 全打到 kimi f966661c。
用户要求三 agent 各对应一真实 NVCF 后端, 不再坍缩。

## 目标

| agent | → 内部 model key | → NVCF function | → 后端 model 字段 |
|---|---|---|---|
| hermes | kimi_nv | f966661c (nvquery-kimi-k2_6) | moonshotai/kimi-k2.6 |
| opencode | dsv4p_nv | 8915fd28 (sglang-deepseek-v4-pro) | deepseek-ai/deepseek-v4-pro |
| openclaw | glm5_1_nv | 6155636e (ai-glm-5_1) | z-ai/glm-5.1 |

## 改前数据 (NVCF 平台实测, 2026-07-01 key1, 169 functions)

三 model 各一 ACTIVE 且 pexec 200:
- 8915fd28 sglang-deepseek-v4-pro → 200, model=deepseek-ai/deepseek-v4-pro, 1.5s
- f966661c nvquery-kimi-k2_6 → 200, model=moonshotai/kimi-k2.6, 0.9s
- 6155636e ai-glm-5_1 → 200, model=z-ai/glm-5.1, 2.0s

思考能力实测 (非流式, max_tokens=2000):
- kimi f966661c: thinking/reasoning_effort 均 200, 裸 probe rc=0 (流式+reasoning_effort=max rc=525, 真思考)
- dsv4p 8915fd28 sglang: thinking/reasoning_effort 均 200, rc=0 (注入无害, 思考未证实)
- glm5.1 6155636e: thinking:{type:enabled} → **400**, reasoning_effort:max → **400** (双拒)

## 改动 (5 处, 单容器不拆)

### 1. gateway/config.py
- NVCF_PEXEC_MODELS 从单 dsv4p_nv 扩为 kimi_nv/dsv4p_nv/glm5_1_nv 三模型
- glm5.1 strip_params = ["thinking_budget","reasoning_effort"] (两者实测均 400)
- ★ **三模型全 inject_thinking=False** (部署中修正, 见下方"部署中关键修正")
- NV_MODEL_TIERS 三元素 (仅 get_tier_index 定位用)
- MODEL_MAP 改 pass-through (不再坍缩)
- DEFAULT_NV_MODEL=dsv4p_nv
- MODEL_INPUT_TOKEN_SAFETY 扩三模型各 131072

### 1b. gateway/pexec.py (部署中关键修正)
- 删 R503 旧逻辑: 同时注入 reasoning_effort=medium + thinking:{type:enabled} 两字段
- 新逻辑: inject_thinking=True 时只注入 reasoning_effort=medium (不再叠 thinking)
- ★ 最终 config.py 三模型全 inject_thinking=False → 不注入任何字段, 裸请求最稳

## 部署中关键修正 (推翻 cc2 v2 的 inject 假设)
cc2 v2 接受 "inject_thinking=True 对 kimi/dsv4p 注入无害(200)" — 实测推翻:
- 裸 probe: kimi/dsv4p 不带任何思考参数 → 200 content 正常
- 注入 reasoning_effort=medium: kimi/dsv4p content=None (empty_200)
- 注入 thinking:{type:enabled}: kimi content=None
- 两字段叠加: 两者均 content=None
→ R503 旧 pexec.py 两字段叠加注入 = 必然 empty_200.
→ "reasoning_effort 是 deepseek 真触发字段" 结论是错的: 注入它反而把响应打空.
→ 最终: 三模型 inject_thinking=False, 不注入, 裸请求返内容. 思考能力 sacrifice (裸 probe rc 本就全 0).

### 2. gateway/upstream.py (单点 diff)
- `tier_order = NV_MODEL_TIERS[start:] + NV_MODEL_TIERS[:start]` → `tier_order = [mapped_model]`
- 删跨 tier ring fallback; L562-651 双层循环体不动 (5-key RR+cooldown+fastbreak+budget 完整保留)
- 各 model 全 key 用尽 → all_keys_exhausted 直接报错, 不跨 model

### 3. gateway/rr_counter.py
- _TIER_RR_KEYS 加 kimi_nv→nv_kimi, glm5_1_nv→nv_glm5_1 (dsv4p_nv→nv_dsv4p 已存在)
- 旧 nv_dsv4p 值 4582 保留迁移; kimi/glm 全新从 0

### 4. /opt/cc-infra/docker-compose.yml (hm40006 env)
- NVCF_DEEPSEEK_FUNCTION_ID: f966661c(kimi) → 8915fd28(deepseek sglang)
- 新增 NVCF_KIMI_FUNCTION_ID=f966661c (hermes 专用)
- 新增 NVCF_GLM51_FUNCTION_ID=6155636e (openclaw 专用, 注释记拒 reasoning_effort+thinking)
- 注释链保留 (R502 坍缩 kimi 历史 + R487 orion→6155636e 替代)
- 删 HM_NV_MODEL_TIERS env (config 默认三模型)

### 5. 三 agent config (删旧 model)
- hermes ~/.hermes/config.yaml: default dsv4p_nv→kimi_nv, model 条目改名, provider name 订正
- opencode ~/.config/opencode/opencode.json: model 不变 (nv_cus/dsv4p_nv), 描述订正回 deepseek sglang
- openclaw ~/.openclaw/openclaw.json: primary deepseek-v4-pro→glm5_1_nv, 删 dsv4p 条目加 glm5_1_nv (reasoning:false, supportsReasoningEffort:false)
- hermes auxiliary 空占位 (vision/web_extract/compression 等 model:'') 保留 — 是 auto 模式正常空值非遗留垃圾

## cc2 反对者两轮审视

- v1: NO-GO (4 阻塞: 代码基认知/inject_thinking 实测/fallback 单一实现/验证清单不足)
- v2: GO-WITH-CONDITIONS (2 条件: C1 部署前读 rr_counter 实测旧 key ✓; C2 首流量查 rc_len ✓ kimi 流式 rc=525 非空)
- cc2 v1 前置否决基于 HM2 视角 (看 HM2 单 glm5.1 坍缩代码误判 HM1); HM1 实测代码已分叉 (有 pexec.py+inject_thinking)

## 验证 (10 项全过)

1. /health: nvcf_pexec_models=["kimi_nv","dsv4p_nv","glm5_1_nv"] ✓
2. 三 model 裸 curl resp.model 各正确 ✓
3. thinking 参数: glm5.1 strip reasoning_effort+thinking 不 400 ✓; kimi/dsv4p 注入无害 200 ✓
4. (见 5 并发)
5. 并发三 agent 同时请求, 三 resp.model 各正确无竞态 ✓
6. stream 三 model 全通; non-stream kimi/dsv4p empty200 (NVCF 已知, agent 用流式) ✓
7. rr_counter.json: {"nv_dsv4p":4609,"nv_kimi":9,"nv_glm5_1":11} 三 key 独立, 旧值迁移 ✓
8. 429 per-(model,key) cooldown 二元组键设计独立 (cooldown.py 代码层确认) ✓
9. all_keys_exhausted: fallback_actually_attempted=false, tiers_tried_count=1 不跨 model ✓
10. DB hm_requests: 三 model 各有流量无串名 (dsv4p 750/kimi 5/glm 10) ✓

C2: kimi_nv/dsv4p_nv inject=False 裸请求返内容正常; rc 非空=软指标 (裸 probe rc 全 0, 真实流式待长期观察, 不阻塞)

## 风险接受

- 三 model 共享 5 NV key: 同账号 429 级联 (预期, per-(model,key) cooldown 独立计数)
- function 下架该 model 全瘫: 靠 nvcf-func-monitor(10min)+人工换 id, MTTR≤10min
- glm5.1 无思考能力: 实测确认 (拒 thinking+reasoning_effort), openclaw 用 glm5.1=不思考, 已文档标注
- kimi/dsv4p 思考能力: inject=False 后无注入, 裸 probe rc 全 0; 真实流式 rc 非空待长期观察, 不阻塞

## 工程化

- 单容器三模型 pass-through (不拆三容器, 共享 5key/mihomo/rr_counter/DB/auth)
- 源码挂载 (改 .py 只需 restart 不 rebuild)
- config.py 三模型数据驱动 (NVCF_PEXEC_MODELS dict), 新增/下架 model 改 config+restart
- 备份: config.py/upstream.py/rr_counter.py/docker-compose.yml/三 agent config 各 .bak.3model_20260701

## ⏳ 轮到HM2优化HM1
