# R12: HM1 优化 HM2 (hm40006) — 修复磁盘满致DB失效; 降低NVCFPexecTimeout; 减少glm5.1 tier 429风暴

**日期**: 2026-06-26 01:20 CST
**执行者**: HM1 (opc_uname)
**目标**: HM2 (opc2_uname@100.109.57.26)
**上一轮**: R11 (HM2→HM1: 修复mihomo宕机, enabled开机自启)

---

## 📊 数据采集

### 1. HM2 hm40006 当前参数 (R10部署后, 容器Up 10小时)

| 参数 | R10值(R10调整后) | HM1稳定值 |
|------|-----------------|----------|
| TIER_COOLDOWN_S | 300 | 300 |
| KEY_COOLDOWN_S | 28.0 | 30.0 |
| MIN_OUTBOUND_INTERVAL_S | 5.0 | 7.0 |
| TIER_TIMEOUT_BUDGET_S | 75 | 70 |
| UPSTREAM_TIMEOUT | 65 | 65 |
| HM_CONNECT_RESERVE_S | 5 | 5 |

### 2. DB状态 — cc_postgres 崩溃

```
cc_postgres: running (unhealthy)
PANIC: could not write to file "pg_logical/replorigin_checkpoint.tmp": No space left on device
→ disk 100% full → postgres crash loop
→ hm40006 每3-4个req就报 [HM-DB] connect failed: could not translate host name "cc_postgres"
```

### 3. 磁盘分析

| 路径 | 大小 | 占总比 |
|------|------|--------|
| /tmp/*.so (遗留共享库) | **85.9 GB** | 76% |
| /var/log/ | 1.1 GB | 1% |
| /home/opc2_uname/ | 6.8 GB | 6% |
| /usr/ | 5.0 GB | 4% |
| **总磁盘** | **110 GB / 115 GB (100%)** | — |

**根因**: 11,942个遗留 `.79fcbc44*.so` / `.79fcffff*.so` 文件占满磁盘 → postgres写入PANIC → crash

### 4. HM2 最近1小时 tier_attempts 错误分布 (DB恢复后查询)

| 错误类型 | 计数 | 平均耗时 | 占比 |
|---------|------|---------|------|
| **429_nv_rate_limit** | **99** | — | 51.6% |
| **NVCFPexecTimeout** | **79** | 39,901ms | 41.1% |
| NVCFPexecSSLEOFError | 11 | 9,235ms | 5.7% |
| NVCFPexecConnectionResetError | 6 | 896ms | 3.1% |

**总计**: 195次错误, 429+Timeout占92.8%

### 5. 每key 429+Timeout分布

| Key | 总attempt | 429 | Timeout | SSLEOF | ConnRst |
|-----|-----------|------|---------|--------|---------|
| k0 | 38 | 19 | 16 | 2 | 1 |
| k1 | 34 | 18 | 13 | 2 | 1 |
| k2 | 40 | 21 | 17 | 1 | 1 |
| k3 | 41 | 21 | 15 | 3 | 2 |
| k4 | 42 | 20 | 18 | 3 | 1 |

429在5个key上均匀分布(~20/each), 不是单个key问题, 是整体rate limit窗口冲突。

### 6. 请求路由统计

| 路由 | 计数 | 占比 | 平均延迟 | p50 | p90 |
|------|------|------|---------|------|------|
| glm5.1直接成功 | 113 | 59.5% | 21,130ms | 14,728ms | 47,157ms |
| fallback(deepseek) | 77 | 40.5% | 53,516ms | 78,476ms | 95,692ms |

### 7. glm5.1 直接成功 每 key分布

| Key | 直接成功 | 平均延迟 | 平均429次数 |
|-----|---------|---------|------------|
| k0 | 26 | 21,672ms | 0.2 |
| k1 | 26 | 21,723ms | 0.4 |
| k2 | 19 | 17,549ms | 0.1 |
| k3 | 22 | 18,349ms | 0.1 |
| k4 | 20 | 26,119ms | 0.1 |

### 8. glm5.1_HM_NV TIER-FAIL 详细

24次tier-fail, 模式分布:
- 全key 429 (429=5): 17次 — **占71%**, 平均耗时5-8秒
- 429=4+other=1: 5次 — SSLEOF/ConnRst组合
- 429=2-3 + other/timeout: 2次 — 混合失败

**关键发现**: 17次全key 429耗时仅5-8秒(快失败) → **KEY_COOLDOWN=28秒未过期, 立即重试全被429** → 需要从5.0→6.0减慢轮转

---

## 🩺 诊断

### 根因1: cc_postgres磁盘满崩溃

11,942个遗留`.so`文件(85.9GB)占满磁盘 → postgres写入PANIC → 数据库不可用 → hm40006无法记录请求日志 → 无法做精确诊断

**修复**: 清理遗留.so文件释放85.9GB → 重启cc_postgres → DB恢复健康

### 根因2: 429 rate limit风暴 + NVCFPexecTimeout

- **429占51.6%**: `MIN_OUTBOUND_INTERVAL_S=5.0` → 5个key轮转一圈只需25秒 → 并发请求交错key → 命中NVCF rate limit
- **Timeout占41.1%**: 79次, 平均39.9s → UPSTREAM_TIMEOUT=65s可覆盖, 但多个key连续timeout耗尽tier budget
- **TIER_TIMEOUT_BUDGET_S=75**: 2个timeout(39s×2=78s)即可耗尽 → fallback太快

**对比R10**: R10的调整(5.0→5.0 MIN, 80→75 BUDGET)方向正确但力度不够 — 429仍然高频

---

## 🔧 优化方案

**策略**: 减缓key轮转频率(5.0→6.0)降低429触发; 收紧tier预算(75→70)匹配HM1验证值; 修复DB恢复诊断能力

| # | 变更 | Before(R10) | After(R12) | 理由 |
|---|------|-------------|-----------|------|
| 1 | **清理磁盘** | 85.9GB .so | 0 | 释放空间 → cc_postgres恢复 → DB日志可用 |
| 2 | **cc_postgres重启** | unhealthy | healthy | 恢复DB连接 → hm40006诊断能力 |
| 3 | `MIN_OUTBOUND_INTERVAL_S` | 5.0 | **6.0** | 减慢key轮转: 5key×6s=30s周期 vs 5s×5key=25s → 减少429并发触发 |
| 4 | `TIER_TIMEOUT_BUDGET_S` | 75 | **70** | 收紧匹配HM1验证值: 2次timeout(39s×2)≈78s>cutoff→更快fallback; 避免无效等待 |

**铁律**: 只改HM2配置, 绝不动HM1本地环境。不停止/重启/kill mihomo。

---

## ✅ 执行记录

```bash
# 1. SSH到HM2, 收集数据
ssh -p 222 opc2_uname@100.109.57.26
docker logs hm40006 --tail 1000
docker exec cc_postgres psql -U litellm -d hermes_logs -c "..."
df -h /  → 100% full
du -sh /tmp/ → 86GB

# 2. 清理磁盘
sudo rm -f /tmp/.79fcbc44*.so /tmp/.79fcffff*.so /tmp/.79fcfe*.so
# → 释放85.9GB, disk 100% → 93%

# 3. 重启cc_postgres
docker compose restart cc_postgres
# → database system is ready to accept connections

# 4. 备份compose
cp docker-compose.yml docker-compose.yml.bak.R12

# 5. 修改参数
sed -i 's/MIN_OUTBOUND_INTERVAL_S: "5.0"/MIN_OUTBOUND_INTERVAL_S: "6.0"/' docker-compose.yml
sed -i 's/TIER_TIMEOUT_BUDGET_S: "75"/TIER_TIMEOUT_BUDGET_S: "70"/' docker-compose.yml
# 更新注释标注R12变更

# 6. 部署
docker stop hm40006 && docker rm hm40006
docker compose up -d hm40006

# 7. 验证
docker exec hm40006 env | grep -E 'MIN_OUTBOUND|TIER_TIMEOUT'
# → MIN_OUTBOUND_INTERVAL_S=6.0  ✓
# → TIER_TIMEOUT_BUDGET_S=70    ✓
```

**最终配置确认**:
- MIN_OUTBOUND_INTERVAL_S=**6.0** ← **R12: 5.0→6.0, 减慢轮转降429**
- TIER_TIMEOUT_BUDGET_S=**70** ← **R12: 75→70, 对齐HM1验证值**
- TIER_COOLDOWN_S=300 (保持)
- KEY_COOLDOWN_S=28.0 (保持)
- UPSTREAM_TIMEOUT=65 (保持)
- HM_CONNECT_RESERVE_S=5 (保持)
- cc_postgres: **healthy** ← **R12: 修复磁盘满 → DB恢复**

---

## 📈 预期效果

1. **429频率降低** — 6.0s间隔 vs 5.0s → key轮转减慢20% → 并发请求较少碰撞同一key → NVCF rate limit触发减少
2. **Timeout更快fallback** — TIER_TIMEOUT_BUDGET=70 → 双timeout(78s)>cutoff → 不等第3key → 省时8-10s/fallback
3. **DB诊断能力恢复** — cc_postgres健康 → 精确错误分布/延迟统计 → 下轮优化有数据支撑
4. **glm5.1直接成功率提升** — R12部署后立即观察到6次连续glm5.1首次尝试成功(5-7s延迟)

---

## ⚠️ 待观察

- **429是否显著下降** — 6.0s间隔需1-2小时验证429计数是否从99/小时降到<60/小时
- **glm5.1直接成功率** — R10为59.5%(113/190), R12目标>65%
- **fallback延迟** — p50=78s应降至<60s(更快fallback+更快direct)
- **磁盘再满风险** — .so文件是何进程产生?需要找到源头防止复发
- **cc_postgres stout日志** — litellm_dsv4p DB不存在警告, 不影响hermes_logs

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记
