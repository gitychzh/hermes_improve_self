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
MIN_OUTBOUND_INTERVAL_S=15.6  ← 本回合变更目标
KEY_COOLDOWN_S=38           ← R267: R258均衡 @ 38
TIER_COOLDOWN_S=22           ← DEAD (不在config.py)
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
| 结论 | 错误全在最近10分钟, 91/91集中 |

### Tier分布 (30min)
| Tier | 请求数 | 平均延迟 | 回退次数 |
|------|--------|----------|----------|
| deepseek_hm_nv | 789 | 22.9s | 1 |
| glm5.1_hm_nv | 202 | 43.8s | 4 |
| (null/失败) | 90 | 116.3s | 0 |

### Per-Key 429 (hm_tier_attempts, 30min)
| Key | 429次数 |
|-----|---------|
| k0 | 4 |
| k1 | 6 |
| k2 | 3 |
| k3 | 3 |
| k4 | 4 |
| 范围 | 1.5× (均匀,非单key热点) |

### Tier层错误 (hm_tier_attempts, 30min)
| Tier | 错误类型 | 数量 |
|------|---------|------|
| glm5.1_hm_nv | 500_nv_error | 30 |
| glm5.1_hm_nv | 429_nv_rate_limit | 20 |
| glm5.1_hm_nv | NVCFPexecSSLEOFError | 18 |
| glm5.1_hm_nv | empty_200 | 12 |
| glm5.1_hm_nv | NVCFPexecConnectionResetError | 2 |

### 10-min vs 30-min 错误对照
| 窗口 | 总请求 | 错误 |
|------|--------|------|
| 10min (03:19-03:29) | 1032 | 91 |
| 30min (02:59-03:29) | 1082 | 91 |
| 前20min (02:59-03:19) | 50 | 0 |

→ 错误100%集中在最近10分钟。10min≥30min是R262定义的需要变更信号。

### Error Detail JSONL — 全部 `all_429: false`
所有error_detail JSONL条目显示 `all_429: false` — 混合故障模式确认:
```json
典型条目 (03:29:21):
  tier=glm5.1_hm_nv, 6 key attempts:
  k3=500_nv_error, k4=500_nv_error, k0=empty_200,
  k1=NVCFPexecTimeout(10.6s), k2=NVCFPexecTimeout(11.4s),
  k3=NVCFPexecTimeout(10.7s)
  elapsed=126856ms, all_429: false
  结论: 不是函数级429饱和, 是server-side混合故障
```

### Budget Breaks (docker logs 03:23-03:29)
```
最新break: tier=glm5.1_hm_nv, budget=128.0s, remaining=1.1s < 10s minimum
所有5 keys在126856ms内全部失败, 触发budget break
TIER_TIMEOUT_BUDGET_S=128s — 足够, 但4-5 key attempts×28-35s ≥ 128s时触发
```

### rr_counter.json (累计请求数)
```json
{"hm_nv_deepseek": 7547, "hm_nv_kimi": 161, "hm_nv_glm5.1": 6407}
```
glm5.1累计6407请求 (生命周期), deepseek累计7547 (大部分来自早期R38/R208多模型期)

---

## 分析

1. **成功率仅91.59%** — 远低于99%阈值。1082请求中90个ATE+1个NVStream=91个错误。KEY_COOLDOWN_S已在R267达到R258=38, 但MIN_OUTBOUND_INTERVAL_S仍差3.6s。

2. **all_429: false × 100%** — 所有error_detail JSONL都显示 `all_429: false`, 这是R264定义的**混合故障模式**: NVCFPexecTimeout + empty_200 + 500 + SSLEOFError + 429的混合, 不是函数级429饱和。NV API函数在响应但返回server-side错误。

3. **10min ≥ 30min** — 90/1032 (10min) vs 90/1082 (30min), 所有错误集中在最近10分钟。这是R262定义的need-change信号。R267的KEY_COOLDOWN变更后, 错误未完全消退 — 需要下一轮参数调整。

4. **R258收敛缺口**: MIN_OUTBOUND_INTERVAL_S=12.0, R258=15.6, 缺口=3.6s。KEY_COOLDOWN已到38, 这是最后一个未达R258均衡的活跃参数。

5. **为什么选MIN_OUTBOUND_INTERVAL_S**: R264定义了向R258回归的双参数收敛路径(KEY_COOLDOWN + MIN_OUTBOUND)。R267已将KEY_COOLDOWN推到38 (R258均衡), 现在MIN_OUTBOUND需要从12.0→15.6完成收敛。

6. **为什么不是其他参数**:
   - `KEY_COOLDOWN_S=38` → 已在R267达到R258均衡值, 不再动。
   - `TIER_COOLDOWN_S=22` → DEAD PARAMETER, 不在config.py。改它无效果。
   - `HM_CONNECT_RESERVE_S=24` → 在upstream.py, 已与HM1=24收敛(gap=0)。
   - `UPSTREAM_TIMEOUT=75` → 已经是高值。NVCFPexecTimeout(~35-44s)占主导, 不是客户侧超时瓶颈。减少会切掉合法慢请求。
   - `TIER_TIMEOUT_BUDGET_S=128` → 预算用尽但128s已足够。budget break发生在5 key attempts × 25-35s ≈ 125s附近, 表示预算合理。增加不会阻止break。

7. **单参数规则**: 本次只改MIN_OUTBOUND_INTERVAL_S一个参数 → 符合"少改多轮"原则。+3.6s delta在4-unit cap内 (实际3.6<4)。

8. **10min/30min交叉验证**: 前20min (02:59-03:19) 只有50请求/0错误 — 说明R267的KEY_COOLDOWN=38生效后, 系统有15分钟安静期。但03:19-03:29爆发91错误 — 说明单靠KEY_COOLDOWN不够, 需要MIN_OUTBOUND配合。

---

## 执行

### 变更: MIN_OUTBOUND_INTERVAL_S: 12.0 → 15.6 (+3.6s)

```bash
# 修改H2的docker-compose.yml — 仅line 472 (hm40006 service)
ssh HM2 "sed -i 's|MIN_OUTBOUND_INTERVAL_S: \"12.0\"|MIN_OUTBOUND_INTERVAL_S: \"15.6\"|' /opt/cc-infra/docker-compose.yml"

# 更新注释为R268版本
sed -i "472s/.*/      MIN_OUTBOUND_INTERVAL_S: \"15.6\"  # R268: .../" docker-compose.yml

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

**效果**: 增加请求间间距 (+3.6s) → NV API key间从12.0s间隔变为15.6s → 减少在NV API server端堆积的并发请求 → 降低 `NVCFPexecTimeout` / `500_nv_error` / `empty_200` 的发生率 → 每key有更多时间在发送前让NV API server恢复 → 减少all_tiers_exhausted的总速率。

**收敛路径**:
- R263 (冷启动): 12.0→8.0 (-4s)
- R264 (恢复): 8.0→12.0 (+4s)
- **R268**: 12.0→15.6 (+3.6s) ← 本回合, 达到R258均衡值

**KEY_COOLDOWN_S收敛路径 (已完成)**:
- R263: 25→18 (-7s, 冷启动)
- R264: 18→30 (+12s)
- R266: 30→34 (+4s)
- R267: 34→38 (+4s) → R258=38 ✓

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记