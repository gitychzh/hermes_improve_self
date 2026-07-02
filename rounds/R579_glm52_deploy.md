# R579: glm-5.2 部署 (glm-5.1 NVCF EOL 后新主力)

## 背景
2026-07-02 NVCF 全系下架 glm-5.1:
- pexec: 6155636e/af904f0c/46f4fb53 均 INACTIVE/404
- integrate: z-ai/glm-5.1 返回 410 Gone ("end of life on 2026-07-02T00:00:00Z")
openclaw 默认 nv_cus/glm5_1_nv 实际全 fallback 到 dsv4p (deepseek), 名不副实.

## 数据 (改前必有数据)
1. **glm-5.1 全下架证实** (直接 NVCF list):
   - 6155636e (ai-glm-5_1): INACTIVE
   - af904f0c (dynamo-glm-5_1): INACTIVE
   - 46f4fb53 (dynamo-hicache-glm-5_1): INACTIVE
   - 3b9748d8 (ai-glm-5_2): ACTIVE ← 唯一可用 glm 系
2. **glm-5.2 元数据**: ownedByDifferentAccount=True (NVIDIA 官方托管), apiBodyFormat=CUSTOM, createdAt=2026-07-02
3. **integrate 端点对 glm 不支持**:
   - z-ai/glm-5.1 → 410 Gone (EOL)
   - z-ai/glm-5.2 → 404 page not found (从未上 integrate)
   - 仅 deepseek/kimi 走 integrate, glm 系只能走 pexec

## 思考触发参数深挖 (抓包探测 5 种触发)
| 触发参数 | reasoning_content | 结论 |
|---|---|---|
| 裸请求(无参数) | None | ❌ 不思考 (非自带) |
| thinking:{type:enabled} | ✅ 有 | ✅ 触发 |
| reasoning_effort=high | None | ❌ 无效 (与 dsv4p 相反) |
| chat_template_kwargs.enable_thinking=True | ✅ 有 | ✅ 触发 (与 glm5.1 同) |
| thinking + effort | ✅ 有 | ✅ (thinking 主导) |

**结论: glm-5.2 思考模式不是自带的, 必须输入参数触发.** 两种有效:
- `thinking:{type:enabled}` (OpenAI 风格)
- `chat_template_kwargs:{enable_thinking:True}` (GLM 原生, 选此因与 glm5.1 一致)

触发后 finish=stop (非 length), 思考消耗 ~400-535 tokens, content 正常 — 健康思考模式.

## 工具调用 bug 发现与修复
经网关测试工具调用: finish=tool_calls 但 tool_calls=null, content 空.
- 直接打 NVCF (非流): tool_calls 结构完整 ✅
- 经网关: tool_calls 丢失 ❌

**根因**: NVU_FORCE_STREAM_UPGRADE=1 把非流请求升级成流式, _accumulate_stream_to_nonstream
重组非流 JSON 时只提取 delta.content/reasoning_content, **不提取 delta.tool_calls** → 结构丢失.
glm5_2_nv 不在 R576 的 EXCLUDE 列表 (只有 dsv4p_nv).

**修复 (R577)**: 把 glm5_2_nv 加进 NVU_FORCE_STREAM_EXCLUDE_MODELS 默认值.
- 非流请求走原生非流 _check_empty_200 分支, 透传完整 body (含 tool_calls)
- glm5.2 思考快 (3-6s), 无需 force-stream 防 timeout
- 验证: 经网关 tool_calls={get_weather({city:北京})} ✅, content 也在 ✅, reasoning 也在 ✅

## 改动 (两机自改, 用户授权 CC 直接改两机)
### /opt/cc-infra/proxy/nv-uni/gateway/config.py
1. NVCF_PEXEC_MODELS 新增 glm5_2_nv 条目:
   - function_ids: [3b9748d8-1d85-40e8-8573-0eeaa63a4b63]
   - strip_params: [thinking_budget, reasoning_effort, thinking]
   - inject: {chat_template_kwargs: {enable_thinking: True}}
2. NV_MODEL_IDS += "glm5_2_nv": "z-ai/glm-5.2"
3. NV_MODEL_TIERS += "glm5_2_nv"
4. MODEL_MAP += glm5_2_nv/glm5.2/z-ai/glm-5.2 → glm5_2_nv
5. MODEL_INPUT_TOKEN_SAFETY += glm5_2_nv: 131072
6. FALLBACK_GRAPH += "glm5_2_nv": ["dsv4p_nv"] (3b9748d8 surge 时降级)
7. NVU_FORCE_STREAM_EXCLUDE_MODELS 默认 "dsv4p_nv,glm5_2_nv" (修 tool_calls 丢失)
8. glm5_1_nv 注释更新 (标记 EOL/410)

### /opt/cc-infra/docker-compose.yml
1. +NVCF_GLM52_FUNCTION_ID: 3b9748d8-1d85-40e8-8573-0eeaa63a4b63
2. NVCF_GLM51_FUNCTION_ID 注释更新 (EOL/410)
3. NV_INTEGRATE_MODELS 改回 "dsv4p_nv,kimi_nv" (去掉 R578 加的 glm5_1_nv — integrate 对 glm 返回 410/404 无效; glm5_2_nv 也不支持 integrate)

### ~/.openclaw/openclaw.json (两机)
1. agents.defaults.model.primary: nv_cus/dsv4p_nv → nv_cus/glm5_2_nv
2. fallbacks: [glm5_1_nv] → [dsv4p_nv]
3. agents.defaults.models += nv_cus/glm5_2_nv alias
4. models.providers.nv_cus.models += glm5_2_nv entry (reasoning=true, thinkingFormat=zai, maxTokens=32768)

## 验证 (改后必有验证)
### HM1
- 基础问答 ✅ "1+1等于2" (glm5.2 返回, 非 fallback)
- 流式 ✅ "中国的首都是北京"
- 思考模式 ✅ reasoning_content 有值, finish=stop, content 正常
- 工具调用 ✅ tool_calls={get_weather({city:北京})}, content+reasoning 都在
- 端到端 openclaw agent ✅ 用 python 工具算 15*17=255
- 日志确认: model=glm5_2_nv→glm5_2_nv, func=3b9748d8, NV-SUCCESS, health=1.0 (无 fallback)

### HM2
- 思考模式 ✅ reasoning_content + content 都正常, finish=stop
- 配置同步: EXCLUDE 含 glm5_2_nv, NV_MODEL_IDS 含 glm5_2_nv

## 关键认知
- glm-5.1 已 EOL (2026-07-02), 不可恢复, 只能升 5.2
- glm-5.2 思考触发方式与 glm-5.1 完全相同 (chat_template_kwargs), 但与 dsv4p 不同 (dsv4p=thinking)
- glm-5.2 ��支持 integrate 端点 (404), 只能走 pexec
- force-stream 升级路径 (_accumulate_stream_to_nonstream) 有设计缺陷: 不累积 tool_calls, 对需要工具调用的模型必须排除
- R578 (HM2→HM1) 把 glm5_1_nv 加进 integrate 无效 (410 Gone), 本轮回退

## 下轮
HM1 或 HM2 可继续优化: 监控 glm5_2_nv 实际流量下的成功率/延迟, 或修 _accumulate_stream_to_nonstream
正确累积 tool_calls (让 force-stream 路径也能保留工具调用, 但当前 glm5.2 已排除暂不急需).
