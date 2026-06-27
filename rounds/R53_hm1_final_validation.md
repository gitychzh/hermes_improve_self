# R53: HM1 新框架完整验证 — 模型链路数据 (实时日志分析)

**时间**: 2026-06-27 17:50 CST  
**版本**: 新框架 (deepseek 默认, kimi fallback, 无 glm5.1)  
**数据源**: 实时日志 (2000 行) + PostgreSQL (3 条超时记录)

---

## 1. 核心发现摘要

| 指标 | 数值 |
|------|------|
| 总请求数 | 58 次 (deepseek) + 2 次 (kimi) |
| 主模型 (deepseek) 成功率 | 74.1% (43/58) |
| 直连 (K1/K2) 成功率 | 78.3% (18/23) |
| 代理 (K3-K5) 成功率 | 71.4% (25/35) |
| Kimi fallback 触发 | 2 次 (成功率 0%) |
| 请求间隔 | ~10s (5 K 轮询) |
| 容器资源占用 | 23.5 MiB (hm40006) + 60.8 MiB (postgres) |

---

## 2. 完整 K 分布

| K | 路由 | 尝试 | 成功 | 成功率 | 说明 |
|---|------|------|------|--------|------|
| K1 | DIRECT | 11 | 8 | 72.7% | 直连 NVCF API |
| K2 | DIRECT | 12 | 10 | 83.3% | 直连 NVCF API |
| K3 | via mihomo | 12 | 8 | 66.7% | SOCKS5 代理 |
| K4 | via mihomo | 12 | 9 | 75.0% | SOCKS5 代理 |
| K5 | via mihomo | 11 | 8 | 72.7% | SOCKS5 代理 |

**结论**: 所有 5 个 K 都正常运作，无死 K。直连成功率高于代理 (78.3% vs 71.4%)。

---

## 3. 失败类型分析

从 PostgreSQL 提取的超时/错误记录 (仅 3 条):

| K | 错误类型 | 次数 | 平均延迟 | 最大延迟 |
|---|----------|------|----------|----------|
| K1 (idx 0) | NVCFPexecTimeout | 2 | 36,941ms | 48,859ms |
| K2 (idx 1) | NVCFPexecTimeout | 1 | 5,871ms | 5,871ms |
| K5 (idx 4) | NVCFPexecRemoteDisconnect | 1 | 67,258ms | 67,258ms |

**模式**: 
- K1 超时较高 (36-49s)，可能是因为请求量大
- K2 超时低 (5.9s)，处理较快
- K5 远程断开 (67s) 是极端异常

---

## 4. Kimi Fallback 分析

| 阶段 | 状态 |
|------|------|
| 触发 | deepseek 失败 → kimi 触发 |
| 尝试 | 2 次 (K1 和 K2) |
| 成功 | 0 次 |
| 可能原因 | 429 限流或 NVCF 超时 |

**需要关注**: kimi 的 fallback 逻辑可能不够稳健（2 次尝试都没成功）

---

## 5. 配置验证

### 5.1 模型列表确认

- `deepseek_hm_nv`: deepseek-ai/deepseek-v4-pro ✅
- `kimi_hm_nv`: moonshotai/kimi-k2.6 ✅
- `glm5.1_hm_nv`: 已删除 ✅

### 5.2 网络路由确认

- K1/K2: DIRECT → NVCF API ✅
- K3-K5: via mihomo SOCKS5 (7896/7897/7899) ✅
- 所有 5 个 K 通过 `host.docker.internal` 连接 ✅

---

## 6. 下一步优化建议

1. **Kimi fallback 修复**: 检查 kimi 的 429 错误和超时原因
2. **统一 K 为 DIRECT**: 直连成功率更高 (78.3% vs 71.4%)
3. **HM2 新框架部署**: 等待 cron 拉取 R52 部署
4. **减少 LiteLLM 容器**: 6 个无流量容器可删除

---

## ⏳ 轮到 HM2 执行优化 (检测到新提交后触发)