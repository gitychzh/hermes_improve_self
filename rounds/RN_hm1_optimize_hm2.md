# R268: HM1→HM2 — MIN_OUTBOUND_INTERVAL_S 12.0→15.6 (+3.6s)

**回合类型**: 单参数优化
**方向**: HM1→HM2 (HM1优化HM2)
**日期**: 2026-06-29 03:34 CST
**作者**: opc_uname
**原则**: 更少报错 更快请求 超低延迟 稳定优先
**铁律**: ⚠️ 只改HM2配置绝不改HM1本地 ⚠️ 绝不停止/重启/kill mihomo
**单轮规则**: 少改多轮积累

---

## 数据收集 (03:23-03:29 CST)

### HM2运行容器环境变量
```
MIN_OUTBOUND_INTERVAL_S=12.0  ← 本回合前
KEY_COOLDOWN_S=38             ← R267: R258均衡 @ 38
TIER_COOLDOWN_S=22            ← DEAD (不在config.py)
UPSTREAM_TIMEOUT=75
TIER_TIMEOUT_BUDGET_S=128
HM_CONNECT_RESERVE_S=24
PROXY_TIMEOUT=300
CHARS_PER_TOKEN_ESTIMATE=3.0
```

### 30分钟窗口 — hm_requests
| 指标 | 值 |
|------|-----|
| 总请求 | 1082 |
| 成功(200) | 991 |
| 成功率 | **91.59%** |
| p50延迟 | 23.9s |
| p95延迟 | 118.8s |
| 平均延迟 | 34.5s |

### 错误分布 (30min)
| 错误类型 | 数量 |
|----------|------|
| all_tiers_exhausted | 90 |
| NVStream_IncompleteRead | 1 |

### 10分钟突发窗口
| 指标 | 值 |
|------|-----|
| 总请求 | 1032 |
| 错误数 | 91 |
| 成功率 | 91.18% |
| 结论 | 错误全在最近10分钟,91/91集中 |

### 10min vs 30min 错误对照
| 窗口 | 总请求 | 错误 |
|------|--------|------|
| 10min (03:19-03:29) | 1032 | 91 |
| 30min (02:59-03:29) | 1082 | 91 |
| 前20min (02:59-03:19) | 50 | 0 |

→ 错误100%集中在最近10分钟。10min≥30min是R262定义的需要变更信号。

### Per-Key 429
| Key | 429次数 |
|-----|---------|
| k0 | 4 |
| k1 | 6 |
| k2 | 3 |
| k3 | 3 |
| k4 | 4 |
| 范围 | 1.5× (均匀) |

### Tier层错误 (30min)
| Tier | 错误类型 | 数量 |
|------|---------|------|
| glm5.1_hm_nv | 500_nv_error | 30 |
| glm5.1_hm_nv | 429_nv_rate_limit | 20 |
| glm5.1_hm_nv | NVCFPexecSSLEOFError | 18 |
| glm5.1_hm_nv | empty_200 | 12 |
| glm5.1_hm_nv | NVCFPexecConnectionResetError | 2 |

### Error Detail JSONL — 全部 `all_429: false`
所有error_detail JSONL条目显示 `all_429: false` — 混合故障模式确认。典型:
```json
tier=glm5.1_hm_nv, 6 key attempts, elapsed=126856ms
all_429: false
错误: 500_nv_error + empty_200 + NVCFPexecTimeout(10-11s)
不是函数级429饱和, 是server-side混合故障
```

### Budget Breaks
```
最新break: tier=glm5.1_hm_nv, budget=128.0s, remaining=1.1s < 10s minimum
```

### rr_counter.json (累计请求数)
```json
{"hm_nv_deepseek": 7547, "hm_nv_kimi": 161, "hm_nv_glm5.1": 6407}
```

---

## 分析

1. **成功率仅91.59%** — 1082请求/90 ATE。R267 KEY_COOLDOWN=38生效后，前20分钟0错误（50请求全成功），但10分钟后爆发91错误。单靠KEY_COOLDOWN不够，需要MIN_OUTBOUND配合。

2. **all_429: false × 100%** — R264定义的混合故障模式确认。NV API函数在响应但返回server-side错误。

3. **10min ≥ 30min** — 所有错误集中在最近10分钟（前20min=0）。R262定义的need-change信号：需要变更。

4. **R258收敛缺口**: MIN_OUTBOUND_INTERVAL_S=12.0, R258=15.6, 缺口=3.6s。KEY_COOLDOWN=38已达R258，这是最后一缺。

5. **为什么选MIN_OUTBOUND_INTERVAL_S**: R264收敛路径中的最后一步。KEY_COOLDOWN已到R258=38，MIN_OUTBOUND需要补到15.6完成双参数收敛。

6. **为什么不是其他参数**:
   - `KEY_COOLDOWN_S=38` → 已达R258，不动。
   - `TIER_COOLDOWN_S=22` → DEAD，不在config.py。
   - `HM_CONNECT_RESERVE_S=24` → 已与HM1收敛(gap=0)。
   - `UPSTREAM_TIMEOUT=75` → 高值，NVCFPexecTimeout(~35-44s)占主导，不是客户侧瓶颈。
   - `TIER_TIMEOUT_BUDGET_S=128` → 预算用尽但128s足够。

7. **单参数规则**: 只改MIN_OUTBOUND_INTERVAL_S → +3.6s在4-unit cap内。

---

## 执行

### 变更: MIN_OUTBOUND_INTERVAL_S: 12.0 → 15.6 (+3.6s)

```bash
# 修改HM2的docker-compose.yml
ssh HM2 "sed -i 's|MIN_OUTBOUND_INTERVAL_S: \"12.0\"|MIN_OUTBOUND_INTERVAL_S: \"15.6\"|' /opt/cc-infra/docker-compose.yml"

# 重建容器(只改compose文件,不动mihomo)
ssh HM2 "cd /opt/cc-infra && docker compose up -d --no-deps --force-recreate hm40006"

# 验证
sleep 3 && docker exec hm40006 env | grep MIN_OUTBOUND_INTERVAL_S  # → 15.6 ✓
```

### 验证结果
```
✅ MIN_OUTBOUND_INTERVAL_S=15.6 (运行容器确认)
✅ KEY_COOLDOWN_S=38 (R258均衡,未变)
✅ TIER_COOLDOWN_S=22 (DEAD,但保留)
✅ UPSTREAM_TIMEOUT=75
✅ TIER_TIMEOUT_BUDGET_S=128
✅ HM_CONNECT_RESERVE_S=24
✅ docker ps: Up 23 seconds (healthy)
✅ mihomo PID 2008535 仍运行 (未触碰)
✅ curl http://localhost:40006/health → 200
```

### 预期效果
| 参数 | 变更前 | 变更后 | 方向 |
|------|--------|--------|------|
| MIN_OUTBOUND_INTERVAL_S | 12.0s | 15.6s | +3.6s → R258=15.6 |

**效果**: 增加请求间间距 → NV API key间从12.0s变为15.6s → 减少NV API server端并发堆积 → 降低混合故障(Timeout/500/empty_200) → 每个key更少遇错 → 减少ATE速率。

**收敛路径**:
- R263 (冷启动): 12.0→8.0 (-4s)
- R264 (恢复): 8.0→12.0 (+4s)
- **R268**: 12.0→15.6 (+3.6s) ← 本回合,达到R258均衡值

**KEY_COOLDOWN_S收敛路径 (已完成)**:
- R263: 25→18, R264: 18→30, R266: 30→34, R267: 34→38 → R258=38 ✓

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记