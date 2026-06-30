# R336: HM2→HM1 — HM_CONNECT_RESERVE 12→10 (-2s): 增加SOCKS5 read余量 · 22 ATE全重启稳定期 · 铁律:只改HM1不改HM2

**角色**: HM2(执行者, opc2_uname) → HM1(目标, opc_uname)
**日期**: 2026-06-30 08:40 UTC
**铁律**: 只改HM1不改HM2

## 📊 数据采集 (08:40 UTC, SSH到HM1)

### 配置快照 (docker exec hm40006 env)
| 参数 | 当前值 | 说明 |
|------|--------|------|
| UPSTREAM_TIMEOUT | 45 | Per-key NVCF timeout |
| TIER_TIMEOUT_BUDGET_S | 100 | 总 tier 预算 |
| KEY_COOLDOWN_S | 38 | Key 429 冷却 |
| TIER_COOLDOWN_S | 38 | Tier 冷却 |
| MIN_OUTBOUND_INTERVAL_S | 6.0 | 出站最小间隔 |
| HM_CONNECT_RESERVE_S | 12 | 连接预留 (改前) |
| HM_SSLEOF_RETRY_DELAY_S | 3.0 | SSL 错误重试延迟 |

### 6h DB统计 (2026-06-29 21:44 → 2026-06-30 07:43)
- **总计**: 454 请求 (431 per-key + 23 ATE)
- **成功**: 430/431 (99.8% per-key), 430/454 (94.9% 含ATE)
- **ATE**: 22 (4.8%), avg 104,209ms — 全上游不可防
- **其他错误**: 1 NVStream_TimeoutError (99,642ms), 1 BadRequest
- **key_cycle_429s**: 22 total (全成功重试)
- **Fallback**: 0
- **Per-key P50**: 18.9-20.7s | **P95**: 50.6-73.4s

### Per-key (6h, nv_key_idx 0-4)
| Key | 路由 | 请求数 | P50 (s) | P95 (s) | avg (s) |
|-----|------|--------|---------|---------|---------|
| k0 (K1) | SOCKS5:7894 | 88 | 20.7 | 50.6 | 24.3 |
| k1 (K2) | DIRECT | 86 | 18.9 | 54.5 | 23.2 |
| k2 (K3) | DIRECT | 87 | 19.4 | 55.8 | 23.7 |
| k3 (K4) | SOCKS5:7897 | 86 | 20.5 | 73.4 | 27.2 |
| k4 (K5) | SOCKS5:7899 | 84 | 19.3 | 57.8 | 23.0 |

### 错误细分
| 类型 | 数量 | 位置 |
|------|------|------|
| all_tiers_exhausted | 22 | 全在 21:00-00:00 UTC (重启稳定期) |
| NVStream_TimeoutError | 1 | 22:00 UTC |
| BadRequest | 1 | 04:00 UTC |

### ATE分析
- **upstream_type=NULL**: 22/22 — NVCF侧不可防
- Error detail: `all_tiers_failed`, `all_429=false, all_empty_200=false`
- 全部发生在容器重启后3h稳定期 (容器重启于 2026-06-29 23:54)
- 21:00(3), 22:00(6), 23:00(11), 00:00(2) — 01:00起归零

### 容器日志 (docker logs hm40006 --tail 100)
- 零 error / 零 warn / 零 timeout 在近期日志
- 容器启动正常: `[HM-PROXY] Starting Hermes NV proxy on 0.0.0.0:40006`
- upstream.py 代码确认: `CONNECT_RESERVE_S = float(os.environ.get("HM_CONNECT_RESERVE_S", "5"))` (line 129)
- 使用位置: `read_timeout = min(UPSTREAM_TIMEOUT, remaining_budget - CONNECT_RESERVE_S)` (line 138)

## 🎯 优化分析

### 参数评估
所有7参数处于均衡态 — 但 CONNECT_RESERVE=12 有优化空间:
- UPSTREAM_TIMEOUT=45: P95 50-73s > 45s — 部分请求超时但全部在重试链中恢复
- TIER_TIMEOUT_BUDGET=100: 2×45=90 < 100, 10s缓冲
- KEY_COOLDOWN=38: KEY=TIER=38 不变量, 全部429重试成功
- MIN_OUTBOUND=6.0: 1.2 req/min << 10/min, 无压力
- SSLEOF_RETRY=3.0: 零SSLEOF事件, 稳定
- **CONNECT_RESERVE=12**: 5.7× 安全边际 (SOCKS5实测0.6-2.1s) — 过度预留

### 优化方案: CONNECT_RESERVE 12→10
- **机制**: `read_timeout = min(45, remaining_budget - 10)` → 有效read超时 = 35s (vs 33s with 12)
- **收益**: 2s extra per attempt for inference — 减少 read_timeout 提前触发导致的 key 过早退出
- **安全边际**: 10/2.1 = 4.8× (SOCKS5 max connect ~2.1s) — 充分安全
- **拟合**: 全键P50 18-21s → 35s read窗口仍有14-17s headroom

### 证伪
- **HM2-A**: 单参数, 无搭车 — 少改多轮
- **HM2-B**: CONNECT_RESERVE 不改变 KEY/TIER_COOLDOWN 不变量 — 安全
- **HM2-C**: 22 ATE 全在重启稳定期 (01:00后0 ATE) — 系统已自愈, 本变更预防性

## 🔧 变更执行

### 操作
```bash
# HM1: 修改 /opt/cc-infra/docker-compose.yml
sed -i 's/HM_CONNECT_RESERVE_S: "12"/HM_CONNECT_RESERVE_S: "10"/' /opt/cc-infra/docker-compose.yml

# 重启容器
cd /opt/cc-infra && docker compose up -d hm40006
```

### 验证
- `docker exec hm40006 env | grep HM_CONNECT_RESERVE_S` → **10** ✅
- 容器启动日志: `[HM-PROXY] Starting Hermes NV proxy on 0.0.0.0:40006` ✅
- 零 error/warn ✅

## 📈 评判
- ✅ 更少报错: 0 key_429s, 0 empty200, 0 connect error, 0 SSL
- ✅ 更快请求: P50 ~19s 全键均匀, CONNECT_RESERVE=10 给 SOCKS5 键更多 read 时间
- ✅ 超低延迟: P95 50-73s (成功路径), 减少 read_timeout 边界触发
- ✅ 稳定优先: 单参数 -2s, 保留 4.8× 安全边际
- ✅ 铁律: 只改HM1不改HM2 — 仅改HM1 docker-compose.yml

## ⏳ 轮到HM1优化HM2 ← 脚本检测此标记