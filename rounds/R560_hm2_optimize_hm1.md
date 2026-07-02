# R560 (HM2→HM1) 优化报告

## 📅 执行时间
2026-07-02 15:30–15:40 (UTC+8)

## 🎯 本轮目标
- 收集R559修改后HM1运行数据
- 基于数据继续小幅调整，每轮少改多轮积累
- 铁律:只改HM1不改HM2

---

## 📊 HM1数据收集

### SSH链路
```
ssh -p 222 opc_uname@100.109.153.83 ✓
hostname=opcsname, user=opc_uname
```

### Docker容器状态
```
hm40006 57a7ccc14387   Up 58 minutes (healthy)
```

### 环境变量快照（关键项）
| 参数 | 当前值 | 来源 |
|---|---|---|
| HM_PEER_FALLBACK_ENABLED | 1 | compose |
| HM_PEER_FALLBACK_TIMEOUT | 30 | compose (R558: 40→35→30) |
| HM_PEER_FALLBACK_URL | http://100.109.57.26:40006 | compose |
| HM_PEXEC_TIMEOUT_FASTBREAK | 1 | compose (R559: 2→1) |
| HM_CONNECT_RESERVE_S | 3 | compose (R533) |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | compose (R543) |
| TIER_TIMEOUT_BUDGET_S | 80 | 代码默认 |
| UPSTREAM_TIMEOUT | 25 | 代码默认 |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | compose (R537) |
| MIN_OUTBOUND_INTERVAL_S | 1.0 | 代码默认 |

### 近100条日志（error/warn关键摘要）
- `[HM-ALL-TIERS-FAIL]` All 1 tiers failed: dsv4p_nv elapsed≈61.2–61.5s, kimi_nv elapsed≈77.4–77.8s. ABORT-NO-FALLBACK.
- `[HM-PEXEC-FASTBREAK]` 1 consecutive NVCFPexecTimeout → fast-break (saved remaining keys). 工作状态正常.
- `[HM-TIER-FAIL]` kimi_nv: 429=0, empty200=1, timeout=1, other=0. dsv4p_nv: 429=0, empty200=0, timeout=1.
- `[HM-PEER-FB]` peer fallback **100%失败**（最近8次记录全为`TimeoutError: timed out after ~30022–30032ms`）.
  - 14:54 dsv4p_nv → 30.0s timeout
  - 15:25 dsv4p_nv → 30.0s timeout
  - 15:26 dsv4p_nv → 30.0s timeout
  - 15:35 peer-originated (hop=1) also all_tiers_exhausted → 无进一步fallback, 直接502.
- `[HM-THINKING-TIMEOUT]` (kimi_nv/dsv4p_nv) stream=True → extended timeout 61s. 频繁触发，但属上游推理延迟，非env可控。

### 成功请求统计（近500条日志）
| 时间 | 模型 | 结果 |
|---|---|---|
| 15:01:08 | kimi_nv k2 | 1st attempt success |
| 15:11:57 | kimi_nv k2 | 1 cycle success |
| 15:21:28 | kimi_nv k3 | 1st attempt success |
| 15:24:17 | kimi_nv k4 | 1st attempt success |
| 15:27:22 | kimi_nv k1 | 1st attempt success |

- **成功率≈33%** (5 success vs ~10 ATE over 34min window).
- dsv4p_nv 在这段时间内 **0次成功**，全为all_tiers_exhausted.

### DB状态
```
/home/opc_uname/hm_ps/hermes_improve_self/llm_requests.db 存在但无表 schema (空DB).
```
> DB未实际写入，分析完全依赖docker logs.

---

## 🔍 数据归因

| 现象 | 根因 | 可改? |
|---|---|---|
| peer fallback 100%失败 | HM1与HM2同时处于all_tiers_exhausted（上游供应商问题），互备通道无可用容量 | ✅ timeout可控 |
| dsv4p_nv 61s pexec timeout | 上游 NVCF function 响应慢/排队，5键全部单键即timeout，fastbreak后无救 | ❌ 上游问题 |
| kimi_nv empty200+timeout | empty200重置fastbreak计数器，实际与FASTBREAK=1不冲突（R559已验证） | ✅ 已优化(FASTBREAK=1) |
| 零429/零SSLEOF | 无rate-limit、无SSL握手错误，最大瓶颈是pexec慢 | N/A |

---

## ✅ 优化决策

### 选定参数: `HM_PEER_FALLBACK_TIMEOUT`: 30 → 25 (-5s)

**理由:**
1. **持续0%成功率验证**: 最近8次peer fallback全部`TimeoutError after ~30022–30032ms`; 30s空等无任何收益，每失败ATE白白浪费30s.
2. **历史安全边际**: R556记录最慢peer成功请求约24s@35s(1.45x). 缩至25s仍覆盖24s最慢成功，余量1.04x; 若未来HM2恢复，25s足够捕获边缘成功案例.
3. **与R556/R558对称**: 上一轮两次各减5s(40→35→30)都基于同一数据趋势; 本轮继续同幅度30→25，节奏一致.
4. **风险极低**: 仅影响all_tiers_exhausted失败路径，不影响成功路径; 若HM2恢复且请求>24s，仅损失边缘case(概率 historically <5%).

**不改的参数及原因:**
- `HM_PEXEC_TIMEOUT_FASTBREAK=1`: R559已验证2→1最优，继续保留.
- `HM_CONNECT_RESERVE_S=3`: 已足够小，再减会截断慢connect边缘case.
- `HM_FORCE_STREAM_UPGRADE_TIMEOUT=61`: thinking扩展等待不可少，上游推理延迟非env可解.
- `TIER_TIMEOUT_BUDGET/UPSTREAM_TIMEOUT`: 已由fastbreak控制实际时长，改大改小均无显著收益.

---

## 🔧 执行过程

### 修改文件
```bash
# HM1 (opc_uname@100.109.153.83)
/opt/cc-infra/docker-compose.yml
```
在 `HM_PEER_FALLBACK_URL` 行后新增：
```yaml
      HM_PEER_FALLBACK_TIMEOUT: "25"  # R560 (HM2→HM1): PEER_FALLBACK_TIMEOUT 30→25 (-5s). 数据验证peer fallback近期100%失败(8次全TimeoutError~30022ms), 每ATE再省5s; 历史最慢peer成功~24s@35s(1.45x), 25s仍1.04x安全边际; 单参数少改多轮. 铁律:只改HM1不改HM2
```
同时移除了旧行 `HM_PEER_FALLBACK_TIMEOUT: "30"`（R558遗留）避免YAML重复键.

### 部署验证
```bash
cd /opt/cc-infra && docker compose up -d hm40006
# → Container hm40006 Recreated → Starting → Started ✓
```
确认新env生效：
```bash
docker exec hm40006 env | grep HM_PEER_FALLBACK_TIMEOUT
# → HM_PEER_FALLBACK_TIMEOUT=25 ✓
```

---

## 📈 预期效果

| 指标 | 预测变化 |
|---|---|
| 失败响应时间 (dsv4p_nv ATE) | -5s (61.0s → ~56.0s) |
| 失败响应时间 (kimi_nv ATE via peer-fb触发时) | -5s (77+30s → 77+25s) |
| peer fallback 挽救率 | 基本不变 (持续0%成功率) |
| 成功请求延迟 | 无影响 (peer fb不参与成功路径) |
| 系统稳定性 | 无额外风险 |

---

## 📝 备注
- 近期HM1/HM2同时出现all_tiers_exhausted高潮，怀疑上游NVCF deepseek/kimi function普遍排队或容量不足，非配置可解.
- 单参数少改多轮策略下，本次仅动1个env; 后续若peer fb持续0%，可继续25→20.

## 🔄 轮次交接

**本轮完成: HM2 优化 HM1 (R560)**

## ⏳ 轮到HM1优化HM2
