#!/usr/bin/env python3
"""HTTP handler for NV proxy (nv_40006_uni) — 三 agent 通用.

R38.12 / unify-nv: ALL models use NVCF pexec direct path (SOCKS5 → ACTIVE functions).
Single-model: dsv4p_nv (no fallback). Per-tier 5-key sequential RR with persistent
counters (全局共享, N+1 跨 agent 连续).
MSG-FIX: messages ending with assistant → append user "Continue."
"""
import http.server
import json
import os
import time
import datetime
import uuid
import http.client
import socket
import urllib.parse

from .config import (
    NVU_NUM_KEYS,
    NV_MODEL_IDS, NV_MODEL_TIERS, DEFAULT_NV_MODEL, MODEL_MAP,
    detect_nv_model, get_tier_index,
    NVCF_PEXEC_MODELS,
    PROXY_ROLE, LISTEN_PORT,
    MODEL_INPUT_TOKEN_SAFETY, DEFAULT_CONTEXT_FALLBACK,
    NVU_GATEWAY_API_KEY,
    NVU_FORCE_STREAM_UPGRADE,
    NVU_FORCE_STREAM_UPGRADE_TIMEOUT,
    NVU_FORCE_STREAM_EXCLUDE_MODELS,
    NVU_PEER_FALLBACK_ENABLED,
    NVU_PEER_FALLBACK_URL,
    NVU_PEER_FALLBACK_TIMEOUT,
)
from .logger import _log, _log_metrics, _log_error_detail
from .upstream import execute_request, UpstreamResult
from .error_mapping import format_nv_all_keys_exhausted, format_nv_error_upstream


# R1-2026-07-01: identify which local agent sent the request, for per-agent
# full-chain analysis. Preference: explicit X-Caller header (set by openclaw's
# provider config). Fallback: User-Agent — "OpenAI/Python" = openclaw alt path;
# "python-httpx"/"python-requests" = hermes/opencode standalone. NB: the
# "opencode/" UA is intentionally NOT mapped to openclaw, because standalone
# opencode uses the same UA — rely on X-Caller instead.
def _detect_caller(user_agent: str, x_caller: str = "") -> str:
    xc = (x_caller or "").strip().lower()
    if xc:
        return xc
    ua = (user_agent or "").strip()
    if ua.startswith("OpenAI/Python"):
        return "openclaw"
    if ua.startswith("python-httpx"):
        return "httpx"
    if ua.startswith("python-requests"):
        return "requests"
    if ua.startswith("opencode/"):
        return "opencode-standalone"
    if ua:
        return "other"
    return "unknown"


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/health", "/"):
            self._send_json(200, {
                "status": "ok",
                "proxy_role": PROXY_ROLE,
                "nv_num_keys": NVU_NUM_KEYS,
                "nvcf_pexec_models": list(NVCF_PEXEC_MODELS.keys()),
                "nv_model_tiers": NV_MODEL_TIERS,
                "nv_default_model": DEFAULT_NV_MODEL,
                "port": LISTEN_PORT,
            })
        elif parsed.path in ("/v1/models", "/models"):
            self._proxy_models()
        else:
            self._send_json(404, {"error": {"message": "not found", "type": "invalid_request_error", "code": "404"}})

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/health", "/", "/v1/models", "/models", "/v1/chat/completions", "/chat/completions"):
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/v1/chat/completions", "/chat/completions"):
            self._handle_openai_nv()
        else:
            self._send_json(404, {"error": {"message": f"Hermes proxy only serves /v1/chat/completions. Role={PROXY_ROLE}",
                                             "type": "invalid_request_error", "code": "404"}})

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    # ─── /v1/chat/completions — OpenAI format (three agents / _nv) ───
    def _handle_openai_nv(self):
        """Handle OpenAI-format requests from Hermes agent.

        R38.12: ALL models use NVCF pexec (no LiteLLM routing).
        MSG-FIX: if messages ends with assistant role, append user "Continue."
        """
        if not self._check_auth():
            return
        t_start = time.time()
        request_id = str(uuid.uuid4())[:8]
        metrics = {
            "request_id": request_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "path": "/v1/chat/completions",
            "proxy_role": PROXY_ROLE,
            "request_model": "?",
            "mapped_model": "?",
            "agent_type": "_nv",
            "caller": _detect_caller(self.headers.get("User-Agent", ""), self.headers.get("X-Caller", "")),
            "stream": False,
            "total_input_chars": 0,
            "ttfb_ms": None,
            "duration_ms": 0,
            "status": 0,
            "error_type": None,
            "error_message": None,
            "upstream": "nv",
        }

        try:
            body_len = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(body_len) if body_len > 0 else b""
            body = json.loads(raw) if raw else {}
        except Exception as e:
            self._send_json(400, {"error": {"message": f"bad request: {e}", "type": "invalid_request_error", "code": "400"}})
            metrics["status"] = 400
            metrics["error_type"] = "BadRequest"
            _log_metrics(metrics)
            return

        request_model = body.get("model", DEFAULT_NV_MODEL)
        is_stream = body.get("stream", False)
        # mapped_model 先算, 供 per-model force-stream 排除判断 (R576)
        mapped_model = detect_nv_model(request_model)
        metrics["mapped_model"] = mapped_model
        metrics["start_tier_idx"] = get_tier_index(mapped_model)
        # R502: Force stream upgrade - non-stream requests upgraded to stream internally
        # to avoid NVCF pexec_timeout. kimi-k2.6 thinking needs full inference time in
        # non-stream mode; stream mode establishes TTFB earlier. SSE is accumulated and
        # returned as non-stream JSON to the caller.
        # R576 (2026-07-03): per-model 排除. dsv4p_nv 流式+thinking 实测 content 丢失 90%
        # (思考消耗 max_tokens, content 在末尾 chunk 且 finish=length 时不产生), 而走
        # integrate 非流原生 26-35s 正常返回 content, 故对 dsv4p_nv 关闭 force-stream.
        force_stream_upgrade = (NVU_FORCE_STREAM_UPGRADE == "1"
                                and not is_stream
                                and mapped_model not in NVU_FORCE_STREAM_EXCLUDE_MODELS)
        if force_stream_upgrade:
            body["stream"] = True
            is_stream_upstream = True
            _log("NV-FORCE-STREAM", "upgrading non-stream->stream for upstream (caller sees non-stream)")
        else:
            is_stream_upstream = is_stream
        metrics["request_model"] = request_model
        metrics["stream"] = is_stream  # record original caller intent
        metrics["force_stream_upgrade"] = force_stream_upgrade
        # OC-R3 (2026-07-01): 记录 reasoning_effort / thinking 以便按思考级别分桶回溯.
        # cc2 指出: 不记 effort 则 effort 类实验改前/改后无法分桶, bursty NVCF 下不可信.
        metrics["reasoning_effort"] = body.get("reasoning_effort")
        thinking_field = body.get("thinking")
        metrics["thinking_type"] = thinking_field.get("type") if isinstance(thinking_field, dict) else thinking_field

        json_chars = len(json.dumps(body))
        metrics["total_input_chars"] = json_chars

        _log("REQ", f"model={request_model}→{mapped_model}→tier_idx={metrics['start_tier_idx']} "
                    f"stream={is_stream} msgs={len(body.get('messages',[]))} agent=_nv caller={metrics['caller']} "
                    f"effort={metrics['reasoning_effort']} thinking={metrics['thinking_type']}")

        # ─── MSG-FIX (R35.10) ───
        messages = body.get("messages", [])
        original_msg_count = len(messages)
        if messages and isinstance(messages[-1], dict) and messages[-1].get("role") == "assistant":
            body["messages"].append({"role": "user", "content": "Continue."})
            _log("MSG-FIX", f"appended user 'Continue.' (original msgs={original_msg_count}, "
                           f"now {len(body['messages'])})")

        # Add stream_options.include_usage for streaming metrics
        if is_stream_upstream and "stream_options" not in body:
            body["stream_options"] = {"include_usage": True}

        # ─── Execute request via NVCF pexec with three-tier fallback ───
        # thinking-timeout (2026-07-01, cc2 核对驱动): 思考型请求无论流式与否都用扩展 timeout.
        # 抓包实测: glm5.1 思考 16-63s, deepseek sglang 思考 5-30s; 默认 UPSTREAM_TIMEOUT=25s
        # 对 glm5.1 长思考太短, 流式请求被 25s 砍掉后多 key 重试累积 502 (cc2 复现 3/4 流式 502).
        # 判定: 该 model 的 inject 配置非空(网关会注入思考触发参数) OR 客户端自带思考参数.
        nvcf_cfg = NVCF_PEXEC_MODELS.get(mapped_model, {})
        is_thinking_req = bool(nvcf_cfg.get("inject")) or bool(body.get("reasoning_effort")) or bool(body.get("chat_template_kwargs")) or bool(body.get("thinking"))
        if force_stream_upgrade:
            result = execute_request(self, body, mapped_model, request_id, metrics, t_start, upstream_timeout_override=NVU_FORCE_STREAM_UPGRADE_TIMEOUT)
        elif is_thinking_req:
            result = execute_request(self, body, mapped_model, request_id, metrics, t_start, upstream_timeout_override=NVU_FORCE_STREAM_UPGRADE_TIMEOUT)
            _log("NV-THINKING-TIMEOUT", f"({mapped_model}) thinking request stream={is_stream} → extended timeout {NVU_FORCE_STREAM_UPGRADE_TIMEOUT}s")
        else:
            result = execute_request(self, body, mapped_model, request_id, metrics, t_start)

        if not result.success:
            if result.all_keys_exhausted:
                metrics["status"] = 429 if result.all_429 else 502
                metrics["error_type"] = "all_tiers_exhausted"
                metrics["duration_ms"] = result.elapsed_ms
                metrics["total_cycle_attempts"] = len(result.key_cycle_attempts)
                metrics["fallback_tiers_used"] = result.fallback_tiers_used
                metrics["tier_model"] = mapped_model
                metrics["error_subcategory"] = "all_tiers_failed_in_mapped_tier"
                metrics["tier_summaries"] = result.tier_attempts

                # ─── 跨机 peer fallback (2026-07-01) ───────────────────────
                # 本机单 tier 5 key 全失败(all_tiers_exhausted) 时, 转发到对端 nv_40006_uni 同模型.
                # 循环防护: 请求头 X-Fallback-Hop ≥1 表示"我是被转发来的", 不再转发.
                # 安全: 只在 tier 耗尽时转发, 不在单 key SSL error 转发 (cc2 仲裁).
                # 429 (all_429) 是 key 级限流, 跨机不增加 key 池, 不转发 (直接返回让客户端退避).
                hop = self.headers.get("X-Fallback-Hop", "0")
                try:
                    hop_n = int(hop)
                except (ValueError, TypeError):
                    hop_n = 0
                is_429 = bool(result.all_429)
                if (NVU_PEER_FALLBACK_ENABLED and NVU_PEER_FALLBACK_URL
                        and hop_n < 1 and not is_429):
                    _log("NV-PEER-FB", f"local all_tiers_exhausted (model={mapped_model}), "
                                       f"attempting peer fallback to {NVU_PEER_FALLBACK_URL}")
                    ok = self._peer_fallback(body, mapped_model, is_stream, metrics)
                    if ok:
                        metrics["peer_fallback_used"] = True
                        _log_metrics(metrics)
                        return
                    _log("NV-PEER-FB", f"peer fallback FAILED for model={mapped_model}, "
                                       f"returning local 502")
                elif hop_n >= 1:
                    _log("NV-PEER-FB", f"peer-originated request (hop={hop_n}) also "
                                       f"all_tiers_exhausted, no further fallback, returning 502")

                _log_metrics(metrics)

                error_payload, client_status = format_nv_all_keys_exhausted(result, mapped_model, request_model)
                extra_hdrs = None
                if client_status == 429:
                    extra_hdrs = {"retry-after": "5"}
                self._send_json(client_status, error_payload, extra_headers=extra_hdrs)
                return
            else:
                error_json = result.final_error_json
                resp_status = result.final_resp_status
                error_payload, client_status = format_nv_error_upstream(error_json, request_model, resp_status)
                extra_hdrs = None
                if client_status == 429:
                    extra_hdrs = {"retry-after": "5"}
                metrics["status"] = client_status
                metrics["error_type"] = "nv_upstream_error"
                metrics["error_message"] = str(error_json)[:200]
                metrics["duration_ms"] = int((time.time() - t_start) * 1000)
                metrics["tier_model"] = mapped_model
                metrics["error_subcategory"] = "nv_upstream_error"
                _log_metrics(metrics)
                self._send_json(client_status, error_payload, extra_headers=extra_hdrs)
                return

        # ─── Success: pass through NVCF pexec response ───
        resp = result.resp
        conn = result.conn
        metrics["nv_key_idx"] = result.nv_key_idx
        metrics["litellm_model"] = result.nv_model_label
        metrics["tier_model"] = result.tier_model
        metrics["fallback_tiers_used"] = result.fallback_tiers_used
        if result.key_cycle_attempts:
            metrics["key_cycle_429s_before_success"] = len(result.key_cycle_attempts)
            metrics["key_cycle_details"] = result.key_cycle_attempts
        if result.fallback_tiers_used and len(result.fallback_tiers_used) > 1:
            metrics["fallback_occurred"] = True

        cached_body = getattr(resp, '_hm_cached_body', None)

        if is_stream and not force_stream_upgrade:
            self._stream_openai_passthrough(resp, conn, metrics, t_start, request_model)
        elif force_stream_upgrade:
            # R502: Accumulate SSE stream -> reconstruct non-stream JSON for caller
            self._accumulate_stream_to_nonstream(resp, conn, metrics, t_start, request_model)
        else:
            ttfb_start = time.time()
            if cached_body is not None:
                resp_body = cached_body
            else:
                resp_body = resp.read()
            metrics["status"] = 200
            metrics["duration_ms"] = int((time.time() - t_start) * 1000)
            metrics["ttfb_ms"] = int((ttfb_start - t_start) * 1000)

            try:
                oai_response = json.loads(resp_body)
                usage = oai_response.get("usage", {})
                metrics["input_tokens"] = usage.get("prompt_tokens", 0)
                metrics["output_tokens"] = usage.get("completion_tokens", 0)
                choices = oai_response.get("choices", [])
                if choices:
                    metrics["finish_reason"] = choices[0].get("finish_reason")
            except Exception:
                pass

            _log_metrics(metrics)

            self.send_response(resp.status)
            for h in ["Content-Type"]:
                v = resp.getheader(h)
                if v:
                    self.send_header(h, v)
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)
            conn.close()

    def _accumulate_stream_to_nonstream(self, resp, conn, metrics, t_start, request_model):
        """R502: Read SSE stream from upstream, accumulate chunks, return as non-stream JSON.

        The upstream was sent stream=True (because of FORCE_STREAM_UPGRADE), but the
        caller expects a non-stream JSON response. We accumulate all SSE data chunks,
        reconstruct the OpenAI non-stream format, and return it to the caller.
        """
        sse_buffer = ""
        all_content_parts = []
        reasoning_content_parts = []
        finish_reason = None
        model_id = None
        usage = {}
        ttfb_recorded = False
        chunk_id = None

        try:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break

                if not ttfb_recorded:
                    metrics["ttfb_ms"] = int((time.time() - t_start) * 1000)
                    ttfb_recorded = True

                sse_buffer += chunk.decode("utf-8", errors="replace")

                while "\n" in sse_buffer:
                    line, sse_buffer = sse_buffer.split("\n", 1)
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]" or not data_str:
                        continue
                    try:
                        data = json.loads(data_str)
                        # Extract content from choices
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            rc = delta.get("reasoning_content")
                            if rc:
                                reasoning_content_parts.append(rc)
                            cont = delta.get("content")
                            if cont:
                                all_content_parts.append(cont)
                            fr = choices[0].get("finish_reason")
                            if fr:
                                finish_reason = fr
                        # Extract model and id
                        if not model_id:
                            model_id = data.get("model", "")
                        if not chunk_id:
                            chunk_id = data.get("id", "")
                        # Extract usage
                        chunk_usage = data.get("usage", {})
                        if chunk_usage:
                            pt = chunk_usage.get("prompt_tokens", 0)
                            ct = chunk_usage.get("completion_tokens", 0)
                            if pt > 0:
                                usage["prompt_tokens"] = pt
                            if ct > 0:
                                usage["completion_tokens"] = ct
                    except json.JSONDecodeError:
                        pass

            # R576 (2026-07-03): 处理 sse_buffer 残留.
            # 循环 while "\n" in sse_buffer 只处理含换行的完整行, 最后一行若无 trailing
            # newline (常见于 NVCF/integrate 流末尾的 content chunk, 连接读完即断) 会留在
            # sse_buffer 未被解析 → content 丢失 (实测 dsv4p force-stream 19/21 content=0c).
            # 修复: 循环结束后对 sse_buffer 残留再跑一遍行解析.
            if sse_buffer.strip():
                line = sse_buffer.strip()
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str and data_str != "[DONE]":
                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                rc = delta.get("reasoning_content")
                                if rc:
                                    reasoning_content_parts.append(rc)
                                cont = delta.get("content")
                                if cont:
                                    all_content_parts.append(cont)
                                fr = choices[0].get("finish_reason")
                                if fr:
                                    finish_reason = fr
                            if not model_id:
                                model_id = data.get("model", "")
                            if not chunk_id:
                                chunk_id = data.get("id", "")
                            chunk_usage = data.get("usage", {})
                            if chunk_usage:
                                pt = chunk_usage.get("prompt_tokens", 0)
                                ct = chunk_usage.get("completion_tokens", 0)
                                if pt > 0:
                                    usage["prompt_tokens"] = pt
                                if ct > 0:
                                    usage["completion_tokens"] = ct
                        except json.JSONDecodeError:
                            pass

        except (http.client.RemoteDisconnected, ConnectionResetError, OSError,
                http.client.IncompleteRead, socket.timeout) as e:
            elapsed_ms = int((time.time() - t_start) * 1000)
            error_class = type(e).__name__
            _log("ERR", f"FORCE-STREAM-ACCUMULATE {error_class} after {elapsed_ms}ms: {e}")
            metrics["error_type"] = f"ForceStreamAccumulate_{error_class}"
        except Exception as e:
            elapsed_ms = int((time.time() - t_start) * 1000)
            error_class = type(e).__name__
            _log("ERR", f"FORCE-STREAM-ACCUMULATE unexpected {error_class} after {elapsed_ms}ms: {e}")
            metrics["error_type"] = f"ForceStreamAccumulate_{error_class}"

        if metrics.get("error_type"):
            metrics["status"] = 502
            metrics["duration_ms"] = int((time.time() - t_start) * 1000)
            # R507: ensure tier_model set even on force_stream_upgrade error path
            if not metrics.get("tier_model"):
                metrics["tier_model"] = metrics.get("mapped_model")
            _log_metrics(metrics)
            self._send_json(502, {"error": {"message": "upstream stream accumulation failed",
                                            "type": "upstream_error", "code": "502"}})
            try:
                conn.close()
            except Exception:
                pass
            return

        # Reconstruct non-stream OpenAI response format
        full_content = "".join(all_content_parts)
        full_reasoning = "".join(reasoning_content_parts)
        message = {"role": "assistant", "content": full_content}
        if full_reasoning:
            message["reasoning_content"] = full_reasoning

        non_stream_resp = {
            "id": chunk_id or ("chatcmpl-" + str(uuid.uuid4())[:8]),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_id or request_model,
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": finish_reason or "stop",
            }],
        }
        if usage:
            non_stream_resp["usage"] = usage

        resp_body = json.dumps(non_stream_resp, ensure_ascii=False).encode("utf-8")

        # Update metrics
        metrics["status"] = 200
        metrics["duration_ms"] = int((time.time() - t_start) * 1000)
        if not metrics.get("ttfb_ms"):
            metrics["ttfb_ms"] = metrics["duration_ms"]
        if usage:
            metrics["input_tokens"] = usage.get("prompt_tokens", 0)
            metrics["output_tokens"] = usage.get("completion_tokens", 0)
        metrics["finish_reason"] = finish_reason or "stop"
        metrics["accumulated_stream_chars"] = len(full_content)
        if full_reasoning:
            metrics["accumulated_reasoning_chars"] = len(full_reasoning)

        _log("NV-FORCE-STREAM-OK", f"accumulated {len(all_content_parts)} chunks, "
              f"content={len(full_content)}c reasoning={len(full_reasoning)}c in {metrics['duration_ms']}ms")
        _log_metrics(metrics)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)
        try:
            conn.close()
        except Exception:
            pass

    def _stream_openai_passthrough(self, resp, conn, metrics, t_start, request_model):
        """Pass through OpenAI streaming SSE response directly to Hermes."""
        ttfb_recorded = False
        streaming_input_tokens = 0
        streaming_output_tokens = 0
        sse_buffer = ""

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        try:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    remaining = sse_buffer.strip()
                    if remaining and remaining.startswith("data:") and remaining[5:].strip() != "[DONE]":
                        data_str = remaining[5:].strip()
                        if data_str:
                            try:
                                data = json.loads(data_str)
                                fr = data.get("choices", [{}])[0].get("finish_reason")
                                if fr:
                                    metrics["finish_reason"] = fr
                                chunk_usage = data.get("usage", {})
                                if chunk_usage:
                                    pt = chunk_usage.get("prompt_tokens", 0)
                                    ct = chunk_usage.get("completion_tokens", 0)
                                    if pt > 0:
                                        streaming_input_tokens = pt
                                    if ct > 0:
                                        streaming_output_tokens = ct
                            except Exception:
                                pass
                    break

                if not ttfb_recorded:
                    metrics["ttfb_ms"] = int((time.time() - t_start) * 1000)
                    ttfb_recorded = True

                sse_buffer += chunk.decode("utf-8", errors="replace")

                try:
                    while "\n" in sse_buffer:
                        line, sse_buffer = sse_buffer.split("\n", 1)
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]" or not data_str:
                            continue
                        try:
                            data = json.loads(data_str)
                            chunk_usage = data.get("usage", {})
                            if chunk_usage:
                                pt = chunk_usage.get("prompt_tokens", 0)
                                ct = chunk_usage.get("completion_tokens", 0)
                                if pt > 0:
                                    streaming_input_tokens = pt
                                if ct > 0:
                                    streaming_output_tokens = ct
                            fr = data.get("choices", [{}])[0].get("finish_reason")
                            if fr:
                                metrics["finish_reason"] = fr
                        except json.JSONDecodeError:
                            pass
                except Exception:
                    pass

                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except Exception:
                    break

        except (http.client.RemoteDisconnected, ConnectionResetError,
                OSError, http.client.IncompleteRead, socket.timeout) as e:
            elapsed_ms = int((time.time() - t_start) * 1000)
            error_class = type(e).__name__
            _log("ERR", f"NV stream {error_class} after {elapsed_ms}ms: {e}")
            metrics["error_type"] = f"NVStream_{error_class}"
        except Exception as e:
            elapsed_ms = int((time.time() - t_start) * 1000)
            error_class = type(e).__name__
            _log("ERR", f"NV stream unexpected {error_class} after {elapsed_ms}ms: {e}")
            metrics["error_type"] = f"NVStream_{error_class}"

        if metrics.get("error_type"):
            metrics["status"] = 502
        else:
            metrics["status"] = 200
        metrics["duration_ms"] = int((time.time() - t_start) * 1000)
        if streaming_input_tokens > 0:
            metrics["input_tokens"] = streaming_input_tokens
        if streaming_output_tokens > 0:
            metrics["output_tokens"] = streaming_output_tokens
        _log_metrics(metrics)

        try:
            conn.close()
        except Exception:
            pass

    # ─── /v1/models ───
    def _proxy_models(self):
        """Return OpenAI-format model list for Hermes (single canonical model)."""
        if not self._check_auth():
            return
        all_models = []
        for model_key in NV_MODEL_TIERS:
            context_len = MODEL_INPUT_TOKEN_SAFETY.get(model_key, DEFAULT_CONTEXT_FALLBACK)
            all_models.append({
                "id": model_key,
                "object": "model",
                "created": 0,
                "owned_by": "nvidia_hermes",
                "context_length": context_len,
            })
        self._send_json(200, {"object": "list", "data": all_models})

    # ─── Helpers ───
    def _check_auth(self):
        """Gate /v1/* endpoints on Authorization: Bearer <NVU_GATEWAY_API_KEY>
        or x-api-key: <NVU_GATEWAY_API_KEY>. /health & CORS preflight are exempt
        (handled by callers never invoking this). Empty key => no auth (back-compat).
        """
        expected = NVU_GATEWAY_API_KEY
        if not expected:
            return True
        auth = self.headers.get("Authorization") or self.headers.get("x-api-key") or ""
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        else:
            token = auth.strip()
        if token != expected:
            self._send_json(401, {"error": {"message": "invalid api key",
                                            "type": "invalid_request_error", "code": "401"}})
            return False
        return True

    def _peer_fallback(self, body, mapped_model, is_stream, metrics):
        """Forward request to peer nv_40006_uni (same model) when local all_tiers_exhausted.

        Returns True if we successfully relayed a response to the client (stream or
        non-stream), False if peer also failed (caller returns local 502).
        Loop prevention: sets X-Fallback-Hop: 1; peer sees hop≥1 and won't re-forward.
        Auth: sends Authorization: Bearer <NVU_GATEWAY_API_KEY> so peer's _check_auth passes.
        Safety (cc2): only called at all_tiers_exhausted, never on single-key SSL error.
        """
        if not NVU_PEER_FALLBACK_URL:
            return False
        # body 入参是已解析的 dict (handlers.py L134 json.loads(raw)), 重新序列化为
        # JSON bytes 给 http.client (传 dict 会触发 "can't concat str to bytes").
        if isinstance(body, (dict, list)):
            body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body_bytes = body.encode("utf-8")
        elif isinstance(body, (bytes, bytearray)):
            body_bytes = bytes(body)
        else:
            _log("NV-PEER-FB", f"body type {type(body).__name__} not serializable, abort")
            return False
        t_fb_start = time.time()
        # parse peer URL → http.client connection
        try:
            from urllib.parse import urlparse
            p = urlparse(NVU_PEER_FALLBACK_URL)
            host = p.hostname
            port = p.port or 40006
            peer_path = p.path.rstrip("/") + "/v1/chat/completions"
        except Exception as e:
            _log("NV-PEER-FB", f"bad NVU_PEER_FALLBACK_URL={NVU_PEER_FALLBACK_URL}: {e}")
            return False

        # copy inbound headers, override hop + auth + host
        fwd_headers = {}
        ct = self.headers.get("Content-Type", "application/json")
        fwd_headers["Content-Type"] = ct
        fwd_headers["X-Fallback-Hop"] = "1"
        fwd_headers["X-Fallback-Origin"] = PROXY_ROLE or "unknown"
        if NVU_GATEWAY_API_KEY:
            fwd_headers["Authorization"] = f"Bearer {NVU_GATEWAY_API_KEY}"
        # caller-supplied headers we want to preserve (e.g. X-Caller)
        for h in ("X-Caller", "X-Request-Id"):
            v = self.headers.get(h)
            if v:
                fwd_headers[h] = v
        fwd_headers["Content-Length"] = str(len(body_bytes))

        peer_conn = None
        try:
            peer_conn = http.client.HTTPConnection(host, port,
                                                  timeout=NVU_PEER_FALLBACK_TIMEOUT)
            peer_conn.request("POST", peer_path, body=body_bytes, headers=fwd_headers)
            resp = peer_conn.getresponse()
        except Exception as e:
            elapsed_ms = int((time.time() - t_fb_start) * 1000)
            _log("NV-PEER-FB", f"peer connect/request failed after {elapsed_ms}ms: "
                               f"{type(e).__name__}: {e}")
            if peer_conn:
                try: peer_conn.close()
                except Exception: pass
            metrics["peer_fallback_error"] = f"connect_{type(e).__name__}"
            metrics["peer_fallback_ms"] = elapsed_ms
            return False

        # peer returned an error status (e.g. 502/429) → don't relay, let caller 502
        if resp.status >= 500 or resp.status == 429:
            elapsed_ms = int((time.time() - t_fb_start) * 1000)
            # drain so connection can be reused/closed cleanly
            try: resp.read()
            except Exception: pass
            try: peer_conn.close()
            except Exception: pass
            _log("NV-PEER-FB", f"peer returned {resp.status} after {elapsed_ms}ms, "
                               f"not relaying, returning local 502")
            metrics["peer_fallback_error"] = f"peer_http_{resp.status}"
            metrics["peer_fallback_ms"] = elapsed_ms
            return False

        # success path — relay response to client
        metrics["peer_fallback_ms"] = int((time.time() - t_fb_start) * 1000)
        metrics["peer_fallback_status"] = resp.status
        ttfb_start = time.time()
        try:
            # send status + headers
            self.send_response(resp.status)
            relay_ct = resp.getheader("Content-Type") or ct
            self.send_header("Content-Type", relay_ct)
            # stream or chunked: prefer Connection close, no Content-Length
            self.send_header("Connection", "close")
            # propagate hop info so downstream knows this was a fallback
            self.send_header("X-Fallback-Served-By", PROXY_ROLE or "unknown")
            self.end_headers()

            # relay body in chunks (works for both SSE stream and buffered JSON)
            total = 0
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                if not metrics.get("ttfb_ms"):
                    metrics["ttfb_ms"] = int((time.time() - ttfb_start) * 1000)
                self.wfile.write(chunk)
                total += len(chunk)
            metrics["peer_fallback_bytes"] = total
            metrics["status"] = resp.status
            metrics["duration_ms"] = int((time.time() - t_fb_start) * 1000)
            _log("NV-PEER-FB", f"peer fallback OK: status={resp.status} "
                               f"bytes={total} ttfb={metrics.get('ttfb_ms')}ms")
            return True
        except Exception as e:
            elapsed_ms = int((time.time() - t_fb_start) * 1000)
            _log("NV-PEER-FB", f"peer relay failed after {elapsed_ms}ms: "
                               f"{type(e).__name__}: {e}")
            metrics["peer_fallback_error"] = f"relay_{type(e).__name__}"
            metrics["peer_fallback_ms"] = elapsed_ms
            return False
        finally:
            try: peer_conn.close()
            except Exception: pass

    def _send_json(self, code, data, extra_headers=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send_raw(code, body, "application/json", extra_headers)

    def _send_raw(self, code, body_bytes, content_type="application/json", extra_headers=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body_bytes)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, str(v))
        self.end_headers()
        self.wfile.write(body_bytes)

    def log_message(self, fmt, *args):
        pass  # Suppress default logging
