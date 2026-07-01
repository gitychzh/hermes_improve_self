# R517 (HM1→HM2): MIN_OUTBOUND_INTERVAL_S 1.5→1.2 — 错峰微调, 降低并发饱和时的队列尾延迟

**轮次**: R517
**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**日期**: 2026-07-02 00:37 UTC
**类型**: 单参数收紧 (outbound throttle -0.3s)
**Commit**: 本commit

## 0. 时区与host标识

- 对端HM2 host_machine标识=`opc2sname`, 主机名=opc2sname。
- ts字段为UTC(日志与系统时间一致)。
- 三模型运行: kimi_nv(f966661c), dsv4p_nv(8915fd28), glm5_1_nv(6155636e)。
- 当前HM2 env基线: FASTBREAK=2, BUDGET=100, UPSTREAM=48, THINKING_TIMEOUT=50, OUTBOUND=1.5, KEY_CD=38, TIER_CD=22。

## 1. 改前数据采集 (HM2对端, host_machine=opc2sname)

### 1a. 容器env实测 (docker exec hm40006 env)

```
UPSTREAM_TIMEOUT=48
TIER_TIMEOUT_BUDGET_S=100
MIN_OUTBOUND_INTERVAL_S=1.5   ← 改前
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=22
HM_PEXEC_TIMEOUT_FASTBREAK=2
HM_CONNECT_RESERVE_S=3
HM_FORCE_STREAM_UPGRADE=1
HM_FORCE_STREAM_UPGRADE_TIMEOUT=50
HM_SSLEOF_RETRY_DELAY_S=1.0
```

### 1b. DB: 30分钟窗口 (改前基线)

| tier_model | total | ok | sr_pct | avg_ms | p50_ms | p95_ms |
|------------|-------|-----|--------|--------|--------|--------|
| dsv4p_nv   | 138   | 134 | 97.1  | 12340  | 9474   | 28403  |
| glm5_1_nv  | 37    | 37  | 100.0 | 20797  | 16521  | 44657  |
| glm5.1_hm_nv | 429 | 429 | 100.0 | 20232  | 12237  | 76084  |
| kimi_nv    | 408   | 322 | 78.9  | 35765  | 17258  | 97822  |
| (null)     | 46    | 0   | 0.0   | 116219 | 120588 | 123110 |

**诊断**:
- dsv4p/glm5: 高SR(97-100%), 低延迟(p50 9-16s)。
- kimi_nv: SR 78.9%, P95 97.8s(接近BUDGET=100), 失败全因all_tiers_exhausted(timeout=2主导, 零429)。

### 1c. kimi_nv per-key SR与延迟 (30min窗口, nv_key_idx有值)

| nv_key_idx | total | ok | avg_dur | avg_ttfb |
|------------|-------|----|---------|----------|
| 0 (k1, direct)     | 82 | 82 | 18448 | 18315 |
| 1 (k2, proxy7894)  | 76 | 76 | 17537 | 17398 |
| 2 (k3, proxy7895)  | 68 | 68 | 17973 | 17833 |
| 3 (k4, direct)     | 71 | 71 | 18933 | 18797 |
| 4 (k5, proxy7896)  | 62 | 62 | 15747 | 15592 |

**诊断**: 5个key各自100%成功, 零key-level失败。说明**瓶颈在超时阈值而非key 429**。

### 1d. docker logs 错误模式 (最近100行)

- kimi_nv pattern: `1st attempt timeout(~48s) → 2nd key timeout(~48s) → FASTBREAK=2触发 → tier-fail ~97s`。
- 30min内全部ATE: `timeout=2`, `429=0`, `other=0` (含3条SSLEOF已自愈, 不计入ATE)。
- Peer fallback: H1(HM1) inter-availability, 5次peer-fb-OK中4次HM2→HM1(258ms ttfb), 1次HM2 origin HM1拒绝(502@20s)。

### 1e. 关键发现: 队列延迟 + outgoing throttle

- kimi_nv成功请求per-key ttfb中位数: 15-18s (热key p50=12.3s)。
- failure路径: `1st timeout 48s → 2nd timeout 48s → FASTBREAK 2连击 → 97s ATE`。
- MIN_OUTBOUND_INTERVAL=1.5 是HM2当前唯一比HM1保守的参数(HM1=2.0→R516前已收紧)。
- 降MIN_OUTBOUND_INTERVAL可在并发波峰时缩短队列尾等待, **不影响单请求超时**。

## 2. 改动计划

### 2a. 候选评估

| 候选 | 数据支撑 | 风险 | 裁决 |
|------|----------|------|------|
| **MIN_OUTBOUND 1.5→1.2** | 零429历史, key cooldown=38s >> 1.5s; 并发波峰时队列深, 微降throttle可减尾延迟 | 极低: 1.2s仍 > tier cooldown(22s)的1/18; 不会触发NV rate limit | **执行** |
| FASTBREAK 2→1 | kimi_nv R473 60min实测0个2连后3rd成功; 失败路径省45s | HM2当前FASTBREAK=2, 与HM1 R516独立; 但failure path已优化(2连key), 1→0无增益 | 不执行(等HM2自评估) |
| THINKING_TIMEOUT 50→45 | kimi p95 ttfb=43s触及边缘 | R515/516已同逻辑收紧, 本轮不应再压 | 不执行 |
| BUDGET 100→90 | 当前ATE~97-100s, 90s会截断部分ATE但无成功增益 | 可能误杀即将成功的k4(30s rescue pattern) | 不执行 |
| UPSTREAM 48→45 | 成功ttfb中位数15-18s, 48s远超 | 无数据支撑缩短 | 不执行 |

### 2b. 最终计划

只做1个参数: `MIN_OUTBOUND_INTERVAL_S: "1.5" → "1.2"`

- 理由: MIN_OUTBOUND_INTERVAL控制同tier key cycle间的最小发车间隔。
  1. 排队吞吐微增: 并发波峰(如同时5-10个kimi并发)时, key轮转从1.5s/键降至1.2s/键, 首键到末键等待-1.5s(5键×0.3s)。
  2. 队列尾延迟微降: 当kimi thinking饱和(50s)时, 后续请求在outbound queue等待, 缩短throttle可降低队列压强。
  3. 零429风险: HM2 key cooldown=38s, tier cooldown=22s, 均远大于1.2s, 不会重置NV rate limit budget。
  4. 不影响成功路径: 单请求ttfb由NVCF side决定, 与client outbound throttle无关。
- 风险对冲: 若DB出现429>3/30min, 立即回滚→1.5。

## 3. 改动执行

### 3a. 备份+改compose (live文件 /opt/cc-infra/docker-compose.yml)

```bash
# HM1侧通过SSH执行
ssh -p 222 opc2_uname@100.109.57.26
# python脚本精确替换(避免sed引号问题)
```

验证:
```
MIN_OUTBOUND_INTERVAL_S: "1.2"  # R517: HM1→HM2 — 1.5→1.2 (-0.3s)...
```

### 3b. 容器重启 (Recreate以应用env)

```bash
cd /opt/cc-infra && docker compose up -d hm40006
# → Container hm40006 Recreate / Recreated / Starting / Started
```

### 3c. 改后验证 (三源交叉)

```
# 源1: 容器env
docker exec hm40006 env | grep MIN_OUTBOUND_INTERVAL_S
MIN_OUTBOUND_INTERVAL_S=1.2

# 源2: compose文件
grep MIN_OUTBOUND_INTERVAL_S /opt/cc-infra/docker-compose.yml
→ line 472: "1.2"

# 源3: 容器启动时间 (recreated)
docker inspect hm40006 --format='{{.State.StartedAt}}'
→ 2026-07-01T16:40:10Z (新启动, Recreate 生效)
```

## 4. 改后预期

- 并发波峰时队列尾等待 -1.5s(5键轮转差距)。
- 不改变单请求成功/失败判定逻辑 (UPSTREAM/FASTBREAK/BUDGET不变)。
- 不改变peer fallback触发时机 (FASTBREAK=2不变, HM1已1)。
- 零429风险 (cooldown >> throttle)。

## 5. CC清单更新

- [HM2-A] MIN_OUTBOUND_INTERVAL_S: ⏳ R517 1.5→1.2 (-0.3s)。待HM2下一轮数据验证429/队列。
- [HM2-B] HM_PEXEC_TIMEOUT_FASTBREAK: ⏳ 当前=2, 与HM1 R516独立。

## 6. 锚定标记

## ⏳ 轮到HM2优化HM1
