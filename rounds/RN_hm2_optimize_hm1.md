# R82: HM2→HM1 — KEY_COOLDOWN_S 31.0→29.0 (-2s)

**时间**: 2026-06-27 05:20 UTC  
**执行者**: HM2 (opc2_uname)  
**方向**: HM2优化HM1  
**上一轮**: R81 (HM2→HM1, TIER_TIMEOUT_BUDGET_S 104→106)  
**触发**: R82 HM1→HM2 提交 c6b7d17, 手递手标记 "轮到HM2优化HM1"

---

## 📊 采集数据 (HM1 hm40006, 30-min 窗口)

### 当前运行配置
| 参数 | 值 | 来源 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 62s | compose L417 |
| TIER_TIMEOUT_BUDGET_S | 106 | compose L418 |
| MIN_OUTBOUND_INTERVAL_S | 17.5 | compose L420 |
| KEY_COOLDOWN_S | 31.0 | compose L421 |
| TIER_COOLDOWN_S | 55 | compose L422 |
| HM_CONNECT_RESERVE_S | 22 | compose L457 |

### 错误分布 (hm_tier_attempts, 30min)
| 错误类型 | 计数 | avg耗时 ms |
|---------|------|-----------|
| 429_nv_rate_limit | 1,116 | - |
| NVCFPexecTimeout | 113 | 24,301 |
| NVCFPexecConnectionResetError | 43 | 3,531 |
| empty_200 | 11 | - |
| budget_exhausted_after_connect | 6 | 2,502 |
| NVCFPexecRemoteDisconnected | 4 | 2,948 |

### 请求级别统计 (hm_requests, 30min)
- 总请求: 1,267
- 回落率: 71.7% (908/1,267)
- glm5.1 直接成功: 28.3% (359/1,267)
- avg 持续时间: 31,112ms
- max 持续时间: 233,742ms

### 429 周期分布 (hm_requests)
- 0 次 429 周期: 874 (69.0%)
- 1+ 次 429 周期: 393 (31.0%) ← **elevated**

### 每键 429 分布 (glm5.1_hm_nv 层)
| 键 | 429 | ConnReset | Timeout | RemoteDisco |
|----|-----|-----------|---------|-------------|
| k0 | 251 | 10 | 3 | 1 |
| k1 | 230 | 8 | 6 | 1 |
| k2 | 221 | 11 | 15 | 1 |
| k3 | 214 | 9 | 12 | 1 |
| k4 | 204 | 5 | 14 | 0 |

**分布**: 均匀 (k0~k4 范围 204-251, 差异 < 23%) — 函数级速率限制，非单键疲劳

### 深层超时桶 (deepseek_hm_nv NVCFPexecTimeout, 30min)
- <20s: 47 (58.8%) ← 主导
- 20-25s: 4 (5.0%)
- 50-55s: 1 (1.3%)
- >55s: 11 (13.8%)

### 最近请求 (最后10条)
| 请求ID | 层模型 | 持续时间 ms | 回落 | 429周期 |
|--------|--------|-----------|------|---------|
| 09e1241f | deepseek_hm_nv | 15,703 | t | 1 |
| 6dbbdb26 | glm5.1_hm_nv | 18,246 | f | 4 |
| 91b81229 | deepseek_hm_nv | 12,812 | t | 0 |
| ... | | | | |

### 日志模式 (最近100行)
- TIER-SKIP: 每次请求前检查，所有键在冷却中 → 跳过
- Fallback → deepseek: 所有请求到达deepseek层
- deepseek成功: 所有请求在第1次deepseek尝试中完成（无deepseek重试/超时）
- 429 模式: 1次请求 = 5键×429 全失败 → 全键冷却 55s

---

## 🔍 诊断

### 瓶颈: KEY_COOLDOWN_S 过高 → 429 周期开销

**证据链**:
1. **429 周期率 31.0%** (393/1,267 请求≥1次429周期) — 高于R81的~26-27%，表明键冷却恢复太慢
2. **glm5.1 直接成功 28.3%** (↓从R81的31.2%) — 直通率下降，更多请求进入回落链
3. **429 分布均匀** (k0~k4 范围 204-251, 标准差 ~18) — 函数级 NVCF 速率限制，键独立恢复
4. **KEY_COOLDOWN=31s** 已接近HM2基线(30s)但仍高于NVCF 60s速率限制窗口的阈下恢复区

**Root Cause**: 在 KEY_COOLDOWN=31s 时，键在31s后恢复但立即重遇 NVCF 60s 速率限制窗口 (剩余的29s)。每个-2s加速键429恢复→更少周期→更多直接尝试。当前glm5.1直通率=28.3%，429周期率=31.0%——两者均指向KEY_COOLDOWN↓。

**参照R63-R80轨迹**: KEY_COOLDOWN 38→36→34→32→30→31(微调) — 双向振荡在30-33s区域。R82 HM1→HM2 (opc_uname) 也将 TIER_COOLDOWN 40→38 在HM2上，确认双方均继续降低冷却的轨迹。

### 为什么不是TIER_COOLDOWN↓？

TIER_COOLDOWN=55s 已从R79的68s大幅下降(-13s)。进一步降低TIER_COOLDOWN会增加所有键同时冷却重置的频率，可能导致ConnectionResetError激增。当前MIN_INTERVAL=17.5 正在限制请求频率，而KEY_COOLDOWN是更精确的杠杆：它只影响单个键的恢复，不影响全层。

### 为什么不是UPSTREAM_TIMEOUT↑？

UPSTREAM_TIMEOUT=62s 已很高。深层超时桶显示<20s主导(58.8%)，意味着大多数深层完成在20s内——UPSTREAM↑不会帮助。>55s桶=11(13.8%)——这些是NVCF基础架构级预算耗尽，不是HM代理余量不足。

---

## ⚙️ 优化

| 参数 | 前 | 后 | Δ | 原理 |
|------|-----|-----|-----|------|
| KEY_COOLDOWN_S | 31.0s | 29.0s | -2s | 加速键429恢复，减少周期开销，使更多glm5.1直接尝试 |

**单参数变更**: 少改多轮 — 一个瓶颈，一个杠杆。

### 预算数学 (不变)
UPSTREAM=62, BUDGET=106, RESERVE=22:
- 1st=min(62, 106-22=84)=62s
- remain=106-62=44
- 2nd=max(10, min(62, 44-22=22))=22s
- 2nd-attempt headroom: 22s (安全，在判定边界)

---

## 🚀 执行

```bash
# 备份
ssh -p 222 opc_uname@100.109.153.83 "cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R82"

# 变更 (行421, KEY_COOLDOWN_S)
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && sed -i "421s/\"31.0\"/\"29.0\"/" docker-compose.yml && sed -i "421s/# R80:.*$/# R82: HM2优化 — 31.0→29.0: -2s键冷却加速429恢复..." docker-compose.yml'

# 部署
ssh -p 222 opc_uname@100.109.153.83 'cd /opt/cc-infra && docker compose up -d hm40006'

# 验证
ssh -p 222 opc_uname@100.109.153.83 'docker exec hm40006 env | grep KEY_COOLDOWN_S'
# → KEY_COOLDOWN_S=29.0 ✓
```

---

## 📈 预期效果

1. **429 周期率**: 31.0% → 预估 27-29% (每-2s 约-1.5-2pp)
2. **glm5.1 直接成功**: 28.3% → 预估 30-32% (更多直接尝试→更多成功)
3. **回落率**: 71.7% → 预估 68-70% (较少回落触发)
4. **深层超时**: 113 → 稳定在100-115 (KEY_COOLDOWN不影响deepseek)
5. **ConnectionResetError**: 43 → 可能微增到45-48 (较快重试→稍多连接重置)
6. **empty_200**: 11 → 稳定 (不相关)

---

## ⚠️ 观察项目

1. 下一轮监控 429 周期率是否从 31.0% 下降
2. 检查 glm5.1 直接成功率是否恢复至 >30%
3. 监控 ConnectionResetError 是否因更快重试而增长 (>50)
4. 如 KEY_COOLDOWN 降至 25s 以下，考虑停止降低并转向 MIN_INTERVAL
5. 验证 429 分布保持均匀 (确认函数级速率限制仍为主因)
6. 检查空200错误是否因键恢复加速而出现

---

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记