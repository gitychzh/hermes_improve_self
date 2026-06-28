# R266: HM1→HM2 — KEY_COOLDOWN_S 30→34 (+4s)

**回合类型**: 优化  
**角色**: HM1 (opc_uname) 优化 HM2  
**变更**: `KEY_COOLDOWN_S` 30→34 (+4s, 向R258收敛)  
**时间戳**: 2026-06-29 02:56 UTC+8  
**原则**: 更少报错, 更快请求, 超低延迟, 稳定优先  
**铁律**: 只改HM2不改HM1

---

## 📊 数据收集

### 30分钟窗口 (02:26 - 02:56 UTC+8)

| 指标 | 值 |
|------|-----|
| 总请求数 | 1138 |
| 成功数 (200) | 1051 |
| 错误数 | 87 |
| 成功率 | **92.5%** |
| P50延迟 | 22.7s |
| P95延迟 | 116.8s |
| 平均延迟 | 32.9s |

### 错误分布 (hm_requests)
```
all_tiers_exhausted:     86  (98.9%)
NVStream_IncompleteRead:   1  (1.1%)
```

### Tier分布
```
deepseek_hm_nv: 881 req, 22.5s avg, 1 fallback from deepseek→deepseek
glm5.1_hm_nv:   171 req, 44.8s avg, 4 fallbacks
| (glm5.1→deepseek):     86 req, 116.1s avg ← 所有ATE来自此
```

### 10分钟爆发窗口 (02:46 - 02:56)
```
总请求: 1087, 成功: 1001 (92.1%)
错误: 86 (100% ATE)
```
→ 错误集中在glm5.1→deepseek fallback路径

### Per-Key 429 (hm_tier_attempts, 30min)
```
k0: 4, k1: 6, k2: 3, k3: 3, k4: 4
总计: 20×429 (key-level, 不是请求级失败)
```

### Tier层错误 (hm_tier_attempts, 30min)
```
deepseek_hm_nv:
  SSLEOFError: 47
  NVCFPexecTimeout: 9
  empty_200: 6

glm5.1_hm_nv:
  500_nv_error: 22
  429_nv_rate_limit: 20
  SSLEOFError: 15
  empty_200: 10
  NVCFPexecConnectionResetError: 2
```

### Error Detail JSONL (host log) — 所有失败请求
**关键发现**: 所有条目显示 `all_429: false` — 非函数级429饱和, 是**混合故障模式**

典型故障链:
```
1. empty_200 → 立即消耗~1s + MIN_OUTBOUND(9s)等待
2. NVCFPexecTimeout(42s) → 大规模超时
3. NVCFPexecTimeout(10s) → 第二波超时  
4. NVCFPexecTimeout(10s) → 第三波超时
5. 429_nv_rate_limit/500_nv_error → 收尾
```
总耗时: 119-127s, 预算剩余: 0.3-1.6s (< 10s minimum)

### Docker Logs — Tier Budget Break
```
[02:43:27.6] [HM-TIER-BUDGET] tier=glm5.1_hm_nv budget 128.0s remaining 0.3s < 10s minimum, breaking
[02:45:38.3] [HM-TIER-BUDGET] tier=glm5.1_hm_nv budget 128.0s remaining 1.6s < 10s minimum, breaking
```

### 当前HM2运行配置
```
KEY_COOLDOWN_S=30          ← 极低 (目标38-45)
TIER_COOLDOWN_S=22          ← 死参数 (config.py不读取)
UPSTREAM_TIMEOUT=75
MIN_OUTBOUND_INTERVAL_S=12.0
TIER_TIMEOUT_BUDGET_S=128
HM_CONNECT_RESERVE_S=24     ← 已收敛 (=HM1)
PROXY_TIMEOUT=300
```

### Mihomo状态
```
✅ pgrep -a mihomo → 2008535 /home/opc2_uname/.local/bin/mihomo
```

---

## 🔍 分析

### 1. 混合故障模式确认 (`all_429: false`)
所有error_detail JSONL条目显示 `all_429: false` — 这不是函数级NV API 429饱和。故障是混合服务器端错误:
- **NVCFPexecTimeout** (42s): 单key超时占主导
- **empty_200**: Content-Length:0 (流式完成但空体)
- **500_nv_error**: 内部服务器错误
- **SSLEOFError**: TLS协议EOF

`all_429: false` + 20×key-level 429 = 混合故障, 不是纯429饱和。**R264模式**: 不能向GLOBAL_COOLDOWN=45收敛, 应保持KEY_COOLDOWN在R258均衡值38附近。

### 2. KEY_COOLDOWN_S=30 过于激进
KEY_COOLDOWN_S=30意味着每个key在429后仅冷却30s就重新可用。对比:
- HM1 KEY_COOLDOWN_S=34 (仍有7s gap到GLOBAL=45)
- 收敛目标: 38-45
- 当前30s → gap到GLOBAL=15s, 到R258=38s有8s gap

**30s的冷却窗口不足**: 当NV API函数级429发生后, GLOBAL_COOLDOWN=45s在代码层lock所有keys。KEY_COOLDOWN_S=30s意味着key在30s后解除但全局锁仍在(还有15s), 导致更多wasted retries。

### 3. TIER_COOLDOWN_S=22 是死参数
**R264验证**: `grep -n "TIER_COOLDOWN_S" /opt/cc-infra/proxy/hm-proxy/gateway/config.py` 返回空 — 确认config.py不读取此参数。compose文件中的TIER_COOLDOWN_S=22对运行无影响。

### 4. 为什么KEY_COOLDOWN_S而不是其他参数

| 参数 | 为什么不改 |
|------|-----------|
| **TIER_COOLDOWN_S** | 死参数, config.py不读取, 改了无效果 |
| **UPSTREAM_TIMEOUT** | 75已高于HM1的63, 增加只会让超时key等更久 |
| **MIN_OUTBOUND_INTERVAL_S** | 12.0合理, 5×12=60s > GLOBAL=45s, 已有15s buffer |
| **TIER_TIMEOUT_BUDGET_S** | 128已足够, 剩余0.3-1.6s说明预算在消耗但非瓶颈 |
| **HM_CONNECT_RESERVE_S** | 24=24已收敛完成, 无需调整 |

**选择KEY_COOLDOWN_S的原因**:
1. 30→34 = +4s, 向R258收敛值38靠近
2. 混合故障模式下(`all_429: false`), 增加KEY_COOLDOWN减少key过早重入429风暴
3. 单一参数变更, 最小风险, 可观测
4. +4s增量 ≤ 4单位规则, 保守步进

---

## 🎯 执行

### 变更: KEY_COOLDOWN_S 30→34 (+4s)

```bash
# 1. 修改compose文件
ssh HM2 'sed -i "s|KEY_COOLDOWN_S: \"30\"|KEY_COOLDOWN_S: \"34\"|" /opt/cc-infra/docker-compose.yml'

# 2. 验证文件修改
grep -n KEY_COOLDOWN_S /opt/cc-infra/docker-compose.yml
# → 473: KEY_COOLDOWN_S: "34"

# 3. 重建容器 (部署新配置)
cd /opt/cc-infra && docker compose up -d --force-recreate --no-deps hm40006
# → Container hm40006 Recreated + Started

# 4. 验证运行环境
sleep 3 && docker exec hm40006 env | grep KEY_COOLDOWN_S
# → KEY_COOLDOWN_S=34 ✅
```

### 验证结果

| 检查项 | 结果 |
|--------|------|
| `docker exec env \| grep KEY_COOLDOWN_S` | **34** ✅ |
| `docker ps --filter name=hm40006` | Up (healthy) ✅ |
| `curl /health` | 200, passthrough ✅ |
| `pgrep -a mihomo` | running ✅ |

---

## 📈 预期效果

| 指标 | 变更前 | 变更后 | 方向 |
|------|--------|--------|------|
| KEY_COOLDOWN_S | 30s | **34s** | +4s ↑ |
| Key再入429间隔 | 30s后 | 34s后 | +4s保护 |
| 减少wasted retries | - | 预期减少 | 混合故障模式下 |
| 成功率目标 | 92.5% | →95%+ | 保守预期 |

### 风险控制
- **UPSTREAM_TIMEOUT=75**: 无影响 (不改变)
- **TIER_TIMEOUT_BUDGET=128**: 无影响 (不改变)
- **Mihomo**: 未触碰 — NV链路完好
- **单参数变更**: 可回滚 (30→34, 如需要回退至30)

---

## 🔄 历史参考

R258均衡值: KEY_COOLDOWN_S=38 (HM2当前30→34向38收敛, gap=4s)  
R264混合故障模式: `all_429: false` → 不向GLOBAL_COOLDOWN=45收敛  
HM1 KEY_COOLDOWN_S=34 (HM2正在追平HM1)

---

## 回合编号

由于检测到脚本触发, 本回合基于最近的Git提交历史确定:

```bash
# 检查最近rounds文件确定回合号
ls rounds/R*.md | sort -V | tail -1
# → 如有R252/R253等, 本回合为 R{N}
```

**注**: 回合编号最终由git push后的实际序列确定。如无冲突, 本回合标记为 R266。

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记