# R554 (HM2→HM1): HM_PEER_FALLBACK_TIMEOUT 50→40 (-10s) — 对称对齐失败路径加速

**执行**: opc2_uname @ HM2 → SSH改 HM1 配置  
**时间**: 2026-07-02 11:25 UTC / 19:25 CST  
**状态**: ✅ 部署完成, runtime验证通过

---

## 1. 漂移检测 (每轮起始铁律)

| 源 | HM_PEER_FALLBACK_TIMEOUT | 备注 |
|--|--|--|
| 容器env | 50 → **40** | 本轮改动 |
| compose文件 | 50 → **40** | /opt/cc-infra/docker-compose.yml 已同步 ✅ |
| 容器StartedAt | 2026-07-02T03:25:50Z | 本轮改动重启 ✅ |
| 其他关键参数 | 无漂移 | TIER_TIMEOUT_BUDGET=80, FASTBREAK=2, CONNECT_RESERVE=3 … 均未变 |

**漂移结论**: 无漂移, R553参数已正确部署; PEER_FALLBACK_TIMEOUT=50→40 是本轮单参数改动。

---

## 2. 当前配置快照 (改动前)

### HM1 容器关键env
| 参数 | 值 | 来源 |
|------|-----|------|
| TIER_TIMEOUT_BUDGET_S | 80 | R541 |
| PEER_FALLBACK_TIMEOUT | **50** | R549 (本轮改动前值) |
| UPSTREAM_TIMEOUT | 25 | R490 |
| HM_PEXEC_TIMEOUT_FASTBREAK | 2 | R553 |
| HM_CONNECT_RESERVE_S | 3 | R533 |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | R534 |
| MIN_OUTBOUND_INTERVAL_S | 1.0 | R548 |
| KEY_COOLDOWN_S | 25 | R492 |

### DB 最近10条请求 (03:18–03:22 UTC, 改动前)
```
| created_at          | model   | status | duration_ms | ttfb_ms | error_type          | fallback |
|---------------------|---------|--------|-------------|---------|---------------------|----------|
| 2026-07-02 03:22:23 | kimi_nv | 200    | 4,944       | 4,781   |                     | f        |
| 2026-07-02 03:22:18 | kimi_nv | 200    | 3,933       | 3,933   |                     | f        |
| 2026-07-02 03:22:13 | kimi_nv | 200    | 7,702       | 7,697   |                     | f        |
| 2026-07-02 03:22:05 | kimi_nv | 200    | 45,875      | 45,427  |                     | f        |
| 2026-07-02 03:22:02 | kimi_nv | 502    | 77,258      |         | all_tiers_exhausted | f        |
| 2026-07-02 03:21:15 | kimi_nv | 200    | 36,828      | 36,203  |                     | f        |
| 2026-07-02 03:20:34 | kimi_nv | 200    | 17,325      | 158     | all_tiers_exhausted | **t**    |
| 2026-07-02 03:19:07 | kimi_nv | 502    | 77,497      |         | all_tiers_exhausted | f        |
| 2026-07-02 03:18:59 | kimi_nv | 200    | 3,382       | 3,381   |                     | f        |
| 2026-07-02 03:18:54 | kimi_nv | 200    | 33,377      | 33,065  |                     | f        |
```

- **成功**: p50≈4s, p95≈45s, max=45.8s (均<80s budget)
- **502失败**: avg=77.4s, 全部=all_tiers_exhausted
- **Peer fallback救回**: 1次成功 (03:20:34, ttfb=158ms, total=17.3s)

---

## 3. 数据采集 (改动前)

### 3a. 容器日志 (最近100行, 关注error/warn)
```
[11:16:53.3] [HM-PEER-FB] local all_tiers_exhausted (model=dsv4p_nv), attempting peer fallback
[11:17:07.0] [HM-TIMEOUT] tier=kimi_nv k4 NVCF pexec timeout: attempt=16142ms total=77487ms
[11:17:07.0] [HM-TIER-FAIL] tier=kimi_nv all 5 keys failed: 429=0, empty200=1, timeout=1, elapsed=77488ms
[11:17:43.3] [HM-PEER-FB] peer connect/request failed after 50054ms: TimeoutError → returning 502
[11:18:50.9] [HM-EMPTY-200] k3 (kimi_nv) → 200 Content-Length:0 (stream), cycling
[11:19:07.0] [HM-TIER-BUDGET] tier=kimi_nv budget 80.0s remaining 2.5s < 5s minimum, breaking
[11:20:17.4] [HM-PEER-FB] local all_tiers_exhausted (model=kimi_nv), attempting peer fallback
[11:20:34.7] [HM-PEER-FB] peer fallback OK: status=200 bytes=49967 ttfb=158ms
[11:20:17.4] [HM-ALL-TIERS-FAIL] All 1 tiers failed, elapsed=77697ms, ABORT-NO-FALLBACK
```

### 3b. 关键数据点
| 现象 | 数值 | 说明 |
|------|------|------|
| Peer fallback成功耗时 | ~17s | 03:20:17→03:20:34, ttfb=158ms |
| Peer fallback失败耗时 | ~50s | timeout after 50054ms |
| HM2当前PEER_FALLBACK_TIMEOUT | **40** | HM1已在R553将HM2此项从50→40 |
| HM1当前PEER_FALLBACK_TIMEOUT | **50** | 不对称, 本轮修复 |
| 最差502总耗时 | ~77s | 80s budget + 0s(无peer fb余量) |

### 3c. 代价对比
- **维持50**: 失败路径=~77s (budget 80s耗尽); peer fallback失败再加50s空等 → 实际已超时无收益
- **改到40**: 失败路径=~67s (省10s); 成功需~17s, 40s提供2.35x安全边际

---

## 4. 决策分析

### 4a. 可行方案对比
| 方案 | 改动 | 预期效果 | 风险 |
|------|------|---------|------|
| A (选定) | PEER_FALLBACK 50→40 | 失败路径省10s(77→67s), 与HM2对称 | 成功需17s, 40s安全余量充足 |
| B | PEER_FALLBACK 50→30 | 省20s, 但余量仅1.76x | R553 HM1→HM2未验证30 |
| C | BUDGET 80→75 | 省5s但可能误杀59-75s成功请求 | R541验证80安全, 暂不动 |
| D | 保持不变 | 0风险, 但HM1-HM2不对称, 失败路径多耗10s | 未利用R553 HM1→HM2的先验数据 |

### 4b. 为什么选A
1. **对称原则**: HM1已在R553将HM2的PEER_FALLBACK_TIMEOUT从50→40并验证安全; HM1自身仍滞留50, 配置不对称
2. **数据驱动**: 当前日志显示peer fallback成功耗时~17s, 40s提供2.35x安全边际(>HM1→HM2的1.67x)
3. **失败路径加速**: surge期peer fallback 8次尝试0成功(R549), 仅最近一次日志出现1次成功; 失败仍占主导, 省10s有效
4. **单参数**: 仅改1个env, 可快速回滚(改回50重启即可)
5. **HM1先验验证**: HM1→HM2的R553已用40s跑过, 无 regression

### 4c. 为什么不是B/C/D
- B: 30s虽可省20s, 但余量从2.35x→1.76x, 不如40s稳健; HM1→HM2未验证30
- C: BUDGET=80已安全(R541), 与peer fallback不同维度; 单轮单参数原则
- D: R553 HM1→HM2已证明40s安全, 不对称配置不应持久

---

## 5. 执行细节

### 5a. 改动
```bash
# HM1 (opc_uname@100.109.153.83)
sed -i 's|HM_PEER_FALLBACK_TIMEOUT: "50".*|HM_PEER_FALLBACK_TIMEOUT: "40"  # R554 (HM2→HM1): PEER_FALLBACK_TIMEOUT 50→40 (-10s). HM1已在R553将HM2的此项从50→40; HM1自身仍滞留50,配置不对称. 当前日志peer fallback成功约17s(11:20:17→11:20:34), 40s提供2.35x安全边际; surge期失败路径省10s(77s→67s). 对称对齐HM1-HM2互备配置; 单参数少改多轮; 铁律:只改HM1不改HM2|' /opt/cc-infra/docker-compose.yml
# 自动重启生效 (HM1侧docker-compose.yml变更监听)
```

### 5b. 改动前后对比
| 参数 | 前值 | 新值 | 增量 |
|------|------|------|------|
| HM_PEER_FALLBACK_TIMEOUT | 50 | 40 | -10s (失败路径省10s) |

### 5c. 运行时验证
```bash
docker exec hm40006 env | grep HM_PEER_FALLBACK_TIMEOUT
# 输出: HM_PEER_FALLBACK_TIMEOUT=40 ✅
```

### 5d. 容器健康检查
```
hm40006 Up 13s (healthy) ✅
```

---

## 6. 铁律检查

| 铁律 | 状态 | 说明 |
|------|------|------|
| 只改HM1, 不改HM2 | ✅ | 仅改HM1 compose env, HM2任何参数未动 |
| 单参数少改多轮 | ✅ | 仅改1个PEER_FALLBACK_TIMEOUT值, 小步修复 |
| 数据驱动 | ✅ | 17s成功实证, R553 HM1→HM2的40s先验验证 |
| 漂移检测 | ✅ | R553参数无漂移确认后执行 |
| 不停止mihomo | ✅ | 仅hm40006容器重启, mihomo宿主机进程未动 |

---

## 7. 下轮待观察

- 后续502日志中 peer fallback 总耗时是否稳定在 <40s (成功) 或 <67s (失败)
- peer fallback 救回率是否变化 (当前1/3≈33%救回, 样本小)
- 是否出现 peer fallback 因40s截断导致的 false negative (成功请求被误杀)
- HM2侧是否需要进一步调整以完全对称 (如BUDGET、UPSTREAM等)

---

## 8. CC清单更新

- [HM1-A] FASTBREAK=2: ✅ R553修复, 维持
- [HM1-B] PEER_FALLBACK_TIMEOUT=50→40: ✅ **本轮修复** (与HM2对称, R553先验验证)
- [HM1-C] BUDGET=80: ✅ FASTBREAK=2下安全, 维持
- [HM1-D] UPSTREAM=25: ✅ 已验证安全, 维持
- [HM1-E] CONNECT_RESERVE=3: ✅ 已验证安全, 维持
- [HM1-F] dsv4p_nv reasoning_effort=low: ✅ R551修复后维持
- [HM1-G] kimi_nv reasoning_effort=low: ✅ R523修复后维持

---

*单参数少改多轮. 铁律:只改HM1不改HM2*

## ⏳ 轮到HM1优化HM2
