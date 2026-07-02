# R565 (HM2→HM1): NOP — HM1 持续离线, 全路径 100% 丢包, 零数据零改动

## 📅 执行时间
UTC 2026-07-02 10:44:36 (HM2 cron 触发)

## 🎯 本轮目标
1. SSH 到 HM1 收集 hm-40006 数据
2. 基于数据执行单参数优化
3. 因 HM1 仍不可达，转为状态记录轮

## 📊 HM1 数据收集
全部失败。

### 连通性测试
| 路径 | 命令 | 结果 |
|------|------|------|
| SSH :222 | `ssh -p 222 opc_uname@100.109.153.83 "echo test"` | Connection timed out |
| Tailscale | `tailscale ping -c 3 100.109.153.83` | timed out, no reply |
| ICMP | `ping -c 3 100.109.153.83` | 100% packet loss |

### Tailscale 状态
```
100.109.153.83   opcsname-1   linux   active; relay "sfo"; offline, last seen 21m ago, tx 30264 rx 0
```
- **Online**: False
- **Last seen**: ~21 分钟前
- **数据收发**: tx 30264 rx 0（无回程流量）
- **直连/中继**: 均不可达

## ✅ 优化决策：NOP (零改动)

| 参数 | 前值 | 新值 | 变动 | 铁律 |
|------|------|------|------|------|
| *(全部)* | — | — | **无** | ✅只改HM1不改HM2 |

### 决策依据
1. **网络不可达**：SSH/Tailscale/ICMP 全路径中断，无法获取 docker logs、env、DB 数据
2. **无数据不瞎改**：缺少实时数据支撑，任何参数调整均为盲飞
3. **稳定性优先**：保持 R563 已生效配置，避免离线期间配置漂移

### HM1 最后已知有效配置 (R563)
```yaml
UPSTREAM_TIMEOUT: 25
MIN_OUTBOUND_INTERVAL_S: 1.0
KEY_COOLDOWN_S: 25
TIER_COOLDOWN_S: 25
HM_CONNECT_RESERVE_S: 3
HM_PEXEC_TIMEOUT_FASTBREAK: 1
HM_EMPTY_200_FASTBREAK: 1
HM_FORCE_STREAM_UPGRADE_TIMEOUT: 61
HM_PEER_FALLBACK_TIMEOUT: 25
HM_SSLEOF_RETRY_DELAY_S: 1.0
TIER_TIMEOUT_BUDGET_S: 95
```

## 🔧 执行过程
| 步骤 | 命令 | 结果 | 时间 |
|------|------|------|------|
| SSH 探测 | `ssh -p 222 opc_uname@100.109.153.83` | ❌ timed out | 10:44 UTC |
| Tailscale 探测 | `tailscale ping -c 3 100.109.153.83` | ❌ no reply | 10:44 UTC |
| ICMP 探测 | `ping -c 3 100.109.153.83` | ❌ 100% loss | 10:44 UTC |
| 配置改动 | *(跳过)* | — | — |
| 容器操作 | *(跳过)* | — | — |

## 📈 预期效果
- **无**：零改动，零预期效果
- HM1 恢复在线后建议：立即执行 `docker exec hm40006 env` + DB 近 2h 查询，补漂移检测

## ⚠️ 风险与建议
1. **持续离线**：HM1 主机或 Tailscale daemon 可能故障，需人工排查
2. **数据空洞**：无法验证 TIER_TIMEOUT_BUDGET_S=95 对 kimi_nv 边缘请求的救助效果
3. **恢复后首件事**：核对 11 个活跃容器参数 → 查 DB max_succ/p95/error → 若 dsv4p 恢复可回调 BUDGET 至 85

## 📝 备注
- **铁律维持**：本轮零 HM1 改动，零 HM2 改动
- 网络连通性优先于参数优化
- 本轮为状态占位，保证轮次连续性

## 🔄 轮次交接
- 本方 (HM2→HM1) 完成本轮（NOP 状态记录）
- 如检测脚本识别到此文件末尾的 `⏳` 标记，即触发 HM1 侧下轮优化

## ⏳ 轮到HM1优化HM2
