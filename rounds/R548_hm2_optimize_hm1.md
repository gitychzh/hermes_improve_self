# R548: HM2 → HM1 链路优化报告

**时间**: 2026-07-02 09:30–09:36 UTC+8  
**执行**: HM2优化HM1 (本session跑在HM2, ssh改对端HM1)  
**窗口**: 改前 08:35–09:30 (55min) / 改后 09:35 新容器启动  
**目标**: HM1链路 → NV API (hm40006, 3model: kimi_nv / dsv4p_nv / glm5_1_nv)  
**类型**: 单参数下调 (MIN_OUTBOUND_INTERVAL_S)  
**铁律**: 只改HM1不改HM2

---

## 漂移检测 (R547声称值 vs 实际部署)

| 参数 | R547声称 | 容器env实际 | compose文件实际 | 状态 |
|------|---------|------------|---------------|------|
| UPSTREAM_TIMEOUT | 25 | 25 ✅ | 25 ✅ | 一致 |
| TIER_TIMEOUT_BUDGET_S | 80 | 80 ✅ | 80 ✅ | 一致 |
| **MIN_OUTBOUND_INTERVAL_S** | **1.2** | **1.2 ✅** | **1.2 ✅** | **一致(本轮改前)** |
| KEY_COOLDOWN_S | 25 | 25 ✅ | 25 ✅ | 一致 |
| TIER_COOLDOWN_S | 25 | 25 ✅ | 25 ✅ | 一致 |
| HM_CONNECT_RESERVE_S | 3 | 3 ✅ | 3 ✅ | 一致 |
| HM_PEXEC_TIMEOUT_FASTBREAK | 1 | 1 ✅ | 1 ✅ | 一致 |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | 1.0 ✅ | 1.0 ✅ | 一致 |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | 61 ✅ | 61 ✅ | 一致 |
| HM_PEER_FALLBACK_TIMEOUT | 61 | 61 ✅ | 61 ✅ | 一致 |
| HM_FORCE_STREAM_UPGRADE | 1 | 1 ✅ | 1 ✅ | 一致 |

**漂移结论**: 零漂移。R541(BUDGET 85→80)、R537(FORCE_STREAM_UPGRADE 59→61)、R538(PEER_FB 59→61)所有参数均实际生效。容器StartedAt=2026-07-02T08:03:00，在R547 commit(774e582)之后。

---

## 数据采集概要 (R547后窗口, 08:35–09:30, 60min, host=opc_uname)

### 1.1 容器env (docker exec hm40006 env | sort)
- UPSTREAM_TIMEOUT=25, TIER_TIMEOUT_BUDGET_S=80, MIN_OUTBOUND_INTERVAL_S=1.2
- HM_FORCE_STREAM_UPGRADE_TIMEOUT=61, HM_PEER_FALLBACK_TIMEOUT=61
- HM_PEXEC_TIMEOUT_FASTBREAK=1, HM_CONNECT_RESERVE_S=3
- HM_SSLEOF_RETRY_DELAY_S=1.0, KEY_COOLDOWN_S=25, TIER_COOLDOWN_S=25
- HM2本地env对照: MIN_OUTBOUND_INTERVAL_S=1.0 → HM1存在0.2s不对称

### 1.2 docker logs最近100行摘要 (grep error/warn/fail/timeout)
- **零429**, **零SSLEOF**, **零WARN**
- **Tier失败模式**: `all 5 keys failed: 429=0, empty200=1, timeout=1, other=0`
- **典型失败时间线**: empty200(~61s) → pexec timeout(~16s) → FASTBREAK=1 → Tier fail at elapsed ~77s
- **Peer fallback**: 8次全部在~61000ms TimeoutError截断(与HM2 ceiling 61s对称且binding)
- `peer-originated request (hop=1) also all_tiers_exhausted` — HM2→HM1互备通道8次, 亦全部失败

### 1.3 60分钟定量统计
| 指标 | 数值 |
|------|------|
| HM-SUCCESS | 90 |
| HM-ALL-TIERS-FAIL | 24 |
| 本地all_tiers_exhausted | 16 |
| peer-originated all_tiers_exhausted | 8 |
| 429 | 0 |
| SSLEOF | 0 |
| 成功率(本地) | 90/(90+16)=84.9% |
| 成功率(含peer) | 90/(90+24)=78.9% |

### 1.4 Key成功分布 (均匀)
- k1 succeeded 18 | k2 succeeded 16 | k3 succeeded 15 | k4 succeeded 20 | k5 succeeded 21

### 1.5 失败延迟分布
- Tier-fail延迟集中在 77.3–78.0s (BUDGET=80耗尽区间)
- peer-fail截断在 61.0s (PEER_FB_TIMEOUT=61)

---

## 候选评估表

| 参数 | 当前值 | 候选新值 | 评估数据 | 决策 |
|------|--------|----------|----------|------|
| **MIN_OUTBOUND_INTERVAL_S** | **1.2** | **1.0** (-0.2s) | HM2本地=1.0，存在0.2s不对称；KEY_COOLDOWN=25 >> 1.0，零429风险(60min日志零429)；key轮转更密可降低高并发排队微延迟；单tier架构无tier间throttle影响 | ✅ **采纳** |
| CONNECT_RESERVE_S | 3 | 2(-1s) | connect实测0.6-2.1s，2=0.95x边际不足；上次R533已论证3是1.4x安全边际 | ❌ |
| UPSTREAM_TIMEOUT | 25 | 28(+3s) | 失败全为NVCF surge(empty200+pexec timeout)，非本地TCP read hang；25s对普通请求已富余；thinking请求由FORCE_STREAM_UPGRADE_TIMEOUT=61覆盖 | ❌ |
| TIER_TIMEOUT_BUDGET_S | 80 | 75(-5s) | 失败在77s budget耗尽，降75只会更快abandon；且成功请求max未统计到>80s但边缘不可证伪 | ❌ |
| HM_PEXEC_TIMEOUT_FASTBREAK | 1 | 0(禁用) | FASTBREAK=0会使ATE路径延长5× attempt，>125s>>BUDGET；全部失败为2-key后break(61+16s)，救回率数据不支持继续尝试 | ❌ |
| HM_PEER_FALLBACK_TIMEOUT | 61 | 65(+4s) | peer fb 61s截断是HM2端需~77s才返回502，单方增加仅延长用户等待无救回；如增到80需HM2同步 | ❌ |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | 63(+2s) | 与HM2=61对称；R537已论证61是ceiling对齐；无边缘请求在59-61s成功证据 | ❌ |
| KEY_COOLDOWN_S | 25 | 22(-3s) | 60min零429，有空间；但上次R162已调至此且长期稳定，当前主要问题是NVCF surge非key可用性 | ❌ |
| SSLEOF_RETRY_DELAY | 1.0 | 0.8(-0.2s) | 60min零SSLEOF；1.0已与HM2对齐(R543)，再降边际为负 | ❌ |

---

## 优化执行

### 2.1 改动详情
- **参数**: `MIN_OUTBOUND_INTERVAL_S`
- **改动**: `1.2 → 1.0` (-0.2s)
- **文件**: `/opt/cc-infra/docker-compose.yml` (HM1实际部署文件)
- **操作**: `sed -i '421s/1.2/1.0/' /opt/cc-infra/docker-compose.yml`
- **新注释**: `# R548: HM2→HM1 — 1.2→1.0 (-0.2s). 与HM2当前1.0对齐; KEY_COOLDOWN=25 >> 1.0 零429风险; 单tier下减少key轮转throttle, 成功路径排队微降; 少改多轮; 铁律:只改HM1不改HM2`

### 2.2 容器重启
- `docker compose up -d hm40006` (项目路径 /opt/cc-infra)
- 容器状态: `Up 46 seconds (healthy)` (验证通过)
- 重启后 env 确认: `MIN_OUTBOUND_INTERVAL_S=1.0` ✅

### 2.3 预期效果
- **成功率**: 中性或微正(对NVCF surge无直接影响)
- **延迟**: 高并发场景key轮转微降，边缘排队延迟-0.2s/key
- **风险**: 极低；KEY_COOLDOWN=25是1.0的25倍，429风险可忽略

---

## 决策分析

1. **NVCF surge仍为root cause**: 60min内失败100%为empty200(~61s)+pexec timeout(~16s)模式，与R546/R547结论一致。dsv4p_nv/glm5_1_nv未单独统计(because单tier ring中kimi_nv占主导地位，或3model function各自独立出现)，但失败形态相同。
2. **互备通道互锁**: HM1(local 77s fail) → peer fb 61s(timeout) + HM2(peer-originated 77s fail) = 两侧互备完全废置。此为**NVCF Global Surge**导致，非本地参数可解。
3. **FASTBREAK=1已达极限**: 每ATE节省3个keys(跳过)，从预算角度看已是最优。
4. **MIN_OUTBOUND对齐**: HM2本地已用1.0(R519)，HM1(R521)仅到1.2。此次-0.2s完成HM1-HM2 outbound interval对称。

---

## 结论

本轮执行**单参数下调**: `MIN_OUTBOUND_INTERVAL_S 1.2 → 1.0`。

- 数据否决其他8项候选(全部基于"NVCF surge不可控，本地参数已达最优/边际为负")
- 唯一采纳的`MIN_OUTBOUND_INTERVAL_S`用于对齐HM2、降低throttle微延迟，风险极低
- 符合"单参数少改多轮"铁律

## ⏳ 轮到HM1优化HM2
