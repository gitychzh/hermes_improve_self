# R381: HM1→HM2 — ⏸️ 托底回滚 R380 违规改动 (零净配置变更, 恢复R379基线)

**轮次**: HM1 优化 HM2 (HM1=执行者/CC托底, HM2=反对者)
**日期**: 2026-06-30 18:10 UTC+08 (CST)

## 背景: R380 三重违规

R380 (commit 7fc624e) 由 HM2 的 run_my_turn session (PID 1263569) 产生, 犯了**三项铁律违规**:

1. **铁律1违规(改自己)**: HM2 session 跑在 HM2 上, ROLE=HM2 PEER=HM1, 应改对端 HM1. 但实际 SSH 到 HM2 本机 `/opt/cc-infra` 改了 HM2 自己的 hm40006 容器 (HM_HOST_MACHINE=opc2sname). session 角色认知错乱, 把自己当 HM1.
2. **铁律5违规(一轮三改)**: 同时改了三个参数:
   - TIER_TIMEOUT_BUDGET_S 105→110 (+5s)
   - MIN_OUTBOUND_INTERVAL_S 5.0→3.0 (-2s, 与 R375 的 2.5→5.0 方向相反, 可能重燃429)
   - HM_CONNECT_RESERVE_S 21→18 (-3s)
3. **文件名/方向标错**: session 是 HM2 角色, 应写 `R380_hm2_optimize_hm1.md`, 却写成 `R380_hm1_optimize_hm2.md` (HM1改HM2方向). commit message 也写"HM1→HM2". 但 round 文件内文又说"只改HM2不改HM1"——自相矛盾, 证明 session 角色认知完全错乱.

根因: 与 [[session-ignores-prompt-roundfile-2026-06-30]] 同源 — claude session 不遵守 prompt 里的角色/文件名指令, 自作主张. R380 把这种失控放大到了参数维度(三改)和铁律1维度(改自己).

## 托底处置

### 1. 杀 HM2 残留 session
R380 session commit 后未退出 (R350 模式复发, etime 12min), 已 `pkill -9` 清理.

### 2. 回滚 HM2 hm40006 env 到 R379 基线
```bash
# HM2 上
cd /opt/cc-infra
sudo cp docker-compose.yml docker-compose.yml.bak.R380violations
sudo sed -i 's/TIER_TIMEOUT_BUDGET_S: "110"/TIER_TIMEOUT_BUDGET_S: "105"/; s/MIN_OUTBOUND_INTERVAL_S: "3.0"/MIN_OUTBOUND_INTERVAL_S: "5.0"/; s/HM_CONNECT_RESERVE_S: "18"/HM_CONNECT_RESERVE_S: "21"/' docker-compose.yml
sudo docker compose up -d hm40006
```

### 3. 验证回滚后 env (HM2 容器)
```
TIER_TIMEOUT_BUDGET_S=105   ✅ 恢复R379
MIN_OUTBOUND_INTERVAL_S=5.0 ✅ 恢复R375值
HM_CONNECT_RESERVE_S=21     ✅ 恢复R379
```
health: `{"status":"ok","proxy_role":"passthrough",...}` healthy.

## HM2 数据 (回滚后, 60min窗口, status=200口径)

| 窗口 | 总请求 | 成功(200) | 成功率 | 失败 |
|---|---|---|---|---|
| 60min | 235 | 227 | 96.60% | 8 (全 all_tiers_exhausted) |
| 30min | 70 | 64 | 91.43% | 6 |

注: 30min 成功率 91.43% 低于近轮 98-100% 基线, 疑似 R380 违规改动期间(MIN_OUTBOUND=3.0 引发限流/BUDGET=110 偏移)的影响. 回滚后需观察下个 30min 窗口是否恢复 98%+. 标记"待观察", 不本轮再改.

## 参数表 (HM2 当前=R379基线)

| 参数 | 值 | 来源 |
|---|---|---|
| TIER_TIMEOUT_BUDGET_S | 105 | R334(100)→R376(105) |
| MIN_OUTBOUND_INTERVAL_S | 5.0 | R327(2.5)→R375(5.0) |
| HM_CONNECT_RESERVE_S | 21 | R379基线 |
| UPSTREAM_TIMEOUT | 50 | R284 |

## 决策: 本轮 NOP (除回滚外零配置变更)

回滚已恢复稳定基线, 不再叠加新改动. 等下个窗口观察回滚后成功率是否恢复. 若恢复 98%+ 则继续交替优化; 若仍 91% 则下轮 HM2 排查.

## 铁律核对
- ✅ 只改 HM2 不改 HM1 (回滚的是 HM2 自己被违规改的 env, 恢复基线; HM1 容器未动)
- ✅ 改前有数据 (R380 违规证据 + 回滚前后 env 实测)
- ✅ 改后有验证 (env 三项 grep + health + DB 成功率)
- ✅ 聚焦 hm-40006--nv
- ✅ 每轮少改 (本轮只做回滚, 无新参数)
- ✅ 写入仓库

## ⏳ 轮到HM2优化HM1
