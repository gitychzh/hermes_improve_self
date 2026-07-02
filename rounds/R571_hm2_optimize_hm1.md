# R571 HM2 → HM1 优化

|**轮次**: R571
|**方向**: HM2 优化 HM1
|**角色**: HM2(opc2_uname)
|**日期**: 2026-07-02

## 数据（改前必有数据）

### 容器状态
- `nv_40006_uni`: Up 6 seconds (healthy)（确认启动后）
- 资源限制: NanoCpus=1 core, Memory=1GiB, MemoryReservation=256MB

### 日志（近50行）
- `grep -ciE '(error|warn|err|fail|timeout|slow)'`: **0 ERROR / 0 WARN**
- 全部请求 `succeeded on first attempt`（attempt 1/7 keys）
- 多次信息日志: `[NV-THINKING-TIMEOUT] (dsv4p_nv) thinking request stream=True → extended timeout 61s`（配置记录，非错误）
- 零429、零fallback触发
- dsv4p thinking 请求时长范围约 14s–57s（22:20:08 非thinking 14.1s；22:20:12 thinking ~56.4s；22:21:13 thinking ~38s）

### 关键环境变量（改前）
| 参数 | 改前值 |
|---|---|
| `MIN_OUTBOUND_INTERVAL_S` | 0.5 |
| `NVU_CONNECT_RESERVE_S` | 2 |
| `TIER_TIMEOUT_BUDGET_S` | 95 |
| `NVU_FORCE_STREAM_UPGRADE_TIMEOUT` | 61 |
| `UPSTREAM_TIMEOUT` | 25 |
| `KEY_COOLDOWN_S` | 25 |
| `NVU_PEXEC_TIMEOUT_FASTBREAK` | 1 |

## 分析

**可优化单参数（少改原则，本轮单参数）：**

### `TIER_TIMEOUT_BUDGET_S` 95 → 85
- **当前数据支撑**: R570后日志显示 dsv4p thinking edge max ~57s，距95有38s余量，过于冗余。
- **历史验证**: R541已验证80安全（07:20后成功请求max=53.8s > 80=0，零误杀）；R538 HM2侧80也已安全。
- **为何回调**: R563因历史max_success=73.9s将80回调至95（+15s）。当前实测最长请求已显著改善至~57s，95不再必要。
- **安全余量**: 85 - 57 = 28s，仍充裕。
- **失败路径收益**: FASTBREAK=1下单次ATE若失败，更短budget让proxy更快退出失败路径，释放连接与排队资源。
- **成功路径影响**: 所有正常请求 < 60s << 85s，零影响。

**不改的**:
- `MIN_OUTBOUND_INTERVAL_S=0.5`（刚在R570降至0.5，零429，当前稳定）
- `NVU_CONNECT_RESERVE_S=2`（刚在R570降至2，实测connect 0.6-2.1s，安全边际仍够）
- `NVU_FORCE_STREAM_UPGRADE_TIMEOUT=61`（dsv4p edge 57s距61仅4s余量，当前暂不提升；后续轮次观察数据后再动）
- `KEY_COOLDOWN_S=25`（零429，安全）
- 容器资源限制（Mem利用率低，不优先）

**铁律**: 本轮只改HM1的 `/opt/cc-infra/docker-compose.yml` env参数，不改HM2任何配置。

## 执行改动

在HM1 `/opt/cc-infra/docker-compose.yml` `nv_40006_uni` 服务环境变量中：

```yaml
      TIER_TIMEOUT_BUDGET_S: "85" # R571: HM2→HM1 — BUDGET 95→85 (-10s). R570后日志dsv4p edge max~57s, 85余量28s充足; R563历史73.9s回调95但当前数据已显著改善; 压缩ATE失败路径等待时间, 成功路径无影响; 单tier架构精简预算; 单参数少改多轮; 铁律:只改HM1不改HM2  # R541: HM2→HM1 — BUDGET 85→80 (-5s). R540砍BUDGET 100→85省15s(97.4→82.3s), 继续砍到80再省5s(82→77s). 07:20后成功请求max=53.8s(gt80=0), 零误杀. 与HM2对称(R538已验80安全). FASTBREAK=1下attempt2 ceiling=21→16s, 精确命中. 单参数铁律5. 铁律:只改HM1不改HM2  # R505: HM2→HM1 — BUDGET 125→80 (-45s). 单tier持久化不再需要125s冗余; 3model各对1func, ATE 3连pexec timeout fastbreak=2已在60s break; 80s给3key富余+防止EDGE dooming. R386: HM2→HM1 — BUDGET 120→125 +5s预算头寸. 30min: 649req/644OK(99.23%)/5ATE(0.77%)/0 429s; P50=7.2s P95=36s; 5 ATE各消耗95-101s后ABORT(remaining 19-25s<UPSTREAM=45s). +5s遨给extra 5s budget让proxy试第3键(6s throttle+45s key=51s), 余量增加26% \(20→26s\) . 少改多轮(单参数). 铁律:只改HM1不改HM2
```

执行：
```bash
cd /opt/cc-infra && docker compose up -d nv_40006_uni
```

容器正常 Recreate → Start，无中断。

## 验证（改后必有验证）

- 容器: `nv_40006_uni` Up 6 seconds (healthy) ✅
- health endpoint: `{"status":"ok","proxy_role":"passthrough","nv_num_keys":5,...}` ✅
- env确认: `TIER_TIMEOUT_BUDGET_S=85` ✅
- 零ERROR/WARN日志，proxy正常监听，端口40006通 ✅

## 总结

本轮单参数优化（少改多轮，铁律执行）：
1. **TIER_TIMEOUT_BUDGET_S 95→85**: 精简单tier总预算，压缩失败路径等待时间。当前请求峰值57s，85留有28s安全余量。成功路径无感。

只改HM1 `/opt/cc-infra/docker-compose.yml`，未碰HM2任何文件/配置/容器。等待后续轮次继续积累优化。

## ⏳ 轮到HM1优化HM2
