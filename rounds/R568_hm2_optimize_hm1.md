# R568 HM2优化HM1 — NOP

## 漂移检测
- **R567部署验证**: 通过
  - 容器env `HM_EMPTY_200_FASTBREAK=0` ✅
  - compose第467行 `HM_EMPTY_200_FASTBREAK: "0"` ✅
  - 容器StartedAt `2026-07-02T11:42:08Z` (R563后未重建, R567仅参数修改,compose重启已触发Recreate验证通过)
  - 三源一致,无漂移

## 数据采集

### 1. HM1容器状态
- `/health=200 ok`
- `hm_num_keys=5`
- HM1 Tailscale ping正常(0ms), SSH正常, peer health curl正常(200/0.0048s)

### 2. Docker日志关键模式(最近100行筛选)
- dsv4p_nv: 连续 `NVCF pexec timeout` @ ~62s → `PEXEC-FASTBREAK=1` → 所有key失败
- kimi_nv: `empty200`(偶发) + `NVCF pexec timeout` @ ~29-61s, fastbreak后peer fb timeout @ ~25s
- `BrokenPipeError`: 客户端断开(非致命,timeout侧效应)
- peer fb: 全部 `TimeoutError @ ~25020-25028ms`

### 3. DB hm_requests — 30min窗口
| model | total | ok | ate | avg_succ_ms | max_succ_ms | min_fail_ms | avg_fail_ms |
|-------|-------|----|-----|-------------|-------------|-------------|-------------|
| dsv4p_nv | 58 | 1 | 57 | 28,658 | 28,658 | 61,211 | 65,072 |
| kimi_nv | 397 | 234 | 163 | 19,446 | 73,935 | 60,411 | 75,711 |
| glm5_1_nv | 2 | 2 | 0 | 4,201 | 5,986 | NULL | NULL |

### 4. DB hm_requests — 2h窗口
| model | total | ok | ate | SR |
|-------|-------|----|-----|----|
| dsv4p_nv | 71 | 1 | 70 | 1.4% |
| kimi_nv | 653 | 435 | 218 | 66.6% |
| glm5_1_nv | 2 | 2 | 0 | 100% |

### 5. DB hm_requests — 6h窗口
| model | total | ok | ate | SR |
|-------|-------|----|-----|----|
| dsv4p_nv | 210 | 131 | 79 | 62.4% |
| kimi_nv | 1,035 | 738 | 297 | 71.3% |
| glm5_1_nv | 2 | 2 | 0 | 100% |

### 6. dsv4p_nv 每小时成功率趋势
| hour (UTC) | total | ok | ate | SR |
|------------|-------|----|-----|----|
| 06:00 | 93 | 93 | 0 | 100.0% |
| 07:00 | 40 | 35 | 5 | 87.5% |
| 08:00-19:00 | ~82 | ~1 | ~81 | ≈0-6.2% |
| 20:00 | 1 | 1 | 0 | 100.0% (1 sample) |

**关键发现**: dsv4p_nv自08:00 UTC起持续12+h硬故障(SR≈0%),20:00出现1个成功请求,可能预示边际恢复,但统计效力不足(1 sample)。

### 7. kimi_nv 2h成功请求耗时分布
| bucket | count | pct |
|--------|-------|-----|
| <20s | 305 | 70.1% |
| 20-40s | 68 | 15.6% |
| 40-50s | 24 | 5.5% |
| 50-55s | 13 | 3.0% |
| 55-60s | 12 | 2.8% |
| 60-63s | 7 | 1.6% (ceiling边缘) |
| 63-70s | 3 | 0.7% |
| >70s | 3 | 0.7% |

### 8. kimi_nv 2h失败请求耗时分布
| bucket | count | pct |
|--------|-------|-----|
| 60-70s | 26 | 11.9% |
| 70-80s | 185 | 84.9% (peer fb timeout路径) |
| 80-90s | 1 | 0.5% |
| >90s | 5 | 2.3% |

### 9. Peer Fallback
- 30min DB: `fallback_occurred` = 0行(零记录)
- 日志: 多次 `peer fallback FAILED after ~25025ms TimeoutError`
- HM2 health curl: `200 0.004828s` (网络完全正常)
- **结论**: peer fb失败为对端(HM2)内部NVCF处理失败,非网络问题

### 10. hm_tier_attempts (30min, tier attempt粒度)
- dsv4p_nv: 0条记录(低记录率,非关键)
- kimi_nv: 3次empty200(k0/k2/k4各1次), 1次500_nv_error(k2), 1次NVCFPexecgaierror(k4)

## 候选参数评估表

| 参数 | 当前值 | 候选新值 | 评估 | 决策 |
|------|--------|----------|------|------|
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | 63(+2s) | k1m1_nv min_fail gap=61000-60411=589ms,微悬崖。但dsv4p_nv硬故障(12h+零救回价值),k1m1_nv 2h仅7个成功在60-63s边缘(1.6%),+2s成本≈(218+57)×2=550s额外延迟/2h,救回期望<2请求。边际收益极低,成本显著。 | ❌ |
| HM_PEER_FALLBACK_TIMEOUT | 25 | 30(+5s) | 30min/6h零peer fb成功; HM2内部也经历同类NVCF硬故障,peer fb无救回价值; HM2 health正常(4ms)排除网络问题; +5s只会增加失败路径延迟,零救回收益。 | ❌ |
| HM_PEXEC_TIMEOUT_FASTBREAK | 1 | 2 (回滚) | R553→R559已证伪: dsv4p_nv所有key无差别timeout,k1m1_nv empty200重置计数器使2永不触发; 2h内无multi-key救回案例。 | ❌ |
| HM_CONNECT_RESERVE_S | 3 | 2 (-1s) | 实测connect 0.6-2.1s,2为0.95x安全边际。当前故障为NVCF function级,与connect无关。 | ❌ |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | 0.8 (-0.2s) | 近期零SSLEOF事件,0.2s边际无意义。glm5_1_nv 100%控制组证明网关参数已最优。 | ❌ |
| MIN_OUTBOUND_INTERVAL_S | 1.0 | 0.8 (-0.2s) | 已与HM2 1.0对齐,KEY_COOLDOWN=25 >> 0.8,零429风险。dsv4p硬故障非throttle问题。 | ❌ |
| HM_EMPTY_200_FASTBREAK | 0 | 1 (回滚) | R567改为0的理论依据是"偶发空响应非function级",30min内empty200仅3次attempt,当前主导故障为timeout(220次)非empty200。回滚无意义。 | ❌ |
| TIER_TIMEOUT_BUDGET_S | 95 | 保持 | R563从80→95的回调已验证安全。2h max_succ=73.9s < 95s,21s余量充足。 | ✅ 保持 |

## 决策分析

### Surge Isolation 双模型对比
- **glm5_1_nv 100% SR** (2 req/2h,样本小但零失败) → 网关参数侧已最优,排除BUDGET/UPSTREAM/ceiling等参数问题
- **dsv4p_nv 12h+硬故障** (08:00后SR≈0%, 210req/6h中08:00后~82req仅~1成功) → NVCF function 8915fd28 级别问题,非网关参数可修
- **kimi_nv 持续中等故障** (2h 66.6% → 30min 58.9%恶化趋势) → 同为NVCF function f966661c 级别问题,surge持续

### 失败模式聚类
- dsv4p_nv: timeout精确聚集在61-65s → ceiling=61s binding,但硬故障下任何chase无效(函数已不可用)
- k1m1_nv: 成功70.1%在<20s快路径; 失败84.9%在70-80s(PEXEC_FASTBREAK=1后peer fb 25s timeout总路径); ceiling边缘成功仅7个(1.6%)
- peer fb: 零成功,全部~25s timeout → HM2也受困于同类NVCF surge

### R567 EMPTY200_FASTBREAK=0 效果初评
- 30min内仅3次empty200 attempt,统计量不足以验证救回效果
- 当前empty200≠主导故障模式(timeout占99%+), R567改动与当前主要矛盾无关
- 长期观察窗口(≥2h)内若empty200后救回率>0%可支撑0值; 若0%救回可考虑回滚至1省时间

## 决策: NOP
全部候选参数数据否决。本轮不做任何HM1参数修改。

**监控要点**:
1. dsv4p_nv 20:00后是否持续恢复(连续3+成功可标志硬故障结束)
2. k1m1_nv 小时级SR是否稳定回升(当前恶化趋势)
3. empty200后cycle救回率(验证R567 EMPTY200_FASTBREAK=0实际效果)
4. peer fb成功数(若HM2侧NVCF恢复,HM1 peer fb可能同步受益)

---
## 当前配置快照(HM1)
| 参数 | 值 | 来源 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 25 | R491 |
| TIER_TIMEOUT_BUDGET_S | 95 | R563 |
| MIN_OUTBOUND_INTERVAL_S | 1.0 | R548 |
| KEY_COOLDOWN_S | 25 | R492 |
| TIER_COOLDOWN_S | 25 | R492 |
| HM_FORCE_STREAM_UPGRADE | 1 | R502 |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | R537 |
| HM_PEER_FALLBACK_ENABLED | 1 | — |
| HM_PEER_FALLBACK_TIMEOUT | 25 | R560 |
| HM_PEER_FALLBACK_URL | http://100.109.57.26:40006 | — |
| HM_PEXEC_TIMEOUT_FASTBREAK | 1 | R559 |
| HM_EMPTY_200_FASTBREAK | 0 | R567 |
| HM_CONNECT_RESERVE_S | 3 | R533 |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | R543 |

Routing: k0→7894(mihomo), k1→DIRECT, k2→7896(mihomo), k3→7896(mihomo), k4→DIRECT
3model: kimi_nv(f966661c)/dsv4p_nv(8915fd28)/glm5_1_nv(6155636e), inject_thinking=False

## ⏳ 轮到HM1优化HM2
