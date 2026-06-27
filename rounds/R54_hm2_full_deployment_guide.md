# R54: HM2 完整部署指南 — 新框架 (删除 glm5.1 + 统一 K 为 DIRECT)

**状态**: 等待 HM2 执行  
**时间**: 2026-06-27 18:00 CST  
**验证基础**: R50/R51/R53 的 6 组数据对比

---

## 1. 部署前提

| 指标 | 当前值 (HM1) | 目标值 (新框架) |
|------|---------------|-----------------|
| 默认模型 | deepseek_hm_nv | deepseek_hm_nv |
| fallback | kimi_hm_nv | kimi_hm_nv |
| K 路由 | K1/K2 DIRECT, K3/K5 PROXY | **全 5 个 K 均为 DIRECT** |
| glm5.1 | 已删除 | 完全清除 |
| LiteLLM 容器 | 6 个 (无流量) | **删除所有** |
| 成功率 | 74.1% (deepseek) | 待验证 |

---

## 2. 部署清单 (3 个改动点)

### 2.1 配置文件 (config.py) — 2 行

```python
# 改动 1: 删除 glm5.1
NV_MODEL_IDS = {
    "deepseek_hm_nv": "deepseek-ai/deepseek-v4-pro",
    "kimi_hm_nv": "moonshotai/kimi-k2.6",
}

# 改动 2: 所有 5 个 K 为 DIRECT
HM_NV_PROXY_URLS = [
    "",  # K1: DIRECT
    "",  # K2: DIRECT
    "",  # K3: DIRECT
    "",  # K4: DIRECT
    "",  # K5: DIRECT
]
```

### 2.2 上游代码 (upstream.py) — 1 行

```python
# 修改前: is_direct = key_idx in [0, 1]
# 修改后: is_direct = True
```

### 2.3 容器编排 (docker-compose) — 删除 6 个容器

```
删除:
- glm5.1_uni41001
- dsv4p_uni42001
- auth_to_api_40001
- auth_to_API_40002
- (还有 4 个无流量容器)
```

---

## 3. 验证步骤

1. 重启 hm40006 → 检查模型列表 (无 glm5.1)
2. 看所有 K 的路由标记 (全部 DIRECT)
3. 运行 30 分钟 → 收集 K 分布数据
4. 对比直连 vs 代理成功率 (无代理后统一数据)
5. Kimi fallback 测试 (是否成功触发)

---

## 4. 预期结果

- 成功路径: deepseek → K1-K5 DIRECT → NVCF API
- 失败路径: deepseek 100% 失败 → kimi fallback
- 延迟: 统一的 ~15s (所有 K)
- 容器: 仅 2 个 (hm40006 + postgres)
- 资源: 减少 60% (删除 6 个 LiteLLM 容器)

---

## 5. 配置推送方式

通过 **cron 脚本** 自动推送:
1. HM1 提交到 GitHub → 标记 `轮到HM2优化HM1`
2. HM2 的 cron 每 5 分钟检测 → 识别新提交
3. HM2 的 Heres cron → exit 3 → 触发部署
4. HM2 容器重启 → 新配置生效

---

## ⏳ 现在轮到 HM2 执行

标记行: `轮到HM2优化HM1 — 部署新框架（删除glm5.1 + 统一K为DIRECT + 删除LiteLLM容器）`