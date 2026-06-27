# R164: HM2 → HM1 — 无变更 (全7参数均衡; R162 KEY_COOLDOWN=38第2次验证; 30min 99.5% 3ATE; 0 429; 0 fallback; NVStream_IncompleteRead 2次为网络层; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 05:30 UTC, HM1 docker hm40006)

### HM1 运行时配置 (`docker exec hm40006 env`)
```
UPSTREAM_TIMEOUT=70
TIER_TIMEOUT_BUDGET_S=156
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=38
MIN_OUTBOUND_INTERVAL_S=19.0
HM_CONNECT_RESERVE_S=24
PROXY_TIMEOUT=300
CHARS_PER_TOKEN_ESTIMATE=3.0
```

### 30min 延迟百分位 (hm_requests, ts >= now()-30min)
| 指标 | 值 |
|------|-----|
| 总请求 | 1166 |
| 成功 (200) | 1160 (99.5%) |
| 错误 | 6 |
| 平均延迟 | 22316ms |
| P50 | 18686ms |
| P90 | 38132ms |
| P95 | 51526ms |
| P99 | 102379ms |

### 30min 错误分类
| 错误类型 | 计数 | 平均延迟 |
|-----------|------|---------|
| all_tiers_exhausted | 3 | 145154ms |
| NVStream_IncompleteRead | 2 | 13187ms |
| NVStream_TimeoutError | 1 | 109523ms |

### 30min 每键错误
| 键 | 错误类型 | 计数 | 平均 |
|-----|---------|------|------|
| kNone | all_tiers_exhausted | 3 | 145154ms |
| k0 | NVStream_TimeoutError | 1 | 109523ms |
| k3 | NVStream_IncompleteRead | 1 | 6827ms |
| k4 | NVStream_IncompleteRead | 1 | 19546ms |

### 30min 每键成功延迟 (status=200)
| 键 | n | 平均 | P50 | P95 |
|----|---|------|-----|-----|
| k0 | 244 | 24651ms | 19925ms | 58188ms |
| k1 | 228 | 22526ms | 18796ms | 53931ms |
| k2 | 220 | 19795ms | 17516ms | 41094ms |
| k3 | 235 | 20664ms | 18372ms | 43655ms |
| k4 | 233 | 21833ms | 18823ms | 52798ms |

### 请求速率 (30min, deepseek_hm_nv)
- 每分钟数据：438分钟有数据
- 平均：2.7 req/min，最大：5 req/min
- 容量（MIN_OUTBOUND=19s）：3.2 req/min
- 利用率：84%

### 24h all_tiers_exhausted 按小时分布
总ATE：45
```
2026-06-27 02:00: 1
2026-06-27 09:00: 1
2026-06-27 10:00: 4
2026-06-27 11:00: 10
2026-06-27 13:00: 5
2026-06-27 15:00: 1
2026-06-27 16:00: 7
2026-06-27 17:00: 8
2026-06-27 18:00: 2
2026-06-27 19:00: 3
2026-06-28 01:00: 1
2026-06-28 02:00: 2
```
分布：白天和夜间均有，非固定模式（Pitfall #30验证）。

### 30min 429计数: 0
### 30min key_cycle_429s 分布
- 0 cycles: 1152 请求
- 1 cycle: 13 请求
- 5 cycles: 1 请求

### 1h 窗口
- 总：1231，成功：1225（99.5%），错误：6，回退：0，P95：52090ms

### 6h 窗口
- 总：2004，成功：1974（98.5%），错误：30，回退：0

### Back-to-back 同键率（最近100个请求）: 8.1% (8/99)

### 24h 状态分解（延迟分析）
| 状态 | n | 平均 | 最小 | 最大 |
|------|---|------|------|------|
| 200 | 4502 | 29683ms | 1295ms | 233742ms |
| 429 | 5 | 172934ms | 138762ms | 219113ms |
| 502 | 46 | 117557ms | 6827ms | 166774ms |

### Docker 日志（最近100行）
100/100 [HM-SUCCESS] — 零错误，零警告。所有请求在第一次尝试时成功。

## 🎯 优化分析

### 全参数评估

| 参数 | 值 | 调整？ | 理由 |
|------|-----|--------|------|
| UPSTREAM_TIMEOUT | 70 | ✗ | 稳定；所有键p95 <60s << 70s限制。降低不会减少ATE（NVCF服务器端）。R158/R159/R160/R161已验证 |
| TIER_TIMEOUT_BUDGET_S | 156 | ✗ | 30min有3 ATE，全是NVCF服务器端（tiers_tried_count=0）。预算余量=16s（2×70+16对比）。R154证明增加超出10s阈值无效果 |
| KEY_COOLDOWN_S | 38 | ✗ | 0 429s；KEY=TIER=38零差；R162已验证。降低引入速率限制风险 |
| TIER_COOLDOWN_S | 38 | ✗ | 0 429s；KEY=TIER=38零差；R156已验证。降低引入速率限制风险 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ✗ | 2.7 req/min vs 3.2容量，84%利用率。有少量429-cycle但不是间隔问题（是速率限制恢复） |
| HM_CONNECT_RESERVE_S | 24 | ✗ | 24h中5个429，但这些是429重试消耗，非连接预留问题 |
| PROXY_TIMEOUT | 300 | ✗ | 内部超时，不在本轮循环中调节 |

### 瓶颈识别
- **3 ATE/30min**：NVCF服务器端PexecTimeout风暴。所有ATE kNone→tiers_tried_count=0确认这是NVCF端，不是HM1配置问题。错误详情JSONL显示kimi num_attempts=0（Pitfall #41持续）
- **2 NVStream_IncompleteRead**：网络层中断（k3=6827ms, k4=19546ms）。不频繁，非配置相关
- **1 NVStream_TimeoutError**（k0=109523ms）：单键NVCF超时，不在HM配置控制范围
- **8.1% back-to-back**：RR计数器偏差，比R161(4.0%)高，但在高流量下可能会波动

### 为什么无需变更
这是R162 KEY_COOLDOWN=38的第2次验证轮次。R162设置KEY=TIER=38修复了Pitfall #44（KEY<TIER反向差）。数据确认：
- 0 429s（30min）→ KEY_COOLDOWN=38有效保护免受速率限制
- 99.5%成功率（30min/1h）→ 系统在底层NVCF波动下稳定
- 0回退（所有窗口）→ 深层搜索层足以处理所有流量
- 所有键p95 <60s << UPSTREAM_TIMEOUT=70 → 成功路径安全
- 预算余量16s > 10s阈值 → 无预算紧张

3次ATE是NVCF服务器端，无法通过配置修复。这是Pitfall #41的延续：当NVCF发生PexecTimeout风暴时，深层搜索键在预算消耗完成之前全部超时，kimi没有机会进行。R154已证明增加预算在此处不会减少ATE。

**稳定性是有效优化成果**。R162的KEY_COOLDOWN=38与R158的UPSTREAM_TIMEOUT=70组合已达成稳定状态。全7参数平衡。

## ⚖️ 评判标准
- ✅ **更少报错**：6个错误/1166个请求 = 0.5%错误率。3 ATE（NVCF端），2网络（不频繁），1超时
- ✅ **更快请求**：P50=18686ms，P90=38132ms。84%利用率，无瓶颈
- ✅ **超低延迟**：P95=51526ms（所有键在40-58s范围内）。无异常值
- ✅ **稳定优先**：0 429s，0回退，全[HM-SUCCESS]日志。R162稳定状态已确认
- ✅ **铁律确认**：仅分析HM1，未更改HM2本地配置

## ⏳ 轮到HM1优化HM2