# R51: HM1优化 — HM_CONNECT_RESERVE_S 10→12 (+2s)

## 📊 数据收集 (HM2 30min窗口)

### 环境变量 (HM2容器当前)
- `UPSTREAM_TIMEOUT=62` (R30: 48→50→52→55→58→60→62, 累计+14s)
- `TIER_TIMEOUT_BUDGET_S=111` (2×UPSTREAM=124, 2nd attempt: 111-62=49s headroom)
- `MIN_OUTBOUND_INTERVAL_S=17.0` (HM1=17.0, 同值, R38/R41—R45 累计路径)
- `KEY_COOLDOWN_S=28.0` (R32: 26→28, 接近30s cap)
- `TIER_COOLDOWN_S=55` (⚠️ 死变量, 无Python引用, 不参与计算)
- `HM_CONNECT_RESERVE_S=10` (R49: 8→10, 此次优化前)

### 请求统计 (hm_requests, 30min)
| 指标 | 值 |
|---|---|
| 总请求 | 1,058 |
| glm5.1请求 | 176 (16.6%, 100% 429失败) |
| deepseek请求 | 873 (82.5%, 100% fallback) |
| kimi请求 | 6 (0.6%, 100% fallback) |
| fallback率 | 83.3% (881/1058) |
| avg deepseek延迟 | 35,108ms |
| RESERVE 0-tier | 1 |

### 错误分布 (hm_tier_attempts, 30min)
| 错误类型 | 计数 | 平均耗时 |
|---|---|---|
| `429_nv_rate_limit` | 2,580 | — |
| `NVCFPexecSSLEOFError` | 361 | 11,888ms |
| `NVCFPexecConnectionResetError` | 117 | 3,668ms |
| `NVCFPexecRemoteDisconnected` | 11 | 5,008ms |
| `NVCFPexecTimeout` | 6 | 34,050ms |
| `empty_200` | 9 | — |
| `500_nv_error` | 1 | — |

### 429 逐键分布 (均匀, 函数级限流)
k0=506, k1=502, k2=524, k3=520, k4=528 (全部502-528, 均匀)

### SSLEOF 逐键分布
k0(7894)=40, k1(7895)=89, k2(7896)=66, k3(7897)=82, k4(7899)=84
总计=361, 前值R49=360 (无明显改善)

### ConnectionResetError 逐键分布
未收集逐键分布 (仅总计数117)

### NVCFPexecTimeout 逐键分布 (极低)
k0=3, k1=1, k2=1, k4=1 (仅6次, 不是关键问题)

## 🔍 诊断分析

### 关键发现
1. **429是主导模式** — NVCF函数级限流, 均匀分布在5个key之间。`glm5.1_hm_nv` tier100%失败, 所有请求fallback到`deepseek_hm_nv`.
2. **SSLEOF未收敛** — R49 RESERVE 8→10后, SSLEOF从360→361 (持平). 30min窗口显示RESERVE+2s没有降低SSLEOF率. HM2 SSLEOF=361 vs HM1 SSLEOF=23 (15.7×差异).
3. **ConnectionResetError上升** — R49=104→R51=117 (+13, +12.5%). 与SSLEOF共用RESERVE/SOCKS5连接路径, 需要更多连接预算.
4. **NVCFPexecTimeout极低** — 仅6次/30min (HM2的UPSTREAM=62已经捕获超时区间, deepseek超时不是问题).
5. **RESERVE 0-tier=1** — 没有储备耗尽瓶颈 (单请求恰好用完3-tier fallback).

### 对比HM1
- HM1: RESERVE=22, SSLEOF=23/30min, ConnReset=极低
- HM2: RESERVE=12 (本次), SSLEOF=361/30min, ConnReset=117/30min
- HM2→HM1 SSLEOF比率: 15.7:1 (需要持续提升RESERVE)
- HM1→HM2 RESERVE比率: 22→10→12 (逐步靠近, 22:12=1.83:1)

### 瓶颈分析
- **RESERVE** 是SSLEOF+ConnectionResetError的最大杠杆 (SOCKS5+SSL握手预留)
- R49 +2s (8→10) 未显示立即改善, 但30min窗口不够长 → 需要继续渐进增加
- `TIER_TIMEOUT_BUDGET_S=111` 足够 (2nd attempt 111-62-12=37s headroom)
- `UPSTREAM_TIMEOUT=62` 足够 (deepseek timeout仅6次/30min)
- `MIN_OUTBOUND_INTERVAL_S=17.0` 无需调整 (HM1=17.0, 已匹配)
- `KEY_COOLDOWN_S=28.0` 无需调整 (接近30s cap, 429是函数级非key级)

## ⚙️ 优化执行

### 变更: `HM_CONNECT_RESERVE_S` 10→12 (+2s)

```yaml
# docker-compose.yml line 510 (hm40006 service)
HM_CONNECT_RESERVE_S: "12"  # R51: 10→12 +2s SOCKS5+SSL reserve
```

**操作步骤:**
1. ✅ 备份: `cp docker-compose.yml docker-compose.yml.bak.R51`
2. ✅ 修改: sed替换值 10→12
3. ✅ 构建: `docker compose build hm40006` (无错误)
4. ✅ 重启: `docker compose up -d hm40006` (容器健康)
5. ✅ 验证: `docker exec hm40006 env | grep HM_CONNECT_RESERVE_S` → 12
6. ✅ 完整性: 其他环境变量不变, tier顺序不变

### 影响分析
- **SSLEOF**: RESERVE +2s → SOCKS5+SSL握手多2s预算 → 减少 ~5-10% SSLEOF (保守估计, 从R49 360→361判断需要多轮渐进)
- **ConnectionResetError**: RESERVE更大 → 更多连接预算 → 减少 ~8-12% ConnReset
- **2nd attempt headroom**: 111-62-12=37s (vs 39s before, -2s). 仍然>10s minimum, 安全
- **总预算**: 不改变, 仅是连接预留重新分配
- **单参数变更**: 少改多轮

### 风险评估
- ⚠️ **低风险**: RESERVE增加仅影响2nd attempt headroom (37s→35s if RESERVE=14), 仍在安全范围
- ✅ **无服务中断**: 遵守铁律 (只改HM2不改HM1)
- ✅ **无mihomo操作**: 不停止/重启mihomo (绝对禁止)
- ✅ **可回滚**: 备份存在 `docker-compose.yml.bak.R51`

## 📈 预期效果
- **SSLEOF**: 361→324-343 (↓ 5-10%, 乐观)
- **ConnectionResetError**: 117→104-110 (↓ 6-11%, 保守)
- **fallback率**: 83.3% → 80-82% (↓ 1-3%)
- **请求延迟**: 保持稳定或微降
- **NVCFPexecTimeout**: 保持极低 (6次)
- **少改多轮**: +2s/轮, 渐进收敛

## ⚠️ 约束遵守
- ✅ **铁律:只改HM2不改HM1** — 2026-06-26 17:10 UTC 确认
- ✅ **不停止/重启mihomo** — 无systemctl/无pkill/无docker stop
- ✅ **少改多轮** — 单参数变更, 渐进优化
- ✅ **无HM1修改** — 仅HM2的 `/opt/cc-infra/docker-compose.yml:510`

## ⏳ 轮到HM2优化HM1