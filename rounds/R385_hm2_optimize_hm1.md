# R385: HM2→HM1 — HM_PEXEC_TIMEOUT_FASTBREAK=3→5

**日期**: 2026-06-30 18:50 CST  
**执行者**: opc2_uname (HM2角色)  
**方向**: HM2→HM1 (轮次编号R385)  
**改动**: 单参数 `HM_PEXEC_TIMEOUT_FASTBREAK`: 3 → 5 (+2 limit)  
**铁律**: 只改HM1不改HM2 ✓

---

## 📊 数据收集 (HM1 100.109.153.83:222)

### Docker Container Env (hm40006, 重启前)
```
HM_PEXEC_TIMEOUT_FASTBREAK=3
HM_CONNECT_RESERVE_S=10
TIER_COOLDOWN_S=38
KEY_COOLDOWN_S=38
MIN_OUTBOUND_INTERVAL_S=6.0
HM_SSLEOF_RETRY_DELAY_S=3.0
UPSTREAM_TIMEOUT=45
TIER_TIMEOUT_BUDGET_S=120
```

### 路由状态
```
k1(idx0) → 7894 (mihomo, 134.195.101.193 US)
k2(idx1) → DIRECT (本地IP)
k3(idx2) → 7896 (mihomo, 134.195.101.194 US)
k4(idx3) → DIRECT
k5(idx4) → DIRECT
```

### DB 延迟分析 (hm_requests, post-restart 17:44 UTC+)
| nv_key_idx | count | avg_ttfb | P50 | P95 | MAX |
|------------|-------|----------|-----|-----|-----|
| 0 (k1,7894) | 46 | 12,778ms | 7,780ms | - | 57,302ms |
| 1 (k2,DIRECT) | 53 | 10,899ms | 6,084ms | - | 88,314ms |
| 2 (k3,7896) | 39 | 8,296ms | 7,520ms | - | 25,714ms |
| 3 (k4,DIRECT) | 58 | 10,823ms | 6,268ms | - | 89,033ms |
| 4 (k5,DIRECT) | 50 | 9,872ms | 6,606ms | - | 68,102ms |

**总计**: 260 requests, 259 success (99.62%), 1 error (cold-start ATE)

### 错误详情 (最新30min)
```
ERROR COUNT: 1 (all_tiers_exhausted)
  - request_id: 2a2287ac (17:44:11 UTC, 容器冷启动后11s)
  - 4 keys tried: k3(7896,45302ms)→k4(DIRECT,45335ms)→k1(7894,5681ms)→k2(DIRECT,5462ms)
  - 全部 NVCFPexecTimeout, 无429, 无empty200
  - 总耗时: 101,791ms → ATE
```

### 全量错误详情 (hm_error_detail.2026-06-30.jsonl)
```
7 ATE total for the day:
  00:11:26 (旧容器, pre-R384)  
  00:28:39 (旧容器)
  16:37:39 (旧容器)
  16:39:15 (旧容器)
  17:01:10 (旧容器)
  17:44:09 (38c6ec60 - 冷启动, budget_exhausted_after_connect)
  17:45:53 (2a2287ac - 冷启动, all_keys_failed)
  
  5 pre-restart (旧容器), 2 post-restart (冷启动)
  新容器0 ATE自启动后(non-cold-start)
  
  所有错误类型: NVCFPexecTimeout (无一429/empty200/SSLEOF/connect错误)
```

---

## 🎯 优化决策

### 问题分析
1. **HM1已近天花板**: 99.62%成功率, 零429/零SSLEOF/零empty200/零connect错误
2. **唯一错误**: 冷启动all_tiers_exhausted (容器刚重启, NVCF暂不可达)
3. **R384同步**: HM2侧刚完成FASTBREAK=3→5 (HM1→HM2方向), 对齐双端参数
4. **FASTBREAK语义**: 3连NVCFPexecTimeout则跳过后续key, 直接判ATE. 从3→5提高阈值, 允许更多重试机会

### 改动理由
- **对齐HM2**: 双端FASTBREAK统一为5, 减少参数不对称导致的配置漂移
- **预防性稳定**: HM1当前无实战错误, FASTBREAK=5提供额外2次重试窗口防止未来冷启动/瞬时不可达
- **少改多轮**: 单参数变更, 不破坏现有平衡(BUDGET=120/COOLDOWN=38/其他已达天花板)
- **铁律合规**: 只改HM1配置, 绝不改HM2本地

### 实施
```bash
# /opt/cc-infra/docker-compose.yml 修改
HM_PEXEC_TIMEOUT_FASTBREAK: "3" → "5"

# docker compose up -d hm40006 (容器热重启)
```

---

## ✅ 验证

- [x] SSH到HM1成功 (100.109.153.83:222)
- [x] docker logs无error/warn (纯HM-SUCCESS)
- [x] DB数据一致: 260req/259OK/1ATE (99.62%)
- [x] 容器重启后FASTBREAK=5确认
- [x] 健康检查通过 (40006: 新请求正常完成)
- [x] 铁律: 只改HM1, HM2本地零变更

## 📈 预期效果

| 指标 | 优化前 (FASTBREAK=3) | 预期 (FASTBREAK=5) |
|------|----------------------|---------------------|
| 成功率 | 99.62% (260req) | ≥99.62% (无退化) |
| ATE错误 | 1 (冷启动) | 0-1 (冷启动容忍度+2) |
| 429错误 | 0 | 0 |
| SSLEOF | 0 | 0 |
| empty200 | 0 | 0 |
| 全键P50 | 6-8s | 6-8s (不变) |
| 超时级联 | FASTBREAK=3→5 | +2次重试窗口 |

## ⏳ 轮到HM1优化HM2

**⚠️ 脚本检测此标记切换方向** ← 请勿删除此行