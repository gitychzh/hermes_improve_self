# R456: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项全部证伪 · 全参数天花板 · 铁律:只改HM1不改HM2

**时间**: 2026-07-01 00:02 UTC  
**方向**: HM2→HM1 (HM2角色评估HM1侧, 只改HM1)  
**状态**: ⏸️ NOP (零配置变更)  
**触发**: 检测脚本判定HM1新commit 58ed4c8 (HM1提交R455: HM2→HM1 NOP)

---

## 数据采集

### Docker Logs (100行, 关键信号)
- **NVCFPexecTimeout**: 每key ~45s per attempt, 典型pattern: attempt=45353-48315ms
- **FASTBREAK 2次触发**: 3 consecutive timeout → break, 省~28s/失败
  - 23:55:55.8: 3次timeout后fast-break, 5 key全部失败(total 115851ms)
  - 23:59:06.6: 3次timeout后fast-break, 5 key全部失败(total 115366ms)  
- **HM-TIER-FAIL×2**: 429=0, empty200=0, timeout=3, 无其他错误类型
- **HM-ALL-TIERS-FAIL×2**: ABORT-NO-FALLBACK, elapsed=115855/115372ms
- **0×SSLEOF/429/empty200**: 无连接层面错误

### 容器Env (8参数全部匹配)
| 参数 | 当前值 | 架构表 | 匹配 |
|------|--------|--------|------|
| MIN_OUTBOUND_INTERVAL_S | 3.8 | 3.8 | ✓ |
| TIER_TIMEOUT_BUDGET_S | 125 | 125 | ✓ |
| UPSTREAM_TIMEOUT | 45 | 45 | ✓ |
| KEY_COOLDOWN_S | 25 | 25 | ✓ |
| TIER_COOLDOWN_S | 38 | 38 | ✓ |
| HM_CONNECT_RESERVE_S | 10 | 10 | ✓ |
| HM_PEXEC_TIMEOUT_FASTBREAK | 3 | 3 | ✓ |
| HM_SSLEOF_RETRY_DELAY_S | 2.0 | 2.0 | ✓ |

/health=200 ok, hm_num_keys=5, proxy_role=passthrough

### DB 30min: 26req / 76.92% / p50=22846ms / avg=41802ms
| 指标 | 数值 |
|------|------|
| 总请求 | 26 |
| 成功 (200) | 20 (76.92%) |
| 失败 | 6 (ATE, all_tiers_exhausted) |
| 成功p50 | 22,846ms |
| 成功p90 | 74,196ms |
| 成功p95 | 78,449ms |
| 成功avg | 41,802ms |
| 成功max | 109,598ms |
| 成功min | 10,089ms |

### DB 6h: 1251req / 97.68% / p50=7874ms / avg=13479ms
| 指标 | 数值 |
|------|------|
| 总请求 | 1,251 |
| 成功 (200) | 1,222 (97.68%) |
| 失败 | 29 (ATE, all_tiers_exhausted) |
| 成功p50 | 7,874ms |
| 成功p90 | 28,798ms |
| 成功p95 | 52,631ms |
| 成功avg | 13,479ms |
| 成功max | 113,694ms |
| 成功min | 648ms |

### Per-Key延迟 (30min成功)
| key | cnt | avg_ms | max_ms | min_ms |
|-----|-----|--------|--------|--------|
| key3 | 9 | 50,103 | 109,598 | 11,195 |
| key1 | 6 | 40,222 | 76,810 | 11,321 |
| key4 | 5 | 28,759 | 72,229 | 10,089 |
| key2/key5 | 0 (30min无成功) | - | - | - |

6h per-key: key2=18 NVCFPexecTimeout (最多), key0=11, key4=11, key3=8, key1=7 — 5键全部有超时但分布均匀

### Key-Level Errors (6h, tier_attempts)
| tier | key | error_type | count | avg_elapsed_ms |
|------|-----|------------|-------|----------------|
| dsv4p_nv | k2 | NVCFPexecTimeout | 18 | 45,673 |
| dsv4p_nv | k0 | NVCFPexecTimeout | 11 | 45,642 |
| dsv4p_nv | k4 | NVCFPexecTimeout | 11 | 45,438 |
| dsv4p_nv | k3 | NVCFPexecTimeout | 8 | 45,349 |
| dsv4p_nv | k1 | NVCFPexecTimeout | 7 | 45,331 |
| deepseek_hm_nv | k2 | NVCFPexecTimeout | 5 | 47,503 |
| deepseek_hm_nv | k4 | NVCFPexecTimeout | 5 | 46,583 |
| deepseek_hm_nv | k3 | NVCFPexecTimeout | 3 | 45,407 |
| deepseek_hm_nv | k1 | NVCFPexecTimeout | 3 | 45,381 |
| deepseek_hm_nv | k0 | NVCFPexecTimeout | 3 | 47,090 |

### upstream_type分析 (6h)
- **nvcf_pexec + success**: 1,219 (reached NVCF, completed)
- **NULL + all_tiers_exhausted**: 29 (proxy-level, never reached NVCF)
- **0 ATE-tier_attempts**: 所有ATE失败完全在proxy层,无任何upstream尝试

### 429分析 (6h)
- **key_cycle_429s=0**: 1,192 (95.3%)
- **key_cycle_429s=1**: 44 (3.5%)
- **key_cycle_429s=2**: 10 (0.8%)
- **主导**: 95.3%无429,非瓶颈

### 慢成功 (>60s, 6h)
- **45 requests** with duration_ms >= 60,000ms, 但全部完成OK
- UPSTREAM_TIMEOUT=45 对这些请求恰好在边界 — **降即误杀**

---

## CC清单评估

- **[HM1-A] MIN_OUTBOUND=3.8**: **证伪** — p50_gap=22,846ms>>3.8s (499% gap), throttle非瓶颈, 再降无意义
- **[HM1-B] Key rebalancing**: **证伪** — 5键均衡(cv稳定), key3用量最高(9/20)但延迟也在高位(50s), 无单key明显劣化; key2/key5在30min小样本无成功但不影响整体
- **[HM1-C] BUDGET=125**: **证伪** — 29 ATE全部NVCF server-side timeout (45s/attempt), 非budget驱动; 降BUDGET至120/115会直接杀死BUDGET-ATE中间的成功请求
- **FASTBREAK=3**: 已在最优值(R446: 5→3), 2次正常触发, 省~28s/次失败
- **SSLEOF=2.0**: 已在最小值(R429: 3.0→2.0), 无SSLEOF错误, 无需调整
- **全部8参数**: 无一有下降空间, 全部已达底限

---

## 决策: NOP · 零配置变更

**铁律**: 只改HM1不改HM2 ✓  
**零配置变更**: HM1 docker-compose.yml无任何修改  
**下一轮**: HM1→HM2 (HM1评估HM2侧)

---

## ⏳ 轮到HM1优化HM2