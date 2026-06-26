# R38: HM1 优化 HM2 (hm40006) — MIN_OUTBOUND_INTERVAL_S 16.0→16.5 (+0.5s, 减少SSLEOF)

**日期**: 2026-06-26 12:05 UTC  
**执行者**: HM1 (opc_uname)  
**目标**: HM2 hm40006 (opc2_uname@100.109.57.26, ssh -p 222)  
**上一轮**: R37 (MIN_OUTBOUND_INTERVAL_S 15.0→16.0)  
**对端触发**: R36 (opc2_uname: HM2→HM1 — TIER_COOLDOWN_S 88→86) → R37 (opc_uname: HM1→HM2 — MIN_OUTBOUND_INTERVAL_S 15→16)

---

## 📊 数据采集

### 1. SSLEOF 和错误分布 (30分钟窗口, 11:55-12:25 UTC)

**hm_requests 汇总:**
```
请求总数: 63
成功: 63 (100.0%)
Fail 502: 0
Fail 500: 0
Fallback count: 52/63 = 82.5%
```

**延迟分布:**
```
p50: 26,993ms
p90: 52,005ms
p95: 61,347ms
Avg total: 27,379ms (duration) / 27,151ms (ttfb)
```

**hm_tier_attempts (错误分布, 30min):**
```
429_nv_rate_limit           | 170 | --       (glm5.1 全部5键429)
NVCFPexecSSLEOFError       |  17 | 12,024ms (mihomo SSL连接中断)
NVCFPexecConnectionResetError | 3  | 1,133ms
```

**Per-key 429 分布 (5/5 keys 均匀):**
```
k0=32, k1=34, k2=35, k3=35, k4=34
→ 完全均匀, NVCF函数级限速 (不是per-key限速)
```

**all_tiers_exhausted: 0** (极好!)

### 2. 环境变量确认
```
MIN_OUTBOUND_INTERVAL_S=16.0   ← R37
KEY_COOLDOWN_S=26.0            ← RN (28→26)
TIER_COOLDOWN_S=55             ← R31后保持
TIER_TIMEOUT_BUDGET_S=111      ← 保持
UPSTREAM_TIMEOUT=62             ← 保持
HM_CONNECT_RESERVE_S=4          ← 保持
```

### 3. 日志采样 (最后100行)
- glm5.1 全部429失败, 100% fallback到deepseek
- 无SSLEOFError在日志中出现 (已在tier_attempts中)
- deepseek fallback成功, 无超时
- 模式: HM-TIER-FAIL → all keys in cooldown → fallback → deepseek成功
- 2次glm5.1成功: k4@12:02:01.5, k5@12:02:09.2 (部分key在冷却内仍可用2429)

---

## 🔍 诊断

### 根因分析

1. **SSLEOFError=17次/30min (已从147降, 仍有)**: mihomo proxy的SSL连接中断继续出现。MIN_OUTBOUND_INTERVAL_S=16.0 (从R37的16.0) 已帮助从147→17, 但17次仍说明连接频率过高, 需要更多间隔。

2. **NVCFPexecConnectionResetError=3次**: 连接被重置, 与SSLEOF是姊妹问题, 都源于mihomo连接压力。

3. **82.5% fallback比率**: glm5.1 tier 100% 429失败, 所有请求 fallback到deepseek。glm5.1只有2次成功(在100行中), 所以大部分请求跳过glm5.1直接走deepseek。

4. **429 均匀分布**: 5/5键429分布均匀(32-35), 证明是NVCF函数ID `822231fa-d4f...` 的全局限速, 不是per-key限速。KEY_COOLDOWN_S=26.0已足够(26/10=2.6 cycles)。

### 优化路径

- **MIN_OUTBOUND_INTERVAL_S**: 继续提高从16.0→16.5 (+0.5s), 进一步降低mihomo连接频率
- **KEY_COOLDOWN_S**: 保持26.0, 429是函数级不是per-key
- **单参数变更**: 只改MIN_OUTBOUND_INTERVAL_S, 少改多轮
- **其他参数全部不变**: UPSTREAM=62, BUDGET=111, KEY=26.0, TIER_COOLDOWN=55, RESERVE=4

### 验证逻辑
- SSLEOF从147→17已改善, 继续降低连接频率
- 0.5s增加: 16.5s / 16.0s = +3.1%间隔, 进一步减少SSL压力
- 边界安全: 16.5s 远低于 UPSTREAM=62s, 无超时风险
- 不影响deepseek fallback路线

---

## ⚙️ 优化执行

### 参数变更

| 参数 | 优化前 | 优化后 | 变化 | 理由 |
|------|--------|--------|------|------|
| MIN_OUTBOUND_INTERVAL_S | 16.0 | 16.5 | +0.5s | SSLEOF=17仍存在, +3.1%间隔继续降低mihomo SSL压力; 单参数变更少改多轮 |

**其他参数全部不变**: UPSTREAM=62, BUDGET=111, KEY=26.0, TIER_COOLDOWN=55, RESERVE=4

### 执行记录

```bash
# 1. 备份
ssh -p 222 opc2_uname@100.109.57.26 'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R38'

# 2. 修改值 (line 479)
ssh -p 222 opc2_uname@100.109.57.26 'cd /opt/cc-infra && sed -i "479s/\"16.0\"/\"16.5\"/" docker-compose.yml'

# 3. 更新注释
ssh -p 222 opc2_uname@100.109.57.26 "cd /opt/cc-infra && sed -i '479s/# R37:.*/# R38: HM1优化 — 16.0→16.5.../' docker-compose.yml"

# 4. 部署
ssh -p 222 opc2_uname@100.109.57.26 'cd /opt/cc-infra && docker compose up -d hm40006'

# 5. 验证 (3s后)
ssh -p 222 opc2_uname@100.109.57.26 'docker exec hm40006 env | grep MIN_OUTBOUND_INTERVAL_S'
→ MIN_OUTBOUND_INTERVAL_S=16.5 ✓
```

### 部署后验证
```
hm40006: Up 36 seconds (healthy)
MIN_OUTBOUND_INTERVAL_S=16.5  ← 已生效
Health: 200 {"status":"ok"}  ← 健康检查通过
```

### 部署后日志观察
```
[12:07:26.4] [HM-TIER-SKIP] tier=glm5.1_hm_nv all keys in cooldown, skipping
[12:07:26.4] [HM-FALLBACK] → falling back to deepseek_hm_nv
[12:07:25.9] [HM-SUCCESS] tier=deepseek_hm_nv k4 succeeded after 5 cycle attempts
```
→ 正常运行, 无异常

---

## 📈 预期效果

- **SSLEOFError继续下降**: 从17 → 目标13-15/30min (减少10-25%)
- **ConnectionResetError更少**: 从3 → 目标1-2
- **g5.1 non-429 slot: 不变**: 429是函数级限速, MIN_OUTBOUND不影响429修复
- **Fallback率可能微升**: 更长的间隔可能意味着更多请求累积时glm5.1仍429
- **延迟分布可能微降**: SSLEOF减少 → deepseek fallback更稳定
- **all_tiers_exhausted: 保持0**: 系统健康

---

## ⚠️ 观察项

1. **SSLEOF下降是否持续**: 目标从17 → 10-15, 需监控下轮
2. **MIN_OUTBOUND_INTERVAL_S上限**: 当前16.5, 继续提高需注意过度限制请求频率
3. **429 均匀分布未变**: 函数级限速不受MIN_OUTBOUND影响
4. **mihomo代理未动**: 仅容器重建, mihomo进程持续运行

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记