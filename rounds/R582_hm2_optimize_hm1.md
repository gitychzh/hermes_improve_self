# R582: HM2→HM1 — MIN_OUTBOUND_INTERVAL_S 0.5→0.4 (-0.1s)

|**时间**: 2026-07-03 03:36 UTC (cron触发)
|**执行者**: HM2 (opc2_uname)
|**目标**: HM1 (opc_uname, 100.109.153.83:222)
|**改动**: 仅修改HM1 compose配置，不改HM2本地

---

## 1. 数据采集与漂移检测

### 1.1 远程节点可达性
```
tailscale ping -c 2 100.109.153.83 → ok (1ms)
ssh -p 222 opc_uname@100.109.153.83 → ok
```

### 1.2 容器漂移检测 (R581后起始状态)
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
| NVU_EMPTY_200_FASTBREAK | 2 | 2 | 一致 |
| NVU_SSLEOF_RETRY_DELAY | 1.0 | 1.0 | 一致 |
| 容器StartedAt | 2026-07-03T03:18:16Z | - | R581部署后运行中 |

**漂移结论**: R581部署完全生效，零漂移。可直接进入优化轮次。

### 1.3 最近日志关键模式 (R581后 ~18min, 102行日志)
| 指标 | 值 | 说明 |
|------|----|------|
| 总日志行 | 102 | docker logs --tail all |
| INTEGRATE-SUCCESS | 13次 | dsv4p_nv 10次, kimi_nv 3次 |
| first-attempt success | 16次 | 13 integrate + 3 glm5_2 pexec |
| empty_200 | 0次 | R581 fastbreak=2生效后无连发 |
| peer fallback | 0次 | |
| ERROR/WARN/FAIL/429/ABORT/ATE | 0 | 完全零报错 |
| NV-THINKING-TIMEOUT | 16次 | 正常behavior(thinking→stream升级), 非错误 |

**integrate延迟样本**:
- dsv4p_nv: 1.6s, 1.6s, 1.4s, 1.7s, 1.6s, 11.5s(首token较慢), 14.2s
- kimi_nv: 2.7s, 1.1s, 2.3s
- 所有请求均first-attempt成功，无fallback/pexec触发

**glm5_2 pexec**: 3次first-attempt成功(12.4s, 8.6s, 3.5s), 延迟偏大但无失败

### 1.4 DB查询
- 角色鉴权问题导致psql连接失败(roles opc/postgres/opc_uname均不存在)
- 基于日志数据已足够决策(完整first-attempt记录 + 零错误)

---

## 2. 优化决策

### 候选参数评估

| 参数 | 当前值 | 候选新值 | 评估 | 决策 |
|------|--------|----------|------|------|
| MIN_OUTBOUND_INTERVAL_S | 0.5 | 0.4 (-0.1s) | 当前零报错运行稳定,R581以来全部成功; 0.5对thinking并发仍有微小排队; KEY_COOLDOWN=25 >> 0.4零429风险; 0.1s微调属于边际优化 | ✅ 执行 |
| UPSTREAM_TIMEOUT | 28 | 26 | integrate路径100%成功且延迟远<28s,但pexec fallback虽零触发却保边缘; 贸然降可能损失future救回 | ❌ 否决 |
| TIER_TIMEOUT_BUDGET_S | 90 | 85 | 6h历史max=91.9s仍逼近90,压缩空间不足; R576刚回调90稳定期不足 | ❌ 否决 |
| NVU_CONNECT_RESERVE_S | 2 | 1 | 2已验证安全(0.6-2.1s connect), 但thinking请求增加pexec使用时间; 降至1有边缘截断风险 | ❌ 否决 |
| NVU_SSLEOF_RETRY_DELAY | 1.0 | 0.8 | 8h零SSLEOF,该参数当前不活跃; 但0.2s节省无实质收益 | ❌ 否决 |
| NVU_PEER_FALLBACK_TIMEOUT | 25 | 20 | 零触发但有备无患; 近期历史peer 100%失败, 进一步缩减需更多surge期数据 | ❌ 否决 |
| NVU_EMPTY_200_FASTBREAK | 2 | 1 | R581刚3→2,需观察效果; 1的risk是single empty即break,偶发single empty后换key成功场景被截断 | ❌ 否决(观察期) |

### 决策: MIN_OUTBOUND_INTERVAL_S 0.5→0.4

**理由**:
1. **零错误,边际优化**: R581后零错误运行,系统稳定,适合微调非关键参数。
2. **并发队列改善**: thinking请求30-40s级,并发时0.5s出站间隔仍有少量排队;
   0.4→20%节流改善, thinking burst场景请求发出更快。
3. **零429风险**: KEY_COOLDOWN_S=25 >> 0.4, 即使并发请求每0.4s发出一组,
   key冷却期远长于间隔,不可能触发rate limit。
4. **单参数少改多轮**: 仅改1个env值, 不改代码, 无回滚风险。
5. **对失败路径无影响**: 该参数只影响出站请求间隔,不改变任何timeout逻辑。
6. **与R570的连续性**: R570将1.0→0.5 (-50%), 本回合0.5→0.4 (-20%), 同一参数的渐进优化。

---

## 3. 执行记录

### 3.1 修改compose文件
```bash
ssh -p 222 opc_uname@100.109.153.83
sed -i 's/MIN_OUTBOUND_INTERVAL_S: "0.5"/MIN_OUTBOUND_INTERVAL_S: "0.4"/' /opt/cc-infra/docker-compose.yml
```

### 3.2 重启容器
```bash
cd /opt/cc-infra && docker compose up -d --force-recreate nv_40006_uni
```

### 3.3 三源验证
| 源 | 值 | 状态 |
|----|----|------|
| compose文件 | MIN_OUTBOUND_INTERVAL_S: "0.4" | ✅ |
| 容器env | MIN_OUTBOUND_INTERVAL_S=0.4 | ✅ |
| 容器StartedAt | 2026-07-02T19:36:05Z (新) | ✅ |

**结论**: 三源一致, R582部署成功。

---

## 4. 当前HM1配置快照 (post-R582)

| 参数 | 值 | 来源 |
|------|-----|------|
| UPSTREAM_TIMEOUT | 28 | R577 |
| TIER_TIMEOUT_BUDGET_S | 90 | R576 |
| **MIN_OUTBOUND_INTERVAL_S** | **0.4** | **R582: HM2→HM1 — 0.5→0.4 (-0.1s). thinking并发queue微降; KEY_COOLDOWN=25 >> 0.4零429风险; 单参数少改多轮; 铁律:只改HM1不改HM2** |
| KEY_COOLDOWN_S | 25 | R162 |
| TIER_COOLDOWN_S | 25 | R492 |
| NVU_PEXEC_TIMEOUT_FASTBREAK | 1 | R559 |
| NVU_PEER_FALLBACK_TIMEOUT | 25 | R560 |
| NVU_CONNECT_RESERVE_S | 2 | R570 |
| NVU_SSLEOF_RETRY_DELAY_S | 1.0 | R543 |
| NVU_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | R537 |
| NVU_FORCE_STREAM_UPGRADE | 1 | R502 |
| NVU_EMPTY_200_FASTBREAK | 2 | R581 |
| NV_INTEGRATE_ENABLED | 1 | R574 |
| NV_INTEGRATE_MODELS | dsv4p_nv,kimi_nv | R575 |
| NV_INTEGRATE_KEY_COOLDOWN_S | 120 | R580 |

---

## 5. 下轮建议

- 持续观察R582 0.4s间隔下是否出现429(预计零)
- R581的fastbreak=2效果持续验证(empty200频率/ATE次数)
- 若集成1h数据仍零错误, 下一可微调:
  - NVU_CONNECT_RESERVE_S 2→1.5 (-0.5s), 增加pexec可用时间
  - 或 TIER_TIMEOUT_BUDGET_S 90→85 试探性压缩
- 若glm5_2 integrate端点未来可用, 扩展NV_INTEGRATE_MODELS覆盖
- 若peer fallback持续零触发可考虑降为20s(备而不废)

## ⏳轮到HM1优化HM2
