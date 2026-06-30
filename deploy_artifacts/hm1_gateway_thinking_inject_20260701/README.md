# HM1 hm40006 网关侧 thinking 统一注入 (2026-07-01)

## 背景

三 agent (hermes/opencode/openclaw) 共用 hm40006 → NVCF dynamo-deepseek-v4-pro (ee2b0de2)。
dynamo function 触发 reasoning_content (思考链) 的硬条件: 请求 body 必须带
`thinking:{"type":"enabled"}`。单独 `reasoning_effort` 不触发 (probe H 实测)。

## 三 agent 注入现状 (改前)

| Agent | 自动注入 thinking? | 思考链 |
|---|---|---|
| openclaw | ✅ 自带 DSv4 thinking wrapper 注入 | ✅ 生效 |
| hermes | ⚠️ 实测会注入 (抓包确认 7× thinking:enabled) | ✅ 已生效 |
| opencode | ❌ 只发 reasoning_effort, 不发 thinking | ❌ 不生效 |

## 改动: 网关侧统一兜底注入

`gateway/pexec.py` `_build_pexec_body`: 当 `nvcf_config["inject_thinking"]=True` 且
body 无 `thinking` 字段时, 补 `thinking:{"type":"enabled"}`。

`gateway/config.py` `NVCF_PEXEC_MODELS["dsv4p_nv"]` 加 `"inject_thinking": True`。

- 仅对声明了 inject_thinking 的 model 生效 (当前仅 dsv4p_nv); glm5.1 等不受影响。
- 已有 thinking 不覆盖 (尊重 openclaw/hermes 自带注入与 reasoning_effort 配置)。

## 铁律

HM1 自改 hm40006 源码 — 跨铁律 "只改对端不改自己"。先例: hm1-mihomo-removed。
理由: 三 agent 共用本机 hm40006, 网关侧单点注入比改各 agent 配置更干净, 且对 openclaw
(自带 thinking) 是 no-op, 对 hermes (已注入) 也是 no-op, 主要惠及 opencode。

## 部署

hm40006 bind-mount gateway 源码 → 改 .py 只需 `docker compose restart hm40006` (无需 rebuild)。
backup: pexec.py.bak.thinking_inject_20260701_003057, config.py.bak.thinking_inject_20260701_003057

## 端到端验证 (2026-07-01 00:31-00:38)

- A. curl 不带 thinking (hermes legacy 模拟) → 注入 → reasoning_content ✅
- B. curl 只带 reasoning_effort (opencode 模拟) → 注入 → reasoning_content ✅
- C. curl 自带 thinking (openclaw 模拟) → 不注入 → reasoning_content ✅
- D. hermes 真实请求 → reasoning_content 575 chunks ✅
- E. opencode 真实请求 → reasoning_content 53 chunks ✅
- INJECT-THINKING 日志触发 8 次 (真实流量兜底生效)
- HM-SUCCESS 全程, 0 错误
