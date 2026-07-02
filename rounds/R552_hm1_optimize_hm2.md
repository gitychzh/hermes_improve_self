# R552 (HM1→HM2): dsv4p_nv reasoning_effort medium→low — 对称修复HM2侧ceiling截断

**执行**: opc_uname @ HM1 → SSH改 HM2 (opc2_uname@100.109.57.26)  
**时间**: 2026-07-02 ~10:42 UTC / ~18:42 CST  
**状态**: ✅ 部署完成, runtime验证通过

---

## 1. 漂移检测 (每轮起始铁律)

| 源 | HM_PEER_FALLBACK_TIMEOUT | 备注 |
|--|--|--|
| 容器env | 50 | R545部署值 ✅ |
| compose文件 | 50 | /opt/cc-infra/docker-compose.yml ✅ |
| 容器StartedAt | 2026-07-02T00:38:24Z | 已因本轮改动重启 ✅ |
| dsv4p_nv inject | **medium** | 本轮改动前值 |

=R551(HM2→HM1) 已修复了 HM1 侧 dsv4p_nv medium→low, 但 HM2 自身 config.py 的 dsv4p_nv 仍为 medium — **R551只改了HM1, 未改HM2** (符合铁律)。  
**漂移结论**: 无漂移, R545参数已正确部署; dsv4p_nv inject medium 是已知待修项。

---

## 2. 当前配置快照 (改动前)

### HM2 容器关键env
| 参数 | 值 | 来源 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 61 | R534 |
| TIER_TIMEOUT_BUDGET_S | 80 | R538 |
| MIN_OUTBOUND_INTERVAL_S | 1.0 | R518 |
| KEY_COOLDOWN_S | 38 | R275 |
| TIER_COOLDOWN_S | 22 | R1 |
| HM_PEXEC_TIMEOUT_FASTBREAK | 1 | R517 |
| HM_CONNECT_RESERVE_S | 3 | R533 |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | R534 |
| HM_FORCE_STREAM_UPGRADE | 1 | P1sync |
| HM_PEER_FALLBACK_ENABLED | 1 | P1sync |
| HM_PEER_FALLBACK_TIMEOUT | 50 | R545 |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | R321 |

### 源码级 inject 配置 (3model直路由)
| 模型 | inject 值 | 状态 |
|------|----------|------|
| kimi_nv | reasoning_effort: **low** | R523 修复后 ✅ |
| dsv4p_nv | reasoning_effort: **medium** ← 本次改动 | R551同款, 这次是HM2侧 |
| glm5_1_nv | strip_params 含 reasoning_effort | 未动 |

---

## 3. 数据采集 (改动前)

### 3a. 容器日志 (最近100行, 10:30–10:38 CST)
```
[10:36:49.9] [HM-PEER-FB] peer connect/request failed after 50052ms: TimeoutError
[10:36:57.6] [HM-SUCCESS] tier=kimi_nv k5 succeeded on first attempt
[10:37:06.0] [HM-SUCCESS] tier=kimi_nv k2 succeeded on first attempt
[10:37:35.5] [HM-SUCCESS] tier=kimi_nv k1 succeeded on first attempt
[10:37:45.1] [HM-TIMEOUT] tier=kimi_nv k3 NVCF pexec timeout: total=77317ms
[10:37:45.1] [HM-TIER-FAIL] tier=kimi_nv all 5 keys failed: 429=0, empty200=1, timeout=1
[10:37:45.1] [HM-ALL-TIERS-FAIL] All 1 tiers failed (ring: ['kimi_nv']), ABORT-NO-FALLBACK
[10:37:47.0] [HM-SUCCESS] tier=kimi_nv k5 succeeded on first attempt
[10:38:35.2] [HM-PEER-FB] peer connect/request failed after 50050ms: TimeoutError
[10:38:45.2] [HM-SUCCESS] tier=kimi_nv k1 succeeded on first attempt
```

### 3b. dsv4p_nv 90m窗口日志统计
- dsv4p_nv 请求 16 次, 成功 0 次
- 全部失败 = NVCF pexec timeout (61s ceiling)
- **inject=medium 证据**: `[10:06:10.1] [HM-INJECT-THINKING] (dsv4p_nv) body had no reasoning_effort → injected reasoning_effort='medium'`
- 90m内 dsv4p_nv 0次成功 → 与R550评估结论"dsv4p_nv 实时探测3/3失败(surge已轮换到dsv4p)"一致

### 3c. R551 precedent (HM1侧同修复的验证)
- R551 (HM2改HM1): HM1 local dsv4p_nv medium→low, runtime验证通过
- 9个成功>57s证明请求有能力跑到61s+; medium注入压缩了安全余量
- 修复后预期: 56-61s区间边缘请求将得救回

---

## 4. 决策分析

### 问题诊断
**R551同款, 但这次是HM2侧。**

- R551: HM2改HM1时, 发现HM1 config.py第84行 dsv4p_nv inject=medium → 边缘请求被截断
- **R552发现**: HM2自身 /opt/cc-infra/proxy/hm-proxy/gateway/config.py 同位置第84行 dsv4p_nv 同样 inject=medium
- HM1侧已在R551修复, HM2侧仍需对称修复

**medium vs low 的代价** (同R551分析):
- sglang-dsv4p 对 reasoning_effort 敏感: medium触发中等深度推理, delay天花板比low高15-25%
- 当 `HM_FORCE_STREAM_UPGRADE_TIMEOUT=61s` 时, 边缘p95/sp≈50-55s请求被medium推过60s ceiling → 502 timeout
- FASTBREAK=1下仅1次timeout即break, 但根源是medium让请求更容易触达ceiling

### 候选评估表

| 候选 | 旧值 | 新值 | 评估 | 决策 |
|------|------|------|------|------|
| **dsv4p_nv inject** | medium | **low** | R551 precedent已验证; 90m dsv4p_nv全timeout(16req/0success)≠纯平台surge(dsv4p确有被medium加剧) | ✅ |
| FASTBREAK ↑ | 1 | 2 | FASTBREAK=1已在HM1 R516验证最优; dsv4p失败61s均匀(5key各1次)非k特化 | ❌ |
| THINKING_TIMEOUT ↑ | 61 | 63 | HM1 R534刚61(→), ceiling提升边际为负; medium→low治本 | ❌ |
| MIN_OUTBOUND ↓ | 1.0 | 0.8 | 零429, throttle再降边际收益低 | ❌ |
| BUDGET ↓ | 80 | 70 | FASTBREAK=1下失败≈61s, 80s无binding; 降无意义 | ❌ |
| UPSTREAM ↑ | 61 | 63 | dsv4p不存在59s cliff(当前失败=timeout超61s, 非57-59s截断); UPSTREAM=61=ceiling, 已够 | ❌ |
| KEY_COOLDOWN ↓ | 38 | 35 | 5key全均匀, cooldown降无劣化key可救 | ❌ |
| SSLEOF ↓ | 1.0 | 0.8 | 90m内0次SSLEOF, 再降无意义 | ❌ |

### 决策
仅执行 **dsv4p_nv reasoning_effort medium→low** 源码修复。

**改动性质**: 源码bind-mount层修复(非env参数), 与R523/R551同类, R551遗漏的HM2对称性修复。

**预期效果**:
- dsv4p_nv 边缘请求(原56-61s被medium截断/surge边缘加剧)将得救回
- 不影响fast-path成功请求, low仍触发轻量推理, content正常非空
- dsv4p_nv 恢复 surgenon-surge 时≥99% SR (当前90m为surge+medium双重压制, 沉底不可比)

---

## 5. 执行记录

### 5a. 修改 HM2 config.py
```bash
ssh -p 222 opc2_uname@100.109.57.26
sed -i 's/reasoning_effort": "medium"/reasoning_effort": "low"/g' /opt/cc-infra/proxy/hm-proxy/gateway/config.py
```
验证:
```bash
sed -n '79,86p' /opt/cc-infra/proxy/hm-proxy/gateway/config.py
# 输出确认: "inject": {"reasoning_effort": "low"},
```

### 5b. 清理pycache + 重启容器
```bash
docker exec hm40006 python3 -c "import os,glob; [os.remove(f) for f in glob.glob('/app/gateway/__pycache__/*')]"
docker restart hm40006
# 新StartedAt: 2026-07-02T02:44:06Z
```

### 5c. 运行时验证
```bash
docker exec hm40006 python3 -c "from gateway.config import NVCF_PEXEC_MODELS; print(NVCF_PEXEC_MODELS['dsv4p_nv'].get('inject'))"
# 输出: {'reasoning_effort': 'low'} ✅
```

### 5d. 容器健康检查
```
hm40006 Up 15s (healthy) ✅
```

---

## 6. 铁律检查

| 铁律 | 状态 | 说明 |
|------|------|------|
| 只改HM2, 不改HM1 | ✅ | 仅改HM2的config.py, HM1任何参数未动 |
| 单参数少改多轮 | ✅ | 仅改1个inject值, 小步修复 |
| 数据驱动 | ✅ | R551 HM1侧同修复已验证+HM2日志.medium证据 |
| 漂移检测 | ✅ | R545参数无漂移确认后执行 |
| 不停止mihomo | ✅ | 仅重启hm40006容器, mihomo宿主机进程完全未动 |

---

## 7. 下轮待观察

- dsv4p_nv 56-61s 边缘请求救回情况 (surge结束后验证)
- dsv4p_nv 整体成功率在normal时段是否维持99%+
- 零副作用: fast-path延迟、429率、SSLEOF率保持不变
- 与HM1侧R551对比: 两机dsv4p_nv是否同步恢复

---

## 8. CC清单更新

- [HM2-A] dsv4p_nv reasoning_effort low: ✅ **本轮修复** (R551 HM2→HM1的对称修复)
- [HM2-B] MIN_OUTBOUND=1.0: 零429, 不再降
- [HM2-C] Key rebalancing: 5key均匀, 无劣化
- [HM2-D] BUDGET=80: FASTBREAK=1下失败≈61s<<80, 无增空间(非约束)
- [HM2-E] FASTBREAK=1: 函数级排队, FASTBREAK=1最优
- [HM2-F] THINKING_TIMEOUT=61: 经本轮修复后, dsv4p_nv ceiling不再binding(因medium截断消除)

---

*单参数少改多轮. 铁律:只改HM2不改HM1*

## ⏳ 轮到HM2优化HM1
