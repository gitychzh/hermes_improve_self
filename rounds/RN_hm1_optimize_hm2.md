# R{NEXT}: HM1→HM2 — HM_CONNECT_RESERVE_S 14→16 (+2s)

**角色**: HM1 (opc_uname)  
**操作**: 优化 HM2 (opc2_uname)  
**轮次**: HM1→HM2 (第N+1轮)  
**时间**: 2026-06-27 21:30 CST  
**原则**: 更少报错 更快请求 超低延迟 稳定优先  
**铁律**: 只改HM2 不改HM1 · 单参数 · 绝不碰mihomo

---

## 📊 数据采集 (30-min窗口 from HM2)

### 1. 总体状态 (hm_requests 表)
```
Total: 83 req | 200 OK: 83 (100%) | 错误: 0 | 0% error rate
p50=9306ms p90=22024ms p95=25657ms p99=52975ms avg=12513ms
```

### 2. 层级分布
| Tier | Count | % | Avg(ms) | 429-Cycles | Fallbacks |
|------|-------|---|---------|------------|-----------|
| glm5.1_hm_nv | 72 | 86.7% | 10779 | 26 | 0 |
| deepseek_hm_nv | 11 | 13.3% | 23868 | 6 | 11(100%) |

**关键发现**: deepseek 100% 请求都是fallback (主tier glm5.1失败后兜底)

### 3. 层级尝试错误 (hm_tier_attempts)
```
glm5.1_hm_nv:  20× 429_nv_rate_limit (即时)
                7× NVCFPexecSSLEOFError (avg=6359ms)
deepseek_hm_nv: 2× NVCFPexecSSLEOFError (avg=8719ms)
```

### 4. 10-min vs 30-min 爆发窗口分析
```
最后10min:  20 req, 0 errors, avg=13140ms
前20min(10-30): 60 req, 0 errors
→ 无爆发模式 — 均匀干净，系统稳定
```

### 5. Docker日志模式 (最近100行 error/warn)
```
[21:16:03] k1→429, k2→429, k3→SSLEOFError
[21:16:39] → fallback to deepseek_hm_nv
[21:16:50] ✅ deepseek success (11.7s)
[21:17:09] k1→429, k2→429, k3→SSLEOFError (重复)
[21:20:58] k3→SSLEOFError
[21:21:31] k1→429, k2→429, k3→SSLEOFError (重复)
```

**模式**: glm5.1 k1/k2 429→k3 SSLEOFError→fallback deepseek→成功  
NV API函数级速率限制: k1+k2均在429, 仅k3可达但SSLEOFError (连接建立失败)

### 6. 当前HM2运行时参数 (docker exec hm40006 env)
| Parameter | Value |
|----------|-------|
| UPSTREAM_TIMEOUT | 71s |
| TIER_TIMEOUT_BUDGET_S | 128s |
| MIN_OUTBOUND_INTERVAL_S | 7.5s |
| KEY_COOLDOWN_S | 38.0s |
| TIER_COOLDOWN_S | 45s |
| HM_CONNECT_RESERVE_S | **14** (→ 16) |
| GLOBAL_COOLDOWN_S | 45s (hard-coded) |

### 7. HM2容器状态
```
hm40006: Up (healthy) | 镜像: cc-infra-hm40006
mihomo: 运行中 (since Jun24, PID 2008535) ✅ 不碰
```

---

## 🔍 分析

### 核心发现
1. **100%成功率, 0错误**: 系统完全稳定, 无需修复错误 — 本轮优化方向应为**延迟降低**
2. **9次SSLEOFError (glm5.1=7 + deepseek=2)**: 这9次连接级失败是主要延迟成本 (avg 6.4-8.7s per event)
3. **HM_CONNECT_RESERVE_S 跨机差距**: HM2=14 vs HM1=24 (10s差距). HM1有+10s连接建立预算, HM2仅有14s用于SOCKS5+SSL握手
4. **KK1/K2 429模式**: NV API函数级速率限制饱和 — glm5.1的k1+k2同时429, k3才能到达NV但SSLEOFError

### 参数选择理由

**选择: HM_CONNECT_RESERVE_S 14→16 (+2s)**

- **为什么选这个**: SSLEOFError是连接建立阶段失败(SSL握手未完成), 不是请求超时 — 增加连接建立预算直接解决根本原因
- **为什么不是 TIER_COOLDOWN_S**: 100%成功率意味着没有层级完全失败, 降低层级cooldown无意义
- **为什么不是 TIER_TIMEOUT_BUDGET_S**: 128s已足够 — 实际deepseek fallback在11.7s完成, 远低于预算
- **为什么不是 KEY_COOLDOWN_S**: 38.0s已接近GLOBAL_COOLDOWN=45s — 429是函数级限制, 继续降低key cooldown会增加无效retry
- **为什么不是 UPSTREAM_TIMEOUT**: 71s远超实际延迟(avg 12.5s) — per-key超时不是瓶颈

### 预算验证
```
Effective budget = TIER_TIMEOUT_BUDGET_S - HM_CONNECT_RESERVE_S
Before: 128 - 14 = 114s
After:  128 - 16 = 112s (减少2s)
```
实际deepseek fallback在11.7s完成 → 112s预算仍有100s+余量 (无风险)

### 跨机收敛路径
```
HM1 (opc_uname):  HM_CONNECT_RESERVE_S = 24
HM2 (opc2_uname): HM_CONNECT_RESERVE_S = 14→16 (+2s per round)
目标: 16→18→20→22→24 (还需4轮, 每轮+2s)
```

---

## ⚡ 执行

### 修改
```bash
# Line 510: /opt/cc-infra/docker-compose.yml
sed -i "510s|HM_CONNECT_RESERVE_S: \"14\"|HM_CONNECT_RESERVE_S: \"16\"|"
```

### 重建容器
```bash
ssh -p 222 opc2_uname@100.109.57.26 \
  'cd /opt/cc-infra && docker compose up -d --no-deps --force-recreate hm40006'
```
结果: `Container hm40006 Recreated → Started` ✅

### 验证
| 检查项 | 结果 |
|--------|------|
| `docker exec hm40006 env \| grep HM_CONNECT_RESERVE_S` | **16** ✅ |
| `docker ps --filter name=hm40006` | Up (healthy) ✅ |
| `curl localhost:40006/health` | 200 OK ✅ |
| `ps aux \| grep mihomo` | 运行中 (PID 2008535) ✅ |
| `docker compose config` | 语法正确 ✅ |

---

## 📈 预期效果

| 指标 | Before | After | 变化 |
|------|--------|-------|------|
| HM_CONNECT_RESERVE_S | 14s | **16s** | +2s |
| 有效tier预算 | 114s | 112s | -2s (无影响) |
| SSLEOFError (glm5.1) | 7/30min (avg 6.4s) | ↓预期3-4/30min | -40% |
| SSLEOFError (deepseek) | 2/30min (avg 8.7s) | ↓预期1/30min | -50% |
| 成功率 | 100% | 100% | 维持 |
| 中位延迟 | 9306ms | ↓预期~8800ms | -500ms |
| P95延迟 | 25657ms | ↓预期~23000ms | -2.6s |

**机理**: +2s连接建立预算 → deepseek/glm5.1 keys有更多SSL握手时间 → SSLEOFError减少 → 减少fallback次数 → 降低P95延迟 + 更快请求

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记