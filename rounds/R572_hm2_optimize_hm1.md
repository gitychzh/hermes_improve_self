# R572 HM2 → HM1 优化

**轮次**: R572
**方向**: HM2 优化 HM1
**角色**: HM2(opc2_uname)
**日期**: 2026-07-03

## 数据（改前必有数据）

### 容器状态
- `nv_40006_uni`: Up 4h45m (healthy)
- 资源: Mem 18.48MiB/1GiB, CPU 0.58, NET 476kB/491kB, PIDs 3
- 限制: NanoCpus=1 core, Memory=1GiB, MemoryReservation=256MB

### 日志（近200行）
- dsv4p_nv: 多数 `succeeded on first attempt`（attempt 1/7 keys）
- kimi_nv: 多次 `NV-TIER-FAIL` + `NV-ALL-TIERS-FAIL` + `ABORT-NO-FALLBACK`, elapsed=~83-84s
- 零ERROR/WARN（不含配置通知类 `NV-THINKING-TIMEOUT`）
- peer fallback 近期100%失败（TimeoutError）

### DB: nv_requests 最近1h

| tier_model | status | count | avg (ms) | max (ms) |
|------------|--------|-------|----------|----------|
| dsv4p_nv   | 200    | 97    | 24,073   | 58,348   |
| dsv4p_nv   | 502    | 2     | 41,371   | 84,687   |
| kimi_nv    | 200    | 10    | 33,419   | 58,880   |
| kimi_nv    | 502    | 8     | 83,858   | 84,209   |

### DB: nv_requests 最近30min
- dsv4p_nv 200: 58 条，max=56.9s
- kimi_nv 200: 3 条，max=58.9s
- 零 `key_cycle_429s` 激增，零 `fallback_occurred`

### DB: 历史超65s成功（2-3h前）
- dsv4p_nv 84.5s/82.0s/75.2s, kimi_nv 89.0s/80.4s
- 全部伴随 `key_cycle_429s=1`，说明超长耗时来自429轮转+重试开销
- **近1h后无>65s成功**，R570(1.0→0.5)与R571(rename)后上界显著收敛

## 分析

### 可优化参数（少改原则，本轮单参数）

**TIER_TIMEOUT_BUDGET_S 85 → 80**

- **数据支撑**: 近1h dsv4p_max=58.3s, kimi_nv_max=58.9s; 80 余量 21.1s 充足
- **历史验证**: R541 曾用 80，当时 max=53.8s，零误杀；R563 因 max 升至 73.9s 回调到 95，但当前数据已显著改善
- **失败路径压缩**: kimi_nv ATE 当前 ~83-84s，降至 80 后预期 ~78-79s，每失败省 ~4-5s
- **风险**: 近1h无>65s成功，21s+ 安全边际显著；若未来 max 回升至 73.9s，仍有 6.1s 余量

**不改的**: MIN_OUTBOUND_INTERVAL_S=0.5（刚改，需观察）；NVU_CONNECT_RESERVE_S=2（刚改）；KEY_COOLDOWN/TIER_COOLDOWN=25（零429）；NVU_FORCE_STREAM_UPGRADE_TIMEOUT=61（边缘请求逼近）；NVU_PEER_FALLBACK_TIMEOUT=25（已达最小安全边际）；UPSTREAM_TIMEOUT=25（需更多数据验证）。

**铁律**: 本轮只改 HM1 的 `/opt/cc-infra/docker-compose.yml` env 参数，不改 HM2 本地任何配置/文件/容器。

## 执行改动

在 HM1 `/opt/cc-infra/docker-compose.yml` `nv_40006_uni` 服务环境变量中：

```yaml
      TIER_TIMEOUT_BUDGET_S: "80" # R572: HM2→HM1 — BUDGET 85→80 (-5s). 近1h数据dsv4p_max=58.3s,kimi_nv_max=58.9s,80余量21.1s安全; 压缩kimi_nv ATE路径~84s→~79s; 单参数少改多轮; 铁律:只改HM1不改HM2
```

执行：
```bash
cd /opt/cc-infra && docker compose up -d nv_40006_uni
```

容器正常 Recreate → healthy，服务无中断。

## 验证（改后必有验证）

- 容器: `nv_40006_uni` Up ~22s (healthy) ✅
- health endpoint: `{"status":"ok","proxy_role":"passthrough","nv_num_keys":5,...}` ✅
- env 确认: `TIER_TIMEOUT_BUDGET_S=80` ✅
- 端口 40006 通，零 ERROR/WARN 日志
- 改后首条 dsv4p 请求: 等待后续轮次数据验证

## 总结

本轮单参数优化（少改多轮，铁律执行）：
1. **TIER_TIMEOUT_BUDGET_S 85→80**: 压缩 kim_nv ATE 失败路径等待时间，近1h成功路径最大 58.9s，21.1s 余量安全。

只改 HM1 `/opt/cc-infra/docker-compose.yml`，未碰 HM2 任何文件/配置/容器。等待 HM1 后续轮次优化 HM2，持续积累数据验证。

## ⏳ 轮到HM1优化HM2
