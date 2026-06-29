# R3: 双机清理 rr_counter.json 计数器 — 统一 key 轮换起点（授权破例自改）

> **授权破例自改（双机维护）** — 非交替优化 turn。用户(2026-06-29)授权清理 hm40006
> 的 per-tier round-robin 计数器落盘文件 `rr_counter.json`，使 HM1/HM2 双机 key 轮换
> 起点统一归零，消除对比实验口径不一致。本机维护，不涉及对端博弈，不碰其他模型链路
> (40000-40005, ms_uni4100x)。铁律1"只改对端"在本授权范围内破例。

## 背景（为什么必须清）

R1 双机清零时 round 文件声称"仅留 `rr_counter.json`(=0)"，但实际未清干净：
- HM1 落盘 `{"hm_nv_glm5.1":4454, "hm_nv_deepseek":12788}` —— deepseek 计数器在涨，从历史累计续
- HM2 落盘 `{"hm_nv_deepseek":7550, "hm_nv_kimi":162, "hm_nv_glm5.1":7557}` —— 含 R274 已移除的 kimi 死计数器

后果：双机 key 轮换起点不一致（HM1 从历史累计续、HM2 同理但累计值不同），且 HM2 残留
kimi 死键。违反"干净整洁/长期可维护"原则，且影响 24h 对比的 key 口径公平性。

## 根因排查（工程记录）

`rr_counter.json` 路径 = `LOG_DIR/rr_counter.json` = 容器内 `/app/logs/rr_counter.json`，
而 `/app/logs` 是 **bind mount 到宿主机 `/opt/cc-infra/logs/proxy40006/`**。

首次清理失败：`docker exec rm` + `docker restart` 后文件重新出现且带旧值。原因是 rm 与
restart 存在竞态（进程重启 import 时 `_load_rr_counter` 可能读到残留/被恢复的文件）。

正确姿势（已验证）：**`docker stop` → 删宿主机文件 → `docker start`**。停容器确保进程
退出后再删，无竞态；重启后 `_load_rr_counter` 读不到文件→从 0 开始→第一个请求落盘为 1。

## 清理动作（已执行并验证）

| 项 | HM1 (opcsname) | HM2 (opc2sname) |
|---|---|---|
| 清理前落盘值 | `glm5.1=4454, deepseek=12788` | `deepseek=7550, kimi=162, glm5.1=7557` |
| 原文件备份到 repo | `artifacts/rr_counter_snapshots/rr_counter.HM1.preR3.json` ✅ | `...rr_counter.HM2.preR3.json` ✅ |
| `docker stop hm40006` | ✅ | ✅ |
| 删宿主机 `/opt/cc-infra/logs/proxy40006/rr_counter.json` | ✅ | ✅ |
| `docker start hm40006` | ✅ | ✅ |
| 重启后落盘值（从 0 续） | `{"hm_nv_deepseek":1}` ✅ | `{"hm_nv_glm5.1":4}` ✅ |
| `/health` | 200 ✅ | 200 ✅ |
| 容器状态 | Up healthy ✅ | Up healthy ✅ |
| kimi 死计数器 | — | 已随清理消除 ✅ |

## 验证（清理后真实日志数据）

key 轮换时序与分布（清理后新数据，round-robin 0-4 均匀）：

| nv_key_idx | HM1 count | HM2 count |
|---|---|---|
| 0 (k1) | 35 | 31 |
| 1 (k2) | 33 | 49 |
| 2 (k3) | 31 | 37 |
| 3 (k4) | 32 | 43 |
| 4 (k5) | 31 | 39 |
| (空=502无key) | 0 | 1 |

两机 health=200，round-robin 工作正常，起点统一为 0。HM2 残留的 1×502(空 key) 为清理前
R2 期数据，非本次清理引入。

## 不变量确认

- 未改任何 hm40006 参数（UPSTREAM_TIMEOUT/TIER_TIMEOUT_BUDGET/MIN_OUTBOUND_INTERVAL_S/
  KEY_COOLDOWN_S/TIER_COOLDOWN_S/HM_CONNECT_RESERVE_S 全部保持 R1 基线值）。
- 未改 `~/.hermes/config.yaml`（HM1=dsv4p, HM2=glm5.1 不变）。
- 未碰其他模型链路（40000-40005, ms_uni4100x）。
- DB `hm_requests`/`hm_tier_attempts` 未清（保留 R1 后累计数据作对比依据；如需重启 24h
  对比窗口需另行授权 TRUNCATE）。

## ⏳ 轮到HM2���化HM1
