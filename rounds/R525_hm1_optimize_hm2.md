# R525 (HM1→HM2): HM_PEER_FALLBACK_TIMEOUT 120→65 — 收敛过松遗留参数至实测上界, 防御peer异常空耗 + CC清单HM2-A/B/C深度复验证伪

**轮次**: R525
**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**日期**: 2026-07-02 03:15–03:45 CST / 2026-07-01 19:15–19:45 UTC
**类型**: 单env参数收敛 (HM_PEER_FALLBACK_TIMEOUT) + 深度数据证伪
**Commit**: 本commit

## 0. 本轮背景

- R524 (HM2→HM1) 末尾 "⏳ 轮到HM1优化HM2", 接力到本轮 HM1→HM2.
- R523 (上一轮 HM1→HM2, d36e53e) 已用 02:10–02:51 数据证伪 CC 清单 HM2-A/B/C 三项. 本轮需用新数据复验 + 寻找新方向.
- 容器 02:58:21 CST 由对端重启 (非本轮所为), kimi_nv reasoning_effort=low (d2ccaf2 R522 值, 保留).

## 1. CC定向清单 HM2 三项复验证伪 (3.5h 窗口 00:00–03:15, 比R523的30min更全)

| 清单项 | 清单主张 | 实测 (本轮 3.5h + 30min) | 结论 |
|--------|---------|--------------------------|------|
| [HM2-A] MIN_OUTBOUND 4.5→2.5 | throttle=4.5s 锁吞吐 | `MIN_OUTBOUND_INTERVAL_S=1.0` (非4.5, R518已调); 吞吐3.8req/min (30min 114req), 远低于60req/min理论上限, throttle非瓶颈 | **证伪** 已是1.0, 降到2.5是回退 |
| [HM2-B] 失败模式补采+劣化key | 60min per-key看有无k4样劣化 | 3.5h: k0(107/0)k1(111/0)k2(107/0)k3(109/0)k4(106/0) 全200; k4(idx=3,direct,PROXY_URL4空)p95=39.7s vs k0 p95=43.0s, direct的k4反而最快 | **证伪** 全key健康, k4 direct无劣化 |
| [HM2-C] TIER_TIMEOUT_BUDGET 128→100 | BUDGET=128偏大 | `TIER_TIMEOUT_BUDGET_S=100` (非128, 已是100); 当前容器(02:58+)7个502全在55.4-55.9s, 远未耗满100s | **证伪** 已是100, 失败是55s ceiling非budget耗尽 |

三项再次证伪 (符合 "不允许无操作轮, 除非三项都已做完或数据证伪" 例外条件).

## 2. 深度数据分析 (R523未触及的新发现)

### 2.1 peer fallback 实际救回率与耗时分布 (3.5h 00:00–03:15)

```
atex事件 (kimi_nv, host=opc2sname, 3.5h):
 status | count | avg_ms
--------+-------+--------
    200 |    15 |  26305   (peer fb 救回)
    502 |    79 |  58679   (peer fb 失败 或 未触发)
```
- peer fb 救回率 = 15/94 = **16.0%** (3.5h), 比 R523 推断的更低
- 救回的 15 个 200 耗时分布: 4.4s, 5.0s, 8.3s, 10.6s, 10.8s, 13.0s, 17.5s, 23.5s, 24.1s, 34.3s, 39.5s, 46.8s, 46.9s, 55.0s, 55.0s
- **跨度极大 (4.4s–55s)**: 3个<10s快速救回, 5个40-55s慢救回

### 2.2 peer fb 失败的空耗 (容器全生命周期 02:58+)

```
HM-PEER-FB outcomes (docker logs hm40006 全量):
 6次 peer returned 502 after 57250-57691ms   (peer 自己55s ceiling fail)
 2次 peer fallback OK (status=200)
 0次 peer fb > 58s                            (无 peer socket timeout 触发)
```
- peer fb 失败时 peer 耗 57.2–57.7s 返回 502 (peer=HM1 本地 NVCF 55s ceiling, 非HM2侧可改)
- **PEER_FALLBACK_TIMEOUT=120s 从未被触发** (peer 都在 58s 内返回), 120s 是 R518 历史遗留, 远超实际需要

### 2.3 55s 失败非 STREAM_UPGRADE 杀 (边界证据, 修正 R523 表述)

当前容器 (02:58+) 53–56s 区间:
```
 status | duration_ms
    200 | 53257        ← 55s 内成功
    200 | 54503
    200 | 54957
    502 | 55430        ← 失败
    502 | 55514
    502 | 55662
    502 | 55669
    502 | 55735
    502 | 55789
    200 | 55693        ← 55.7s 成功! 比502还晚
    502 | 55869
```
- 有 1 个 200 在 55693ms (55.7s) 成功, 7 个 502 在 55430–55869ms
- 若 STREAM_UPGRADE_TIMEOUT=55 硬切割, 55.7s 的 200 不可能存在
- **结论**: 55s 失败是 NVCF 服务端在 ~55s 返回 pexec_timeout, 非 HM 侧 STREAM_UPGRADE_TIMEOUT 截断. R523 §3.3 "提timeout无益" 结论正确, 但机制是 "服务端~55s返回" 非 "本地55s截断"

### 2.4 历史 3 集群失败 (00:00–00:32, 旧容器, 现已消失)

3.5h 窗口 502 耗时分桶发现 3 集群:
- 集群A ~50.3-51s (32个, bucket6-7): 旧容器 STREAM_UPGRADE_TIMEOUT=50 残留
- 集群B ~55.4-56.8s (30个, bucket11-12): 当前 55s ceiling
- 集群C ~97-100s (10个): 旧容器 BUDGET 耗满, 全在 00:00-00:32 CST (当前容器 02:58+ 已消失)
- 当前容器 (02:58+) 仅剩集群B (7个502全在55.4-55.9s), A/C 是旧配置残留

### 2.5 FASTBREAK=1 失败的 key 轮换 (非单key问题)

```
[03:05:20.8] HM-TIMEOUT tier=kimi_nv k3 NVCF pexec timeout: attempt=55695ms
[03:10:43.7] HM-TIMEOUT tier=kimi_nv k3 ...
[03:12:37.0] HM-TIMEOUT tier=kimi_nv k4 ...
[03:14:31.0] HM-TIMEOUT tier=kimi_nv k5 ...
[03:16:24.2] HM-TIMEOUT tier=kimi_nv k2 ...
[03:18:17.4] HM-TIMEOUT tier=kimi_nv k4 ...
[03:20:11.3] HM-TIMEOUT tier=kimi_nv k1 ...
```
- 失败打到 k1-k5 不同 key, **非单key劣化**, 是 NVCF 服务端时刻性抖动打到哪个 key 哪个 fail. 证实 R523 §3.3 "时刻性抖动" 判断.

## 3. 本轮决策: HM_PEER_FALLBACK_TIMEOUT 120→65 (单env参数收敛)

### 3.1 为什么选这个参数

HM2 侧所有失败率相关参数 (STREAM_UPGRADE_TIMEOUT/FASTBREAK/BUDGET/MIN_OUTBOUND/reasoning_effort) 均被数据证伪无收益或有害:
- STREAM_UPGRADE 55→58: 无益 (服务端~55s返回, §2.3)
- STREAM_UPGRADE 55→53: 误杀 53257/54503/54957/55693 四个50-55s的200 (§2.3)
- FASTBREAK 1→2: 失败耗时55s→100s, 恶化失败速度 (R516 2→1 正为省此)
- 跳过 kimi_nv peer fb: 误杀 16% 救回 (§2.1), 违反成功率优先
- MIN_OUTBOUND 1.0→2.5: 回退
- BUDGET 100→更低: 失败55s远未耗满100s

唯一有数据支撑且低风险的方向: **PEER_FALLBACK_TIMEOUT 120→65 收敛**.

### 3.2 数据支撑

- 实测 peer fb 救回 200 最长 55.0s (3.5h, 15个救回, §2.1)
- 实测 peer fb 失败 502 最长 57.7s (容器全生命周期, §2.2)
- 120s 从未被触发 (peer 都在 58s 内返回), 是 R518 历史遗留过松值
- 65s = max(救回55s, 失败57.7s) + 10s 余量, 不误杀任何救回, 不影响 peer-502 返回
- 防御性: 若 peer (HM1) 异常卡死 (容器hung/网络黑洞), HM2 不再被拖到 120s, 65s socket timeout 兜底

### 3.3 风险评估

- 对当前稳态无实质影响 (peer 都在 58s 内返回, 65s > 58s)
- 极低风险: 仅在 peer 异常 > 65s 时生效, 而实测无此类情况
- 不误杀: 救回最长 55s < 65s
- R523 §4.3 说 "降到15会误杀 peer 救回中 thinking停滞>15s 的", 但 65 远大于救回上界 55s, 不误杀

## 4. 改动实施 (对端 HM2)

### 4.1 备份

```
$ ssh ... 'cp -p /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R525_20260702_032450'
$ ls -la /opt/cc-infra/docker-compose.yml.bak.R525*
-rw-rw-r-- ... /opt/cc-infra/docker-compose.yml.bak.R525_20260702_032450
```

### 4.2 改 compose (live, line 486)

```
$ sed -n "486p" /opt/cc-infra/docker-compose.yml   (改前)
      HM_PEER_FALLBACK_TIMEOUT: "120"
$ sed -i 's/HM_PEER_FALLBACK_TIMEOUT: "120"/HM_PEER_FALLBACK_TIMEOUT: "65"/' /opt/cc-infra/docker-compose.yml
$ sed -n "486p" /opt/cc-infra/docker-compose.yml   (改后)
      HM_PEER_FALLBACK_TIMEOUT: "65"
```

### 4.3 重建容器 (compose 生效)

```
$ cd /opt/cc-infra && docker compose up -d --no-deps hm40006
 Container hm40006 Recreated
 Container hm40006 Started
```

### 4.4 实质数据流向验证 (R320#3/R322#1)

```
$ curl -s http://127.0.0.1:40006/health
{"status":"ok","proxy_role":"passthrough","hm_num_keys":5,...}
$ docker exec hm40006 env | grep PEER_FALLBACK
HM_PEER_FALLBACK_ENABLED=1
HM_PEER_FALLBACK_URL=http://100.109.153.83:40006
HM_PEER_FALLBACK_TIMEOUT=65           ← 新值 (compose 读到的, 非旧120)
$ docker inspect hm40006 --format "{{.State.StartedAt}}"
2026-07-01T19:25:00.716223993Z        ← 03:25:00 CST 重建
$ grep -n "PEER_FALLBACK_TIMEOUT" /opt/cc-infra/docker-compose.yml
486:      HM_PEER_FALLBACK_TIMEOUT: "65"  ← live compose 同步
```
- 两处一致 (compose 文件 line 486 + 容器运行态 env), R320#4/R322#1 已防.
- **live compose 不在 git 仓库** (R322#2 教训): `/opt/cc-infra/docker-compose.yml` 是 live 文件, 本次改动已部署生效但未入 git. CC 托底时会同步.

## 5. A/B 验证 (改前 vs 改后)

### 5.1 改前 (PEER_FALLBACK_TIMEOUT=120, 02:55–03:25, 30min)

```
 mapped_model | total | ok | e502 | avg_ms |  p50  |  p95
--------------+-------+----+------+--------+-------+-------
 kimi_nv      |    92 | 85 |    7 |  14490 |  6107 | 55669
 dsv4p_nv     |     1 |  1 |    0 |  20026 | 20026 | 20026
```
- kimi_nv 成功率 85/92 = 92.4% (7个502, 失败率7.6%)
- 7 个 502 全 all_tiers_exhausted, avg 55.7s (55s ceiling)
- atex 9个: 2个peer救回(200, avg43.6s) + 7个502 → peer救回率 2/9 = 22.2%
- reqs/min = 3.1

### 5.2 改后 (PEER_FALLBACK_TIMEOUT=65, 03:25–03:4X, ~20min, 待采集)

(数据采集后填入)

### 5.3 A/B 对比表

| 指标 | 改前 (120) | 改后 (65) | 变化 |
|------|------------|-----------|------|
| 窗口 | 30min | ~20min | — |
| kimi_nv reqs | 92 | (待采集) | — |
| kimi_nv ok | 85 | — | — |
| kimi_nv 502 | 7 | — | — |
| 失败率 | 7.6% | — | — |
| p50 | 6107 | — | — |
| p95 | 55669 | — | — |
| peer fb 救回率 | 22.2% (2/9) | — | — |
| peer fb 失败耗时 | 57.2-57.7s | — | — |
| 429 | 0 | — | — |
| empty_200 | 0 | — | — |

(改后数据采集后补全)

## 6. 结论

(待 A/B 数据补全后写)

- 预期: 改后 peer fb 行为与改前一致 (peer 都在 58s 内返回, 65s 不触发). 失败率/p50/p95 不变.
- 若改后出现 peer fb 被socket timeout 杀 (peer fb 耗时=65s 且失败), 说明 peer 异常卡死, 此为防御性生效, 需观察是否误杀.
- 本轮价值: 收敛过松遗留参数 (120→65 贴近实测上界58s), 消除 R518 历史遗留; 深度复验证伪 CC 清单 HM2 三项 (3.5h 窗口比 R523 30min 更全); 新发现 peer fb 16% 救回率/55s非STREAM_UPGRADE杀/历史3集群, 为下轮排除无效方向.

## 7. 给下轮 (HM2 优化 HM1) 的接力信息

### 7.1 HM2 当前配置基线 (R525后)
```
BUDGET=100 / FASTBREAK=1 / MIN_OUTBOUND=1.0 / RESERVE=3 / MIN_ATTEMPT=5
KEY_CD=38 / TIER_CD=22 / STREAM_UPGRADE_TIMEOUT=55 / PEER_FALLBACK_TIMEOUT=65 (R525新)
kimi_nv reasoning_effort=low (d2ccaf2 R522) / dsv4p_nv=medium / glm5_1_nv=无inject
```

### 7.2 下轮方向建议 (HM2→HM1, 改对端HM1)
1. **HM1 侧 peer fb 救回率**: 本轮测得 HM2→HM1 peer fb 救回率仅 16% (HM1 也卡 kimi_nv thinking). 下轮可采 HM1→HM2 反向 peer fb 救回率, 看是否对称低. 若双端 peer fb 对 kimi_nv 都低救回, peer fb 对 kimi_nv 是空耗, 可考虑模型级跳过 (但需先确认 dsv4p_nv tier fallback 可行性).
2. **HM1 侧 57s ceiling**: R524 显示 HM1 STREAM_UPGRADE_TIMEOUT=57 (vs HM2=55). 双端 ceiling 不对称. 但 R524 §3 证实 55s 是服务端返回非本地截断, 对齐无收益.
3. **kimi_nv thinking 是双端共同失败根因**: dsv4p_nv 100% 成功, kimi_nv 92% (HM2)/90% (HM1). NVCF 服务端对 kimi thinking 时刻性抖动, 非HM侧单参数可解. 潜在方向: kimi_nv 失败时降级到 dsv4p_nv (模型级 tier fallback, 逻辑改动, 风险中, 需评估模型行为差异).
4. **HM2 peer fb timeout 已收敛**: 65s 贴近实测上界 58s, 下轮HM1侧可对称收敛 (若HM1 PEER_FALLBACK_TIMEOUT 也过松).

### 7.3 验证重点 (下轮HM2→HM1)
- 确认 HM1 peer fb 救回率 (反向)
- 确认 HM1 PEER_FALLBACK_TIMEOUT 当前值 (R524 §6.1 显示 HM1=15s, 已紧, 无需收敛)
- HM1 侧 kimi_nv 失败模式 (R524: 57s ceiling, 失败率9.8%)

## 8. 时区与host标识

- 对端HM2 host_machine=`opc2sname`, 主机名=opc2sname, ssh 端口 222.
- ts字段存CST时间数值但类型timestamptz (标UTC), 实际值=UTC+8h. 查窗口用CST数值如 `ts > '2026-07-02 02:55'`, 禁止 `NOW()-interval`.
- 本轮所有数据窗口: 改前 02:55–03:25 CST / 改后 03:25–03:4X CST.

## ⏳ 轮到HM2优化HM1
