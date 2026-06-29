# R1: 双机清零重置 — 进入 glm5.1(HM2) vs dsv4p(HM1) 24h 全新数据对比观测期

> **授权破例自改（双机清零维护）** — 非交替优化 turn。用户(2026-06-29)要求清除 HM1/HM2 两边
> 全部历史数据/日志/备份数据，保留已就绪的干净单模型 live 配置作为对比基线，用全新数据
> 重启 24h 双机对比，判定 glm5.1 vs dsv4p 谁更好。本文件为清零后第 1 个轮次（R1 重新编号）。

## 清零动作（已执行并验证）

| 项 | HM1 (opcsname) | HM2 (opc2sname) |
|---|---|---|
| DB `hm_requests` / `hm_tier_attempts` | TRUNCATE → 0 / 0 ✅ | TRUNCATE → 0 / 0 ✅ |
| `logs/proxy40006/` jsonl+log+.db | 全删，仅留 `rr_counter.json`(=0) ✅ | 全删，仅留 `rr_counter.json` ✅ |
| `docker-compose.yml.bak.*` | 63 个全删 ✅ | 72 个全删 ✅ |
| `backups/` 目录内容 | 清空 ✅ | 清空 ✅ |
| `gateway/*.bak*` | 5 个全删 ✅ | 5 个全删 ✅ |
| `~/.hermes/config.yaml.bak*`/`.corrupt*` | 全删，留 live ✅ | 全删，留 live ✅ |
| repo `rounds/*.md` | 317 个全删（含未提交 R277） ✅ | pull 同步 ✅ |
| repo `upstream_*.py` | 2 个全删 ✅ | pull 同步 ✅ |
| hm40006 容器 | Up healthy, /health=ok ✅ | Up healthy, /health=ok ✅ |

git 历史（旧 round 文件）保留，可 `git show HEAD~1:rounds/...` 追溯；工作区从 R1 重新开始。

## 对比基线（保留的 live 配置，本轮不改）

两边各自已调稳的单模型链路，作为 24h 对比的公平起跑线：

| 参数 | HM1 (dsv4p, deepseek_hm_nv) | HM2 (glm5.1, glm5.1_hm_nv) |
|---|---|---|
| hermes `model.default` | `deepseek_hm_nv` | `glm5.1_hm_nv` |
| hm40006 active tier | deepseek_hm_nv (single) | glm5.1_hm_nv (single) |
| UPSTREAM_TIMEOUT | 64 | 70 |
| TIER_TIMEOUT_BUDGET_S | 164 | 128 |
| MIN_OUTBOUND_INTERVAL_S | 19.2 | 13.0* |
| KEY_COOLDOWN_S | 38 | 38 |
| TIER_COOLDOWN_S | 38 | 22 |
| HM_CONNECT_RESERVE_S | 24 | 22 |

\* HM2 `MIN_OUTBOUND_INTERVAL_S` 在清零窗口内由容器重启从 config.py 默认重载为 13.0
（盘点点位时为 11.0）。active tier 仍为单模型 glm5.1，不影响对比有效性；记为基线值。

**本轮起 N 轮内双方都不改 hm40006 tunable 参数**（只观测，违反则污染对比）。

## 24h 观测期约束

- 双方都不改 hm40006 参数（UPSTREAM_TIMEOUT / TIER_TIMEOUT_BUDGET_S / MIN_OUTBOUND_INTERVAL_S /
  KEY_COOLDOWN_S / TIER_COOLDOWN_S / HM_CONNECT_RESERVE_S / strip_params / MODEL_TIERS）。
- 突发故障只做**恢复性重启**（`docker compose up -d hm40006` / restart），不改参数；并在
  对应轮次文件记录中断时段，对比时剔除该窗口。
- 每 30min 落一个数据点，两边同窗口、同 SQL。

## 对比口径（两边同窗口同 SQL，每 30min 一点）

- 成功率：`hm_requests.status=200 / count(*)`
- 延迟：avg / P50 / P95 `duration_ms`（status=200 子集）
- 错误分布：`hm_tier_attempts.error_type` 计数（empty_200 / NVCFPexecTimeout /
  NVCFPexecSSLEOFError / all_tiers_exhausted / …）
- 429 / fallback：`key_cycle_429s` 求和、`fallback_occurred=true` 计数
- 吞吐：30min `hm_requests` 请求数

DB 表名为 `hm_requests` + `hm_tier_attempts`；`hm_tier_attempts` 的 key 列名为 `nv_key_idx`。

## 决策标准（24h 后，按优先级）

1. 成功率：高者胜（差 >1 个百分点即显著）。
2. 延迟 P50/P95：低者胜。
3. 稳定性：502/中断次数少者胜。
4. 持平则保留实现更简洁、strip_params 更少、上游更稳者。

## 收敛动作（24h 后，输方）

输方 hm40006 的 `HM_NV_MODEL_TIERS` / NVCF_*_FUNCTION_ID 切到赢方模型，hermes config
`default` 同步切；清输方 config.py 里败模型死代码（function_id / MODEL_MAP 别名 /
_TIER_RR_KEYS / MODEL_INPUT_TOKEN_SAFETY，仿旧 R276 清 kimi 模式）；rebuild + 验证 +
轮次文件 + commit。最终两机只跑同一模型，链路整洁。

## 验证 checklist（本清零轮）

- [x] HM1 DB 两表 count=0
- [x] HM2 DB 两表 count=0
- [x] HM1/HM2 logs/proxy40006 仅留 rr_counter.json
- [x] HM1/HM2 docker-compose.yml.bak.* 全删，live compose 保留
- [x] HM1/HM2 backups/ 清空
- [x] HM1/HM2 gateway/*.bak* 全删，live config.py/upstream.py 保留
- [x] HM1/HM2 ~/.hermes 仅留 live config.yaml
- [x] repo rounds/ 清空，upstream_*.py 删除
- [x] HM1 hm40006 healthy + env 不变（dsv4p 基线）
- [x] HM2 hm40006 healthy + env 不变（glm5.1 基线，MIN_OUTBOUND=13.0）
- [x] R1 种子文件带 turn marker，轮次机制连续

## ⏳ 轮到HM2优化HM1

（24h 观测期内 HM2 暂不执行参数优化；marker 仅维持轮次机制连续，HM2 pull 后进入观测）
