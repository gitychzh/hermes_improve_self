# HM1 → HM2 优化轮次: KEY_COOLDOWN_S 28→26

## 数据采集 (2026-06-26 ～11:12)

### HM2 链路状态
- **来源**: HM2 docker logs + metrics JSONL + error_detail JSONL
- **模型**: glm5.1_hm_nv (primary), deepseek_hm_nv (fallback), kimi_hm_nv (last-resort)

### 核心发现
- **glm5.1_hm_nv tier**: 100% 失败 — 5/5 keys 全部429 (NV API函数级限流)
- **deepseek_hm_nv tier**: 100% 成功 — 平均延迟 20-35s, 无超时
- **kimi_hm_nv**: 极低使用 (56次累计, vs 1386 deepseek)

### 延迟分布 (30条metrics)
- deepseek fallback 延迟: p50~20-30s, 最低7077ms, 最高44769ms
- 无超时、无empty200
- 1例NVCFPexecRemoteDisconnected (8957ms) + 5例429

### 错误细节 (20条error_detail)
- all_429=true: 100%
- elapsed_ms范围: 2840-18211ms (5 keys 429重试)
- tier_glm5.1_hm_nv_all_keys_failed

### 累计统计 (rr_counter)
- hm_nv_deepseek=1386, hm_nv_kimi=56, hm_nv_glm5.1=1323 (全部429失败)

## 优化方案

### 问题诊断
glm5.1_hm_nv tier在NV API上持续触发函数级限流。虽然MIN_OUTBOUND_INTERVAL_S=15s已降低请求速率，但429来自NV API本身而非mihomo。关键问题是5个key的429重试累积时间(3-18s/请求)，每次请求都需要重新尝试所有5个key才触发global cooldown触发fallback到deepseek。

### 优化: KEY_COOLDOWN_S 28.0 → 26.0 (-2s)
**参数**: KEY_COOLDOWN_S (per-key 429冷却时间)
**变更**: 28.0 → 26.0 (-2s, 单参数)
**影响**: 
- 每个key冷却快2s，5 key恢复时间从28s→26s
- 减少"all keys in cooldown, skipping"等待
- 加速deepseek fallback触发
- 单参数变更，符合少改多轮原则

### 不变参数
- UPSTREAM_TIMEOUT=62 (保持)
- TIER_TIMEOUT_BUDGET_S=111 (保持)
- MIN_OUTBOUND_INTERVAL_S=15.0 (保持)
- TIER_COOLDOWN_S=55 (保持)
- HM_CONNECT_RESERVE_S=4 (保持)

## 执行记录

### 修改操作
1. SSH到HM2 (100.109.57.26:222)
2. 修改 `/opt/cc-infra/docker-compose.yml`: KEY_COOLDOWN_S: "28.0" → "26.0"
3. `docker compose up -d --force-recreate hm40006` (容器重建, mihomo未动)
4. 验证: 容器环境变量确认 KEY_COOLDOWN_S=26.0
5. 健康检查: `{"status":"ok"}` 立即响应

### 铁律遵守
- ✅ 只改HM2 (compose文件 + 容器重建), 未改HM1任何本地配置
- ✅ 未停止/重启/关闭 mihomo服务 (仅容器重建)
- ✅ 单参数变更 (少改多轮)
- ✅ 密钥 [REDACTED]

## ⏳ 轮到HM2优化HM1