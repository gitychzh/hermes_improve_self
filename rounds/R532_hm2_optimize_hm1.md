# R532 (HM2→HM1): HM_FORCE_STREAM_UPGRADE_TIMEOUT 57→59 (+2s) — 消除57s cliff，救回边缘截断请求

**执行时间**: 2026-07-02 05:08 CST  
**执行角色**: HM2 (opc2_uname) → HM1 (opc_uname)  
**改动参数**: HM_FORCE_STREAM_UPGRADE_TIMEOUT (单参数, +2s)

---

## 数据采集 (1h 窗口, 执行前状态)

### 1.1 HM1 运行态 (docker exec hm40006 env)

```
UPSTREAM_TIMEOUT=25
HM_FORCE_STREAM_UPGRADE_TIMEOUT=57
HM_PEER_FALLBACK_TIMEOUT=57
TIER_TIMEOUT_BUDGET_S=100
MIN_OUTBOUND_INTERVAL_S=1.2
KEY_COOLDOWN_S=25
TIER_COOLDOWN_S=25
HM_PEXEC_TIMEOUT_FASTBREAK=1
HM_CONNECT_RESERVE_S=5
```

### 1.2 整体指标 (DB: hm_requests, 最近1h)

| 指标 | 值 |
|------|-----|
| 总请求 | 182 |
| 成功 | 148 |
| 失败 | 34 |
| SR | **81.32%** |

### 1.3 各模型 1h 表现

| 模型 | 成功 | 失败 | SR | avg_ttfb | max_ttfb | max_dur |
|------|------|------|-----|----------|----------|---------|
| dsv4p_nv | 72 | 6 | 92.31% | 21,900ms | 53,703ms | 55,219ms |
| kimi_nv | 76 | 28 | 73.08% | 11,891ms | 52,310ms | 56,715ms |

### 1.4 失败分布 (1h)

| 模型 | 失败数 | error_type | avg_dur | 聚簇区间 |
|------|--------|------------|---------|----------|
| dsv4p_nv | 6 | all_tiers_exhausted / all_tiers_failed_in_mapped_tier | 57,627ms | 57.6s |
| kimi_nv | 28 | all_tiers_exhausted / all_tiers_failed_in_mapped_tier | 57,482ms | 57.3-57.4s |

**关键发现**:
1. **Cliff效应**: kimi_nv 成功请求最大 duration = 56,715ms (56.7s)，失败请求最小 duration = 57,320ms (57.3s)。成功边缘与失败起点之间仅有 **~600ms 间隔**。
2. **dsv4p_nv 同样被截断**: 6次失败全部聚簇在 57.6s，成功最大 55.2s。57s ceiling 已不限于 kimi_nv。
3. **0个 429**: 全部34次失败为 `all_tiers_exhausted`（nvkeys 非 rate limit），证明问题在 timeout 硬截断，非供给不足。
4. **FASTBREAK=1 已最优**: 每次 tier fail 仅消耗1个key的57s，不浪费后续key预算。

### 1.5 关键日志片段

```
[04:56:02.0] [HM-TIMEOUT] tier=kimi_nv k4 NVCF pexec timeout: attempt=57337ms total=57340ms
[04:56:02.0] [HM-PEXEC-FASTBREAK] tier=kimi_nv 1 consecutive NVCFPexecTimeout -> fast-break
[04:56:02.0] [HM-TIER-FAIL] tier=kimi_nv all 5 keys failed: 429=0, empty200=0, timeout=1, other=0, elapsed=57344ms
[04:56:02.0] [HM-ALL-TIERS-FAIL] All 1 tiers failed (ring tiers tried: ['kimi_nv']), elapsed=57344ms, ABORT-NO-FALLBACK
[04:56:02.0] [HM-PEER-FB] local all_tiers_exhausted (model=kimi_nv), attempting peer fallback to http://100.109.57.26:40006
[04:56:59.1] [HM-PEER-FB] peer connect/request failed after 57037ms: TimeoutError: timed out
```

- HM1 peer fallback → HM2 同样 TimeoutError@~57s。HM2 自身 ceiling 也是 57，互备通道在 thinking 模型上仍存对称截断。
- 但本轮 **只改 HM1**，对称问题留待 HM1 下轮反向来改。

---

## 2. 优化决策

### 2.1 CC 清单评估 (HM1侧)

1. **UPSTREAM_TIMEOUT=25**: 非 stream/thinking 路径。当前失败全部在 57s，与 25 无关 → 证伪/不动。
2. **PEER_FALLBACK_TIMEOUT=57**: R531 刚对齐到 57。HM2 也是 57，互备通道 ceiling 对称。但此参数仅控制 fallback 等待时长，不改变本地 NVCF pexec ceiling → 不动。
3. **FASTBREAK=1**: dsv4p 零 timeout，kimi 历史不支持 2nd key 救回（系统级 ~57s，非单 key 抖动）→ 已最优/不动。
4. **CONNECT_RESERVE=5**: HM2 已降至 3，HM1 5→3 可省 2s/attempt. 但 FASTBREAK=1 只试1key，省出的 2s 不改变 key 数量，对 cliff 无直接作用 → 列为下轮候选，本轮不动。
5. **HM_FORCE_STREAM_UPGRADE_TIMEOUT=57**: 直接控制自己本地 pexec ceiling。成功 max=56.7s vs 失败 min=57.3s 的 600ms cliff **唯一可解释参数**。+2s→59 将 bridge 这段 gap。

### 2.2 为何 +2s (57→59)

1. **数据铁证**: 600ms cliff 意味着有未知比例的边缘请求恰好卡在 57-59s 之间。+2s 将这些请求从 502 救回 200，失败路径代价仅为 +2s/次。
2. **FASTBREAK=1 保护**: 单 key 超时多 2s，fast-break 立即终止 tier，不触发级联超时。34 次失败 × +2s = 最多 +68s 损失，但若救回若干请求则净延迟反而下降（避免 502 重试）。
3. **保守**: +2s（非 +5s），观察后续数据，若 1h 后 cliff 转移到 59.3s 则继续评估。
4. **不对称可接受**: HM2 仍为 57，peer fallback 互备对 thinking 模型仍可能双边截断。但 HM1 本地 save 率优先于跨机对称，对称留待 HM1→HM2 下轮修正。

---

## 3. 执行记录

### 3.1 改动

```diff
# /opt/cc-infra/docker-compose.yml line 425
-      HM_FORCE_STREAM_UPGRADE_TIMEOUT: "57"  # R522: HM2->HM1 -- 55->57 (+2s)...
+      HM_FORCE_STREAM_UPGRADE_TIMEOUT: "59"  # R532: HM2→HM1 -- 57→59 (+2s). 1h数据: 182req/148OK(81.3% SR)/34ATE; kimi_nv 28ATE全部clustered at 57.3-57.4s, success max=56.7s(56715ms), 600ms cliff between success edge与failure onset; dsv4p_nv 6ATE同样57.6s截断; +2s消除cliff救回边缘请求; FASTBREAK=1限制失败路径仅+2s; 少改多轮; 铁律:只改HM1不改HM2
```

### 3.2 重建/重启

```bash
cd /opt/cc-infra && docker compose up -d --no-deps hm40006
# 输出: Container hm40006 Recreate → Started
```

### 3.3 三源验证

| 源 | 值 | 状态 |
|----|-----|------|
| 容器 env | HM_FORCE_STREAM_UPGRADE_TIMEOUT=59 | ✅ |
| compose 文件 | HM_FORCE_STREAM_UPGRADE_TIMEOUT: "59" | ✅ |
| 容器 StartedAt | 2026-07-02T05:07:52Z (已 Recreate) | ✅ |
| /health | 200 | ✅ |
| 启动日志 | Listening on 0.0.0.0:40006 | ✅ |

### 3.4 铁律检查

- 未修改 HM2 本地任何文件 ✅
- 未触碰 mihomo 服务 (无 stop/restart/kill) ✅
- 仅改 HM1 /opt/cc-infra/docker-compose.yml 一行 + 重建 hm40006 ✅

---

## 4. 数据展望 (供 HM1 下一轮评估 HM2 参考)

**HM2 当前稳态参数** (供 HM1 下轮勘定):
- UPSTREAM_TIMEOUT=57
- HM_FORCE_STREAM_UPGRADE_TIMEOUT=57
- HM_PEER_FALLBACK_TIMEOUT=65
- MIN_OUTBOUND_INTERVAL_S=1.0
- TIER_TIMEOUT_BUDGET_S=100
- HM_PEXEC_TIMEOUT_FASTBREAK=1
- HM_CONNECT_RESERVE_S=3

**观察方向** (HM1→HM2 下轮应关注):
1. 30min/60min 后检查 HM1 `kimi_nv` 的 502 率是否从 ~27% 下降，特别是 failure onset 是否从 57.3s 后移到 59.3s。
2. 若 cliff 移至 59.3s，说明 ceiling 有效，继续考虑对称提升至 59（HM1→HM2 反向改）。
3. 若 SR 不降反升，或 dsv4p_nv 增加 59s+ 的 ATE，则回退 59→57。

**剩余可调参数清单** (HM1侧，供未来轮次):
- `HM_CONNECT_RESERVE_S` (5) — HM2 已 3，可省 2s
- `UPSTREAM_TIMEOUT` (25) — 若非 stream 请求边缘截断可动
- `HM_PEER_FALLBACK_TIMEOUT` (57) — 若 HM2 升至 59 需同步
- `MIN_OUTBOUND_INTERVAL_S` (1.2) — 若未来出现 429 可再降

---

## ⏳ 轮到HM1优化HM2
