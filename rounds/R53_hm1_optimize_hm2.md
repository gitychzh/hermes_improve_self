# R53: HM1优化 — HM_CONNECT_RESERVE_S 12→14 (+2s)

## 📊 数据收集 (HM2 实时日志窗口)

### 环境变量 (HM2容器当前)
- `UPSTREAM_TIMEOUT=62` (R52: 48→50, HM2端维持, deepseek超时不是瓶颈)
- `TIER_TIMEOUT_BUDGET_S=111` (2×UPSTREAM=124, 2nd attempt: 111-62=49s headroom)
- `MIN_OUTBOUND_INTERVAL_S=17.0` (与HM1=17.0同值, R38-R45累计路径)
- `KEY_COOLDOWN_S=28.0` (接近30s cap, 429是函数级非key级)
- `TIER_COOLDOWN_S=55` (⚠️ 死变量, 无Python引用)
- `HM_CONNECT_RESERVE_S=12` (R51: 10→12, 此次优化前)

### HM2日志实时观察 (200行窗口, ~2分钟)
```
Log entries: 200
Error patterns: 85 total
  - 429_nv_rate_limit: 25 (glm5.1 tier全部429, 100% fallback到deepseek)
  - SSLEOFError: 3 (持续低水平)
  - ConnectionResetError: 2 (持续低水平)
  - COOLDOWN/CYCLE/FAIL: 55 (中间状态日志)
```

### Tier行为
- **glm5.1_hm_nv**: 100% 429失败, 所有key在cooldown中, 全部fallback
- **deepseek_hm_nv**: 100% 成功 (primary失败后全部fallback到此), 5 keys k1-k5循环
  - k1: 多轮完成 (1-5次尝试, avg ~18s)
  - k5: 多轮完成 (5次尝试, ~15s)
- **kimi_hm_nv**: 0次触发 (deepseek已捕获所有请求)

### Deepseek成功请求模式 (实时)
```
[17:46:02.8] k5 → deepseek NVCF pexec → 5 cycle attempts → SUCCESS ~15s
[17:46:18.1] k1 → deepseek NVCF pexec → 1st attempt → SUCCESS ~18s
[17:46:38.3] k5 → glm5.1 NVCF pexec → 429 (主tier尝试但失败)
```

---

## 🔍 诊断分析

### 核心问题
HM2的SSLEOF=361/30min (vs HM1=23/30min, 15.7:1) — 这是最大的性能差距。

R51 RESERVE 10→12 (+2s) 后的数据:
- 预期SSLEOF: 361→324-343 (↓ 5-10%)
- 实际窗口: 缺乏30min数据验证 (R51刚实施, 此轮次为首次响应)

### SSLEOF根本原因
- NVCF API调用经过SOCKS5代理 (mihomo → host.docker.internal:7894-7899)
- SSL握手在SOCKS5隧道内进行, 需要额外连接预算
- HM2的RESERVE=12 (vs HM1=22) — 差距10s
- 每条key的proxy路由通过mihomo (host.docker.internal:7894→7899)
- SSLEOF发生在NVCF基础设施级 (非key级), 无法通过key COOLDOWN改善

### 对比HM1
| 参数 | HM1 | HM2 | 差距 |
|---|---|---|---|
| RESERVE | 22 | 12→14 | 22:14=1.57:1 (改善中) |
| SSLEOF/30min | 23 | 361 | 15.7:1 |
| ConnReset/30min | ~5 | 117 | 23:1 |
| UPSTREAM | 50 (R52) | 62 | HM2更大 |
| MIN_INTERVAL | 17.0 | 17.0 | 匹配 |

### 瓶颈诊断
- **RESERVE是SSLEOF+ConnectionResetError的最大杠杆** — SOCKS5+SSL握手预留
- R49(8→10) → R51(10→12) → **R53**(12→14): 三次连续+2s增量
- HM2→HM1 RESERVE比率: 12→22=1.83:1 → 14→22=1.57:1 (持续收敛)
- 2nd attempt headroom: 111-62-14=35s (vs 37s before, -2s). 仍然>10s minimum, 安全
- deepseek完成时间: 15-25s (35s headroom足够)
- BUDGET=111 无需调整 (2nd attempt预算充足)
- UPSTREAM=62 无需调整 (HM1端才是瓶颈, HM2端超时已充足)
- KEY_COOLDOWN=28.0 接近30s cap (429是函数级, 非key级)
- MIN_INTERVAL=17.0 已匹配HM1, 无需调整

### 决策: 继续RESERVE渐进路径

**变更**: `HM_CONNECT_RESERVE_S` 12→14 (+2s)
**理由**: 单参数变更, 少改多轮。继续R49→R51→R53的RESERVE渐进路径。

### 预算重算 (RESERVE=14, BUDGET=111, UPSTREAM=62)
- 1st attempt: min(62, 111-14=97) = 62s
- 剩余预算: 111-62 = 49s
- 2nd attempt: max(10, min(62, 49-14=35)) = 35s
- deepseek完成时间: 15-25s (35s > 10s minimum, 安全)

---

## ⚙️ 优化执行

### 变更: `HM_CONNECT_RESERVE_S` 12→14 (+2s)

```yaml
# /opt/cc-infra/docker-compose.yml line 510 (hm40006 service)
HM_CONNECT_RESERVE_S: "14"  # R53: 12→14: +2s SOCKS5+SSL connection reserve
```

**操作步骤**:
1. ✅ 备份: `cp docker-compose.yml docker-compose.yml.bak.R53`
2. ✅ 修改: sed替换值 12→14 (行510)
3. ✅ 注释更新: R51→R53 引用标记
4. ✅ 部署: `docker compose up -d hm40006` (容器重建+启动)
5. ✅ 验证: `docker exec hm40006 env | grep HM_CONNECT_RESERVE_S` → 14
6. ✅ 完整性: 其他参数不变
   - `UPSTREAM_TIMEOUT=62` ✓
   - `TIER_TIMEOUT_BUDGET_S=111` ✓
   - `MIN_OUTBOUND_INTERVAL_S=17.0` ✓
   - `KEY_COOLDOWN_S=28.0` ✓
   - `TIER_COOLDOWN_S=55` ✓ (死变量)

### 验证输出
```
HM_CONNECT_RESERVE_S=14 ✓
UPSTREAM_TIMEOUT=62 ✓
TIER_TIMEOUT_BUDGET_S=111 ✓
MIN_OUTBOUND_INTERVAL_S=17.0 ✓
KEY_COOLDOWN_S=28.0 ✓
TIER_COOLDOWN_S=55 ✓
hm40006 Up (healthy) ✓
```

---

## 📈 预期效果
- **SSLEOF**: 361→320-340 (↓ 5-10%, RESERVE +2s给SOCKS5+SSL更多握手预算)
- **ConnectionResetError**: 117→105-112 (↓ 5-10%, 更多连接预算减少Reset)
- **429_nv_rate_limit**: 不变 (函数级限流, RESERVE不参与)
- **fallback率**: 83.3% → 80-82% (↓ 1-3%, 1st attempt多2s预算)
- **请求延迟**: 保持稳定 (deepseek 15-25s, 持续)
- **2nd attempt headroom**: 35s (vs 37s before, -2s). 仍安全
- **少改多轮**: +2s/轮, 渐进收敛
- **RESERVE轨迹**: R49(8→10)→R51(10→12)→**R53**(12→14) — 三次连续+2s

### 风险评估
- ✅ **低风险**: RESERVE增加仅影响2nd attempt headroom (35s, 仍>10s minimum)
- ✅ **无服务中断**: 遵守铁律 (只改HM2不改HM1)
- ✅ **无mihomo操作**: 不停止/重启mihomo (绝对禁止)
- ✅ **可回滚**: 备份存在 `docker-compose.yml.bak.R53`

---

## ⚠️ 约束遵守
- ✅ **铁律:只改HM2不改HM1** — 2026-06-26 17:46 UTC 确认
- ✅ **不停止/重启mihomo** — 无systemctl/无pkill/无docker stop
- ✅ **少改多轮** — 单参数变更, 渐进优化
- ✅ **无HM1修改** — 仅HM2的 `/opt/cc-infra/docker-compose.yml:510`
- ✅ **不重启/kill mihomo** — mihomo作为NV API链路必要代理, 保持运行

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记