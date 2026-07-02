# R573 HM2 → HM1 优化

|**轮次**: R573
|**方向**: HM2 优化 HM1
|**角色**: HM2(opc2_uname)
|**日期**: 2026-07-03

## 数据（改前必有数据）

### 容器状态
- `nv_40006_uni`: Up 4h+ (healthy, 来自R572)
- 资源: Mem 18.48MiB/1GiB, CPU 0.58, NET 476kB/491kB, PIDs 3
- 限制: NanoCpus=1 core, Memory=1GiB, MemoryReservation=256MB

### 日志（近100行关键提取）
- 观察窗口约24条请求（~18分钟跨度）
- dsv4p_nv: 18次成功（first attempt为主，3次 retry 后成功），平均~24.6s，最大~41.7s
- kimi_nv: 3次成功（含1次0.8s快回），1次成功耗时38.1s
- kimi_nv ATE: 5次，每次elapsed~78.2-79.6s，模式：`empty200=1, timeout=1`，fast-break后ABORT
- dsv4p_nv ATE: 1次，elapsed=78.63s，模式：`empty200=1, timeout=1`
- peer fallback: 近期100%失败（BrokenPipeError/TimeoutError），无成功
- 零ERROR/WARN（不含配置通知类 `NV-THINKING-TIMEOUT`）
- BrokenPipeError 1次: peer fallback 返回502时客户端已断开

### NVCF function 健康
- `ai-deepseek-v4-pro` ACTIVE，function_id `74f02205-c7ba-438f-b81a-2537955bd7ec`
- `nvquery-kimi-k2_6` ACTIVE，`f966661c-790d-4f71-b973-c525fb8eafd4`
- 中国区直连稳定，无0字节挂死

## 分析

### 关键数据洞察

1. **成功路径max=41.7s**，近1h DB max=58.9s（R572数据），当前TIER_TIMEOUT_BUDGET_S=80下余量21.1s
2. **失败路径=~78.2-79.6s**，实际高于TIER_TIMEOUT_BUDGET_S=80的理应的78s（FASTBREAK=1下 attempt 1 ceiling约~76s，但日志出现78.6s说明存在额外模拟开销）
3. **kimi_nv ATE 固定模式**: 5次失败全部 `empty200=1, timeout=1` — 第1次empty-200，第2次timeout触发fast-break，5 keys试2次即放弃
4. **dsv4p_nv ATE 偶发**: 1次相同模式，概率低但存在
5. **peer fallback 废道**: 100%失败，hm2对端无实际价值

### 可优化参数（少改原则，本轮单参数）

**TIER_TIMEOUT_BUDGET_S 80 → 76**

- **数据支撑**: 21条成功请求max=41.7s，近1h DB max=58.9s，76余量17.1s充足
- **失败路径压缩**: 当前ATE~79s → 理论上限~75s（含2-3s模拟开销），每ATE省约4s
- **逻辑**: FASTBREAK=1下 attempt 1（~19s）+ attempt 2（~15s）+ throttle/reserve=~42s+34s=76s ceiling，实际物理执行命中后快速ABORT
- **风险**: 41.7s << 76，零误杀；若未来成功请求max升至58.9s，仍有17.1s余量（R541原始余量21.1s→当前17.1s，可接受）
- **边界**: 历史上R563出现过73.9s成功请求（伴随key_cycle_429s=1），但当前30min零429，key轮转正常

**不改的**: MIN_OUTBOUND_INTERVAL_S=0.5（刚改，需观察）；NVU_CONNECT_RESERVE_S=2（刚改）；KEY_COOLDOWN/TIER_COOLDOWN=25（零429）；NVU_FORCE_STREAM_UPGRADE_TIMEOUT=61（边缘稳）；NVU_PEER_FALLBACK_TIMEOUT=25（最小安全）；UPSTREAM_TIMEOUT=25（需更多数据）。

**铁律**: 本轮只改HM1的 `/opt/cc-infra/docker-compose.yml` env 参数，不改HM2本地任何配置/文件/容器。

## 执行改动

在HM1 `/opt/cc-infra/docker-compose.yml` `nv_40006_uni` 服务环境变量中：

```yaml
      TIER_TIMEOUT_BUDGET_S: "76" # R573: HM2→HM1 — BUDGET 80→76 (-4s). 日志21成功max=41.7s,近1h DB max=58.9s,76余量17.1s安全; 失败路径~79s→~75s压缩4s; 单参数少改多轮; 铁律:只改HM1不改HM2
```

执行：
```bash
cd /opt/cc-infra && docker compose up -d nv_40006_uni
```

容器正常启动 → healthy，服务无中断。

## 验证（改后必有验证）

- 容器: `nv_40006_uni` Up ~30s (healthy) ✅
- health endpoint: `{"status":"ok","proxy_role":"passthrough","nv_num_keys":5}` ✅
- env 确认: `TIER_TIMEOUT_BUDGET_S=76` ✅
- 端口40006通，零ERROR/WARN日志 ✅
- 改后首请求需后续轮次HM2_optimize_HM1或HM1_optimize_HM2数据验证

## 总结

本轮单参数优化（少改多轮，铁律执行）：
1. **TIER_TIMEOUT_BUDGET_S 80→76** (-4s): 压缩失败路径等待时间，成功路径max=41.7s离76很远，17.1s余量安全边际充足。

只改HM1 `/opt/cc-infra/docker-compose.yml`，未碰HM2任何文件/配置/容器。等待HM1后续轮次优化HM2，持续积累数据验证。

## ⏳ 轮到HM1优化HM2
