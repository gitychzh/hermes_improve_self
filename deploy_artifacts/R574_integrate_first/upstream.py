#!/usr/bin/env python3
"""Upstream request executor for NV proxy (nv_40006_uni) — 三 agent 通用.

Reng (HM1 self-change, authorized): modularized for long-term maintainability.
NVCF connection layer → gateway/nvcf_conn.py; pexec request
construction/validation → gateway/pexec.py. This file now holds the core
tier-key loop (_try_tier_keys) and three-tier fallback orchestration
(execute_request). Logic is byte-for-byte equivalent to the pre-refactor
version.

Rproxy (HM1 self-change, authorized): per-key direct/proxy routing is driven
purely by NVU_PROXY_URL<n> env (empty=direct, non-empty=mihomo SOCKS5).
k2/k4 direct, k1/k3/k5 via mihomo on HM1. _make_nvcf_proxy_conn (in nvcf_conn.py)
handles the empty→direct branch internally, so the unified call below routes
both paths.

R38.10: deepseek bypasses DEGRADING integrate API → NVCF pexec orion (ACTIVE).
R38.8:  Connection refused fast-break + startup retry.
R38.6:  sock.settimeout BEFORE getresponse, Connection:close.

Default tier: deepseek (primary) + kimi (fallback)
If all 5 keys fail → fallback to next tier.
If all tiers also all-fail → ABORT-NO-FALLBACK.

Chain: nv_40006_uni → NVCF pexec (deepseek/kimi only). K1/K2 direct, K3-K5 via mihomo SOCKS5 → NV API
"""
import json
import os
import http.client
import socket
import threading
import time

from .config import (
    NVU_KEYS, NVU_NUM_KEYS, NVU_PROXY_URLS,
    NV_MODEL_IDS, NV_MODEL_TIERS, DEFAULT_NV_MODEL, detect_nv_model,
    get_tier_index,
    NVCF_PEXEC_MODELS, NVCF_BASE_URL,
    UPSTREAM_TIMEOUT, TIER_TIMEOUT_BUDGET_S, NVU_FORCE_STREAM_UPGRADE_TIMEOUT,
    FALLBACK_GRAPH, FALLBACK_HEALTH_THRESHOLD,
    _next_nv_key,
    throttle_outbound,
    is_key_cooling, mark_key_cooling, reset_key429_count,
    TIER_COOLDOWN_S,
    NV_INTEGRATE_ENABLED, NV_INTEGRATE_HOST, NV_INTEGRATE_PATH,
    NV_INTEGRATE_KEY_COOLDOWN_S, NV_INTEGRATE_PATH_COOLDOWN_S, NV_INTEGRATE_MODELS,
)
from .logger import _log, _log_metrics, _log_error_detail
from .nvcf_conn import _make_nvcf_proxy_conn
from .pexec import _build_pexec_body, _check_empty_200
from . import func_health


class UpstreamResult:
    """Result from NVCF pexec upstream request execution."""
    def __init__(self):
        self.success = False
        # Success fields
        self.resp = None
        self.conn = None
        self.tier_model = ""
        self.nv_key_idx = 0
        self.nv_model_label = ""
        self.is_stream = False
        self.key_cycle_attempts = []
        self.upstream_type = "nvcf_pexec"
        self.tier_attempts = []
        self.fallback_tiers_used = []
        # R_multi: 本次 tier 选中的 function_id (用于上层 func_health.record_result)
        self.function_id = ""
        # Error fields
        self.all_keys_exhausted = False
        self.all_429 = False
        self.empty_200 = False
        self.elapsed_ms = 0
        self.final_error_json = None
        self.final_resp_status = 0


# ─── R572: Integrate direct path (5-key 首选, pexec 降为 fallback) ──────────
# 实测 integrate.api.nvidia.com/v1/chat/completions 比 pexec 快 2-3x 且无 surge,
# 但单 key 有 ~6-12/min 的 per-key RPM 限流 (冷却 1-2min). 策略:
#   5 key 独立 rr 轮换 (不与 pexec 的 _next_nv_key 共用 counter) →
#   遇 429 标该 key 冷却 (NV_INTEGRATE_KEY_COOLDOWN_S) 立即跳下一 key →
#   全限流 → 标整条 path 冷却 (NV_INTEGRATE_PATH_COOLDOWN_S) 返回 all_keys_exhausted,
#   由 execute_request 回退到 pexec tier.
# 思考参数复用 NVCF_PEXEC_MODELS[model]["inject"] (integrate 与 pexec 74f02205 触发方式一致).
_integrate_rr_counter = 0  # 模块级独立 rr, 不持久化 (重启从 0 开始, 无害)
_integrate_rr_lock = threading.Lock()
_integrate_path_cooldown_until = 0.0  # 整条 integrate path 冷却截止 (全 key 429 时触发)


def _integrate_is_path_cooling():
    return time.monotonic() < _integrate_path_cooldown_until


def _integrate_mark_path_cooling(duration_s):
    global _integrate_path_cooldown_until
    _integrate_path_cooldown_until = time.monotonic() + duration_s


def _integrate_tier_name(tier_model):
    """虚拟 tier 名, 隔离 cooldown 状态 (不与 pexec 同 model 的 cooldown 混)."""
    return f"{tier_model}_integrate"


def _try_integrate_keys(oai_body, tier_model, request_id, metrics, t_start,
                        is_stream, prior_cycle_attempts, upstream_timeout_override=None):
    """Try all 5 keys via integrate.api.nvidia.com direct path, starting from independent RR.

    镜像 _try_tier_keys 结构但走 integrate /v1/chat/completions 路径.
    - 成功 (200 非空): 返回 success
    - 429: 标该 key 冷却 (NV_INTEGRATE_KEY_COOLDOWN_S), 立即跳下一 key
    - 连接错误/timeout: 跳下一 key (不 fast-break, integrate 偶发抖动)
    - 全 key 失败: 返回 all_keys_exhausted, 由 execute_request 回退 pexec
    """
    global _integrate_rr_counter
    result = UpstreamResult()
    result.is_stream = is_stream
    result.tier_model = tier_model
    result.upstream_type = "nv_integrate"
    result.function_id = "integrate"  # func_health 不追踪 integrate (无 function id)
    key_cycle_attempts = list(prior_cycle_attempts)

    nv_model_id = NV_MODEL_IDS[tier_model]
    nvcf_config = NVCF_PEXEC_MODELS[tier_model]
    integ_tier = _integrate_tier_name(tier_model)

    # 复用 _build_pexec_body: 它做 strip_params + inject (thinking:{type:enabled} 等),
    # integrate 路径接受同样的 body 格式 (已实测 200 + rc 非空).
    integ_body = _build_pexec_body(oai_body, tier_model, nvcf_config)
    integ_data = json.dumps(integ_body).encode("utf-8")

    with _integrate_rr_lock:
        start_key_idx = _integrate_rr_counter % NVU_NUM_KEYS
        _integrate_rr_counter += 1

    _log("NV-INTEGRATE", f"Starting integrate tier={tier_model} model={nv_model_id} "
                         f"start_key=k{start_key_idx+1} path={NV_INTEGRATE_PATH}")

    CONNECT_RESERVE_S = float(os.environ.get("NVU_CONNECT_RESERVE_S", "5"))
    MIN_ATTEMPT_TIMEOUT = 5
    consecutive_pexec_timeout = 0
    PEXEC_TIMEOUT_FASTBREAK = int(os.environ.get('NVU_PEXEC_TIMEOUT_FASTBREAK', '3'))
    EMPTY_200_FASTBREAK = int(os.environ.get("NVU_EMPTY_200_FASTBREAK", "1"))

    tier_budget_start = time.time()

    for attempt_idx in range(NVU_NUM_KEYS + 2):
        key_idx = (start_key_idx + attempt_idx) % NVU_NUM_KEYS
        t_attempt_start = time.time()

        elapsed_in_tier = time.time() - tier_budget_start
        if elapsed_in_tier >= TIER_TIMEOUT_BUDGET_S:
            _log("NV-INTEGRATE-BUDGET", f"tier={tier_model} budget {TIER_TIMEOUT_BUDGET_S}s "
                                        f"exceeded after {elapsed_in_tier:.1f}s, breaking")
            break

        remaining_budget = TIER_TIMEOUT_BUDGET_S - elapsed_in_tier
        if remaining_budget < MIN_ATTEMPT_TIMEOUT:
            break
        per_attempt_timeout = max(MIN_ATTEMPT_TIMEOUT,
                                  min(upstream_timeout_override if upstream_timeout_override else UPSTREAM_TIMEOUT,
                                      remaining_budget - CONNECT_RESERVE_S))

        # 跳过冷却中的 key (per-key 429 冷却)
        if is_key_cooling(integ_tier, key_idx):
            _log("NV-INTEGRATE", f"tier={tier_model} k{key_idx+1} cooling (429), skipping")
            if attempt_idx >= NVU_NUM_KEYS and all(is_key_cooling(integ_tier, k) for k in range(NVU_NUM_KEYS)):
                _log("NV-INTEGRATE", f"tier={tier_model} all integrate keys in cooldown, breaking")
                break
            continue

        if NVU_NUM_KEYS == 0 or key_idx >= len(NVU_KEYS):
            continue

        nv_key = NVU_KEYS[key_idx]
        proxy_url = NVU_PROXY_URLS[key_idx] if key_idx < len(NVU_PROXY_URLS) else ""
        is_direct = (not proxy_url) or (proxy_url.strip() == "")

        # throttle: 第一次出站前节流 (复用全局 throttle, 分摊 per-key 压力)
        if attempt_idx == 0:
            throttle_outbound()

        _log("NV-INTEGRATE", f"tier={tier_model} attempt {attempt_idx+1}/{NVU_NUM_KEYS + 2}: "
                             f"k{key_idx+1} → integrate {nv_model_id} {'DIRECT' if is_direct else 'via ' + proxy_url}")

        # 复用 R295 header camouflage (与 pexec 一致, 风格统一)
        hdr_extra = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://build.nvidia.com",
            "Referer": "https://build.nvidia.com/explore/discover",
        }
        headers_out = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {nv_key}",
            "Content-Length": str(len(integ_data)),
            "Connection": "close",
            **hdr_extra,
        }

        try:
            t_connect_start = time.time()
            conn = _make_nvcf_proxy_conn(proxy_url, nvcf_host=NV_INTEGRATE_HOST, timeout=per_attempt_timeout)
            connect_elapsed = time.time() - t_connect_start
            post_connect_remaining = TIER_TIMEOUT_BUDGET_S - (time.time() - tier_budget_start)
            if post_connect_remaining < MIN_ATTEMPT_TIMEOUT:
                _log("NV-INTEGRATE-BUDGET", f"tier={tier_model} k{key_idx+1} after connect "
                                            f"({connect_elapsed:.1f}s) remaining {post_connect_remaining:.1f}s, aborting")
                try: conn.close()
                except Exception: pass
                break
            read_timeout = min(per_attempt_timeout, post_connect_remaining)
            conn.request("POST", NV_INTEGRATE_PATH, body=integ_data, headers=headers_out)
            if conn.sock:
                conn.sock.settimeout(read_timeout)
            resp = conn.getresponse()

            if resp.status >= 400:
                error_body = resp.read()
                try: error_json = json.loads(error_body)
                except Exception: error_json = {"error": error_body.decode("utf-8", errors="replace")}
                conn.close()
                err_str = json.dumps(error_json)

                should_cycle = resp.status in (429, 408, 500, 502)
                if should_cycle:
                    cycle_reason = ("429_integrate_rate_limit" if resp.status == 429 else
                                    "408_integrate_timeout" if resp.status == 408 else
                                    "500_integrate_error" if resp.status == 500 else "502_integrate_error")
                    key_cycle_attempts.append({
                        "tier": tier_model,
                        "nv_key_idx": key_idx,
                        "litellm_model": f"integrate_{nv_model_id}_k{key_idx+1}",
                        "error_body": err_str[:500],
                        "error_type": cycle_reason,
                        "upstream_type": "nv_integrate",
                    })
                    if resp.status == 429:
                        mark_key_cooling(integ_tier, key_idx, duration_s=NV_INTEGRATE_KEY_COOLDOWN_S)
                        _log("NV-INTEGRATE-COOLDOWN", f"tier={tier_model} k{key_idx+1} marked cooling {NV_INTEGRATE_KEY_COOLDOWN_S}s after 429")
                    _log("NV-INTEGRATE-CYCLE", f"tier={tier_model} k{key_idx+1} → {resp.status} ({cycle_reason}), cycling")
                    consecutive_pexec_timeout = 0
                    continue

                # Non-cycling error → report (与 pexec 一致)
                result.final_error_json = error_json
                result.final_resp_status = resp.status
                result.key_cycle_attempts = key_cycle_attempts
                result.elapsed_ms = int((time.time() - t_start) * 1000)
                return result

            # 200 — check empty
            is_empty = _check_empty_200(resp, key_idx, tier_model, is_stream)
            if is_empty:
                key_cycle_attempts.append({
                    "tier": tier_model,
                    "nv_key_idx": key_idx,
                    "litellm_model": f"integrate_{nv_model_id}_k{key_idx+1}",
                    "error_type": "empty_200",
                    "upstream_type": "nv_integrate",
                })
                _log("NV-INTEGRATE-EMPTY", f"tier={tier_model} k{key_idx+1} empty 200, cycling")
                if EMPTY_200_FASTBREAK > 0:
                    _log("NV-INTEGRATE-EMPTY-FASTBREAK", f"tier={tier_model} empty_200 fast-break")
                    break
                consecutive_pexec_timeout = 0
                try: conn.close()
                except Exception: pass
                continue

            # Valid success
            consecutive_pexec_timeout = 0
            result.success = True
            result.resp = resp
            result.conn = conn
            result.tier_model = tier_model
            result.nv_key_idx = key_idx
            result.nv_model_label = f"integrate_{nv_model_id}_k{key_idx+1}"
            result.key_cycle_attempts = key_cycle_attempts
            result.fallback_tiers_used = [tier_model]
            result.upstream_type = "nv_integrate"
            reset_key429_count(integ_tier, key_idx)
            metrics["upstream_type"] = "nv_integrate"
            metrics["tier_model"] = tier_model
            metrics["nv_key_idx"] = key_idx
            metrics["litellm_model"] = result.nv_model_label
            if key_cycle_attempts:
                metrics["key_cycle_429s_before_success"] = len(key_cycle_attempts)
                _log("NV-INTEGRATE-SUCCESS", f"tier={tier_model} k{key_idx+1} succeeded after "
                                              f"{len(key_cycle_attempts)} cycle attempts")
            else:
                _log("NV-INTEGRATE-SUCCESS", f"tier={tier_model} k{key_idx+1} succeeded on first attempt")
            return result

        except socket.timeout as e:
            attempt_elapsed_ms = int((time.time() - t_attempt_start) * 1000)
            _log("NV-INTEGRATE-TIMEOUT", f"tier={tier_model} k{key_idx+1} integrate timeout: "
                                          f"attempt={attempt_elapsed_ms}ms")
            key_cycle_attempts.append({
                "tier": tier_model,
                "nv_key_idx": key_idx,
                "litellm_model": f"integrate_{nv_model_id}_k{key_idx+1}",
                "error_type": "IntegrateTimeout",
                "elapsed_ms": attempt_elapsed_ms,
                "upstream_type": "nv_integrate",
            })
            consecutive_pexec_timeout += 1
            if consecutive_pexec_timeout >= PEXEC_TIMEOUT_FASTBREAK:
                _log("NV-INTEGRATE-FASTBREAK", f"tier={tier_model} {consecutive_pexec_timeout} "
                                               f"consecutive timeouts -> fast-break")
                break
            continue

        except (ConnectionRefusedError, http.client.RemoteDisconnected) as e:
            attempt_elapsed_ms = int((time.time() - t_attempt_start) * 1000)
            _log("NV-INTEGRATE-CONN", f"tier={tier_model} k{key_idx+1} connection error: {e}")
            key_cycle_attempts.append({
                "tier": tier_model,
                "nv_key_idx": key_idx,
                "litellm_model": f"integrate_{nv_model_id}_k{key_idx+1}",
                "error_type": f"Integrate{type(e).__name__}",
                "elapsed_ms": attempt_elapsed_ms,
                "upstream_type": "nv_integrate",
            })
            continue

        except Exception as e:
            error_class = type(e).__name__
            elapsed_ms = int((time.time() - t_attempt_start) * 1000)
            _log("NV-INTEGRATE-ERR", f"tier={tier_model} k{key_idx+1} {error_class}: {e}")
            is_ssl_err = (error_class == "SSLEOFError" or error_class == "SSLError" or
                          error_class == "SSLZeroReturnError")
            if is_ssl_err:
                _log("NV-INTEGRATE-SSL-CYCLE", f"tier={tier_model} k{key_idx+1} SSL error ({elapsed_ms}ms) — cycle")
                continue
            key_cycle_attempts.append({
                "tier": tier_model,
                "nv_key_idx": key_idx,
                "litellm_model": f"integrate_{nv_model_id}_k{key_idx+1}",
                "error": str(e)[:200],
                "error_type": f"Integrate{error_class}",
                "elapsed_ms": elapsed_ms,
                "upstream_type": "nv_integrate",
            })
            continue

    # ─── All integrate keys exhausted ───
    tier_attempts = [a for a in key_cycle_attempts if a.get("tier") == tier_model]
    all_429 = all(a.get("error_type") == "429_integrate_rate_limit" for a in tier_attempts) if tier_attempts else False

    result.all_keys_exhausted = True
    result.all_429 = all_429
    result.empty_200 = False
    result.key_cycle_attempts = key_cycle_attempts
    result.elapsed_ms = int((time.time() - t_start) * 1000)

    fail_summary = (f"429={sum(1 for a in tier_attempts if a.get('error_type')=='429_integrate_rate_limit')}, "
                    f"empty200={sum(1 for a in tier_attempts if a.get('error_type')=='empty_200')}, "
                    f"timeout={sum(1 for a in tier_attempts if 'Timeout' in a.get('error_type',''))}, "
                    f"other={sum(1 for a in tier_attempts if a.get('error_type') not in ('429_integrate_rate_limit','empty_200') and 'Timeout' not in a.get('error_type',''))}")
    _log("NV-INTEGRATE-FAIL", f"tier={tier_model} all integrate keys failed: {fail_summary}, "
                               f"elapsed={result.elapsed_ms}ms")

    # 全 key 429 → 标整条 integrate path 冷却, 强制走 pexec
    if all_429:
        _integrate_mark_path_cooling(NV_INTEGRATE_PATH_COOLDOWN_S)
        _log("NV-INTEGRATE-PATH-COOLDOWN", f"tier={tier_model} all integrate keys 429. "
                                            f"Marking integrate path cooling {NV_INTEGRATE_PATH_COOLDOWN_S}s")

    _log_error_detail({
        "request_id": request_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "error_subcategory": f"integrate_{tier_model}_all_keys_failed",
        "tier_model": tier_model,
        "tier_attempts": tier_attempts,
        "all_429": all_429,
        "elapsed_ms": result.elapsed_ms,
    })

    return result


def _try_tier_keys(oai_body, tier_model, request_id, metrics, t_start,
                   is_stream, prior_cycle_attempts, upstream_timeout_override=None):
    """Try all 5 keys within one tier via NVCF pexec, starting from current RR position.

    R38.12: ALL models use NVCF pexec. No LiteLLM branch.
    On 429/500/502: cycle to next key within same tier.
    On empty 200: cycle to next key within same tier.
    On other error: report immediately (no cycling).
    Connection refused fast-break: 2+ consecutive → break to next tier.
    Tier timeout budget: stop if cumulative time exceeds budget.

    Returns: UpstreamResult
    """
    result = UpstreamResult()
    result.is_stream = is_stream
    result.tier_model = tier_model
    # R_multi: 记录本次选中的 function_id, 供上层 func_health.record_result 使用
    result.function_id = ""
    key_cycle_attempts = list(prior_cycle_attempts)


    nv_model_id = NV_MODEL_IDS[tier_model]
    nvcf_config = NVCF_PEXEC_MODELS[tier_model]
    nvcf_host = NVCF_BASE_URL
    # R_multi: 从候选列表 function_ids 中按健康度选首选. surge 中的 function 自动跳过.
    _candidates = nvcf_config.get("function_ids") or [nvcf_config.get("function_id")]
    function_id = func_health.select_healthy_function(tier_model, _candidates)
    result.function_id = function_id
    nvcf_path = f"/v2/nvcf/pexec/functions/{function_id}"

    _log("NV-TIER", f"Starting tier={tier_model} model={nv_model_id} "
                    f"func={function_id[:12]}... (position from rr_counter)")

    # Build request body with per-model param stripping
    pexec_body = _build_pexec_body(oai_body, tier_model, nvcf_config)

    # Get starting key from per-tier persistent counter
    start_key_idx = _next_nv_key(tier_model)

    tier_budget_start = time.time()
    consecutive_conn_err = 0
    CONN_ERR_FAST_BREAK = 2
    # R347 (HM1-C): consecutive NVCFPexecTimeout fast-fail. After N consecutive pexec
    # timeouts in the same tier, break early instead of cycling remaining keys — saves
    # ~30-50s on doomed ATE requests. Default N=3 (per CC directive: front-3 keys all
    # NVCFPexecTimeout). Env-tunable for rollback. Rescue cases (k4/k5 save after 3+ timeouts)
    # are rare (2/231=0.87% in R347 baseline) — accepted per stability>success tradeoff eval.
    consecutive_pexec_timeout = 0
    PEXEC_TIMEOUT_FASTBREAK = int(os.environ.get('NVU_PEXEC_TIMEOUT_FASTBREAK', '3'))

    EMPTY_200_FASTBREAK = int(os.environ.get("NVU_EMPTY_200_FASTBREAK", "1"))
    for attempt_idx in range(NVU_NUM_KEYS + 2):
        key_idx = (start_key_idx + attempt_idx) % NVU_NUM_KEYS
        t_attempt_start = time.time()  # R38.14: per-attempt start time for accurate logging

        # Tier timeout budget check (before each attempt)
        elapsed_in_tier = time.time() - tier_budget_start
        if elapsed_in_tier >= TIER_TIMEOUT_BUDGET_S:
            _log("NV-TIER-BUDGET", f"tier={tier_model} budget {TIER_TIMEOUT_BUDGET_S}s "
                                    f"exceeded after {elapsed_in_tier:.1f}s, breaking")
            break

        # R38.14: per-attempt timeout respects remaining budget
        # R40 A2: reserve CONNECT_RESERVE_S for SOCKS5 connect+SSL handshake (2-5s observed).
        #   Pre-R40 bug: per_attempt_timeout = min(45, remaining) ignored connect time, so
        #   attempt 1 spent 45s(read)+3s(connect)=48s but budget thought only 45s elapsed;
        #   attempt 2 then got remaining=15s, spent 3s(connect)+15s(read)=18s → total 66s,
        #   ~74s with throttle/overhead, blowing past the 60s budget and showing as 74.2s
        #   in the 502 error. Reserve keeps the read timeout within true remaining budget.
        CONNECT_RESERVE_S = float(os.environ.get("NVU_CONNECT_RESERVE_S", "5"))
        remaining_budget = TIER_TIMEOUT_BUDGET_S - elapsed_in_tier
        MIN_ATTEMPT_TIMEOUT = 5  # R45: 10→5 — 10s 下限在 budget 被前次 timeout 吃掉后误杀后续 key (NVCF 实测 p50=3s); 5s 仍保留 dooming-attempt 保护 # Don't attempt if less than 10s budget remains (doomed attempt)
        if remaining_budget < MIN_ATTEMPT_TIMEOUT:
            _log("NV-TIER-BUDGET", f"tier={tier_model} budget {TIER_TIMEOUT_BUDGET_S}s "
                                    f"remaining {remaining_budget:.1f}s < {MIN_ATTEMPT_TIMEOUT}s minimum, breaking")
            break
        # Read timeout = min(UPSTREAM_TIMEOUT, remaining - CONNECT_RESERVE) so connect+read together stay in budget
        per_attempt_timeout = max(MIN_ATTEMPT_TIMEOUT,
                                  min(upstream_timeout_override if upstream_timeout_override else UPSTREAM_TIMEOUT, remaining_budget - CONNECT_RESERVE_S))

        # Skip keys in 429 cooldown
        if is_key_cooling(tier_model, key_idx):
            _log("NV-KEY", f"tier={tier_model} k{key_idx+1} is in cooldown (429), skipping")
            if attempt_idx >= NVU_NUM_KEYS and all(is_key_cooling(tier_model, k) for k in range(NVU_NUM_KEYS)):
                _log("NV-TIER", f"tier={tier_model} all keys in cooldown, breaking")
                break
            continue

        # ─── NVCF pexec request ───
        if NVU_NUM_KEYS == 0 or key_idx >= len(NVU_KEYS):
            _log("NV-PEXEC-ERR", f"tier={tier_model} k{key_idx+1} no NV key/proxy configured")
            key_cycle_attempts.append({
                "tier": tier_model,
                "nv_key_idx": key_idx,
                "error_type": "nvcf_pexec_no_key",
                "upstream_type": "nvcf_pexec",
            })
            continue

        nv_key = NVU_KEYS[key_idx]
        # ─ Rproxy: per-key proxy strategy driven by NVU_PROXY_URL<n> env ─
        # empty proxy_url → DIRECT (k2/k4 on HM1); non-empty → mihomo SOCKS5 (k1/k3/k5).
        # _make_nvcf_proxy_conn handles the empty→direct branch internally.
        proxy_url = NVU_PROXY_URLS[key_idx] if key_idx < len(NVU_PROXY_URLS) else ""
        is_direct = (not proxy_url) or (proxy_url.strip() == "")

        # Build per-attempt request (model field already set in pexec_body)
        pexec_data = json.dumps(pexec_body).encode("utf-8")

        _log("NV-KEY", f"tier={tier_model} attempt {attempt_idx+1}/{NVU_NUM_KEYS + 2}: "
                       f"k{key_idx+1} → NVCF pexec {function_id[:12]}... {'DIRECT' if is_direct else 'via ' + proxy_url}")

        # R295-port (HM1 self-change, authorized): HTTP header camouflage for NVCF
        # fingerprint bypass. Ported from HM2 R295. HM2 applies it to key_idx in (0,4)
        # (k1/k5, which are the mihomo-proxied keys on HM2). On HM1 the user elected to
        # apply camouflage to ALL keys (k1-k5) for maximum disguise — so this is
        # unconditional, no key_idx guard. Mirrors HM2's exact 6 headers:
        # User-Agent (browser), Origin/Referer (build.nvidia.com source),
        # X-Requested-With, Accept-Language, Accept.
        hdr_extra = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://build.nvidia.com",
            "Referer": "https://build.nvidia.com/explore/discover",
        }
        headers_out = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {nv_key}",
            "Content-Length": str(len(pexec_data)),
            "Connection": "close",
            **hdr_extra,
        }

        try:
            # Throttle before making connection (SOCKS5 connect is a real outbound)
            if attempt_idx == 0:
                throttle_outbound()
            t_connect_start = time.time()
            # Rproxy: _make_nvcf_proxy_conn routes DIRECT when proxy_url empty, else mihomo.
            conn = _make_nvcf_proxy_conn(proxy_url, nvcf_host=nvcf_host, timeout=per_attempt_timeout)
            connect_elapsed = time.time() - t_connect_start
            # R40 A2: re-check budget AFTER connect — connect time wasn't counted when
            # computing per_attempt_timeout above, so a slow connect may have eaten the budget.
            post_connect_remaining = TIER_TIMEOUT_BUDGET_S - (time.time() - tier_budget_start)
            if post_connect_remaining < MIN_ATTEMPT_TIMEOUT:
                _log("NV-TIER-BUDGET", f"tier={tier_model} k{key_idx+1} after connect "
                                        f"({connect_elapsed:.1f}s) remaining {post_connect_remaining:.1f}s "
                                        f"< {MIN_ATTEMPT_TIMEOUT}s, aborting attempt")
                try:
                    conn.close()
                except Exception:
                    pass
                key_cycle_attempts.append({
                    "tier": tier_model,
                    "nv_key_idx": key_idx,
                    "litellm_model": f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}",
                    "error_type": "budget_exhausted_after_connect",
                    "elapsed_ms": int(connect_elapsed * 1000),
                    "upstream_type": "nvcf_pexec",
                })
                break
            # Read timeout = whatever remains in the budget, capped by per_attempt_timeout
            read_timeout = min(per_attempt_timeout, post_connect_remaining)
            conn.request("POST", nvcf_path, body=pexec_data, headers=headers_out)
            # R38.6 CRITICAL FIX: sock.settimeout() BEFORE getresponse()
            # R40 A2: use read_timeout (post-connect remaining) instead of per_attempt_timeout
            if conn.sock:
                conn.sock.settimeout(read_timeout)
            resp = conn.getresponse()

            if resp.status >= 400:
                error_body = resp.read()
                try:
                    error_json = json.loads(error_body)
                except Exception:
                    error_json = {"error": error_body.decode("utf-8", errors="replace")}
                conn.close()
                err_str = json.dumps(error_json)

                consecutive_conn_err = 0

                should_cycle = resp.status in (429, 408, 500, 502)
                if should_cycle:
                    cycle_reason = "429_nv_rate_limit" if resp.status == 429 else \
                                   "408_nvcf_timeout" if resp.status == 408 else \
                                   "500_nv_error" if resp.status == 500 else "502_nv_error"
                    key_cycle_attempts.append({
                        "tier": tier_model,
                        "nv_key_idx": key_idx,
                        "litellm_model": f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}",
                        "error_body": err_str[:500],
                        "error_type": cycle_reason,
                        "upstream_type": "nvcf_pexec",
                    })
                    if resp.status == 429:
                        mark_key_cooling(tier_model, key_idx)
                        _log("NV-COOLDOWN", f"tier={tier_model} k{key_idx+1} marked cooling after 429")
                    _log("NV-CYCLE", f"tier={tier_model} k{key_idx+1} \u2192 "
                                     f"{resp.status} ({cycle_reason}), cycling to next key")
                    consecutive_pexec_timeout = 0  # R347: reset (429/500/502 != timeout)
                    continue

                # Non-cycling error → report
                result.final_error_json = error_json
                result.final_resp_status = resp.status
                result.key_cycle_attempts = key_cycle_attempts
                result.elapsed_ms = int((time.time() - t_start) * 1000)
                return result

            # ─── 200 response — check for empty ───
            is_empty = _check_empty_200(resp, key_idx, tier_model, is_stream)

            if is_empty:
                key_cycle_attempts.append({
                    "tier": tier_model,
                    "nv_key_idx": key_idx,
                    "litellm_model": f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}",
                    "error_type": "empty_200",
                    "upstream_type": "nvcf_pexec",
                })
                _log("NV-EMPTY-CYCLE", f"tier={tier_model} k{key_idx+1} empty 200, cycling")
                if EMPTY_200_FASTBREAK > 0:
                    _log("NV-EMPTY-FASTBREAK", f"tier={tier_model} empty_200 fast-break (saved remaining keys)")
                    break
                consecutive_pexec_timeout = 0  # R347: reset (empty_200 != timeout)
                try:
                    conn.close()
                except Exception:
                    pass
                continue

            # ─── Valid success response ───
            consecutive_conn_err = 0
            consecutive_pexec_timeout = 0  # R347: reset on success
            result.success = True
            result.resp = resp
            result.conn = conn
            result.tier_model = tier_model
            result.nv_key_idx = key_idx
            result.nv_model_label = f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}"
            result.key_cycle_attempts = key_cycle_attempts
            result.fallback_tiers_used = [tier_model]
            result.upstream_type = "nvcf_pexec"
            reset_key429_count(tier_model, key_idx)
            metrics["upstream_type"] = "nvcf_pexec"
            metrics["tier_model"] = tier_model
            metrics["nv_key_idx"] = key_idx
            metrics["litellm_model"] = result.nv_model_label
            if key_cycle_attempts:
                metrics["key_cycle_429s_before_success"] = len(key_cycle_attempts)
                metrics["key_cycle_details"] = key_cycle_attempts
                _log("NV-SUCCESS", f"tier={tier_model} k{key_idx+1} succeeded after "
                                    f"{len(key_cycle_attempts)} cycle attempts")
            else:
                _log("NV-SUCCESS", f"tier={tier_model} k{key_idx+1} succeeded on first attempt")
            return result

        except socket.timeout as e:
            # R38.14: use per-attempt elapsed, not request-level t_start
            attempt_elapsed_ms = int((time.time() - t_attempt_start) * 1000)
            total_elapsed_ms = int((time.time() - t_start) * 1000)
            _log("NV-TIMEOUT", f"tier={tier_model} k{key_idx+1} NVCF pexec timeout: "
                               f"attempt={attempt_elapsed_ms}ms total={total_elapsed_ms}ms")
            key_cycle_attempts.append({
                "tier": tier_model,
                "nv_key_idx": key_idx,
                "litellm_model": f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}",
                "error_type": "NVCFPexecTimeout",
                "elapsed_ms": attempt_elapsed_ms,  # R38.14: per-attempt elapsed, not total
                "upstream_type": "nvcf_pexec",
            })
            consecutive_pexec_timeout += 1  # R347 (HM1-C): track consecutive pexec timeouts
            if consecutive_pexec_timeout >= PEXEC_TIMEOUT_FASTBREAK:
                _log("NV-PEXEC-FASTBREAK", f"tier={tier_model} {consecutive_pexec_timeout} consecutive "
                                          f"NVCFPexecTimeout -> fast-break (saved remaining keys)")
                break
            continue

        except (ConnectionRefusedError, http.client.RemoteDisconnected) as e:
            attempt_elapsed_ms = int((time.time() - t_attempt_start) * 1000)  # R38.14
            _log("NV-CONN", f"tier={tier_model} k{key_idx+1} connection error: {e}")
            consecutive_conn_err += 1
            key_cycle_attempts.append({
                "tier": tier_model,
                "nv_key_idx": key_idx,
                "litellm_model": f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}",
                "error_type": f"NVCFPexec{type(e).__name__}",
                "elapsed_ms": attempt_elapsed_ms,
                "upstream_type": "nvcf_pexec",
            })
            if consecutive_conn_err >= CONN_ERR_FAST_BREAK:
                _log("NV-CONN-BREAK", f"tier={tier_model} {consecutive_conn_err} consecutive "
                                       f"connection errors → fast-break")
                break
            continue

        except Exception as e:
            error_class = type(e).__name__
            elapsed_ms = int((time.time() - t_attempt_start) * 1000)  # R38.14: per-attempt
            _log("NV-ERR", f"tier={tier_model} k{key_idx+1} {error_class}: {e}")

            # R1: SSLEOFError/SSLError/SSLZeroReturnError — mihomo/NVCF SSL hiccup (read-stage EOF
            # after NVCF侧 reset, 已观测单次吃 31s budget).
            # F-fix (2026-07-01, cc2 三轮仲裁): 不重试同 key, 直接 cycle 下一 key.
            #   原逻辑 sleep 3s + continue (注释"retry SAME key"实为下一 key, 注释错误).
            #   sleep 3s 纯浪费 tier budget; 同 mihomo 出口(k3/k4 都走 7896)持续 SSL error,
            #   重试同出口必败还倒贴 sleep. 切 DIRECT key(k2/k5)可能秒成功, 既省 sleep 又换出口.
            #   把 budget 留给后续 key, 也顺带给单 tier 内更多 key 重试机会.
            is_ssl_err = (error_class == "SSLEOFError" or error_class == "SSLError" or
                         error_class == "SSLZeroReturnError")
            if is_ssl_err:
                _log("NV-SSL-CYCLE", f"tier={tier_model} k{key_idx+1} SSL error ({elapsed_ms}ms) — "
                                     f"cycle to next key (no same-key retry, F-fix saves budget)")
                continue  # cycle to next key — 不 sleep, 不重试同 key

            if "gaierror" in error_class.lower() or "socket" in error_class.lower():
                consecutive_conn_err += 1
                if consecutive_conn_err >= CONN_ERR_FAST_BREAK:
                    _log("NV-CONN-BREAK", f"tier={tier_model} {consecutive_conn_err} consecutive "
                                           f"DNS/socket errors → fast-break")
                    key_cycle_attempts.append({
                        "tier": tier_model,
                        "nv_key_idx": key_idx,
                        "litellm_model": f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}",
                        "error": str(e)[:200],
                        "error_type": f"NVCFPexec{error_class}",
                        "elapsed_ms": elapsed_ms,
                        "upstream_type": "nvcf_pexec",
                    })
                    break
            key_cycle_attempts.append({
                "tier": tier_model,
                "nv_key_idx": key_idx,
                "litellm_model": f"nvcf_{NV_MODEL_IDS[tier_model]}_k{key_idx+1}",
                "error": str(e)[:200],
                "error_type": f"NVCFPexec{error_class}",
                "elapsed_ms": elapsed_ms,
                "upstream_type": "nvcf_pexec",
            })
            continue

    # ─── All keys in this tier exhausted ───
    tier_attempts = [a for a in key_cycle_attempts if a.get("tier") == tier_model]
    all_429 = all(a.get("error_type") == "429_nv_rate_limit" for a in tier_attempts)
    all_empty = all(a.get("error_type") == "empty_200" for a in tier_attempts)

    result.all_keys_exhausted = True
    result.all_429 = all_429
    result.empty_200 = all_empty
    result.key_cycle_attempts = key_cycle_attempts
    result.elapsed_ms = int((time.time() - t_start) * 1000)

    fail_summary = f"429={sum(1 for a in tier_attempts if a.get('error_type')=='429_nv_rate_limit')}, " \
                   f"empty200={sum(1 for a in tier_attempts if a.get('error_type')=='empty_200')}, " \
                   f"timeout={sum(1 for a in tier_attempts if 'Timeout' in a.get('error_type',''))}, " \
                   f"other={sum(1 for a in tier_attempts if a.get('error_type') not in ('429_nv_rate_limit','empty_200') and 'Timeout' not in a.get('error_type',''))}"
    _log("NV-TIER-FAIL", f"tier={tier_model} all {NVU_NUM_KEYS} keys failed: {fail_summary}, "
                          f"elapsed={result.elapsed_ms}ms")

    if all_429:
        for k in range(NVU_NUM_KEYS):
            mark_key_cooling(tier_model, k, duration_s=int(TIER_COOLDOWN_S))
        _log("NV-GLOBAL-COOLDOWN", f"tier={tier_model} all keys 429. Marking all cooling {TIER_COOLDOWN_S:.0f}s (TIER_COOLDOWN)")

    _log_error_detail({
        "request_id": request_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "error_subcategory": f"tier_{tier_model}_all_keys_failed",
        "tier_model": tier_model,
        "tier_attempts": tier_attempts,
        "all_429": all_429,
        "all_empty_200": all_empty,
        "elapsed_ms": result.elapsed_ms,
    })

    return result


def execute_request(handler, oai_body, mapped_model, request_id, metrics, t_start, upstream_timeout_override=None):
    """Execute NVCF pexec request with three-tier fallback (R38.12, R40 ring fallback).

    ALL models use NVCF pexec direct path. No LiteLLM routing.
    - mapped_model determines starting tier (default: dsv4p_nv)
    - R40 CRITICAL FIX: ring fallback — tier_order = TIERS[start:] + TIERS[:start]
      This guarantees ANY tier (including the last) has 2 fallback tiers.
      Pre-R40 bug: TIERS[start_idx:] slice — when start_tier was the LAST tier
      (e.g. glm5.1 in R38.9 order [..., glm5.1]), the slice had only 1 element,
      so a failure at that tier returned 502 with NO fallback attempted.
      Symptom: "Tiers tried: [dsv4p_nv: 2×mixed]" 74.2s, agent stuck.
    - Each tier tries 5 keys with per-tier persistent RR counter
    - On tier all-fail: fallback to next tier in ring order (wraps around)
    - All tiers fail: ABORT-NO-FALLBACK
    - R38.8: If all tiers fail with ONLY connection errors, wait 5s and retry once.
    """
    start_tier_idx = get_tier_index(mapped_model)
    is_stream = oai_body.get("stream", False)

    # R551/R_multi: 动态 surge fallback. tier_order = [mapped_model] + 健康度达标的备选.
    # 跨 model fallback 由 FALLBACK_GRAPH 白名单控制 (默认空=R503行为, 不跨 model).
    # 健康度检查 per-function: 检查 alt model 的首选 function 是否健康.
    tier_order = [mapped_model]
    for alt in FALLBACK_GRAPH.get(mapped_model, []):
        alt_cfg = NVCF_PEXEC_MODELS.get(alt, {})
        alt_cands = alt_cfg.get("function_ids") or [alt_cfg.get("function_id")]
        alt_primary = alt_cands[0] if alt_cands else None
        if alt_primary and func_health.is_healthy(alt_primary):
            tier_order.append(alt)

    if len(tier_order) > 1:
        _log("NV-REQ", f"mapped_model={mapped_model} start_tier={mapped_model} "
                       f"stream={is_stream} tier_chain={tier_order} "
                       f"(dynamic fallback, health={func_health.snapshot()})")
    else:
        _log("NV-REQ", f"mapped_model={mapped_model} start_tier={mapped_model} "
                       f"stream={is_stream} tier_chain={tier_order} (no fallback, 3model)")

    for retry_idx in range(2):
        all_attempts = []
        all_tier_summaries = []
        fallback_tiers_used = []

        for tier_idx, tier_model in enumerate(tier_order):
            is_first_tier = (tier_idx == 0)
            prev_tier = tier_order[tier_idx - 1] if not is_first_tier else None

            # Skip tier if all keys in cooldown
            all_cooling = all(is_key_cooling(tier_model, k) for k in range(NVU_NUM_KEYS))
            if all_cooling:
                _log("NV-TIER-SKIP", f"tier={tier_model} all keys in cooldown, skipping")
                # R40 A3: cooldown is neither 429 nor empty-200 — don't misclassify.
                all_tier_summaries.append({
                    "tier": tier_model,
                    "all_429": False,
                    "all_empty_200": False,
                    "all_cooldown": True,
                    "num_attempts": 0,
                    "elapsed_ms": 0,
                    "skipped": True,
                })
                if not is_first_tier:
                    _log("NV-FALLBACK", f"Tier {prev_tier} all-failed → "
                                        f"falling back to {tier_model} (skipped, cooldown)")
                continue

            if not is_first_tier:
                _log("NV-FALLBACK", f"Tier {prev_tier} all-failed → "
                                    f"falling back to {tier_model}")

            # R572: 首选 integrate 直连路径 (仅 first tier + NV_INTEGRATE_MODELS + path 未冷却).
            # integrate 全 key 失败/全 429 → 回退下方 pexec _try_tier_keys (同一 tier_model).
            if (is_first_tier and NV_INTEGRATE_ENABLED and tier_model in NV_INTEGRATE_MODELS
                    and not _integrate_is_path_cooling()):
                integ_result = _try_integrate_keys(oai_body, tier_model, request_id, metrics, t_start,
                                                    is_stream, all_attempts, upstream_timeout_override)
                if integ_result.success and not integ_result.empty_200:
                    integ_result.fallback_tiers_used = [tier_model]
                    metrics["tier_model"] = integ_result.tier_model
                    metrics["fallback_tiers_used"] = integ_result.fallback_tiers_used
                    if retry_idx > 0:
                        _log("NV-STARTUP-RETRY-SUCCESS", f"Startup retry #{retry_idx} succeeded (integrate)")
                        metrics["startup_retry"] = retry_idx
                    # integrate 无 function_id, 不记 func_health (它只追踪 pexec function).
                    return integ_result
                # integrate 失败 → 累积 attempts, 落到 pexec _try_tier_keys 重试同一 model.
                _log("NV-INTEGRATE-FALLBACK", f"tier={tier_model} integrate all-failed → "
                                               f"falling back to pexec same model")
                all_attempts = list(integ_result.key_cycle_attempts)
                all_tier_summaries.append({
                    "tier": tier_model,
                    "path": "nv_integrate",
                    "all_429": integ_result.all_429,
                    "all_empty_200": integ_result.empty_200,
                    "num_attempts": len([a for a in integ_result.key_cycle_attempts
                                         if a.get("tier") == tier_model]),
                    "elapsed_ms": integ_result.elapsed_ms,
                    "fell_back_to_pexec": True,
                })

            tier_result = _try_tier_keys(oai_body, tier_model, request_id, metrics, t_start,
                                         is_stream, all_attempts, upstream_timeout_override)

            if tier_result.success and not tier_result.empty_200:
                tier_result.fallback_tiers_used = tier_order[:tier_idx + 1]
                if not is_first_tier:
                    _log("NV-FALLBACK-SUCCESS", f"Success on fallback tier {tier_model} "
                                                f"after primary {tier_order[0]} failed")
                    metrics["fallback_from"] = prev_tier
                    metrics["fallback_to"] = tier_model
                metrics["tier_model"] = tier_result.tier_model
                metrics["fallback_tiers_used"] = tier_result.fallback_tiers_used
                if retry_idx > 0:
                    _log("NV-STARTUP-RETRY-SUCCESS", f"Startup retry #{retry_idx} succeeded")
                    metrics["startup_retry"] = retry_idx
                # R_multi: 按本次选中的 function_id 记录健康度 (不是按 model)
                func_health.record_result(tier_result.function_id, True)
                return tier_result

            # Tier all-failed: record and try next
            # R40 A4: simplified — single condition, no `or a not in all_attempts` dead code.
            tier_attempts = [a for a in tier_result.key_cycle_attempts
                             if a.get("tier") == tier_model]
            # R_multi: 按本次选中的 function_id 记录失败. all_keys_exhausted=该function本轮surge.
            func_health.record_result(tier_result.function_id, False)
            all_tier_summaries.append({
                "tier": tier_model,
                "all_429": tier_result.all_429,
                "all_empty_200": tier_result.empty_200,
                "all_cooldown": False,
                "num_attempts": len(tier_attempts),
                "elapsed_ms": tier_result.elapsed_ms,
            })
            all_attempts = list(tier_result.key_cycle_attempts)

            if tier_result.conn:
                try:
                    tier_result.conn.close()
                except Exception:
                    pass

        # ─── All tiers exhausted ───
        _log("NV-ALL-TIERS-FAIL", f"All {len(tier_order)} tiers failed "
                                   f"(ring tiers tried: {tier_order}), "
                                   f"elapsed={int((time.time() - t_start) * 1000)}ms, ABORT-NO-FALLBACK")

        has_429 = any(s.get("all_429") for s in all_tier_summaries)
        has_empty = any(s.get("all_empty_200") for s in all_tier_summaries)

        # Check if ALL failures were connection errors only
        all_conn_err = not has_429 and not has_empty and all(
            ("Conn" in a.get("error_type", "") or "gai" in a.get("error_type", "").lower() or
             "socket" in a.get("error_type", "").lower())
            for a in all_attempts
        ) and len(all_attempts) > 0

        if all_conn_err and retry_idx == 0:
            _log("NV-STARTUP-RETRY", f"All tiers failed with only connection errors. Waiting 5s...")
            time.sleep(5)
            continue

        break

    # Build final result
    has_429 = any(s.get("all_429") for s in all_tier_summaries)
    has_empty = any(s.get("all_empty_200") for s in all_tier_summaries)

    final_result = UpstreamResult()
    final_result.success = False
    final_result.all_keys_exhausted = True
    final_result.all_429 = has_429 and not has_empty
    final_result.empty_200 = has_empty
    final_result.key_cycle_attempts = all_attempts
    final_result.tier_attempts = all_tier_summaries
    final_result.fallback_tiers_used = tier_order
    final_result.elapsed_ms = int((time.time() - t_start) * 1000)
    final_result.final_resp_status = 429 if has_429 else 502

    _log_error_detail({
        "request_id": request_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "error_subcategory": "all_tiers_failed",
        "start_tier": tier_order[0],
        "tiers_tried": tier_order,
        "tier_summaries": all_tier_summaries,
        "total_attempts": len(all_attempts),
        "elapsed_ms": final_result.elapsed_ms,
        "startup_retry_attempted": retry_idx > 0,
    })

    # R41: Do NOT call _log_metrics() here. The metrics dict passed into this
    # function (from handlers._handle_openai_nv) is written by handlers.py in
    # the `all_keys_exhausted` branch (handlers.py ~L142) with full DB-compatible
    # fields (request_id, timestamp, duration_ms, status, fallback_tiers_used...).
    # A second _log_metrics here previously emitted a *sparse* dict (only
    # request_id/error_subcategory/start_tier/tiers_tried/elapsed_ms) missing the
    # NOT NULL `ts`/`timestamp` and the `duration_ms`/`fallback_tiers_used` keys
    # that db._build_request_row reads. One sparse dict in a flush batch made the
    # whole batch INSERT fail and rollback → hermes_logs.nv_requests stayed empty
    # (~96 rows on 06-24, only 6 landed). error_detail file above is unaffected.
    # Removing this duplicate restores DB persistence without losing event signal.

    return final_result
