# R45: HM2→HM1 优化

**日期**: 2026-06-26 14:45  
**Actor**: HM2 (opc2_uname)  
**Target**: HM1 (100.109.153.83:222)  
**触发**: HM1提交R45(4b18246) → 轮到HM2优化HM1  
**上一轮**: R44 (HM2→HM1, TIER_BUDGET 94→96)

---

## 数据收集

### 1. 容器环境 (docker exec hm40006 env)
| 参数 | 值 |
|---|---|
| UPSTREAM_TIMEOUT | 42 |
| TIER_TIMEOUT_BUDGET_S | 96 |
| MIN_OUTBOUND_INTERVAL_S | 14.0 |
| KEY_COOLDOWN_S | 38.0 |
| TIER_COOLDOWN_S | 84 |
| HM_CONNECT_RESERVE_S | 22 |

### 2. 日志分析 (30min窗口, 1095行)
- **错误/警告行**: 40行 (grep -ciE error|warn|fail)
- **SSLEOFError (日志)**: 5条 (200行tail)
- **ConnectionResetError**: 29条 (deepseek tier, hm_tier_attempts, avg 2229ms)
- **NVCFPexecRemoteDisconnected**: 3条

### 3. DB统计 (30min窗口)

#### 3a. 错误分布 (hm_tier_attempts)
| error_type | cnt | avg_elapsed_ms |
|---|---|---|
| 429_nv_rate_limit | 1165 | — |
| NVCFPexecTimeout | 104 | 29428 |
| NVCFPexecConnectionResetError | 29 | 2229 |
| budget_exhausted_after_connect | 5 | 797 |
| NVCFPexecRemoteDisconnected | 3 | 3775 |

#### 3b. 请求路由 (hm_requests)
| fallback_occurred | cnt | avg_dur_ms |
|---|---|---|
| f (直连) | 122 | 16034 |
| t (fallback) | 1217 | 18782 |

**Fallback率**: 90.8% (1221/1344)

#### 3c. Tier分布 (hm_tier_attempts)
| tier | cnt |
|---|---|
| glm5.1_hm_nv | 1197 (99% 429) |
| deepseek_hm_nv | 105 |
| kimi_hm_nv | 2 |

#### 3d. Deepseek超时桶 (104 NVCFPexecTimeout)
| bucket | cnt | % |
|---|---|---|
| <20s | 36 | 34.6% |
| 20-25s | 11 | 10.6% |
| 25-30s | 8 | 7.7% |
| 30-35s | 1 | 1.0% |
| **>40s** | **41** | **39.4%** |

#### 3e. 0-tier全层耗尽
| tiers_tried | key_cycle_429s | cnt | avg_dur_ms |
|---|---|---|---|
| 0 | 0 | 3 | 169145 |

#### 3f. 最近请求延迟快照 (最后10条)
| request_id | tier_model | duration_ms | fallback | key_cycle_429s |
|---|---|---|---|---|
| cf338b29 | deepseek_hm_nv | 15317 | t | 1 |
| 7e91c9ce | deepseek_hm_nv | 10933 | t | 0 |
| 1fca8ea6 | deepseek_hm_nv | 26420 | t | 6 |
| 13829ac7 | glm5.1_hm_nv | 12885 | f | 0 |
| f820d4b0 | deepseek_hm_nv | 15248 | t | 0 |
| 91b733ed | deepseek_hm_nv | 27407 | t | 0 |
| 5c88d59d | deepseek_hm_nv | 25689 | t | 0 |
| 6942091b | deepseek_hm_nv | 27878 | t | 0 |
| 3a281c79 | deepseek_hm_nv | 53704 | t | 1 |
| 2d219631 | deepseek_hm_nv | 55204 | t | 5 |

#### 3g. glm5.1 per-key 429 (函数级, 均匀)
| nv_key_idx | 429 | ConnReset |
|---|---|---|
| 0 | 217 | 5 |
| 1 | 233 | 6 |
| 2 | 237 | 5 |
| 3 | 238 | 7 |
| 4 | 241 | 6 |

#### 3h. Deepseek per-key timeout桶
| key | <20s | 20-25s | 25-30s | 30-35s | >40s |
|---|---|---|---|---|---|
| k0 | 7 | 1 | 4 | 0 | 5 |
| k1 | 10 | 3 | 1 | 0 | 9 |
| k2 | 5 | 2 | 1 | 0 | 11 |
| k3 | 6 | 5 | 1 | 0 | 5 |
| k4 | 8 | 0 | 1 | 1 | 11 |

---

## 诊断

### 1. Fallback率90.8% — 稳定高位
glm5.1直连成功122条(9.1%)，1165次429失败——函数级NVCF 429限流。所有5个key均匀分布(217-241)，无per-key差异。glm5.1主层本身不是优化目标。

### 2. Deepseek >40s桶占39.4% (41/104)
在UPSTREAM=42下，TIER_BUDGET=96，RESERVE=22:
- 1st attempt = min(42, 96-22=74) = 42s
- Remaining = 96-42 = 54s
- 2nd attempt = max(10, min(42, 54-22=32)) = 32s

>40s桶41事件=请求在第1次(42s)+第2次(32s)总计已消耗74s才超时——NVCF基础设施级超时，非headroom不足。

2nd-attempt 32s已覆盖25-30s(8事件)+30-35s前半(1事件)。BUDGET 96→98仅增加+2s到2nd尝试，但30-35s桶仅1事件——不值得。

### 3. ConnectionResetError=29 — 新增长 (R42=18)
从R42的18上升到29(+11)。MIN_INTERVAL=14.0下仍增长——更多重试=更多连接重置。但SSLEOF=5(≈0)稳定在R42验证水平。这是mihomo连接压力，非MIN_INTERVAL立即可解决的。

### 4. 0-tier=3 — RESERVE=22稳定
3个全层耗尽(avg 169s, tiers_tried=0, key_cycle_429s=0)——连接级SOCKS5+SSL失败。RESERVE已饱和，不调整。

### 5. 关键决策
**TIER_COOLDOWN_S 84→82 (-2s)**：继续R34→R37的-2s递减轨迹(R34:90→88, R36:88→86, R37:86→84)。加速glm5.1恢复重试，减少tier-skip等待。90.8% fallback下减少无效等待直接影响平均延迟。

---

## 优化

| 参数 | 旧值 | 新值 | 理由 |
|---|---|---|---|
| TIER_COOLDOWN_S | 84 | **82** (-2s) | 继续加速glm5.1恢复重试；R34→R37递减轨迹(-2s×4轮)；ConnectionResetError=29(deepseek)不影响此参数；0-tier=3(RESERVE=22稳定) |

**预算数学不变**:
- 1st attempt = 42s (min(42, 96-22))
- 2nd attempt = 32s (max(10, min(42, 54-22)))
- 2nd-attempt headroom = 32s (覆盖25-30s全桶+30-35s前半)

---

## 执行记录

```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R45'

# 修改 TIER_COOLDOWN_S 84→82 (line 422)
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '422s/\"84\"/\"82\"/' docker-compose.yml"

# 更新注释
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && sed -i '422s/# R37:.*$/# R45: HM2优化 — 84→82: -2s tier cooldown; 继续加速glm5.1恢复重试; ConnectionResetError=29(deepseek), 0-tier=3(RESERVE=22稳定), fallback=90.8pct; 少改多轮(单参数变更); 铁律:只改HM1不改HM2/' docker-compose.yml"

# 部署
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'

# 验证
# docker exec hm40006 env → TIER_COOLDOWN_S=82 ✓
# docker ps → hm40006 Up healthy ✓
# 确认: 仅改HM1配置(TIER_COOLDOWN_S), HM2本地未动
```

---

## 预期效果

1. **TIER-SKIP等待-2s**: 从84s→82s，每次tier切换节省2s
2. **glm5.1重试加速**: 82s内可重新尝试glm5.1(NVCF函数级429仍存在但恢复窗口更短)
3. **ConnectionResetError**: 此参数不直接影响——mihomo连接压力来自MIN_INTERVAL/代理端口，非tier cooldown
4. **0-tier**: RESERVE=22已稳定，无预期变化
5. **Fallback率**: 90.8%可能微降至~89-90%(glm5.1恢复更快=更多直连尝试=更多429=更少fallback？待观察)

---

## 观察项

1. **ConnectionResetError 29→监控**: 下次收集数据时对比post-R45是否变化
2. **SSLEOF=5稳定**: R42 MIN_INTERVAL=14.0已验证
3. **TIER_COOLDOWN_S下限**: 当前82s(R34:90→88→86→84→82); 若继续-2s到80s需检查TIER-SKIP率
4. **BUDGET=96**: 在UPSTREAM=42下2nd=32s已够用; 除非>40s桶继续增长才考虑BUDGET→98
5. **HM1未从mihomo优化获益**: 只改compose, 不改mihomo/proxy port配置

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记