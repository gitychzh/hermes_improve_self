1|# R266: HM1→HM2 — KEY_COOLDOWN_S 30→34 (+4s)
2|
3|**回合类型**: 优化  
4|**角色**: HM1 (opc_uname) 优化 HM2  
5|**变更**: `KEY_COOLDOWN_S` 30→34 (+4s, 向R258收敛)  
6|**时间戳**: 2026-06-29 02:56 UTC+8  
7|**原则**: 更少报错, 更快请求, 超低延迟, 稳定优先  
8|**铁律**: 只改HM2不改HM1
9|
10|---
11|
12|## 📊 数据收集
13|
14|### 30分钟窗口 (02:26 - 02:56 UTC+8)
15|
16|| 指标 | 值 |
17||------|-----|
18|| 总请求数 | 1138 |
19|| 成功数 (200) | 1051 |
20|| 错误数 | 87 |
21|| 成功率 | **92.5%** |
22|| P50延迟 | 22.7s |
23|| P95延迟 | 116.8s |
24|| 平均延迟 | 32.9s |
25|
26|### 错误分布 (hm_requests)
27|```
28|all_tiers_exhausted:     86  (98.9%)
29|NVStream_IncompleteRead:   1  (1.1%)
30|```
31|
32|### Tier分布
33|```
34|deepseek_hm_nv: 881 req, 22.5s avg, 1 fallback from deepseek→deepseek
35|glm5.1_hm_nv:   171 req, 44.8s avg, 4 fallbacks
36|| (glm5.1→deepseek):     86 req, 116.1s avg ← 所有ATE来自此
37|```
38|
39|### 10分钟爆发窗口 (02:46 - 02:56)
40|```
41|总请求: 1087, 成功: 1001 (92.1%)
42|错误: 86 (100% ATE)
43|```
44|→ 错误集中在glm5.1→deepseek fallback路径
45|
46|### Per-Key 429 (hm_tier_attempts, 30min)
47|```
48|k0: 4, k1: 6, k2: 3, k3: 3, k4: 4
49|总计: 20×429 (key-level, 不是请求级失败)
50|```
51|
52|### Tier层错误 (hm_tier_attempts, 30min)
53|```
54|deepseek_hm_nv:
55|  SSLEOFError: 47
56|  NVCFPexecTimeout: 9
57|  empty_200: 6
58|
59|glm5.1_hm_nv:
60|  500_nv_error: 22
61|  429_nv_rate_limit: 20
62|  SSLEOFError: 15
63|  empty_200: 10
64|  NVCFPexecConnectionResetError: 2
65|```
66|
67|### Error Detail JSONL (host log) — 所有失败请求
68|**关键发现**: 所有条目显示 `all_429: false` — 非函数级429饱和, 是**混合故障模式**
69|
70|典型故障链:
71|```
72|1. empty_200 → 立即消耗~1s + MIN_OUTBOUND(9s)等待
73|2. NVCFPexecTimeout(42s) → 大规模超时
74|3. NVCFPexecTimeout(10s) → 第二波超时  
75|4. NVCFPexecTimeout(10s) → 第三波超时
76|5. 429_nv_rate_limit/500_nv_error → 收尾
77|```
78|总耗时: 119-127s, 预算剩余: 0.3-1.6s (< 10s minimum)
79|
80|### Docker Logs — Tier Budget Break
81|```
82|[02:43:27.6] [HM-TIER-BUDGET] tier=glm5.1_hm_nv budget 128.0s remaining 0.3s < 10s minimum, breaking
83|[02:45:38.3] [HM-TIER-BUDGET] tier=glm5.1_hm_nv budget 128.0s remaining 1.6s < 10s minimum, breaking
84|```
85|
86|### 当前HM2运行配置
87|```
88|KEY_COOLDOWN_S=30          ← 极低 (目标38-45)
89|TIER_COOLDOWN_S=22          ← 死参数 (config.py不读取)
90|UPSTREAM_TIMEOUT=75
91|MIN_OUTBOUND_INTERVAL_S=12.0
92|TIER_TIMEOUT_BUDGET_S=128
93|HM_CONNECT_RESERVE_S=24     ← 已收敛 (=HM1)
94|PROXY_TIMEOUT=300
95|```
96|
97|### Mihomo状态
98|```
99|✅ pgrep -a mihomo → 2008535 /home/opc2_uname/.local/bin/mihomo
100|```
101|
102|---
103|
104|## 🔍 分析
105|
106|### 1. 混合故障模式确认 (`all_429: false`)
107|所有error_detail JSONL条目显示 `all_429: false` — 这不是函数级NV API 429饱和。故障是混合服务器端错误:
108|- **NVCFPexecTimeout** (42s): 单key超时占主导
109|- **empty_200**: Content-Length:0 (流式完成但空体)
110|- **500_nv_error**: 内部服务器错误
111|- **SSLEOFError**: TLS协议EOF
112|
113|`all_429: false` + 20×key-level 429 = 混合故障, 不是纯429饱和。**R264模式**: 不能向GLOBAL_COOLDOWN=45收敛, 应保持KEY_COOLDOWN在R258均衡值38附近。
114|
115|### 2. KEY_COOLDOWN_S=30 过于激进
116|KEY_COOLDOWN_S=30意味着每个key在429后仅冷却30s就重新可用。对比:
117|- HM1 KEY_COOLDOWN_S=34 (仍有7s gap到GLOBAL=45)
118|- 收敛目标: 38-45
119|- 当前30s → gap到GLOBAL=15s, 到R258=38s有8s gap
120|
121|**30s的冷却窗口不足**: 当NV API函数级429发生后, GLOBAL_COOLDOWN=45s在代码层lock所有keys。KEY_COOLDOWN_S=30s意味着key在30s后解除但全局锁仍在(还有15s), 导致更多wasted retries。
122|
123|### 3. TIER_COOLDOWN_S=22 是死参数
124|**R264验证**: `grep -n "TIER_COOLDOWN_S" /opt/cc-infra/proxy/hm-proxy/gateway/config.py` 返回空 — 确认config.py不读取此参数。compose文件中的TIER_COOLDOWN_S=22对运行无影响。
125|
126|### 4. 为什么KEY_COOLDOWN_S而不是其他参数
127|
128|| 参数 | 为什么不改 |
129||------|-----------|
130|| **TIER_COOLDOWN_S** | 死参数, config.py不读取, 改了无效果 |
131|| **UPSTREAM_TIMEOUT** | 75已高于HM1的63, 增加只会让超时key等更久 |
132|| **MIN_OUTBOUND_INTERVAL_S** | 12.0合理, 5×12=60s > GLOBAL=45s, 已有15s buffer |
133|| **TIER_TIMEOUT_BUDGET_S** | 128已足够, 剩余0.3-1.6s说明预算在消耗但非瓶颈 |
134|| **HM_CONNECT_RESERVE_S** | 24=24已收敛完成, 无需调整 |
135|
136|**选择KEY_COOLDOWN_S的原因**:
137|1. 30→34 = +4s, 向R258收敛值38靠近
138|2. 混合故障模式下(`all_429: false`), 增加KEY_COOLDOWN减少key过早重入429风暴
139|3. 单一参数变更, 最小风险, 可观测
140|4. +4s增量 ≤ 4单位规则, 保守步进
141|
142|---
143|
144|## 🎯 执行
145|
146|### 变更: KEY_COOLDOWN_S 30→34 (+4s)
147|
148|```bash
149|# 1. 修改compose文件
150|ssh HM2 'sed -i "s|KEY_COOLDOWN_S: \"30\"|KEY_COOLDOWN_S: \"34\"|" /opt/cc-infra/docker-compose.yml'
151|
152|# 2. 验证文件修改
153|grep -n KEY_COOLDOWN_S /opt/cc-infra/docker-compose.yml
154|# → 473: KEY_COOLDOWN_S: "34"
155|
156|# 3. 重建容器 (部署新配置)
157|cd /opt/cc-infra && docker compose up -d --force-recreate --no-deps hm40006
158|# → Container hm40006 Recreated + Started
159|
160|# 4. 验证运行环境
161|sleep 3 && docker exec hm40006 env | grep KEY_COOLDOWN_S
162|# → KEY_COOLDOWN_S=34 ✅
163|```
164|
165|### 验证结果
166|
167|| 检查项 | 结果 |
168||--------|------|
169|| `docker exec env \| grep KEY_COOLDOWN_S` | **34** ✅ |
170|| `docker ps --filter name=hm40006` | Up (healthy) ✅ |
171|| `curl /health` | 200, passthrough ✅ |
172|| `pgrep -a mihomo` | running ✅ |
173|
174|---
175|
176|## 📈 预期效果
177|
178|| 指标 | 变更前 | 变更后 | 方向 |
179||------|--------|--------|------|
180|| KEY_COOLDOWN_S | 30s | **34s** | +4s ↑ |
181|| Key再入429间隔 | 30s后 | 34s后 | +4s保护 |
182|| 减少wasted retries | - | 预期减少 | 混合故障模式下 |
183|| 成功率目标 | 92.5% | →95%+ | 保守预期 |
184|
185|### 风险控制
186|- **UPSTREAM_TIMEOUT=75**: 无影响 (不改变)
187|- **TIER_TIMEOUT_BUDGET=128**: 无影响 (不改变)
188|- **Mihomo**: 未触碰 — NV链路完好
189|- **单参数变更**: 可回滚 (30→34, 如需要回退至30)
190|
191|---
192|
193|## 🔄 历史参考
194|
195|R258均衡值: KEY_COOLDOWN_S=38 (HM2当前30→34向38收敛, gap=4s)  
196|R264混合故障模式: `all_429: false` → 不向GLOBAL_COOLDOWN=45收敛  
197|HM1 KEY_COOLDOWN_S=34 (HM2正在追平HM1)
198|
199|---
200|
201|## 回合编号
202|
203|由于检测到脚本触发, 本回合基于最近的Git提交历史确定:
204|
205|```bash
206|# 检查最近rounds文件确定回合号
207|ls rounds/R*.md | sort -V | tail -1
208|# → 如有R252/R253等, 本回合为 R{N}
209|```
210|
211|**注**: 回合编号最终由git push后的实际序列确定。如无冲突, 本回合标记为 R266。
212|
213|## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记