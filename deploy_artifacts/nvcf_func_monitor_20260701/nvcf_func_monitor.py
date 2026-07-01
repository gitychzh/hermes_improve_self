#!/usr/bin/env python3
"""
NVCF function 健康监控 (2026-07-01)

目的: 自动检测 hm40006 当前使用的 NVCF function 是否进入衰退/下架状态,
      并在故障前预警 + 推荐替代 function。

机制 (见 memory: nvcf-function-lifecycle-mechanism-2026-07-01):
  - NVCF function 4 状态管线: ACTIVE → DEGRADING → DEGRADED → INACTIVE
  - INACTIVE = 404 (秒级失败); DEGRADING = 45s 挂死超时
  - NVCF 持续轮换推理引擎后端 (orion/dynamo/sglang/ai-...), 旧版本随时下架
  - status 是唯一可信可用性信号

调度: systemd timer nvcf_func_monitor.timer (每 10min)
日志: /home/opc_uname/hm_ps/hermes_improve_self/logs/nvcf_func_monitor.log

退出码:
  0 = 当前 function ACTIVE, 一切正常
  1 = 当前 function DEGRADING (衰退中, 即将下架, 应尽快切)
  2 = 当前 function INACTIVE/DEGRADED (已下架, 必须立即切)
  3 = 无法判断 (查询失败, 不告警)
"""
import json
import os
import subprocess
import sys
import time
import urllib3
from datetime import datetime

urllib3.disable_warnings()

REPO = "/home/opc_uname/hm_ps/hermes_improve_self"
LOG_FILE = f"{REPO}/logs/nvcf_func_monitor.log"
NVCF_BASE = "https://api.nvcf.nvidia.com/v2/nvcf/functions"
# 关注的 model 名称前缀 (deepseek-v4 + kimi, 即 hm40006 可能用的后端)
WATCH_PREFIXES = ("deepseek-v4", "kimi")
# 思考链实测时用的 model 字段候选 (按 function name 匹配)
MODEL_FIELD_CANDIDATES = {
    "sglang": "deepseek-ai/deepseek-v4-pro",
    "dynamo": "deepseek-ai/deepseek-v4-pro",
    "orion": "deepseek-ai/deepseek-v4-pro",
    "ai-deepseek": "deepseek-ai/deepseek-v4-pro",
    "nvquery-kimi": "moonshotai/kimi-k2.6",
    "ai-kimi": "moonshotai/kimi-k2.6",
}


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    # systemd service 的 StandardOutput 会把 print 落盘到 log;
    # 仅在非 systemd 环境下手动写文件 (避免重复)
    if not os.environ.get("INVOCATION_ID"):  # systemd 会设 INVOCATION_ID
        try:
            with open(LOG_FILE, "a") as f:
                f.write(line + "\n")
        except Exception:
            pass


def get_hm40006_env(var):
    """从 hm40006 容器读 env (避免在宿主机暴露 keys)"""
    r = subprocess.run(
        ["docker", "exec", "hm40006", "python3", "-c",
         f"from gateway.config import {var}; print({var})"],
        capture_output=True, text=True, timeout=15
    )
    return r.stdout.strip() if r.returncode == 0 else None


def get_keys_and_current():
    """拿 keys + 当前 function_id + model id 映射"""
    r = subprocess.run(
        ["docker", "exec", "hm40006", "python3", "-c",
         "import os, json; from gateway.config import HM_NV_KEYS, NV_MODEL_IDS, NVCF_PEXEC_MODELS; "
         "fid = os.environ.get('NVCF_DEEPSEEK_FUNCTION_ID') or NVCF_PEXEC_MODELS['dsv4p_nv'].get('function_id',''); "
         "print(json.dumps({'keys': HM_NV_KEYS, 'fid': fid, 'model_ids': NV_MODEL_IDS}))"],
        capture_output=True, text=True, timeout=15
    )
    if r.returncode != 0:
        return None
    # stdout 可能混了 [HM-RR] stderr 输出, 取最后一行 json
    for line in reversed(r.stdout.strip().split("\n")):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:
                pass
    return None


def fetch_all_functions(key):
    """GET /v2/nvcf/functions 全量"""
    http = urllib3.PoolManager(timeout=30)
    r = http.request("GET", NVCF_BASE,
                     headers={"Authorization": f"Bearer {key}"}, retries=False)
    if r.status != 200:
        log(f"ERROR: NVCF list API HTTP {r.status}: {r.data[:200]}")
        return None
    return json.loads(r.data).get("functions", [])


def find_function(funcs, fid):
    for f in funcs:
        if f.get("id") == fid:
            return f
    return None


def recommend_alternatives(funcs, current_f):
    """找替代: 只按 WATCH_PREFIXES (deepseek-v4/kimi) 的 ACTIVE 候选.
    注意: ncaId 是 NVCF 平台级共享部署资源 ID, 同一 ownedByDifferentAccount=true 的
    所有 function (含不相关 ai-riva/ai-gemma 等) 都共享同一 ncaId, 不能作筛选器.
    真正的引擎区分靠 name 前缀 (dynamo/orion/sglang/nvquery-kimi/ai-kimi/ai-deepseek).
    """
    cands = [f for f in funcs if f.get("status") == "ACTIVE"
             and any(p in f.get("name", "").lower() for p in WATCH_PREFIXES)
             and (not current_f or f.get("id") != current_f.get("id"))]

    # 若 current_f 是 watched prefix 之一, 优先放同引擎前缀 (同 name 第一段) 的到前面
    if current_f:
        cur_prefix = current_f.get("name", "").split("-")[0]
        cands.sort(key=lambda f: 0 if f.get("name", "").startswith(cur_prefix) else 1)
    return cands


def probe_reasoning(key, fid, func_name):
    """实测 function 是否 emit 非空 reasoning_content"""
    # 按 name 选 model 字段
    model_field = "deepseek-ai/deepseek-v4-pro"
    for prefix, mf in MODEL_FIELD_CANDIDATES.items():
        if prefix in func_name.lower():
            model_field = mf
            break
    body = json.dumps({
        "model": model_field,
        "messages": [{"role": "user", "content": "What is 2+2? think step by step."}],
        "max_tokens": 150, "stream": False,
        "thinking": {"type": "enabled"}, "reasoning_effort": "high"
    }).encode()
    http = urllib3.PoolManager(timeout=45)
    try:
        r = http.request("POST",
                         f"https://api.nvcf.nvidia.com/v2/nvcf/pexec/functions/{fid}",
                         headers={"Authorization": f"Bearer {key}",
                                  "Content-Type": "application/json"},
                         body=body, retries=False)
        if r.status != 200:
            return {"http": r.status, "ok": False, "rc_len": 0,
                    "detail": r.data.decode()[:120]}
        d = json.loads(r.data)
        msg = d.get("choices", [{}])[0].get("message", {})
        rc = msg.get("reasoning_content", "") or ""
        return {"http": 200, "ok": True, "rc_len": len(rc),
                "has_reasoning": bool(rc), "model_field": model_field}
    except Exception as e:
        return {"http": 0, "ok": False, "rc_len": 0,
                "detail": f"{type(e).__name__}: {str(e)[:80]}"}


def main():
    log("=== NVCF function 健康检查开始 ===")
    info = get_keys_and_current()
    if not info:
        log("ERROR: 无法从 hm40006 读取 keys/function_id (容器异常?)")
        return 3

    keys = info["keys"]
    cur_fid = info["fid"]
    model_ids = info["model_ids"]
    log(f"当前 function_id: {cur_fid}")
    log(f"当前 NV_MODEL_IDS: {model_ids}")

    funcs = fetch_all_functions(keys[0])
    if funcs is None:
        return 3
    log(f"NVCF 账号共 {len(funcs)} 个 functions")

    cur_f = find_function(funcs, cur_fid)
    if not cur_f:
        log(f"⚠️ 当前 function_id {cur_fid} 不在账号列表中 → 已下架 (INACTIVE/删除)")
        cur_status = "MISSING"
    else:
        cur_status = cur_f.get("status", "?")
        log(f"当前 function: name={cur_f.get('name')} status={cur_status} "
            f"created={cur_f.get('createdAt','')[:10]} ncaId={cur_f.get('ncaId','')[:12]}")

    # 状态判定
    if cur_status == "ACTIVE":
        log("✅ 当前 function ACTIVE, 正常")
        # 顺带扫一眼 watched prefix 里有没有新的 ACTIVE (信息性, 不告警)
        watched_active = [f for f in funcs if f.get("status") == "ACTIVE"
                          and any(p in f.get("name", "").lower() for p in WATCH_PREFIXES)
                          and f.get("id") != cur_fid]
        log(f"   (信息) watched-prefix ACTIVE 候选 {len(watched_active)} 个:")
        for f in watched_active[:5]:
            log(f"      {f.get('name'):35s} {f['id'][:8]}  created={f.get('createdAt','')[:10]}")
        return 0

    if cur_status in ("DEGRADING", "DEGRADED"):
        level = "DEGRADED" if cur_status == "DEGRADED" else "DEGRADING"
        log(f"🚨 当前 function {cur_status} — {'已下架' if level=='DEGRADED' else '衰退中, 即将下架'}!")
    elif cur_status == "MISSING":
        log(f"🚨 当前 function 已从列表消失 — 必须立即切换!")
    elif cur_status == "INACTIVE":
        log(f"🚨 当前 function INACTIVE (404) — 必须立即切换!")
    else:
        log(f"⚠️ 未知 status: {cur_status}")

    # 找替代
    cands = recommend_alternatives(funcs, cur_f)
    if not cands:
        log("❌ 未找到任何 ACTIVE 替代 function — 需人工介入 (可能 NVCF 全面故障)")
        return 2

    log(f"\n=== 替代候选 ({len(cands)} 个 ACTIVE) ===")
    # 实测 top 3 候选的 reasoning_content
    probed = []
    for f in cands[:3]:
        name = f.get("name", "")
        fid = f["id"]
        log(f"  探针: {name} ({fid[:8]}) ...")
        result = probe_reasoning(keys[0], fid, name)
        log(f"    → HTTP {result['http']} ok={result.get('ok')} "
            f"rc_len={result.get('rc_len', 0)} model={result.get('model_field','?')} "
            f"detail={result.get('detail','')}")
        if result.get("has_reasoning"):
            probed.append((f, result))
            log(f"    ✅ 支持 reasoning_content!")

    log("\n=== 推荐操作 ===")
    if probed:
        best_f, best_r = probed[0]
        log(f"推荐切换到: {best_f.get('name')} ({best_f['id']})")
        log(f"  model 字段: {best_r['model_field']}")
        log(f"  需改 hm40006:")
        log(f"    1. docker-compose.yml env NVCF_DEEPSEEK_FUNCTION_ID: {best_f['id']}")
        log(f"    2. gateway/config.py NV_MODEL_IDS['dsv4p_nv']: {best_r['model_field']}")
        log(f"    3. docker compose up -d hm40006 (recreate)")
        log(f"  并提交到仓库 deploy_artifacts/")
    else:
        log("⚠️ 候选均不支持 reasoning_content — 可切 orion (无思考链但可用) 作降级")
        # 找 orion
        orion = [f for f in cands if "orion" in f.get("name", "").lower()]
        if orion:
            log(f"  降级方案: {orion[0].get('name')} ({orion[0]['id']}) — 无思考链但可用")

    return 2 if cur_status in ("INACTIVE", "DEGRADED", "MISSING") else 1


if __name__ == "__main__":
    sys.exit(main())
