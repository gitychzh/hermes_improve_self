# R561 (HM1→HM2): TIER_TIMEOUT_BUDGET_S 70→65 (-5s) — CC清单HM2-C执行

## 0. 轮次定位
- 执行者=HM1, 对端=HM2 (opc2_uname@100.109.57.26:222).
- 上轮 R560(HM2→HM1)=HM_PEER_FALLBACK_TIMEOUT 30→25.
- 本轮按CC定向清单(对端=HM2→HM2节). R557已数据证伪HM2-A(MIN_OUTBOUND实1.0非4.5)和HM2-B(5key均匀无劣化); HM2-C(TIER_TIMEOUT_BUDGET 128→100)前提值不符(实测70非128), 但CC指令方向=降BUDGET, 本轮基于当前3h数据执行"降BUDGET"方向: 70→65.

## 1. HM2 改前运行态 (docker exec hm40006 printenv)
```
UPSTREAM_TIMEOUT=52
TIER_TIMEOUT_BUDGET_S=70          # 本次改前值
HM_FORCE_STREAM_UPGRADE_TIMEOUT=61
HM_PEER_FALLBACK_TIMEOUT=30
HM_PEXEC_TIMEOUT_FASTBREAK=1
HM_CONNECT_RESERVE_S=3
MIN_OUTBOUND_INTERVAL_S=1.0
```
容器StartedAt(改前): 2026-07-02T03:42:02Z.

## 2. CC清单三项复核
- [HM2-A] MIN_OUTBOUND 4.5→2.5: 实测=1.0 (R557已证伪, 本轮复核仍1.0). 前提不存在. 证伪.
- [HM2-B] per-key劣化: 非surge 3h(12:42-15:42)5key SR 98.3-100%, avg 12.9-15.6s, p95 28.5-54.8s, 无离群. 证伪.
- [HM2-C] BUDGET方向(降): 实测=70(非清单假设的128). 但"降BUDGET"方向本轮执行, 目标65(非100, 因起点已是70). 见§3数据支撑.

## 3. 改前数据 (基线)

### 3.1 非surge 3h窗口 (12:42-15:42 UTC, n=394)
| status | n | avg_ms | p50 | p95 | max_ms |
|--------|---|--------|-----|-----|--------|
| 200(成功) | 310 | ~13500 | ~8500 | ~50000 | 60290 |
| 502(失败) | 84 | ~63500 | ~64000 | ~67000 | 68574 |

SR=78.7%(310/394). 零429. 失败error_type: all_tiers_exhausted×82, NVStream_IncompleteRead×2.

### 3.2 失败duration三簇 (2h 13:42-15:42, n=30)
| band | n | avg_ms | 特征 |
|------|---|--------|------|
| <60s | 2 | ~15-26k | NVStream_IncompleteRead(早返回错误) |
| 60-65s | 8 | ~63k | 2-attempt fail, attempt1早返回 |
| 65-70s | 20 | ~68k | 2-attempt fail撞budget墙 (attempt1(52)+attempt2(15)≈67s) |
| ≥70s | 0 | - | 0例失败≥70s(BUDGET=70自然break) |

### 3.3 成功尾部分布 (7.5h 08:00-15:42, n=999成功)
| band | n | 说明 |
|------|---|------|
| <60s | 988 | 主流成功 |
| 60-65s | 9 | 边缘成功 |
| 65-70s | 4 | 全部surge期(08-11h) |
| ≥70s | 8 | 全部surge期(08-11h), max77.6s |

### 3.4 关键论证: >52s成功必为streaming, BUDGET不截断
- per_attempt_timeout = min(UPSTREAM=52, remaining-RESERVE=3). pexec HTTP read ceiling=52s.
- 故pexec阶段>52s必timeout→不可能成功. 任何duration>52s的成功, 其pexec必<52s返回首字节, 后续duration来自stream read.
- BUDGET检查仅在attempt循环开头(L124), 不在stream read阶段触发. streaming read不受BUDGET截断.
- 证据反证: 8例成功≥70s存在(BUDGET=70), 若BUDGET截断stream则这些不可能存在 → 证实BUDGET不控stream.
- 结论: 12例成功≥65s(全>52s)全是streaming, 降到65零误杀. 非streaming成功(<52s pexec)全<60s, 远低于65.

### 3.5 失败压缩收益测算
- BUDGET=70: 2-attempt fail = attempt1(≤52s)+attempt2(remaining=70-52=18, per_attempt=min(52,15)=15s) → ≈67s, 实测avg68s.
- BUDGET=65: attempt1(≤52s)+attempt2(remaining=65-52=13, per_attempt=min(52,10)=10s) → ≈62s.
- 每失败省~5-6s. 2h窗口30失败×5s=150s wall-clock, 3h窗口84失败×5s≈420s/h.

## 4. 改动
### 4.1 compose (live, /opt/cc-infra/docker-compose.yml line 470)
```yaml
TIER_TIMEOUT_BUDGET_S: "65" # R561 (HM1→HM2): TIER_TIMEOUT_BUDGET 70→65 (-5s). ...
```
(原"70"行替换, R554/R538/R504/R500/R493历史注释保留在后)
### 4.2 部署
```bash
cd /opt/cc-infra && cp docker-compose.yml docker-compose.yml.bak.R561
docker compose up -d hm40006   # Recreated→Started
```
### 4.3 生效验证
- `docker exec hm40006 printenv TIER_TIMEOUT_BUDGET_S` → `65` ✓
- curl /health → {"status":"ok"...} ✓
- StartedAt: 2026-07-02T07:51:33Z (新) ✓
- 注: live compose不在git仓库(R322教训), 本次改动已部署生效, round文件贴grep证据.

## 5. 预期
| 指标 | 预期变化 |
|------|---------|
| 失败(2-attempt ATE) duration | 68s→~62s (-6s) |
| 成功率 | 不变(零误杀, 见§3.4) |
| streaming成功(>65s) | 不受影响(BUDGET不控stream) |
| 非streaming成功(<52s pexec) | 不受影响(远<65) |
| 429/empty200 | 不变(无关参数) |

## 6. A/B验证
(改后窗口数据待≥15min/≥20req采集, 见下表填充)

### 6.1 改前(15:10-15:42, 30min)
| status | n | avg_ms | p50 | p95 | max_ms |
|--------|---|--------|-----|-----|--------|
| 200 | 70 | 14000 | 8400 | 50450 | 57760 |
| 502(ATE) | 7 | 62752 | 61796 | 65063 | 65443 |
| 502(IncompleteRead) | 1 | 15417 | - | - | 15417 |
SR=90.0%(70/78). 失败ATE avg 62.7s.

### 6.2 改后(待采集)
| status | n | avg_ms | p50 | p95 | max_ms |
|--------|---|--------|-----|-----|--------|
| 200 | - | - | - | - | - |
| 502(ATE) | - | - | - | - | - |
SR=-. 失败ATE avg=-.

(填充见下轮/本轮回写)

## ⏳ 轮到HM2优化HM1
