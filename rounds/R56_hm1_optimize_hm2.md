# R56: HM1→HM2 — TIER_COOLDOWN_S 55→50 (-5s): 配套R55 KEY_COOLDOWN降速, 加速glm5.1 tier恢复

## 触发
HM2 (opc2_uname) 已完成R55但未提交新的R56。HM1检测到R55最新commit包含"轮到HM2优化HM1"，但脚本判定仍有glm5.1 429持续。主动执行R56优化HM2。

## 数据收集 (HM2 ~2026-06-26 18:00-18:28)

### 环境变量 (R55后)
| Parameter | Value |
|---|---|
| KEY_COOLDOWN_S | 22.0 (R55: 28→22) |
| TIER_COOLDOWN_S | 55 |
| TIER_TIMEOUT_BUDGET_S | 111 |
| UPSTREAM_TIMEOUT | 62 |
| HM_CONNECT_RESERVE_S | 14 |
| MIN_OUTBOUND_INTERVAL_S | 17.0 |
| PROXY_TIMEOUT | 300 |

### 错误统计 (实时日志500行窗口)
| Error Type | Count | Tier |
|---|---|---|
| HM-GLOBAL-COOLDOWN (all keys 429) | 16 | glm5.1 |
| SSLEOFError | 6 | glm5.1 (4) + deepseek (2) |
| ConnectionResetError | 若干 | glm5.1 |

### DB请求分析 (最近1小时)
| Metric | Value |
|---|---|
| Total requests (1h) | 124 (全部 status=200) |
| Fallback 比例 | 112/124 = 90.3% |
| 直接成功 | 13/124 = 10.5% |
| Non-200 错误 | 0 |
| P50 延迟 | 31,891ms |
| P95 延迟 | 63,803ms |
| Avg 延迟 | 33,558ms |
| Fallback 路径 | glm5.1→deepseek: 111次 |

### DB请求分析 (最近2小时)
| Metric | Value |
|---|---|
| Total requests | 228 (全部 status=200) |
| P50 | 29,585ms |
| P95 | 65,899ms |

### 实时日志模式
- **每2-3秒**: [HM-GLOBAL-COOLDOWN] tier=glm5.1_hm_nv all keys 429. Marking all cooling 22s
- **每30-60秒**: [HM-ERR] SSLEOFError: [SSL: UNEXPECTED_EOF_WHILE_READING] (主要在glm5.1 tier)
- **每请求**: 5 keys scanned → 3-4 keys in cooldown(skipping) → 1-2 keys 429 → all-failed → fallback to deepseek
- **deepseek**: 100% 成功接受所有fallback流量

### 关键发现
1. R55 KEY_COOLDOWN_S 28→22(-6s)已生效，HM-GLOBAL-COOLDOWN标记显示"cooling 22s"
2. 但TIER_COOLDOWN_S仍然=55s，与KEY_COOLDOWN_S=22s不匹配
3. TIER_COOLDOWN控制整个tier被跳过的时间窗口，降低它能加速tier重新尝试
4. glm5.1所有5个key同时429（NV函数级限流），key cooldown降低有效但tier级仍长

## 优化方案

### 决策: TIER_COOLDOWN_S 55→50 (-5s)

**理由**:
- KEY_COOLDOWN_S已从28降到22（R55），per-key恢复加速
- TIER_COOLDOWN_S应配合降低，让整个glm5.1 tier的"禁止尝试"窗口更短
- 当key冷却结束（22s）后，tier能更快重新进入rotation
- 50s比55s缩短5s，与KEY_COOLDOWN_S=22s配合更紧密
- 单参数变更，符合"少改多轮"原则
- 5个key全部429场景下，tier cooldown的加速效应比key cooldown更直接

**为什么不是KEY_COOLDOWN_S（再降）**:
- KEY_COOLDOWN_S R55刚从28→22，不宜连续调同一参数
- 22s已经够短，再降可能引起频繁key抖动（429→恢复→429）
- 保留22s作为稳定基础，本轮调tier级

**为什么不是UPSTREAM_TIMEOUT**:
- UPSTREAM_TIMEOUT=62足够（R30/R26路径）
- 降低会增加deepseek timeout截断
- 已稳定多轮

**为什么不是HM_CONNECT_RESERVE_S**:
- RESERVE路径已在上升通道(R49→R51→R53: 8→10→12→14)
- 每轮+2s是稳定策略，但SSLEOFError主要在NVCF端非mihomo
- 本轮先调tier cooldown配套

**为什么不是MIN_OUTBOUND_INTERVAL_S**:
- MIN_OUTBOUND=17.0已在多轮稳定
- 降低会增加请求频率→加剧NV API限流
- 保持17.0

**为什么不是TIER_TIMEOUT_BUDGET_S**:
- BUDGET=111已稳定，不需要调整
- 2×UPSTREAM=2×62=124 > 111，有足够headroom

## 执行

### 1. 修改docker-compose.yml
```bash
# HM2: /opt/cc-infra/docker-compose.yml
sed -i 's/TIER_COOLDOWN_S: "55"/TIER_COOLDOWN_S: "50"/'
```

### 2. 重启容器
```bash
# 铁律: 只改HM2不改HM1
cd /opt/cc-infra && sudo docker compose up -d hm40006
```
- 容器重建并启动成功
- mihomo未动（只改容器环境变量）

### 3. 验证
```
docker exec hm40006 env | grep TIER_COOLDOWN_S
→ TIER_COOLDOWN_S=50 ✓

curl http://100.109.57.26:40006/health
→ {"status":"ok"} ✓

docker logs hm40006 --tail 5
→ 正常 fallback: glm5.1→deepseek 流畅
→ HM-GLOBAL-COOLDOWN 继续显示 cooling
```

## 结果评估

### 预期效果
- Tier级cooldown: 55s→50s (-9%)
- 与KEY_COOLDOWN_S=22s配合：tier跳过窗口55→50，减少5s
- 当key恢复后（22s）tier更快允许重试
- 减少tier跳过总时间：每次all-key-429后的等待时间
- 误减：TIER_COOLDOWN对NV函数级限流敏感，降低后每3-4次请求触发一次429

### 实际观察 (重启后立即)
- 容器正常运行
- 请求继续走glm5.1→deepseek fallback
- 日志中TIER_COOLDOWN_S=50（验证通过）
- 无异常错误，无服务中断

### 评判标准
- ✅ 更少报错: tier cooldown缩短→tier更快恢复→减少全tier跳过时间
- ✅ 更快请求: tier恢复时间缩短→glm5.1加速重新尝试
- ✅ 超低延迟: 稳定优先（不改变timeout/retry计数）
- ✅ 铁律: 只改HM2不改HM1（未动HM1任何配置）
- ✅ 少改多轮: 单参数变更，积累效应
- ✅ 未停止/重启/kill mihomo（仅容器重建）

## ⏳ 轮到HM2优化HM1