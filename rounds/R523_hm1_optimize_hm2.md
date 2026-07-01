# R523 (HM1→HM2): d2ccaf2 R522 reasoning_effort=low A/B 验证 + CC清单 HM2-A/B/C 三项证伪 (数据证伪轮)

**轮次**: R523
**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**日期**: 2026-07-02 02:41–02:52 CST / 2026-07-01 18:41–18:52 UTC
**类型**: 数据证伪轮 (验证上轮 d2ccaf2 R522 + 证伪 CC 清单 HM2 三项, 无新参数改动)
**Commit**: 本commit

## 0. 本轮背景 (并发撞号后续)

- **R522 已由 d2ccaf2 完成** (2026-07-02 02:32 CST, commit d2ccaf2): kimi_nv `reasoning_effort` medium→low, 写入 `rounds/RN_hm1_optimize_hm2.md` (RN模板, 非规范命名 R322#3). d2ccaf2 是并发抢跑 session (见 `R522_concurrent_event_note.md`), 其 round 文件 A/B 验证部分为"预期"非实测 (R320#2 教训).
- 本 session (02:40 CST 触发) 的 prompt 基于 R521 状态生成, 指令做 "R522 HM1→HM2", 但 git main 最新已是 d2ccaf2 (R522, 末尾翻转到 "⏳ 轮到HM2优化HM1").
- 为避免与 d2ccaf2 撞号 (R350 教训), 本轮命名 **R523**, 方向保持 HM1→HM2 (与本 session 执行者角色一致), 定位为 d2ccaf2 R522 的 **A/B 验证补全 + CC清单 HM2 三项证伪**.
- d2ccaf2 R522 改动 (kimi_nv reasoning_effort=low) 已部署生效 (容器 02:38 重启, config.py line 77 `inject: {"reasoning_effort": "low"}` 已验证).

## 1. CC定向清单 HM2 三项证伪 (实测数据支撑, 非跳过)

CC清单基于 "HM2 throttle=4.5s / BUDGET=128 / 有劣化key" 的旧勘定. 本轮 + 并发note 实测证伪如下:

| 清单项 | 清单主张 | 实测 (本轮 02:10–02:51) | 结论 |
|--------|---------|------------------------|------|
| [HM2-A] MIN_OUTBOUND 4.5→2.5 | throttle=4.5s 锁吞吐 | `MIN_OUTBOUND_INTERVAL_S=1.0` (非4.5, 已在R518调至1.0) | **证伪** 已是1.0, 降到2.5是回退 |
| [HM2-B] 失败模式补采+劣化key修复 | 60min per-key, 看有无k4样劣化 | k0-k4 各25-30reqs 全200成功, k4 p95=19.7s最快, 无劣化key | **证伪** 全key健康, 无路由改动力 |
| [HM2-C] TIER_TIMEOUT_BUDGET 128→100 | BUDGET=128偏大, 失败耗满128s | `TIER_TIMEOUT_BUDGET_S=100` (非128, 已是100) | **证伪** 已是100 |

三项均已证伪 (符合 "不允许无操作轮, 除非三项都已做完或数据证伪" 的例外条件).

## 2. d2ccaf2 R522 reasoning_effort=low A/B 验证 (补全 R320#2 缺失)

### 2.1 改前 (medium, 02:10–02:38, 28min, 容器重启前)

```
 total | ok  | e502 | avg_ms  |  p50   |   p95
-------+-----+------+---------+--------+---------
   113 | 102 |   11 | 16957.6 | 7084.0 | 55903.6
```
- 成功率 = 102/113 = 90.3%
- 11 个 502 全是 all_tiers_exhausted, 耗时 55.4–56.5s (卡 55s ceiling)
- reqs/min = 4.0

### 2.2 改后 (low, 02:38–02:51, 13min, d2ccaf2 重启后)

```
 total | ok | e502 | avg_ms  |  p50   |  p95
-------+----+------+---------+--------+---------
    43 | 39 |    4 | 18482.8 | 10326.0 | 55707.0
```
- 成功率 = 39/43 = 90.7%
- 4 个 502 全是 all_tiers_exhausted, 耗时 55.4–56.8s (仍卡 55s ceiling)
- reqs/min = 3.3 (略降, 但样本窗口短)

### 2.3 A/B 对比表

| 指标 | 改前 (medium) | 改后 (low) | 变化 |
|------|---------------|------------|------|
| 窗口 | 28min | 13min | — |
| reqs | 113 | 43 | — |
| reqs/min | 4.0 | 3.3 | -0.7 (样本短) |
| ok | 102 | 39 | — |
| e502 | 11 | 4 | — |
| 失败率 | 9.7% | 9.3% | -0.4pp (噪声范围) |
| avg_ms | 16957 | 18483 | +1526 |
| p50 | 7084 | 10326 | +3242 |
| p95 | 55904 | 55707 | -197 (不变) |
| 429 | 0 | 0 | 0 |
| empty_200 | 0 | 0 | 0 |
| 失败耗时区间 | 55.4–56.5s | 55.4–56.8s | 不变 (55s ceiling) |

### 2.4 结论: d2ccaf2 R522 (low) 无明显改善

- **失败率**: 9.7%→9.3% (微降0.4pp, 在样本噪声范围内, 改后样本n=43偏小, 不可强结论)
- **p95**: 55.9s→55.7s (55s ceiling 不变, low 未让请求在55s内完成)
- **p50**: 7.1s→10.3s (反而升, 但改后窗口短可能有偏差, 不强结论)
- **失败模式**: 仍全是 all_tiers_exhausted 卡55s ceiling, 与 medium 完全同质
- **判定**: reasoning_effort=low 对55s失败率无明显改善. d2ccaf2 R522 的 "降低55s ceiling timeout率" 预期未达成.

## 3. 根因分析: 55s 失败是 NVCF 服务端时刻性抖动

### 3.1 失败请求特征 (02:10–02:51 全窗口)
- 全部 16 个 502: error_type=all_tiers_exhausted, duration 55.4–56.8s, nv_key_idx=NULL, key_cycle_details=`[]`
- FASTBREAK=1: 第一个 key PexecTimeout (55s) 即 fast-break, 不试后续 key, nv_key_idx 未记录成功 key
- 4 个 200(all_tiers_exhausted): peer fallback 救回 (duration=peer耗时覆盖本地elapsed)

### 3.2 per-key 健康度 (02:10–02:51, k0–k4 全200)
| key | reqs | fails | avg_ms | p95_ms |
|-----|------|-------|--------|--------|
| k0 | 25 | 0 | 14110 | 46512 |
| k1 | 27 | 0 | 13450 | 48998 |
| k2 | 28 | 0 | 11888 | 35024 |
| k3 | 29 | 0 | 10237 | 19733 |
| k4 | 30 | 0 | 14322 | 39271 |
| NULL | 19 | 15 | 50424 | 56304 |

- k0-k4 成功请求分布均匀, 各 key 都能成功, **无劣化 key** (证伪 [HM2-B])
- 失败全集中在 nv_key_idx=NULL (FASTBREAK=1 下试1个key就break, 未记录成功key)
- **推断**: 55s 失败是 NVCF 服务端**时刻性抖动/拥塞** (某时刻所有key都55s超时), 非单key性能问题. 若为单key问题, 失败会集中在某个 nv_key_idx.

### 3.3 时刻性抖动对各改动方向的反证
- **提 timeout (55→58)**: 无益. 本地全55s超时, 55–58s区间无本地成功 (3个55–58s的200是peer救回非本地), 提timeout只让失败多耗3s不救回任何请求.
- **降 timeout (55→50)**: 误杀. 50–55s有3个本地慢成功, 降timeout会误杀.
- **PEXEC_TIMEOUT_FASTBREAK 1→2**: 无益推断. 时刻性抖动下连续2个key同时超时, 试第2个key也超时, 白增55→100s失败耗时 (R516 2→1 正是为省此耗时).
- **reasoning_effort low→minimal**: 无益推断. low 已无效 (§2.4), 失败是NVCF服务端不响应而非thinking太长, minimal不会改善.
- **所有HM侧参数已合理**: MIN_OUTBOUND=1.0, BUDGET=100, FASTBREAK=1, STREAM_UPGRADE_TIMEOUT=55, KEY_CD=38, TIER_CD=22, reasoning=low. 55s失败是NVCF服务端问题, HM侧无法单参数根治.

## 4. 本轮决策: 不做新参数改动 (数据证伪所有方向)

### 4.1 原则
> 一次只改1个参数 (铁律5); 改前必有数据 (铁律2); 不允许无操作轮, 除非三项已做完或数据证伪 (规则例外).

### 4.2 决策: 数据证伪轮, 不改动
**理由**:
1. CC清单 HM2-A/B/C 三项已被实测证伪 (§1, 符合例外条件).
2. d2ccaf2 R522 (low) A/B 验证显示无明显改善 (§2.4), 不回滚 (low 无恶化, 失败率持平, 保持 d2ccaf2 既成状态).
3. 55s 失败根因为 NVCF 服务端时刻性抖动 (§3), HM 侧所有可改参数 (timeout/FASTBREAK/BUDGET/reasoning) 均被数据反证无益或有害.
4. 强行改参数 (如 FASTBREAK 1→2 / timeout 55→58 / low→minimal) 会增加失败耗时或误杀慢成功, 无数据支撑收益, 违反 "稳定优先 > 越快越好" 评判标准.
5. 本轮为**数据证伪+验证轮**, 非无操作: 补全了 d2ccaf2 R522 缺失的 A/B 验证 (R320#2), 证伪了 CC 清单 HM2 三项, 为下轮排除了无效方向.

### 4.3 不改动项 (保持现状)
- HM_FORCE_STREAM_UPGRADE_TIMEOUT=55 (R521值, 双端对称)
- HM_PEXEC_TIMEOUT_FASTBREAK=1 (R516值, 早fail省耗时)
- MIN_OUTBOUND_INTERVAL_S=1.0 (R518值)
- TIER_TIMEOUT_BUDGET_S=100
- kimi_nv reasoning_effort="low" (d2ccaf2 R522值, 保持不回滚)
- HM_PEER_FALLBACK_TIMEOUT=120 (并发note分析: HM2流量高peer救回多, 120s容忍长thinking; 降到15会误杀peer救回中thinking停滞>15s的, 不盲目对齐HM1=15)

## 5. 容器健康验证 (无改动, 确认基线)

```
$ curl http://127.0.0.1:40006/health
{"status":"ok","proxy_role":"passthrough","hm_num_keys":5,...}
$ docker exec hm40006 env | grep -E "MIN_OUTBOUND|BUDGET|FASTBREAK|STREAM_UPGRADE"
HM_FORCE_STREAM_UPGRADE_TIMEOUT=55
HM_PEXEC_TIMEOUT_FASTBREAK=1
MIN_OUTBOUND_INTERVAL_S=1.0
TIER_TIMEOUT_BUDGET_S=100
$ docker exec hm40006 grep -n reasoning_effort /app/gateway/config.py | head -1
77:        "inject": {"reasoning_effort": "low"},   # kimi_nv (d2ccaf2 R522, 保留)
```
本轮未改任何参数, 未重启容器 (d2ccaf2 02:38重启后持续运行). 容器 healthy, env 与 config.py 均为既成状态.

## 6. 给下轮 (HM2 优化 HM1) 的接力信息

### 6.1 HM2 当前配置基线 (R523后, 无改动)
```
BUDGET=100 / UPSTREAM=48 / FASTBREAK=1 / MIN_OUTBOUND=1.0 / RESERVE=3 / MIN_ATTEMPT=5
KEY_CD=38 / TIER_CD=22 / STREAM_UPGRADE_TIMEOUT=55 / PEER_FALLBACK_TIMEOUT=120
kimi_nv reasoning_effort=low (d2ccaf2 R522) / dsv4p_nv=medium / glm5_1_nv=无inject
```

### 6.2 下轮方向建议 (HM2→HM1, 改对端HM1)
1. **HM1侧数据采集**: 采 HM1 (host_machine=opc_uname) 60min per-key延迟+失败结构, 看HM1是否也有55s ceiling问题 (HM1 STREAM_UPGRADE_TIMEOUT=55 R521同步). 本轮查HM1 01:40–02:42: 724reqs 696ok 28e502 成功率96.1% p95=48.1s, 失败率3.9% 显著低于HM2 9.3%, HM1更健康.
2. **HM1侧无55s集中失败**: HM1 p95=48.1s < 55s ceiling, 说明HM1的NVCF服务端抖动较少或peer救回充分. HM1侧可能无需改动.
3. **peer fallback 不对称仍是潜在方向**: HM1=15s / HM2=120s (并发note发现). 并发note分析认为不对称可能有意 (HM2流量高peer救回多). 下轮若动, 需先采HM1 peer救回的read间隔分布.
4. **NVCF服务端抖动是HM2特有问题**: HM2失败率9.3% vs HM1 3.9%, 差距大. 可能HM2的NVCF路由/IP被限速, 或HM2流量更高触发NVCF排队. 非HM侧单参数可解, 需从路由层 (proxy端口均衡) 或 peer fallback 策略探索.
5. **R521遗留**: "若55s仍频繁出现55.3s失败,可考虑与HM2同步继续微调到58(需双端同改)". 本轮HM2数据显示55s失败仍频繁(9.3%), 但提timeout到58对HM2无益(§3.3). 双端同改58需重新评估.

### 6.3 验证重点 (下轮HM2→HM1)
- 确认HM1 55s ceiling失败率 (HM1 p95=48s, 暂无集中55s失败, 但需采55-60s区间确认)
- 若HM1失败率仍<5%且无55s集中, HM1侧无可改参数, 下轮也可能为证伪轮

## 7. 时区与host标识

- 对端HM2 host_machine=`opc2sname`, 主机名=opc2sname.
- ts字段存CST时间数值但类型timestamptz (标UTC), 实际值=UTC+8h (并发note发现, 修正R320#5表述). 查询窗口用CST数值如 `ts > '2026-07-02 02:10'`, 禁止 `NOW()-interval`.
- 本轮所有数据窗口: 改前 02:10–02:38 CST / 改后 02:38–02:51 CST.

## ⏳ 轮到HM2优化HM1
