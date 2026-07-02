# R546 (HM2→HM1): ⏸️ NOP — R544数据确认kimi_nv function-level surge持续, dsv4p_nv 99.4%控制组; 全部候选参数数据否决. 单参数少改多轮. 铁律:只改HM1不改HM2

## 漂移检测 (R543/R544声称值 vs 实际部署)

| 参数 | R544声称 | 容器env实际 | compose文件实际 | 状态 |
|------|---------|------------|---------------|------|
| UPSTREAM_TIMEOUT | 25 | 25 ✅ | 25 ✅ | 一致 |
| TIER_TIMEOUT_BUDGET_S | 80 | 80 ✅ | 80 ✅ | 一致 |
| MIN_OUTBOUND_INTERVAL_S | 1.2 | 1.2 ✅ | 1.2 ✅ | 一致 |
| KEY_COOLDOWN_S | 25 | 25 ✅ | 25 ✅ | 一致 |
| TIER_COOLDOWN_S | 25 | 25 ✅ | 25 ✅ | 一致 |
| HM_CONNECT_RESERVE_S | 3 | 3 ✅ | 3 ✅ | 一致 |
| HM_PEXEC_TIMEOUT_FASTBREAK | 1 | 1 ✅ | 1 ✅ | 一致 |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | 1.0 ✅ | 1.0 ✅ | 一致 |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | 61 ✅ | 61 ✅ | 一致 |
| HM_PEER_FALLBACK_TIMEOUT | 61 | 61 ✅ | 61 ✅ | 一致 |
| HM_FORCE_STREAM_UPGRADE | 1 | 1 ✅ | 1 ✅ | 一致 |
| inject_thinking(kimi_nv/dsv4p_nv/glm5_1_nv) | False/False/False | 运行时查看为null(运行时解析为null,源码中`inject`键非`inject_thinking`) | config.py中kimi=low,dsv4p=medium,glm=chat_template_kwargs enable_thinking | ✅ 源码无漂移(R502+后续未动) |

**漂移结论**: 零漂移。R543(SSLEOF 1.5→1.0)和R544(NOP)所有参数均实际生效。容器StartedAt=2026-07-02T00:03:22.82359706Z,在R543 commit(a6e6437, 08:04+08)之前。

## 数据采集概要 (R544后窗口, 08:20采样)

- **docker logs最近100行**: 零429, 零SSLEOF, 零WARN。peer fallback 5次全失败于~61000ms(61s timeout截断,CEILING BINDING)。
- **2h DB汇总**:
  - dsv4p_nv: 2291req | 2277ok(99.4%) | min_fail=57263ms(max) | max_ok=91125ms | p95=32220ms | 14 fail
  - kimi_nv: 1219req | 967ok(79.3%) | min_fail=50241ms | max_ok=95245ms | p95=47720ms | 253 fail
  - **Surge Isolation**: dsv4p_nv与kimi_nv差距20.1pp — function-level surge确认,网关参数非root cause.

## 候选评估表 (数据否决全部)

| 参数 | 当前值 | 候选新值 | 评估数据 | 决策 |
|------|--------|----------|----------|------|
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | 63(+2s) | dsv4p min_fail=57.2s→gap=3.8s; kimi min_fail=50.2s→gap=10.8s; peer fb 5×61000ms截断是61s CEILING本身对端HM2限制; HM1本地ceiling不与peer fb binding | ❌ |
| UPSTREAM_TIMEOUT | 25 | 23(-2s) | dsv4p p50=6.4s/p95=32.2s/零timeout; kimi失败全NVCF surge非速连问题 | ❌ |
| TIER_TIMEOUT_BUDGET_S | 80 | 75(-5s) | 2h只有2个成功>70s(kimi 80s区间3req,dsv4p 2req),但max_ok=95.2s>75会误杀; 且BUDGET影响attempt2 ceiling不影响fast-break路径 | ❌ |
| MIN_OUTBOUND_INTERVAL_S | 1.2 | 1.0(-0.2s) | HM1 key_cooldown=25 >> 1.2; dsv4p无429但无吞吐量压力证据 | ❌ |
| CONNECT_RESERVE_S | 3 | 2(-1s) | max connect=2.1s实测, 2仅0.95x边际不足 | ❌ |
| SSLEOF_RETRY_DELAY | 1.0 | 0.5(-0.5s) | 2h零SSLEOF; 但1.0已是HM2对称值,再降边际为负 | ❌ |
| FASTBREAK | 1 | 0(禁fast-break) | FASTBREAK=0意味着ATE=N×UPSTREAM=5×25=125s>>BUDGET; 零历史证据支持>1次重试可成功 | ❌ |
| HM_PEER_FALLBACK_TIMEOUT | 61 | 63(+2s) | peer fb截断在61000ms是HM2端处理需61s vs cutoff 61s=exact ceiling; HM2已61, HM1已61, 对称且binding; 再增需HM2同步 | ❌ |

## 决策分析

1. **Surge Isolation强化**: dsv4p_nv 2h 99.4% SR 是 HM1 网关参数已最优的铁证。kimi_nv 的 20.7% 失败率与 dsv4p_nv 的 0.6% 差距极端, 且 kimi_nv 失败全为 NVCF 侧 function 级容量/排队问题(小时级 42.9%→100%→90.5%→73.3% 剧烈波动)。
2. **Ceiling绑定评估**: peer fallback 全部 61000ms 截断 → HM1 peer_fb=61 对端 HM2 处理实际需 61s, 但 HM2 本地 HM_FORCE_STREAM_UPGRADE_TIMEOUT=61 意味着任何通过 peer fb 的流式升级请求在 HM2 端也要跑满 61s。这是**对端约束**, 单方上调 HM1 的 peer_fb 无法救回(请求仍会在 HM2 端被 61s 截断)。
3. **BUDGET误杀**: 2h窗口 only 5/3604 requests >70s (3 kimi + 2 dsv4p, all <100s), 但这些>80s成功存在(最远dsv4p 91.1s)。若BUDGET降至75会误杀2个慢成功。
4. **FASTBREAK状态**: FASTBREAK=1已极限, dsv4p_nv零timeout支持, kimi_nv救回率极低(2h仅1次peer fb OK,且并非fast-break救回而是peer fallback通道)。FASTBREAK=0会延长失败路径5倍。

## 结论

全部候选参数被数据否决。本轮为**NOP(参数-wise)**。

## ⏳ 轮到HM1优化HM2
