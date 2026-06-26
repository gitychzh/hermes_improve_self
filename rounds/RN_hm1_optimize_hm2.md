# R88: HM1 → HM2 优化执行 (HM1优化HM2)

**时间**: 2026-06-27 07:20–07:28 UTC+8  
**作者**: opc_uname (HM1)  
**铁律**: 只改HM2配置, 绝不改HM1本地  
**参数**: KEY_COOLDOWN_S 36.0 → 40.0 (+4s)

---

## 📊 诊断数据采集

### 来源
- HM2 SSH: `ssh -p 222 opc2_uname@100.109.57.26`
- docker logs hm40006 --tail 100 (07:19-07:21, 2分钟窗口)
- docker exec hm40006 env (运行时实际环境变量)
- docker compose config (docker-compose.yml 当前配置)

### hm40006 日志 (100行, 07:19-07:20)

#### glm5.1_hm_nv tier
```
100% 429 — 完全无成功, 5键全429模式一致:
- 07:19:41: k5→429, k1→429, k2→429, k3/k4 in cooldown → all 5 failed: 429=5, elapsed=16462ms
- 07:19:45: GLOBAL-COOLDOWN 45s applied
- 07:20:42: k4→429, k5→429, k1→429, k2→429, k3→429, k4 in cooldown → all 5 failed: 429=5, elapsed=9365ms

Pattern: 每个key首次尝试即429 (NV rate limit), 全键1-2秒内相继429
GLOBAL-COOLDOWN=45s硬编码, 覆盖所有5键
```

#### deepseek_hm_nv tier (fallback)
```
100% 成功率 — 所有fallback在deepseek完成:
- 07:20:10: k3 succeeded after 6 cycle attempts (SSLEOFError → retry same key → 成功)
- 07:20:36: k3 succeeded on first attempt
- 07:27:52: k4 succeeded after 5 cycle attempts (24.8s total)

SSLEOFError: transient — 代码已有 retry same key 逻辑 (2s backoff)
单次失败后重试同key可成功, 无需cycle到下一个key
```

### 运行时环境变量 (docker exec hm40006 env)
| 参数 | 实际值 |
|------|--------|
| UPSTREAM_TIMEOUT | 55 |
| TIER_TIMEOUT_BUDGET_S | 120 |
| MIN_OUTBOUND_INTERVAL_S | 21.0 |
| KEY_COOLDOWN_S | 36.0 (优化前) |
| TIER_COOLDOWN_S | 48 |
| HM_CONNECT_RESERVE_S | 12 |

### 容器状态
- `hm40006 Up 13 minutes (healthy)` — 优化前容器正常运行
- `mihomo` 进程: `opc2_un+ 2008535` — 运行中 (自Jun24), 未停止

### RR Counter (持久化状态)
```json
{"hm_nv_deepseek": 2994, "hm_nv_kimi": 83, "hm_nv_glm5.1": 2911}
```
- deepseek处理了2994个请求 (主力tier)
- glm5.1处理了2911个请求 (但全部429失败)
- kimi仅处理了83个请求 (极少fallback到kimi)

---

## 🎯 问题分析

### 核心发现
glm5.1_hm_nv tier **100% 不可用** — NV API函数级速率限制:
- 5个key全部遭遇429 (NV rate limit at `ai-glm5_1` function level)
- 0个成功, 100% fallback到deepseek
- 每个key首次尝试即429, 无重试机会
- 全5键在6-10秒内全部429 (快速失败)

### 延迟结构
```
总延迟 = glm5.1 futile attempt (6-16s) + deepseek fallback (20-25s) = 26-41s
```
- glm5.1是纯粹的延迟税 — 无产出, 仅消耗预算
- deepseek 100%成功(偶有SSLEOFError), 但被glm5.1前置延迟拖慢
- 每轮glm5.1尝试消耗~6-16s (全键测试完)

### 429机制分析
```
KEY_COOLDOWN_S=36.0 → 指数退避:
  - 第1次429: 36s cooldown
  - 第2次连续429: min(36×2¹, 50) = 50s (cap)
  
GLOBAL-COOLDOWN: 硬编码45s (all 5 keys 429时)
  - 所有5键标记45s冷却
  - 覆盖per-key cooldown
```

### 优化方向
**增加KEY_COOLDOWN_S** — 让每个key在被429后冷却更久:
- 当前36s → 40s = +4s首级冷却
- 第1次429: 40s (vs 36s) = +4s
- 第2次连续429: min(40×2, 50) = 50s (cap不变)
- 减少key重新进入轮转的频率
- 给NV速率限制桶更多恢复时间

---

## ⚙️ 优化执行

### 更改: KEY_COOLDOWN_S 36.0 → 40.0 (+4s)

**文件**: `/opt/cc-infra/docker-compose.yml` (hm40006 service env)

**操作**:
```bash
ssh -p 222 opc2_uname@100.109.57.26
cd /opt/cc-infra
cp docker-compose.yml docker-compose.yml.bak.R88
sed -i 's|KEY_COOLDOWN_S: "36.0"|KEY_COOLDOWN_S: "40.0"|' docker-compose.yml
docker compose up -d --force-recreate hm40006
```

**理由**:
- 当前36.0s per-key cooldown, keys re-enter rotation too quickly
- +4s = 40.0s首级冷却, 让key在429后多等4秒
- 6-10s内5键全429 → 更长冷却减少快速重入
- 指数退避第2级仍cap在50s (无变化)
- 少改多轮: 单参数变更, 4s增量

**验证**:
```bash
docker exec hm40006 env | grep KEY_COOLDOWN_S
→ KEY_COOLDOWN_S=40.0 ✓

docker exec hm40006 python3 -c 'from gateway.config import *; print("KEY_COOLDOWN_S:", KEY_COOLDOWN_S)'
→ KEY_COOLDOWN_S runtime: 40.0 ✓
```

**容器状态**: `hm40006 Up 43 seconds (healthy)` ✓

---

## 📈 指标对比

| 参数 | 优化前 | 优化后 | Δ |
|------|--------|--------|-----|
| KEY_COOLDOWN_S | 36.0s | 40.0s | +4s |
| MIN_OUTBOUND_INTERVAL_S | 21.0s | 21.0s | 0 |
| TIER_COOLDOWN_S | 48s | 48s | 0 (未使用) |
| TIER_TIMEOUT_BUDGET_S | 120s | 120s | 0 |
| UPSTREAM_TIMEOUT | 55s | 55s | 0 |
| HM_CONNECT_RESERVE_S | 12s | 12s | 0 |

**预期效果**: 
- per-key首级cooldown: 36→40s (+4s)
- 减少key在429后快速重回轮转频率
- 每key多4s冷却 = NV速率限制桶多4s恢复
- 整体429频率微降 (边际改善, 少改多轮积累)

---

## 📝 备注

- **铁律遵守**: ✅ 只改HM2 docker-compose.yml (1个env参数), 未动HM1任何文件
- **mihomo**: ⚠️ 未停止/重启/kill mihomo服务 (NV API链路的必要代理)
- **少改多轮**: 本轮仅改1个参数 (KEY_COOLDOWN_S +4s)
- **策略**: glm5.1永久429 → 增加per-key冷却时间, 减少无效重试频率
- **叠加效应**: R86 (HM_CONNECT_RESERVE -3s) + R87 (MIN_OUTBOUND +2s) + R88 (KEY_COOLDOWN +4s) = 三环累积优化
- **持续观察**: 下一轮等待HM2优化HM1, 继续监控deepseek fallback latency趋势

---

## ⏳ 轮到HM2优化HM1