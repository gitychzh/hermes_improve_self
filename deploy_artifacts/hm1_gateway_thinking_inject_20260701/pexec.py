#!/usr/bin/env python3
"""NVCF pexec request construction and response validation.

Extracted from upstream.py (Reng modularization). Logic is byte-for-byte
equivalent to the original; no behavioral change.

- _build_pexec_body: per-model param stripping (strip_params declaration)
- _check_empty_200: detect 200 responses with null/empty choices → treat as failure
"""
import json

from .config import NV_MODEL_IDS
from .logger import _log


def _build_pexec_body(oai_body, tier_model, nvcf_config):
    """Build NVCF pexec request body with per-model param stripping.

    R38.12: Each model declares which params NVCF pexec rejects via strip_params.
    - deepseek/kimi: strip_params=[] → all params pass through ✅
    - glm5.1: strip_params=["thinking_budget"] → strip thinking_budget (NVCF 400) ❌
      reasoning_effort is OK (tested 200 OK) → NOT stripped.

    Args:
        oai_body: original OpenAI-format request body from Hermes
        tier_model: internal NV model key (dsv4p_nv)
        nvcf_config: NVCF_PEXEC_MODELS[tier_model] dict

    Returns: request body dict, ready for json.dumps
    """
    pexec_body = dict(oai_body)
    pexec_body["model"] = NV_MODEL_IDS[tier_model]

    # Per-model param stripping (declaration in nvcf_config["strip_params"])
    strip_params = nvcf_config.get("strip_params", [])
    for param in strip_params:
        pexec_body.pop(param, None)

    # thinking-inject (2026-07-01): 网关侧统一补 thinking:{type:"enabled"}.
    # 仅对声明了 inject_thinking=True 的 model 生效 (当前仅 dsv4p_nv/dynamo).
    # dynamo function 触发 reasoning_content 的硬条件是 body 必须带 thinking:{type:enabled};
    # hermes (legacy path 不注入) / opencode (只发 reasoning_effort) 都缺这个字段.
    # 已有 thinking 字段则不覆盖 (openclaw 自带注入, 尊重其 reasoning_effort 配置).
    if nvcf_config.get("inject_thinking") and "thinking" not in pexec_body:
        pexec_body["thinking"] = {"type": "enabled"}
        _log("HM-INJECT-THINKING", f"({tier_model}) body had no thinking field → injected thinking:{{type:enabled}}")

    return pexec_body


def _check_empty_200(resp, key_idx, tier_model, is_stream):
    """Check if a 200 response is actually empty (no real content).

    NV API can return 200 with null choices, null content, or empty response.
    These are treated as failures and trigger key cycling or fallback.

    Returns: True if empty 200, False if valid response.
    On valid non-stream: sets resp._hm_cached_body for later use.
    """
    content_length_str = resp.getheader("Content-Length", "-1")

    if is_stream:
        # Streaming: can't read body. Content-Length=0 is a strong signal.
        if content_length_str == "0":
            _log("HM-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 Content-Length:0 (stream)")
            return True
        return False

    # Non-streaming: read and inspect body
    resp_body = resp.read()
    resp._hm_cached_body = resp_body

    if not resp_body or len(resp_body) == 0:
        _log("HM-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 empty body (0 bytes)")
        return True

    try:
        oai_resp = json.loads(resp_body)
    except (json.JSONDecodeError, ValueError):
        _log("HM-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 unparseable body ({len(resp_body)}b)")
        return True

    choices = oai_resp.get("choices")
    if choices is None:
        _log("HM-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 choices=null")
        return True
    if isinstance(choices, list) and len(choices) == 0:
        _log("HM-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 choices=[] (empty)")
        return True
    if isinstance(choices, list) and choices[0] is None:
        _log("HM-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 choices[0]=null")
        return True
    if isinstance(choices, list) and len(choices) > 0:
        msg = choices[0].get("message")
        if msg is None:
            _log("HM-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 message=null")
            return True
        content = msg.get("content")
        if content is None:
            _log("HM-EMPTY-200", f"k{key_idx+1} ({tier_model}) → 200 content=null")
            return True

    return False
