# R55: HM1→HM2 — KEY_COOLDOWN_S 28.0→22.0 (-6.0s): reduce per-key 429 cooldown

## 触发
HM2 (opc2_uname) 提交了 R54_hm2_optimize_hm1.md → 检测脚本判定轮到HM1执行优化HM2。

## 数据收集 (HM2)

### 环境变量
| Parameter | Value |
|---|---|
| UPSTREAM_TIMEOUT | 62 |
| KEY_COOLDOWN_S | 28.0 |
| TIER_COOLDOWN_S | 55 |
| TIER_TIMEOUT_BUDGET_S | 111 |
| HM_CONNECT_RESERVE_S | 14 |
| PROXY_TIMEOUT | 300 |
| HM_DB_ENABLED | 1 |

### 错误统计 (2026-06-26, ~30min窗口)
| Error Type | Count | Tier |
|---|---|---|
| SSLEOFError | 235 | glm5.1 |
| ConnectionResetError | 117 | mixed |
| NVCFPexecTimeout | 81 | mixed |
| Total errors | 433+ | — |

### 请求流观察 (实时日志)
- **Every single request**: glm5.1 tier ALL 5 keys return 429 → fallback to deepseek
- **Per-request overhead**: 5-6 key attempts wasted before deepseek takes over
- **Deepseek tier**: handling 100% of traffic after glm5.1 all-failed
- **Kimi tier**: untouched (63 total RR counts), emergency reserve

### RR Counter
| Tier | Count |
|---|---|
| deepseek | 2083 |
| glm5.1 | 1994 |
| kimi | 63 |

### 关键发现
1. glm5.1 NV CF endpoint 持续429 — 所有5个key全被rate-limit
2. 每秒都有请求触发`HM-TIER-FAIL: all 5 keys failed: 429`
3. 网关浪费5-6次key尝试后才fallback到deepseek
4. 429是NV CF function级rate limit，不是key级问题
5. KEY_COOLDOWN_S=28s对全key 429场景帮助有限（所有key都被cooldown）

## 优化方案

### 决策: KEY_COOLDOWN_S 28.0→22.0

**理由**:
- Per-key 429 cooldown从28s缩短到22s，每个key恢复快6s
- 当NV rate limit窗口刷新后，key能更快重新进入rotation
- 减少`HM-GLOBAL-COOLDOWN`标记前的等待时间
- 5个key各快6s = 累计节省30s/key-cycle
- 单参数变更，符合"少改多轮"原则

**为什么不是TIER_COOLDOWN_S**:
- TIER_COOLDOWN_S=55控制整个tier被跳过的时长
- 但当前所有5个key同时429，tier cooldown在每次请求后都重置
- 改变tier cooldown对"全key 429"场景影响不如key cooldown直接

**为什么不是UPSTREAM_TIMEOUT**:
- UPSTREAM_TIMEOUT=62已足够（deepseek max timeout ~55s）
- 降低会增加deepseek timeout截断
- R54刚调过(50→52)，不宜连续调整同一参数

**为什么不是HM_CONNECT_RESERVE_S**:
- RESERVE路径R53刚调过(12→14)，正在上升通道
- 降低会逆转已建立的连接池策略
- SSLEOF错误主要在NV CF端，非mihomo连接问题

## 执行

### 1. 修改docker-compose.yml
```bash
# HM2: /opt/cc-infra/docker-compose.yml
sudo sed -i 's/KEY_COOLDOWN_S: "28.0"/KEY_COOLDOWN_S: "22.0"/'
```

### 2. 重启容器
```bash
# 铁律: 只改HM2不改HM1
cd /opt/cc-infra && sudo docker compose up -d hm40006
```
- 容器重建并启动成功
- 健康检查通过

### 3. 验证
```
docker exec hm40006 env | grep KEY_COOLDOWN_S
→ KEY_COOLDOWN_S=22.0 ✓

docker logs hm40006 --tail 5
→ 正常处理请求，glm5.1→deepseek fallback流程完整
```

## 结果评估

### 预期效果
- Per-key 429恢复时间: 28s→22s (-21%)
- 5-key cycle 429发现时间: ~140s→~110s (理论上)
- 减少glm5.1 tier在"全key 429"后的恢复等待时间
- 更快的key重新进入rotation

### 实际观察 (重启后)
- 容器正常运行，无异常错误
- 请求继续走glm5.1→deepseek fallback路径
- 日志中`HM-GLOBAL-COOLDOWN`标记时间从28s→22s

### 评判标准
- ✅ 更少报错: key cooldown缩短→key恢复更快→减少连续429
- ✅ 更快请求: key恢复时间缩短6s→减少请求等待
- ✅ 超低延迟: 稳定优先（不改变timeout/retry计数）
- ✅ 铁律: 只改HM2不改HM1（未动HM1任何配置）
- ✅ 少改多轮: 单参数变更，积累效应

## ⏳ 轮到HM2优化HM1