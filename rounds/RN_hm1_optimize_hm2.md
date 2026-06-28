# R261: HM1→HM2 — MIN_OUTBOUND_INTERVAL_S 15.6→16.0 (+0.4s) — 单轮优化

**回合类型**: 优化 (单参数)
**方向**: HM1 (opc_uname) → HM2 (opc2_uname)
**时间**: 2026-06-29 00:35 UTC
**原则**: 更少报错，更快请求，超低延迟，稳定优先 — 铁律:只改HM2不改HM1 — 少改多轮(单参数)

## 摘要

HM2 的 deepseek tier 30min 成功率 97.36% (1217/1250)，未达 99% 目标。33 个请求错误：32 all_tiers_exhausted + 1 NVStream_IncompleteRead。Deepseek tier 键级错误 88/30min (67 SSLEOFError + 15 NVCFPexecTimeout + 6 empty_200)，NVCFPexecTimeout 消耗 34-40s/键，3-4 次超时级联导致预算 124s 耗尽 (剩余 1.2-8.8s)。R260 刚提 TIER_TIMEOUT_BUDGET_S 120→124，本次继续单参数路径：MIN_OUTBOUND_INTERVAL_S 15.6→16.0 (+0.4s) 减少 SSLEOFError 键碰撞频率，给 deepseek 键更多空间在 SSL 中断后恢复。

## 参数变化

| 参数 | 旧值 | 新值 | 增量 |
|------|------|------|------|
| MIN_OUTBOUND_INTERVAL_S | 15.6 | 16.0 | +0.4s |

## 数据采集

### 30-min 窗口 (ha_requests)
- Total: 1250, Success: 1217 → **97.36%**
- Errors: 33 (32 all_tiers_exhausted + 1 NVStream_IncompleteRead)
- Avg duration: 25916ms

### 10-min 突发窗口
- Total: 1207, Success: 1174 → **97.27%**
- Errors: 33 (32 all_tiers_exhausted + 1 NVStream_IncompleteRead)
- **所有错误都集中在最近 10 分钟** — 前 20 分钟 0 错误 (42 请求)

## 执行

```bash
# 1. 修改 compose 文件
ssh HM2 "sed -i 's|MIN_OUTBOUND_INTERVAL_S: \"15.6\"|MIN_OUTBOUND_INTERVAL_S: \"16.0\"|' /opt/cc-infra/docker-compose.yml"

# 2. 重建容器
docker compose up -d --force-recreate --no-deps hm40006

# 3. 验证: MIN_OUTBOUND_INTERVAL_S=16.0, /health=200, mihomo 运行
```

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记