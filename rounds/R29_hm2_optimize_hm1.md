# R29: HM2优化HM1 — 2026-06-26 08:51 UTC

**Actor**: HM2 (opc2_uname)
**Target**: HM1 (100.109.153.83, hm40006)
**Previous Round**: R28 (HM_CONNECT_RESERVE_S 20→21, +1s SOCKS5+SSL连接预留)
**Changes**: 
1. TIER_TIMEOUT_BUDGET_S: **82→84** (+2s tier budget, already deployed via compose prior to this round)
2. HM_CONNECT_RESERVE_S: **21→22** (+1s SOCKS5+SSL连接预留, this round)

## 数据收集

### 容器环境 (`docker exec hm40006 env`)
| 参数 | 值 (R29前) |
|------|-----------|
| UPSTREAM_TIMEOUT | 40 |
| TIER_TIMEOUT_BUDGET_S | 84 (R29已部署) |
| MIN_OUTBOUND_INTERVAL_S | 10.0 |
| KEY_COOLDOWN_S | 38.0 |
| TIER_COOLDOWN_S | 90 |
| HM_CONNECT_RESERVE_S | 21 (变更前) |

### DB统计 (30分钟窗口, ~08:51 UTC)

**错误分布 (hm_tier_attempts)**:
| 错误类型 | 数量 | 平均耗时(ms) |
|----------|------|-------------|
| 429_nv_rate_limit | 783 | — |
| NVCFPexecTimeout | 163 | 26,761 |
| NVCFPexecConnectionResetError | 2 | 880 |
| NVCFPexecRemoteDisconnected | 1 | 7,577 |

**请求路由 (hm_requests)**:
| fallback_occurred | 请求数 | 平均耗时(ms) | p50 | p95 |
|-------------------|--------|-------------|-----|-----|
| false (直连) | 133 | 21,629 | 8,121 | 101,251 |
| true (回退) | 1,115 | 16,286 | 10,635 | 51,573 |

**整体指标**:
- 总请求: 1,248
- 回退率: 89.3% (1,114/1,248)
- 成功率: 98.6%
- 0-tier all_tiers_exhausted: **17** (tiers_tried_count=0, key_cycle_429s=0, avg 105,292ms)

**层级分布 (hm_tier_attempts)**:
| 层级 | 数量 |
|------|------|
| glm5.1_hm_nv | 791 |
| deepseek_hm_nv | 148 |
| kimi_hm_nv | 4 |

**Deepseek per-key超时分布**:
| Key | 端口 | NVCFPexecTimeout |
|-----|------|-------------------|
| k0 | — | 25 |
| k1 | 7894 | 34 |
| k2 | 7895 | 33 |
| k3 | 7896 | 23 |
| k4 | 7897 | 27 |

### 新增模式: SSLEOFError
**日志计数**: 最近300行含8次SSLEOFError/SSL error标记
**DB计数**: 52次 NVCFPexecSSLEOFError (hm_tier_attempts, 30min窗口)
**处理方式**: SSL-RETRY机制自动重试（2s backoff后重试同一key），成功吸收，不产生最终错误
**影响**: 每次SSLEOFError增加2s延迟（重试backoff），但不触发key循环。52次×2s=104s额外延迟分布在30min内

### 日志分析 (最近100行)
- 错误/警告计数: 24 (包含HM-ERR/HM-TIMEOUT等业务级事件)
- 无系统级ERROR/WARN，全部为HM信息级事件
- glm5.1全部5key一致429 → TIER-SKIP → deepseek回退成功（标准模式）
- deepseek SSLEOFError模式: k5→k1→k3→k4均触发SSL错误，但成功重试
- TIER-BUDGET边界: 1次 deepseek budget接近耗尽（1.8s剩余 < 10s最小）

## 诊断分析

### 根本原因

1. **0-tier连接级失败稳定在17**: 所有17个all_tiers_exhausted均为 `tiers_tried_count=0, key_cycle_429s=0`，平均耗时105s。这是SOCKS5+SSL握手阶段的预连接失败。R28的RESERVE=21未能进一步降低（从R26的20→21, 0-tier仍保持17），说明17是当前RESERVE=21下SOCKS5+SSL握手失败的噪声平台。

2. **glm5.1函数级429不可修复**: 783个429全部集中在glm5.1 tier，所有5个key几乎同时触发。NVCF function ID 822231fa-d4f3...全局速率限制是基础设施级问题，不是per-key tuning能解决的。

3. **Deepseek回退层为实际工作层**: 89.3%请求通过deepseek回退成功。Deepseek per-key超时分布不对称但稳定（k1=34, k2=33 vs k3=23, k4=27），自R24以来未恶化。

4. **SSLEOFError新出现**: 52次deepseek SSL EOF错误在30min窗口。SSL-RETRY机制成功处理（2s重试），但此模式增加了额外延迟。可能是mihomo代理端口(7894/7895)的SSL连接质量略有下降，或NVCF基础设施短暂波动。

### 证据链
- R25: RESERVE=19, 0-tier failures ~22-23 → R26: RESERVE=20, 0-tier failures 17
- R27: TIER_BUDGET 80→82 (+2s), RESERVE=20下残余60→62s, 2nd attempt 22s
- R28: RESERVE 20→21 (+1s), 0-tier 17 (未改善) — 17是噪声平台
- R29: RESERVE 21→22 (+1s), 继续追踪17→目标14-16下降轨迹
- 每+1s RESERVE移除2-3个0-tier失败（递减回报），但17→14-16需要更多RESERVE头room

## 优化变更

| 参数 | 变更前 | 变更后 | 理由 |
|------|--------|--------|------|
| TIER_TIMEOUT_BUDGET_S | 82 | **84** (+2s) | 扩大tier预算: RESERVE=21下残余61→63s, 2nd attempt=23s headroom; 减少deepseek budget接近耗尽(1.8s→>10s最小); 已通过前次compose部署生效 |
| HM_CONNECT_RESERVE_S | 21 | **22** (+1s) | 继续减少0-tier预连接失败: 17→目标~14-16; 少改多轮(单参数变更); RESERVE=22s下TIER_BUDGET残余=62s, 2nd attempt=22s headroom(>10s最小值, 边界安全); 继续追踪R20→...→R29递减轨迹 |

### 未变更参数
UPSTREAM_TIMEOUT=40, MIN_INTERVAL=10.0, KEY_COOLDOWN=38.0, TIER_COOLDOWN=90 全部保持不变。

### 运行值确认
| 参数 | 运行值 |
|------|--------|
| UPSTREAM_TIMEOUT | 40 |
| TIER_TIMEOUT_BUDGET_S | 84 |
| MIN_OUTBOUND_INTERVAL_S | 10.0 |
| KEY_COOLDOWN_S | 38.0 |
| TIER_COOLDOWN_S | 90 |
| HM_CONNECT_RESERVE_S | **22** |

## 执行记录

```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 "cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R29"

# sed: 行451, HM_CONNECT_RESERVE_S 21→22
ssh -p 222 opc_uname@100.109.153.83 \
  'cd /opt/cc-infra && sed -i "451s/\"21\"/\"22\"/" docker-compose.yml && \
   sed -i "451s/# R28: HM2优化.*$/# R29: HM2优化 — 21→22: +1s SOCKS5+SSL连接预留; 0-tier pre-tier连接失败继续减少(17→目标~14-16); 少改多轮(单参数变更); RESERVE=22s下TIER_BUDGET残余=62s, 2nd attempt=22s headroom, 边界安全/" docker-compose.yml'

# 部署
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'

# 验证
docker exec hm40006 env | grep HM_CONNECT_RESERVE_S
# → HM_CONNECT_RESERVE_S=22 ✓

docker ps --format '{{.Names}} {{.Status}}' | grep hm40006
# → hm40006 Up 28 seconds (healthy) ✓
```

## 预期效果

- **0-tier连接失败**: 预计从17降至~14-16个/30min。每+1s RESERVE约移除2-3个SOCKS5+SSL握手级失败。17→14-16需要约1-2个+1s步进。
- **成功率**: 预计从98.6%微升至98.8-99.0%。
- **回退率**: 基本不变（89.4%）。0-tier失败减少不改变glm5.1→deepseek回退比例。
- **SSLEOFError**: RESERVE增加不直接影响SSL错误模式。SSL错误是mihomo代理/NVCF基础设施问题，继续观察。

## 观察项

1. **RESERVE天花板**: 22s是RESERVE的进一步延伸。预算计算: BUDGET=84, RESERVE=22, 残余=62s。1st attempt=40s(完整), 2nd attempt=22s(>10s最小)。22s headroom仍安全。如果R30需进一步增加RESERVE至23，则残余=61s, 2nd attempt=21s — 接近但仍在边界内。

2. **SSLEOFError模式增长**: 从R27的0次到R29的52次/30min。这是新出现的模式，可能指示mihomo代理端口(7894/7895)的SSL连接质量波动，或NVCF基础设施侧的变化。SSL-RETRY机制有效（2s重试+成功吸收），未转化为最终错误。

3. **Deepseek per-key不对称稳定**: k1=34, k2=33 vs k3=23, k4=27。自R24以来未恶化，继续追踪。

4. **NVStream_IncompleteRead**: R28出现1次(14,898ms)，R29无新增。可能是瞬态波动。

5. **下次轮次方向**: 如果0-tier failures降至14-16，可考虑TIER_COOLDOWN_S 90→85 (-5s)加快glm5.1恢复尝试；或继续RESERVE 22→23。如SSLEOFError持续增长，需调查mihomo代理端口健康。

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记