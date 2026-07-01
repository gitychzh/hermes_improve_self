#!/usr/bin/env python3
"""Configuration for NV proxy (hm40006) — single-model dsv4p_nv, 三 agent 通用.

unify-nv (2026-06-30): 内部 model key 从 deepseek_hm_nv 改为 dsv4p_nv, 反映
      通用语义 (供 hermes/opencode/openclaw 三 agent 共用, 非 Hermes 专属).
      旧名 deepseek_hm_nv 保留为 alias 向后兼容.
R274: Removed kimi dead code. The proxy serves exactly one model —
      dsv4p_nv (deepseek-v4-pro) — via NVCF pexec. No tier fallback.

Chain: agent (hermes/opencode/openclaw) → hm40006 → NVCF pexec
       (orion-deepseek-v4-pro, ACTIVE) → per-key SOCKS5 → mihomo/direct → NV API.

5 keys (k1→k5) round-robin with a persistent RR counter (全局共享, N+1 跨 agent
连续, 重启续接). A request fails only when all 5 keys are exhausted
(429 / empty 200 / timeout) within the tier budget — there is no model fallback.

Reng (HM1 self-change, authorized): modularized for long-term maintainability.
RR counter state machine → gateway/rr_counter.py; 429 cooldown state machine
→ gateway/cooldown.py; NVCF connection layer → gateway/nvcf_conn.py; pexec
request construction/validation → gateway/pexec.py. This file now holds pure
configuration + throttle_outbound only. Logic is byte-for-byte equivalent;
all downstream `from .config import ...` statements keep working via re-export.
"""
import os
import sys
import time
import threading

# ─── Network ──────────────────────────────────────────────────────────────
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "40006"))
PROXY_TIMEOUT = int(os.environ.get("PROXY_TIMEOUT", "300"))
UPSTREAM_TIMEOUT = int(os.environ.get("UPSTREAM_TIMEOUT", "30"))  # CC-2026-07-01: 45->30, NVCF挂死超时更快放弃切key; compose env 同步  # R38.5: 60→45 (NV p95<30s)

# ─── Gateway auth (局域网 agent 共享 key, 2026-06-30) ──────────────────────
# 空 = 不校验(向后兼容); 非空 = /v1/* 须带 Authorization: Bearer <HM_GATEWAY_API_KEY>
# 或 x-api-key: <HM_GATEWAY_API_KEY>. /health 与 CORS preflight 免鉴权.
# 默认 nv-local (与 hermes config model.api_key 一致, 局域网 agent 共用).
HM_GATEWAY_API_KEY = os.environ.get("HM_GATEWAY_API_KEY", "nv-local")

# ─── Proxy Role ────────────────────────────────────────────────────────────
# "passthrough" — serves /v1/chat/completions (OpenAI format)
PROXY_ROLE = os.environ.get("PROXY_ROLE", "passthrough")

# ─── Logging ──────────────────────────────────────────────────────────────
LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")

# ─── NVCF pexec configuration (三模型 pass-through, 各 agent 各后端) ──────
# 3model (2026-07-01): 从单 dsv4p_nv 坍缩态扩为三模型直路由, 三 agent 各对应一真实后端.
#   hermes   → kimi_nv  (f966661c nvquery-kimi-k2_6)
#   opencode → dsv4p_nv (8915fd28 sglang-deepseek-v4-pro)
#   openclaw → glm5_1_nv (6155636e ai-glm-5_1)
# NVCF 平台实测 (2026-07-01 key1, 169 functions): 三 id 均 ACTIVE 且 pexec 200.
# 思考能力抓包实测 (2026-07-01 key1 直连 NVCF, 完整 dump 全字段, 足 max_tokens + 推理题):
#   - deepseek sglang 8915fd28: ★ 真支持思考. 触发参数=reasoning_effort(取值 max/high/...),
#     内容在 message.reasoning_content(非流式) / delta.reasoning_content(流式逐块). rc 非空 174-343 字符.
#     thinking:{type:enabled} 对 sglang 无效(200 但 rc 空, 参数被忽略).
#   - glm5.1 6155636e: ★ 真支持思考, 但触发方式与 deepseek 完全不同!
#     触发参数=chat_template_kwargs:{enable_thinking:true} (glm 原生 chat template 方式, 非 reasoning_effort).
#     内容字段同 reasoning_content. rc 非空 1388-1757 字符, usage completion_tokens plain 224→思考 711.
#     reasoning_effort 任何合法值(none/minimal/low/medium/high/xhigh) → 200 但 rc 恒空(无效); =max → 400.
#     thinking:{type:enabled} / 顶层 enable_thinking / thinking:"enabled" → 400 拒收.
#   - kimi f966661c: ★ 真支持思考. 触发参数=reasoning_effort(同 deepseek, OpenAI 风格),
#     也接受 thinking:{type:enabled} / chat_template_kwargs.enable_thinking (三种都 rc 非空 878-3193).
#     内容字段同 reasoning_content. 用 reasoning_effort 与 deepseek 保持一致.
# 教训: NVCF 每个 function 思考触发参数各不相同, 不能假设统一, 必须逐个完整 dump 抓包.
# inject 字段语义: dict, key=要注入的 body 参数路径, value=要设的值; 客户端已自带该参数则不覆盖.
NVCF_BASE_URL = os.environ.get("NVCF_BASE_URL", "api.nvcf.nvidia.com")
NVCF_PEXEC_MODELS = {
    "kimi_nv": {
        "function_id": os.environ.get("NVCF_KIMI_FUNCTION_ID",
                                      "f966661c-790d-4f71-b973-c525fb8eafd4"),  # nvquery-kimi-k2_6 (ACTIVE, hermes 专用)
        "strip_params": ["thinking_budget"],  # NVCF 拒 thinking_budget → 400
        # ★ 抓包证实 (2026-07-01): kimi 接受 reasoning_effort/thinking:{type:enabled}/chat_template_kwargs 三种触发,
        # 均返回非空 reasoning_content (rc 878-3193). 与 deepseek sglang 同用 OpenAI 风格 reasoning_effort 最一致.
        # 客户端(hermes)自带则不覆盖.
        "inject": {"reasoning_effort": "medium"},
    },
    "dsv4p_nv": {
        "function_id": os.environ.get("NVCF_DEEPSEEK_FUNCTION_ID",
                                      "8915fd28-fe8f-47d6-a35d-d745d78b35d5"),  # sglang-deepseek-v4-pro (ACTIVE, opencode 专用)
        "strip_params": [],  # deepseek params 全透传
        # ★ 抓包证实: reasoning_effort 触发 sglang 真思考, rc 非空. 客户端(openclaw --thinking)自带则不覆盖.
        "inject": {"reasoning_effort": "medium"},
    },
    "glm5_1_nv": {
        "function_id": os.environ.get("NVCF_GLM51_FUNCTION_ID",
                                      "6155636e-8ca8-4d9a-b4e5-4e8d231dfd3f"),  # ai-glm-5_1 (ACTIVE, openclaw 专用)
        # ★ strip reasoning_effort(对 glm5.1 无效且 =max 会 400) + thinking 字段(400) + thinking_budget(400)
        "strip_params": ["thinking_budget", "reasoning_effort", "thinking"],
        # ★ 抓包证实: glm5.1 唯一有效触发=chat_template_kwargs.enable_thinking=true (glm 原生方式).
        # 客户端(opencode)不发此参数, 网关必须注入; 已自带则不覆盖.
        "inject": {"chat_template_kwargs": {"enable_thinking": True}},
    },
}

# ─── NV API keys for NVCF pexec (all models use same 5 keys) ──────────────
HM_NV_KEYS = []
for i in range(1, 6):
    key = os.environ.get(f"HM_NV_KEY{i}", "")
    if key:
        HM_NV_KEYS.append(key)
HM_NUM_KEYS = len(HM_NV_KEYS)

# ─── Per-key mihomo SOCKS5 proxy URLs ──────────────────────────────────────
# K1→7894, K2→direct, K3→7896, K4→direct, K5→7899  (Rproxy: empty=direct)
HM_NV_PROXY_URLS = []
for i in range(1, 6):
    url = os.environ.get(f"HM_NV_PROXY_URL{i}", "")
    HM_NV_PROXY_URLS.append(url)  # Rproxy: keep ALL slots incl. empty for correct index alignment

if HM_NUM_KEYS < 5:
    print(f"[HM-CONFIG] WARN: only {HM_NUM_KEYS} NV keys configured (expected 5)", file=sys.stderr, flush=True)

# ─── R40 removed: no more LiteLLM glm5.1 HTTP containers ───

# ─── Three-model tiers (3model 2026-07-01: 各 agent 各后端, 无跨 tier fallback) ───
# NV_MODEL_TIERS 仅用于 get_tier_index 定位 start tier; upstream.execute_request 改 tier_order=[mapped_model]
# 单元素, 天然无跨 tier fallback (各 agent 各后端语义, 不允许 deepseek 悄悄变 glm5.1).
NV_MODEL_TIERS = ["kimi_nv", "dsv4p_nv", "glm5_1_nv"]

NV_MODEL_IDS = {
    "kimi_nv": "moonshotai/kimi-k2.6",
    "dsv4p_nv": "deepseek-ai/deepseek-v4-pro",
    "glm5_1_nv": "z-ai/glm-5.1",
}

DEFAULT_NV_MODEL = "dsv4p_nv"  # 裸 model 兜底 (opencode 裸名即此)

# ─── Tier timeout budget ──────────────────────────────────────────────────
TIER_TIMEOUT_BUDGET_S = float(os.environ.get("TIER_TIMEOUT_BUDGET_S", "60"))

# ─── Agent suffix (unify-nv: _nv 通用, 非 Hermes 专属) ───────────────────
AGENT_SUFFIXES = {
    "_nv": {"name": "NVCus", "format": "openai"},
}
DEFAULT_AGENT_SUFFIX = "_nv"

# ─── Model name mapping (3model 2026-07-01: pass-through, 不再坍缩) ─────
# 三模型各自路由到对应内部 key, 不再统一坍缩到 dsv4p_nv.
# detect_nv_model() 对未知名 fallback 到 DEFAULT_NV_MODEL (dsv4p_nv).
MODEL_MAP = {
    "kimi_nv": "kimi_nv",
    "kimi-k2.6": "kimi_nv",
    "moonshotai/kimi-k2.6": "kimi_nv",
    "dsv4p_nv": "dsv4p_nv",
    "deepseek-v4-pro": "dsv4p_nv",
    "deepseek-ai/deepseek-v4-pro": "dsv4p_nv",
    "glm5_1_nv": "glm5_1_nv",
    "glm5.1": "glm5_1_nv",
    "z-ai/glm-5.1": "glm5_1_nv",
}

def detect_nv_model(model_id: str) -> str:
    """Map a frontend model name to the internal NV model key.

    Returns: one of kimi_nv / dsv4p_nv / glm5_1_nv. Falls back to
    DEFAULT_NV_MODEL for unrecognized names.
    """
    mapped = MODEL_MAP.get(model_id, None)
    if mapped and mapped in NV_MODEL_IDS:
        return mapped
    return DEFAULT_NV_MODEL

def get_tier_index(mapped_model: str) -> int:
    """Get the tier index for a mapped model."""
    try:
        return NV_MODEL_TIERS.index(mapped_model)
    except ValueError:
        return 0

# ─── Token estimation ──────────────────────────────────────────────────────
CHARS_PER_TOKEN_ESTIMATE = float(os.environ.get("CHARS_PER_TOKEN_ESTIMATE", "3.0"))

# ─── Outbound throttle ──────────────────────────────────────────────────────
MIN_OUTBOUND_INTERVAL_S = float(os.environ.get("MIN_OUTBOUND_INTERVAL_S", "1.5"))
_outbound_last_sent = 0.0
_outbound_throttle_lock = threading.Lock()

def throttle_outbound():
    """Enforce MIN_OUTBOUND_INTERVAL_S between consecutive outbound requests."""
    if MIN_OUTBOUND_INTERVAL_S <= 0:
        return
    global _outbound_last_sent
    with _outbound_throttle_lock:
        now = time.monotonic()
        elapsed = now - _outbound_last_sent
        wait = MIN_OUTBOUND_INTERVAL_S - elapsed
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _outbound_last_sent = now

# ─── Context window (3model: 三模型各 131072) ───────────────────────────
MODEL_INPUT_TOKEN_SAFETY = {
    "kimi_nv": 131072,
    "dsv4p_nv": 131072,
    "glm5_1_nv": 131072,
}
DEFAULT_CONTEXT_FALLBACK = 131072

# ─── Thread locks for logging ────────────────────────────────────────────
_log_lock = threading.Lock()
_metrics_lock = threading.Lock()
_error_detail_lock = threading.Lock()

# ─── Re-exports for backward compatibility (Reng modularization) ──────────
# These state machines were extracted to their own modules. Re-export here so
# all existing `from .config import _next_nv_key / is_key_cooling / ...`
# statements in handlers.py and upstream.py keep working unchanged.
# NOTE: imported at end-of-file so LOG_DIR / HM_NUM_KEYS (needed by rr_counter)
# are already defined when the import resolves.
from .rr_counter import (  # noqa: E402
    _next_nv_key,
    _save_rr_counter,
)


# ─── R502: Stream upgrade for non-stream requests ──────────────────────
# Non-stream reqs to NVCF have ~48%% SR vs ~87%% for stream (kimi-k2.6 thinking).
# NVCF server must complete full inference before sending first byte in non-stream,
# causing frequent pexec_timeout. Stream mode avoids this by establishing TTFB earlier.
# FORCE_STREAM_UPGRADE=1: upgrade non-stream → stream internally, accumulate SSE,
# return non-stream JSON to caller. Zero caller-visible change.
# R502: When force-stream-upgrade is active, non-stream requests are sent as stream
# to NVCF. Thinking requests (injected thinking:type:enabled) need longer for first
# byte. This override extends the per-attempt upstream timeout for upgraded requests
# only (original non-stream callers). Default: 55s (vs 25s normal), giving thought
# models more time to emit the first SSE chunk.
HM_FORCE_STREAM_UPGRADE_TIMEOUT = int(os.environ.get('HM_FORCE_STREAM_UPGRADE_TIMEOUT', '55'))
HM_FORCE_STREAM_UPGRADE = os.environ.get('HM_FORCE_STREAM_UPGRADE', '0')

# ─── 跨机 peer fallback (2026-07-01, 用户要求两台互备) ──────────────────
# 本机 hm40006 在 all_tiers_exhausted (单 tier 5 key 全失败) 时, 转发请求到对端 hm40006
# 同模型, 而非直接返回 502. 对端同样 all_keys_exhausted 才真正返回 502.
# 循环防护: 转发请求带 X-Fallback-Hop: 1 头, 对端收到该头 ≥1 时不再转发 (无状态 hop count).
# 安全约束 (cc2 三轮仲裁): 只在 tier 耗尽时转发, 不在单 key SSL error 转发
#   (否则 F-fix 删的跨机重试以转发形式复活, 且两次跨机往返比本地重试慢).
# 透传: 流式 SSE + 非 JSON 均透传, 对端响应原样回客户端.
# env: HM_PEER_FALLBACK_URL (对端 hm40006 base, 如 http://100.109.57.26:40006)
#      HM_PEER_FALLBACK_ENABLED (1 开启, 默认关)
HM_PEER_FALLBACK_ENABLED = os.environ.get('HM_PEER_FALLBACK_ENABLED', '0') == '1'
HM_PEER_FALLBACK_URL = os.environ.get('HM_PEER_FALLBACK_URL', '').rstrip('/')
# 转发请求自身的超时 (秒). 对端 hm40006 内部有自己的 tier budget, 这里只限转发整体上限.
HM_PEER_FALLBACK_TIMEOUT = int(os.environ.get('HM_PEER_FALLBACK_TIMEOUT', '120'))
from .cooldown import (  # noqa: E402
    is_key_cooling,
    mark_key_cooling,
    reset_key429_count,
    KEY_COOLDOWN_S,
    TIER_COOLDOWN_S,
)
