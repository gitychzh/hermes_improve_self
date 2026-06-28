# R263: HM1→HM2 — config.py 清理死代码, 收敛为单一 glm5.1 NVCF pexec — 单轮清理, 收敛为单一 glm5.1 NVCF pexec — 单轮清理

**回合类型**: 清理 (单主题: 源码与实际配置对齐)
**方向**: HM1 (opc_uname) → HM2 (opc2_uname)
**时间**: 2026-06-29 01:13 UTC
**关联**: 与 HM2 提交的 R262 (TIER_TIMEOUT_BUDGET_S 124→128 调参, commit f10826f) 同一时段但独立 — 本轮只清 config.py 死代码, 不改 env。改前容器 env 已被 HM2 的 R262 部署为 TIER_TIMEOUT_BUDGET_S=128; 本轮 rebuild 沿用该值, 未改动 env。
**原则**: 干净整洁、工程化、便于长期调参维护 — 铁律:只改HM2不改HM1

## 摘要

HM2 hm40006 容器 env 已收敛为单模型 glm5.1_hm_nv (`HM_NV_MODEL_TIERS=["glm5.1_hm_nv"]`)，
但 `gateway/config.py` 源码仍保留 R38.14/R208 的三模型 (glm5.1/deepseek/kimi) 骨架, 且
`MODEL_MAP` 把 `glm5.1_hm_nv` 偷偷路由到 `deepseek_hm_nv`。导致 /health 暴露三个 pexec
模型, 且真实请求的 `mapped_model` 字段被记成 deepseek_hm_nv (尽管 tier 实际跑 glm5.1)。
本轮删除 deepseek/kimi 全部死代码, 让源码与单模型 env 完全一致, 消除幽灵映射。

## 改前数据 (基线, 改前 30min ha_requests→hm_requests)

### hm_requests 30min 总览 (改前)
- Total: 56, OK(200): 43 → **76.79%**
- Errors: 13 (全部 all_tiers_exhausted)
- Avg duration: 61559ms, Max: 127583ms

### mapped_model 分布 (改前 — 暴露偷路由问题)
| request_model | mapped_model | tier_model | cnt |
|---|---|---|---|
| glm5.1_hm_nv | **deepseek_hm_nv** | glm5.1_hm_nv | 43 |
| glm5.1_hm_nv | **deepseek_hm_nv** | (空) | 13 |

→ hermes 发 glm5.1_hm_nv, 但 mapped_model 被记成 deepseek_hm_nv (MODEL_MAP 偷路由铁证)。

### hm_tier_attempts 30min (改前 — 实际命中 glm5.1 function)
- 全部 tier=glm5.1_hm_nv, litellm_model=nvcf_z-ai/glm-5.1_k1..k5
- 错误: 429_nv_rate_limit / empty_200 / 500_nv_error / NVCFPexecSSLEOFError
- 无任何 deepseek/kimi 实际命中 (证明 deepseek/kimi 是死代码)

### /health (改前)
`nvcf_pexec_models: ["deepseek_hm_nv","kimi_hm_nv","glm5.1_hm_nv"]` (暴露死代码)

## 代码变化 (gateway/config.py)

| 区块 | 改前 | 改后 |
|---|---|---|
| 文件头 docstring | R38.14 三模型 tier 描述 | R262 单模型 glm5.1 描述, 注明清理历史 |
| `NVCF_PEXEC_MODELS` | 3 模型 (deepseek/kimi/glm5.1) | 仅 glm5.1_hm_nv |
| `NV_MODEL_IDS` | 3 模型 ID | 仅 `"glm5.1_hm_nv":"z-ai/glm-5.1"` |
| `NV_MODEL_TIERS` 默认值 | `["deepseek_hm_nv","glm5.1_hm_nv","kimi_hm_nv"]` | `["glm5.1_hm_nv"]` |
| `DEFAULT_NV_MODEL` 默认值 | `deepseek_hm_nv` | `glm5.1_hm_nv` |
| `MODEL_MAP` | glm5.1_* → deepseek_hm_nv (偷路由) + deepseek/kimi 别名 | 全部别名 → glm5.1_hm_nv |
| `_TIER_RR_KEYS` | 3 tier RR 键 | 仅 glm5.1 |
| `MODEL_INPUT_TOKEN_SAFETY` | 3 模型 context | 仅 glm5.1 (170000) |
| 行数 | 316 行 | 284 行 |

保留: `_OLD_RR_KEY_MAP` (历史 RR 计数器键名迁移表, 删除会丢失持久化 RR 状态)。

## 备份

- 宿主源码: `/opt/cc-infra/proxy/hm-proxy/gateway/config.py.bak.R262.1782666820` (14297 字节)
- 容器内: `/app/gateway/config.py.bak.R262` (14297 字节)

## 部署

改 `gateway/*.py` 必须 rebuild (非 restart):
```
cd /opt/cc-infra && docker compose build hm40006 && docker compose up -d hm40006
```
容器 15s 内转 healthy。

## 验证 (改后, 真实请求 + 日志数据)

### /health (改后)
`nvcf_pexec_models: ["glm5.1_hm_nv"]`, `hm_model_tiers: ["glm5.1_hm_nv"]`, `hm_default_model: glm5.1_hm_nv` ✅

### 真实请求 (curl 直打 40006, 非流式)
- model=glm5.1_hm_nv → 200, content="R262-OK", response.model=z-ai/glm-5.1 ✅
- model=glm5.1 (hermes 别名) → 200, content="R262-ALIAS-OK", response.model=z-ai/glm-5.1 ✅

### DB 记录 (改后两条测试请求)
| request_model | mapped_model | tier_model | upstream_type | status |
|---|---|---|---|---|
| glm5.1_hm_nv | **glm5.1_hm_nv** | glm5.1_hm_nv | nvcf_pexec | 200 |
| glm5.1 | **glm5.1_hm_nv** | glm5.1_hm_nv | nvcf_pexec | 200 |

→ mapped_model 不再是 deepseek_hm_nv, 偷路由已修复 ✅

### 改后窗口 (rebuild 完成后) 整体
- Total: 5, OK: 4 → 80.00% (窗口流量少, 仅几分钟)
- mapped_model 分布: 100% glm5.1_hm_nv (零 deepseek) ✅
- 错误: 1 all_tiers_exhausted (glm5.1 本身 5-key 限流, 非本次清理引入)

## 预期效果

- 源码与单模型 env 完全一致, /health 不再暴露死模型
- mapped_model 字段真实反映 glm5.1, 后续调参日志可读性提升
- 消除 "env 改回多 tier 时请求会偷偷跑 deepseek" 的隐患
- 不改变实际推理行为 (改前 tier 已是 glm5.1), 仅清理源码与字段

## 后续轮次 (不在本轮范围)

- R263: 清 hermes provider_models_cache.json (17 个脏模型名)
- R264: hermes config.yaml 去 litellm-local-ms fallback (纯 NV 单链路)
- R265: 归档废弃 litellm-nv-hm/litellm-nv/litellm-glm51(-fb) 目录

## 回滚

```
docker cp /opt/cc-infra/proxy/hm-proxy/gateway/config.py.bak.R262.1782666820 hm40006:/app/gateway/config.py
# 或宿主层面:
cp /opt/cc-infra/proxy/hm-proxy/gateway/config.py.bak.R262.1782666820 /opt/cc-infra/proxy/hm-proxy/gateway/config.py
cd /opt/cc-infra && docker compose build hm40006 && docker compose up -d hm40006
```

## ⏳ 轮到HM2优化HM1
