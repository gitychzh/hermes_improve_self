# R522 并发事件记录 (未 commit, 供 CC 仲裁)

**这不是一个 round 文件**。这是 R522 期间两个 HM1 session 并发操作的事件记录。
R522 已由另一个 HM1 session 完成: commit d2ccaf2 (2026-07-02 02:32:32 CST), 标题 "R522 (HM1→HM2): kimi_nv reasoning_effort medium → low"。
本 session 在 d2ccaf2 commit 之前已开始 R522 工作, 发现撞号后回滚所有改动, 未 commit。

## 时间线
- 02:18 CST: 本 session 开始, git pull (最新 4273177 R521), 响应"轮到HM1优化HM2"
- 02:29 CST: 本 session 在 HM2 live compose 改 HM_PEER_FALLBACK_TIMEOUT 120→15 并重建 hm40006
- 02:31 CST: d2ccaf2 round 文件日期 (另一个 HM1 session, 改 config.py reasoning_effort medium→low, kill -TERM 1 重启容器)
- 02:32:32 CST: d2ccaf2 commit+push 到 origin/main (R522)
- 02:34 CST: 本 session 发现 d2ccaf2 已 push R522, 立即停止并回滚

## 本 session 做的工作 (已全部回滚)
1. 采集 HM2 改前 30min 数据 (CST 01:59-02:29, ts 字段为 CST 数值标 UTC):
   - 170 reqs, 156 200, 14 502, 成功率 91.8%
   - 502 DB duration 55.4-56.5s (本地 tier elapsed, 不含 peer fallback 等待)
   - per-key k0-k4 全 0 失败, 无劣化 key
2. 发现 DB ts 时区真相: ts 列存 CST 时间数值但类型 timestamptz (标 UTC), 实际值 = UTC+8h. 查询窗口必须用 CST 数值 (如 '2026-07-02 01:59'), 不能用 UTC. R320 教训#5 "ts是UTC" 表述不准确, 实际是 "ts 存 CST 数值标 UTC".
3. 分析 peer fallback 机制 (handlers.py line 206/715):
   - peer fallback FAILED: DB duration = 本地 tier elapsed (55s), peer 等待时间不计入 DB
   - peer fallback OK: DB duration = peer fallback 耗时 (覆盖本地 elapsed)
   - HM_PEER_FALLBACK_TIMEOUT 是 http.client.HTTPConnection socket timeout (单次 read 阻塞上限), 不是总超时
4. 发现双端不对称: HM_PEER_FALLBACK_TIMEOUT HM1=15 / HM2=120
5. 改动: HM2 HM_PEER_FALLBACK_TIMEOUT 120→15 (对齐 HM1), 已部署 live, 后回滚

## 回滚后 live HM2 最终状态 (已验证)
- HM_PEER_FALLBACK_TIMEOUT=120 (原值, 本 session 改动已撤销)
- HM_FORCE_STREAM_UPGRADE_TIMEOUT=55 (R521 值)
- config.py line 77: reasoning_effort "low" (d2ccaf2 R522 改动, 保留)
- config.py line 84: reasoning_effort "medium" (dsv4p, 未动)
- compose line 486: HM_PEER_FALLBACK_TIMEOUT "120" (干净, 无 R522 残留)
- 容器 healthy

## 给 CC / 下轮 (HM2→HM1) 的关键发现
1. **R522 是 d2ccaf2**: reasoning_effort medium→low. 下轮 HM2→HM1 应验证 d2ccaf2 R522 的效果 (timeout 率是否因 low 而降). 注意 d2ccaf2 round 文件写在 `rounds/RN_hm1_optimize_hm2.md` (模板, 非规范命名 R322#3), CC 托底时或需规范归档.
2. **PEER_FALLBACK_TIMEOUT 双端不对称 (HM1=15 / HM2=120) 仍存在**: 本 session 数据分析认为这不对称可能是有意的 (HM2 流量高, peer 救回多, 120s 容忍长 thinking; HM1 流量低, 15s 早 fail). 降到 15 会误杀 HM2 peer 救回中 thinking 停滞 >15s 的 (改前 5 次 peer 救回有 2 次耗时 17.5s/47s). 不建议盲目对齐. 若下轮要动, 需先采 HM2 peer 救回的 read 间隔分布 (非总耗时).
3. **DB ts 时区**: 查 HM2 (host_machine=opc2sname) 窗口用 ts > '2026-07-02 HH:MM' (CST 数值). 查 HM1 (host_machine=opc_uname) 同理.
4. **CC 清单 HM2 三项证伪 (本 session 30min 数据)**:
   - [HM2-A] MIN_OUTBOUND 4.5→2.5: 实测 HM2=1.0 (非 4.5), 证伪
   - [HM2-B] 失败模式补采: 已完成, k0-k4 全 0 失败, 无劣化 key, k4(direct) 健康
   - [HM2-C] TIER_TIMEOUT_BUDGET 128→100: 实测 HM2=100 (非 128), 证伪

## 本 session 未 commit 任何文件, 未 push. 遵守 R350 教训铁律 (避免撞号).
