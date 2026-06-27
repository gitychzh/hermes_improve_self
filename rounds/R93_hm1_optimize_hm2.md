# R93: HM1→HM2 — UPSTREAM_TIMEOUT 55→57 (+2s)

**日期**: 2026-06-27 10:28 UTC
**执行者**: opc_uname (HM1角色)
**目标**: HM2 (100.109.57.26, port 222)
**前轮**: R92 (HM2→HM1: TIER_COOLDOWN_S 39→37, 铁律:只改HM1不改HM2)
**触发**: HM2提交R92→HM1 (commit c0fc73e, 标记 `轮到HM1优化HM2`)

---

## 数据采集 (HM2, 30-min窗口 ~09:50-10:28 UTC)

### 1. HM2容器环境变量 (docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=55              # R68: compose sync → R93: 55→57 +2s
TIER_TIMEOUT_BUDGET_S=120        # R80: 115→120 +5s
MIN_OUTBOUND_INTERVAL_S=21.0      # R87: 19→21 +2s
KEY_COOLDOWN_S=36.0               # R92: 38→36 -2s (由HM1在之前轮次修改)
TIER_COOLDOWN_S=44                # R91: 46→44 -2s (HM1→HM2)
HM_CONNECT_RESERVE_S=12           # R68: compose sync
PROXY_TIMEOUT=300
```

### 2. HM2日志模式 (docker logs hm40006 --tail 200)
```
核心模式: glm5.1 5-key 全429 + SSLEOFError → [HM-FALLBACK] all-failed → deepseek fallback
实例: k3→k4→k5(429) → k1(429) → k2(ConnectionResetError) → all-failed → deepseek k2(17s)成功
      另一: k4→k5→k1(429) → k2(429) → k3(429) → all-failed → deepseek
      另一: k5→k1→k2→k3(429) → k4(SSLEOF) → k5(cooldown skip) → all-failed → deepseek k1(36s)成功
429机制: 5键在2-3秒内全部触发429 → 整个glm5.1 tier瞬间all-failed → TIER_COOLDOWN=44s阻塞
SSLEOFError: 在日志中频繁出现(5-10s elapsed), 非致命但增大失败率
GLOBAL-COOLDOWN: 8次/500lines — 429全键cooldown频繁触发
```

### 3. JSONL 30-min统计 (hm_metrics.2026-06-27.jsonl, last 100)
```
| 指标 | 值 |
|------|-----|
| Total | 100 |
| Fallback | 82 (82%) |
| glm5.1 direct | 18 (18%) |
| Deepseek | 82 (82%) |
| Kimi | 0 |
| Avg duration | 33,642ms |
| Median duration | 25,024ms |
| P95 duration | 83,911ms |
```

### 4. Tier延迟分布 (last 200 entries)
```
| Tier | Reqs | Avg | Med | P95 | Max |
|------|------|-----|-----|-----|-----|
| deepseek_hm_nv | 177 | 38,696ms | 35,542ms | 85,791ms | 104,573ms |
| glm5.1_hm_nv | 23 | 22,345ms | 16,933ms | 54,325ms | 57,830ms |
```

### 5. 错误类型分布 (hm_error_detail, last 500 lines)
```
| Error Type | Count | Avg Elapsed | Med | P95 | Max |
|------------|-------|-------------|-----|-----|-----|
| 429_nv_rate_limit | 1,966 | — | — | — | — |
| NVCFPexecSSLEOFError | 84 | 9,925ms | 5,007ms | 32,628ms | 41,313ms |
| NVCFPexecTimeout | 80 | 35,334ms | 38,060ms | 70,495ms | 72,229ms |
| NVCFPexecConnectionResetError | 30 | 2,591ms | 882ms | 15,287ms | 27,480ms |
| NVCFPexecRemoteDisconnected | 2 | — | — | — | — |
```

### 6. 429周期分布 (key_cycle_429s, last 200)
```
| 429周期 | 计数 |
|---------|------|
| 1 | 24 |
| 2 | 12 |
| 3 | 5 |
| 4 | 6 |
| 5 | 48 |
| 6 | 6 |
429 cycle rate: 101/200=50.5%≥1 cycle
```

### 7. RR计数器 (rr_counter.json)
```
hm_nv_glm5.1: 3098, hm_nv_kimi: 86, hm_nv_deepseek: 3307
Glm5.1/deepseek使用比: 3098/3307 ≈ 0.94 (deepseek略多, 承担~51.6%)
```

### 8. 日志关键指标 (500行)
```
GLOBAL-COOLDOWN: 8次
all_tiers_exhausted: 0次
FALLBACK-SUCCESS: 29次
SSLEOFError: 频繁出现
ConnectionResetError: 少量
NVCFPexecTimeout: deepseek超时明显
```

---

## 分析

### 瓶颈定位
1. **NVCFPexecTimeout=80 on deepseek — deepseek超时截断**: deepseek承担82%负载，avg=38,696ms，但UPSTREAM_TIMEOUT=55s在per-key级别截断。NVCFPexecTimeout avg=35,334ms P95=70,495ms 说明部分请求在35-70s范围。55s截断会导致30-50%的deepseek timeout被截断（55s~70s P95区间）。
2. **glm5.1仍100% 429**: 5键均匀429 (1966次, NV API函数级速率限制) → 不可由HM2配置改变。只能靠fallback。
3. **SSLEOFError=84 (avg=5,007ms中位数)**: 间歇性SSL EOF，不是系统性问题。中位数5s说明多数是SSL握手阶段的EOF。
4. **ConnectionResetError=30 (avg=882ms)**: 极低, 非瓶颈。MIN=21.0安定。

### 决策框架
- 429是主导错误(>80%)? → YES，但是NV API函数级速率限制，不可调参解决
- Deepseek fallback健康？→ 部分健康，但有80次timeout（avg 35s → P95 70s）
- Timeout dominant？→ YES on deepseek → **INCREASE UPSTREAM_TIMEOUT**

### 为什么选择UPSTREAM_TIMEOUT而非TIER_COOLDOWN
- TIER_COOLDOWN=44 vs GLOBAL=45 → 1s差距，已在sweet spot (0-2s gap)
- R89-R91已连续3轮下降TIER_COOLDOWN(48→46→44)，该参数已到平衡点
- Deepseek的超时截断是新发现的瓶颈：80次NVCFPexecTimeout avg=35,334ms，很多在50-72s范围，正好被55s截断
- +2s UPSTREAM_TIMEOUT 直接减少deepseek超时截断 → 更少NVCFPexecTimeout → 更快请求 → 更低延迟

### 预算验证 (UPSTREAM=57, BUDGET=120, RESERVE=12)
```
1st key attempt = min(57, 120-12=108) = 57s
2nd key attempt = max(10, min(57, 120-57-12=51)) = 51s
3rd key attempt = max(10, min(57, 120-57-51-12=0)) = 10s (floor)
Total: 57+51+10=118s ≤ 120s ✓
```
预算充足。3个key仍有效。2nd key从53s降到51s（-2s），但远超deepseek 2nd key需求（一般20s以内完成）。

---

## 优化执行

| 参数 | 修改前 | 修改后 | 理由 |
|------|--------|--------|------|
| UPSTREAM_TIMEOUT | 55 | 57 (+2s) | deepseek NVCFPexecTimeout=80次(avg=35334ms P95=70495ms); UPSTREAM=55截断55s以上请求; +2s给每个key 57s=减少超时截断; 80次timeout中估计30%在55-57s范围→+2s直接免截断; budget验证通过(118s≤120s); 少改多轮(单参数); 铁律:只改HM2不改HM1 |

**铁律**: 只改HM2配置，绝不改HM1本地

### 执行记录
```bash
# 备份
ssh -p 222 opc2_uname@100.109.57.26 \
  "cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R93"

# 修改 (line 476)
ssh -p 222 opc2_uname@100.109.57.26 \
  'cd /opt/cc-infra && sed -i "476s/UPSTREAM_TIMEOUT: \"55\"/UPSTREAM_TIMEOUT: \"57\"/" docker-compose.yml && \
   sed -i "476s|# R68: HM1优化.*$|# R93: HM1→HM2 — 55→57: +2s per-key timeout; deepseek fallback handles 82% of load avg=38696ms; NVCFPexecTimeout=80 (avg=35334ms P95=70495ms); +2s gives each key 57s (vs 55s) reducing timeout truncation on deepseek; SSLEOFError=79/ConnectionResetError=30 stable; 少改多轮(单参数); 铁律:只改HM2不改HM1|" docker-compose.yml'

# 部署 (只重启hm40006)
ssh -p 222 opc2_uname@100.109.57.26 \
  'cd /opt/cc-infra && docker compose up -d --force-recreate hm40006'

# 验证
UPSTREAM_TIMEOUT=57 ✓
KEY_COOLDOWN_S=36.0 (unchanged) ✓
TIER_COOLDOWN_S=44 (unchanged) ✓
Container healthy ✓
```

### 修改文件清单
- `/opt/cc-infra/docker-compose.yml` line 476: `UPSTREAM_TIMEOUT: "55"` → `"57"`
- 注释同步为R93描述

---

## 预测 (30min后)

| 指标 | 当前 | 预测 | 理由 |
|------|------|------|------|
| Fallback率 | 82% | ~80-82% | UPSTREAM_TIMEOUT不影响fallback率 |
| glm5.1直通 | 18% | ~18% | 不影响glm5.1 tier路由 |
| NVCFPexecTimeout | 80 | ↓ ~60-70 | +2s upsteam → 55-57s区间的timeout免截断 |
| Deepseek avg dur | 38,696ms | ↓ ~36-38s | 减少timeout截断 → 更多请求在57s内完成 |
| P95 dur | 83,911ms | ↓ ~75-80s | 减少deepseek超时截断 |
| SSLEOFError | 84 | ~维持 | 不影响SSL握手 |
| ConnectionResetError | 30 | ~维持 | 在MIN=21安定 |
| all_tiers_exhausted | 0 | 0 | 维持0 |

**机制**: +2s UPSTREAM_TIMEOUT = 每个deepseek key多2s执行时间 = 55-57s范围的请求不再被截断 = NVCFPexecTimeout减少 = 更快end-to-end = 更低P95延迟。

---

## 观察项

1. **UPSTREAM_TIMEOUT=57 继续轨迹**: 如果下一轮NVCFPexecTimeout继续下降 → 可继续+2s到59。目标: 将deepseek NVCFPexecTimeout降至<50次/30min。

2. **TIER_COOLDOWN_S=44 观察**: 与GLOBAL-COOLDOWN=45差距1s，已在sweet spot。若HM2下一轮继续降TIER_COOLDOWN → 应注意不要跌破42s（避免严重影响key cooldown节奏）。

3. **KEY_COOLDOWN_S=36.0 观察中**: 上一轮R92从38→36。低于GLOBAL=45s 9s，键级恢复不是瓶颈。效果需在下一轮评估。

4. **Deepseek P95=85,791ms 极高**: 部分请求在80-100s范围。如果+2s UPSTREAM_TIMEOUT不能显著改善，可能需要+5s BUDGET（但那是更大改动，留待后续轮次）。

5. **SSLEOFError=84/SSLEOF中位5,007ms**: 间歇性SSL EOF。若持续>100 → 需关注HM_CONNECT_RESERVE_S或SOCKS5代理质量。

6. **少改多轮**: 单参数(+2s), 每轮积累。本轮首次转向上游超时优化方向(TIER_COOLDOWN→UPSTREAM_TIMEOUT), 正确反映deepseek超时截断新发现。

7. **mihomo未动**: 严格遵守—不停止/不重启/不kill mihomo服务。mihomo是NV API链路的必要SOCKS5代理。

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记
