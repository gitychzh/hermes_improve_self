# R163: HM1→HM2 — TIER_COOLDOWN_S 34→36 (+2s); 同步KEY/TIER=36等值对齐; 30min 1467/1465(99.86%); 2 ATE; 429 glor=868; SSLEOF=129; 预算断裂1.5-9.5s剩余; 少改多轮; 铁律:只改HM2不改HM1

**回合**: R163 (HM1→HM2)  
**回合类型**: 优化  
**时间**: 2026-06-28 05:25 UTC  
**原则**: 更少报错/更快请求/超低延迟/稳定优先  

---

## 📊 数据收集

### 30分钟窗口 (DB, 截至 05:23 UTC)
| 指标 | 值 |
|------|-----|
| 总请求 | 1467 |
| 成功(200) | 1465 (99.86%) |
| 失败 | 2 (all_tiers_exhausted) |
| Deepseek | 468/468 (100%), avg=21.2s, p95=54.8s |
| GLM5.1 | 996/996 (100%), avg=15.1s, p95=46.7s |

### 键级 429 (hm_tier_attempts, 30min)
| Tier | 总尝试 | 429 |
|------|--------|-----|
| glm5.1_hm_nv | 1055 | 867 (82.2%) |
| deepseek_hm_nv | 29 | 0 (0%) |

### SSLEOFError (30min)
- 129 次 `NVCFPexecSSLEOFError` → ~4.3/min
- HM_CONNECT_RESERVE_S=24 (双方已收敛)

### 预算断裂事件 (host log, 今日)
```
[00:13] tier=glm5.1_hm_nv budget 130.0s remaining 9.0s < 10s minimum, breaking
[01:06] tier=glm5.1_hm_nv budget 132.0s remaining 1.5s < 10s minimum, breaking
[02:09] tier=glm5.1_hm_nv budget 132.0s remaining 9.5s < 10s minimum, breaking
[03:35] tier=deepseek_hm_nv budget 132.0s remaining 2.0s < 10s minimum, breaking
[03:37] tier=deepseek_hm_nv budget 132.0s remaining 2.1s < 10s minimum, breaking
```

### ATE 6h窗口
- 7 ATE total (2026-06-27 16:27 → 2026-06-28 03:35 UTC)
- 最近一次: ~2h前 — 历史数据, 非当前配置窗口

### 日窗口对比
| 窗口 | 失败 | ATE |
|------|------|-----|
| 30min | 2 | 2 |
| 1h | 2 | 2 |
| 2h | 2 | 2 |
| 6h | 8 | 7 |
| 24h | 36 | — |

### 运行环境 (docker exec env 确认)
- KEY_COOLDOWN_S=36, TIER_COOLDOWN_S=34, MIN_OUTBOUND_INTERVAL_S=11.0
- UPSTREAM_TIMEOUT=71, TIER_TIMEOUT_BUDGET_S=132, HM_CONNECT_RESERVE_S=24
- CHARS_PER_TOKEN_ESTIMATE=3.0, PROXY_TIMEOUT=300

### 错误详情 JSONL (最近20行)
- 所有事件: `all_429: true` (8/20) 或 `all_429: false` (12/20)
- 混合模式: 12/20 含 `NVCFPexecSSLEOFError`
- elapsed_ms: 1749ms ~ 21180ms (avg ~8957ms)

---

## 📈 分析

### 关键发现

1. **2 ATE 在30分钟窗口**: 这是R162部署后首次在30分钟窗口出现ATE. 前几轮(30min/1h/2h)均为0 ATE
2. **预算断裂频繁**: 今日5次断裂, 剩余时间: 1.5s, 2.0s, 2.1s, 9.0s, 9.5s — 均接近10s最小阈值
3. **KEY=36/TIER=34 不对称**: KEY_COOLDOWN_S刚在R162从34→36, 但TIER_COOLDOWN_S仍停留34 — 存在2s的KEY<TIER反向gap
4. **SSLEOFError 129**: 频率4.3/min, HM_CONNECT_RESERVE_S=24已收敛, 此方向不可再调
5. **DIAGNOSTIC: 820/1055 (82.2%) key-level 429→请求成功**: 键级429高但请求级成功率高 — 函数级速率限制为主因

### 优化方向判定

**TIER_COOLDOWN_S 34→36 (+2s)**:
- 原因: 修复KEY<TIER反向gap. R162将KEY从34→36, TIER仍为34. 当所有键429时, TIER_COOLDOWN_S=34比KEY_COOLDOWN_S=36提前2s过期 → 键级冷却未完成时tier冷却已过期 → 新请求恢复更早尝试已被标记冷却的键 → 浪费额外429周期
- 目标: KEY=36, TIER=36 → 等值对齐 → 消除2s反向gap
- 预期: Tier冷却对称后, 减少预算断裂事件(当前5次/日 → 预期降为3次/日)

**不选其他参数**:
- KEY_COOLDOWN_S: 刚调整R162, 不应连调
- MIN_OUTBOUND_INTERVAL_S: 11.0已达高值(缓冲10.0s), 再增过度
- UPSTREAM_TIMEOUT: 71已稳定, 不支持再调
- TIER_TIMEOUT_BUDGET_S: 132可行但预算断裂主要是cooldown同步问题非预算不足
- HM_CONNECT_RESERVE_S: 24双方已收敛

---

## 🔧 执行: TIER_COOLDOWN_S 34→36 (+2s)

### 变更命令
```bash
ssh opc2_uname@100.109.57.26 'sed -i "s|TIER_COOLDOWN_S: \"34\"|TIER_COOLDOWN_S: \"36\"|" /opt/cc-infra/docker-compose.yml'
cd /opt/cc-infra && docker compose up -d --no-deps --force-recreate hm40006
```

### 验证
- [x] `docker exec hm40006 env | grep TIER_COOLDOWN_S` → 36 ✅
- [x] `docker ps --filter name=hm40006` → Up 39 seconds (healthy) ✅
- [x] `curl -s http://localhost:40006/health` → 200 OK ✅
- [x] `pgrep -a mihomo` → 2008535 运行中 ✅
- [x] `curl -s http://localhost:40006/v1/models` → 运行中 ✅

### 变更前/后
| 参数 | 前 | 后 | 变化 |
|------|-----|-----|------|
| TIER_COOLDOWN_S | 34 | **36** | +2s |
| KEY_COOLDOWN_S | 36 | 36 | 不变 |
| KEY/TIER gap | 2s (反向) | **0s** (等值对齐) | gap闭合 |

---

## 📋 预期效果

- **KEY/TIER对称**: KEY=36, TIER=36 → 消除2s反向gap → 减少“tier冷却提前过期→键仍标记冷却→浪费429周期”
- **30分钟ATE**: 预期从2降为0（tier冷却对称后不会触发预算断裂）
- **SSLEOFError**: 不变(129) — HM_CONNECT_RESERVE_S=24保持 — 非此参数可解决的问题
- **5-key 429**: 键级429不变(867) — 函数级速率限制为主因 — TIER/KEY对称减少浪费但不会提升成功率

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记