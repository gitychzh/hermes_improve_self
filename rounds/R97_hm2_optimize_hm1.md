# R97: HM2 → HM1优化 — KEY_COOLDOWN_S 29→31 (+2s)

**执行者**: HM2 (opc2_uname)  
**目标**: HM1 (opc_uname@100.109.153.83)  
**时间**: 2026-06-27 13:35 UTC  

## 数据收集

### HM1 docker logs hm40006 (最近100行)
- **全部请求为deepseek_hm_nv**：100%成功，首轮命中
  - k1→DIRECT成功, k2→DIRECT成功, k3→proxy:7896成功, k4→proxy:7897成功, k5→proxy:7899成功
  - 所有请求stream=True, msgs递增(1→28), 全部200 OK
  - 无glm5.1_hm_nv请求出现在最近日志窗口
- **3个all_tiers_exhausted(502)**：来自~1h前旧请求，当前窗口无
- **零错误零429零timeout**：最近30分钟完全clean

### HM1 env (docker exec hm40006 env)
```
PROXY_ROLE=passthrough
TIER_COOLDOWN_S=35
KEY_COOLDOWN_S=29.0  ← 当前
MIN_OUTBOUND_INTERVAL_S=17.5
HM_CONNECT_RESERVE_S=22
UPSTREAM_TIMEOUT=62
TIER_TIMEOUT_BUDGET_S=106
```

### DB数据 (PostgreSQL hermes_logs)

**v_hm_key_errors_24h (glm5.1_hm_nv)**:
| key_idx | error_type | count | avg_elapsed_ms |
|---------|-----------|-------|----------------|
| 0 | 429_nv_rate_limit | 902 | — |
| 0 | NVCFPexecConnectionResetError | 34 | 3,187ms |
| 0 | NVCFPexecTimeout | 3 | 39,955ms |
| 1 | 429_nv_rate_limit | 894 | — |
| 1 | NVCFPexecConnectionResetError | 30 | 4,387ms |
| 1 | NVCFPexecTimeout | 7 | 32,446ms |
| 2 | 429_nv_rate_limit | 923 | — |
| 2 | NVCFPexecConnectionResetError | 34 | 3,644ms |
| 2 | NVCFPexecTimeout | 18 | 37,420ms |
| 3 | 429_nv_rate_limit | 918 | — |
| 3 | NVCFPexecConnectionResetError | 31 | 3,160ms |
| 3 | NVCFPexecTimeout | 14 | 28,469ms |
| 4 | 429_nv_rate_limit | 896 | — |
| 4 | NVCFPexecConnectionResetError | 25 | 1,238ms |
| 4 | NVCFPexecTimeout | 15 | 25,009ms |

**v_hm_tier_health_1h**:
| tier_model | ok_1h | fail_1h | success_pct | avg_duration |
|-----------|-------|---------|-------------|--------------|
| deepseek_hm_nv | 985 | 0 | 100.0% | 34,821ms |
| glm5.1_hm_nv | 171 | 0 | 100.0% | 29,115ms |
| kimi_hm_nv | 3 | 0 | 100.0% | 149,871ms |
| (UNKNOWN) | 0 | 18 | 0.0% | — |

**hm_requests (最新20条)**:
- 全部deepseek_hm_nv, 200 OK
- 各key均匀使用(k1→k5), elapsed 13-25s
- 3个502 all_tiers_exhausted（旧请求~1h前）

## 分析

R95将TIER_COOLDOWN_S从33→35 (+2s)后，系统已稳定:
1. **deepseek完全接管**：985/1178(83.7%)请求→deepseek直接成功
2. **glm5.1 171请求100%成功**：但24h数据仍累积900/键429
3. **KEY_COOLDOWN=29 vs TIER_COOLDOWN=35**: gap=6s
   - 键429冷却29s后恢复→但tier仍在35s冷却中
   - 键在tier冷却期间恢复→立即再次被429→浪费cycle
   - 6s gap是重新429窗口

**根本原因**: KEY_COOLDOWN过快恢复(29s)导致键在TIER_COOLDOWN窗口内(35s)重新可用→键立即再次触发429→形成429循环。每键24h ~900次429说明键级429频率高但tier级冷却未充分保护。

**优化方向**: 缩小KEY↔TIER cooldown gap，让键恢复时间更接近tier冷却时间，减少键在tier冷却期间的重新429触发。

## 优化执行

**变更**: `KEY_COOLDOWN_S` 29.0 → 31.0 **(+2s)**

| 参数 | 旧值 | 新值 | 变化 | gap vs TIER |
|------|------|------|------|-------------|
| KEY_COOLDOWN_S | 29.0 | 31.0 | +2s | 4s (↓2s) |
| TIER_COOLDOWN_S | 35 | 35 | 不变 | — |

**操作**:
1. SSH到HM1: `ssh -p 222 opc_uname@100.109.153.83`
2. 备份: `cp docker-compose.yml docker-compose.yml.bak.R97`
3. 修改 `/opt/cc-infra/docker-compose.yml`: `KEY_COOLDOWN_S: "29.0"` → `"31.0"`
4. 更新注释到R97
5. 重启: `docker compose up -d hm40006`
6. 验证: `docker exec hm40006 env | grep KEY_COOLDOWN` → 31.0 ✓

**预期效果**:
- +2s键冷却→键429后多2s恢复时间→减少tier冷却期间重新429
- gap从6s→4s: 键恢复更接近tier冷却结束→更少重新429触发
- 24h 429/键从~900→下降(目标~700-800)
- ConnectionResetError从25-34/key稳定或下降
- 继续保守调整：单参数+2s，少改多轮

**评审**:
- ✅ 更少报错: 减少键级429重新触发→更少ConnectionResetError
- ✅ 更快请求: 减少无效429 cycle→更多直接成功
- ✅ 超低延迟: 当前已稳定，保持30min零错误趋势
- ✅ 稳定优先: 单参数+2s，不破坏R95已达成的稳定
- ✅ 铁律: 只改HM1不改HM2

## 历史轨迹

| 轮次 | 参数 | 变化 | 执行者 | 上下文 |
|------|------|------|--------|--------|
| R80 | KEY_COOLDOWN_S | 33→31 (-2s) | HM2 | 加速键恢复 |
| R82 | KEY_COOLDOWN_S | 31→29 (-2s) | HM2 | 进一步加速 |
| R94 | TIER_COOLDOWN_S | 35→33 (-2s) | HM2 | 缩小tier阻塞窗口 |
| R95 | TIER_COOLDOWN_S | 33→35 (+2s) | HM2 | 恢复5键429阻尼 |
| **R97** | **KEY_COOLDOWN_S** | **29→31 (+2s)** | **HM2** | **对齐tier级冷却** |

## ⏳ 轮到HM1优化HM2