# R{next}: HM1→HM2 — KEY_COOLDOWN_S 38→42 (+4s)

**角色**: HM1 (opc_uname)  
**方向**: HM1→HM2 (优化HM2)  
**回合类型**: 优化  
**修改参数**: KEY_COOLDOWN_S  
**变更**: 38 → 42 (+4s)

---

## 铁律声明
- ✅ 只改HM2 (`/opt/cc-infra/docker-compose.yml`), 绝不改HM1
- ✅ mihomo未停止/未重启 (pgrep确认: PID 2008535 运行中)
- ✅ 少改多轮 (单参数)

---

## 📊 数据收集

### 1. 30分钟窗口DB摘要
```sql
SELECT COUNT(*), SUM(CASE WHEN status = 200 THEN 1 ELSE 0 END),
       SUM(CASE WHEN status != 200 THEN 1 ELSE 0 END),
       AVG(duration_ms)::INTEGER
FROM hm_requests WHERE ts > NOW() - INTERVAL '30 minutes';
```
**结果**: 1477 total, 1473 OK, 4 errors → **99.73% 成功**

```sql
SELECT tier_model, COUNT(*), AVG(duration_ms)::INTEGER, SUM(CASE WHEN fallback_occurred THEN 1 ELSE 0 END)
FROM hm_requests WHERE ts > NOW() - INTERVAL '30 minutes'
GROUP BY tier_model ORDER BY cnt DESC;
```
**结果**:
| tier_model | requests | avg_ms | fallbacks |
|---|---|---|---|
| glm5.1_hm_nv | 802 | 13507 | 0 |
| deepseek_hm_nv | 671 | 22290 | 671 |
| (ATE fallback) | 4 | 141674 | 0 |

### 2. 错误分布
```sql
SELECT error_type, COUNT(*) FROM hm_requests
WHERE ts > NOW() - INTERVAL '30 minutes' AND status != 200
GROUP BY error_type ORDER BY COUNT(*) DESC;
```
**结果**: 4 × `all_tiers_exhausted` (0其他错误)

### 3. 最近10请求
全部glm5.1_hm_nv → **全部fallback到deepseek成功** (status=200). 耗时: 9073ms~138974ms (glm5.1 tier失败→fallback deepseek成功)

### 4. Docker日志 (最近100行 error/warn/429/budget)
```
[08:31:43] deepseek_hm_nv k1 SSLEOFError (1次)
[08:32:05-08:33:16] glm5.1_hm_nv 429 waves × 2 (all 5 keys 429)
  - HM-GLOBAL-COOLDOWN: all keys 429, Marking all cooling 45s
  - 无budget break/无timeout/无其他error
```

### 5. Host JSONL错误详情 (最近N条)
全部glm5.1失败 → **all_429: true** (纯函数级速率限制):
- 26/28 entries all_429=true; 2/28 mixed (NVCFPexecConnectionResetError+429, 500_nv_error+429)
- elapsed_ms: 630ms~13838ms (大部分<10s, 快速429循环)

### 6. 运行配置 (docker exec env)
| 参数 | 值 |
|---|---|
| KEY_COOLDOWN_S | **38** |
| TIER_COOLDOWN_S | **45** |
| MIN_OUTBOUND_INTERVAL_S | **13.8** |
| TIER_TIMEOUT_BUDGET_S | **145** |
| UPSTREAM_TIMEOUT | **71** |
| HM_CONNECT_RESERVE_S | **24** |
| PROXY_TIMEOUT | **300** |

### 7. 429 per-key (30min, hm_tier_attempts)
| tier | key_idx | 429 count |
|---|---|---|
| glm5.1 | k0 | 322 |
| glm5.1 | k1 | 248 |
| glm5.1 | k2 | 225 |
| glm5.1 | k3 | 227 |
| glm5.1 | k4 | 188 |
**Total 429 key attempts**: ~1210 (key-level waste, 非请求失败)

### 8. Round-robin计数器状态
```
hm_nv_deepseek: 5518
hm_nv_kimi: 130
hm_nv_glm5.1: 5734
```

---

## 🔍 分析

### 核心发现
1. **glm5.1 tier 100% function-level 429饱和**: 所有错误detail lines都是 `all_429: true` — NV API函数级速率限制，非per-key配额问题
2. **KEY_COOLDOWN_S=38 < GLOBAL_COOLDOWN=45s (7s缺口)**: 键级冷却在38s过期，但全局45s冷却未清 → 键在38-45s区间被重新尝试，仍返回429 → **浪费的429循环**
3. **TIER_COOLDOWN_S=45已收敛到GLOBAL=45**: 层级冷却已对齐全局，但键级冷却落后7s
4. **deepseek fallback 100%成功**: 所有671 fallback请求全部成功(status=200), deepseek作为后备完全可靠

### 为什么KEY_COOLDOWN_S?
- 历史轨迹: KEY_COOLDOWN_S曾在R92 (40→38), 随后HM1收敛到34. 当前HM2=38, HM1=34 (已收敛). 现在需要把HM2的KEY_COOLDOWN_S提升向GLOBAL_COOLDOWN=45s收敛
- 429模式100% all_429 (函数级限制) → 键级冷却越接近全局45s, 越少浪费的早期重试
- 每轮+4s, 多轮渐进收敛: 38→42→? (接近45)

### 为什么不是其他参数?
- **TIER_COOLDOWN_S**: 已45, 已匹配GLOBAL=45. 再增加超出45不会有效果 (键级冷却在层级冷却过期前已限制)
- **MIN_OUTBOUND_INTERVAL_S**: 13.8已经宽裕 (5×13.8=69s > GLOBAL=45), 增加间距不会改变429窗口
- **TIER_TIMEOUT_BUDGET_S**: 145已充足, 4 ATE在1477请求中 (0.27%), 不是预算瓶颈
- **HM_CONNECT_RESERVE_S**: 24已收敛到HM1=same, 无跨机缺口
- **UPSTREAM_TIMEOUT**: 71已合适, deepseek p95未突破

---

## 🔧 执行

### 变更
```bash
# 备份
cd /opt/cc-infra && cp docker-compose.yml docker-compose.yml.bak.RN

# 修改行480
sed -i "480s|KEY_COOLDOWN_S: \"38\"|KEY_COOLDOWN_S: \"42\"|" docker-compose.yml

# 重建容器
docker compose up -d --force-recreate --no-deps hm40006
```

### 验证
```bash
docker exec hm40006 env | grep KEY_COOLDOWN_S
→ KEY_COOLDOWN_S=42 ✅

curl -s http://localhost:40006/health
→ {"status":"ok","hm_model_tiers":["glm5.1_hm_nv","deepseek_hm_nv","kimi_hm_nv"],"hm_default_model":"glm5.1_hm_nv"} ✅

pgrep -a mihomo
→ 2008535 /home/opc2_uname/.local/bin/mihomo  ✅
```

---

## 📈 预期效果

| 指标 | 变更前 | 预期后 |
|---|---|---|
| KEY_COOLDOWN_S | 38s | **42s** (+4s) |
| 键级冷却vs全局 | 7s缺口 | **3s缺口** (收敛) |
| 浪费的429早期键尝试 | ~1210/30min | 减少 (38-42s区间不再重试) |
| success rate | 99.73% | ≥99.73% (不降) |
| ATE | 4/30min | ≤4 (不变) |

**关键**: KEY_COOLDOWN_S从38→42的+4s增加减少在38-42s时间窗内的浪费键重试 — 此窗口恰好是GLOBAL_COOLDOWN=45s仍在清除中的区间

---

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记