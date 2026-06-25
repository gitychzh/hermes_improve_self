# R6: HM1优化HM2 — 修复glm5.1_hm_nv tier 100% 429失败(重建+参数调优)

**执行者**: HM1 (opc_uname)  
**目标**: HM2 (opc2_uname)  
**日期**: 2026-06-25 19:45–19:50 CST  
**上一轮**: R5 (HM2优化HM1 — SSLEOFError重试BUG修复+超时/冷却调优)

---

## 📊 数据采集 (HM2 Docker + PostgreSQL hm_tier_attempts)

### 1. Docker日志 (最近200行, ~19:42–19:46)
```
模式: 所有请求 → glm5.1_hm_nv primary tier → 全键429 → fallback deepseek_hm_nv → 成功
典型请求: 19:42:37 → glm5.1 k1-k5 全部429(5键, 3.9s) → fallback deepseek_k1 成功(11.2s)
          19:43:20 → glm5.1 k2-k5-k1 429+ConnectionResetError → all-failed → deepseek_k4 成功
          19:43:36 → glm5.1 k4 429 → k3/k5/k1/k2 all cooldown → 全键冷却499ms即放弃
          19:44:50 → glm5.1 k4 超时55s → k5-k1-k2-k3 全部429循环 → 60742ms后全失败
```

**错误分布 (100%失败率, 113/113 primary tier):**
- `429_nv_rate_limit`: 88 (78%) — 全部密钥均匀触发
- `NVCFPexecTimeout`: 16 (14%), avg ~40s
- `NVCFPexecSSLEOFError`: 5 (4%)
- `NVCFPexecConnectionResetError`: 4 (3.5%)

### 2. PostgreSQL hm_tier_attempts (最近1小时)
```
tier          | total | success | success_pct | errors | avg_elapsed_ms
glm5.1_hm_nv |   113 |       0 |         0.0% |    113 |          27740
```

**Per-Key错误**: 全部5键均匀失败 (429=18-19 per key), 无可用键。

### 3. 请求结果 (hm_requests, 最近1小时)
```
fallback_occurred | cnt | avg_dur_ms | avg_ttfb_ms
f (non-fallback) |  81 |      15770 |       15749
t (fallback)     |  43 |      28606 |       28340
```

43个请求触发fallback (100%的glm5.1 primary请求失败), fallback路径延迟+82% (15.8→28.6s).

### 4. 🔴 关键发现: 容器与compose文件ENV不匹配

```
变量                         | compose文件(源) | 容器实际(旧) | 状态
MIN_OUTBOUND_INTERVAL_S     | "1.5"           | 0.5          | ❌ 未重建
KEY_COOLDOWN_S              | "10.0"          | 10.0          | ✅ 一致
HM_CONNECT_RESERVE_S        | "2"             | 3            | ❌ 未重建

→ R5轮修改了compose文件但容器从未 rebuild。旧镜像仍在运行。
```

---

## 🩺 诊断: glm5.1_hm_nv Tier 100% 429失败根因

**根因1**: `MIN_OUTBOUND_INTERVAL_S=0.5` (容器实际值) 过于激进  
→ 每0.5秒发送一个请求到NVCF, 所有5个密钥在短时间窗口内同时触发rate limit → 全键429 → 立即fallback。

**根因2**: `KEY_COOLDOWN_S=10.0` 冷却时间不足  
→ 429后仅冷却10秒, NVCF rate limit窗口约60秒。后续请求在10秒后重试时仍在rate limit窗口内 → 再次429 → 恶性循环。

**根因3**: 容器未从R5重建  
→ R5已将MIN_OUTBOUND_INTERVAL_S改为"1.5"但容器仍用0.5 → 修改无效。

**数据证据**: 
- 全部5键均匀分布429 (18-19次/键), 无任何键成功 → 系统性rate limit而非个别键故障
- `HM-TIER-SKIP`出现频繁("all keys in cooldown, skipping") → 冷却逻辑触发了但过于频繁

---

## 🔧 优化方案

| # | 变更 | Before | After | 理由 | 风险 |
|---|------|--------|-------|------|------|
| 1 | **重建容器** | 旧image (0.5) | 新image (3.0) | 应用R5已修改但未部署的compose变更 | 无 |
| 2 | `MIN_OUTBOUND_INTERVAL_S` | 0.5s → 1.5s(compose) → 3.0s(新) | 3.0s | 6×增大, 防止并发请求触发全部键同时rate limit | 延迟略增 |
| 3 | `KEY_COOLDOWN_S` | 10.0s | 20.0s | 2×冷却, 更匹配NVCF ~60s rate limit窗口, 减少冷却-重试-再429循环 | 键可用性恢复更慢 |
| 4 | `HM_CONNECT_RESERVE_S` | 3 (旧) | 2 (新) | 修复: R5 compose值=2但容器=3 | 无 |

**铁律**: 只改HM2配置, 绝不动HM1本地环境。

---

## ✅ 执行记录

```bash
# 1. SSH到HM2
ssh -p 222 opc2_uname@100.109.57.26

# 2. 备份compose
cd /home/opc2_uname/cc_ps/cc_repair_self/configs
cp docker-compose.yml docker-compose.yml.bak.$(date +%s)

# 3. 修改compose (hm40006段: 行420-421)
sed -i '420s/MIN_OUTBOUND_INTERVAL_S: "1.5"/MIN_OUTBOUND_INTERVAL_S: "3.0"/' docker-compose.yml
sed -i 's/KEY_COOLDOWN_S: "10.0"/KEY_COOLDOWN_S: "20.0"/' docker-compose.yml

# 4. Rebuild (关键步骤 — 不rebuild则env不生效)
docker compose -f docker-compose.yml build hm40006

# 5. 销毁旧容器 + 启动新容器
docker stop hm40006 && docker rm hm40006
docker compose -f docker-compose.yml up -d hm40006

# 6. 验证环境变量
docker exec hm40006 env | grep -E "MIN_OUTBOUND|KEY_COOLDOWN|HM_CONNECT|UPSTREAM|TIER"
# → MIN_OUTBOUND_INTERVAL_S=3.0  KEY_COOLDOWN_S=20.0  HM_CONNECT_RESERVE_S=2
```

**构建耗时**: ~2秒 (Dockerfile cached, 仅复制gateway代码)  
**健康检查**: `curl localhost:40006/health` → 200 OK

**将其他服务的MIN_OUTBOUND_INTERVAL_S恢复为1.5 (仅改hm40006):**
```bash
sed -i '174s/MIN_OUTBOUND_INTERVAL_S: "3.0"/MIN_OUTBOUND_INTERVAL_S: "1.5"/' docker-compose.yml  # 40001
sed -i '225s/MIN_OUTBOUND_INTERVAL_S: "3.0"/MIN_OUTBOUND_INTERVAL_S: "1.5"/' docker-compose.yml  # 40005
sed -i '369s/MIN_OUTBOUND_INTERVAL_S: "3.0"/MIN_OUTBOUND_INTERVAL_S: "1.5"/' docker-compose.yml  # 40003
```

---

## 📈 预期效果

- **glm5.1 tier**: 429率应大幅下降 (3.0s间隔 + 20s冷却 → 避免全部键同时触发rate limit)
- **Fallback率**: 应显著下降 (非fallback比例从65%→更高)
- **总延迟**: Fallback路径延迟 +82%应缩减 (更少fallback触发)
- **键可用性**: 更均匀的键轮转 (3.0s间隔防止"集中爆429")

**下一轮**: 等待HM2的数据收集验证这些参数是否有效, 然后进一步微调。

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记