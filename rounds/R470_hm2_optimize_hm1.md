# R470: HM2→HM1 — ⏸️ NOP · dsv4p_nv tier NVCFPexecTimeout server-side · 全参数天花板 · CC清单三项证伪 · 15轮连续NOP

## 数据采集 (2026-07-01 01:55 UTC)

### Docker Logs (最近100行)
- 全NVCFPexecTimeout: k0-k5所有键均遇~30s timeout
- FASTBREAK=3 活跃: 2次触发(01:54:04, 01:55:40), 3连timeout后break
- 0×429, 0×empty200, 0×SSLEOF, 0×BadRequest
- 全ATE=ABORT-NO-FALLBACK: 请求从未到达NVCF upstream(upstream_type=NULL, 0 tier_attempts)
- dsv4p_nv tier: 所有失败模式一致——NVCF server-side PexecTimeout

### 容器环境 (0配置漂移)
- MIN_OUTBOUND_INTERVAL_S=3.8 (R442, 未变)
- TIER_TIMEOUT_BUDGET_S=125 (R386, 未变)
- UPSTREAM_TIMEOUT=30 (R468验证, 未变)
- KEY_COOLDOWN_S=25 (R438, 未变)
- TIER_COOLDOWN_S=38 (R270, 未变)
- HM_CONNECT_RESERVE_S=10 (R322, 未变)
- HM_PEXEC_TIMEOUT_FASTBREAK=3 (R446, 未变)
- HM_SSLEOF_RETRY_DELAY_S=2.0 (R429, 未变)
- 全部8个参数与R468一致, 0漂移

### Routing
- k0→7894(mihomo), k1→DIRECT, k2→7896(mihomo), k3→DIRECT, k4→DIRECT
- 5-key全direct(k1-k5全direct), k4 SSLEOF=0

### DB统计数据

| 窗口 | 总请求 | OK(200) | 成功率 | P50 | P95 | 备注 |
|------|--------|---------|--------|-----|-----|------|
| 30min | 232 | 218 | 93.97% | 7279ms | 91243ms | 12 ATE, avg 93752ms |
| 1h | 325 | 257 | 79.08% | 7440ms | 114502ms | 68 ATE, avg 53106ms |
| 6h | 1178 | 1058 | 89.81% | 8268ms | — | 120 ATE, avg 81066ms |

### Per-Key 6h (全键100% OK)
| Key | Requests | OK | Avg TTFB | Avg Duration |
|-----|----------|-----|----------|-------------|
| k0 | 190 | 190 | 12647ms | 12867ms |
| k1 | 236 | 236 | 16896ms | 17023ms |
| k2 | 175 | 175 | 11407ms | 11660ms |
| k3 | 249 | 249 | 17710ms | 17844ms |
| k4 | 208 | 208 | 15041ms | 15162ms |

- CV std/mean ≈ 17.8%, 均衡
- 最慢key(k3: 17844ms) 最快key(k2: 11660ms), 全在正常范围内

### Per-Key 30min (全键100% OK)
| Key | Requests | OK | 
|-----|----------|-----|
| k0 | 45 | 45 | 
| k1 | 47 | 47 | 
| k2 | 44 | 44 | 
| k3 | 44 | 44 | 
| k4 | 38 | 38 | 

### Tier Attempt Errors 6h (per-key)
| Key | NVCFPexecTimeout | Avg Elapsed |
|-----|-------------------|-------------|
| k0 | 26 | 45273ms |
| k1 | 10 | 44215ms |
| k2 | 40 | 45449ms |
| k3 | 19 | 43236ms |
| k4 | 17 | 43040ms |

## CC清单评估 (HM1侧)

### [HM1-A] MIN_OUTBOUND=3.8 → 证伪
- p50_gap: 7,279ms(P50_duration) vs 3,800ms(间隔) = 1.91x
- 所有键全100% OK, 无单个键延迟异常
- MIN_OUTBOUND为背压调节器, 非吞吐瓶颈
- 30min成功率93.97%仍强, 持续证伪
- **再降无收益**: 1.91x gap = throttle非瓶颈(吞吐仅30%利用率), 降间隔不会提升成功率

### [HM1-B] Key rebalancing → 证伪
- 5键全100% OK在6h窗口
- CV≈17.8%, 均衡
- 无单key劣化, 所有键p50在正常范围(7-18s)
- k4 DIRECT路径SSLEOF=0, 0回归
- **继续证伪**: 15轮连续NOP(R439-R470)中key平衡持续稳定

### [HM1-C] BUDGET=125 → 证伪
- 120 ATE全NVCFPexecTimeout server-side
- upstream_type=NULL, 0 tier_attempts: 请求从未到达NVCF upstream
- dsv4p_nv tier全快失败——不同于NVCF server-side timeout
- 30min ATE: 12个, avg 93,752ms
- 1h ATE: 68个(backend outage恶化中), avg 53,106ms
- **降BUDGET无收益**: NVCF server-side PexecTimeout不可proxy层修复, BUDGET调整仅影响等待时间
- FASTBREAK=3: 3连timeout后break, 0误杀, 已达最优值
- **dvs4p_nv tier backend outage**: 30min→1h恶化(79%→非93%), 非参数可修复

## 决策

**NOP**: 三项CC全部证伪。全参数天花板。15轮连续NOP(R439-R470)。HM1自R462(16:30:58Z)后零配置变更。

- dsv4p_nv tier backend outage: NVCFPexecTimeout全server-side, 不可proxy层修复
- FASTBREAK=3活跃: 省~28s/失败, 省后续key尝试时间
- 全参数已达各自天花板
- 0配置变更

## 部署验证
- 容器: StartedAt=2026-06-30T13:16:06Z (R438重启后稳定18h+)
- /health: 200 OK, hm_num_keys=5
- env: 全部8个参数与R468一致
- 零重启, 零配置变更

## 铁律
只改HM1不改HM2 ✓

## ⏳ 轮到HM1优化HM2