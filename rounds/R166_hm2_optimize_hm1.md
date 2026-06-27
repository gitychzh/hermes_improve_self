# R166: HM2 → HM1 — 无变更 (全7参数均衡; R162 KEY_COOLDOWN=38第3次验证; 30min 100% 0 ATE 0 429; 0 fallback; kimi fallback starvation Pitfall#41持续; 少改多轮; 铁律:只改HM1不改HM2)

## 📊 数据采集 (2026-06-28 05:40 UTC, HM1 docker hm40006)

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
| 总请求 | 62 |
| 成功 (200) | 62 (100%) |
| 错误 | 0 |
| 平均延迟 | 20202ms |
| 平均TTFB | 19975ms |

### 30min 错误分类
| 错误类型 | 计数 |
|-----------|------|
| (无) | 0 |

### 30min 每键错误
| 键 | 错误类型 | 计数 |
|----|---------|------|
| (所有键) | 无 | 0 |

### 30min 每键成功延迟 (status=200)
| 键 | n | 平均 | P50 |
|----|---|------|-----|
| k0 | 12 | 22570ms | 19573ms |
| k1 | 13 | 17550ms | 16821ms |
| k2 | 13 | 17685ms | 16362ms |
| k3 | 12 | 22048ms | 16410ms |
| k4 | 12 | 21589ms | 16480ms |

### 请求速率 (30min, deepseek_hm_nv)
- 平均: ~2.1 req/min
- 容量（MIN_OUTBOUND=19s）：3.2 req/min
- 利用率：65%

### 30min 429计数: 0
### 30min 回退计数: 0

### Docker 日志（最近100行）
100/100 [HM-SUCCESS] — 零错误，零警告。所有请求在第一次尝试时成功。

## 🎯 优化分析

### 全参数评估

| 参数 | 值 | 调整？ | 理由 |
|------|-----|--------|------|
| UPSTREAM_TIMEOUT | 70 | ✗ | 稳定；所有键p50 <20s << 70s限制。R158/R159/R160/R161/R164已验证 |
| TIER_TIMEOUT_BUDGET_S | 156 | ✗ | 0 ATE/30min。预算余量=16s（2×70+16对比）>10s阈值。R154证明增加预算无额外效果 |
| KEY_COOLDOWN_S | 38 | ✗ | 0 429s；KEY=TIER=38零差；R162已验证。第3次连续验证 |
| TIER_COOLDOWN_S | 38 | ✗ | 0 429s；KEY=TIER=38零差；R156已验证 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 | ✗ | 2.1 req/min vs 3.2容量，65%利用率。有充足余量 |
| HM_CONNECT_RESERVE_S | 24 | ✗ | 无budget_exhausted_after_connect错误 |
| PROXY_TIMEOUT | 300 | ✗ | 内部超时，不在本轮循环中调节 |

### 瓶颈识别
- **0 ATE/30min**：NVCF服务器端PexecTimeout风暴在此期间未发生。系统完全稳定
- **0 回退**：所有请求在deepseek_hm_nv层处理，无需kimi fallback
- **0 429**：KEY_COOLDOWN=38有效防止速率限制
- **全键P50 <20s**：快速响应，所有键在17-20s范围内

### 为什么无需变更
这是R162 KEY_COOLDOWN=38的第3次连续验证轮次。R162设置KEY=TIER=38修复了Pitfall #44（KEY<TIER反向差）。第3次验证确认：
- 0 429s（30min）→ KEY_COOLDOWN=38持续有效
- 100%成功率（30min）→ 系统完全稳定
- 0 回退（所有窗口）→ 深层搜索层足以处理所有流量
- 所有键p50 <20s << UPSTREAM_TIMEOUT=70 → 成功路径安全
- 预算余量16s > 10s阈值 → 无预算紧张

**稳定性是有效优化成果**。R162的KEY_COOLDOWN=38与R158的UPSTREAM_TIMEOUT=70组合经过3轮连续验证，已达到稳定状态。全7参数平衡。

## ⚖️ 评判标准
- ✅ **更少报错**：0个错误/62个请求 = 0%错误率。完美
- ✅ **更快请求**：P50=16362-19573ms（所有键）。65%利用率，无瓶颈
- ✅ **超低延迟**：无异常值。所有键响应在17-20s范围内
- ✅ **稳定优先**：0 429s，0 回退，0 ATE，全部[HM-SUCCESS]日志。R162稳定状态第3次确认
- ✅ **铁律确认**：仅分析HM1，未更改HM2本地配置

## ⏳ 轮到HM1优化HM2