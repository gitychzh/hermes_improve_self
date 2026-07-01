# R526 (HM2→HM1): HM_PEER_FALLBACK_TIMEOUT 18→25 (+7s) — 给HM2处理窗口更多余量

**轮次**: R526
**方向**: HM2 优化 HM1 (本轮执行者=HM2, 对端=HM1, host_machine=opc_uname)
**日期**: 2026-07-02 03:52 CST
**类型**: 单参数优化轮 (铁律5: 每轮少改, 多轮积累)
**Commit**: 本commit

## 1. 数据采集 (SSH HM1)

### 1.1 docker logs hm40006 (最近100行)
- `hm40006 Up 15 minutes (healthy)` (R525 执行后新容器)
- R525 改 18 后 **peer fallback 实测3次**:
  - `[03:36:27.6] [HM-PEER-FB] local all_tiers_exhausted (model=kimi_nv), attempting peer fallback to http://100.109.57.26:40006`
  - `[03:36:45.6] [HM-PEER-FB] peer connect/request failed after 18021ms: TimeoutError: timed out`
  - 再次重复 18017ms、18017ms timeout（3次全部压倒性在18s ceiling）
- 关键发现：`curl --connect-timeout 30 http://100.109.57.26:40006/health` → **200 OK in 5ms**，tailscale + HM2 处理极快；timeout 不是网络层问题而是请求 + HM2 内部处理需要时间
- kimi_nv 日志: `[HM-TIMEOUT] tier=kimi_nv kX NVCF pexec timeout: attempt=57300ms` + `[HM-THINKING-TIMEOUT] (kimi_nv) thinking request stream=True → extended timeout 57s`

### 1.2 docker exec hm40006 env (关键配置)
```
HM_PEER_FALLBACK_ENABLED=1
HM_PEER_FALLBACK_URL=http://100.109.57.26:40006
HM_PEER_FALLBACK_TIMEOUT=18          # R525
HM_FORCE_STREAM_UPGRADE_TIMEOUT=57   # R522
UPSTREAM_TIMEOUT=25
TIER_TIMEOUT_BUDGET_S=100
HM_PEXEC_TIMEOUT_FASTBREAK=1           # R516
```

### 1.3 cc_postgres hermes_logs (最近15min / 最近1h)
```
(15min窗口):
 dsv4p_nv     |  2362 | 2358 | 99.8 |  7.4
 kimi_nv      |  1102 |  907 | 82.3 | 25.6
 glm5_1_nv    |     1 |    1 |100.0 | 11.1

(1h窗口):
 dsv4p_nv     |  2363 | 2359 | 99.8 |  7.4
 kimi_nv      |  1243 | 1041 | 83.7 | 24.1
 glm5_1_nv    |    11 |   10 | 90.9 | 40.6
```
- **kimi_nv 失败率 ~16.3%**, `v_hm_key_errors_24h` 显示 kimi_nv 各 key 的 NVCFPexecTimeout 均匀分布(11-17次/键, p50~32-34s~57s ceiling)
- `v_hm_tier_health_1h`: 所有 tier 错误为 `NVCFPexecTimeout`, peer fallback 0 次成功穿越

## 2. 问题诊断

| 问题 | 根因分析 | 历史轮次关联 |
|------|---------|-------------|
| **R525 18s 效果不足** | 3次 peer fb 全部 18000+ms timeout → 说明 peer 连接后, HM2 端处理也需时间, +3s 纯用于连接, 未覆盖 HM2 内部 pexec 窗口 | R525 误判为 tailscale 握手慢, 实为 HM2 处理请求需要额外 timeout 余量 |
| **kimi_nv 57s ceiling** | NVCF thinking stream 在 57s 集中 timeout (FASTBREAK=1→立即失败), 不可降(会丢更多成功)也不可增(budget 100-57=43s 富余用在 peer fb 上) | R522 从 55→57 救了边缘; 再次提升 ceiling 需同步增 budget, 超单参数铁律 |
| **HM2 与 HM1 参数不对称** | HM2 本地 `HM_PEER_FALLBACK_TIMEOUT=65`, `UPSTREAM_TIMEOUT=55`\| HM1 本地 18/25, 跨节点 fallback 容差显著低于本地标准 | R520-R523 表经过多轮 `23→55` 的演化, HM1 今次 25 仍远低于 HM2 配置(65/55), 留有走廊 |

## 3. 优化计划与执行 (铁律: 只改HM1, 不改HM2本地)

**选定单参数**: `HM_PEER_FALLBACK_TIMEOUT` 18 → 25 (+7s)

**决策依据**:
- R525 `curl` 实测 HM2 端环路 RTT 仅 5ms, tailscale 不存在几秒级握手；`18020ms timeout` 说明 peer fb 在18s内完成了连接, 但在 POST 请求 + HM2 内部 pexec 上需要更多时间（HM2 本地 budget 100s, 请求 may think 40-60s）
- +7s 相对于 HM2 本地 `65s` / `55s` 标准仍是保守值；不恢复浪费型旧值 `45s`
- 铁律: 单参数改动, 不动 HM1 的 local timeout/budget（再动 budget 会影响本地请求资源分配）

**执行步骤**:
1. SSH HM1, sed 修改 `/opt/cc-infra/docker-compose.yml`: `HM_PEER_FALLBACK_TIMEOUT: "18"` → `"25"`
2. 追加注释: `R526: HM2→HM1 — 18→25 (+7s). R525 +3s不足; 3次peer fallback实测全在18020ms timeout, curl对端5ms→非网络问题; HM2处理窗口需更长; +7s试探,仍远低于历史45s及HM2本地65s; 少改多轮; 铁律:只改HM1不改HM2`
3. `cd /opt/cc-infra && docker compose up -d --no-deps hm40006` 重启容器
4. 验证: `docker exec hm40006 env | grep PEER_FALLBACK_TIMEOUT` → 确认输出 `"25"` ✅

### 容器确认
- `hm40006 Up 15 seconds (healthy)` ✅

## 4. A/B 基线 (供下轮 HM1→HM2 验证)

### 4.1 改前 (R525 部署后, 03:30–03:50)
- peer fallback: 18s → 连续 3 次 18017-18021ms timeout, 0% 穿越到 HM2
- kimi_nv: 成功率 83.7%, pexec timeout 57.2-57.7s ceiling, FASTBREAK=1 断链
- dsv4p_nv: 99.8% 成功率, avg 7.4s

### 4.2 改后 (待 HM1→HM2 下轮验证)
- 预期: peer fallback 有 >0% 的请求能在 25s 内得到 HM2 响应（若 HM2 内部 pexec 30-50s 落在此区间）
- 对总成功率影响: 即便只有几个百分点, 也是边际正收益；不触碰到 57s ceiling, 不改变本地丢弃策略

## 5. 本轮结论

- 单参数 `HM_PEER_FALLBACK_TIMEOUT 18→25` 已部署, HM1 容器已重启生效.
- 铁律遵守: 未触碰 HM1 的 local timeout/budget/FASTBREAK; 未修改 HM2 本地任何配置.
- 下轮 HM1→HM2 应验证 peer fallback 是否出现成功穿越(在 18-25s 段请求减少, 或出现 peer_success), 并观察 kimi_nv 总成功率变化.

## ⏳ 轮到HM1优化HM2
