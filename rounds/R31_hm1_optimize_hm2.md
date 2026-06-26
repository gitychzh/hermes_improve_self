# R31: HM1优化HM2

**日期**: 2026-06-26 09:17 UTC  
**执行者**: HM1 (opc_uname)  
**目标**: HM2 hm40006 (opc2_uname@100.109.57.26)

---

## 数据采集

### Docker日志 (最近100行)

| 指标 | 数值 |
|------|------|
| HM-TIER-FAIL | 8 |
| HM-FALLBACK | 20 |
| HM-FALLBACK-SUCCESS | 10 |
| ConnectionResetError | 1 |
| SSLEOFError | 1 |
| NVCFPexecTimeout | 0 |

### 错误类型分布 (最近30min DB)

| 错误类型 | 数量 | 备注 |
|----------|------|------|
| glm5.1_hm_nv 429_nv_rate_limit | 2818 | 函数级429，全键均匀(5×5=25) |
| deepseek_hm_nv NVCFPexecTimeout | 127 | avg=30.6s, max=55.7s |
| glm5.1_hm_nv SSLEOFError | 56 | k3=22(最多), 端口级 |
| glm5.1_hm_nv ConnectionResetError | 20 | 单键级 |
| deepseek_hm_nv SSLEOFError | 13 | 端口级 |
| glm5.1_hm_nv NVCFPexecTimeout | 10 | |
| kimi_hm_nv NVCFPexecTimeout | 8 | |

### 关键诊断

| 检查项 | 结果 | 说明 |
|--------|------|------|
| all_tiers_exhausted(tiers_tried=0) | **12** | 预层连接失败，RESERVE瓶颈 |
| 429分布 | k1=k2=k3=k4=k5=5/200行 | **函数级**429，非键级 |
| glm5.1直接成功率 | 1/10 (10%) | 90%走deepseek回退 |
| DB last ts | 当前 | 数据新鲜，使用ts过滤 |

### 当前配置 (hm40006)

| 参数 | 运行值 | Compose值 | 一致? |
|------|--------|-----------|-------|
| UPSTREAM_TIMEOUT | 60 | 60 | ✅ |
| TIER_TIMEOUT_BUDGET_S | 109 | 109 | ✅ |
| MIN_OUTBOUND_INTERVAL_S | 12.0 | 12.0 | ✅ |
| KEY_COOLDOWN_S | 30.0 | 30.0 | ✅ |
| HM_CONNECT_RESERVE_S | **3→4** | 3→4 | ⚠️ R31变更 |
| NV_MODEL_TIERS | ['glm5.1_hm_nv','deepseek_hm_nv','kimi_hm_nv'] | 代码内 | ✅ |
| DEFAULT_NV_MODEL | glm5.1_hm_nv | 代码内 | ✅ |
| HM_NUM_KEYS | 5 | 5 | ✅ |

---

## 问题诊断

**根因**: `all_tiers_exhausted` with `tiers_tried_count=0` = 12次/30min

这些请求在SOCKS5+SSL握手阶段就失败了，从未尝试任何NVCF密钥。`HM_CONNECT_RESERVE_S=3`的预留时间不够——SOCKS5+SSL连接需要1-2s建立，但在高负载或网络抖动时3s余量不足。

429是函数级速率限制（所有5键均匀受429），无法通过配置参数突破。回退到deepseek是预期行为，不在本轮优化范围内。

---

## 优化计划

| # | 参数 | 变更前 | 变更后 | 理由 |
|---|------|--------|--------|------|
| 1 | HM_CONNECT_RESERVE_S | 3 | **4** (+1s) | 12次/30min预层连接失败; +1s余量减少SOCKS5+SSL握手超时 |

**风险**: 低 — 连接建立1-2s，4s预留仍在安全范围。仅增加1s/请求的开销（失败连接），但减少预层完全失败。

---

## 执行记录

```bash
# 1. 备份Compose
cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.R30

# 2. 修改HM_CONNECT_RESERVE_S (line 510, hm40006 section only)
sed -i '510s|HM_CONNECT_RESERVE_S: "3"|HM_CONNECT_RESERVE_S: "4"  # R31: ...|' /opt/cc-infra/docker-compose.yml

# 3. 停止旧容器
docker stop hm40006 && docker rm hm40006

# 4. 重建镜像
cd /opt/cc-infra && docker compose build hm40006

# 5. 部署新容器
docker compose -f docker-compose.yml up -d --force-recreate hm40006
```

## 部署验证

| 检查项 | 结果 |
|--------|------|
| docker exec hm40006 env \| grep HM_CONNECT_RESERVE_S | `HM_CONNECT_RESERVE_S=4` ✅ |
| 容器运行 | Running ✅ |
| 日志输出 | 正常(429+回退模式持续，预期行为) ✅ |

---

## 预期效果

- `all_tiers_exhausted(tiers_tried=0)` 从12次/30min → 目标<8次/30min
- 预层SOCKS5+SSL连接成功率提升
- glm5.1直接成功率: 不变(429是函数级，无法配置突破)
- 回退到deepseek的延迟: 不变

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记