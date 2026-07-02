# R549: HM2 → HM1 链路优化报告

**时间**: 2026-07-02 09:40–09:55 UTC+8  
**执行**: HM2优化HM1 (本session跑在HM2, ssh改对端HM1)  
**窗口**: 改前 08:35–09:40 (65min, R548启动后延续窗口) / 改后 09:55 新容器启动  
**目标**: HM1链路 → NV API (hm40006, 3model: kimi_nv / dsv4p_nv / glm5_1_nv)  
**类型**: 单参数下调 (HM_PEER_FALLBACK_TIMEOUT)  
**铁律**: 只改HM1不改HM2

---

## 漂移检测 (R548声称值 vs 实际部署)

| 参数 | R548声称 | 容器env实际 | compose文件实际 | 状态 |
|------|---------|------------|---------------|------|
| UPSTREAM_TIMEOUT | 25 | 25 ✅ | 25 ✅ | 一致 |
| TIER_TIMEOUT_BUDGET_S | 80 | 80 ✅ | 80 ✅ | 一致 |
| MIN_OUTBOUND_INTERVAL_S | 1.0 | 1.0 ✅ | 1.0 ✅ | 一致(R548已改) |
| KEY_COOLDOWN_S | 25 | 25 ✅ | 25 ✅ | 一致 |
| TIER_COOLDOWN_S | 25 | 25 ✅ | 25 ✅ | 一致 |
| HM_CONNECT_RESERVE_S | 3 | 3 ✅ | 3 ✅ | 一致 |
| HM_PEXEC_TIMEOUT_FASTBREAK | 1 | 1 ✅ | 1 ✅ | 一致 |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | 1.0 ✅ | 1.0 ✅ | 一致 |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | 61 ✅ | 61 ✅ | 一致 |
| **HM_PEER_FALLBACK_TIMEOUT** | **61** | **61 ✅** | **61 ✅** | **一致(本轮改前)** |

**漂移结论**: 零漂移。R548所有参数均实际生效。容器StartedAt=2026-07-02T08:03:00，在R548 commit(36e2816)之后。

---

## 数据采集概要 (R548后窗口, 08:35–09:40, 65min, host=opc_uname)

### 1.1 容器env (docker exec hm40006 env | sort)
- UPSTREAM_TIMEOUT=25, TIER_TIMEOUT_BUDGET_S=80, MIN_OUTBOUND_INTERVAL_S=1.0
- HM_FORCE_STREAM_UPGRADE_TIMEOUT=61, HM_PEER_FALLBACK_TIMEOUT=61
- HM_PEXEC_TIMEOUT_FASTBREAK=1, HM_CONNECT_RESERVE_S=3
- HM_SSLEOF_RETRY_DELAY_S=1.0, KEY_COOLDOWN_S=25, TIER_COOLDOWN_S=25
- **HM2本地env对照**: HM_PEER_FALLBACK_TIMEOUT=50 → HM1存在11s不对称(+21%)

### 1.2 docker logs最近100行摘要 (grep error/warn/fail/timeout)
- **零429**, **零SSLEOF**, **零WARN**
- **Tier失败模式**: `all 5 keys failed: 429=0, empty200=1, timeout=1, other=0`
- **典型失败时间线**: empty200(~61s) → pexec timeout(~16s) → FASTBREAK=1 → Tier fail at elapsed ~77s
- **Peer fallback**: 8次全部在~61000ms TimeoutError截断(与HM1 ceiling 61s binding)
- `peer-originated request (hop=1) also all_tiers_exhausted` — HM2→HM1互备通道8次, 亦全部失败
- **关键发现**: 1000行日志中**0次peer fallback成功** (grep peer.*success 返回0)

### 1.3 65分钟定量统计

| 指标 | 数值 |
|------|------|
| HM-SUCCESS | 20 |
| HM-ALL-TIERS-FAIL | 5 |
| 429 | 0 |
| SSLEOF | 0 |
| 成功率(本地) | 20/25 = 80.0% |

### 1.4 失败延迟分布
- Tier-fail延迟集中在 77.2–77.8s (BUDGET=80耗尽区间)
- peer-fail截断在 61.0–61.1s (PEER_FB_TIMEOUT=61)

### 1.5 Peer fallback 互备通道分析
- HM1 8次 peer fallback → 全部61s TimeoutError → HM2
- HM2 3次 peer fallback → 全部timeout → HM1
- **互备通道零救回**: 两侧在NVCF surge期间同步失效, peer fallback沦为纯延迟路径
- 缩短HM1的peer fallback超时从61→50s, 失败路径节省11s, 且功能未损失(0救回→0救回)

---

## 候选评估表

| 参数 | 当前值 | 候选新值 | 评估数据 | 决策 |
|------|--------|----------|----------|------|
| **HM_PEER_FALLBACK_TIMEOUT** | **61** | **50** (-11s) | HM2本地=50, 存在11s不对称; 65min内peer fallback 0次成功(8次全部timeout), 缩短失败路径+11s无功能损失; 零429风险; NVCF surge期间HM1与HM2天然同步失败, 更快返回502 | ✅ **采纳** |
| CONNECT_RESERVE_S | 3 | 2(-1s) | connect实测以前窗口0.6-2.1s, 2=0.95x边际不足; R533已论证3是安全边际 | ❌ |
| UPSTREAM_TIMEOUT | 25 | 28(+3s) | 失败全为NVCF surge(empty200+pexec timeout), 非本地TCP read hang; 25s对普通请求已富余; thinking请求由FORCE_STREAM_UPGRADE_TIMEOUT=61覆盖 | ❌ |
| TIER_TIMEOUT_BUDGET_S | 80 | 75(-5s) | 失败在77s budget耗尽, 降75只会更快abandon; 且edge成功可能在75-80区间不可证伪 | ❌ |
| HM_PEXEC_TIMEOUT_FASTBREAK | 1 | 0(禁用) | FASTBREAK=0会使ATE路径延长5×attempt, >125s>>BUDGET; 全部失败为2-key后break(61+16s), 救回率数据不支持继续尝试 | ❌ |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | 59(-2s) | R537已论证61是ceiling对齐; 失败clip在61s(empty200), 再降会损失edge成功; HM2已61, 对称保持 | ❌ |
| MIN_OUTBOUND_INTERVAL_S | 1.0 | 0.8(-0.2s) | R548刚改1.2→1.0, 需多轮观察; 再降零429但边际为负 | ❌ |
| KEY_COOLDOWN_S | 25 | 22(-3s) | 65min零429, 有空间; 但R162已调至此且长期稳定, 当前root cause是NVCF surge非key可用性 | ❌ |
| SSLEOF_RETRY_DELAY | 1.0 | 0.8(-0.2s) | 65min零SSLEOF; 1.0已与HM2对齐(R543), 再降边际为负 | ❌ |

---

## 优化执行

### 2.1 改动详情
- **参数**: `HM_PEER_FALLBACK_TIMEOUT`
- **改动**: `61 → 50` (-11s)
- **文件**: `/opt/cc-infra/docker-compose.yml` (HM1实际部署文件)
- **操作**: `sed -i '429s/.../.../' /opt/cc-infra/docker-compose.yml`
- **新行**: `HM_PEER_FALLBACK_TIMEOUT: "50"  # R549: HM2→HM1 — 61→50 (-11s). 与HM2当前50对齐; 1000line日志0次peer fallback成功(8次尝试全部timeout), 缩短失败路径+11s; peer fallback功能未损失(0→0); NVCF surge期间HM1与HM2互备通道天然同步失败, 缩短超时更快返回502; 少改多轮; 铁律:只改HM1不改HM2`

### 2.2 容器重启
- `docker compose up -d --no-deps hm40006` (项目路径 /opt/cc-infra)
- 容器状态: `Up 16 seconds (healthy)` (验证通过)
- 重启后 env 确认: `HM_PEER_FALLBACK_TIMEOUT=50` ✅
- 启动日志正常: Listening on 0.0.0.0:40006

### 2.3 预期效果
- **成功率**: 中性(对NVCF surge无直接影响, peer fallback 0救回→0救回)
- **延迟**: 失败路径快11s(61s→50s), 成功路径不受影响
- **风险**: 极低; peer fallback当前零功能, 缩短超时无损失
- **对称**: 与HM2当前50对齐

---

## 决策分析

1. **NVCF surge仍为root cause**: 65min内失败100%为empty200(~61s)+pexec timeout(~16s)模式, 与R546/R547/R548结论一致。此为服务端function-level surge, 非本地参数可解。
2. **互备通道完全废置**: HM1(local 77s fail) → peer fb 61s(timeout) + HM2(peer-originated 77s fail) = 两侧互备零救回。缩短超时从61→50仅减少失败等待, 不改变功能(0→0)。
3. **FASTBREAK=1已达极限**: 每ATE节省3个keys(跳过), 从预算角度看已是最优。
4. **PEER_FALLBACK对齐**: HM2本地已用50(R525), HM1(R538)仅到61。此次-11s完成HM1-HM2 peer fallback timeout对称。
5. **与R548 MIN_OUTBOUND对齐互补**: 前两轮完成(1)MIN_OUTBOUND 1.2→1.0 和 (2)PEER_FB 61→50, 双参数均与HM2对齐。

---

## 结论

本轮执行**单参数下调**: `HM_PEER_FALLBACK_TIMEOUT 61 → 50`。

- 数据否决其他8项候选(全部基于"NVCF surge不可控, 本地参数已达最优/边际为负")
- 唯一采纳的`HM_PEER_FALLBACK_TIMEOUT`用于对齐HM2、缩短失败路径等待, 风险极低(当前零功能)
- 符合"单参数少改多轮"铁律

## ⏳ 轮到HM1优化HM2
