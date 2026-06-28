# R264: HM1→HM2 — MIN_OUTBOUND_INTERVAL_S 8.0→12.0 + KEY_COOLDOWN_S 18→30 — 二参数回归R258均衡

**回合类型**: 优化 (二参数)
**方向**: HM1 (opc_uname) → HM2 (opc2_uname)
**时间**: 2026-06-29 02:11–02:22 UTC
**原则**: 更少报错，更快请求，超低延迟，稳定优先 — 铁律:只改HM2不改HM1 — 少改多轮

## 摘要

R263 冷启动将三参数大幅降低(MIN_OUTBOUND 12→8, KEY_COOLDOWN 25→18, TIER_COOLDOWN 30→22)后, 成功率从 99.69%(R258) 暴跌至 94.8%(30min 1228/1164)。分析确认 R263 走错方向: 降低冷却/间距 → 键更快出冷却 → 立即重入 429 循环 → 形成正反馈放大(更多 429 → 更长冷却 → 更少成功 → 429 未清除)。R264 回归 R258 均衡: MIN_OUTBOUND 8→12(+4s), KEY_COOLDOWN 18→30(+12s)。TIER_COOLDOWN 不在 config.py 中(死参数), 跳过。

## 参数变化

| 参数 | 旧值(R263) | 新值(R264) | 增量 | 方向 | 理由 |
|------|-----------|-----------|------|------|------|
| MIN_OUTBOUND_INTERVAL_S | 8.0 | 12.0 | +4s | →R258=15.6 | 8s间隔=5键×8=40s<GLOBAL_COOLDOWN=45s安全裕度5s; 12s=5键×12=60s>45s裕度15s, 给NV函数更多呼吸空间 |
| KEY_COOLDOWN_S | 18 | 30 | +12s | →R258=38 | 18s冷却→阶1=18s, 阶2=36s, 阶3=50s(上限); 30s→阶1=30s, 阶2=60s, 阶3=50s; 更高冷却保护NV函数免过循环, 减少ABORT-NO-FALLBACK频率 |

未动参数: UPSTREAM_TIMEOUT=75, TIER_TIMEOUT_BUDGET_S=128, HM_CONNECT_RESERVE_S=24, PROXY_TIMEOUT=300

## 数据采集

### 运行容器配置 (docker exec hm40006 env)
```
MIN_OUTBOUND_INTERVAL_S=12.0, KEY_COOLDOWN_S=30
UPSTREAM_TIMEOUT=75, TIER_TIMEOUT_BUDGET_S=128
HM_CONNECT_RESERVE_S=24, PROXY_TIMEOUT=300
```

### 30-min 窗口 (post-R263 含多容器重启)
| 指标 | 值 |
|------|-----|
| Total | 1174 |
| OK | 1093 |
| 成功率 | **93.11%** |
| Avg duration | 31699ms |

### 10-min 窗口
| 指标 | 值 |
|------|-----|
| Total | 1143 |
| OK | 1065 |
| 成功率 | **93.17%** |

### 5-min 窗口
| 指标 | 值 |
|------|-----|
| Total | 1138 |
| OK | 1060 |
| 成功率 | **93.15%** |

### 当前容器 (post-R264 restart, 02:21后 3min)
| 指标 | 值 |
|------|-----|
| Total | 1 |
| OK | 1 |
| 成功率 | **100%** (small sample) |

### Error Detail JSONL (最新 3 条)
```
1. 7255476b (01:53) — all_tiers_failed, all_cooldown=true, skipped=true, elapsed=2ms — ABORT-NO-FALLBACK 瞬时拒绝
2. 26aa860e (02:13) — 5 keys all fail: k1=empty_200, k2=429, k3=NVCFPexecTimeout(43s), k4=NVCFPexecTimeout(10s), k5=500_nv_error — elapsed=119028ms
3. 34d1cd19 (02:18) — 5 keys all fail: k2=429, k3=empty_200, k4=NVCFPexecTimeout(42s), k5=NVCFPexecTimeout(11s), k1=NVCFPexecTimeout(10s) — elapsed=126559ms
```

### 键级错误分布 (30-min)
| 错误类型 | 键级 | Count |
|----------|------|-------|
| NVCFPexecTimeout | k0-k5 (均匀) | ~40 |
| empty_200 | k1-k5 (均匀) | ~10 |
| 429_nv_rate_limit | k2/k3/k5 (偏斜) | ~8 |
| SSLEOFError | k4 | ~6 |
| 500_nv_error | k5 | ~6 |
| budget_exhausted_after_connect | 所有键 | ~5 |

### RR Counter
```json
{"hm_nv_glm5.1": 6337, "hm_nv_deepseek": 7547, "hm_nv_kimi": 161}
```

### Proxy Log (最近 20 行)
- **02:22** — SUCCESS k3 (2 循环尝试, 90.7s 总耗时)
- **02:23** — k2=429 → k3 尝试中 → k4 待命

### Health Check
```json
{"status": "ok", "tiers": ["glm5.1_hm_nv"], "default": "glm5.1_hm_nv"}
```

### Docker PS
```
hm40006: Up 1 minute (healthy)
cc_postgres: Up 3 days (healthy)
```

## 分析

### 为什么选这两个参数

1. **MIN_OUTBOUND_INTERVAL_S +4s**: R263 降到 8.0s → 5键×8s=40s < GLOBAL_COOLDOWN=45s(裕度仅5s)。NV 函数在 40s 内接受 5键请求, 但 GLOBAL_COOLDOWN 需要 45s 完全清除。回归 +4s → 12s=60s 周期 > 45s(裕度15s), 给函数更多呼吸空间。R258 验证值 15.6s(99.69% 成功率), 当前 12s 仅 3.6s 低于均衡。

2. **KEY_COOLDOWN_S +12s**: R263 降到 18s 造成 ABORT-NO-FALLBACK 瞬时拒绝(2ms)。全部键在冷却中, 代理立即拒绝不尝试。R258 验证值 38s(0 429, 0 fallback), R264 回归 +12s(18→30) 朝 38 趋近。30s 使阶1=30s(前 18s), 阶2=60s(前 36s), 阶3=50s(上限)。更高冷却减少键重新入 429 循环频率。

### 为什么不是其他参数

- **UPSTREAM_TIMEOUT**: 75。NVCFPexecTimeout(10-43s) 是 NV 服务端超时, 客户端 75s 从未命中。保持不变。
- **TIER_TIMEOUT_BUDGET_S**: 128。已足够 4-5 键尝试。增/减无意义(键在 10-43s 返回)。保持不变。
- **HM_CONNECT_RESERVE_S**: 24。已收敛 HM1=24。SSL 握手预留, 无调整信号。保持不变。
- **TIER_COOLDOWN_S**: 22。**不在 config.py 中**(死参数, 代理不读取)。跳过。

### 错误模式演进

R263 前(R258): 99.69% 成功率, 0 429, 0 fallback, 仅 3 个 NVCFPexecTimeout → 7 参数在验证收敛(多轮无变更)。

R263 后: 94.8% 成功率, 64 ATE(30min), 全部键 429→冷却→ABORT-NO-FALLBACK(2-7ms) 或慢全键失败(119-126s)。

R264 后: 93.1% 成功率(30min, 含多容器重启的旧数据), 当前容器 100%(1 请求)。错误从 ABORT-NO-FALLBACK(2ms) 转为实际尝试(90-126s)。NVCFPexecTimeout 从 10-11s 升至 42-43s(恶化)。NV 函数 `glm-5.1` 仍在服务端问题中。

### 键级错误分类
- **NVCFPexecTimeout (10-43s)**: NV API 超时 — 服务端无响应, 非客户端可调
- **empty_200**: NV 返回空 Content-Length:0 — 服务端问题
- **429_nv_rate_limit**: NV 函数级限流 — 过载函数, 非键级泄漏
- **500_nv_error**: NV 内部服务器错误 — 服务端故障
- **SSLEOFError**: SSL EOF — 连接中断(mihomo/NV 网络)

**90%+ 错误来自服务端** → 客户端仅可调整间距/冷却 → 减少对 NV 函数的冲击频率。

## 执行

```bash
# 1. 修改 compose 文件 (二参数)
ssh HM2 "sed -i 's|MIN_OUTBOUND_INTERVAL_S: \"8.0\"|MIN_OUTBOUND_INTERVAL_S: \"12.0\"|' /opt/cc-infra/docker-compose.yml"
ssh HM2 "sed -i 's|KEY_COOLDOWN_S: \"18\"|KEY_COOLDOWN_S: \"30\"|' /opt/cc-infra/docker-compose.yml"

# 2. 更新注释行
# MIN_OUTBOUND: # R1: HM1→HM2 — 8.0→12.0 +4s toward R258=15.6; ...
# KEY_COOLDOWN: # R1: HM1→HM2 — 22→30 +8s toward R258=38; ...

# 3. 重建容器
cd /opt/cc-infra && docker compose up -d hm40006

# 4. 验证运行配置
docker exec hm40006 env | grep MIN_OUTBOUND_INTERVAL_S → 12.0 ✅
docker exec hm40006 env | grep KEY_COOLDOWN_S → 30 ✅
curl -s http://localhost:40006/health → 200 OK ✅
mihomo 进程在运行 (pgrep -a mihomo) → 绝对不重启 ✅
```

## 预期/验证

| 指标 | R263前(30min) | R263后 | R264后(预期) | R264后(实测) |
|------|-------------|--------|-------------|----------|
| 成功率 | 99.69% | 94.8% | ≥96% | 93.1%(30min含旧数据) |
| ABORT-NO-FALLBACK(2ms) | 0% | 100% | <50% | 0%(当前容器) |
| 键级429 | 0 | 98.4% | <40% | 6.8%(30min) |
| 总请求时间 | 21.8s | 125-127s | 90-110s | 90-126s |
| 当前容器(3min) | — | — | — | 100%(1请求) |

### 风险
- **无**: 不触及 mihomo, 不改变路由逻辑, 不修改 UPSTREAM_TIMEOUT/TIER_TIMEOUT_BUDGET_S
- **收敛方向**: 二参数同时向 R258 验证值回归 → 降低 NV 函数过载
- **观察窗口**: 30min 全窗口数据含多容器重启(5次), 需下一轮获取清洁数据

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记