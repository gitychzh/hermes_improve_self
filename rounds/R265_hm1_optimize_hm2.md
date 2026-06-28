# R265: HM1→HM2 — 去掉 hermes MS fallback, 收敛为纯 NV glm5.1 单链路 — 单轮清理 (清理批次)

**回合类型**: 清理 (单主题: hermes 链路收敛)
**方向**: HM1 (opc_uname) → HM2 (opc2_uname)
**时间**: 2026-06-29 01:34 UTC
**批次**: 与 R263/R264 同属 HM2 模型链路清理批次, 人工授权连续提交, 跳过交替
**原则**: 干净整洁、工程化、便于长期调参维护 — 铁律:只改HM2不改HM1

## 摘要

HM2 hermes `config.yaml` 保留着 `litellm-local-ms` (40003, MS glm5.1 baseline) 作为
fallback provider。R263 已把 hm40006 收敛为单一 NV glm5.1, MS 中间层不在热路径,
该 fallback 与"纯 NV 单链路"目标不符且增加维护面。本轮删除 `providers.litellm-local-ms`
段与 `fallback_providers` 段, 让 hermes 只剩 NV glm5.1_hm_nv @ 40006 一条链。
代价: NV 全 key 失败时 hermes 直接报错, 无 MS 兜底 (用户已确认接受)。

## 改前数据

### config.yaml (改前, 12509B)
```yaml
providers:
  litellm-nv-hm: {... 40006 glm5.1_hm_nv ...}
  litellm-local-ms:      # ← 删除
    base_url: http://127.0.0.1:40003/v1
    default_model: glm5.1_hm_ms
fallback_providers:      # ← 删除
- litellm-local-ms
```

### 链路现状 (R263/R264 后)
- hm40006: 单模型 glm5.1_hm_nv, NVCF pexec function 822231fa (ai-glm5_1)
- /health: nvcf_pexec_models=["glm5.1_hm_nv"], default=glm5.1_hm_nv
- 40003 (MS) 容器仍运行但已不在 hermes 热路径

## 变化

| 区块 | 改前 | 改后 |
|---|---|---|
| `providers.litellm-local-ms` | 存在 (40003 MS baseline) | 删除 |
| `fallback_providers` | `[- litellm-local-ms]` | 删除 (整个 key) |
| 文件 | 12509B / 含 fallback | 12329B / 纯 NV 单链路 |

保留: `providers.litellm-nv-hm` (40006), `model.default=glm5.1_hm_nv`,
`model_aliases.glm5.1 → glm5.1_hm_nv @ 40006`。

## 备份

- `~/.hermes/config.yaml.bak.R265.1782668039` (12509B, 改前完整副本)

## 验证

- [x] Python yaml.safe_load + 断言: 无 litellm-local-ms, 无 fallback_providers, 主 provider 在
- [x] `hermes config check` 无报错
- [x] `model_aliases.glm5.1` 保留指向 40006/glm5.1_hm_nv
- [x] hermes gateway 重启: PID 2440944 (01:38:12 CST), active (running)
- [x] `hermes gateway status` → ✓ running
- [x] 端到端: POST 40006/v1/chat/completions model=glm5.1_hm_nv → 200, content="ok"
- [x] YAML 注释无丢失 (原文件本无注释, grep ^# 改前改后均=0)

## 风险与回滚

- 代价: NV 全 key 失败时 hermes 无 MS 兜底, 直接报错 (用户已确认接受纯 NV 单链路)。
- yaml.dump 重写: 已校验 top keys 与 model_aliases 完整, hermes config check 通过。
- 回滚: `cp ~/.hermes/config.yaml.bak.R265.1782668039 ~/.hermes/config.yaml && hermes gateway restart`

## ⏳ 轮到HM2优化HM1
