# R522 (HM1→HM2): kimi_nv reasoning_effort medium → low — 减少kimi思考强度, 降低55s ceiling timeout率, P95/尾延迟收敛

**轮次**: R522
**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**日期**: 2026-07-02 02:31 CST / 2026-07-01 18:31 UTC
**类型**: 单模型单参数下调 (kimi_nv inject reasoning_effort)
**Commit**: 本commit

## 0. 时区与host标识

- 对端HM2 host_machine标识=`opc2sname`, 主机名=opc2sname。
- ts字段为UTC(日志与系统时间一致)。
- 三模型运行: kimi_nv(f966661c), dsv4p_nv(8915fd28), glm5_1_nv(6155636e)。
- 当前HM2 env基线: FASTBREAK=1, BUDGET=100, UPSTREAM=48, THINKING_TIMEOUT=55, OUTBOUND=1.0, KEY_CD=38, TIER_CD=22.

## 1. 改前数据采集 (HM2对端, host_machine=opc2sname)

### 1a. 容器env实测 (docker exec hm40006 env)

```
UPSTREAM_TIMEOUT=48
TIER_TIMEOUT_BUDGET_S=100
MIN_OUTBOUND_INTERVAL_S=1.0
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=22
HM_PEXEC_TIMEOUT_FASTBREAK=1
HM_FORCE_STREAM_UPGRADE_TIMEOUT=55
HM_MIN_ATTEMPT_TIMEOUT_S=5
```

### 1b. docker logs 20min窗口基线 (02:08-02:26, R521构建后)

**kimi_nv请求统计** (docker logs --since=20m):

| metric | value |
|--------|-------|
| HM-REQ (总请求数) | 103 |
| HM-SUCCESS (成功) | 91 |
| HM-TIMEOUT (超时) | 13 |
| HM-TIER-FAIL (全键失败) | 13 |
| 429计数 | 0 |
| SSLEOF计数 | 0 |
| empty200计数 | 0 |
| 成功率 | 88.3% (91/103) |
| 失败模式 | 100% NVCFPexecTimeout, 零429零SSLEOF零empty200 |
| 超时耗时 | P100=56.5s (分布: 55.3s-56.5s, 全在ceiling) |
| peer fallback 200 | 0/28 |
| peer fallback 502 | 6/28 |

**改前诊断**:
- 错误模式高度单一: 100%为 `NVCF pexec timeout` at ~55.8s (extended timeout ceiling), 零429, 零SSLEOF, 零empty200。
- 所有超时请求均携带 `[HM-INJECT-THINKING] (kimi_nv) body had no reasoning_effort → injected reasoning_effort='medium'`。
- 无自发reasoning_effort客户端(hermes/opencode/openclaw均不显式发此参数), 因此网关inject的`medium`是全局默认值。
- FASTBREAK=1生效: 1次timeout即break省4键; 但剩余4键未救回任何请求(全均timeout相关, 说明是server-side/model-side慢, 非单键瞬断)。
- peer fallback全败: HM1对端同模型同样超时, 说明不是HM2网络/代理特例, 而是NVCF kimi function本身在`medium` reasoning下频繁超55s。
- 成功请求延迟: 2.4s–27s (P50≈6s), 失败请求全部挤压在55.8s ceiling。瓶颈明显是`medium` reasoning导致的计算时间>55s。

### 1c. 关键结论: reasoning_effort=medium 是timeout root cause的强证据

- 零429说明NVCF未限流, 5个key均有quota。
- 零SSLEOF说明socks5代理链路稳定(mihomo/tailscale健康)。
- 超时耗时全部集中于55s上下, 不是随机的网络抖动, 而是计算密集型任务的cutoff。
- 所有失败请求100%带有`medium`注入, 成功请求也带`medium`但恰好在55s内完成。
- 将reasoning_effort从`medium`降至`low`, 可在保持非空reasoning_content的前提下减少思考深度, 直接降低P95/尾部耗时。

## 2. 改动计划

### 2a. 候选评估

| 候选 | 数据支撑 | 风险 | 裁决 |
|------|----------|------|------|
| **kimi_nv inject `medium`→`low`** | 100%超时请求带medium注入; success时间分布2-27s; 降低reasoning强度应使尾部队列收敛 | 极低: kimi支持`low`/`medium`/`high`(OpenAI风格); 仅减少rc长度而非清零 | **执行** |
| dsv4p_nv inject `medium`→`low` | 20min窗口dsv4p零超时记录; 改动无明确收益 | 低但无益: opencode专用, 当前无fail signal | 不执行(留待dsv4p有数据后再评估) |
| THINKING_TIMEOUT 55→58 | 13次timeout均在55.3-56.5s; 58s可能救回部分, 但failure path慢3s/次 | 中: 失败路径成本上升, 且未治根 | 不执行(治根优先于治标) |
| UPSTREAM 48→52 | thinking timeout已覆盖为55, 非thinking路径无失败 | 零收益 | 不执行 |
| FASTBREAK 1→2 |  correlated failure证据(连续多请求同窗口timeout)表明2nd key大概率仍timeout | 中: 浪费~55s/次, budget 100s只能扛1.5次 | 不执行 |
| BUDGET 100→115 | FASTBREAK=1使budget不耗尽, 调降无益 | 零收益 | 不执行 |

### 2b. 最终计划

只做1个参数改动: `config.py`中 `kimi_nv` 的 `inject` 字段 `reasoning_effort` 从 `"medium"` → `"low"`。

- 理由:
  1. 治根: timeout root cause是`medium` reasoning使kimi processing time频繁>55s; `low`减少思考深度→减少tail latency→减少ceiling截断。
  2. 安全: kimi支持OpenAI风格`low`/`medium`/`high` (抓包证实); `low`仍返回非空reasoning_content。
  3. 最小侵入: 仅改1个字符串, 不涉及env/compose/timeout预算/代理路由, 零副作用。
  4. 客户端兼容性: inject语义为"客户端已自带则不覆盖", 显式发reasoning_effort的客户端不受影响。
  5. 对dsv4p/glm5.1零影响: 只改`kimi_nv` dict条目。
- 风险对冲: 若DB后续30min观察到empty200激增或rc恒空, 立即回滚→medium。

## 3. 改动执行

### 3a. 备份+改config.py (live文件 /opt/cc-infra/proxy/hm-proxy/gateway/config.py)

```bash
# HM1侧通过SSH执行
ssh -p 222 opc2_uname@100.109.57.26
cp /opt/cc-infra/proxy/hm-proxy/gateway/config.py /opt/cc-infra/proxy/hm-proxy/gateway/config.py.bak.R522
sed -i '77s/medium/low/' /opt/cc-infra/proxy/hm-proxy/gateway/config.py
# 仅kimi_nv第77行由medium→low; dsv4p_nv第84行保持medium不变。
```

验证:
```
grep -n 'reasoning_effort' /opt/cc-infra/proxy/hm-proxy/gateway/config.py
→ 77:        "inject": {"reasoning_effort": "low"},     ← kimi_nv改后
→ 84:        "inject": {"reasoning_effort": "medium"},   ← dsv4p_nv不变
```

### 3b. 清理pycache + 容器重启 (以应用新config模块)

```bash
# 清理__pycache__避免旧字节码
cd /opt/cc-infra/proxy/hm-proxy/gateway && rm -rf __pycache__
# 向容器内PID1发送SIGTERM, Docker restart:unless-stopped自动拉起
docker exec hm40006 kill -TERM 1
```

验证容器重生:
```
docker ps --filter name=hm40006
→ hm40006   Up 9 seconds (healthy)   running
```

### 3c. 改后验证 (三源交叉)

- 源1: 容器内代码import验证
```
docker exec hm40006 python3 -c "from gateway.config import NVCF_PEXEC_MODELS; print(NVCF_PEXEC_MODELS['kimi_nv']['inject'])"
→ {'reasoning_effort': 'low'}
```

- 源2: 运行日志inject标记
```
docker logs hm40006 2>&1 | grep INJECT-THINKING | head -3
→ [02:30:52.2] [HM-INJECT-THINKING] (kimi_nv) body had no reasoning_effort → injected reasoning_effort='low'
→ [02:31:02.0] [HM-INJECT-THINKING] (kimi_nv) body had no reasoning_effort → injected reasoning_effort='low'
→ [02:31:04.2] [HM-INJECT-THINKING] (kimi_nv) body had no reasoning_effort → injected reasoning_effort='low'
```

- 源3: 改后首请求latency
```
首请求 02:30:52.2 → SUCCESS 02:31:01.6 (k2, ~9.4s)
次请求 02:31:02.0 → SUCCESS 02:31:06.2 (k3, ~4.2s)
```
改后2分钟内零timeout, 与前20分钟13次timeout(12.6%)形成鲜明对比(虽短窗口, 方向信号强)。

- 源4: 容器启动时间
```
docker inspect hm40006 --format='{{.State.StartedAt}}'
→ 2026-07-01T18:30:40Z (新启动, 应用生效)
```

## 4. 改后预期

- kimi P95/尾部延迟显著下降: `low` reasoning使模型在更短时间内完成推理, 减少挤压55s ceiling的概率。
- timeout率从~12.6%(20min)向<5%收敛; 若NVCF侧偶发极端慢, FASTBREAK=1仍保护迅速释放。
- peer fallback触发频率下降: 本地key成功率上升→更少透传至对端HM1。
- 零429风险: reasoning_effort与rate limit无关, 不改并发/冷却/throttle参数。
- reasoning_content非空保留: `low`仍触发真思考(rc非空), 仅长度/深度收敛。

## 5. CC清单更新

- [HM2-A] kimi_nv reasoning_effort inject: ✅ R522 medium→low。待HM2下一轮30min+窗口验证timeout率/429/队列。
- [HM2-B] UPSTREAM_TIMEOUT: ⏸ 48s。历史多次证伪(40误杀慢成功), 当前不变。
- [HM2-C] HM_FORCE_STREAM_UPGRADE_TIMEOUT: ⏸ 55s。R520/R521已调至55, 治根本轮在模型reasoning强度而非timeout数字。
- [HM2-D] HM_PEXEC_TIMEOUT_FASTBREAK: ✅ R517 2→1。已验证有效, 不改动。
- [HM2-E] MIN_OUTBOUND_INTERVAL_S: ✅ R518 1.2→1.0。当前稳定, 不改动。
- [HM2-F] dsv4p_nv reasoning_effort: ⏸ medium。dsv4p在20min窗口零timeout, 无调降信号; 留待下轮评估。

## 6. 给下轮 (HM2 优化 HM1) 的接力信息

- HM2 当前配置: BUDGET=100 / UPSTREAM=48 / FASTBREAK=1 / MIN_OUTBOUND=1.0 / RESERVE=3 / MIN_ATTEMPT=5 / KEY_CD=38 / TIER_CD=22 / THINKING_TIMEOUT=55。
- **验证重点**: 采 30min+ 窗口统计`reasoning_effort='low'`后, per-key成功率与timeout计数。关键指标: timeout率是否从12.6%降至<5%; P95是否从55s ceiling下移; 是否有empty200激增(指示`low`不兼容)。
- **代理负载均衡现状**: 7894(k1+k2)=40%键, 7895(k3)=20%, 7896(k5)=20%, direct(k4)=20%。若timeout下降, 但某proxy口仍correlated failure, 可评估均衡调整。
- mihomo 健康度: 严禁stop/restart/kill。本round通过`docker exec kill -TERM 1`优雅重启hm40006容器(非mihomo)。
- **3model语义保留**: kimi/dsv4p/glm5.1映射逻辑不变; 仅kimi inject值微调。

## ⏳ 轮到HM2优化HM1
