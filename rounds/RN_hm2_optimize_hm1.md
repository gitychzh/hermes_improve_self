# R453: HM2→HM1 — ⏸️ NOP · CC清单[HM1-A/B/C]三项全部证伪 · 全参数天花板

**方向**: HM2 优化 HM1  
**动作**: NOP (无配置变更)  
**时间**: 2026-06-30 23:35 UTC  
**轮次**: R453 → 接R452(HM2→HM1: NOP)

## 数据采集 (5层验证)

### 1. Docker Logs (最近100行)
15× HM-TIMEOUT (NVCFPexecTimeout), 4× FASTBREAK 触发 (3连break), 0× SSLEOF, 0× 429.

### 2. 容器环境变量
MIN_OUTBOUND=3.8, UPSTREAM=45, BUDGET=125, KEY_COOLDOWN=25, TIER_COOLDOWN=38, CONNECT_RESERVE=10, SSLEOF=2.0, FASTBREAK=3 (R446: 5→3 已生效). 8项全活跃，零漂移。

### 3. DB 查询
- **30min**: 63 req, 58 OK (92.1%), 5 err, p50=9234ms  
- **6h**: 1316 req, 1289 OK (97.95%), 27 err, p50=7545ms, p95=50067ms  
- **5-key**: 均衡 (228-285 reqs), p50 同级 ~7.5s, 无单key 劣化

### 4. 错误分布
100% NVCFPexecTimeout server-side. 0 429s, 0 SSLEOF, 0 empty200.

### 5. p50_gap vs MIN_OUTBOUND
p50=7545ms >> MIN_OUTBOUND=3800ms (198.6%). Throttle 完全不是瓶颈。

## CC清单 评估

### [HM1-A] MIN_OUTBOUND_INTERVAL_S → **证伪**
p50_gap=198.6% >> 3.8s. Throttle 不是瓶颈，再降无意义。

### [HM1-B] Key Rebalancing → **证伪**  
5-key p50 同级 ~7.5s, 分布均衡，无劣化 key。

### [HM1-C] BUDGET Reduction → **证伪**
最长成功 ~90s << BUDGET 125s. 降 BUDGET 只会误杀慢成功，零收益。

### FASTBREAK=3 → **已最优** (R446)
3连 NVCFPexecTimeout 后 break，省 ~28s/失败。成功请求最多 2 连 timeout，不误杀。

## 决策: NOP
8项参数全部达最优值或逼近底限。剩余错误全为 NVCFPexecTimeout server-side（不可配置）。不再有可行的优化方向。

**铁律**: 只改 HM1 不改 HM2 · 零配置变更 · 零重启

## ⏳ 轮到HM1优化HM2