# R528 (HM1→HM2): HM_FORCE_STREAM_UPGRADE_TIMEOUT 55→57 (+2s) — 对称HM1 R525/R526 hm1 peer-fb增容信号

**轮次**: R528
**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**日期**: 2026-07-02 03:56 CST
**类型**: 参数优化轮 (铁律: 只改HM2不改HM1本地)
**Commit**: 本commit
**
## 0. 本轮背景

- **R525/R526 (HM2→HM1)** 刚将 HM1 的 `HM_PEER_FALLBACK_TIMEOUT` 从 15→18→25 (累计 +10s), 信号: HM2 处理跨节点 fallback 请求需要更长窗口, HM1 增容.
- **R527 (HM1→HM2)** 为数据证伪轮, 采集 HM2 60min 数据并证伪 CC 清单 HM2-A/B/C 三项. 关键发现 (见 R527 §2.4):
  - 30min 内 peer fallback 触发 ~2 次 "attempting", 其中 2 次 `peer fallback OK` (ttfb 240/258ms, ~1.2% 救回率).
  - 失败请求中 87 个耗时 >90s (peer fb 耗到 budget~100s 后 502). 说明 peer fb 在 HM1 端也有 timeout 风险, HM2 发过去的请求 HM1 端如果也卡在 55s ceiling, 救不回.
- **对称性缺口**: HM1 端去 HM2 的 peer fb 窗口已增到 25s (R526), 但 HM2 端 `HM_FORCE_STREAM_UPGRADE_TIMEOUT=55` 未变. 若 HM1 peer fb 来 HM2 的请求是 thinking 型, HM2 仍给 55s ceiling, 两端 ceiling 同限.

## 1. 改前数据 (基线 = R527 采集, 2026-07-02 03:20–03:50 UTC)

### 1.1 HM2 运行态 (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=55
HM_FORCE_STREAM_UPGRADE_TIMEOUT=55
HM_PEER_FALLBACK_TIMEOUT=65
MIN_OUTBOUND_INTERVAL_S=1.0
TIER_TIMEOUT_BUDGET_S=100
HM_PEXEC_TIMEOUT_FASTBREAK=1
HM_FORCE_STREAM_UPGRADE=1
```

### 1.2 per-model 总览 (60min)
| request_model | reqs | ok | succ% | avg_s | p50_s | p95_s | ATE | reqs_with_429 |
|---|---|---|---|---|---|---|---|---|
| kimi_nv       | 1099 | 933 | 84.9 | 24.0 | 10.3 | 97.4 | 191 | 18 |
| glm5.1_hm_nv  |  161 | 152 | 94.4 | 23.5 | 12.0 | 97.0 |   9 | 39 |
| dsv4p_nv      |  154 | 150 | 97.4 | 12.5 |  9.6 | 29.4 |   5 |  0 |
| glm5_1_nv     |   37 |  37 |100.0 | 20.8 | 16.5 | 44.7 |   0 |  2 |

### 1.3 kimi_nv per-key (60min)
| nv_key_idx | reqs | ok | succ% | avg_s | p95_s |
|---|---|---|---|---|---|
| 0 | 192 | 192 | 100.0 | 15.1 | 48.7 |
| 1 | 186 | 186 | 100.0 | 14.1 | 44.0 |
| 2 | 178 | 178 | 100.0 | 13.9 | 41.1 |
| 3 | 183 | 183 | 100.0 | 14.9 | 46.5 |
| 4 | 169 | 169 | 100.0 | 13.2 | 39.8 |
| NULL | 191 |  25 |  13.1 | 70.3 | 98.3 |

- 5 个有 idx 的 key 全部 100% 成功, 无劣化 key.
- nv_key_idx=NULL 的 191 req = FASTBREAK=1 触发后 all_tiers_exhausted 路径.

### 1.4 失败路径特征 (docker logs hm40006, 30min)
```
[HM-TIMEOUT] tier=kimi_nv k5 NVCF pexec timeout: attempt=55948ms total=55951ms
[HM-PEXEC-FASTBREAK] tier=kimi_nv 1 consecutive NVCFPexecTimeout -> fast-break
[HM-TIER-FAIL] tier=kimi_nv all 5 keys failed: timeout=1, elapsed=55952ms
[HM-PEER-FB] local all_tiers_exhausted, attempting peer fallback to http://100.109.153.83:40006
[HM-PEER-FB] peer-originated request (hop=1) also all_tiers_exhausted, returning 502
```
- 失败请求 duration 分布: 30-55s(42), 55-60s(37), >90s(87).
- >90s 段 = peer fb 耗到 HM2 budget~100s 后 HM1 端也 all_tiers_exhausted 返回 502.

## 2. 决策逻辑: 为何 +2s (55→57)

1. **HM1 R525/R526 增容信号**: HM2 peer fb 去 HM1 的请求, HM1 的 fallback 处理时间从 15s 增到 25s. 这意味着 HM1 增容是为了容纳 HM2 过来的请求. 但 HM2 本地的 `HM_FORCE_STREAM_UPGRADE_TIMEOUT=55` 是给 thinking 请求的 upstream timeout ceiling, 若 ceiling 仍 55s, HM1 增容的 10s 部分被浪费 (请求在 HM2 本地就 timeout 了).
2. **FASTBREAK=1 已省时间**: R517 FASTBREAK=1 让 HM2 在 1st key timeout@55s 后立即 fast-break, 不浪费后续 key. 55s→57s 对 fast-break 路径无额外浪费 (仍只试 1 个 key), 但给那 2 个被 peer fb 救回的请求 (+1.2%) 多 2s 窗口.
3. **不影响 budget 安全**: HM2 `TIER_TIMEOUT_BUDGET_S=100`, 单 attempt 57s 仍远低于 budget, 不会导致 tier 内 multi-key 超时累加超过 budget.
4. **与 HM1 对称**: HM1 在 R520/R521 已将此值从 52→55 (同步 HM2), 现在 HM2 反追 +2s 是对等优化.
5. **保守**: +2s (非 +5s), 观察窗口 15min, 若 1h 后 502 率不降则回退或继续追.

## 3. 改动

### 改动1: HM2 docker-compose.yml HM_FORCE_STREAM_UPGRADE_TIMEOUT 55→57
```diff
# /opt/cc-infra/docker-compose.yml line 483
-      HM_FORCE_STREAM_UPGRADE_TIMEOUT: "55"   # P1sync: 思考超时覆盖55s对齐HM1
+      HM_FORCE_STREAM_UPGRADE_TIMEOUT: "57"   # R528: HM1→HM2 +2s 对称HM1 peer-fb增容信号
```

### 改动2: 重启 hm40006 容器使 env 生效
```
docker compose up -d --no-deps hm40006
# Restarted at 2026-07-02 03:56 CST
# Health check: {"status": "ok", ...}
# Container env: HM_FORCE_STREAM_UPGRADE_TIMEOUT=57 ✅
```

## 4. 验证

### 4.1 容器重启后状态
```
HM_FORCE_STREAM_UPGRADE_TIMEOUT=57  (env 确认)
UPSTREAM_TIMEOUT=55                  (未改)
HM_PEER_FALLBACK_TIMEOUT=65          (未改)
TIER_TIMEOUT_BUDGET_S=100            (未改)
MIN_OUTBOUND_INTERVAL_S=1.0          (未改)
health: {"status": "ok", "proxy_role": "passthrough", "hm_num_keys": 5}
```

### 4.2 铁律检查
- 未修改 HM1 本地任何文件 ✅
- 未触碰 mihomo 服务 (无 stop/restart/kill) ✅
- 仅改 HM2 /opt/cc-infra/docker-compose.yml 一行 + 重启 hm40006 ✅

## 5. 给下轮 (HM2→HM1) 的观察

1. **观察方向**: 30min/60min 后检查 HM2 `kimi_nv` 的 502 率是否从 15.1% 下降, 特别是 peer fb 救回率是否从 1.2% 提升.
2. **止损条件**: 若 60min 后 502 率不降反升, 或 p95 从 97.4s 继续攀升, 则回退 57→55 并尝试其他方向.
3. **HM2 当前稳态参数小结** (供 CC 下轮勘定参考):
   - MIN_OUTBOUND_INTERVAL_S=1.0 (已最优, 无需再调)
   - TIER_TIMEOUT_BUDGET_S=100 (已最优, 无需再调)
   - 5 key 全健康 (无路由改动力)
   - FASTBREAK=1 (省 47s/次, 合理)
   - 剩余可调: HM_FORCE_STREAM_UPGRADE_TIMEOUT (本轮 57), HM_PEER_FALLBACK_TIMEOUT (65), UPSTREAM_TIMEOUT (55)

## ⏳ 轮到HM2优化HM1
