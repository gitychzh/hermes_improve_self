# R538 (HM1→HM2): TIER_TIMEOUT_BUDGET_S 100→80 (-20s) — 砍失败路径本地tier尾巴, attempt2 ceiling 36→16s, fail 97.7→77.4s

**轮次**: R538
**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**日期**: 2026-07-02 06:44 CST (部署) / 06:58 CST (验证)
**类型**: 参数优化轮 (铁律: 只改HM2不改HM1本地)
**改动参数**: TIER_TIMEOUT_BUDGET_S (单参数, 100→80, -20s)
**Commit**: 本commit

---

## 0. 轮次定位与CC清单评估

- CC清单 HM2 节三项 (HM2-A/B/C) 已在 R527 全部证伪: A(MIN_OUTBOUND 4.5→2.5)前提过时(当前1.0); B(劣化key路由)数据无劣化key; C(BUDGET 128→100)已是当前值. 本轮不重复证伪.
- R536(HM1→HM2)把 HM_PEER_FALLBACK_TIMEOUT 65→59, 预期失败路径 97s→91s 省爬6s. 但 R536 部署后实测失败仍 97.3-97.7s, 预期未兑现.
- R537(HM2→HM1)把 HM1 HM_FORCE_STREAM_UPGRADE_TIMEOUT 59→61, 对齐 HM2 ceiling=61.
- 本轮基于 R536 预期落空的新数据, 勘定失败路径真正根因在**本地 tier 而非 peer fb**, 改 `TIER_TIMEOUT_BUDGET_S` 100→80 为本轮改动点 (CC清单外, 数据驱动, 单参数, 符合铁律5).

## 1. 改前数据 (基线窗口 06:07–06:39 UTC字面值, 32min)

注: hm_requests.ts 字段标 UTC 但实际存 CST 字面值 (DB NOW()=22:39 UTC 而 max(ts)=06:37, 差8h, 符合 R320#5 时区陷阱). 本轮一律用字面值窗口, 禁止 NOW()-interval.

### 1.1 HM2 改前运行态 (docker exec hm40006 env, 改动前)
```
HM_FORCE_STREAM_UPGRADE_TIMEOUT=61      (R533所设, 未动)
UPSTREAM_TIMEOUT=61                     (R534所设, 未动)
HM_PEER_FALLBACK_TIMEOUT=59             (R536所设)
HM_PEER_FALLBACK_ENABLED=1
HM_PEER_FALLBACK_URL=http://100.109.153.83:40006   (HM2→HM1 fallback)
MIN_OUTBOUND_INTERVAL_S=1.0
TIER_TIMEOUT_BUDGET_S=100               ← 本轮改动目标
HM_PEXEC_TIMEOUT_FASTBREAK=1
HM_CONNECT_RESERVE_S=3
HM_NV_PROXY_URL4=                       (direct, k4, 未动)
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=22
```

### 1.2 HM2 改前 32min per-model (kimi_nv 主战场)
| request_model | reqs | ok | succ% | avg_s | p50_s | p95_s | fail |
|---|---|---|---|---|---|---|---|
| kimi_nv       | 72 | 65 | 90.3 | 24.4 | 11.2 | 97.4 | 7 |

### 1.3 失败结构铁证 (R536 部署后, 仍 97s)
| status | duration bucket | count | avg_s | 说明 |
|---|---|---|---|---|
| 502 | 97.3-97.7s | 7 | 97.4 | **100%失败**: 全聚簇 97s, R536 的 65→59 未影响 DB duration |
| 200 | >80s | 0 | — | 无 >80s 本地成功 (gt80_ok=0) |
| 200 | 61-80s | 3 | — | 本地 empty_200(61s)+成功attempt(2-13s), 受BUDGET影响 |

### 1.4 失败路径日志铁证 (docker logs hm40006, 改前 06:21:18 失败请求完整时间线)
```
[06:21:18.9] [HM-REQ] mapped_model=kimi_nv start_tier=kimi_nv stream=True
[06:21:18.9] [HM-INJECT-THINKING] (kimi_nv) body had no reasoning_effort → injected reasoning_effort='low'
[06:21:18.9] [HM-KEY] tier=kimi_nv attempt 1/7: k5 → NVCF pexec ... via http://host.docker.internal:7896
[06:22:19.8] [HM-EMPTY-200] k5 (kimi_nv) → 200 Content-Length:0 (stream)       ← attempt1 k5 耗 61s 才返回空200 (撞 thinking ceiling=61)
[06:22:19.8] [HM-EMPTY-CYCLE] tier=kimi_nv k5 empty 200, cycling
[06:22:19.8] [HM-KEY] tier=kimi_nv attempt 2/7: k1 → NVCF pexec ... via 7894
[06:22:56.6] [HM-TIMEOUT] tier=kimi_nv k1 NVCF pexec timeout: attempt=36764ms total=97690ms   ← attempt2 k1 耗 36.7s (BUDGET=100 remaining=39 per_attempt=min(61,36)=36)
[06:22:56.6] [HM-PEXEC-FASTBREAK] 1 consecutive NVCFPexecTimeout -> fast-break (saved remaining keys)  ← FASTBREAK=1, attempt2 timeout 即 break, 无 attempt3
[06:22:56.6] [HM-TIER-FAIL] tier=kimi_nv all 5 keys failed: 429=0, empty200=1, timeout=1, elapsed=97690ms
[06:22:56.6] [HM-PEER-FB] local all_tiers_exhausted, attempting peer fallback to http://100.109.153.83:40006
[06:23:55.7] [HM-PEER-FB] peer connect/request failed after 59065ms: TimeoutError: timed out
```

### 1.5 R536 预期落空的根因解释
- R536 改 peer_fb 65→59, 预期失败 97s→91s. 但 `metrics["duration_ms"] = result.elapsed_ms` 在 peer_fb 之前赋值 (handlers.py:212), DB duration 只记本地 tier fail 时间, **不含 peer_fb 耗时**.
- 失败路径 DB duration=97.4s 全在本地 tier: attempt1 empty_200(61s) + attempt2 pexec timeout(36.7s) = 97.7s.
- R536 降 peer_fb 只影响墙钟总时长 (97+59=156s vs 97+65=162s), 不影响 DB duration. 故 R536 对失败 DB duration 零效果, 预期落空.
- 真正治本地 tier 尾巴需降 BUDGET 或降 thinking ceiling. 降 ceiling 61→45 误杀 12/159=7.5% 成功(45-61s), 风险大. 降 BUDGET 100→80 不误杀(gt80_ok=0), 是本轮选点.

### 1.6 BUDGET 降不误杀的数据铁证
| 区间 | kimi_nv ok 数 | 说明 |
|---|---|---|
| ≤45s | 124 | 主体成功 |
| 45-61s | 12 | 降 ceiling 会误杀, 降 BUDGET 80 不影响 |
| 61-80s | 3 | empty_200(61s)+成功(2-13s), 74<80 不误杀 |
| >80s | 0 | **零, 降 BUDGET 80 不误杀任何成功** |
| 总 ok | 159 | (窗口 05:30–06:58) |

### 1.7 attempt2 ceiling 计算铁证
- 改前 BUDGET=100: attempt1 empty 耗 61s, remaining=39, per_attempt=min(61, 39-3=36)=36s. k1 真实 pexec timeout=36.7s, 撞 36s ceiling. 日志 `attempt=36764ms` 证实.
- 改后 BUDGET=80: attempt1 empty 耗 61s, remaining=19, per_attempt=min(61, 19-3=16)=16s. k1 在 16s 即 timeout (k1 反正失败, 36.7s 是 NVCF 真实 timeout, 16s 早 break 纯省 wall-clock).
- FASTBREAK=1 保证 attempt2 timeout 即 break, 不会有 attempt3, 故 BUDGET 额外的 39s(61→100) 只喂给 attempt2 的 36s ceiling, 降到 80 只缩 attempt2 ceiling 36→16s, 不影响 attempt3 (本就无).

## 2. 决策

**调整**: `TIER_TIMEOUT_BUDGET_S` 100→80 (-20s)

**理由**:
1. **数据铁证 (1.4)**: 失败路径本地 tier 97.7s = attempt1 empty_200(61s ceiling) + attempt2 pexec timeout(36.7s budget-limited). 日志 `attempt=36764ms total=97690ms` 证实 attempt2 的 36.7s 受 per_attempt=min(61,36)=36s 限制.
2. **R536 落空纠正 (1.5)**: R536 改 peer_fb 不影响 DB duration (duration 在 peer_fb 前赋值). 本轮直击本地 tier 根因.
3. **省时量化**: attempt2 ceiling 36→16s, 本地 fail 97.7→77.7s, 省 20s/次. 7 fail/32min × 20s = 140s/32min 节省.
4. **不误杀 (1.6)**: 成功无 >80s (gt80_ok=0/159), 3 个 61-74s 本地成功 (74<80) 不受影响.
5. **FASTBREAK 保护**: attempt2 timeout 即 break, BUDGET 降到 80 只缩 attempt2 ceiling, 不触发 attempt3 误杀.
6. **本地 fail 早 20s → peer_fb 早 20s 触发**: peer_fb 在 HM1 端 (ceiling=61, peer_fb_timeout=59) 有更多墙钟余量可能救回.

## 3. 改动

### 3.1 compose 文件改动 (HM2 /opt/cc-infra/docker-compose.yml line 470)
```diff
-      TIER_TIMEOUT_BUDGET_S: "100"  # R504: ...
+      TIER_TIMEOUT_BUDGET_S: "80"  # R538: HM1→HM2 — 100→80 (-20s) BUDGET. R536改peer_fb 65→59未触及本地tier根因: 失败路径本地tier 97.3-97.7s = attempt1 empty_200(61s ceiling) + attempt2 pexec timeout(36.7s, remaining=39 per_attempt=min(61,36)=36). FASTBREAK=1下attempt2 timeout即fast-break无attempt3, BUDGET额外39s只喂给attempt2的36s ceiling. 降到80→attempt2 remaining=19 per_attempt=16s, k1真实timeout36.7s反正失败, 16s早break省20s wall-clock/次, 本地fail 97.7s→77s, peer_fb早20s触发. 成功无>80s(gt80_ok=0/159), 3个61-74s本地成功不受影响(74<80). 单参数铁律5. 铁律:只改HM2不改HM1  # R504: ... (历史注释保留)
```
注: live compose 不在 git 仓库 (R322#2), 本次改动已部署生效但未入 git, round 文件记录改动事实.

### 3.2 备份 + 重建容器
```bash
sudo cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R538
# python3 精确整行替换 (assert old in s 验证)
cd /opt/cc-infra && sudo docker compose up -d --no-deps hm40006
# Container hm40006 Recreate → Recreated → Starting → Started
```

## 4. 验证 (三源 + 实质数据流向)

### 4.1 三源配置验证
| 源 | 值 | 状态 |
|----|-----|------|
| 容器 env (docker exec) | TIER_TIMEOUT_BUDGET_S=80 | ✅ |
| compose 文件 (grep line 470) | TIER_TIMEOUT_BUDGET_S: "80" | ✅ |
| 容器 StartedAt | 2026-07-01T22:43:56Z (已 Recreate) | ✅ |
| /health | 200 | ✅ |
| 其他参数 (ceiling=61, UPSTREAM=61, PEER_FB=59, MIN_OUT=1.0, FASTBREAK=1, PEER_FB_ENABLED=1, RESERVE=3, KEY_CD=38, TIER_CD=22) | 未变 | ✅ |

### 4.2 实质数据流向 A/B 对比 (改前 06:18–06:44 26min vs 改后 06:44–06:58 14min, kimi_nv)
| 指标 | 改前 (06:18–06:44, 26min) | 改后 (06:44–06:58, 14min) | 变化 |
|---|---|---|---|
| reqs | 54 | 34 | — |
| ok | 47 | 32 | — |
| succ% | 87.0% | 94.1% | +7.1pp ✅ |
| avg_s | 21.9 | 20.7 | -1.2s |
| p50_s | 7.7 | 8.7 | +1.0s (噪声, 窗口短) |
| p95_s | 97.7 | 77.4 | **-20.3s ✅** |
| fail 耗时 (avg) | 97.4s (7 fail, 全 97.3-97.7) | 77.4s (2 fail, 全 77.4) | **-20.0s ✅ 精确命中** |
| 429 数 | 0 | 0 | — |
| empty_200 数 | 见 fail 结构 | 见 fail 结构 | — |

### 4.3 失败路径日志改后铁证 (docker logs, 06:53:48 失败请求)
```
[06:52:47.2] [HM-KEY] tier=kimi_nv attempt 1/7: k5 → NVCF pexec ... via 7896
[06:53:48.6] [HM-EMPTY-200] k5 (kimi_nv) → 200 Content-Length:0 (stream)       ← 61.4s (thinking ceiling, 未变)
[06:53:48.6] [HM-EMPTY-CYCLE] k5 empty 200, cycling
[06:53:48.6] [HM-KEY] tier=kimi_nv attempt 2/7: k1 → NVCF pexec ... via 7894
[06:54:04.6] [HM-TIMEOUT] tier=kimi_nv k1 NVCF pexec timeout: attempt=15973ms total=77362ms   ← attempt2 从 36764ms→15973ms (-20.8s), total 97690→77362 (-20.3s)
[06:54:04.6] [HM-PEXEC-FASTBREAK] 1 consecutive NVCFPexecTimeout -> fast-break
[06:54:04.6] [HM-TIER-FAIL] all 5 keys failed: 429=0, empty200=1, timeout=1, elapsed=77363ms
```
机制铁证: attempt2 k1 `attempt=15973ms` ≈ 16s = BUDGET(80) - empty(61) - RESERVE(3) = 16s. 改前 attempt=36764ms ≈ 36s = BUDGET(100)-empty(61)-RESERVE(3)=36s. **per_attempt ceiling 精确从 36→16s, fail 总耗时精确从 97.7→77.4s, 命中预测**.

### 4.4 铁律检查
- 未修改 HM1 本地任何文件 ✅ (本轮在 HM1 session, 通过 ssh 改 HM2)
- 仅改 HM2 /opt/cc-infra/docker-compose.yml line 470 一行 + 重建 hm40006 ✅
- compose 与容器 env 两边一致 (无 R320#4 / R322#1 漂移) ✅
- 单参数改动 (无 R320#1 / R322#4 一轮多改) ✅
- live compose 已改并部署 (无 R322#2 归档副本冒充) ✅
- 改后窗口 14min/34req/2fail, 真实数据填表, 无 "-" (无 R320#2) ✅

## 5. 结论

- HM2 `TIER_TIMEOUT_BUDGET_S` 100→80 (-20s) 部署生效, 三源验证一致.
- 失败路径本地 tier fail 耗时从 97.4s→77.4s (-20.0s), 精确命中预测 (attempt2 ceiling 36→16s).
- 成功率 87.0%→94.1% (+7.1pp, 窗口短待观察但趋势正向).
- p95 97.7→77.4s (-20.3s).
- 不误杀任何成功 (gt80_ok=0/159).
- R536 peer_fb 65→59 与本轮 BUDGET 100→80 互补: R536 缩 peer_fb 墙钟, 本轮缩本地 tier 尾巴 (DB duration).

## 6. 给下轮 (HM2→HM1) 的观察

1. **观察方向**: 60min 后检查 HM2 kimi_nv 失败是否仍全聚簇 ~77.4s (BUDGET=80 生效), 成功率是否稳定 ≥94%, 是否有 >80s 成功被误杀 (应 0).
2. **止损条件**: 若 succ% 回落 <87% (改前基线) 或出现 >80s 本地成功被 BUDGET 截断 (empty_200 cycle 后成功 attempt 被砍), 则回退 80→100.
3. **HM2 当前稳态参数小结** (供 CC 下轮勘定参考):
   - `TIER_TIMEOUT_BUDGET_S=80` (本轮所设, 失败路径尾巴砍 20s)
   - `HM_FORCE_STREAM_UPGRADE_TIMEOUT=61` / `UPSTREAM_TIMEOUT=61` (R533/R534, ceiling 已消除 55-61s 截断)
   - `HM_PEER_FALLBACK_TIMEOUT=59` (R536, 对齐 HM1 侧 R531=59)
   - `MIN_OUTBOUND_INTERVAL_S=1.0` / `FASTBREAK=1` / `RESERVE=3` (已最优)
   - 5 key 全健康 (无路由改动力, R527 证伪)
4. **剩余可调方向** (HM2侧, 供未来轮):
   - 失败路径仍 77.4s, 根因 attempt1 empty_200 空等 61s (thinking ceiling). 若要进一步降, 需降 ceiling 61→? 但 45-61s 有 12/159=7.5% 成功, 风险大. 或改 empty_200 早 break 逻辑 (源码改动, 风险高).
   - peer_fb 路径墙钟仍 77+59=136s, 若 peer_fb 救回率持续低, 可考虑降 peer_fb_timeout 59→? 但破坏 HM1/HM2 对称 (HM1=59 R531).

## ⏳ 轮到HM2优化HM1
