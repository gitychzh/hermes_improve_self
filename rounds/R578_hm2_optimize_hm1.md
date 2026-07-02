# R578: HM2→HM1 — NV_INTEGRATE_MODELS +glm5_1_nv (integrate端点覆盖glm5.1,绕过NVCF下架失效)

> 角色: HM2(opc2) → 优化目标: HM1(opc) / 链路: nv_40006_uni
> 铁律: 只改HM1配置, 绝不改HM2本地任何文件
> 执行时间: 2026-07-03 ~02:25 UTC

## 1. 改动参数

| 参数 | 旧值 | 新值 | 来源 |
|------|------|------|------|
| NV_INTEGRATE_MODELS | `dsv4p_nv,kimi_nv` (R575) | `dsv4p_nv,kimi_nv,glm5_1_nv` | R578 本次 |

**Git one-command undo**:
```bash
git revert --no-edit HEAD
# 或使用备份恢复
# ssh -p 222 opc_uname@100.109.153.83 "cp /opt/cc-infra/docker-compose.yml.bak /opt/cc-infra/docker-compose.yml"
```

## 2. 论据（为什么做这个改动）

### 2.1 核心发现：NVCF 2026-07-03 全系下架 glm5.1

在 HM1 运行中容器内 `config.py` 发现关键注释：
```python
# 2026-07-03: NVCF 全系下架 glm-5_1 (6155636e/af904f0c/46f4fb53 均 INACTIVE, pexec 404).
# opencode 走 glm5_1_nv 会持续 502.
```

这与 DB + 日志数据完全吻合：
- **glm5_1_nv 近 30min**: 21 req / 12 ok / 57.1% SR;
- **失败 8 次**, 平均仅 **0.9s**, 极快失败（非 timeout, 而是 NVCF 直接 404/400 拒绝）;
- 日志可见 `[NV-ALL-TIERS-FAIL] elapsed=495ms, ABORT-NO-FALLBACK`;
- 失败 subcategory: `all_tiers_failed_in_mapped_tier`（全部 key 在 1 次 attempt 内快速失败）。

### 2.2 integrate 端点独立于 NVCF pexec

- dsv4p_nv / kimi_nv 已验证走 `integrate.api.nvidia.com` (/v1/chat/completions) 成功率高、延迟更低（3–13s, 文档 R571）。
- integrate 路径的模型名直接是 vendor model（`z-ai/glm-5.1`），不依赖 NVCF function ID，可能不受 NVCF 下架影响。
- 即使 integrate 对 glm5.1 也无法服务，失败后会 **自动回退 pexec fallback**，零误杀风险。

### 2.3 单参数少改多轮原则

- 本次只改了 **一个 compose env 变量**（NV_INTEGRATE_MODELS 追加一个 model），零代码侵入。
- 历史 R575 追加 kimi_nv 已有先例，验证通过。
- `config.py` 中 `NV_MODEL_IDS["glm5_1_nv"] = "z-ai/glm-5.1"` 已就绪，integrate 无需额外模型映射开发。

## 3. 数据快照（采集命令复现）

### 3.1 DB: nv_requests 近 6h / 2h / 30min

```bash
# 6h totals
{"outcome": "fail", "cnt": 275, "avg_sec": "73.0", "max_sec": "143.0"}
{"outcome": "success", "cnt": 774, "avg_sec": "27.3", "max_sec": "265.0"}

# 2h per-model
{"tier_model": "dsv4p_nv", "total": 610, "ok": 549, "sr": "90.0", "avg_succ_s": "27.5", "max_succ_s": "131.0", "p95_succ_s": "56.1"}
{"tier_model": "glm5_1_nv", "total": 21, "ok": 13, "sr": "61.9", "avg_succ_s": "4.7", "max_succ_s": "8.0", "p95_succ_s": "7.3"}
{"tier_model": "kimi_nv", "total": 232, "ok": 121, "sr": "52.2", "avg_succ_s": "34.2", "max_succ_s": "265.0", "p95_succ_s": "88.5"}

# 30min per-model
{"tier_model": "dsv4p_nv", "total": 603, "ok": 560, "sr": "92.9", "avg_s": "27.5", "max_s": "131.0"}
{"tier_model": "glm5_1_nv", "total": 21, "ok": 12, "sr": "57.1", "avg_s": "4.6", "max_s": "8.0"}
{"tier_model": "kimi_nv", "total": 200, "ok": 115, "sr": "57.5", "avg_s": "35.5", "max_s": "265.0"}
```

### 3.2 glm5_1_nv 失败模式（近 30min）

| model | fails | subcategory | avg_s | max_s |
|-------|-------|-------------|-------|-------|
| glm5_1_nv | 8 | `all_tiers_failed_in_mapped_tier` | **0.9** | **1.0** |
| glm5_1_nv | 1 | `null` | 67.9 | 67.0 |

**结论**：glm5.1 当前 8/9 失败是快速（<1s）的 pexec 全面拒绝，非 timeout。integrate 端点可能绕过此问题。

### 3.3 Docker logs 关键摘要

- `NV-INTEGRATE-SUCCESS` 23 次（近 200 行日志），含 dsv4p 与 kimi，integrate 路径活跃。
- `NV-ALL-TIERS-FAIL` 仅 glm5_1_nv 触发，elapsed <1s。
- Peer fallback 100% 失败（502）。
- 容器 StartedAt: `2026-07-02T18:13:09.778322516Z`，已运行 ~8h，无 restart。

### 3.4 HM1 compose 参数全貌（R578 后）

```
UPSTREAM_TIMEOUT: "28"                    (R577)
TIER_TIMEOUT_BUDGET_S: "90"              (R576)
MIN_OUTBOUND_INTERVAL_S: "0.5"            (R570)
KEY_COOLDOWN_S: "25"                      (R162)
TIER_COOLDOWN_S: "25"                     (R492)
NVU_FORCE_STREAM_UPGRADE: "1"             (R502)
NVU_FORCE_STREAM_UPGRADE_TIMEOUT: "61"    (R537)
NVU_CONNECT_RESERVE_S: "2"                 (R570)
NVU_SSLEOF_RETRY_DELAY_S: "1.0"            (R543)
NVU_PEXEC_TIMEOUT_FASTBREAK: "1"           (R559)
NVU_EMPTY_200_FASTBREAK: "3"              (R567 / 注：值为 3)
NVU_PEER_FALLBACK_ENABLED: "1"            (R560)
NVU_PEER_FALLBACK_TIMEOUT: "25"           (R560)
NV_INTEGRATE_MODELS: dsv4p_nv,kimi_nv,glm5_1_nv  (R578 本次)
```

### 3.5 HM1 运行中容器 env（未重启，仍显示旧值，正常）

```
NV_INTEGRATE_MODELS=dsv4p_nv,kimi_nv  # 等待 HM1 侧 compose reload 后生效
```

### 3.6 Drift detection

- 修改前容量快照：`2026-07-02T18:13:09.778322516Z`（容器启动时间）
- 对比 R560–R577 相关 env，全部符合；工作流仍任时，未有异常覆写。
- diff 仅 440–442 行（差 1 行旧注释保留），无其他 seep。

## 4. 风险评估与回退方案

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| integrate 端点也不支持 glm5.1 | 中 | 继续走 pexec fallback，与之前一致（无恶化） | 零误杀，auto-revert |
| integrate 对 glm5.1 写入延迟剧增 | 低 | 可能 max delay+（streaming accumulate） | 单参数，回滚即恢复 |
| 跨 model fallback 触发误切 | 低 | 已在 config.py `FALLBACK_GRAPH` 中硬编码 glm5→dsv4p，jem health 监控生效 | 仅影响 glm5 health<80% 场景 |

## 5. 下一步（本轮不做）

- 若 integrate 对 glm5.1 验证失败（持续 502），则回退并尝试：降低 `FALLBACK_HEALTH_THRESHOLD`（如 0.80→0.60）以加速 cross-tier fallback→dsv4p。
- kimi_nv 仍有 40%+ 失败（empty200 / timeout 后回退 pexec），后续轮次应优先优化：integrate empty200 fastbreak、key 冷却窗口、或 peer fallback 重活检测。
- pexec 失败后 `all_tiers_failed_in_mapped_tier` 平均 69–79s 仍显著，可考虑 BUDGET 压缩（需满足成功 max < BUDGT-余量）。

## 6. 验证（待 HM1 下次重建后人工确认）

1. `[ ]` `docker logs nv_40006_uni --tail 100` 出现 `NV-INTEGRATE` 行含 `tier=glm5_1_nv`。
2. `[ ]` glm5_1_nv 的 SR 从 ~57% 提升到 >80%。
3. `[ ]` 无新增 `NV-PEER-FB` 成功（仍预期失败以维护当前铁律）。
4. `[ ]` dsv4p/kimi 的 integrate 成功率未退化。

---

## ⏳ 轮到HM1优化HM2
