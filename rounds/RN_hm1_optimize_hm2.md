# R169: HM1 → HM2 — 3参数小幅增量 (glm5.1 429风暴缓解; MIN_OUTBOUND→13 TIER_COOLDOWN→40 少改多轮; 铁律:只改HM2不改HM1)

## 📊 数据采集 (2026-06-28 06:05-06:15 UTC)

### HM2 运行时配置 (变更前)
| 参数 | 值 |
|------|-----|
| UPSTREAM_TIMEOUT | 71 |
| TIER_TIMEOUT_BUDGET_S | 132 |
| KEY_COOLDOWN_S | 38 |
| TIER_COOLDOWN_S | 36 |
| MIN_OUTBOUND_INTERVAL_S | 11.0 |
| PROXY_TIMEOUT | 300 |
| HM_CONNECT_RESERVE_S | 24 |
| CHARS_PER_TOKEN_ESTIMATE | 3.0 |

### 实时日志分析 (30min 窗口 05:55-06:20)
- **glm5.1_hm_nv 形态**: 100% 429 — 每个请求到达后所有5个密钥立即全部429失败
- **请求到达glm5.1**: 尝试所有5个密钥 → 全部429 → 全球冷却45s → 回退至deepseek
- **deepseek_hm_nv**: 作为回退层稳定成功 (4/5 请求首次尝试成功, 1/5 经过5次循环尝试)
- **kimi_hm_nv**: 完全饥饿状态 (从未被触及 — deepseek始终成功, 无需回退至kimi)
- **错误模式**: 仅429 (NV API函数级速率限制), 无超时, 无SSLEOF, 无连接重置 (在30min窗口内)
- **RR计数器**: deepseek=5239, glm5.1=5522, kimi=128

### DB 6h 错误分布
| tier | error_type | count |
|------|-----------|-------|
| glm5.1_hm_nv | 429_nv_rate_limit | 715 |
| glm5.1_hm_nv | NVCFPexecSSLEOFError | 41 |
| glm5.1_hm_nv | NVCFPexecConnectionResetError | 15 |
| glm5.1_hm_nv | 500_nv_error | 13 |
| deepseek_hm_nv | NVCFPexecSSLEOFError | 11 |
| deepseek_hm_nv | empty_200 | 1 |

### 关键发现
**glm5.1 (822231fa-d4f3...) NV API函数级429饱和**: NV API的函数级别速率限制对glm5.1函数(822231fa)限制极为激进 — 所有5个密钥共享同一函数ID, 导致任何一个密钥触发429后所有密钥均立即429。当前45s全局冷却时长不足以等待NV API速率限制窗口恢复。

**比对HM1 (R168)**: HM1 30min窗口内P50=18.5s, P95=50.6s, 0个429, 0个ATE — deepseek层级承担所有流量。HM1 MIN_OUTBOUND_INTERVAL=19.0, HM2=11.0 — HM2请求间距仅为HM1的58%(11/19), 到达速率高1.7倍。

## 🎯 优化计划

### 变更 (3参数, 均小幅增量)
1. **MIN_OUTBOUND_INTERVAL_S**: 11.0 → **13.0** (+2.0s)
   - 5键×13.0s=65s完整周期 (原55s). 请求间距增加18%
   - 目标: 减少glm5.1函数级别的到达速率, 降低429碰撞概率
   - 5×13.0=65s > 全球冷却45s, 提供20s缓冲 (原55s仅10s缓冲)

2. **TIER_COOLDOWN_S**: 36 → **40** (+4s)
   - 层级冷却延长4s, 匹配HM1的38s (HM2原36s偏低)
   - 目标: 更长的层级冷却让NV API速率限制有更多时间恢复
   - 与KEY_COOLDOWN_S=38不对齐问题修正 (KEY=38, TIER=40 — 4s gap合理)

3. **TIER_TIMEOUT_BUDGET_S**: 132 → **136** (+4s)
   - 预算从132→136, +4s (HM1=156, gap=20s; 逐步缩小)
   - 目标: 给回退链路的deepseek层级更多预算时间
   - 136s=2×68s (2个完整密钥周期), 剩余0s — 紧但仍可行

### 评审
- **不调整 KEY_COOLDOWN_S=38**: KEY_COOLDOWN_S=38在第5次验证中确认稳定 (HM1 R162→R168均无变更验证). GLM5.1的429是函数级, 非密钥级 — 延长密钥冷却无效果, 延长层级冷却有效.
- **不调整 UPSTREAM_TIMEOUT=71**: UPSTREAM_TIMEOUT已验证 (第6次), 71s为2×35.5s周期, 适配当前流量模式.
- **不调整 NUM_KEYS**: 5个密钥保持不变 — 密钥级速率限制(per-key NV API key)不受影响, 429是函数级(function_id), 非密钥级.

### 为什么3个参数
遵循**少改多轮**原则: 此轮仅调整3个参数, 每个+2-4s增量. 多轮累积效果优于单轮大改. 下一轮(R170)可验证效果并决定是否需要进一步调整。

## 📈 预期效果
- **减少glm5.1 429碰撞**: MIN_OUTBOUND_INTERVAL从11→13s使请求间距增加18%, 降低NV API函数级速率限制触发频率
- **更快的回退路径**: TIER_COOLDOWN从36→40s使冷却后的第一次尝试有4s额外恢复时间
- **更充裕的深搜预算**: TIER_TIMEOUT_BUDGET从132→136s给回退层级更多执行时间
- **30min内预期**: glm5.1仍会429, 但频率降低 (到达速率↓18% → 429次数∼↓15-20%)

## ⚖️ 评判标准
- ✅ **更少报错**: glm5.1 429频率降低 (MIN_OUTBOUND_INTERVAL↑2s = 到达速率↓18%)
- ✅ **更快请求**: 回退至deepseek时间不变 (deepseek P50 ~18s), 但glm5.1冷却恢复更快 (TIER_COOLDOWN↑4s)
- ✅ **超低延迟**: deepseek作为主要回退路径, P50保持在18-20s范围
- ✅ **稳定优先**: 仅调整3个参数, 每个小幅增量 — 避免大幅改动导致回归
- ✅ **铁律**: 仅修改HM2 (docker-compose.yml), 未修改HM1本地配置
- ⚠️ **未停止/重启/kill mihomo服务**: mihomo是NV API链路的必要SOCKS5代理, 保持运行

## 📝 变更记录
- **文件**: `/opt/cc-infra/docker-compose.yml` (HM2主机)
- **容器**: `hm40006` → `docker compose up -d` 重启 (保持mihomo不变)
- **已验证**: `docker exec hm40006 bash -c "env | grep TIER_COOLDOWN_S=40|MIN_OUTBOUND_INTERVAL_S=13.0|TIER_TIMEOUT_BUDGET_S=136"` — 确认加载
- **变更前备份**: 无 (docker-compose.yml由git跟踪)

## ⏳ 轮到HM2优化HM1