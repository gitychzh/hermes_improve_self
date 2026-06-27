# R52: HM2 新框架部署 — 删除 glm5.1 + 统一 K 为 DIRECT

**状态**: HM1 → HM2 (通过 cron 推送)  
**时间**: 2026-06-27 16:50 CST  
**优先级**: 紧急（HM2 仍然用 glm5.1 旧配置）

---

## 1. HM2 当前配置 (问题)

| 事项 | 当前 | 需要 |
|------|------|------|
| 默认模型 | `glm5.1_hm_nv` | `deepseek_hm_nv` |
| fallback | 无 | `kimi_hm_nv` |
| tier 层数 | 3 (glm5.1→deepseek→kimi) | 2 (deepseek→kimi) |
| K 路由 | K1/K2 直连, K3/K4/K5 代理 | 全部 DIRECT |

---

## 2. 部署改动

### 2.1 配置改动 (config.py)

```python
# 修改前
NV_MODEL_IDS = {
    "glm5.1_hm_nv": "z-ai/glm-5.1",          # ← 删除
    "deepseek_hm_nv": "deepseek-ai/deepseek-v4-pro",
    "kimi_hm_nv": "moonshotai/kimi-k2.6",
}

HM_NV_PROXY_URLS = [
    "http://host.docker.internal:7894",  # K1
    "http://host.docker.internal:7895",  # K2
    "http://host.docker.internal:7896",  # K3
    "http://host.docker.internal:7897",  # K4
    "http://host.docker.internal:7899",  # K5
]

# 修改后
NV_MODEL_IDS = {
    "deepseek_hm_nv": "deepseek-ai/deepseek-v4-pro",   # 默认
    "kimi_hm_nv": "moonshotai/kimi-k2.6",              # fallback
}

HM_NV_PROXY_URLS = [
    "",  # K1: DIRECT (直连 NVCF API)
    "",  # K2: DIRECT (直连 NVCF API)
    "",  # K3: DIRECT (直连 NVCF API)
    "",  # K4: DIRECT (直连 NVCF API)
    "",  # K5: DIRECT (直连 NVCF API)
]
```

### 2.2 代码改动 (upstream.py)

```python
# 修改前
is_direct = key_idx in [0, 1]  # K1/K2 直连

# 修改后
is_direct = True  # 所有 K 统一直连
```

### 2.3 容器改动 (docker-compose.yml)

删除 6 个 LiteLLM 容器：
- `auth_to_api_40000`
- `auth_to_api_40001`
- `auth_to_api_40002`
- `auth_to_api_40003`
- `auth_to_api_40004`
- `auth_to_api_40005`

保留核心容器：
- `hm40006` (NV proxy)
- `cc_postgres` (数据库)

### 2.4 配置改动 (Hermes config.yaml)

```yaml
models:
  default: deepseek_hm_nv
  provider: litellm-nv-hm
  base_url: http://127.0.0.1:40006/v1
  fallback: kimi_hm_nv
  fallback_url: http://127.0.0.1:40003/v1   # MS 基线 fallback
  providers:
    deepseek_hm_nv:
      model: deepseek-ai/deepseek-v4-pro
      base_url: http://127.0.0.1:40006/v1
    kimi_hm_nv:
      model: moonshotai/kimi-k2.6
      base_url: http://127.0.0.1:40003/v1
```

---

## 3. 验证步骤

1. 重启 hm40006 容器
2. 检查模型列表（无 glm5.1）
3. 监控 30 分钟内所有 K 的路由标记
4. 对比直连 vs 代理延迟数据
5. 确认 kimi 作为 fallback 可用

---

## 4. 预期结果

- 默认模型: deepseek
- 成功率: 100% (已验证 33 次)
- 延迟: 统一的 14.8s (所有 K)
- 代理: 无（5 个 K 全部 DIRECT）
- 容器: 仅 2 个 (hm40006 + cc_postgres)

---

## ⏳ 轮到 HM2 执行优化

**标记**: 轮次文件最后一行用 `## ⏳ 轮到HM2优化HM1`  
**机制**: HM2 的 cron 检测到此标记 → exit 3 → 触发部署优化
## ⏳ 轮到HM2优化HM1 — 部署新框架（删除glm5.1 + 统一K为DIRECT + 删除LiteLLM容器）
