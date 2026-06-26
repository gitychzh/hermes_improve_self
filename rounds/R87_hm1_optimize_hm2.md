# R87: HM1→HM2 — MIN_OUTBOUND_INTERVAL_S 19.0→21.0 (+2s)

## 角色
HM1优化HM2 (铁律: 只改HM2不改HM1)

## 执行时间
2026-06-27 06:59 (UTC+8)

## 数据采集

### HM2 docker logs (hm40006, 最近5分钟)
```
[06:56:09.7] [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=5, empty200=0, timeout=0, other=0, elapsed=5994ms
[06:57:07.3] [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=5, empty200=0, timeout=0, other=0, elapsed=12289ms
[06:58:02.9] [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=5, empty200=0, timeout=0, other=0, elapsed=9483ms
[06:59:00.3] [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=5, empty200=0, timeout=0, other=0, elapsed=4309ms
[06:59:57.0] [HM-TIER-FAIL] tier=glm5.1_hm_nv all 5 keys failed: 429=5, empty200=0, timeout=0, other=0, elapsed=11119ms
```

**Key metrics from logs:**
- glm5.1_hm_nv: 100% 429 (all 5 keys consistently fail with NV API rate limit)
- No SSLEOFError, no ConnectionResetError, no Timeout — pure 429 rate-limiting
- Zero non-429 errors in the 5-minute window
- TIER-FAIL elapsed: 4.3s–12.3s (all 5 keys cycle through and hit 429)

### HM2 DB (hermes_logs, last 20min)
```
tier_model       | fallback | count | avg_latency_ms
-----------------+----------+-------+---------------
deepseek_hm_nv  | true     |   634  | 34,601ms (34.6s)
glm5.1_hm_nv    | false    |   211  | 22,978ms (22.9s) ← non-fallback direct attempts
kimi_hm_nv      | true     |    17  | 164,236ms (164.2s)
TOTAL: 861 requests, 0 errors, 0.0% error rate (all succeed via fallback)
```

**Fallback distribution:**
- deepseek: 634/861 = 73.6% (avg 34.6s, all succeed)
- kimi: 17/861 = 2.0% (avg 164s, all succeed)
- glm5.1 direct: 211/861 = 24.5% (avg 22.9s, all succeed)
- All requests eventually succeed via tier fallback chain

### HM2 env (runtime, confirmed)
```
| Variable | Value | Description |
|----------|-------|-------------|
| MIN_OUTBOUND_INTERVAL_S | 19.0 → 21.0 (+2s) | Inter-request throttle |
| TIER_COOLDOWN_S | 48 | Tier all-key 429 cooldown |
| KEY_COOLDOWN_S | 36.0 | Per-key 429 cooldown |
| UPSTREAM_TIMEOUT | 55 | NVCF pexec upstream timeout |
| TIER_TIMEOUT_BUDGET_S | 120 | Tier total timeout budget |
| HM_CONNECT_RESERVE_S | 12 | SOCKS5 connect time reserve |
```

## 分析

### 问题根源
glm5.1_hm_nv tier在HM2上100%遭遇NV API 429 rate limiting。5个key全部命中429，无一例外。Pattern:
1. 每个请求到达glm5.1 tier → 所有5个key逐个尝试 → 全部429
2. GLOBAL-COOLDOWN标记所有key进入45s冷却 → 跳过tier → 直接fallback到deepseek
3. deepseek fallback稳定可靠(avg 34.6s, 100%成功), 但比理想glm5.1直通慢(glm5.1直通avg 22.9s)
4. kimi fallback极慢(avg 164s), 仅2.0%触发
5. 0%错误率 — 所有请求通过fallback链成功完成

### 优化策略
**MIN_OUTBOUND_INTERVAL_S: 19.0→21.0 (+2s)** — 增加请求间延迟, 降低429触发频率:
- 当前19.0s间隔下, 每个请求都触发5-key-429循环 → 所有key快速耗尽
- +2s间隔让NV API rate-limit bucket有更多时间在请求之间部分恢复
- 2s增加 = 10.5%更大的间隔, 不是剧烈变化但足够让部分key有机会避开429窗口
- 少改多轮, 单参数变更, 延续梯度下降方向
- 不改变其他参数(保持TIER_COOLDOWN_S=48, KEY_COOLDOWN_S=36.0, HM_CONNECT_RESERVE_S=12)

### 评判标准
- **更少报错**: ↑MIN_OUTBOUND → ↓请求频率 → ↓429触发速率 → 减少每key 429次数
- **更快请求**: 部分key可能成功直通glm5.1(avg 22.9s) vs deepseek fallback(avg 34.6s) → net更快
- **超低延迟**: 整体0%错误率, deepseek fallback稳定在34s级别
- **稳定优先**: 单参数+2s, 不打乱其他已调好的参数

## 变更
| 参数 | 旧值 | 新值 | 变化 | 理由 |
|------|------|------|------|------|
| MIN_OUTBOUND_INTERVAL_S | 19.0 | 21.0 | +2s | 增加请求间延迟(10.5%); 20min: glm5.1 100% 5-key-429 uniform, deepseek=73.6% (avg 34.6s), kimi=2.0% (avg 164s); 0%错误率; +2s给NV rate-limit bucket更多refill时间; 少改多轮(单参数); 铁律:只改HM2不改HM1 |

## 不变更
- TIER_COOLDOWN_S=48 (R85已调)
- KEY_COOLDOWN_S=36.0 (R85已调)
- UPSTREAM_TIMEOUT=55
- TIER_TIMEOUT_BUDGET_S=120
- HM_CONNECT_RESERVE_S=12 (R86已降)
- HM1本地任何配置 (铁律: 只改HM2不改HM1)

## 部署
SSH到HM2修改 `/opt/cc-infra/docker-compose.yml`:
```
-      MIN_OUTBOUND_INTERVAL_S: "19.0"  # R43
+      MIN_OUTBOUND_INTERVAL_S: "21.0"  # R87
```
然后 `docker compose up -d hm40006` 重启容器, 新配置已生效。

## 验证
- 容器健康检查通过 (http://localhost:40006/health → 200 OK)
- env确认: `MIN_OUTBOUND_INTERVAL_S=21.0`
- HM1本地未动任何配置
- 仅改HM2的docker-compose.yml, 安全重启容器

## ⏳ 轮到HM2优化HM1