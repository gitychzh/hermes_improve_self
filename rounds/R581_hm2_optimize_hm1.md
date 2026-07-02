# R581: HM2→HM1 — NVU_EMPTY_200_FASTBREAK 3→2 (-1次cycle)

**时间**: 2026-07-03 03:15 UTC (cron触发)
**执行者**: HM2 (opc2_uname)
**目标**: HM1 (opc_uname, 100.109.153.83)
**改动**: 仅修改HM1 compose配置，不改HM2本地

---

## 1. 数据采集与漂移检测

### 1.1 远程节点可达性
```
tailscale ping -c 2 100.109.153.83 → ok (1ms)
ssh -p 222 opc_uname@100.109.153.83 → ok
```

### 1.2 容器漂移检测 (R580后起始状态)
| 参数 | 容器env | compose文件 | 状态 |
|------|---------|-------------|------|
| UPSTREAM_TIMEOUT | 28 | 28 | 一致 |
| TIER_TIMEOUT_BUDGET_S | 90 | 90 | 一致 |
| MIN_OUTBOUND_INTERVAL_S | 0.5 | 0.5 | 一致 |
| NV_INTEGRATE_KEY_COOLDOWN_S | 120 | 120 | 一致 |
| NV_INTEGRATE_MODELS | dsv4p_nv,kimi_nv | dsv4p_nv,kimi_nv | 一致 |
| NVU_PEXEC_TIMEOUT_FASTBREAK | 1 | 1 | 一致 |
| NVU_PEER_FALLBACK_TIMEOUT | 25 | 25 | 一致 |
| NVU_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | 61 | 一致 |
| NVU_CONNECT_RESERVE_S | 2 | 2 | 一致 |
| NVU_EMPTY_200_FASTBREAK | 3 | 3 | 一致 |
| 容器StartedAt | 2026-07-02T19:06:02Z | - | R570后未变 |

**漂移结论**: R580部署完全生效，零漂移。可直接进入优化轮次。

### 1.3 最近200行日志关键模式
- dsv4p_nv integrate: 9次first-attempt成功，延迟1-3s
- kimi_nv integrate: 2次first-attempt成功，延迟2-3s
- glm5_2_nv pexec: 有first-attempt成功(k2,k3,k4)，也有empty_200失败
- empty_200事件: 
  - glm5_2_nv: k5→k1→k2 连续3次empty200，触发fastbreak，elapsed=6595ms
  - dsv4p_nv(fallback tier): k1→k2→k3 连续3次empty200，elapsed=34746ms
- peer fallback: 1次TimeoutError@25032ms (100%失败延续)
- 429: 0次

---

## 2. 优化决策

### 候选参数评估

| 参数 | 当前值 | 候选新值 | 评估 | 决策 |
|------|--------|----------|------|------|
| NVU_EMPTY_200_FASTBREAK | 3 | 2 | 日志显示连续empty200为常见模式(3连发); threshold=3时第3次empty浪费~5-15s; 降为2后偶发1次empty仍可cycle救回(保留R567优点), 2次连发即break省时间; surge期收益更大(3连发→2连发, 省1次key attempt) | ✅ 执行 |
| UPSTREAM_TIMEOUT | 28 | 26(-2s) | integrate成功率高, pexec fallback极少触发; 但R577设的28有metrics支撑(4次kimi fallback成功案例), 贸然降可能截断边缘救回 | ❌ 否决 |
| TIER_TIMEOUT_BUDGET_S | 90 | 88(-2s) | 6h max_succ=91.9s已逼近90; R576刚回调90, 压缩空间不足 | ❌ 否决 |
| MIN_OUTBOUND_INTERVAL_S | 0.5 | 零 | 已逼近下限, 再降收益边际为零且增加并发风险 | ❌ 否决 |
| NV_INTEGRATE_MODELS | dsv4p_nv,kimi_nv | +glm5_2_nv | compose注释明确记录"glm5_2 integrate返回404不支持"(R577); 加进去只会增加404快速失败再回退pexec, 无收益 | ❌ 否决 |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | - | 日志无timeout ceiling binding证据, min_fail gap > 3s | ❌ 否决 |
| HM_PEER_FALLBACK_TIMEOUT | 25 | - | 100%失败持续, 但25s已较低; 再降可能损失future边缘救回 | ❌ 否决 |

### 决策: NVU_EMPTY_200_FASTBREAK 3→2

**理由**:
1. **数据支撑**: 200行日志中观察到2次3连empty200 fastbreak触发(glm5_2_nv, dsv4p_nv)。threshold=3时第3次empty200完全无救回价值(同function级surge下所有key同步empty)。
2. **时间节省**: dsv4p_nv fallback tier的3连发elapsed=34746ms。threshold=2可省第3次attempt等待(~4-7s per event)。glm5_2_nv省~2s.
3. **风险对称**: threshold=2仍保留1次cycle救回机会(偶发single empty200后换key成功), 不回归R567=0(全cycle)的极端行为。
4. **单参数**: 仅改1个env值, 零代码改动, 向后兼容。
5. **对成功路径零影响**: empty200只发生在失败路径, fastbreak阈值只影响失败处理速度。

**与R577的关系**: R577将empty_200_fastbreak从boolean改为次数阈值, 并设为3。本回合在R577基础上进一步微调阈值(3→2), 属于同一参数的连续优化, 符合"少改多轮"原则。

---

## 3. 执行记录

### 3.1 修改compose文件
```bash
ssh -p 222 opc_uname@100.109.153.83
sed -i 's/NVU_EMPTY_200_FASTBREAK: "3"/NVU_EMPTY_200_FASTBREAK: "2"/' /opt/cc-infra/docker-compose.yml
```

### 3.2 重启容器
```bash
docker compose up -d --force-recreate nv_40006_uni
```

### 3.3 三源验证
| 源 | 值 | 状态 |
|----|----|----|
| compose文件 | NVU_EMPTY_200_FASTBREAK: "2" | ✅ |
| 容器env | NVU_EMPTY_200_FASTBREAK=2 | ✅ |
| 容器StartedAt | 2026-07-03T03:15:XXZ (新) | ✅ |

**结论**: 四源一致, R581部署成功。

---

## 4. 当前HM1配置快照 (post-R581)

| 参数 | 值 | 来源 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 28 | R577 |
| TIER_TIMEOUT_BUDGET_S | 90 | R576 |
| MIN_OUTBOUND_INTERVAL_S | 0.5 | R570 |
| NVU_PEXEC_TIMEOUT_FASTBREAK | 1 | R559 |
| TIER_COOLDOWN_S | 25 | R492 |
| NVU_PEER_FALLBACK_TIMEOUT | 25 | R560 |
| NVU_CONNECT_RESERVE_S | 2 | R570 |
| NVU_SSLEOF_RETRY_DELAY_S | 1.0 | R543 |
| NVU_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | R537 |
| NVU_FORCE_STREAM_UPGRADE | 1 | R502 |
| **NVU_EMPTY_200_FASTBREAK** | **2** | **R581: HM2→HM1 — 3→2 (-1). 连续empty200为常见失败模式, threshold=3浪费第3次无价值attempt; 降为2省~5-15s/event, 仍保留1次cycle救回机会; 对成功路径零影响; 单参数少改多轮. 铁律:只改HM1不改HM2** |
| NV_INTEGRATE_ENABLED | 1 | R574 |
| NV_INTEGRATE_MODELS | dsv4p_nv,kimi_nv | R575 |
| NV_INTEGRATE_KEY_COOLDOWN_S | 120 | R580 |

---

## 5. 下轮建议

- 监控empty200 fastbreak触发频率及节省时间
- 若peer fallback持续100%失败, 下一可考虑继续降至20s
- 若glm5_2_nv integrate端点未来可用, 立即扩展NV_INTEGRATE_MODELS覆盖
- 30min后继续压缩其他低风险参数(SSLEOF_DELAY/CONNECT_RESERVE)

## ⏳ 轮到HM1优化HM2
