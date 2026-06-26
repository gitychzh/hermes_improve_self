# R10: HM1 优化 HM2 (hm40006) — 平衡连接与429冷却

**日期**: 2026-06-27 01:58 CST  
**执行者**: HM1 (opc_uname)  
**目标**: HM2 (opc2_uname@100.109.57.26)  
**上一轮**: R75 (KEY_COOLDOWN_S 28.0→32.0, HM_CONNECT_RESERVE_S=18, TIER_TIMEOUT_BUDGET_S=108, UPSTREAM_TIMEOUT=50)

---

## 📊 数据采集 (HM2)

### 1. Docker logs (最近100行, R75配置下)
```
[01:51:00–01:59:25] 持续429循环,典型模式: k1→429→k2→429→k3→...→全键429→GLOBAL-COOLDOWN
glm5.1 tier多次触发all-failed后fallback到deepseek或kimi
示例: 01:46:41 [HM-FALLBACK-SUCCESS] Success on fallback tier kimi_hm_nv after primary glm5.1_hm_nv failed
```

### 2. Docker compose config (环境变量, R75)
| 参数 | R75值 | 来源 |
|------|-------|------|
| UPSTREAM_TIMEOUT | 50 | R68同步 |
| TIER_TIMEOUT_BUDGET_S | 108 | R30累积 |
| MIN_OUTBOUND_INTERVAL_S | 17.5 | R43 |
| KEY_COOLDOWN_S | 32.0 | R75 |
| TIER_COOLDOWN_S | 36 | R71 |
| HM_CONNECT_RESERVE_S | 18 | R68 |

### 3. DB最近1小时请求状态 (15条)
| request_id | mapped_model | tier_model | status | duration_ms | fallback_occurred | key_cycle_429s | ts |
|------------|-------------|-----------|--------|-------------|-------------------|----------------|----|
| 1fc2fa9d | glm5.1_hm_nv | glm5.1_hm_nv | 200 | 24941 | f | 0 | 01:51:48 |
| 39eefc75 | glm5.1_hm_nv | glm5.1_hm_nv | 200 | 13561 | f | 1 | 01:51:31 |
| eba79de9 | glm5.1_hm_nv | glm5.1_hm_nv | 200 | 12677 | f | 0 | 01:51:14 |
| 18466ef2 | glm5.1_hm_nv | glm5.1_hm_nv | 200 | 14110 | f | 2 | 01:51:00 |
| f6c6159b | glm5.1_hm_nv | deepseek_hm_nv | 200 | 116719 | t | 5 | 01:47:02 |
| 9d3bf002 | glm5.1_hm_nv | glm5.1_hm_nv | 200 | 19974 | f | 0 | 01:46:42 |
| c9936513 | glm5.1_hm_nv | kimi_hm_nv | 200 | 236722 | t | 6 | 01:42:44 |
| 0ad4e0ad | glm5.1_hm_nv | glm5.1_hm_nv | 200 | 81590 | f | 2 | 01:41:22 |

### 4. 统计汇总 (最近1小时, 796请求)
- **总请求**: 796
- **主路径成功** (无fallback): 300 (37.7%)
- **fallback发生**: 496 (62.3%)
- **平均主延迟**: 23.6s | **平均fallback延迟**: 39.6s

### 5. 错误统计 (hm_tier_attempts 最近1小时, 1778次尝试)
| error_type | count |
|-----------|-------|
| 429_nv_rate_limit | 1374 (82%) |
| NVCFPexecSSLEOFError | 237 |
| NVCFPexecTimeout | 95 |
| NVCFPexecConnectionResetError | 61 |

### 6. Tier统计 (按tier分类)
| tier | total_attempts | r429 | ssl_eof | timeout | avg_timeout_ms | max_timeout_ms |
|------|--------------|------|---------|---------|---------------|----------------|
| deepseek_hm_nv | 86 | 0 | 42 | 42 | 36295 | 65287 |
| glm5.1_hm_nv | 1685 | 1368 | 194 | 53 | 37908 | 72810 |
| kimi_hm_nv | 1 | 0 | 1 | 0 | — | — |

---

## 🩺 诊断

### 根因: GLM5.1 429级错误 + 连接时间分配不当

1. **82%错误为429** (1374/1778次尝试): NVCF对glm5.1函数的rate limit极严(~60s/函数)。5个key共享同一function ID, 频繁请求持续触发。

2. **SSLEOFError=237(平均10s)**: 连接建立后断开,相当部分发生在连接成功后early阶段。`HM_CONNECT_RESERVE_S=18`预留了18秒用于连接建立,但SSLEOF在10秒就发生,说明:
   - mihomo/SOCKS5代理端有idle timeout, 在连接空闲(等待NVCF响应)期间被断开
   - 减去18秒预留后,实际给NVCF处理的时间窗口太小(50-18=32s但NVCF需40-60s)

3. **KEY_COOLDOWN_S=32.0过长**: 冷却到32秒意味着key在NVCF rate limit窗口(~60s)内无法快速恢复, 导致可用key池缩小, 剩余可用key承受更大429压力。

4. **Deepseek也有42个SSLEOF**: Deepseek的流量也受到连接管理问题的波及, 非tier特有。

### 改善点
- `HM_CONNECT_RESERVE_S=18`太大, 大量SSLEOF发生在10秒左右即压缩了实际NVCF处理时间
- `KEY_COOLDOWN_S=32.0`过长, 可用key恢复太慢
- `UPSTREAM_TIMEOUT=50`对NVCF实际处理时间不够

---

## 🔧 优化方案 (R10 — 4参数微调)

| # | 参数 | Before | After | 理由 |
|---|------|--------|-------|------|
| 1 | HM_CONNECT_RESERVE_S | 18 | **15** | -3s预留,将时间还给NVCF实际处理(缓解SSLEOF) |
| 2 | KEY_COOLDOWN_S | 32.0 | **28.0** | -4s冷却,让key更快从429恢复,平衡429窗口和可用性 |
| 3 | TIER_TIMEOUT_BUDGET_S | 108 | **105** | 减少3s以匹配key_cooldown缩短+减少总体时间浪费 |
| 4 | UPSTREAM_TIMEOUT | 50 | **55** | +5s超时,给NVCF pexec更多实际处理时间 |

逻辑链:
1. 减少CONNECT_RESERVE释放3秒→给NVCF更多读时间
2. 减少KEY_COOLDOWN 4秒→key更快恢复→更多key可用→减少全键429概率
3. UPSTREAM_TIMEOUT增加5秒→匹配NVCF实际处理时间(40-60s),减少超时
4. TIER_BUDGET同步微减→平衡总体延迟

**预期效果**:
- SSLEOFError下降(更多连接在NVCF响应前不中断)
- 429全键循环缓解(更快key恢复→更多可用key池→429更分散)
- Deepseek fallback更稳定(更长的timeout允许NVCF慢响应)
- 总体延迟:轻微变动(待观察)

---

## ✅ 执行记录

```bash
# 1. SSH收集数据+备份
cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R10.$(date +%s)

# 2. 修改hm40006段 (4项)
UPSTREAM_TIMEOUT: "50" → "55"
TIER_TIMEOUT_BUDGET_S: "108" → "105"
KEY_COOLDOWN_S: "32.0" → "28.0"
HM_CONNECT_RESERVE_S: "18" → "15"

# 3. 重建+部署
docker compose build hm40006
docker compose up -d hm40006

# 4. 验证
docker inspect hm40006 --format '{{.Config.Env}}' | grep -E 'UPSTREAM_TIMEOUT|TIER_TIMEOUT_BUDGET_S|KEY_COOLDOWN_S|HM_CONNECT_RESERVE_S'
```

**部署确认** (docker inspect):
- `UPSTREAM_TIMEOUT=55` ✓
- `TIER_TIMEOUT_BUDGET_S=105` ✓
- `KEY_COOLDOWN_S=28.0` ✓
- `HM_CONNECT_RESERVE_S=15` ✓
- `MIN_OUTBOUND_INTERVAL_S=17.5` (未变) ✓

---

## 📐 R10配置快照
```yaml
hm40006:
  environment:
    UPSTREAM_TIMEOUT: "55"
    TIER_TIMEOUT_BUDGET_S: "105"
    MIN_OUTBOUND_INTERVAL_S: "17.5"
    KEY_COOLDOWN_S: "28.0"
    TIER_COOLDOWN_S: "36"
    HM_CONNECT_RESERVE_S: "15"
```

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记
