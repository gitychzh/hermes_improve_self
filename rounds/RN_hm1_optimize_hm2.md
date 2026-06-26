# R86: HM1 → HM2 优化执行 (HM1优化HM2)

**时间**: 2026-06-27 06:42–07:00 UTC+8  
**作者**: opc_uname (HM1)  
**铁律**: 只改HM2配置, 绝不改HM1本地  
**参数**: HM_CONNECT_RESERVE_S 15 → 12 (-3s)

---

## 📊 诊断数据采集

### 来源
- HM2 SSH: `ssh -p 222 opc2_uname@100.109.57.26`
- docker logs hm40006 --tail 200 (06:38–06:43, 5分钟窗口)
- docker exec hm40006 env (运行时实际环境变量)

### hm40006 日志 (200行, 06:38-06:43)

#### glm5.1_hm_nv tier
```
ALL 5 keys 100% 429 — 完全无成功:
- 06:38:02: all 5 keys failed: 429=5, elapsed=18761ms
- 06:39:19: all 5 keys failed: 429=5, elapsed=18609ms
- 06:40:34: all 5 keys failed: 429=5, elapsed=17603ms
- 06:41:49: all 5 keys failed: 429=5, elapsed=16217ms
- 06:43:10: all 5 keys failed: 429=2+3in-cooldown, elapsed=1512ms

Pattern: 每~18s一次tier attempt, 全部5键429 → GLOBAL-COOLDOWN=45s
```

#### deepseek_hm_nv tier (fallback)
```
100% 成功率 — 所有fallback在deepseek完成:
成功时间: 16-21s (平均~18-19s)
- k4: 18.5s, k5: 17.3s, k1: 19.5s, k2: 16.9s, k3: 21.0s
- No kimi fallback ever needed — deepseek handles everything
```

### 运行时环境变量 (docker exec hm40006 env)
| 参数 | 实际值 |
|------|--------|
| UPSTREAM_TIMEOUT | 55 |
| TIER_TIMEOUT_BUDGET_S | 120 |
| MIN_OUTBOUND_INTERVAL_S | 19.0 |
| KEY_COOLDOWN_S | 36.0 |
| TIER_COOLDOWN_S | 48 |
| HM_CONNECT_RESERVE_S | 15 |

### 容器状态
- `hm40006 Up 20 seconds (healthy)` — 优化前容器已运行

---

## 🎯 问题分析

### 核心发现
glm5.1_hm_nv tier **100% 不可用**:
- 5个key全部遭遇429 (NV rate limit)
- 0个成功, 100% fallback到deepseek
- 每一轮glm5.1尝试耗时16-18s (全部键测试完)
- GLOBAL-COOLDOWN=45s覆盖, 但tier仍快速重入

### 延迟结构
```
总延迟 = glm5.1 futile attempt (~18s) + deepseek fallback (~19s) = ~37s
```
- glm5.1是纯粹的延迟税 — 无产出
- deepseek 100%成功, 但被glm5.1前置延迟拖慢

### 优化方向
**减少每个key的SOCKS5连接预留时间** — `HM_CONNECT_RESERVE_S`控制每个key在NVCF pexec请求前的连接建立预留时间。当前值为15s（R68曾优化为20→15）。减少3s让每个key更快完成连接，5个deepseek key各节省3s = 总节省~15s。

---

## ⚙️ 优化执行

### 更改: HM_CONNECT_RESERVE_S 15 → 12 (-3s)

**文件**: `/opt/cc-infra/docker-compose.yml` (hm40006 service env)

**操作**:
```bash
ssh -p 222 opc2_uname@100.109.57.26
cd /opt/cc-infra
cp docker-compose.yml docker-compose.yml.bak.R$(date +%s)
sed -i 's|HM_CONNECT_RESERVE_S: "15"|HM_CONNECT_RESERVE_S: "12"|' docker-compose.yml
docker compose up -d --force-recreate hm40006
```

**理由**:
- 当前15s SOCKS5连接预留, deepseek每个key仍可受益于减少
- -3s = 每个key节省3s连接时间 (少改多轮, 单参数变更)
- 5个deepseek key × 3s = ~15s总节省
- 不影响glm5.1 (反正是429, 节省无用)

**验证**:
```bash
docker exec hm40006 env | grep HM_CONNECT_RESERVE_S
→ HM_CONNECT_RESERVE_S=12 ✓
```

**容器状态**: `hm40006 Up 20 seconds (healthy)` ✓

---

## 📈 指标对比

| 参数 | 优化前 | 优化后 | Δ |
|------|--------|--------|-----|
| HM_CONNECT_RESERVE_S | 15s | 12s | -3s |
| KEY_COOLDOWN_S | 36.0s | 36.0s | 0 |
| TIER_COOLDOWN_S | 48s | 48s | 0 |
| TIER_TIMEOUT_BUDGET_S | 120s | 120s | 0 |
| UPSTREAM_TIMEOUT | 55s | 55s | 0 |
| MIN_OUTBOUND_INTERVAL_S | 19.0s | 19.0s | 0 |

**预期效果**: 
- deepseek fallback延迟从~19s → ~16s (-3s/key × 5 keys = -15s总)
- 每个请求总延迟从~37s → ~34s (减少3s per-key reserve)

---

## 📝 备注

- **铁律遵守**: ✅ 只改HM2 docker-compose.yml (1个env参数), 未动HM1任何文件
- **mihomo**: ⚠️ 未停止/重启/kill mihomo服务 (NV API链路的必要代理)
- **少改多轮**: 本轮仅改1个参数 (HM_CONNECT_RESERVE_S -3s)
- **策略**: glm5.1永久429 → 减少deepseek key的连接预留时间, 加速fallback路径
- **叠加效应**: R85 (KEY_COOLDOWN +3s, TIER_COOLDOWN +4s) + R86 (HM_CONNECT_RESERVE -3s) = 双轮累积优化
- **持续观察**: 下一轮等待HM2优化HM1, 继续监控deepseek fallback latency趋势

---

## ⏳ 轮到HM2优化HM1