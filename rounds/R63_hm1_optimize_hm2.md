# R63: HM1→HM2 优化轮

**日期**: 2026-06-26 20:45 UTC  
**执行者**: HM1 (opc_uname)  
**优化目标**: HM2 (hm40006 on 100.109.57.26)  
**前一轮**: R62 (HM2→HM1: UPSTREAM_TIMEOUT 56→58) + R61 (HM1→HM2: UPSTREAM_TIMEOUT 62→60)  
**检测触发**: HM2提交 R62_hm2_optimize_hm1.md (commit f9e4701), 结尾标记 `轮到HM1优化HM2`

---

## 📊 数据采集 (30分钟窗口)

### 1. 日志统计 (docker logs --tail 500)
```
HM-SUCCESS:            22
HM-TIER-FAIL:          1
HM-FALLBACK-SUCCESS:   1
HM-TIMEOUT:            4
SSLEOFError:           2
COOLDOWN (429):        4
```

### 2. 运行环境 (HM2)
| 参数 | 值 |
|------|-----|
| UPSTREAM_TIMEOUT | **60** (R61从62→60) |
| TIER_TIMEOUT_BUDGET_S | **111** |
| MIN_OUTBOUND_INTERVAL_S | **17.0** |
| KEY_COOLDOWN_S | **26.5** |
| TIER_COOLDOWN_S | **42** (DEAD) |
| HM_CONNECT_RESERVE_S | **18** (R62从16→18) |

### 3. 错误分布 (hm_error_detail, 30min)
| 错误类型 | 数量 | 备注 |
|----------|------|------|
| 429_nv_rate_limit (glm5.1) | **1,937** | 函数级限流100%饱和 |
| NVCFPexecSSLEOFError | **238** | ⚠️ 最高非429错误 |
| NVCFPexecConnectionResetError | **111** | NVCF基础设施级别 |
| NVCFPexecTimeout | **15** | 低, avg=35.0s |
| empty_200 | **13** | 低 |
| NVCFPexecRemoteDisconnected | **10** | 低 |

### 4. 超时桶分布 (NVCFPexecTimeout)
| 桶 | 数量 | % |
|----|------|---|
| <20s | 4 | 26.7% |
| 20-40s | 6 | 40.0% |
| 40-60s | 3 | 20.0% |
| >60s | **2** | **13.3%** |

- 平均超时: **35.0s**
- >60s: 仅2个 (13.3%, 迄今最低)

### 5. 指标卷 (hm_metrics)
```
970 events with duration_ms in 30min
平均duration: 37,953ms
```

### 6. 0-tier (tiers_tried_count=0)
```
0 条 — 完全消除 (连续多轮)
```

---

## 🔍 诊断

### 瓶颈 #1: SSLEOFError=238 (显著)
NVCFPexecSSLEOFError=238是最高非429错误。这是mihomo代理连接不稳定的表现。MIN_OUTBOUND_INTERVAL_S=17.0已较高，继续增加可能收益递减。SSLEOF属于连接层问题，非参数可完全解决。

### 瓶颈 #2: 429函数级限流 (不变)
1,937次429_nv_rate_limit，glm5.1全线429。这是NVCF基础设施限制，不可通过参数调整解决。

### 瓶颈 #3: NVCFPexecTimeout=15 (低)
超时仅15个，且>60s桶仅2个(13.3%)，是迄今最低。平均35s的timeout完全可以被58-60s的UPSTREAM_TIMEOUT覆盖。

### 决策: UPSTREAM_TIMEOUT 60→58 (-2s)

**依据**:
- R61已从62→60 (-2s)，本轮继续同方向60→58 (-2s)
- NVCFPexecTimeout=15 (低), avg=35.0s — 58s完全覆盖主要超时范围
- >60s桶仅2个 (13.3%) — 这些在60s时也会超时，58s无实质损失
- 预算数学保持安全: 1st=58s, 2nd=max(10, min(58, 53-18=35)) = 35s
- 与R62(HM2→HM1: 56→58, +2s)形成镜像 — 双方均在58s点
- 少改多轮: 单参数变更 (-2s), 渐进式

**预算计算 (变更后)**:
- UPSTREAM=58, BUDGET=111, RESERVE=18
- 1st attempt: min(58, 111-18=93) = **58s**
- remaining: 111-58 = 53
- 2nd attempt: max(10, min(58, 53-18=35)) = **35s**
- 3rd attempt: remaining 35-35=0 < 10 → BREAK

---

## ⚙️ 变更执行

| 参数 | 变更前 | 变更后 | 理由 |
|------|--------|--------|------|
| UPSTREAM_TIMEOUT | 60 | **58** | -2s: 继续UPSTREAM收敛; timeout低(15个), avg=35s, 58s完全覆盖; 少改多轮 |

### SSH命令
```bash
# 备份
ssh HM2 "cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R63"

# 值变更 (line 476)
ssh HM2 "cd /opt/cc-infra && sed -i '476s/\"60\".*R61: HM1优化.*受益/\"58\"  # R63: HM1优化 — 60→58: -2s per-key timeout; continuing UPSTREAM收敛; NVCFPexecTimeout=15(低) avg=35s; 58s covers full range; SSLEOF=238(关注); 少改多轮; 单参数变更; 所有tier受益/' docker-compose.yml"

# 部署
ssh HM2 "cd /opt/cc-infra && docker compose up -d hm40006"
```

### 验证
```
UPSTREAM_TIMEOUT=58 ✓
hm40006 Up 27 seconds (healthy) ✓
mihomo process=1 (running, 未停止) ✓
hm40006正常启动, 处理请求中 ✓
```

---

## 📈 预期效果

**预算计算 (变更后)**:
- UPSTREAM=58, BUDGET=111, RESERVE=18
- 1st attempt: 58s (从60s减少2s)
- 2nd attempt: 35s (从33s增加2s, remaining更多=53)
- 预算利用更均衡

**预期**:
- 总请求延迟微降 (-2s per constrained 1st attempt)
- >60s桶: 2→2-3 (无变化, 这些请求在60s时也会超时)
- SSLEOFError: 不变 (连接层参数未变)
- 429计数: 不变 (函数级限流未变)

---

## ⚠️ 观察项

- **UPSTREAM=58与HM1对称**: HM1(R62后)=58, HM2(R63后)=58 — 双方汇聚到58s
- **下一轮**: 若58s效果好, 可考虑56s(-2s)或BUDGET调整
- **SSLEOFError=238需持续关注**: 连接层稳定性问题，MIN_OUTBOUND_INTERVAL_S=17.0已较高
- **少改多轮**: 单参数变更 (-2s)
- **铁律**: 只改HM2不改HM1 ✓
- **禁止**: 未停止/重启/kill mihomo ✓ (mihomo process=1, running)

---

## 📝 本轮总结

R63继续UPSTREAM收敛路径 (R61: 62→60, R63: 60→58).  
与R62(HM2→HM1: 56→58)形成镜像 — 双方HM1/HM2均在UPSTREAM=58s点.  
2s虽小, 但在多键循环中累积有效果.  
超时量低(15个30min), 平均35s, 58s完全覆盖.  
SSLEOFError=238是当前最大非429问题, 属于mihomo连接层, 非timeout参数可解.  
实际瓶颈仍是NVCF函数级限流(100%饱和), 无法通过纯参数调整解决.

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记