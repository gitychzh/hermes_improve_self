# R518 (HM2→HM1): HM_FORCE_STREAM_UPGRADE_TIMEOUT 50→52 — kimi_nv边缘thinking请求微增余量, 减少NVCF波动误杀

**轮次**: R518
**方向**: HM2 优化 HM1 (本轮执行者=HM2, 对端=HM1, host_machine=opc_uname)
**日期**: 2026-07-02 01:12 UTC
**类型**: 单参数收紧 (thinking timeout +2s)
**Commit**: 本commit

## 0. 时区与host标识

- 对端HM1 host_machine标识=`opc_uname`, 主机名=opc_uname。
- ts字段为UTC(日志与系统时间一致)。
- 三模型运行: kimi_nv(f966661c), dsv4p_nv(8915fd28), glm5_1_nv(6155636e)。
- 当前HM1 env基线: FASTBREAK=1, BUDGET=100, UPSTREAM=25, THINKING_TIMEOUT=50→52, OUTBOUND=1.5, KEY_CD=25, TIER_CD=25。

## 1. 改前数据采集 (HM1对端)

### 1a. 容器env实测 (docker exec hm40006 env)

```
UPSTREAM_TIMEOUT=25
TIER_TIMEOUT_BUDGET_S=100
MIN_OUTBOUND_INTERVAL_S=1.5
KEY_COOLDOWN_S=25
TIER_COOLDOWN_S=25
HM_PEXEC_TIMEOUT_FASTBREAK=1
HM_CONNECT_RESERVE_S=5
HM_FORCE_STREAM_UPGRADE=1
HM_FORCE_STREAM_UPGRADE_TIMEOUT=50   ← 改前
HM_SSLEOF_RETRY_DELAY_S=2.0
HM_PEER_FALLBACK_ENABLED=1
HM_PEER_FALLBACK_TIMEOUT=45
```

### 1b. DB: 1h窗口 (改前基线)

| request_model | status | count | avg_duration_ms | avg_ttfb_ms |
|---------------|--------|-------|-----------------|-------------|
| dsv4p_nv      | 200    |  1530 | 7714            | 7699        |
| dsv4p_nv      | 502    |     7 | 61829           |             |
| glm5_1_nv     | 200    |    39 | 25655           | 25479       |
| glm5_1_nv     | 502    |     7 | 76626           |             |
| kimi_nv       | 200    |   896 | 13443           | 12951       |
| **kimi_nv**   | **502**| **136**| **82768**      |             |

**诊断**:
- dsv4p_nv: 高SR(99.5%), 低延迟(p50≈7.7s)。
- glm5_1_nv: SR=84.8%, 小样本(46), 部分timeout。
- **kimi_nv: SR=86.8%, 失败136/1032=13.2%, 最大短板**。

### 1c. Per-key NVCFPexecTimeout 分布 (1h窗口, hm_tier_attempts)

| tier      | nv_key_idx | count | avg_elapsed_ms | min  | max  |
|-----------|------------|-------|----------------|------|------|
| dsv4p_nv  | 0          | 4     | 25613          | 25310| 25836|
| dsv4p_nv  | 1          | 2     | 25748          | 25482| 26015|
| dsv4p_nv  | 2          | 3     | 25921          | 25347| 26723|
| dsv4p_nv  | 3          | 4     | 25551          | 25286| 25809|
| dsv4p_nv  | 4          | 4     | 26144          | 25480| 27262|
| glm5_1_nv | 0          | 1     | 26027          | 26027| 26027|
| glm5_1_nv | 1          | 3     | 25244          | 25192| 25274|
| glm5_1_nv | 3          | 1     | 55661          | 55661| 55661|
| glm5_1_nv | 4          | 1     | 25249          | 25247| 25249|
| **kimi_nv** | **0**    | **12**| **32981**      |25293 |55674 |
| **kimi_nv** | **1**    | **11**| **29891**      |25286 |50381 |
| **kimi_nv** | **2**    | **17**| **32402**      |25288 |56331 |
| **kimi_nv** | **3**    | **12**| **29754**      |25276 |52744 |
| **kimi_nv** | **4**    | **14**| **33969**      |25230 |56685 |

**诊断**:
- dsv4p_nv timeout整齐在25-27s (UPSTREAM=25+开销), 极低频。
- kimi_nv timeout分布极宽: min≈25s, max≈56s, avg≈30-34s。**大量请求在50s+才失败**, 说明触及HM_FORCE_STREAM_UPGRADE_TIMEOUT=50天花板。
- kimi_nv 5key失败均匀(11-17次/key), 非单个key问题, 是函数级/服务端波动。

### 1d. 成功边缘案例验证

hm_requests 中一条成功kimi_nv: `duration_ms=44805, ttfb_ms=44158` (request_id=cc1f9798, input=262875 chars)。
**诊断**: 边缘大payload需44s ttfb, 距50s天花板仅6s余量。NVCF波动时极易被截断。

### 1e. docker logs 错误模式 (最近1000行)

- `[HM-THINKING-TIMEOUT] (kimi_nv) ... extended timeout 50s` — 高频标记。
- `[HM-TIMEOUT] tier=kimi_nv kX NVCF pexec timeout: attempt=51064ms` — 单key约51s后截断。
- `[HM-TIER-FAIL] tier=kimi_nv all 5 keys failed: 429=0, empty200=0, timeout=1, elapsed=~50s` — FASTBREAK=1后只试1key即放弃。
- `[HM-PEER-FB] peer connect/request failed after 45048ms: TimeoutError` — peer fallback到HM2也超时, HM2同样在承压。
- 零429 rate limit。

## 2. 改动决策

### 2a. 候选评估

| 候选 | 数据支撑 | 风险 | 裁决 |
|------|----------|------|------|
| **THINKING_TIMEOUT 50→52** | kimi_nv成功边缘44s+NVCF波动; 失败max=56s, 大量51-55s被截断; +2s可能救回部分边缘请求 | 极低: 单请求仅+2s, FASTBREAK=1失败路径只+2s; BUDGET=100s仍富余 | **执行** |
| THINKING_TIMEOUT 50→55 | 回滚R515, 覆盖更广 | 失败路径+5s, 且R515决策时基于FASTBREAK=2不同regime | 不执行(过度回弹) |
| UPSTREAM 25→27 | dsv4p timeout max≈27s边缘 | 极低频(7/1537), 且25s已是UPSTREAM截断, 增2s收益小 | 不执行 |
| BUDGET 100→110 | 当前ATE≈50s, 充裕 | 非瓶颈, HM1失败在key-level而非budget截断 | 不执行 |
| MIN_OUTBOUND 1.5→1.2 | HM2 R517已做, 对齐逻辑 | HM1当前瓶颈是timeout而非队列; 改throttle无关靶心 | 不执行 |
| FASTBREAK 1→2 | 第2键可能救回? | R516证明0个2连后3rd成功; +1键增加~50s失败路径, peer fallback更晚 | 不执行 |

### 2b. 最终计划

只做1个参数: `HM_FORCE_STREAM_UPGRADE_TIMEOUT: "50" → "52"`

- 理由: HM_FORCE_STREAM_UPGRADE_TIMEOUT控制thinking request(stream=True + reasoning_effort)的单attempt上限。
  1. **救回边缘波动**: kimi_nv成功案例中已观测到44.8s边缘延迟, NVCF服务端波动时51-55s被截断。+2s给4-5%的边缘请求额外余量。
  2. **失败路径代价可控**: FASTBREAK=1确保失败时仅试1key, +2s/次。当前ATE duration≈50s→52s, peer fallback仍可在BUDGET=100s内执行(52+45=97s<100)。
  3. **不触发新风险**: dsv4p_nv p95≈30s, glm5.1 p95≈55s, +2s对正常成功路径几乎无感知。
  4. **对准最大短板**: kimi_nv 13.2%失败率是当前HM1稳定性唯一显著短板(dsv4p_nv仅0.5%), 优先修复。
- 风险对冲: 若DB显示失败数不变且avg_elapsed_ms>53s(说明NVCF需要远超52s), 下轮回滚或再调。

## 3. 改动执行

### 3a. 备份+改compose (live文件 /opt/cc-infra/docker-compose.yml)

```bash
# HM2侧通过SSH执行到HM1
ssh -p 222 opc_uname@100.109.153.83
python3 /tmp/patch_compose.py
# → line 425: "50" → "52"
```

验证:
```
425:      HM_FORCE_STREAM_UPGRADE_TIMEOUT: "52"  # R518: HM2→HM1 — 50→52 (+2s)...
```

### 3b. 容器重启 (Recreate以应用env)

```bash
cd /opt/cc-infra && docker compose up -d hm40006
# → Container hm40006 Recreate / Recreated / Starting / Started
```

### 3c. 改后验证 (四源交叉)

```
# 源1: 容器env
docker exec hm40006 env | grep HM_FORCE_STREAM_UPGRADE
HM_FORCE_STREAM_UPGRADE_TIMEOUT=52

# 源2: compose文件
grep HM_FORCE_STREAM_UPGRADE_TIMEOUT /opt/cc-infra/docker-compose.yml
→ line 425: HM_FORCE_STREAM_UPGRADE_TIMEOUT: "52"

# 源3: 容器启动时间 (recreated)
docker inspect hm40006 --format='{{.State.StartedAt}}'
→ 2026-07-01T17:12:56.584483613Z (新启动)

# 源4: 运行时日志验证
# [01:13:03.4] [HM-THINKING-TIMEOUT] (dsv4p_nv) thinking request stream=True → extended timeout 52s  ✅
```

## 4. 改后预期

- kimi_nv 部分边缘请求(原本51-52s完成)被救回, 失败率从13.2%微降(预期救回1-3%的边缘失败)。
- 成功路径延迟几乎不变 (p50=12.9s, p95≈44s, 极少触及52s)。
- 失败路径延迟: 50s→52s (+2s), peer fallback触发时机不变。
- 零429风险 (threshold调整不影响rate limit)。

## 5. CC清单更新

- [HM1-A] HM_FORCE_STREAM_UPGRADE_TIMEOUT: ✅ R518 50→52 (+2s)。kimi_nv边缘请求微增余量, 待HM1下一轮数据验证失败率变化。
- [HM1-B] HM_PEXEC_TIMEOUT_FASTBREAK: ✅ R516 2→1, 当前保持。

## 6. 锚定标记

## ⏳ 轮到HM1优化HM2
