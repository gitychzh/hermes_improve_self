# R4: 双机 TRUNCATE DB 重启 24h 对比窗口 + HM1 hm40006 容器崩溃修复（授权破例自改）

> **授权破例自改（双机维护）** — 非交替优化 turn。用户(2026-06-29)授权清理 DB
> `hm_requests`/`hm_tier_attempts`，使 24h 对比窗口从零重启。本机维护，不碰其他模型链路
> (40000-40005, ms_uni4100x)。铁律1"只改对端"在本授权范围内破例。

## 清理动作（已执行并验证）

| 项 | HM1 (opcsname) | HM2 (opc2sname) |
|---|---|---|
| 清理前 hm_requests | 175 (12:35–13:34) | 252 (12:39–13:41) |
| 清理前 hm_tier_attempts | 0 | 4 |
| `TRUNCATE TABLE hm_requests, hm_tier_attempts` | ✅ | ✅ |
| 清理后 | 0 / 0 ✅ | 0 / 0 ✅ |
| 聚合快照留档 | `artifacts/db_snapshots/preR4_2026-06-29.md` ✅ | 同 ✅ |

清理前 DB 聚合快照已写入 repo 留档，可追溯。

## HM1 hm40006 容器崩溃修复（清理过程中发现并修复）

**现象**: TRUNCATE 后核对 health 时，HM1 hm40006 处于 restarting 崩溃循环：
```
File "/app/gateway/handlers.py", line 29, in <module>
    from .upstream import execute_request, UpstreamResult
ModuleNotFoundError: No module named 'gateway.upstream'
```

**根因排查**（不是 TRUNCATE 引起的）:
- TRUNCATE 只动 cc_postgres DB，与 hm40006 容器文件/镜像无关
- 临时从镜像 `cc-infra-hm40006` 起新容器 `python3 -c "from gateway import upstream"` →
  `import OK /app/gateway/upstream.py`，**镜像层 upstream.py 完好**
- 结论: hm40006 旧容器**可写层**的 `__pycache__/upstream.cpython-310.pyc` 损坏，
  Python 加载 pyc 失败导致相对导入 `from .upstream` 报 No module named

**修复**: `cd /opt/cc-infra && docker compose up -d --force-recreate hm40006` —
丢弃损坏的可写层，从干净镜像重新创建容器。不追着修 pyc，直接从镜像重建（工程化做法）。

**验证（修复后）**:
- health=200 ✅
- 日志干净: `[HM-PROXY] Listening on 0.0.0.0:40006 (role=passthrough, default_tier=deepseek_hm_nv)` ✅
- 无 ModuleNotFoundError ✅
- rr_counter bind mount 保留: `{"hm_nv_deepseek":16}` ✅（未因重建丢失，从清理后续涨）
- deepseek_hm_nv tier 正常加载 ✅

## 双机最终状态（清理+修复后）

| 项 | HM1 | HM2 |
|---|---|---|
| hm40006 health | 200 ✅ | 200 ✅ |
| hm40006 容器 | Up healthy (force-recreated) | Up healthy (R3 后未变) |
| 日志 | 干净, Listening | 活跃, k3/k4 succeeded |
| rr_counter.json | `{"hm_nv_deepseek":16}` 从0续 | `{"hm_nv_glm5.1":71}` 从0续 |
| DB hm_requests | 0 (待新请求流入) | 15 (13:41:45+, TRUNCATE后新数据) |
| DB hm_tier_attempts | 0 | (TRUNCATE后归零) |
| hm40006 参数 | R1基线不变 | R1基线不变 |
| ~/.hermes/config | dsv4p 不变 | glm5.1 不变 |

## 24h 对比窗口正式重启

从此刻(2026-06-29 13:41+ UTC+8)起，双机 DB 全清、rr_counter 全清、配置基线一致，
24h 对比窗口干净重启。HM1 dsv4p / HM2 glm5.1，纯观测期不改参数。

## 不变量确认

- 未改任何 hm40006 参数（UPSTREAM_TIMEOUT/TIER_TIMEOUT_BUDGET/MIN_OUTBOUND_INTERVAL_S/
  KEY_COOLDOWN_S/TIER_COOLDOWN_S/HM_CONNECT_RESERVE_S 全部保持 R1 基线值）。
- 未改 `~/.hermes/config.yaml`。
- 未碰其他模型链路（40000-40005, ms_uni4100x）。
- HM1 容器崩溃修复用 force-recreate 从原镜像重建，未改镜像、未改源码、未改 compose。

## ⏳ 轮到HM2优化HM1
