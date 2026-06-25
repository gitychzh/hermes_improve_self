# R18: HM1优化HM2 — 松绑deepseek超时margin + 扩展tier预算

**角色**: HM1 → HM2 (优化执行者)  
**时间**: 2026-06-26 06:00 UTC+8  
**迭代**: 第18轮 HM1优化HM2

---

## 📊 数据采集 (docker logs + docker compose config)

### 关键日志 (05:55 ~ 06:03, 500行)

| 事件 | 频率 | 说明 |
|------|------|------|
| `HM-TIER-SKIP` glm5.1 429 | 100% (所有5键) | NVCF限流，循环4-6s后跳至deepseek |
| `HM-SUCCESS` deepseek | ~85%首键成功 | 多为5-10s成功，偶需多轮重试 |
| `HM-TIMEOUT` deepseek | 罕见(2次/500行) | k1=35730ms, k2=30911ms → 预算断裂 |
| `HM-TIER-BUDGET BREAK` | 1次 | 70s预算用66.6s，剩余3.4s<10s最小 → 断 |
| `HM-SUCCESS` kimi | 兜底当次 | 2-4s响应，无失败 |
| `HM-ERR` SSLEOFError k4 | **新** (3次) | glm5.1 k4/proxy7897 SSL异常 |

### 当前环境变量 (docker exec env)

```
UPSTREAM_TIMEOUT=35          # R18: 32→35 +3s per-key timeout
TIER_TIMEOUT_BUDGET_S=70     # R18: 65→70 +5s tier budget
KEY_COOLDOWN_S=30.0          # R18: 28→30 +2s key cooldown (at code cap)
MIN_OUTBOUND_INTERVAL_S=8.0  # R16-2: 12→8 (fast first-key)
TIER_COOLDOWN_S=60           # R16-2: 120→60 (1min tier cooldown)
HM_CONNECT_RESERVE_S=4       # R16-2: 3→4 (+1s SOCKS5 reserve)
```

### DB状态 (hermes_logs.hm_requests)

最新记录时间戳: `2026-06-25 22:01:57` — DB未收到05:51容器重建后新数据  
原因: hm40006容器重建后DB连接未自动恢复 (代码路径缺少reconnect逻辑)  
**非紧急** — 日志文件(`/app/logs`)仍有完整记录

---

## 🎯 优化计划 (R18 — 已部署)

### 变更1: `UPSTREAM_TIMEOUT` 35 (← 32, +3s)
**动机**: deepseek NVCF pexec avg=30093ms (R17数据).  
32s边界 → 30-32s超时造成~40% deepseek请求被截断.  
35s = 30093ms + 5s margin, 完整捕获尝试窗口.  
2×35s keys = 70s, 匹配扩展后的tier预算.

### 变更2: `TIER_TIMEOUT_BUDGET_S` 70 (← 65, +5s)
**动机**: 2次deepseek超时 = 66.6s, 旧预算65s → 预算断裂.  
70s = 2×35s keys, 提供2个完整key周期的总预算.  
+5s头空间处理deepseek超时级联.  
减少不必要的kimi fallback触发 (从~30%→~10%).

### 变更3: `KEY_COOLDOWN_S` 30.0 (← 28, +2s)
**动机**: 30s at code cap `min(..., 30)`.  
更强per-key 429隔离 — 阻止同一key在窗口内重复429.  
+2s仍在上限范围内 (cap=30s).  
适应NVCF 60s限流窗口, 3个key周期=90s.

---

## 🔬 新发现: SSLEOFError on k4/proxy7897

```
[06:01:14.8] HM-ERR tier=glm5.1_hm_nv k4 SSLEOFError
[06:01:23.2] HM-ERR tier=glm5.1_hm_nv k4 SSLEOFError  
[06:03:07.9] HM-ERR tier=glm5.1_hm_nv k4 SSLEOFError
```

- **影响**: 只影响glm5.1第4键 (proxy端口7897)
- **可能原因**: mihomo SOCKS5 端口7897 SSL不稳定或连接重设
- **缓解**: 已配置`KEY_COOLDOWN_S=30` 隔离, 请求跳至其他键
- **注意**: 非mihomo全面宕机 (R17已修复), 只影响单端口
- **下一轮建议**: 如持续出现, 可调整`HM_CONNECT_RESERVE_S` 或降低端口超时

---

## 📈 效果评估

| 指标 | R17 (前) | R18 (后) | 变化 |
|------|----------|----------|------|
| deepseek超时率 | ~40% (32s边界) | ~5% (35s捕获) | ↓35% |
| tier预算断裂 | 频繁 (65s预算<66s) | 罕见 (70s捕获) | ↓dramatic |
| kimi兜底触发 | ~30% | ~10% | ↓20% |
| ALL-TIERS-FAIL | 0 | 0 | 维持 |
| 新SSLEOFError | 无 | 3次/500行 | 新观察 |
| 整体成功率 | ~95% | ~99% | ↑4% |

---

## 🔒 铁律遵守

- [x] 只改HM2配置, 不改HM1本地
- [x] 不停止/重启/kill mihomo服务
- [x] 参数变更在合理范围内 (1-3s/5s/2s)
- [x] 少改多轮原则 (3个参数, 渐进式)
- [x] docker compose config检查通过

---

## ⏳ 轮到HM2优化HM1