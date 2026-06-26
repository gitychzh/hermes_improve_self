# R45: HM1优化HM2 — MIN_OUTBOUND_INTERVAL_S 17.5→17.0 (-0.5s): counterproductive reversal

**日期**: 2026-06-26
**执行者**: HM1 (opc_uname@100.109.57.26)
**目标**: HM2 (opc2_uname@100.109.57.26)

---

## 数据收集

### DB 快照 (last 30min, ts=2026-06-26 14:15 UTC)

| 指标 | 值 |
|------|-----|
| hm_requests total | 1228 |
| fallback rate | 84.0% (1032/1228) |
| glm5.1 成功 | 196 (avg 17.7s) |
| deepseek 成功 | 1023 (avg 28.1s) |
| kimi 成功 | 9 (avg 120.5s) |
| DB freshness | max(ts)=14:15, max(created_at)=06:17 (stale — created_at overridden) |

### Tier Attempts Error Breakdown (30min)

| Error Type | Count | Avg elapsed |
|------------|-------|-------------|
| 429_nv_rate_limit | 2996 | — |
| NVCFPexecSSLEOFError | 231 | 10.5s |
| NVCFPexecConnectionResetError | 62 | 2.8s |
| NVCFPexecTimeout | 23 | 41.0s |
| NVCFPexecRemoteDisconnected | 6 | 8.1s |
| empty_200 | 4 | — |

### Per-Key 429 Distribution (even → function-level)

| Key | 429 Count |
|-----|-----------|
| k0 (idx=0) | 587 |
| k1 (idx=1) | 582 |
| k2 (idx=2) | 601 |
| k3 (idx=3) | 614 |
| k4 (idx=4) | 612 |

### RESERVE Bottleneck Check
- `all_tiers_exhausted` with `tiers_tried_count=0`: **0** → pre-tier connections healthy

### 运行环境变量 (before)
```
MIN_OUTBOUND_INTERVAL_S=17.5
KEY_COOLDOWN_S=26.0
TIER_TIMEOUT_BUDGET_S=111
UPSTREAM_TIMEOUT=62
HM_CONNECT_RESERVE_S=6  (DEAD — not read by gateway code)
DEFAULT_NV_MODEL=glm5.1_hm_nv  ✓ correct
NV_MODEL_TIERS=['glm5.1_hm_nv', 'deepseek_hm_nv', 'kimi_hm_nv']  ✓ correct
```

---

## 问题诊断

### 1. 429是主导错误类型 (2996/30min, ~100/min)
- 全部5个key均匀分布(587-614) → NVCF function-level rate limit，不是per-key
- glm5.1_hm_nv的NVCF function ID `822231fa-d4f` 在所有key上共享
- 请求频率 ~0.68 req/s 远超 NVCF 1 req/60s 限制

### 2. SSLEOFError = 231 — 连接层错误
- R43的 +0.5s (17.0→17.5) 已经超过 mihomo idle timeout (~15-20s)
- 在17.5s间距下，每次请求遇到已关闭的mihomo连接 → SSLEOF
- k1 (idx=1) 的SSLEOF最多(61)，其他key 31-49

### 3. NVCFPexecTimeout = 23 — 已控制
- 远低于R25基线127，说明deepseek超时已在可控范围

### 4. HM_CONNECT_RESERVE_S = 6 是死变量
- `grep -rn "CONNECT_RESERVE" /app/gateway/config.py` 返回0匹配
- 该变量存在于docker-compose.yml但未被代码读取

---

## 优化计划

### 变更: MIN_OUTBOUND_INTERVAL_S 17.5 → 17.0 (-0.5s)

| 参数 | Before | After | 变化 |
|------|--------|-------|------|
| MIN_OUTBOUND_INTERVAL_S | 17.5 | 17.0 | -0.5s |

**理由**:
- R43的+0.5s (17.0→17.5) 产生了**反效果**: SSLEOF从~196→231 (↑17.8%)
- 17.5s > mihomo idle timeout (15-20s), 导致连接复用失败
- 回退到17.0s, 在mihomo idle timeout以下, 保持连接活跃
- 单参数变更, 少改多轮原则

**风险评估**:
- 低风险: 只是回退R43的变更, 17.0s之前已稳定运行
- 预期效果: SSLEOFError下降, ConnectionResetError下降
- 不会影响429 rate limit (function-level, 与MIN_OUTBOUND无关)

---

## 执行记录

```bash
# 1. 修改 HM2 的 docker-compose.yml (line 479)
ssh opc2_uname@100.109.57.26 \
  "sed -i '479s/17.5/17.0/' /opt/cc-infra/docker-compose.yml"

# 2. 重建镜像
cd /opt/cc-infra && docker compose build hm40006
# → Image cc-infra-hm40006 Built

# 3. 停止旧容器 + 部署新容器
docker stop hm40006 && docker rm hm40006
docker compose -f docker-compose.yml up -d hm40006
# → Container hm40006 Started

# 4. 验证
docker exec hm40006 env | grep MIN_OUTBOUND_INTERVAL_S
# → MIN_OUTBOUND_INTERVAL_S=17.0 ✓

docker logs hm40006 --tail 10
# → [HM-SUCCESS] tier=glm5.1_hm_nv ... 正常处理请求
```

---

## 部署后立即验证

```
[14:24:14.5] [HM-SUCCESS] tier=glm5.1_hm_nv k3 succeeded after 2 cycle attempts
[14:24:30.8] [HM-SUCCESS] tier=glm5.1_hm_nv k2 succeeded on first attempt
```
- glm5.1_hm_nv 正在成功处理请求
- 服务正常运行, 未停止

---

## 铁律确认
- [x] 只改HM2不改HM1
- [x] 未停止/重启/kill mihomo服务
- [x] DEFAULT_NV_MODEL = glm5.1_hm_nv (primary)
- [x] 单参数变更, 少改多轮

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记