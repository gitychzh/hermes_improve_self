# R54: HM2优化 — UPSTREAM_TIMEOUT 50→52 (+2s)

## 📊 数据收集 (HM1 30min窗口，2026-06-26 17:50 UTC)

### 环境变量 (HM1容器当前)
- `UPSTREAM_TIMEOUT=50` (R52: 48→50, 上次优化)
- `TIER_TIMEOUT_BUDGET_S=96` (R44: 94→96)
- `MIN_OUTBOUND_INTERVAL_S=14.0` (R42: 13.5→14.0)
- `KEY_COOLDOWN_S=38.0` (R19: 35→38, 稳定)
- `TIER_COOLDOWN_S=82` (R45: 84→82)
- `HM_CONNECT_RESERVE_S=22` (R29: 21→22, 稳定)

### 请求统计 (hm_requests, 30min)
| 指标 | 值 |
|---|---|
| 总请求 | 1,131 |
| fallback | 1,018 (90.0%) |
| direct | 113 (10.0%) |
| fallback平均延迟 | 21,286ms |
| direct平均延迟 | 16,581ms |

### 错误分布 (hm_tier_attempts, 30min)
| 错误类型 | 计数 | 平均耗时 |
|---|---|---|
| 429_nv_rate_limit | 1,063 | - |
| NVCFPexecTimeout | 76 | 30,355ms |
| NVCFPexecConnectionResetError | 51 | 1,887ms |
| budget_exhausted_after_connect | 5 | 797ms |
| NVCFPexecRemoteDisconnected | 4 | 1,210ms |

### Tier分布
- glm5.1_hm_nv: 1,114次尝试 (93.8%全部尝试)
- deepseek_hm_nv: 79次尝试 (76 timeout, 5 budget_exhausted, 4 remote_disc)
- kimi_hm_nv: 1次尝试

### Deepseek超时桶分布 (76 NVCFPexecTimeout事件)
```
<20s:   25 (32.9%)
20-25s:  6 (7.9%)
25-30s:  6 (7.9%)
30-35s:  5 (6.6%)
>40s:   32 (42.1%)  ← 最大桶, 目标
```

### 每条Key的Deepseek超时
```
k0: 11 timeout + 2 budget → <20s=4, 25-30s=3, >40s=4
k1: 16 timeout + 1 budget → <20s=6, 20-25s=1, 25-30s=1, 30-35s=1, >40s=6
k2: 17 timeout → <20s=4, 20-25s=1, 25-30s=1, 30-35s=1, >40s=10
k3: 14 timeout + 2 budget → <20s=5, 20-25s=4, >40s=5
k4: 17 timeout → <20s=6, 25-30s=1, 30-35s=3, >40s=7
```

### 日志级别计数
- SSLEOF: 1次 (极低)
- ConnectionResetError: 51次 (NVCF基础设施级)
- all_tiers_exhausted: 2次 (0-tier, tiers_tried_count=0, avg_dur=180,404ms)

### 最近10条请求延迟
```
request_id  | tier_model      | duration_ms | fallback | key_cycle_429s | error_type | tiers_tried | nv_key_idx
8435fbae    | deepseek_hm_nv  | 22280       | t        | 0              |            | 2           | 2
9118ceba    | deepseek_hm_nv  | 12855       | t        | 0              |            | 2           | 1
c5da9403    | deepseek_hm_nv  | 8022        | t        | 0              |            | 2           | 0
41ca918f    | deepseek_hm_nv  | 18583       | t        | 0              |            | 2           | 4
59135f9e    | deepseek_hm_nv  | 8773        | t        | 0              |            | 2           | 3
aae793f7    | deepseek_hm_nv  | 19920       | t        | 5              |            | 2           | 2
ba9adad9    | deepseek_hm_nv  | 42597       | t        | 0              |            | 2           | 1
9ac1639d    | deepseek_hm_nv  | 14518       | t        | 0              |            | 2           | 1
ad6e1d70    | deepseek_hm_nv  | 10854       | t        | 0              |            | 2           | 4
c88037a9    | deepseek_hm_nv  | 31093       | t        | 5              |            | 2           | 3
```
全10条均为deepseek fallback, 延迟范围 8-42s, 2条有key_cycle_429s=5 (glm5.1失败后切换)

---

## 🔍 诊断

**>40s桶 = 32 (42.1%)** — 深寻超时桶中绝对最大, 确认UPSTREAM_TIMEOUT扩展轨迹依旧是正确优化向量。

在UPSTREAM=50: 1st attempt=50s, 2nd=24s。>40s桶32事件 (42.1%) 代表深寻完成耗时40-50s范围 (NVCF基础设施级预算耗尽)。R52从48→50 (+2s)后未见明显下降 (33→32, -3%), 表明50-52s边界仍需捕获。

**决策**: UPSTREAM_TIMEOUT 50→52 (+2s), 单参数变更, 少改多轮。

### 预算重算 (UPSTREAM=52, BUDGET=96, RESERVE=22)
- 1st attempt: min(52, 96-22=74) = 52s
- 剩余: 96-52 = 44s
- 2nd attempt: max(10, min(52, 44-22=22)) = 22s

2nd attempt从24s→22s (-2s), 1st attempt获得+2s (50→52s)。净效果: 捕获50-52s NVCF边界完成, 减少进入2nd-attempt fallback周期的请求。

**轨迹**: R10(40→42) → R46(42→44) → R48(44→46) → R50(46→48) → R52(48→50) → **R54**(50→52)
六次连续+2s增量 (R10起算), 全部单参数, 全部针对>40s深寻超时桶。

**2nd-attempt headroom预警**: 当前22s, 覆盖<20s桶 (25事件, 32.9%) + 小部分20-25s桶。2nd-attempt已接近20s下限。R52已验证: 2nd=24s时仍能处理大部分20-25s区间。若继续+2s到54, 2nd=20s (临界)。需在R54后评估是否需BUDGET/KEY_COOLDOWN调整以恢复2nd-attempt headroom。

---

## ⚙️ 优化执行

### 变更: `UPSTREAM_TIMEOUT` 50→52 (+2s)

```yaml
# docker-compose.yml line 417 (hm40006 service)
UPSTREAM_TIMEOUT: "52"  # R54: 50→52 +2s upstream timeout
```

**操作步骤**:
1. ✅ 备份: `cp docker-compose.yml docker-compose.yml.bak.R54`
2. ✅ 修改: `sed -i '417s/"50"/"52"/' docker-compose.yml`
3. ✅ 注释更新: `sed -i '417s/# R52:.*$/# R54: .../' docker-compose.yml`
4. ✅ 部署: `docker compose up -d hm40006` (容器重建+启动)
5. ✅ 验证: `docker exec hm40006 env | grep UPSTREAM_TIMEOUT` → 52
6. ✅ 完整性: 其他参数不变 (BUDGET=96, RESERVE=22, MIN_INTERVAL=14.0, KEY_COOLDOWN=38.0, TIER_COOLDOWN=82)

### 验证输出
```
UPSTREAM_TIMEOUT=52 ✓
TIER_TIMEOUT_BUDGET_S=96 ✓
MIN_OUTBOUND_INTERVAL_S=14.0 ✓
KEY_COOLDOWN_S=38.0 ✓
TIER_COOLDOWN_S=82 ✓
HM_CONNECT_RESERVE_S=22 ✓
hm40006 Up 51 seconds (healthy) ✓
```

---

## 📈 预期效果
- **NVCFPexecTimeout >40s桶**: 32→25-28 (↓ 12-22%, 捕获50-52s边界完成)
- **NVCFPexecTimeout 总计**: 76→67-72 (↓ 5-12%)
- **fallback率**: 90.0%→88-89% (↓ 1-2%, 更多1st attempt成功)
- **请求延迟**: 保持稳定 (深寻延迟 ~15-40s, 持续)
- **ConnectionResetError**: 51→47-50 (↓ 2-8%, 1st attempt更多完成=更少re-attempt)
- **SSLEOF**: 1→1-3 (极低水平持续)
- **0-tier**: 2→1-2 (RESERVE=22饱和, 极低)
- **少改多轮**: 单参数+2s, 渐进收敛

---

## ⚠️ 约束遵守
- ✅ **铁律:只改HM1不改HM2** — 2026-06-26 17:50 UTC确认
- ✅ **不停止/重启mihomo** — 无systemctl/无pkill/无docker stop
- ✅ **少改多轮** — 单参数变更, 渐进优化
- ✅ **无HM2修改** — 仅HM1的 `/opt/cc-infra/docker-compose.yml:417`
- ✅ **Post-deploy验证** — 所有参数确认, 容器健康

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记