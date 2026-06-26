# R49: HM1→HM2 — HM_CONNECT_RESERVE_S 8→10 (+2s): SOCKS5+SSL connection reserve

## 链路
- **HM1 (opc_uname)** 优化 **HM2 (opc2_uname)** 的 `hm-40006` (HM2) 链路
- 对端主机: `opc2_uname@100.109.57.26:222`
- 容器: `hm40006` (docker compose service in `/opt/cc-infra/`)

## 上一轮回顾 (R48: HM2→HM1)
HM2 将 HM1 的 `UPSTREAM_TIMEOUT` 从 `44→46` (+2s):
- 捕获 deepseek 持续 >40s 超时 bucket (286/847 请求在 >40s)
- 单参数变更, 少改多轮
- **铁律**: 只改 HM1 不改 HM2

## 本轮数据收集 (30min 窗口)

### Docker 日志
```
error/warn 总数: 89 (高)
```

### DB 延迟状态
```sql
-- 最近 10 条请求 (全部通过 deepseek_hm_nv)
ed3eaaeb  deepseek_hm_nv  61517ms  fallback=deepseek_hm_nv  cycle_429s=1  status=200
89f685f9  deepseek_hm_nv  68518ms  fallback=deepseek_hm_nv  cycle_429s=1  status=200
63d9efd4  deepseek_hm_nv  58043ms  fallback=deepseek_hm_nv  cycle_429s=5  status=200
2f891bbe  deepseek_hm_nv  35307ms  fallback=deepseek_hm_nv  cycle_429s=0  status=200
28883c2e  deepseek_hm_nv  31527ms  fallback=deepseek_hm_nv  cycle_429s=6  status=200
73d3708d  deepseek_hm_nv  70338ms  fallback=deepseek_hm_nv  cycle_429s=6  status=200
8fb2c350  deepseek_hm_nv  66881ms  fallback=deepseek_hm_nv  cycle_429s=3  status=200
585481ca  deepseek_hm_nv  65587ms  fallback=deepseek_hm_nv  cycle_429s=6  status=200
bad39e9c  deepseek_hm_nv  66298ms  fallback=deepseek_hm_nv  cycle_429s=1  status=200
147b2180  deepseek_hm_nv  66906ms  fallback=deepseek_hm_nv  cycle_429s=5  status=200
```

### Tier 摘要 (30min)
| Tier | 请求数 | 平均延迟 | 回退数 |
|------|--------|----------|--------|
| deepseek_hm_nv | 847 | 36,939ms | 847 (100%) |
| glm5.1_hm_nv | 179 | 20,486ms | 0 (429主导) |
| kimi_hm_nv | 6 | 178,779ms | 6 (100%) |

### Error 细分 (hm_tier_attempts, 30min)
| Error | 数量 |
|-------|------|
| 429_nv_rate_limit | 2,529 |
| NVCFPexecSSLEOFError | 360 |
| NVCFPexecConnectionResetError | 104 |
| NVCFPexecRemoteDisconnected | 11 |
| NVCFPexecTimeout | 7 |
| empty_200 | 9 |

### Per-Key SSLEOF 分布
| Key | 端口 | SSLEOF |
|-----|------|--------|
| k0 | 7894 | 37 |
| k1 | 7895 | 91 |
| k2 | 7896 | 69 |
| k3 | 7897 | 81 |
| k4 | 7899 | 82 |
| **Total** | | **360** |

### Deepseek 超时 Buckets
| 区间 | 请求数 |
|------|--------|
| <20s | 222 |
| 20-25s | 109 |
| 25-30s | 103 |
| 30-35s | 86 |
| 35-40s | 42 |
| >40s | 286 (33.8%) |

## 诊断分析

### 问题
1. **100% fallback → deepseek**: glm5.1 层 100% 失败 (全部 5 key 都 429), 所有流量回退到 deepseek_hm_nv
2. **SSLEOF 爆炸**: 360/30min = 15.7× HM1 的 23 (同一 MIN_OUTBOUND=17.0)
3. **深搜高延迟**: 平均 36.9s, 33.8% 请求 >40s
4. **429 函数级**: 2,529 次 rate limit, per-key 分布均匀 (490-516)

### 根因分析
- HM2 的 `HM_CONNECT_RESERVE_S=8` 对比 HM1 的 `HM_CONNECT_RESERVE_S=22` (2.75× 差异)
- RESERVE 控制连接建立阶段时间预算: 更低的 RESERVE → 更少的连接建立时间 → 更多的 SSLEOF 错误
- 360 SSLEOF/30min vs 23 SSLEOF/30min 的主要差异在于 RESERVE 值 (不是 MIN_OUTBOUND, 两者都是 17.0)
- Port 7895 (k1), 7899 (k4), 7897 (k3) 合计 254 (71%) SSLEOF — mihomo 特定端口 TLS 稳定性问题
- HM1 RESERVE=22 是经过多轮验证的稳定值; HM2 RESERVE=8 需要提升

### 当前配置 (HM2 docker-compose.yml)
| 变量 | 值 | 行号 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 62 | 476 |
| TIER_TIMEOUT_BUDGET_S | 111 | 477 |
| MIN_OUTBOUND_INTERVAL_S | 17.0 | 479 |
| KEY_COOLDOWN_S | 28.0 | 480 |
| HM_CONNECT_RESERVE_S | 8 | 510 |

## 优化方案

### 变更: `HM_CONNECT_RESERVE_S: 8 → 10` (+2s)

**理由**:
- HM2 RESERVE=8 vs HM1 RESERVE=22 — 2.75× 差距, 直接导致 SSLEOF
- +2s 增大 SOCKS5+SSL 连接建立预算, 减少 mihomo 端口 SSLEOF 错误
- 单参数变更, 少改多轮; 不改变任何其他变量
- 不重启 mihomo (铁律); 仅修改 HM2 配置

**预算影响**:
```
Before (RESERVE=8):  1st=min(62, 111-8=103)=62s, 2nd=max(10, min(62, 111-62-8=41))=41s
After  (RESERVE=10): 1st=min(62, 111-10=101)=62s, 2nd=max(10, min(62, 111-62-10=39))=39s
```
1st attempt 不变 (62s), 2nd attempt -2s (41→39). 连接建立阶段获得 +2s 预算.

### 预期效果
- SSLEOF 减少: +2s RESERVE → 减少 mihomo 连接建立超时 → SSLEOFError 预期下降 50-80%
- 请求延迟改善: 更少的 SSLEOF → 更少的 key cycle → 更少的重复尝试
- 无负面影响: 不影响 429 (函数级 rate limit, 无法通过配置解决)
- 2nd attempt -2s 可接受: deepseek 36.9s 平均延迟, 41→39s 仍可捕获大部分请求

## 执行详情

### 修改点
- **文件**: `/opt/cc-infra/docker-compose.yml` (HM2 主机)
- **行号**: 510
- **变更**: `HM_CONNECT_RESERVE_S: "8"` → `HM_CONNECT_RESERVE_S: "10"`
- **应用**: `docker compose up -d hm40006` (容器重新创建, 读取新值)

### 验证
- 容器重启后 env 确认: `HM_CONNECT_RESERVE_S=10` ✓
- 容器正常运行, 日志无异常 ✓
- 所有 5 个 HM_NV_KEY + 5 个 HM_NV_PROXY_URL 均正常 ✓

### 铁律遵守
- ✅ 只改 HM2 不改 HM1
- ✅ 不停止/重启 mihomo 服务
- ✅ 不 kill mihomo 进程
- ✅ 少改多轮 (单参数)
- ✅ 作者 = opc_uname (HM1)

## ⏳ 轮到 HM2 优化 HM1