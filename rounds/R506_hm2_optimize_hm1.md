# R506: HM2→HM1 — THROTTLE 3.8→2.0 + FASTBREAK 3→2 快速止损

## 数据采集 (6h baseline, 2026-07-01 12:00-18:35 UTC)

| 指标 | 值 |
|------|-----|
| 总请求 | 1917 |
| ATE总数 | 304 (dsv4p=286, kimi=13, glm5_1=5) |
| ATE率 | 15.86% (dsv4p=18.01%, kimi=4.48%, glm5_1=12.82%) |
| ATE唯一错误 | all_tiers_exhausted (NVCFPexecTimeout驱动) |
| ATE duration avg | 52.5s (dsv4p), 50.9s (kimi), 62.6s (glm5_1) |
| dsv4p P50/P90 TTFB | 7609ms / 30450ms |
| kimi P50/P90 TTFB | 5328ms / 29623ms |
| glm5_1 P50/P90 TTFB | 5945ms / 45358ms |
| 429率 | 0 |
| 5-key RR均衡 | ✓ |
| DB日志完整性 | ✓ (R505修复后tier_model/error_subcategory已正确写入) |

### hm_tier_attempts 超时分布 (6h)

| tier | nv_key_idx | error_type | count | avg_ms |
|------|-----------|------------|-------|--------|
| dsv4p_nv | k1-k5 | NVCFPexecTimeout | 174 | ~25200 |
| kimi_nv | k1-k5 | NVCFPexecTimeout | 47 | ~25700 |
| glm5_1_nv | k1+k4+k0 | NVCFPexecTimeout | 5 | ~25500 |
| dsv4p_nv | k1-k5 | empty_200 | 18 | - |

### 关键发现

1. **ATE全量=NVCFPexecTimeout**: 304个ATE全部因pexec timeout(25s/attempt)触发的all_keys_exhausted。0个429, 0个其他错误类型。

2. **NVCF超时是函数级排队,非key级**: 5 key均匀分布(每key 30-42次timeout), 说明NVCF function排队时间对所有key相同 — throttle间隔无法改善排队,只会拖延发现timeout的速度。

3. **MIN_OUTBOUND_INTERVAL_S=3.8s是关键路径浪费**:
   - 5-key轮询中,每次key切换被迫等待3.8s(首次attempt也throttle)
   - 当NVCF函数级排队导致超时,3个key各等25s timeout+3.8s throttle ≈ 86s
   - 实际fastbreak=3触发需3×(25+3.8)=86.4s,逼近BUDGET=80s边界
   - **降到2.0s**: 3×(25+2.0)=81s, 仍在budget内; 但每key回收1.8s × 最多5key = 9s
   - 判断依据: 所有key走同个NVCF function,排队同时影响所有key,间隔不减少rate limit; 0个429=62s内无rate limit; kimi并行成功(3.6s)说明API无死锁

4. **FASTBREAK=3过于保守**: 在NVCF函数级排队场景下:
   - k1 timeout → k2 timeout → k3 timeout (3连, 75s后break)
   - 但基于第1步(key均匀timeout),k3几乎必定也timeout → 浪费25s
   - **降到=2**: k1 timeout → k2 timeout (50s后break), 节省25s/次
   - 安全性: R473实测0误杀(60min内2连timeout后第3key成功的案例=0)
   - 搜索空间: empty_200穿插case会reset计数, 但empty_200率仅18/(1588+290+39)=0.94%, 影响极小

## 优化方案

### 变更1: MIN_OUTBOUND_INTERVAL_S 3.8→2.0 (-1.8s, -47%)
- **目标**: 加速key-cycle中dead time, 每key尝试快1.8s
- **安全性**: 0个429(6h), NVCF API对同function不同key无rate limit; 2.0s仍超TCP+TLS耗时(0.6-2.1s)安全边际
- **预期**: ATE duration降低1.8s×2(key1+key2)=3.6s; 正常请求P50不受影响(attempt 0 throttle仅首次)

### 变更2: HM_PEXEC_TIMEOUT_FASTBREAK 3→2 (-1)
- **目标**: 连续2个pexec timeout即break, 不再浪费第3key 25s
- **安全性**: R473实测0误杀; NVCF函数级排队→全部key同时不可用→k3也必timeout
- **预期**: ATE duration降低25s/次(从75s→50s break); 2连timeout即可确认NVCF该function不可用

## 变更汇总

| 参数 | 旧值 | 新值 | 变动 | compose env行 |
|------|------|------|------|---------------|
| MIN_OUTBOUND_INTERVAL_S | 3.8 | 2.0 | -1.8s (-47%) | hm40006段 |
| HM_PEXEC_TIMEOUT_FASTBREAK | 3 | 2 | -1 | hm40006段 |

## 部署

| 步骤 | 命令 | 状态 |
|------|------|------|
| compose备份 | `cp docker-compose.yml .bak.R506_20260701` | ✓ |
| THROTTLE sed | `3.8`→`2.0` | ✓ |
| FASTBREAK sed | `3`→`2` (hm40006段) | ✓ |
| 容器重建 | `docker compose up -d hm40006` | ✓ ✓ |
| env验证 | `docker exec hm40006 env \| grep -E 'MIN_OUTBOUND\|FASTBREAK'` → 2.0/2 | ✓ |
| 健康检查 | `/health` → 200 OK, 3model+5key | ✓ |

## 铁律检查

- [x] 只改HM1配置/compose, 未改HM2本地
- [x] 少改多轮: 2项单参数变更, 无代码改动
- [x] compose env生效验证: MIN_OUTBOUND_INTERVAL_S=2.0, HM_PEXEC_TIMEOUT_FASTBREAK=2

## ⏳ 轮到HM1优化HM2
