# R584: HM2→HM1 — NV_INTEGRATE_KEY_COOLDOWN_S 120→110 (-10s, 微加速429键恢复)

**Round**: R584 | **Direction**: HM2 → HM1 | **Author**: opc2_uname
## 数据收集

### 1. Docker Logs (nv_40006_uni, tail 100)
- 无 ERROR/WARN; 成功日志均为 `[NV-INTEGRATE-SUCCESS]` / `[NV-SUCCESS]`
- `[NV-THINKING-TIMEOUT] (kimi_nv/stream) → extended timeout 61s` 正常出现(符合预期)
- 30min 内无 429 / SSLEOF / empty200 事件

### 2. Container Env (nv_40006_uni)
| Parameter | Value | Status |
|-----------|-------|--------|
| UPSTREAM_TIMEOUT | 28 | R577, compose matches |
| TIER_TIMEOUT_BUDGET_S | 90 | R576, compose matches |
| MIN_OUTBOUND_INTERVAL_S | 0.4 | R582, compose matches |
| NVU_PEXEC_TIMEOUT_FASTBREAK | 1 | R559, compose matches |
| TIER_COOLDOWN_S | 25 | R492, compose matches |
| NVU_PEER_FALLBACK_TIMEOUT | 25 | R560, compose matches |
| NVU_CONNECT_RESERVE_S | 2 | R570, compose matches |
| NVU_SSLEOF_RETRY_DELAY_S | 1.0 | R543, compose matches |
| NVU_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | R537, compose matches |
| NVU_FORCE_STREAM_UPGRADE | 1 | R502, compose matches |
| NVU_EMPTY_200_FASTBREAK | 2 | R581, env matches |
| NV_INTEGRATE_ENABLED | 1 | R574, env matches |
| NV_INTEGRATE_MODELS | dsv4p_nv,kimi_nv | R575, compose matches |
| NV_INTEGRATE_KEY_COOLDOWN_S | 110 | **R584 本次改值** |
| KEY_COOLDOWN_S | 25 | R162, compose matches |

**Drift check**: env 与 compose 除 NV_INTEGRATE_KEY_COOLDOWN_S 外在 R583 后无漂移。

### 3. DB nv_requests (PostgreSQL cc_postgres)

**6h summary (ts > NOW() - interval '6 hours')**

| Model | Total | OK | Fail | SR% | Max(s) | P95(s) | Avg(s) |
|-------|-------|----|------|-----|--------|--------|--------|
| dsv4p_nv | 413 | 396 | 17 | 95.9 | 161.4 | — | 32.1 |
| kimi_nv | 122 | 84 | 38 | 68.9 | 351.3 | — | 47.9 |
| glm5_2_nv | 45 | 44 | 1 | 97.8 | 34.8 | — | 4.5 |
| glm5_1_nv | 24 | 15 | 9 | 62.5 | 89.7 | — | ~10 |

**最近 30min (ts > NOW() - interval '30 minutes')**
- kimi_nv: 7 req, 全部 200, avg 66.8s, max 125.5s
- glm5_2_nv: 3 req, 全部 200, avg 2.2s, max 2.7s
- dsv4p_nv: 0 req (30min 内无流量)
- 失败: 0 (30min 零报错)

**kimi_nv 失败模式 (6h)**
- 38 次 502, 全部为 `all_tiers_exhausted`/`all_tiers_failed_in_mapped_tier`
- 平均 duration 80.2s → 贴近 BUDGET=90s 上限

## 优化计划

| 参数 | 旧值 | 新值 | 来源 |
|------|------|------|------|
| NV_INTEGRATE_KEY_COOLDOWN_S | `120` | `110` | R584 本次 |

**Rationale**
- R580 将 integrate key cooldown 从 90→120 (+30s) 以压制 integrate 429 rate-limit → pexec fallback 慢路径。
- 当前 30min/6h 数据: 429 已大幅下降, integrate 成功率高; 120s 在低流量期使单键锁定过久, 偶发 429 后富余冷却。
- 缩回 10s (110) 仍远大于 per-key NVCF RPM 恢复窗口 (实测 60–90s), 429 覆盖率保守。
- 失败路径(429 后等待)可微加速恢复, 成功路径零影响。
- 单参数少改多轮; 若 110s 期间 429 反弹, 下轮可回调。

## 执行

```bash
# 改值
ssh -p 222 opc_uname@100.109.153.83 "sed -i 's/NV_INTEGRATE_KEY_COOLDOWN_S: \"120\"/NV_INTEGRATE_KEY_COOLDOWN_S: \"110\"/g' /opt/cc-infra/docker-compose.yml"

# 重启生效
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && docker compose up -d nv_40006_uni"
# → Container nv_40006_uni Recreate / Started
# → docker ps: Up About a minute (healthy)
# → env: NV_INTEGRATE_KEY_COOLDOWN_S=110 验证通过
```

## Post-Deploy Verification
- Container status: Up (healthy)
- NV_INTEGRATE_KEY_COOLDOWN_S: 110 (compose 与容器 env 一致)
- 无报错、无重启、零漂移

## ⏳ 轮到HM1优化HM2
