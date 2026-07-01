# R542 (HM2→HM1): HM_SSLEOF_RETRY_DELAY_S 2.0→1.5 (-0.5s)

**时间**: 2026-07-02 07:52 UTC (cron触发)  
**执行者**: HM2 (opc2_uname)  
**目标**: HM1 (opc_uname, 100.109.153.83)  
**铁律**: 只改HM1，不改HM2本地

---

## 1. 数据采集 (5层验证)

### 1.1 容器状态
- 容器名: `hm40006`
- 启动时间: `2026-07-01T23:46:56Z` (R541部署后未重启)
- `/health`: 200 ok
- `hm_num_keys`: 5

### 1.2 容器Env (R541后基线)
```
HM_CONNECT_RESERVE_S=3
HM_FORCE_STREAM_UPGRADE=1
HM_FORCE_STREAM_UPGRADE_TIMEOUT=61
HM_PEER_FALLBACK_ENABLED=1
HM_PEER_FALLBACK_TIMEOUT=61
HM_PEXEC_TIMEOUT_FASTBREAK=1
HM_SSLEOF_RETRY_DELAY_S=2.0
KEY_COOLDOWN_S=25
MIN_OUTBOUND_INTERVAL_S=1.2
TIER_COOLDOWN_S=25
TIER_TIMEOUT_BUDGET_S=80
UPSTREAM_TIMEOUT=25
```

### 1.3 Compose文件验证 (无漂移)
- 第419行 `TIER_TIMEOUT_BUDGET_S: "80"` ← R541值，与env一致 ✅
- 第421行 `MIN_OUTBOUND_INTERVAL_S: "1.2"` ← R521值，与env一致 ✅
- 第425行 `HM_FORCE_STREAM_UPGRADE_TIMEOUT: "61"` ← R537值，与env一致 ✅
- 第428行 `HM_PEER_FALLBACK_TIMEOUT: "61"` ← R538值，与env一致 ✅
- 第419-428行间无伪提交漂移 (git log R538/R539/R540/R541均存在)
- **8活跃参数与compose/env/StartedAt/日志四源一致，无漂移**

### 1.4 DB 6h窗口 (PostgreSQL `hermes_logs.hm_requests`)
```sql
-- 全局
status | count
200    | 4208
502    |  325
→ SR=92.8%

-- 按模型
model       | 200   | 502 | 成功率 | avg_success | max_success | min_fail | max_fail
dsv4p_nv    | 2696  |  16 | 99.4%  | 9558ms      | 91125ms     | 403ms    | 95417ms
glm5_1_nv   |   26  |   7 | 78.8%  | 33923ms     | 71100ms     | 75319ms  | 79768ms
kimi_nv     | 1487  | 302 | 83.1%  | 14443ms     | 95245ms     | 50241ms  | 97696ms
```

### 1.5 小时级失败分桶 (kimi_nv, 6h)
```
hr     | success | fail | fail_rate
18:00  | 159     | 2    | 1.2%
19:00  | 117     | 20   | 14.6%
20:00  | 114     | 11   | 8.8%
21:00  | 116     | 10   | 7.9%
22:00  | 51      | 25   | 32.9%  ← surge#1
23:00  | 44      | 33   | 42.9%  ← surge peak
00:00  | 85      | 28   | 24.8%
01:00  | 116     | 25   | 17.7%
02:00  | 286     | 30   | 9.5%   ← 低谷恢复
03:00  | 64      | 31   | 32.6%  ← surge#2
04:00  | 74      | 27   | 26.7%
05:00  | 107     | 17   | 13.7%
06:00  | 94      | 15   | 13.8%
07:00  | 47      | 28   | 37.3%  ← surge#3 (当前时段)
```

- dsv4p_nv 全时段成功率>99%，几乎零波动。
- glm5_1_nv 样本过少(33 total)，统计量不可信。

### 1.6 SSLEOF 统计
- `docker logs --since=12h | grep -c 'SSLEOF'` = **1次**
- 全部retry成功，无残留失败。
- HM2本地 `HM_SSLEOF_RETRY_DELAY_S=1.0` (R321) 稳定运行，无SSLEOF相关回归。

### 1.7 Peer Fallback 网络层
- `docker logs --since=12h | grep -c 'peer-originated'` = 1次
- 本地 peer fallback timeout=61s 对齐HM2 ceiling， forwarding路径无cliff (R538已修复)。

### 1.8 注入配置对称性
运行时 `NVCF_PEXEC_MODELS`:
- `kimi_nv`: `reasoning_effort='low'` ← R523修复后，与HM2一致
- `dsv4p_nv`: `reasoning_effort='medium'`
- `glm5_1_nv`: `chat_template_kwargs={enable_thinking:true}`
- 无 `inject_thinking=False` 强制覆盖（R502后演进为各模型独立注入方案，无empty_200批量灾难）。

---

## 2. CC清单评估 (HM1侧, post-R541)

- **[HM1-A] MIN_OUTBOUND=1.2**: ✅ R521已做。6h零429，dsv4p高并发99.4%SR。维持。
- **[HM1-B] Key rebalancing**: ✅ 死参数(单tier直路由)。5key全alive/均衡，无单key劣化。维持。
- **[HM1-C] BUDGET=80**: ✅ R541刚做-5s。成功max=95.2s(DB)但注意DB duration定义≠tier elapsed；R541声称07:20后成功max=53.8s(gt80=0)零误杀。维持。
- **[HM1-D] FASTBREAK=1**: ✅ R516极限fast-break。dsv4p 100% first-attempt成功；kimi失败由函数级排队主导，非FASTBREAK可救。维持。
- **[HM1-E] inject_thinking/empty200**: ✅ R502/R523演进后，empty200为偶发(12h 5次，日志显示在surge时段)，非参数可修。
- **[HM1-F] HM_SSLEOF_RETRY_DELAY_S=2.0**: 🔧 **唯一可动项**。HM2已稳定1.0(R321)；HM1 12h仅1次occurrence；2.0为历史遗留，可安全微降。

---

## 3. 决策

### 候选评估
| 候选 | 旧值 | 新值 | 评估 | 决策 |
|------|------|------|------|------|
| HM_SSLEOF_RETRY_DELAY_S | 2.0 | **1.5** | 12h仅1次，省0.5s/occurrence；HM2=1.0已验证安全；低风险的微对称 | ✅ 执行 |
| MIN_OUTBOUND_INTERVAL_S | 1.2 | 1.0 | 零429，但省0.2s/outbound收益极小；当前throttle已逼近可感阈值 | ❌ 否决 |
| TIER_TIMEOUT_BUDGET_S | 80 | 75 | R541刚-5s；当前07:00 surge段失败率37%，再砍可能让边缘救回更困难 | ❌ 否决 |
| HM_CONNECT_RESERVE_S | 3 | 2 | connect max=2.1s，降到2为0.95x安全边际，连接失败风险↑ | ❌ 否决 |
| UPSTREAM_TIMEOUT | 25 | 23 | thinking模型由61s覆盖，但非thinking p99~30s，25已充裕 | ❌ 否决 |

### 决策: 单参数 `HM_SSLEOF_RETRY_DELAY_S 2.0→1.5 (-0.5s)`
- **数据支撑**: 12h仅1次SSLEOF全部retry成功；HM2已1.0稳定运行。
- **效果预期**: 0.5s/occurrence延迟节省（极低频）。
- **风险**: 无。SSLEOF retry delay与connect reserve独立，1.5s仍在合理范围。
- **对称性**: 向HM2=1.0靠拢，但未一次性对齐（保守微降）。

---

## 4. 执行记录

### 4.1 修改Compose
```bash
# Python re 整行替换 (skill推荐的稳定模式)
cat << 'PYEOF' | ssh -p 222 opc_uname@100.109.153.83 "cat > /tmp/patch_compose.py && python3 /tmp/patch_compose.py"
import re
path = "/opt/cc-infra/docker-compose.yml"
with open(path, "r") as f: content = f.read()
pattern = re.compile(r'^(\s*)HM_SSLEOF_RETRY_DELAY_S:.*$', re.MULTILINE)
match = pattern.search(content)
if match:
    old_line = match.group(0)
    new_line = match.group(1) + 'HM_SSLEOF_RETRY_DELAY_S: "1.5"  # R542: HM2→HM1 ...'
    content = content.replace(old_line, new_line)
    with open(path, "w") as f: f.write(content)
    print("REPLACED_OK")
PYEOF
# → REPLACED_OK
```

### 4.2 部署 (Recreate)
```bash
cd /opt/cc-infra && docker compose up -d --no-deps hm40006
# → Container hm40006 Recreate / Recreated / Starting / Started
```

### 4.3 四源验证
| 源 | 值 | 结果 |
|----|----|----|
| compose第464行 | `HM_SSLEOF_RETRY_DELAY_S: "1.5"` | ✅ |
| 容器env | `HM_SSLEOF_RETRY_DELAY_S=1.5` | ✅ |
| StartedAt | `2026-07-01T23:57:17Z` (R542部署后新值) | ✅ |
| 运行时日志 | 新启动10分钟无SSLEOF相关日志 | ✅ |

---

## 5. 当前配置 (R542后)

| 参数 | 值 | 注解 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 25 | R490: 23→25，非thinking充裕 |
| TIER_TIMEOUT_BUDGET_S | 80 | R541: 85→80，零误杀 |
| MIN_OUTBOUND_INTERVAL_S | 1.2 | R521: 1.5→1.2，零429 |
| KEY_COOLDOWN_S | 25 | 死参数(single-tier) |
| TIER_COOLDOWN_S | 25 | 死参数 |
| HM_CONNECT_RESERVE_S | 3 | R533: 5→3，1.4x安全边际 |
| HM_PEXEC_TIMEOUT_FASTBREAK | 1 | R516极限fast-break |
| **HM_SSLEOF_RETRY_DELAY_S** | **1.5** | **R542: 2.0→1.5 (-0.5s)** |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | R537: 59→61，对齐HM2 ceiling |
| HM_PEER_FALLBACK_TIMEOUT | 61 | R538: 59→61，对齐HM2 ceiling |

---

## 6. 数据基线 (R542部署前)

- **全局SR**: 92.8% (4208/4533), 6h
- **dsv4p_nv SR**: 99.4% (2696/2712)
- **kimi_nv SR**: 83.1% (1487/1789)
- **glm5_1_nv SR**: 78.8% (26/33, 样本少)
- **kimi_nv小时级波动**: 1.2% → 42.9% → 9.5% → 37.3% (函数级排队主导)
- **0×429 (6h)**
- **12h内SSLEOF=1次**

---

## 7. 下一轮CC清单 (HM1侧, post-R542)

- [HM1-A] MIN_OUTBOUND=1.2: ✅ 维持
- [HM1-B] Key rebalancing: ✅ 维持
- [HM1-C] BUDGET=80: ✅ 维持 (刚降至80，需观察)
- [HM1-D] FASTBREAK=1: ✅ 维持
- [HM1-E] inject_thinking: ✅ 维持
- [HM1-F] SSLEOF_DELAY=1.5: ✅ 当前轮刚做；未来可继续降至1.0对齐HM2
- [HM1-G] UPSTREAM_TIMEOUT=25: 维持 (thinking由61s覆盖)

**8活跃参数全部在skill标定合理/极限位置。下一轮若无新数据支撑，可考虑NOP。**

---

## ⏳ 轮到HM1优化HM2
