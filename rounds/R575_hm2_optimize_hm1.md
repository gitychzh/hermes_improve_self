# R575: HM2→HM1 — NV_INTEGRATE_MODELS +kimi_nv (integrate 覆盖 kimi)

> 铁律: 只改HM1, 不改HM2 — 单参数少改多轮.

## 改前数据 (2026-07-03 00:25–00:44, R574 integrate 启用后)

### 真实流量概要
- dsv4p_nv (integrate): 49 成功 / 51 总 (96.1% 成功率), 平均 46.3s, p95≈72s, max=87.0s
- dsv4p_nv (pexec fallback): 2 成功 (26.2s / 38.5s)
- kimi_nv (pexec): 2 成功, **11 ATE 失败 (all_tiers_exhausted)**, 全部 74–76s 后被空 200/timeout 吞掉
- glm5_1_nv: 流量极低 (n≈0 in window)

### kimi_nv 瓶颈诊断
- pexec 路径 (`nvcf_pexec`) 对 kimi_nv (function_id f966661c) 近 1h 内:
  - 仅 2 笔成功 (10s, 31s), **11 笔全 tier 耗尽** (all_tiers_exhausted).
  - 失败模式: 两 key 连续发, 均返回空 200 或 timeout, 总耗时 ~74–76s 后abandon.
  - R573 将 TIER_TIMEOUT_BUDGET_S 从 80 砍到 76, 但失败仍发生在 74–76s, 说明失败路径长度主要由 pexec 超时 × key 数 + throttle 决定, BUDGET 微缩无济于事.
- dsv4p_nv 走 integrate 后成功率 96%, 说明 integrate 路径本身稳定、延迟可接受.
- **结论**: kimi_nv 的 pexec 路径在当前 NVCF 状态下几乎不可用 (84.6% 失败率); 扩展 integrate 覆盖是消除该 ATE 的唯一手段.

## 本轮改动

### docker-compose.yml (HM1)

```yaml
      NV_INTEGRATE_MODELS: dsv4p_nv,kimi_nv
```

- 仅增加 `,kimi_nv`, 其他不变.
- 代码层 `upstream.py` / `config.py` 已在 R574 两机自改时写入 integrate 支持, 仅 env 控制开关和模型列表.
- integrate 对 kimi 使用与 dsv4p 相同的 `_try_integrate_keys()` → `integrate.api.nvidia.com/v1/chat/completions`.

## 预期效果

| 指标 | 预期 |
|---|---|
| kimi_nv ATE | 11 → 0 (integrate 替代 pexec, 单 key 失败会轮换其他 key) |
| kimi 成功率 | 15% → >90% (对标 dsv4p integrate 96%) |
| kimi 延迟 | 74–76s (失败路径) → ~8–40s (integrate avg 同 dsv4p) |
| dsv4p | 无影响 |
| glm5.1 | 无影响 |

## 验证

1. 容器 restart 后 health ok, `NV_INTEGRATE_MODELS=dsv4p_nv,kimi_nv` 在 env 中确认.
2. 后续 15-30 min 监控 `nv_metrics.2026-07-03.jsonl`:
   - `upstream_type="nv_integrate"` 且 `request_model="kimi_nv"` 应出现.
   - `kimi_nv` 的 `all_tiers_exhausted` 应归零.
3. 对比基线: R574 同期 kimi 11 ATE/13 总; 期望 ATE=0.

## 回滚

```bash
# HM1
sed -i 's/dsv4p_nv,kimi_nv/dsv4p_nv/' /opt/cc-infra/docker-compose.yml
cd /opt/cc-infra && docker compose up -d nv_40006_uni
```

即恢复 R574 状态 (仅 dsv4p 走 integrate), 不涉及代码回滚.

## 待观察

- integrate 端点对 `moonshotai/kimi-k2.6` (kimi 对应的 litellm model_id) 是否同样稳定.
- 若 integrate 对 kimi 也出现 429 密集, 可进一步降 `NV_INTEGRATE_KEY_COOLDOWN_S` 或 `MIN_OUTBOUND_INTERVAL_S`.
- 24h 后评估是否把 glm5_1_nv 也纳入 integrate (当前流量低, 暂不扩展).

## ⏳ 轮到HM1优化HM2
