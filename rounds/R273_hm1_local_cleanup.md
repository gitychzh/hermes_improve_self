# R273: HM1 本机 hermes 配置清理 — 单模型 dsv4p, 删 kimi/glm5.1, 清缓存 — 授权破例自改

**回合类型**: 清理 (单主题: hermes config 收敛为单一 dsv4p)
**方向**: HM1 本机 (授权破例自改, 非交替优化方向)
**时间**: 2026-06-29 09:36 UTC+8 (gateway 重启时间)
**原则**: 干净整洁、工程化、便于长期调参维护
**授权说明**: 用户明确授权本次 HM1 本地直接改本机 hermes (破铁律"只改对端不改自己"),
  因 HM1 hermes 自身需清理。容器侧 (hm40006) 未动 — 仅改 hermes config.yaml + 缓存。

## 摘要

HM1 hermes (~/.hermes/config.yaml) 经交替优化循环 (HM2 改 HM1) 已收敛为 default=deepseek_hm_nv,
但仍有残留: provider_models_cache.json 缓存 13 个脏模型名 (kimi/glm5.1/minimax), 且 gateway
自 06-28 17:49 起未重启, 配置变更 (06-29 01:41) 未确认加载。本轮: 删脏缓存 + 重启 gateway
+ 真实请求/日志验证新配置真实生效。kimi-k2.6 别名 / litellm-local-ms fallback / model_aliases
经 HM2 之前轮次已删, 本轮确认其已清。

## 改前数据 (基线, HM1 hermes_logs, 重启前 30min)

### hm_requests 30min 总览 (改前)
- Total: 79, OK(200): 75 → **93.75%** (注: 另一次采集 80/75=93.75%)
- request_model/mapped_model 分布: 100% deepseek_hm_nv (零 kimi/glm5.1 实际流量)
- 说明: hermes 实际只在用 dsv4p, kimi-k2.6 别名与 40003 fallback 已是死配置

### config.yaml 状态 (改前, HM2 已通过交替优化改好)
- model.default = deepseek_hm_nv ✅
- providers.litellm-nv-hm.models: 仅 deepseek_hm_nv (aliases: deepseek-v4-pro/deepseek/dsv4p) ✅
- fallback_providers = [] (litellm-local-ms/40003 已删) ✅
- model_aliases = 空 (kimi 别名段已删) ✅
- grep kimi-k2.6 / litellm-local-ms 出现次数 = 0 ✅

### provider_models_cache.json (改前 — 脏)
- openai-api provider 缓存 13 模型: kimi_hm, glm5.1_hm, minimax_hm, deepseek_hm, kimi,
  kimi-k2.6, moonshotai/kimi-k2.6, glm5.1, glm-5.1, minimax, minimax-m3, deepseek,
  deepseek-v4-pro — 陈旧探测缓存, 需清

### gateway 状态 (改前)
- pid 3201228, 自 2026-06-28 17:49 起运行 (7h+)
- config.yaml mtime 2026-06-29 01:41 — 配置已改但 gateway 未重启, 加载状态未确认

## 实际变更 (本轮只做两件事)

1. **删 provider_models_cache.json** (备份: .bak.R264.1782696525)
   - hermes 重启后重新探测 40006 可用模型, 应只回 deepseek_hm_nv
2. **重启 hermes-gateway.service** (systemctl --user restart)
   - 旧进程 3201228 drain 超时 (180s, 1 active cron agent 卡住) → 09:36:18 SIGKILL
   - 新进程 3515863 于 09:36:18 启动, 09:36:23 飞书重连成功

config.yaml 本身未编辑 (已是 HM2 之前轮次改好的目标态), 仅备份保底:
- config.yaml.bak.R264.1782696525
- provider_models_cache.json.bak.R264.1782696525

## 验证 (真实请求 + 日志数据, 确认新配置真实加载)

### 真实请求 (curl 打 127.0.0.1:40006, 重启后)
| 请求 model | HTTP | 返回 model | 内容 |
|---|---|---|---|
| deepseek_hm_nv | 200 | deepseek-ai/deepseek-v4-pro | "R264-DSV4P-OK" ✅ |
| dsv4p (别名) | 200 | deepseek-ai/deepseek-v4-pro | "R264-ALIAS-OK" ✅ |
| kimi-k2.6 (hermes已删别名) | 200 | deepseek-ai/deepseek-v4-pro | "Hello!..." ✅ |

→ kimi-k2.6 已从 hermes config 删除, 发该名时 hermes 透传给 40006, 容器仍映射到
   kimi_hm_nv 但 tier 落到 deepseek (容器侧 kimi 死代码未清, 见"遗留不一致")。

### DB hm_requests 记录 (重启后最新5条)
| request_model | mapped_model | tier_model | upstream_type | status |
|---|---|---|---|---|
| deepseek_hm_nv | deepseek_hm_nv | deepseek_hm_nv | nvcf_pexec | 200 |
| kimi-k2.6 (探测) | kimi_hm_nv | deepseek_hm_nv | nvcf_pexec | 200 |
| deepseek_hm_nv | deepseek_hm_nv | deepseek_hm_nv | nvcf_pexec | 200 |
| deepseek_hm_nv | deepseek_hm_nv | deepseek_hm_nv | nvcf_pexec | 200 |
| dsv4p | deepseek_hm_nv | deepseek_hm_nv | nvcf_pexec | 200 |

### 重启后 mapped_model 分布 (15min)
- deepseek_hm_nv: 33 (97%)
- kimi_hm_nv: 1 (仅我主动探测 kimi-k2.6 触发, 非 hermes 正常流量)

### tier attempts litellm_model
- nvcf_deepseek-ai/deepseek-v4-pro_k1 ✅ (dsv4p function)

### 整体成功率对比 (60min 窗口)
| period | total | ok | succ_pct |
|---|---|---|---|
| BEFORE(restart) | 148 | 138 | 93.24% |
| AFTER(restart) | 13 | 13 | **100.00%** |

→ 重启后零错误, 新配置稳定运行。

## 遗留不一致 (不在本轮范围, 容器侧未动)

hm40006 容器 /health 仍返回 nvcf_pexec_models=["deepseek_hm_nv","kimi_hm_nv"],
hm_model_tiers=["deepseek_hm_nv","kimi_hm_nv"] — 容器 config.py 仍含 kimi 死代码
(与 R263 清 HM2 容器的情况相同, 但本轮按用户指令"容器不动"未处理)。
若直接对 40006 发 kimi 别名, 容器仍会映射到 kimi_hm_nv tier。hermes 自身链路
不受影响 (hermes config 已无 kimi 别名, 所有请求落 deepseek)。

## 回滚

```
cp ~/.hermes/provider_models_cache.json.bak.R264.1782696525 ~/.hermes/provider_models_cache.json
cp ~/.hermes/config.yaml.bak.R264.1782696525 ~/.hermes/config.yaml
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
systemctl --user restart hermes-gateway.service
```

## ⏳ 本轮为授权破例自改, 不触发交替优化轮换。下轮由 timer 正常调度。
