# R276: HM1 hm40006 容器清理 kimi 死代码 — 与 hermes 纯 dsv4p 配置对齐 — 授权破例自改

**回合类型**: 清理 (单主题: 容器 config.py 与 hermes config 对齐)
**方向**: HM1 本机 (授权破例自改, 非交替优化方向)
**时间**: 2026-06-29 11:06 UTC+8 (hm40006 rebuild 时间)
**原则**: 干净整洁、工程化、hermes 链路 (40006) 只用 dsv4p; 严格不碰 40003

## 摘要

R273 已把 HM1 hermes config 清成纯 dsv4p (deepseek_hm_nv 单模型, 无 kimi 别名,
无 40003 fallback)。但 hm40006 容器 config.py 仍含 kimi 死代码 — /health 暴露
nvcf_pexec_models=[deepseek,kimi], 且直接对 40006 发 kimi-k2.6 会被容器映射到
kimi_hm_nv (R273 验证3 实测 mapped_model=kimi_hm_nv)。本轮清容器侧 kimi 死代码,
让 hermes→40006 整条链路与 HM2 (R263) 一致: 纯 dsv4p, 无 kimi 路径。

## 改前数据 (基线)

### hm40006 /health (改前)
`nvcf_pexec_models: ["deepseek_hm_nv","kimi_hm_nv"]`, `hm_model_tiers: ["deepseek_hm_nv","kimi_hm_nv"]`

### 容器 config.py (改前, 292 行)
- NVCF_PEXEC_MODELS: deepseek + kimi 两模型
- NV_MODEL_TIERS: ["deepseek_hm_nv","kimi_hm_nv"]
- NV_MODEL_IDS: 含 kimi_hm_nv
- MODEL_MAP: 含 kimi-k2.6/kimi/moonshotai/kimi-k2.6 等 6 个 kimi 别名
- _TIER_RR_KEYS / MODEL_INPUT_TOKEN_SAFETY: 含 kimi

### R273 暴露的行为问题 (改前)
直接 curl 40006 发 model=kimi-k2.6 → 容器映射到 kimi_hm_nv → DB mapped_model=kimi_hm_nv
(尽管 hermes 不发 kimi, 但容器侧路径存在, 配置不一致)

## 代码变化 (gateway/config.py)

| 区块 | 改前 | 改后 |
|---|---|---|
| docstring | R50.0 两模型 (deepseek+kimi) | R274 单模型 dsv4p, 注明清理历史 |
| NVCF_PEXEC_MODELS | deepseek + kimi | 仅 deepseek_hm_nv |
| NV_MODEL_TIERS | ["deepseek_hm_nv","kimi_hm_nv"] | ["deepseek_hm_nv"] |
| NV_MODEL_IDS | 2 模型 | 仅 deepseek_hm_nv |
| MODEL_MAP | deepseek 别名 + 6 个 kimi 别名 | deepseek 别名 + dsv4p 别名 |
| _TIER_RR_KEYS | 2 tier | 仅 deepseek |
| _OLD_RR_KEY_MAP | kimi 迁移到 hm_nv_kimi | kimi 迁移到 hm_nv_deepseek (保持久化RR状态) |
| MODEL_INPUT_TOKEN_SAFETY | 2 模型 | 仅 deepseek (131072) |
| 行数 | 292 | 276 |

保留 _OLD_RR_KEY_MAP 的 kimi 项 (改指向 hm_nv_deepseek) — rr_counter.json 可能持久化了
hm_nv_kimi 计数器, 删迁移项会孤立; 迁移到 deepseek 更安全。

## 备份

- 宿主源码: `/opt/cc-infra/proxy/hm-proxy/gateway/config.py.bak.R274.1782702374` (12634 字节)
- 容器内: `/app/gateway/config.py.bak.R274`

## 部署

改 gateway/*.py 必须 rebuild:
```
cd /opt/cc-infra && sudo docker compose build hm40006 && sudo docker compose up -d hm40006
```
容器 9s 内转 healthy。

## 验证 (真实请求 + 日志数据, 确认新配置真实生效)

### /health (改后)
`nvcf_pexec_models: ["deepseek_hm_nv"]`, `hm_model_tiers: ["deepseek_hm_nv"]`,
`hm_default_model: deepseek_hm_nv` ✅ (kimi 消失)

### 真实请求 (curl 打 127.0.0.1:40006, 改后)
| 请求 model | HTTP | 返回 model | mapped_model(DB) |
|---|---|---|---|
| deepseek_hm_nv | 200 | deepseek-ai/deepseek-v4-pro | deepseek_hm_nv ✅ |
| dsv4p (别名) | 200 | deepseek-ai/deepseek-v4-pro | deepseek_hm_nv ✅ |
| kimi-k2.6 (探测) | 200 | deepseek-ai/deepseek-v4-pro | **deepseek_hm_nv** ✅ |

→ 关键对比: R273 改前发 kimi-k2.6 → mapped_model=kimi_hm_nv;
   R276 改后发 kimi-k2.6 → mapped_model=deepseek_hm_nv。
   容器侧 kimi 路径彻底消失, 行为变化被 DB 实证。

### DB hm_requests (rebuild 后 10min)
- mapped_model 分布: 22/22 = 100% deepseek_hm_nv (零 kimi) ✅
- 最新5条 (含3种model名) 全部 mapped_model=tier_model=deepseek_hm_nv, upstream=nvcf_pexec, status=200 ✅
- tier attempts 空 (10min 全部一次成功, 无 fallback 触发) — 链路健康

## 红线确认 (不碰 40003)

- auth_to_api_40003 容器: Up 11 hours, 06-28 15:56 启动 (远早于本轮), /health 正常
  (glm5.1 → ms_uni41001), 本轮完全未触碰 ✅
- hm40006 容器: 06-29 03:06 (11:06 本地) rebuild, 本轮改动 ✅

## 与 HM2 对齐

HM2 的 hm40006 容器已于 R263 清成纯 glm5.1 (HM2 的目标模型); HM1 的 hm40006 容器
本轮清成纯 deepseek (HM1 的目标模型)。两台 hermes→40006 链路均无 kimi 死代码,
config.py 与各自 hermes config 一致。

## 回滚

```
sudo cp /opt/cc-infra/proxy/hm-proxy/gateway/config.py.bak.R274.1782702374 /opt/cc-infra/proxy/hm-proxy/gateway/config.py
cd /opt/cc-infra && sudo docker compose build hm40006 && sudo docker compose up -d hm40006
```

## ⏳ 本轮为授权破例自改, 不触发交替优化轮换。下轮由 timer 正常调度。
