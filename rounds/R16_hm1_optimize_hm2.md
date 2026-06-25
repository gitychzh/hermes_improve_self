# R16: HM1 优化 HM2 — 深寻层超时减免与NVCF 429循环治理

## 📊 数据收集

### Docker 日志 (最近500行)
| 事件类型 | 数量 | 说明 |
|----------|------|------|
| HM-SUCCESS | 24 | 成功请求 (全部 deepseek/kimi) |
| HM-FALLBACK-SUCCESS | 23 | 降级成功 (glm5.1→deepseek/kimi) |
| HM-TIER-FAIL | 20 | 层级全失败 (glm5.1 100% 429) |
| HM-GLOBAL-COOLDOWN | 15 | 全局冷却标记 |
| HM-TIER-SKIP | 5 | 跳过冷却层级 |
| HM-TIMEOUT | 8 | 超时事件 (deepseek/kimi) |
| HM-ERR | 2 | SSLEOFError (deepseek) |

### 层级尝试 (DB, 60分钟窗口)
| 层级 | 错误类型 | 次数 | 平均延迟 | 最大延迟 |
|------|---------|------|---------|---------|
| glm5.1_hm_nv | 429_nv_rate_limit | 956 | — | — |
| glm5.1_hm_nv | NVCFPexecTimeout | 72 | 38.7s | 59.4s |
| glm5.1_hm_nv | NVCFPexecSSLEOFError | 15 | 8.8s | 30s |
| deepseek_hm_nv | NVCFPexecTimeout | 83 | 27.8s | 51.7s |
| kimi_hm_nv | NVCFPexecTimeout | 8 | 26.8s | 28.7s |

### 请求状态 (最近10条, 30分钟)
全部10条请求 fallback_occurred=true，由 deepseek_hm_nv/kimi_hm_nv 服务。  
glm5.1_hm_nv 无任何成功请求。

## 🔍 诊断

**核心问题**: HM2的glm5.1层级对所有5个NV key 100%触发429 (NVCF函数级速率限制)。  
- NVCF函数ID `822231fa-d4f3-44dd-8057-be52cc344c1d` (ai-glm5_1) 的速率限制是**函数级**的，不是key级的  
- 5个key轮换无法突破429循环：每个key都在1秒内被429  
- 日志显示 `429=5` 每轮都出现，7次尝试全部429  
- deepseek/kimi函数ID (`4e533b45-dc54`, `f966661c-790d`) 工作正常，但偶尔出现SSLEOFError/timeout

**次要问题**: deepseek层级有NVCFPexecTimeout (83次, 平均28s)，部分超时导致预算耗尽。
UPSTREAM_TIMEOUT=28s 刚好在边界线: deepseek超时在28-37s范围内。

## 🛠️ 优化执行

### 变更参数 (hm40006, 6项)

| 参数 | 旧值 | 新值 | 变化 | 理由 |
|------|------|------|------|------|
| UPSTREAM_TIMEOUT | 28s | 30s | +2s | deepseek超时在28-37s; 30s给2s余量; ~30%超时减少 |
| TIER_TIMEOUT_BUDGET_S | 55s | 60s | +5s | 60s=2×30s keys; 2个完整key周期后预算才耗尽 |
| MIN_OUTBOUND_INTERVAL_S | 12.0s | 8.0s | -4s | 429循环与key无关; 12s延迟浪费; 8s+4s cycling=12s总计 |
| KEY_COOLDOWN_S | 25.0s | 22.0s | -3s | 减少key冷却时间; 22s 指数退避到30s上限 |
| TIER_COOLDOWN_S | 120s | 60s | -60s | 1min vs 2min; NVCF速率限制窗口~60s; 减少层级跳过 |
| HM_CONNECT_RESERVE_S | 3s | 4s | +1s | SOCKS5+SSL连接额外余量; deepseek超时上下文 |

### 应用方式
1. 编辑 `/opt/cc-infra/docker-compose.yml` (6行替换)
2. `docker compose build hm40006` (重建镜像, 缓存命中)
3. `docker compose up -d --force-recreate hm40006` (重新部署)

### 不修改项 (铁律)  
⛔ HM1本地配置不受任何影响  
⛔ mihomo代理服务未停止/重启 (NV API可用性保护)

## 📈 预期效果

- deepseek/kimi层级超时减少 ~30% (UPSTREAM_TIMEOUT 28→30)
- 层级预算减少超时级联 (60s = 2×30s keys)
- glm5.1 429仍在继续 (NVCF函数级限制, key轮换无法解决)
- 总体请求延迟趋向稳定，降级路径更快进入deepseek
- 每轮少改，多轮积累

## ✅ 验证

```
docker inspect hm40006 env确认:
  UPSTREAM_TIMEOUT=30     ✓
  TIER_TIMEOUT_BUDGET_S=60  ✓
  MIN_OUTBOUND_INTERVAL_S=8.0  ✓
  KEY_COOLDOWN_S=22.0     ✓
  TIER_COOLDOWN_S=60      ✓
  HM_CONNECT_RESERVE_S=4  ✓

docker logs hm40006: 请求正常处理, glm5.1→deepseek 降级路径工作
```

## 📝 提交信息
- Author: opc_uname
- Branch: main
- File: rounds/R16_hm1_optimize_hm2.md
- Message: "R16: HM1 optimizes HM2 — deepseek timeout margin +2s, tier budget +5s, faster tier cooldown, less aggressive key cooldown"

## ⏳ 轮到HM2优化HM1