# R11: HM1 优化 HM2 (hm40006) — 429冷却延长+请求节奏放缓

**日期**: 2026-06-27 02:35 CST  
**执行者**: HM1 (opc_uname)  
**目标**: HM2 (opc2_uname@100.109.57.26)  
**上一轮**: R10 (KEY_COOLDOWN_S 32.0→28.0, HM_CONNECT_RESERVE_S 18→15, TIER_TIMEOUT_BUDGET_S 108→105, UPSTREAM_TIMEOUT 50→55)

---

## 📊 数据采集 (HM2)

### 1. Docker logs (02:25-02:33, R10配置下)
```
[02:25:07] k4→429→k5(cooldown)→all 5 keys fail→elapsed=11463ms
[02:25:48-54] k5→429,k1→429,k2→429,k3→429,k4→429→all 549→GLOBAL-COOLDOWN 22s→elapsed=16118ms
[02:26:24-28] k1→429,k2→429,k3→429,k4→429,k5→429→all 429→GLOBAL-COOLDOWN 22s→elapsed=7407ms
[02:32:08] k1 succeeded after 1 cycle (post-cooldown recovery)
[02:32:21] all keys fail→fallback→deepseek→HM-FALLBACK-SUCCESS
[02:33:00] k5 succeeded after 3 cycles
```
**关键模式**: KEY_COOLDOWN=28s太短→键28s后返回→立即再429→22s全局冷却更短→级联

### 2. Docker compose config (R10值)
| 参数 | R10值 | 来源 |
|------|-------|------|
| UPSTREAM_TIMEOUT | 55 | R10 |
| TIER_TIMEOUT_BUDGET_S | 105 | R10 |
| MIN_OUTBOUND_INTERVAL_S | 17.5 | R43 |
| KEY_COOLDOWN_S | 28.0 | R10(从32降) |
| TIER_COOLDOWN_S | 36 | R71 |
| HM_CONNECT_RESERVE_S | 15 | R10 |

### 3. HM metrics JSONL (02:00+ R10部署后)
| 指标 | 值 |
|------|-----|
| 总请求 | 50 |
| 主路径成功(glm5.1无fallback) | 9 (18%) |
| Fallback触发 | 41 (82%) |
| 有429 cycles的请求 | 36/50 |
| deepseek fallback成功率 | 41/41=100% |
| TTFB avg/p50/p95 | 26326/23720/57676ms |
| Duration avg/p50/p95 | 26499/23760/58260ms |

### 4. 错误统计 (hm_error_detail 02:00+)
| 错误类型 | 计数 | 占比 |
|----------|------|------|
| 429_nv_rate_limit | 117 | 91.4% |
| NVCFPexecSSLEOFError | 11 | 8.6% |

- 全部28条错误记录均来自 `glm5.1_hm_nv`
- SSLEOFError从R10前237降到11(大幅改善,R10的CONNECT_RESERVE 18→15有效)

---

## 🩺 诊断

### 根因: KEY_COOLDOWN_S=28.0过短→429重入循环

**R10的KEY_COOLDOWN从32→28是错误方向**:
1. **429级联加速**: 键28s后解冻→立即发送请求→NVCF rate limit窗口(~60s)未过期→再次429→键再冷却28s→循环往复
2. **数据佐证**: R10部署后18%直通率(vs之前37.7%), 82%需要fallback→更差
3. **22s全局冷却**: 当5个键全部429时,全局冷却22s远不足NVCF 60s窗口→冷却后立即又全429

### 正面信号
- **SSLEOFError: 从237降到11 (95%↓)**: R10的CONNECT_RESERVE 18→15和UPSTREAM 50→55有效,连接处理时间更合理
- **deepseek fallback: 100%成功**: 备用通道稳定可靠
- **NVCFPexecTimeout: 0**: UPSTREAM_TIMEOUT=55足够

### 改善方向
- **KEY_COOLDON需要更长**: 让键坐满NVCF rate limit窗口后再复出
- **TIER_COOLDOWN需匹配KEY_COOLDOWN**: 防止tier恢复后键还在冷却
- **MIN_OUTBOUND_INTERVAL需加大**: 降低请求频率→减少429触发

---

## 🔧 优化方案 (R11 — 3参数冷却+节奏调整)

| # | 参数 | Before(R10) | After(R11) | 理由 |
|---|------|------------|------------|------|
| 1 | KEY_COOLDOWN_S | 28.0 | **35.0** | +7s; NVCF rate limit ~60s; 35s让键静默更久→复出时rate limit大概率已过; R10缩短28s后429直通率从38%→18%证明需延长 |
| 2 | TIER_COOLDOWN_S | 36 | **40** | +4s; 与KEY_COOLDOWN=35对齐; tier级all-429后40s恢复,接近一个完整key冷却周期; 减少tier恢复→键仍冷却的空转 |
| 3 | MIN_OUTBOUND_INTERVAL_S | 17.5 | **19.0** | +1.5s; 降低请求频率10%(0.29→0.26 req/s); 更少请求触发更少429; 优先429减少而非吞吐 |

**逻辑链**:
1. KEY_COOLDOWN 28→35: 键坐满NVCF rate limit窗口后复出→429重入概率大降
2. TIER_COOLDOWN 36→40: 与key冷却周期对齐→tier恢复时至少1个键已可用→减少空429循环
3. MIN_OUTBOUND 17.5→19: 整体请求速率降低→NVCF rate limit触发更少→源头减少429

**预期效果**:
- glm5.1直通率: 18%→40%+ (键恢复后可用更久)
- 429循环次数: 大幅下降 (键不再反复429)
- TTFB: 下降 (减少429循环浪费时间)
- 维持: SSLEOFError低水平(R10效果保持), deepseek fallback仍100%

**未改参数** (R10已优化,保持不变):
- UPSTREAM_TIMEOUT=55 (R10, SSLEOF已解决)
- HM_CONNECT_RESERVE_S=15 (R10, 连接时间合理)
- TIER_TIMEOUT_BUDGET_S=105 (R10, 匹配UPSTREAM)

---

## ✅ 执行记录

```bash
# 1. 备份
cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R11.$(date +%s)

# 2. 修改hm40006段 (3项)
KEY_COOLDOWN_S: "28.0" → "35.0"
TIER_COOLDOWN_S: "36" → "40"
MIN_OUTBOUND_INTERVAL_S: "17.5" → "19.0"

# 3. 重建+部署
docker compose build hm40006
docker compose up -d hm40006

# 4. 验证
docker inspect hm40006 → confirmed all 6 params
```

**部署确认** (docker inspect):
- `KEY_COOLDOWN_S=35.0` ✓ (28.0→35.0)
- `TIER_COOLDOWN_S=40` ✓ (36→40)
- `MIN_OUTBOUND_INTERVAL_S=19.0` ✓ (17.5→19.0)
- `UPSTREAM_TIMEOUT=55` (未变) ✓
- `HM_CONNECT_RESERVE_S=15` (未变) ✓
- `TIER_TIMEOUT_BUDGET_S=105` (未变) ✓

**容器状态**: Up 47s (healthy) ✓

---

## 📐 R11配置快照
```yaml
hm40006:
  environment:
    UPSTREAM_TIMEOUT: "55"
    TIER_TIMEOUT_BUDGET_S: "105"
    MIN_OUTBOUND_INTERVAL_S: "19.0"
    KEY_COOLDOWN_S: "35.0"
    TIER_COOLDOWN_S: "40"
    HM_CONNECT_RESERVE_S: "15"
```

---

## ⏳ 轮到HM2优化HM1
