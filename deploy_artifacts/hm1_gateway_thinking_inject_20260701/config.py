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
UPSTREAM_TIMEOUT = int(os.environ.get("UPSTREAM_TIMEOUT", "45"))  # R38.5: 60→45 (NV p95<30s)

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

# ─── NVCF pexec configuration (single model: dsv4p_nv, 三 agent 通用) ──────
# unify-nv: 内部 model key 从 deepseek_hm_nv 改为 dsv4p_nv (反映通用语义, 非 Hermes 专属).
# 旧名 deepseek_hm_nv 在 MODEL_MAP 里保留为 alias, 向后兼容 hermes config 与 DB 历史.
NVCF_BASE_URL = os.environ.get("NVCF_BASE_URL", "api.nvcf.nvidia.com")
NVCF_PEXEC_MODELS = {
    "dsv4p_nv": {
        "function_id": os.environ.get("NVCF_DEEPSEEK_FUNCTION_ID",
                                      "ee2b0de2-dba5-4a21-993d-d393bacfb853"),  # dynamo-deepseek-v4-pro (ACTIVE, supports reasoning_content)
        # thinking-via-dynamo (2026-06-30): orion (4e533b45) does NOT emit reasoning_content
        # for any thinking param; dynamo (ee2b0de2) does, via deepseek-native thinking:{type:"enabled"}.
        # Verified: dynamo streaming returns reasoning_content chunks BEFORE content chunks.
        # strip_params still strips thinking_budget (glm5.1 legacy); thinking/reasoning_effort pass through.
        "strip_params": ["thinking_budget"],  # R277: strip thinking_budget — empty_200 root cause
        # thinking-inject (2026-07-01): 三 agent 网关侧统一注入 thinking:{type:"enabled"}.
        # 动机: dynamo function 触发 reasoning_content 的硬条件是 body 必须带 thinking:{type:enabled}.
        # - openclaw: 自带注入 (DSv4 thinking wrapper), 不受影响 (已有 thinking 时不覆盖).
        # - hermes: nv_cus 走 legacy path, 只给 kimi 注入 thinking, dsv4p_nv 不注入.
        # - opencode: 只发 reasoning_effort, 不发 thinking:{type:enabled}, 单独 effort 不触发 dynamo.
        # 网关侧补齐: 当 body 无 thinking 字段时补 {type:enabled}, 让三 agent 全部拿到思考链.
        # 安全: 仅对此 model 开启 (inject_thinking=True); glm5.1 等其他 model 不受影响.
        "inject_thinking": True,
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

# ─── Single-model tier (unify-nv: dsv4p_nv only, no fallback) ────────────
NV_MODEL_TIERS = ["dsv4p_nv"]

NV_MODEL_IDS = {
    "dsv4p_nv": "deepseek-ai/deepseek-v4-pro",
}

DEFAULT_NV_MODEL = "dsv4p_nv"  # unify-nv: 单模型 dsv4p, 三 agent 通用

# ─── Tier timeout budget ──────────────────────────────────────────────────
TIER_TIMEOUT_BUDGET_S = float(os.environ.get("TIER_TIMEOUT_BUDGET_S", "60"))

# ─── Agent suffix (unify-nv: _nv 通用, 非 Hermes 专属) ───────────────────
AGENT_SUFFIXES = {
    "_nv": {"name": "NVCus", "format": "openai"},
}
DEFAULT_AGENT_SUFFIX = "_nv"

# ─── Model name mapping (unify-nv: single canonical name dsv4p_nv) ───────
# 历史别名 (deepseek_hm_nv / dsv4p / deepseek* 等) 已移除, 统一为 dsv4p_nv.
# detect_nv_model() 对未知名 fallback 到 DEFAULT_NV_MODEL, 旧请求不受影响.
MODEL_MAP = {
    "dsv4p_nv": "dsv4p_nv",  # 唯一规范名
    "deepseek-v4-pro": "dsv4p_nv",  # thinking-via-dynamo: 让 openclaw DSv4 thinking wrapper 命中白名单
    # openclaw 的 createDeepSeekV4OpenAICompatibleThinkingWrapper 只认 model id
    # "deepseek-v4-pro" (split("/").pop()), 才会注入 thinking:{type:"enabled"}。
    # 此别名映射到内部 dsv4p_nv, 后端不变, 仅触发 openclaw 思考注入。
}

def detect_nv_model(model_id: str) -> str:
    """Map a frontend model name to the internal NV model key.

    Returns: dsv4p_nv (the only supported model). Falls back to
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

# ─── Context window (unify-nv: dsv4p_nv) ────────────────────────────────
MODEL_INPUT_TOKEN_SAFETY = {
    "dsv4p_nv": 131072,
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
from .cooldown import (  # noqa: E402
    is_key_cooling,
    mark_key_cooling,
    reset_key429_count,
    KEY_COOLDOWN_S,
    TIER_COOLDOWN_S,
)
