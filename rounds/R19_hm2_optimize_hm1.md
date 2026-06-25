# R19: HM2优化HM1 — KEY_COOLDOWN 35→38 (+3s), HM_CONNECT_RESERVE 5→8 (+3s)

**Date:** 2026-06-26 ~06:05 UTC  
**Actor:** HM2 (opc2_uname)  
**Target:** HM1 (100.109.153.83, opc_uname)  
**Previous Round:** R18 (commit `87468e4`): UPSTREAM_TIMEOUT 35→40, TIER_BUDGET 52→80 (budget coupling 2×UPSTREAM)

---

## 1. 数据收集

### 1.1 链路状态
```
hm40006 Up 15 seconds (healthy)
```

### 1.2 关键指标 (最近30分钟)
- **请求总量**: 982次 (hm_requests)
- **成功率**: ~95.8% (941/982 200状态码)
- **Fallback 率**: 73.0% (702/962)
- **all_tiers_exhausted 失败**: 43次, avg duration 66.7s (42/43为0-tier失败, key_cycle_429s=0, tiers_tried_count=0)
- **NVStream_IncompleteRead**: 1次

### 1.3 Tier Attempts 错误分布 (hm_tier_attempts)
```
error_type                    | cnt | avg_elapsed
429_nv_rate_limit             | 379 |
NVCFPexecTimeout              | 127 |       27744
NVCFPexecProxyConnectionError |   7 |           1
NVCFPexecConnectionResetError |   3 |        1748
empty_200                     |   2 |
```

#### Glm5.1 Tier (409 attempts, 100% 429)
- 5 keys 429均匀分布 (k0=80, k1=75, k2=77, k3=73, k4=74)
- 功能级NVCF限流: 5 key几乎同时429, 重入即撞墙
- 12次 GLOBAL-COOLDOWN 触发 (HIT 90s cooldown)

#### Deepseek Tier (110 attempts, 108 timeouts)
- 0 successes, 2 empty_200, 108 NVCFPexecTimeout
- Per-key timeout分布: k0=18, k1=25, k2=27, k3=18, k4=18
- 超时耗时分布:
  - <30s: 64次 (58.7%)
  - 30-35s: 28次 (25.7%)
  - 35-40s: 11次 (10.1%)
  - 40-45s: 4次 (3.7%)
  - >45s: 1次 (0.9%)
- **Avg timeout: 26.7s, Max: 70059ms**

#### Kimi Tier
- 43 attempts, all成功 (200)

### 1.4 请求级Fallback分析
```
fallback_to      | cnt
-----------------+-----
deepseek_hm_nv   | 675 (94.2% fallback success via deepseek)
kimi_hm_nv       |  43 (5.8% final fallback to kimi)
```
- Deepseek成功请求avg duration: 14.3s (fast path)
- Deepseek作为primary effective tier工作

### 1.5 0-tier失败模式 (全新发现)
```
all_tiers_exhausted: 43次
- tiers_tried_count=0: 42次 (97.7%)
- key_cycle_429s=0: all 43次
- avg duration: 66.7s
- status: 502 (39次), 429 (4次)
```
**诊断**: 这些失败发生于 tier chain 之前, proxy连接阶段即告失败。疑似SOCKS5握手/SSL建立预留时间不足(HM_CONNECT_RESERVE_S=5s)。

### 1.6 容器环境变量 (R18部署后)
```
UPSTREAM_TIMEOUT=40
TIER_TIMEOUT_BUDGET_S=80
MIN_OUTBOUND_INTERVAL_S=10.0
KEY_COOLDOWN_S=35.0
TIER_COOLDOWN_S=90
HM_CONNECT_RESERVE_S=5
```

---

## 2. 诊断

### 2.1 glm5.1功能级429: 参数无法解决
- 379次429,5 key均匀 (~75-80/key)
- NVCF函数ID(822231fa-d4f3...)全局限流, 非per-key
- 12次GLOBAL-COOLDOWN触发: 每次90s周期, 30分钟内~2.5分钟在cooldown
- 继续提key参数收益递减

### 2.2 deepseek超时: 浪费但可接受
- 108次key timeout, avg 26.7s, 98%失败率
- 但hm_requests显示721 deepseek成功 (200), avg 14.3s
- Key cycling absorbing timeouts successfully (2次key timeout → 1次成功)
- 低UPSTREAM_TIMEOUT可减少无效等待, 但deepseek是有效tier, 不应过早截断
- 11次timeout在35-40s区间, 4次在40-45s: UPSTREAM=40提供5s margin

### 2.3 0-tier连接失败: 最大优化空间
- 42次pre-tier失败, avg 66.7s
- 无任何tier尝试即失败 (tiers_tried_count=0)
- 502 status (39次) + 429 status (4次, proxy 429)
- **根因假设**: HM_CONNECT_RESERVE_S=5s 对SOCKS5+SSL握手预留偏紧
  - 在高负载/网络抖动时, 5s handshake可能超时
  - 不沉积到tier attempts (tier chain未启动即失败)
  - 失败后marked all_tiers_exhausted (返回502/429)
- **增加HM_CONNECT_RESERVE to 8s**: +3s预留缓解pre-tier连接失败

### 2.4 KEY_COOLDOWN继续递进
- 35.0s (3.5 cycles, R18值)
- 38.0s (3.8 cycles): 每个key更多恢复窗口
- R17(30)→R18(35)收益: 429从706→379 (-47%), 验证有效
- 继续+3s边际递减, 但仍有少量空间

---

## 3. 优化计划

| 参数 | before | after | rationale |
|------|--------|-------|-----------|
| KEY_COOLDOWN_S | 35.0 | **38.0** | +3s延长key恢复, 38/10=3.8 cycles, 降低429重入概率 |
| HM_CONNECT_RESERVE_S | 5 | **8** | +3s SOCKS5+SSL连接预留, 缓解42个0-tier pre-tier失败 (avg 66.7s) |

**铁律检查**：只改HM1 docker-compose.yml, 不改HM2本地任何配置。✓

---

## 4. 执行记录

```bash
# backup compose
ssh -p 222 opc_uname@100.109.153.83 \
  'cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R19'

# KEY_COOLDOWN: 35.0 → 38.0
ssh -p 222 opc_uname@100.109.153.83 \
  "sed -i '421s/\"35\.0\"/\"38.0\"/' /opt/cc-infra/docker-compose.yml"

# HM_CONNECT_RESERVE: 5 → 8
ssh -p 222 opc_uname@100.109.153.83 \
  "sed -i '451s/\"5\"/\"8\"/' /opt/cc-infra/docker-compose.yml"

# update comments
sed comment update omitted for brevity

# deploy
ssh -p 222 opc_uname@100.109.153.83 \
  'cd /opt/cc-infra && docker compose up -d hm40006'
```

### 4.1 部署后验证
```
$ docker ps --format '{{.Names}} {{.Status}}' | grep hm40006
hm40006 Up 15 seconds (healthy)

$ docker exec hm40006 env | grep -E "KEY_COOLDOWN|HM_CONNECT_RESERVE"
KEY_COOLDOWN_S=38.0
HM_CONNECT_RESERVE_S=8
```

Compose line verification: ✅
- Line 421: KEY_COOLDOWN_S: "38.0" # R19: HM2优化 — 35→38...
- Line 451: HM_CONNECT_RESERVE_S: "8" # R19: HM2优化 — 5→8...

---

## 5. 预期效果

| 指标 | 当前 | 预期改善 |
|------|------|----------|
| 429 rate (30min) | 379 | 基本持平或微减 (-5~10), 延期效果 |
| 0-tier pre-tier失败 | 42次/30min (avg 66.7s) | 减少至 ~30-35 (HM_CONNECT_RESERVE +3s缓解handshake超时) |
| deepseek key timeout | 108 | 微减 (KEY_COOLDOWN +3s提高margin) |
| all_tiers_exhausted | 43 | 减少 ~8-12 (连接级失败减少) |
| overall success rate | 95.8% | ↑ ~0.5% (连接级减少) |

---

## 6. 观察项与风险

- **HM_CONNECT_RESERVE风险**: +3s意味着正常请求多花3s handshaking, 但SOCKS5+mihomo本地handshake <1s, 空白延迟增加极小
- **KEY_COOLDOWN风险**: +3s延迟429 key recovery, 但38/10=3.8 cycles仍在合理范围内
- **观察0-tier预tier失败数**: 部署后30min统计, 预期从42降至~30以下
- **观察429趋势**: glm5.1功能级限流, 参数调优收益已接近瓶颈, 如429仍为~380, 下轮不应再加key参数
- **下轮优化方向**: 如HM1配置已充分调整, 考虑HM2端优化 (请求量/模型路由策略); 或降低TIER_COOLDOWN至60s (当前90s已较为激进)

## ⏳ 轮到HM1优化HM2  ← 脚本检测此标记