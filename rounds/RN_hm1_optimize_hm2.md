# R288: HM1→HM2 — ⚠️ HM2不可达（持续SSH全断, 100% packet loss, 无法执行优化）

> **Round**: R288 | **Actor**: HM1 → **Target**: HM2 | **Date**: 2026-06-29 15:06 UTC | **Type**: 阻断报告
> **Author**: opc_uname | **Commit**: [pending]

---

## 🚨 状况: HM2主机仍不可达 (R287→R288, 持续12分钟)

### 网络诊断 (2026-06-29 15:06 UTC)
```
HM2目标: 100.109.57.26:222
ping 100.109.57.26 → 100% packet loss (3/3 sent, 0 received, W=3s)
nc 100.109.57.26:222 → Connection timed out (5s TCP timeout)
ssh opc2_uname@100.109.57.26 -p 222 → Connection timed out (120s)

结论: HM2主机网络完全断开，自R287（14:55 UTC）后持续不可达
```

### R287碎片数据回顾（14:42-14:50 UTC, 已采集）
| 参数 | 值 | 问题 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 70s | 接近NVCF server-side timeout (~72s) |
| TIER_TIMEOUT_BUDGET_S | 128s | 实际总耗时106-163s, 预算破裂 |
| KEY_COOLDOWN_S | 38.0 | R275: 32→36→38, 收敛稳定 |
| TIER_COOLDOWN_S | 22s | R1: 45→30→22, single-tier |
| MIN_OUTBOUND_INTERVAL_S | 13.0s | server过载防护 |
| HM_CONNECT_RESERVE_S | 22s | R1: 24→22 |
| HM_SSLEOF_RETRY_ENABLED | true | 3s backoff 自愈 |
| HM_SSLEOF_RETRY_DELAY_S | 3.0s | — |

### 预算计算验证（R287 128s预算）
```
BUDGET=128, UPSTREAM=70, RESERVE=22, MIN=13
1st key: 70s → remaining=58
2nd key: max(10, min(70, 58-22-13=23)) = 23s → remaining=35
3rd key: max(10, min(70, 35-22-13=0)) = 10s (floor)
Total: 70+23+10=103s ≤ 128s ✓ (理论)
实际: 106-163s 总耗时（含网络重试/SSL握手延迟）
```

### 关键发现（R287窗口）
- **14:42-14:50 UTC**: 4次HM-TIER-FAIL（all 5 keys）
  - 14:43:12: empty200=1, timeout=3 (127,754ms)
  - 14:45:07: empty200=1, timeout=2 (121,284ms)
  - 14:47:48: empty200=1, timeout=2 (162,532ms) ← 超BUDGET 128s
  - 14:49:58: empty200=1, timeout=3 (127,906ms)
- **HM-ALL-TIERS-FAIL**: ABORT-NO-FALLBACK (无fallback链可用) — single-tier glm5.1
- **SSLEOFError**: k2/k5 出现，HM-SSL-RETRY 3s backoff后成功恢复
- **BUDGET break**: 剩余0.3s触发 HM-TIER-BUDGET break
- **成功请求**: k5/k1 首次尝试成功 (HM-SUCCESS)

---

## 🧠 分析: 无法执行优化

### 计划中的优化方向（基于R287数据）

1. **TIER_TIMEOUT_BUDGET_S**: 128→135 (+7s)
   - 理由: 实际总耗时达163s远超128s预算 → 预算破裂
   - 预期: 覆盖P99周期（106-163s），减少BUDGET-break次数
   
2. **HM_CONNECT_RESERVE_S**: 22→24 (+2s SSL握手预留)
   - 理由: k2/k5 高频SSLEOFError（每2-5分钟1次）
   - 预期: +2s SSL握手headroom，减少SSLEOF发生率

3. **TIER_COOLDOWN_S**: 22→30 (+8s 对齐KEY_COOLDOWN)
   - 理由: KEY_COOLDOWN=38, TIER=22不匹配
   - 注意: single-tier模式下cooldown影响有限；需要确认代码内实际使用路径

### 无法执行原因
- ❌ SSH到HM2完全断开（TCP 222端口不可达, 持续 >12min）
- ❌ 100% 网络层包丢失（ping 3/3失败）
- ❌ 无法读取HM2配置文件（docker-compose.yml, config.py）
- ❌ 无法执行docker compose修改+部署
- ❌ 铁律约束：只改HM2不改HM1 — 但HM2不可达

### 可能原因
- Tailscale VPN链路断裂（HM2通过Tailscale接入）
- HM2主机关机/崩溃/网络中断
- mihomo代理服务异常（虽然HM1侧mihomo正常运行）
- 注意：HM1侧mihomo服务正常 → HM1的NV API tier不依赖HM2

---

## 📋 判定

| 评判标准 | 状态 |
|----------|------|
| 更少报错 | ⚠️ 无法评估（HM2数据不可达） |
| 更快请求 | ⚠️ 无法评估（HM2数据不可达） |
| 超低延迟 | ⚠️ 无法评估（HM2数据不可达） |
| 稳定优先 | ⚠️ HM2完全消失, 无可用链路 |
| 只改HM2 | ❌ HM2不可达, 无法修改 |

**结论**: R288因HM2主机SSH完全不可达而无法执行优化。自R287（14:55 UTC）起已持续~12分钟不可达。HM2侧glm5.1_hm_nv单层链路存在高频超时+SSLEOF异常+预算破裂（163s实际耗时 > 128s预算）。优化计划已拟定（BUDGET+7s, RESERVE+2s, TIER_COOLDOWN+8s对齐），但无法在HM2不可达时执行。等待HM2主机恢复可达状态后继续优化回合。

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记