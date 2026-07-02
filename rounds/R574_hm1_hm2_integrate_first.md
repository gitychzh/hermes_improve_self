# R574: 两机自改 — dsv4p_nv 首选 integrate 直连, pexec 降为 fallback

> 铁律: 只改对端, 不改自己 — 本轮用户授权两机自改 (R568/R569/R571 同模式).
> 改前必有数据 / 改后必有验证 / 聚焦 hm-40006--nv (dsv4p_nv) / 所有修改写入仓库.

## 背景

用户提出: NVCF pexec 持续有 surge/timeout/502, 能否换走 `integrate.api.nvidia.com` 标准路径?
初判假设 "integrate 自带思考、开箱即用" — 实测推翻: integrate 与 pexec 74f02205 思考触发参数
完全一致 (都要 `thinking:{type:enabled}`), 都无视 reasoning_effort. 不是开箱即用, 网关仍要注入.

但实测发现 integrate 在**延迟和成功率**上显著优于 pexec:
- 延迟 3-13s 平均 8.9s (pexec 15-28s, 快 2-3x)
- 成功率 10/10 (pexec 有 surge/502/empty_200)
- 无 function id 选择 (无 surge 概念)

新瓶颈: integrate per-key RPM 限流 (~6-12/min, 冷却 1-2min). 但**实测限流是 per-key 不是
per-IP** (key2 限流不影响同 IP 的 key4) → 5 key 独立轮换可分摊, 合计 ~50 RPM, hermes 峰值 8/min
远低于上限.

## 改前数据 (2026-07-02 实测)

### 真实流量 (HM1, dsv4p_nv = openclaw 主力)
- 209 req/天, 占 82% (kimi 43, glm5.1 4)
- 常态 2-3 req/min, 峰值 8 req/min (23:48)

### integrate 路径探测
| 测试 | 结果 |
|---|---|
| 裸请求 (无参数) | rc=None, 不自带思考 |
| reasoning_effort=high | rc=None, 无效 |
| thinking:{type:enabled} | **rc 有内容**, 与 pexec 74f02205 一致 |
| 10 发成功率 | 10/10, avg 8.9s |
| 单 key RPM 上限 | ~6-12/min (key5 第 7 发 429) |
| 限流粒度 | **per-key** (key2 限流, 同 IP key4 仍 200) |
| 冷却时长 | 1-2 min |

### 改动前 pexec 基线 (7/2 23时)
- 108 req, 96 成功, 22 失败 (timeout/empty/502) = **88.9% 成功率**

## 方案 (方案C增强版, 用户定稿)

5 key 全走 integrate 首选, pexec 降为 fallback:
1. **常态**: 5 key 独立 rr 轮换走 integrate, 复用全局 throttle (MIN_OUTBOUND_INTERVAL_S=0.5,
   代码默认 1.5) 分摊压力
2. **429 即跳**: 某 key 429 → 标该 key 冷却 90s (NV_INTEGRATE_KEY_COOLDOWN_S, 实测冷却 1-2min 取保守)
   → 立即换下一 key 重试 (per-key 独立已验证, 不会连累)
3. **全限流**: 5 key 都 429 → 标整条 integrate path 冷却 60s (NV_INTEGRATE_PATH_COOLDOWN_S)
   → fallback 现有 pexec _try_tier_keys (同 model, 保证不宕)
4. **思考参数**: 复用 NVCF_PEXEC_MODELS[model]["inject"] (thinking:{type:enabled}),
   integrate 与 pexec 74f02205 触发方式一致, body 构造复用 _build_pexec_body

### 关键设计决策
- **独立 rr counter**: integrate 用模块级 `_integrate_rr_counter`, 不复用 `_next_nv_key` —
  避免 rr_counter.py 的 `_TIER_RR_KEYS` 把 "dsv4p_nv_integrate" fallback 到 "nv_dsv4p"
  与 pexec 的 dsv4p 共用 counter 互相干扰
- **虚拟 tier 名**: cooldown 用 `f"{tier_model}_integrate"` (如 "dsv4p_nv_integrate") 隔离,
  不与 pexec 同 model 的 cooldown 混淆
- **func_health 不追踪 integrate**: integrate 无 function_id, 不调 record_result
  (func_health 只追踪 pexec function surge)
- **只对 NV_INTEGRATE_MODELS 生效**: 默认 `["dsv4p_nv"]` (openclaw 主力, 流量最大 82%).
  kimi_nv (hermes) / glm5_1_nv (opencode) 流量低, 保持 pexec, 不受影响

## 改动文件

| 文��� | 改动 |
|---|---|
| `config.py` | 加 NV_INTEGRATE_* 配置块 (ENABLED/HOST/PATH/KEY_COOLDOWN/PATH_COOLDOWN/MODELS), 默认只 dsv4p_nv |
| `upstream.py` | 加 `_try_integrate_keys()` 函数 (镜像 _try_tier_keys 结构, 走 integrate 路径); `execute_request` first tier 前置 integrate 调用, 失败回退 pexec |

- 备份: `config.py.bak.R574` / `upstream.py.bak.R574` (两机各一份)
- 归档: `deploy_artifacts/R574_integrate_first/{config,upstream}.py`
- 两机源码挂载, 改 .py 只需 restart (清 __pycache__ + docker compose restart)

## 验证 (2026-07-03 00:27+)

### HM1 改动后真实流量
| 指标 | 值 |
|---|---|
| integrate 总请求 | 23 |
| integrate 成功 | 23 (100%) |
| 429 cycle (恢复) | 1 (某 key 429 → 跳下一 key → 成功) |
| timeout | 0 |
| →pexec fallback | 0 (integrate 全程扛住) |
| path cooldown | 0 |

**成功率 100% (23/23), 对比改动前 88.9% (96/108)**. 429 cycle 机制验证: 1 次 429 被正确
标冷却 + 跳 key 恢复, 未影响最终成功率.

### HM2 同步
- 代码 scp 同步, restart 后 E2E curl 测试通过 (integrate 路径, rc 有内容)
- health ok, 5 key 在

## 可调旋钮 (env)

| env | 默认 | 说明 |
|---|---|---|
| NV_INTEGRATE_ENABLED | 1 | 总开关 (0=完全走 pexec, 回退旧行为) |
| NV_INTEGRATE_MODELS | dsv4p_nv | 哪些 model 走 integrate (逗号分隔) |
| NV_INTEGRATE_KEY_COOLDOWN_S | 90 | 单 key 429 冷却秒 |
| NV_INTEGRATE_PATH_COOLDOWN_S | 60 | 全 key 429 时 path 冷却秒 (强制 pexec) |
| (已有) MIN_OUTBOUND_INTERVAL_S | 0.5 (live) / 1.5 (default) | 全局出站间隔, 分摊 per-key 压力 |

## 回滚

`NV_INTEGRATE_ENABLED=0` 重启容器即完全回退到 pexec-only 行为, 零代码改动.
代码层回滚: `cp upstream.py.bak.R574 upstream.py && cp config.py.bak.R574 config.py` + restart.

## 待观察

- 样本量仍小 (23 发), 需积累 24h 真实流量确认稳态成功率
- NVCF integrate 端点本身的稳定性 (R38.10 历史注释说它曾 DEGRADING, 现已恢复, 但需持续监控)
- 若 integrate 端点再次 DEGRADING, NV_INTEGRATE_ENABLED=0 一键回退

## ⏳ 轮到HM2优化HM1
