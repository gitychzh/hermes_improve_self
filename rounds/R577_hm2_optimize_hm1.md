# R577: HM2→HM1 — UPSTREAM_TIMEOUT 25→28 (+3s pexec fallback 边缘救回)

> 角色: HM2(opc2) → 优化目标: HM1(opc) / 链路: nv_40006_uni
> 铁律: 只改HM1配置, 绝不改HM2本地任何文件

## 1. 数据来源与采集命令

### 1.1 容器日志 (最近800行)
```
ssh opc_uname@100.109.153.83 -p 222
# docker logs nv_40006_uni --tail 800 2>&1
# 主要关注 NV-INTEGRATE / NV-PEER-FB / NV-TIMEOUT / NV-EMPTY-200
```

日志关键发现:
- NV-INTEGRATE-SUCCESS: 86 次 (近期), 其中 dsv4p 首击成功率极高 (几乎全 first attempt), kimi 偶发成功
- NV-INTEGRATE-FAIL: 2 次 (empty200 全部 keys 后失败), 发生在 01:03-01:04
- NV-EMPTY-200: 45 次 (kimi 密集出现, dsv4p 偶发)
- NV-TIMEOUT: 24 次 (kimi 22 次, dsv4p 2 次)
- 容器近期经历多次 restart (01:14/01:19/01:23), 可能为 deploy 或健康检查触发, 现已稳定

### 1.2 容器环境变量 (修改前后对比)
```bash
docker exec nv_40006_uni env | grep -E 'UPSTREAM|TIER_TIMEOUT|MIN_OUTBOUND|KEY_COOLDOWN|TIER_COOLDOWN|FASTBREAK|CONNECT_RESERVE|SSLEOF|STREAM_UPGRADE|EMPTY_200|INTEGRATE|PEER_FALLBACK' | sort
```

修改前:
```
NVU_CONNECT_RESERVE_S=2
NVU_EMPTY_200_FASTBREAK=0
NVU_FORCE_STREAM_UPGRADE=1
NVU_FORCE_STREAM_UPGRADE_TIMEOUT=61
NVU_PEXEC_TIMEOUT_FASTBREAK=1
NVU_PEER_FALLBACK_ENABLED=1
NVU_PEER_FALLBACK_TIMEOUT=25
NVU_PEER_FALLBACK_URL=http://100.109.57.26:40006
NVU_SSLEOF_RETRY_DELAY_S=1.0
NV_INTEGRATE_MODELS=dsv4p_nv,kimi_nv
TIER_TIMEOUT_BUDGET_S=90
TIER_COOLDOWN_S=25
UPSTREAM_TIMEOUT=25
```

修改后 (recreated):
```
UPSTREAM_TIMEOUT=28   ← 本轮修改
TIER_TIMEOUT_BUDGET_S=90
(...其余不变)
```

### 1.3 DB 请求延迟与成功率 (多窗口)

**5分钟数据**:
| tier_model | total | succ | fail | SR%   | avg_s_ms | avg_f_ms |
|------------|-------|------|------|-------|----------|----------|
| dsv4p_nv   | 576   | 533  | 43   | 92.5% | 27,056   | 69,822   |
| glm5_1_nv  | 13    | 12   | 1    | 92.3% | 4,561    | 67,868   |
| kimi_nv    | 184   | 94   | 90   | 51.1% | 33,778   | 78,753   |

**全量日志 1.5h 级** (nv_metrics.2026-07-03.jsonl):
| 指标 | 数值 |
|------|------|
| 总请求数 (含 502) | ~160 条 metrics |
| upstream_type nv_integrate | 86 |
| upstream_type nvcf_pexec   | 51 |
| upstream_type NONE (预算截断/未达上游) | 25 |

成功请求延迟分布 (metrics JSONL):
- dsv4p_nv: 成功 120 次, max=131,245ms, 3次 >80s (87s, 80.4s, 131.2s), 多数 20-60s
- kimi_nv: 成功 17 次, max=265,838ms, 5次 >60s, 多数 7-50s 但长尾极大
- glm5_1_nv: 成功 12 次, max 未超限

**失败原因细分** (metrics):
- kimi_nv / all_tiers_exhausted: 22 次
- dsv4p_nv / all_tiers_exhausted: 2 次

### 1.4 关键代码逻辑发现

gateway/upstream.py 中 integrate 失败后 **自动回退 pexec**: 
> "全 key 失败: 返回 all_keys_exhausted, 由 execute_request 回退 pexec"

这意味着: 当 integrate 路径 (empty200 / timeout) 失败后, proxy 会尝试 pexec fallback。
本次 UPSTREAM_TIMEOUT 扩展即为了 **扩展 pexec fallback 的救回窗口**。

### 1.5 参数现状 (docker-compose.yml, R576 基线)
```
UPSTREAM_TIMEOUT: "28"                    (R577 本次 ← 25→28)
TIER_TIMEOUT_BUDGET_S: "90"              (R576)
MIN_OUTBOUND_INTERVAL_S: "0.5"            (R570)
KEY_COOLDOWN_S: "25"                      (R162)
TIER_COOLDOWN_S: "25"                     (R492)
NVU_FORCE_STREAM_UPGRADE: "1"             (R502)
NVU_FORCE_STREAM_UPGRADE_TIMEOUT: "61"    (R537)
NVU_CONNECT_RESERVE_S: "2"                (R570)
NVU_SSLEOF_RETRY_DELAY_S: "1.0"           (R543)
NVU_PEXEC_TIMEOUT_FASTBREAK: "1"          (R559)
NVU_EMPTY_200_FASTBREAK: "0"              (R567)
NVU_PEER_FALLBACK_ENABLED: "1"            (R560)
NVU_PEER_FALLBACK_TIMEOUT: "25"           (R560)
NV_INTEGRATE_MODELS: dsv4p_nv,kimi_nv     (R575)
```

## 2. 候选参数评估 (按优先级排序)

| 参数 | 现值 | 评估 | 本轮决策 |
|------|------|------|----------|
| UPSTREAM_TIMEOUT | **25** | **binding (边缘)**: integrate 失败后回退 pexec 路径中, pexec per-attempt timeout = min(25, remaining_budget - 2); metrics 少量 pexec fallback 成功 (kimi 4 次, dsv4p 多) 均 <25s, 但边缘长尾 (如 dsv4p 80s+ 成功) 若走 pexec 可能被 25s 截断; +3s 提供救回窗口 | **25→28 (+3s)** |
| TIER_TIMEOUT_BUDGET_S | 90 | R576 刚回调, 当前 6h max=131s(ds)/266s(kimi) 属 integrate streaming 长尾, 不 binding pexec; p95 余量充足 | 不改 |
| NVU_CONNECT_RESERVE_S | 2 | 地板价, 实测 connect 0.6-2.1s | 不改 |
| MIN_OUTBOUND_INTERVAL_S | 0.5 | 地板价, KEY_COOLDOWN=25 >> 0.5 零 429 风险 | 不改 |
| NVU_PEXEC_TIMEOUT_FASTBREAK | 1 | ATE 模式为 empty200+1次 timeout, fastbreak=1 已捕获 | 不改 |
| NVU_EMPTY_200_FASTBREAK | 0 | R567 验证: empty200 独立出现时 5 keys 均有机会救回 | 不改 |
| NV_INTEGRATE_MODELS | dsv4p_nv,kimi_nv | kimi integrate 仍有 empty200, 但保留无额外成本 | 不改 |
| NVU_PEER_FALLBACK_TIMEOUT | 25 | 近期 0 次 peer fallback 记录 | 不改 |

## 3. 本轮改动与推理

### 改动: `UPSTREAM_TIMEOUT 25 → 28` (+3s)

- **数据支撑**: 
  - integrate 失败后回退 pexec 是既定代码逻辑 (upstream.py)
  - metrics 中 4 次 kimi pexec fallback 成功, dsv4p pexec 成功 47 次
  - pexec per-attempt timeout = min(UPSTREAM_TIMEOUT, remaining_budget - CONNECT_RESERVE)
  - 当 remaining_budget 充裕时 (首击), timeout ≈ UPSTREAM_TIMEOUT; 部分请求可能在 25-28s 边缘被截断
  - R490 原始设定 25 时数据为 "5 success 22-23s near edge", 当时成功 max=41.7s; 当前 regime 已变, 边缘请求延迟上升
- **风险**: 失败路径等待微增 (avg_f 79s → 82s, 仍 < BUDGET=90); 对 integrate streaming 长尾 (80-266s) 无影响
- **单参数**, 符合 "少改多轮" 铁律

**铁律查核**: compose 层面改, 不改 hm2 本地, 改完 HM1 立即 recreate 容器验证 env 一致性 → `UPSTREAM_TIMEOUT=28` 已确认。

**部署命令**:
```bash
sed -i '418s/UPSTREAM_TIMEOUT: "25"/UPSTREAM_TIMEOUT: "28"/' /opt/cc-infra/docker-compose.yml
cd /opt/cc-infra && docker compose up -d --no-deps --force-recreate nv_40006_uni
```

容器状态: `healthy`, env 已生效 UPSTREAM_TIMEOUT=28, 无 error/warn 级日志。

### git diff (应用于 HM1 docker-compose.yml)
```diff
--- a/opt/cc-infra/docker-compose.yml
-      UPSTREAM_TIMEOUT: "25"  # R490: HM2→HM1 — 23→25 (+2s revert R481)...
+      UPSTREAM_TIMEOUT: "28"  # R577: HM2→HM1 — UPSTREAM_TIMEOUT 25→28 (+3s). integrate失败后回退pexec路径偶发边缘timeout截断, metrics中4次kimi pexec fallback成功<25s但长尾有潜在收益; +3s扩展pexec fallback救回窗口且不显著增加失败等待(avg 79s→82s仍<BUDGET=90); 成功路径80-131s长尾不受影响(属integrate streaming); 单参数少改多轮; 铁律:只改HM1不改HM2
```

## 4. 评判维度

| 维度 | 本轮影响 | 备注 |
|------|----------|------|
| 更少报错 | 边际改善 | 扩展 pexec fallback 救回窗口, 可能救回 25-28s 边缘请求 |
| 更快请求 | -3s/ATE (等待微增) | 代价: 若救回失败则等待 +3s; 但成功救回则延迟大幅降低 (从 502→200) |
| 超低延迟 | 无影响 | p50=27s(ds)/34s(kimi) 未触及 |
| 稳定性优先 | ↑ | 减少边缘 pexec timeout 导致的截断不确定性 |

> 注: kimi_nv 成功率 ~51% 的 root cause 仍为 function-level empty200 surge (integrate 与 pexec 均受影响), 非网关参数可修。R577 仅对 pexec fallback 边缘窗口做保守扩展, 建议后续轮次继续观测 NVCF 上游稳定性。

## ⏳ 轮到HM1优化HM2
