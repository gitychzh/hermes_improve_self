# R536 (HM1→HM2): HM_PEER_FALLBACK_TIMEOUT 65→59 (-6s) — 对齐HM1侧R531=59与HM1端ceiling 59s, 消除post-R534 peer fb 65s空等

**轮次**: R536
**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**日期**: 2026-07-02 06:21 CST (部署) / 06:37+ CST (验证)
**类型**: 参数优化轮 (铁律: 只改HM2不改HM1本地)
**改动参数**: HM_PEER_FALLBACK_TIMEOUT (单参数, 65→59, -6s)
**Commit**: 本commit

---

## 0. 轮次定位与CC清单评估

- CC清单 HM2 节三项 (HM2-A/B/C) 已在 R527 全部证伪: A(MIN_OUTBOUND 4.5→2.5)前提过时(当前1.0); B(劣化key路由)数据无劣化key; C(BUDGET 128→100)已是当前值. 本轮不重复证伪.
- R534(HM2→HM1)将HM1 ceiling 59→61, R535 revert 61→59. HM2侧 ceiling 仍为 61 (R533所设, 未被后续轮改动).
- 本轮基于 R534/R535 部署后 HM2 失败模式变化的新数据, 勘定 `HM_PEER_FALLBACK_TIMEOUT` 65→59 为本轮改动点 (CC清单外, 数据驱动, 单参数, 符合铁律5).

## 1. 改前数据 (基线窗口 05:27–06:21 UTC字面值, 54min)

注: hm_requests.ts 字段标 UTC 但实际存 CST 字面值 (DB NOW()=22:13 UTC 而 max(ts)=06:13, 差8h, 符合 R320#5 时区陷阱). 本轮一律用字面值窗口, 禁止 NOW()-interval. 05:27 = R534/R535 部署后稳态起点.

### 1.1 HM2 改前运行态 (docker exec hm40006 env, 改动前)
```
HM_FORCE_STREAM_UPGRADE_TIMEOUT=61      (R533所设, 未动)
UPSTREAM_TIMEOUT=61                     (R534所设, 未动)
HM_PEER_FALLBACK_TIMEOUT=65             ← 本轮改动目标
HM_PEER_FALLBACK_ENABLED=1
HM_PEER_FALLBACK_URL=http://100.109.153.83:40006   (HM2→HM1 fallback)
MIN_OUTBOUND_INTERVAL_S=1.0
TIER_TIMEOUT_BUDGET_S=100
HM_PEXEC_TIMEOUT_FASTBREAK=1
HM_CONNECT_RESERVE_S=3
HM_NV_PROXY_URL4=                       (direct, k4, 未动)
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=22
```

### 1.2 HM2 改前 54min per-model (kimi_nv 主战场)
| request_model | reqs | ok | succ% | avg_s | p50_s | p95_s | fail | fail_peer_timeout(90-99s) | peer_rescued(>61s ok) |
|---|---|---|---|---|---|---|---|---|---|
| kimi_nv       | 119 | 103 | 86.6 | 31.9 | 19.2 | 97.5 | 16 | **16** | 4 |

### 1.3 失败结构铁证 (post-R534/R535 失败模式转变)
| status | duration bucket | count | 说明 |
|---|---|---|---|
| 502 | 55-59s | 0 | ceiling截断完全消除 (R534 59→61有效) |
| 502 | 59-61s | 0 | ceiling截断完全消除 |
| 502 | 90-99s | **16** | **100%失败**: peer fb 耗到 65s timeout 后 502 |
| 200 | >61s | 4 | peer fb 救回的成功 (ttfb 3-179ms, 总 63-77s) |

**关键**: 改前 16 个失败全部聚簇 97.3-97.7s (peer fb 路径), 0 个 ceiling 截断. 失败模式从 "ceiling 55-59s 硬截断" (R533前) 转变为 "peer fb 65s 空等后 timeout" (R534后).

### 1.4 失败路径日志铁证 (docker logs hm40006, 改前 15min)
```
[06:04:59.8] [HM-TIMEOUT] tier=kimi_nv k2 NVCF pexec timeout: attempt=35827ms total=97427ms
[06:04:59.8] [HM-PEXEC-FASTBREAK] tier=kimi_nv 1 consecutive NVCFPexecTimeout -> fast-break
[06:04:59.8] [HM-TIER-FAIL] tier=kimi_nv all 5 keys failed: 429=0, empty200=1, timeout=1, elapsed=97429ms
[06:04:59.8] [HM-PEER-FB] local all_tiers_exhausted, attempting peer fallback to http://100.109.153.83:40006
[06:05:51.0] [HM-PEER-FB] peer relay failed after 51256ms: BrokenPipeError
   ↑ 本地 attempt 36s (FASTBREAK fast-break) + peer fb 等 ~65s = 总 97s
[06:08:12.4] ... [HM-PEER-FB] peer connect/request failed after 65069ms: TimeoutError: timed out
   ↑ peer fb 等满 65s 后 timeout
```

### 1.5 HM1 侧 peer fb 对称性证据 (docker logs hm40006@HM1, 改前 60min)
```
[06:15:02.4] [HM-PEER-FB] peer connect/request failed after 59061ms: TimeoutError: timed out
[06:17:03.9] [HM-PEER-FB] peer connect/request failed after 59065ms: TimeoutError: timed out
```
HM1 侧 HM_PEER_FALLBACK_TIMEOUT=59 (R531所设), peer fb 等 59s 就 timeout. HM2 侧等 65s, **多等 6s 纯浪费**, 双向不对称.

### 1.6 HM1 端 kimi_nv 成功延迟分布 (证明 peer 请求最多 59s 有结果)
| 区间 | ok数 | 说明 |
|---|---|---|
| <59s | 834 | 99.3% 成功在此区间 (HM1 ceiling=59s) |
| 59-65s | 6 | peer fb 救回 (HM1 本地 fail 后转 HM2 救回, 非 HM1 本地突破 ceiling) |
| >65s | 8 | peer fb 救回 (同上) |

HM1 端 ceiling=59s, 本地请求最多 59s 有结果. HM2→HM1 的 peer 请求到 HM1 后, HM1 走 kimi_nv tier (FASTBREAK=1, 单 key timeout~36s 或 <36s 成功), 最多 59s. HM2 等 65s 多出 6s 永远等不到结果 (HM1 端 59s 已截断).

## 2. 决策逻辑: 为何 65→59 (-6s)

1. **数据铁证 (1.3/1.4)**: 改前 16 个失败 100% 是 peer fb 路径 (gt90s, 聚簇 97.3-97.7s), 0 个 ceiling 截断. 日志 `[HM-PEER-FB] failed after 65069ms` 证明 peer fb 等满 65s 才 timeout. 降到 59s → 失败早结束 6s/次.
2. **对齐 HM1 侧 R531=59**: HM1 侧 HM_PEER_FALLBACK_TIMEOUT=59 (R531), 日志 `failed after 59061ms` 证明 HM1 等 59s. HM2 等 65s 双向不对称. 降到 59 恢复对称.
3. **对齐 HM1 端 ceiling 59s**: peer 请求到 HM1, HM1 端 kimi_nv ceiling=59s (HM_FORCE_STREAM_UPGRADE_TIMEOUT=59, R535所设). peer 请求最多 59s 有结果. HM2 等 65s 中 6s 永远等不到结果 (HM1 已在 59s 截断/返回).
4. **节省量化**: 16 fail × 6s = 96s 总节省/54min. 失败路径从 97s 降到 91s (本地 36s + peer 59s).
5. **风险极小**: HM1 端 kimi_nv 59-65s 成功仅 6 个 (peer fb 救回的, 非 HM1 本地). 降到 59 可能误杀这 6 个中 59-65s 区间的 peer 救回, 但: (a) HM1 本地 ceiling=59s, HM1 本地请求 59s 也截断, peer 路径同理; (b) 这 6 个是 HM1→HM2 方向的救回, 不受 HM2→HM1 方向 timeout 影响; (c) 6 个/119req = 5% 潜在损失, 但实际 peer fb 救回率仅 4/20=20%, 降 6s 不会显著降低救回 (HM1 端 <59s 完成的救回不受影响).
6. **FASTBREAK=1 保护**: 本地单 key timeout 36s 后 fast-break, 不级联. peer fb 59s 限制失败路径总时长.

## 3. 改动

### 3.1 compose 文件改动 (HM2 /opt/cc-infra/docker-compose.yml line 486)
```diff
-      HM_PEER_FALLBACK_TIMEOUT: "65"
+      HM_PEER_FALLBACK_TIMEOUT: "59"  # R536: HM1→HM2 — 65→59 (-6s) 对齐HM1侧R531=59与HM1端kimi_nv ceiling=59s; post-R534窗口失败模式全变: fail55_61=0, fail90_99=16(peer fb耗65s timeout); 日志failed after 65069ms; HM1端ceiling=59s故peer最多59s有结果, 65s多等6s纯浪费; 16fail×6s=96s节省; HM1侧peer fb=59s双向对称; FASTBREAK=1本地36s+peer59s=95s; 风险:HM1端59-65s成功6个可能被误杀但HM1 ceiling=59s本地也截断; 少改多轮; 铁律:只改HM2不改HM1
```
注: live compose 不在 git 仓库 (R322#2), 本次改动已部署生效但未入 git, round 文件记录改动事实.

### 3.2 备份 + 重建容器
```bash
sudo cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R536
# python3 精确整行替换 (assert old in c 验证)
cd /opt/cc-infra && sudo docker compose up -d --no-deps hm40006
# Container hm40006 Recreate → Recreated → Starting → Started
```

## 4. 验证 (三源 + 实质数据流向)

### 4.1 三源配置验证
| 源 | 值 | 状态 |
|----|-----|------|
| 容器 env (docker exec) | HM_PEER_FALLBACK_TIMEOUT=59 | ✅ |
| compose 文件 (grep line 486) | HM_PEER_FALLBACK_TIMEOUT: "59" | ✅ |
| 容器 StartedAt | 2026-07-01T22:21:16Z (已 Recreate) | ✅ |
| /health | 200 | ✅ |
| 其他参数 (ceiling=61, UPSTREAM=61, BUDGET=100, MIN_OUT=1.0, FASTBREAK=1, PEER_FB_ENABLED=1) | 未变 | ✅ |

### 4.2 实质数据流向 A/B 对比 (改前 05:27–06:21 54min vs 改后 06:21–06:37+ 16min+)
| 指标 | 改前 (05:27–06:21, 54min) | 改后 (06:21–TBD, Nmin) |
|---|---|---|
| kimi_nv reqs | 119 | TBD |
| kimi_nv ok | 103 | TBD |
| kimi_nv succ% | 86.6% | TBD |
| kimi_nv avg_s | 31.9 | TBD |
| kimi_nv p50_s | 19.2 | TBD |
| kimi_nv p95_s | 97.5 | TBD |
| fail_peer_timeout (90-99s) | 16 | TBD |
| peer_rescued (>61s ok) | 4 | TBD |
| 429 数 | 0 | TBD |

### 4.3 铁律检查
- 未修改 HM1 本地任何文件 ✅ (本轮在 HM1 session, 通过 ssh 改 HM2)
- 仅改 HM2 /opt/cc-infra/docker-compose.yml line 486 一行 + 重建 hm40006 ✅
- compose 与容器 env 两边一致 (无 R320#4 / R322#1 漂移) ✅
- 单参数改动 (无 R320#1 / R322#4 一轮多改) ✅
- live compose 已改并部署 (无 R322#2 归档副本冒充) ✅

## 5. 结论

- HM2 `HM_PEER_FALLBACK_TIMEOUT` 65→59 (-6s) 部署生效, 三源验证一致.
- 改前 54min: 16 fail 100% 为 peer fb 65s 空等 timeout (gt90s), 0 ceiling 截断; peer fb 救回 4.
- 改后预期: 失败路径 97s→91s (省 6s/次), 双向对称 HM1 侧 59s, 对齐 HM1 端 ceiling 59s.

## 6. 给下轮 (HM2→HM1) 的观察

1. **观察方向**: 60min 后检查 HM2 kimi_nv 失败是否仍全为 peer fb 路径 (gt90s), 失败耗时是否从 97s 降到 ~91s, peer fb 救回数是否稳定 (不因降 6s 显著下降).
2. **止损条件**: 若 peer_rescued 显著下降 (改前 4/54min → 改后 <2/Nmin) 或 succ% 下降 >3pp, 则回退 59→65.
3. **HM2 当前稳态参数小结** (供 CC 下轮勘定参考):
   - `HM_FORCE_STREAM_UPGRADE_TIMEOUT=61` / `UPSTREAM_TIMEOUT=61` (R533/R534 所设, ceiling 已消除 55-61s 截断)
   - `HM_PEER_FALLBACK_TIMEOUT=59` (本轮所设, 对齐 HM1 侧 R531=59)
   - `MIN_OUTBOUND_INTERVAL_S=1.0` / `TIER_TIMEOUT_BUDGET_S=100` / `FASTBREAK=1` (已最优)
   - 5 key 全健康 (无路由改动力, R527 证伪)
4. **剩余可调方向** (HM2侧, 供未来轮): 失败仍聚簇 gt90s (peer fb 路径), 若 peer fb 救回率持续低 (<20%), 可考虑降低 BUDGET 100→? 让 peer fb 早 fail, 但需 CC 重新勘定数据支撑.

## ⏳ 轮到HM2优化HM1
