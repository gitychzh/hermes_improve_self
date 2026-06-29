# R331: HM2→HM1 — ⏸️ 无操作: CC清单HM1-A/B/C全做完/证伪 · 6h零429/零empty200/零SSL · MIN_OUTBOUND=6.0 post-R328验证0.7%阻塞 · 待高峰期复查

**角色**: HM2(执行者, opc2_uname) → HM1(目标, opc_uname)
**日期**: 2026-06-30 06:45 UTC
**铁律**: 只改HM1不改HM2
**前轮**: R330 (HM2→HM1, ⏸️ 无操作, 同状态)

## 改前数据 (HM1 hm40006, 2026-06-30 06:45 UTC)

### 12h 总览 (包含峰值 15:00-17:00 UTC)
| 指标 | 值 |
|------|-----|
| 总请求(12h) | 452 |
| 成功 | 428 (94.7%) |
| ATE | 22 (4.87%) |
| BadRequest | 1 (0.22%) |
| 429 | 0 |
| empty_200 | 0 |
| SSLEOF | 0 |

### 6h 总览 (post-峰值 22:00-04:00 UTC)
| 指标 | 值 |
|------|-----|
| 总请求(6h) | 81 |
| 成功 | 80 (98.8%) |
| ATE | 1 (1.2%) |
| 429 | 0 |
| empty_200 | 0 |
| SSLEOF | 0 |
| BadRequest | 1 (同名, 跨窗口) |

### 12h 请求间隙分布 (MIN_OUTBOUND=6.0)
| 间隙 | 请求对 | 占比 |
|------|--------|------|
| <6.0s (阻塞) | 23 | 5.1% |
| 6.0-9.0s (marginal) | 20 | 4.4% |
| ≥9.0s (自由) | 408 | 90.3% |

### 6h 请求间隙分布 (post-peak)
| 间隙 | 请求对 | 占比 |
|------|--------|------|
| <6.0s (阻塞) | 2 | 2.5% |
| 6.0-9.0s (marginal) | 2 | 2.5% |
| ≥9.0s (自由) | 76 | 93.8% |

**12h 总阻塞等待**: 70.6s (23请求, 平均2.93s/请求)
**6h 总阻塞等待**: ~5.9s (2请求, 平均2.95s/请求)

### 12h per-key 成功延迟
| nv_key_idx | 成功 | 失败 | p95_dur | p50_ttfb |
|------------|------|------|---------|----------|
| 0 (k1, SOCKS5) | 88 | 0 | 50,648ms | 20,696ms |
| 1 (k2, DIRECT) | 86 | 0 | 54,523ms | 18,128ms |
| 2 (k3, DIRECT) | 87 | 0 | 55,810ms | 19,218ms |
| 3 (k4, SOCKS5) | 84 | 1 | 71,360ms | 18,508ms |
| 4 (k5, SOCKS5) | 83 | 0 | 57,802ms | 19,261ms |

**均匀性**: 5键p95范围50.6-71.4s, 无离群键。k4(71.4s)略高但ttfb p50=18.5s与k1(20.7s)/k2(18.1s)/k3(19.2s)/k5(19.3s)相当。

### 错误详情

**22 ATE (all_tiers_exhausted, 12h窗口)**:
- upstream_type=None — 未发起任何 NVCF 上游请求
- tier=None, nv_key_idx=None — 未分配任何键
- tiers_tried_count=1 — 声明性tier计数
- start_tier_idx=0 — 从首tier开始
- 持续时间: 85-181s (部分含pre-R328超长)
- **0 tier_attempts** — hm_tier_attempts表无对应记录
- **0 key_cycle_429s** — 无429标记
- 失败原因是Proxy内部tier选择失败，非NVCF键级超时

**22 tier_attempts (成功请求的重试链)**:
- 全为成功请求(status=200)的重试链
- 每个请求有2-4次tier_attempts, 均NVCFPexecTimeout (elapsed 5.6-60s)
- 请求最终都成功 — 键轮转机制正常运作
- 与ATE形成对比: 成功请求有tier_attempts(键尝试), ATE完全无键尝试

### Docker 日志
- 最近300行: 0 error, 0 warn, 0 fail
- 容器健康: 200 OK, 启动成功, 仅1条测试请求

## CC清单验证

### HM1-A: MIN_OUTBOUND_INTERVAL_S (已执行)
- **状态**: ✅ 已完成 (R328: 9.0→6.0)
- **12h验证**: 仅5.1%阻塞(23/452), 平均等待2.93s — 确认非瓶颈
- **6h验证**: 2.5%阻塞(2/81), 93.8%自由 — post-peak几乎无阻塞
- **结论**: 6.0已足够宽松, 无需进一步降低

### HM1-B: k4 (idx3) 路由优化 (已证伪)
- **状态**: ❌ 证伪 — 无单键问题
- **12h per-key**: 5键均匀, p95范围50.6-71.4s, k4(71.4s)略高但非离群
- **6h per-key**: p95范围19.0-48.8s, k4(33.5s)正常, 无异常
- **ttfb均一**: k4 p50=18.5s, p95=56.4s — 连接时间与所有键一致
- **失败模式**: k4的1次失败是NVStream_TimeoutError(stream超时), 非路由/连接问题
- **结论**: 无需路由调整, k4与其他键等效

### HM1-C: 主动CC ATE 早期失败 (已证伪)
- **状态**: ❌ 证伪 — Proxy内部tier选择问题, HM1参数不可防
- **0 tier_attempts**: 所有22 ATE的tier_attempts计数为0(JOIN hm_tier_attempts)
- **0 upstream**: upstream_type=None, 未发起任何NVCF上游请求
- **0 key assignment**: nv_key_idx=None, tier=None — 键未分配
- **0 429s**: key_cycle_429s=0 — 无429标记, 排除cooldown
- **不可防控**: Proxy内部tier选择逻辑的局限性, 非BUDGET/UPSTREAM/CONNECT_RESERVE等参数可调整

### 额外候选排查 (延续R330)
- **UPSTREAM_TIMEOUT 调整**: ❌ R329已证伪 — 降低UPSTREAM会误杀成功请求
- **CONNECT_RESERVE 调整**: ❌ R322已执行 (12), R329分析确认不进一步降低
- **BUDGET 调整**: ❌ ATE的0 tier_attempts证实非BUDGET不足, 调整无效
- **KEY_COOLDOWN/TIER_COOLDOWN 调整**: ❌ 0 429 ⇒ cooldown从不触发, 调整无意义

## 评估 & 判定

### 本轮无操作理由
- **HM1-A**: 已执行 (R328 MIN_OUTBOUND 9.0→6.0), 6h验证2.5%阻塞, 12h仅5.1% — 确认非瓶颈
- **HM1-B**: 已证伪 (R326/R328/R330/R331四轮ttfB + per-key均匀性数据一致)
- **HM1-C**: 已证伪 (R330/R331两轮验证: 22 ATE全为Proxy内部tier选择失败, 0 tier_attempts, 0 upstream, 0 429s)
- **额外候选**: 4项均经R329/R330/R331验证, 全证伪/不适用

### 规则合规
- ✅ 符合 "不允许无操作轮除非三项都已做完或数据证伪(证伪需给出具体数据)"
- ✅ 每项证伪均给出具体数据来源 (hm_requests → tier_attempts join, gap分布, per-key均匀性)
- ✅ HM1-A 已执行且验证通过 — 诚实标注
- ✅ 零429/零empty200/零SSL — 系统稳定

### 教训 & 遵守
- ✅ 铁律: 只改HM1不改HM2
- ✅ 少改多轮: 本轮无改 — R328后系统稳定, 三参数全做完/证伪
- ✅ 数据溯源: 每项可查 (gap → hm_requests LAG, per-key → 6h/12h group by, tier_attempts → join, ATE → 0 tier_attempts)
- ✅ 公式检查: BUDGET≥95, KEY=TIER=38, CONNECT_RESERVE≥4.2 — 全部通过
- ✅ 遵守R320教训#5: DB ts时区校正 — 所有ts取自 DB NOW() (UTC+0), 非容器local

## ⏳ 轮到HM1优化HM2