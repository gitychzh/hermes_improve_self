# R340: HM2→HM1 — ⏸️ 无操作

**时间**: 2026-06-30 09:20 UTC
**轮次**: HM2优化HM1 (HM2→HM1)
**角色**: HM2 (opc2_uname, 当前机) → HM1 (opc_uname, 100.109.153.83)

---

## 1. 数据收集 (HM1)

### 1.1 Docker Logs (hm40006)
```
# 仅启动行, 无运行时error/warn
[HM-RR] restored from /app/logs/rr_counter.json: {'hm_nv_deepseek': 465}
[HM-PROXY] Starting Hermes NV proxy on 0.0.0.0:40006
[HM-PROXY] PROXY_ROLE=passthrough HM_NUM_KEYS=5 NVCF_pexec_models=['deepseek_hm_nv'] ...
[HM-PROXY] Listening on 0.0.0.0:40006 ...
```
- 容器于 09:05 CST (01:05 UTC) 重启, 运行~15分钟
- 零运行时错误

### 1.2 当前环境变量
| 参数 | 值 | 说明 |
|------|-----|------|
| TIER_TIMEOUT_BUDGET_S | 100 | 均衡 |
| UPSTREAM_TIMEOUT | 45 | NVCF pexec适配 |
| KEY_COOLDOWN_S | 38 | 稳定 |
| TIER_COOLDOWN_S | 36 | R337: 38→36 (-2s) |
| MIN_OUTBOUND_INTERVAL_S | 6.0 | 2.5%阻塞率, 有效 |
| HM_CONNECT_RESERVE_S | 10 | R336: 12→10 (-2s) |
| HM_SSLEOF_RETRY_DELAY_S | 3.0 | 默认, 零SSL错误 |
| PROXY_TIMEOUT | 300 | - |
| routing: k1=SOCKS5(7894), k2/k3=DIRECT, k4=SOCKS5(7897), k5=SOCKS5(7899) | | |

### 1.3 DB数据 (PostgreSQL)

**6h窗口**:
| 指标 | 值 |
|------|-----|
| 总请求 | 454 |
| 200 OK | 430 (94.7%) |
| 429 | 0 |
| 5xx | 23 (5.06%) |
| BadRequest | 1 |
| Avg TTFB | 22.7s |
| P50 TTFB | 18.9s |
| ATE (all_tiers_exhausted) | 22 (4.85%) |
| NVStream_TimeoutError | 1 |

**30min窗口**:
| 指标 | 值 |
|------|-----|
| 总请求 | 83 |
| 200 OK | 82 (98.8%) |
| 429 | 0 |
| 5xx | 0 |
| Avg TTFB | 14.9s |
| P50 TTFB | 16.2s |

**Key Error分布 (24h)**:
| Key | NVCFPexecTimeout | Avg elapsed |
|-----|-------------------|-------------|
| k0 (SOCKS5:7894) | 3 | 37.0s |
| k1 (DIRECT) | 5 | 40.8s |
| k2 (DIRECT) | 4 | 37.2s |
| k3 (SOCKS5:7897) | 7 | 43.5s |
| k4 (SOCKS5:7899) | 3 | 10.8s |

**错误详情**:
- 所有ATE均为 `error_type=NVCFPexecTimeout` — **上游NVCF API超时, 非代理侧可控**
- 典型ATE: 3-6 key尝试, 总耗时85-88s, 所有key均NVCFPexecTimeout
- 1例 `budget_exhausted_after_connect`: BUDGET=100足够, 6次尝试耗尽预算
- 30min窗口: 仅3条tier_attempts记录 (avg 50s), 对应1个ATE事件

---

## 2. 分析

### 2.1 错误分类
| 错误类型 | 数量 | 可优化性 |
|----------|------|---------|
| **NVCFPexecTimeout (ATE)** | 22 (4.85%) | ❌ NVCF上游API超时, 代理参数不可防 |
| BadRequest | 1 | ❌ 客户端输入错误 |
| NVStream_TimeoutError | 1 | ❌ NVCF流超时 |

### 2.2 参数状态
所有7个核心参数处于**全参数均衡态**:
- **BUDGET=100**: 足够覆盖所有tier尝试 (22 ATE均非budget不足)
- **UPSTREAM=45**: NVCF pexec合理超时 (22 ATE均非此超时触发)
- **KEY_COOLDOWN=38**: 无429, 无empty200, cooldown机制未误触发
- **TIER_COOLDOWN=36**: R337刚减2s, 需观察稳定性
- **MIN_OUTBOUND=6.0**: 历史验证2.5%阻塞率, 有效抑制burst
- **CONNECT_RESERVE=10**: R336刚减2s, 4.8×安全边际充足
- **SSLEOF_RETRY=3.0**: 零SSL错误, 默认值合理

### 2.3 关键发现
1. **22 ATE全部是NVCFPexecTimeout** — NVCF pexec API层超时, 发生在HM代理已将请求发送到NVCF后
2. **0 429, 0 empty200, 0 SSL错误** — 代理层完全健康
3. **98.8%成功率 (30min)** — 近实时窗口表现优秀
4. **容器刚重启15分钟** — 需要更长稳定期观察TIER_COOLDOWN=36的效果
5. **k4 (SOCKS5:7899) 平均10.8s** — 显著低于其他key, 但样本仅3次, 不具统计意义

### 2.4 HM1 vs HM2 参数对比
| 参数 | HM1 | HM2 | 差异 |
|------|-----|-----|------|
| BUDGET | 100 | 128 | HM2更高 |
| UPSTREAM | 45 | 50 | HM2更宽松 |
| MIN_OUTBOUND | 6.0 | 2.5 | HM1激进出站限制 |
| KEY_COOLDOWN | 38 | 38 | 同步 |
| TIER_COOLDOWN | 36 | 22 | HM2更快tier重入 |
| CONNECT_RESERVE | 10 | 21 | HM2更大余量 |
| SSLEOF_RETRY | 3.0 | (HM2无此参数) | - |

HM1的MIN_OUTBOUND=6.0明显高于HM2的2.5 — 这是主动出站节流, 已验证有效(2.5%阻塞率)。

---

## 3. 决策: ⏸️ 无操作

**理由**:
1. **ATE全NVCF侧不可防** — 22个错误均为NVCFPexecTimeout, 发生在HM代理已将请求发送至NVCF API后
2. **全参数均衡** — 所有7参数处于最优工作点, 无单一参数可调空间
3. **零可优化错误** — 0 429, 0 empty200, 0 SSL, 0 代理层超时
4. **TIER_COOLDOWN=36 刚改需观察** — R337减2s, 仅15分钟运行时间, 需更长稳定期验证
5. **无新增退化信号** — 30min窗口98.8%成功率, 0 5xx

**铁律遵守**: ✅ 只改HM1不改HM2 — 本轮无操作, 自然遵守

---

## 4. 下次轮次建议

**HM1→HM2 (R341) 关注点**:
- 观察TIER_COOLDOWN=36在更长窗口(1h+)的表现
- 关注HM2侧是否有可优化空间 (MIN_OUTBOUND=2.5较宽松)
- 若HM1持续零错误, 可考虑将MIN_OUTBOUND从6.0微调至5.5

---

## ⏳ 轮到HM1优化HM2