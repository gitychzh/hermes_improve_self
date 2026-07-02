# R566 (HM2→HM1): NOP — HM1 持续全路径失联, SSH/Tailscale/ICMP 全超时, 零数据零改动

## 📅 执行时间
UTC 2026-07-02 18:51+ (HM2 cron 触发)

## 🎯 本轮目标
1. SSH 到 HM1 收集 hm-40006 链路数据
2. 基于数据执行单参数优化
3. 因 HM1 全员失联，转为状态记录轮

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
100.109.153.83   opcsname-1   gitychzh@   linux   active; relay "sfo"; offline, last seen 31m ago, tx 47736 rx 0
```
- **Online**: False
- **Last seen**: ~31 分钟前
- **数据收发**: tx 47736 rx 0（无回程流量）
- **中继/直连**: 均不可达，无 CurAddr

## ✅ 优化决策：NOP (零改动)

| 参数 | 前值 | 新值 | 变动 | 铁律 |
|------|------|------|------|------|
| *(全部)* | — | — | **无** | ✅只改HM1不改HM2 |

### 决策依据
1. **全路径 100% 丢包**：SSH/Tailscale/ICMP 全通路中断，零通信路径
2. **无数据不瞎改**：无法执行 `docker logs`、`docker exec env`、DB 查询，盲调参数 = 冒险
3. **连续三轮 NOP 叠加**：R564→R565→R566，HM1 已离线并失联超过 8h，优先排查主机/网络/进程恢复
4. **稳定性优先**：保持 HM1 最后已知有效配置（R563），待恢复后补漂移检测

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
| SSH 探测 | `ssh -p 222 opc_uname@100.109.153.83` | ❌ timed out | 18:51+ |
| Tailscale 探测 | `tailscale ping -c 3 100.109.153.83` | ❌ no reply | 18:51+ |
| ICMP 探测 | `ping -c 3 100.109.153.83` | ❌ 100% loss | 18:51+ |
| 配置改动 | *(跳过)* | — | — |
| 容器操作 | *(跳过)* | — | — |

## 📈 预期效果
- **无**：零改动，零预期效果
- HM1 恢复在线后建议：立即执行 `docker exec hm40006 env` + DB 近 2h 查询，补漂移检测

## ⚠️ 风险与建议
1. **持续离线**：HM1 主机或 Tailscale daemon/iptables 故障，需远程人工排查
2. **数据空洞**：R563 之后无新 DB 记录，无法验证 TIER_TIMEOUT_BUDGET_S=95 对 kimi_nv 边缘请求的救助效果
3. **dsv4p 硬故障状态未知**：离线期间无法确认 dsv4p_nv 是否恢复
4. **恢复后首件事**：
   - `docker ps` 确认 hm40006 状态
   - `docker exec hm40006 env | grep -E "TIMEOUT|BUDGET|COOLDOWN|FASTBREAK"`
   - 查 DB 近 2h max_succ / p95 / error 分布
   - 若 dsv4p 恢复 → 优先回调 TIER_TIMEOUT_BUDGET_S 至 85（R540 曾验证安全值）

## 📝 备注
- **铁律维持**：本轮零 HM1 改动，零 HM2 改动
- 网络连通性优先于参数优化
- 连续 NOP 轮次意味着 HM1 已进入硬离线状态，长期失联应考虑基础设施恢复而非参数调优

## 🔄 轮次交接
- 本方 (HM2→HM1) 完成本轮（NOP 状态记录）
- 如检测脚本识别到此文件末尾的 `⏳` 标记，即触发 HM1 侧下轮优化

## ⏳ 轮到HM1优化HM2
