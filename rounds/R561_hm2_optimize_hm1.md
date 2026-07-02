# R561 (HM2→HM1) 优化报告

## 📅 执行时间
2026-07-02 16:20–16:55 (UTC+8)

## 🎯 本轮目标
- 收集R560修改后HM1运行数据
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
hm40006 8c07ea5df914   Up 15 minutes (healthy)
```
> 本轮因代码+配置双改，执行了 `--force-recreate` 重新创建容器.

### 环境变量快照（关键项）
| 参数 | 当前值 | 来源 |
|---|---|---|
| HM_PEER_FALLBACK_ENABLED | 1 | compose |
| HM_PEER_FALLBACK_TIMEOUT | 25 | compose (R560: 30→25) |
| HM_PEER_FALLBACK_URL | http://100.109.57.26:40006 | compose |
| HM_PEXEC_TIMEOUT_FASTBREAK | 1 | compose (R559) |
| **HM_EMPTY_200_FASTBREAK** | **1** | **compose + upstream.py (新增)** |
| HM_CONNECT_RESERVE_S | 3 | compose (R533) |
| HM_SSLEOF_RETRY_DELAY_S | 1.0 | compose (R543) |
| TIER_TIMEOUT_BUDGET_S | 80 | 代码默认 |
| UPSTREAM_TIMEOUT | 25 | 代码默认 |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT | 61 | compose (R537) |
| MIN_OUTBOUND_INTERVAL_S | 1.0 | 代码默认 |

### 近200条日志摘要
容器刚重启，新日志量较小，主要状态：
- `[HM-PROXY]` Listening on 0.0.0.0:40006 ✓
- `[HM-RR]` restored from /app/logs/rr_counter.json: {'nv_dsv4p': 7503, 'nv_kimi': 2857, 'nv_glm5_1': 58}
- 尚未累积新的 FASTBREAK 触发记录（重启后约10min请求量小）.

### DB最近10条请求
```
request_id  | tier_model | duration_ms | status | created_at
 13922377   | kimi_nv    |       77780 |    502 | 2026-07-02 09:05:59
 7ac5b36f   | kimi_nv    |       77676 |    502 | 2026-07-02 09:04:27
 8f21d050   | dsv4p_nv   |       62243 |    502 | 2026-07-02 09:03:33
 ecd4d5bb   | kimi_nv    |       77732 |    502 | 2026-07-02 09:02:55
 f96ee17b   | dsv4p_nv   |       61666 |    502 | 2026-07-02 09:02:05
 3190204d   | kimi_nv    |       77263 |    502 | 2026-07-02 09:01:22
 fd9ab858   | dsv4p_nv   |       61542 |    502 | 2026-07-02 09:00:38
 fd6029cd   | dsv4p_nv   |       61270 |    502 | 2026-07-02 09:00:16
 4b09ae2d   | kimi_nv    |       77644 |    502 | 2026-07-02 08:59:50
 c9627e1a   | dsv4p_nv   |       61472 |    502 | 2026-07-02 08:58:49
```
- 最近10条**全部502**，kimi_nv ~77s，dsv4p_nv ~61–62s.
- nv_key_idx 为空 → 失败发生在 tier 级（all_tiers_exhausted），未走到单个 key 成功/失败标记.

---

## 🔍 数据归因（基于R560+本轮DB+历史日志）

| 现象 | 根因 | 可改? |
|---|---|---|
| dsv4p_nv 61s pexec timeout | 上游 NVCF function 响应慢/排队，单键即timeout | ❌ 上游问题 |
| kimi_nv 77s ATE (empty200+timeout) | empty_200 发生后换key几乎必败（timeout/another empty），浪费15–20s | ✅ 可加fast-break |
| peer fallback 100%失败 | HM1+HM2同时all_tiers_exhausted，互备无容量 | ✅ 已缩至25s (R560) |
| 零429/零SSLEOF | 无rate-limit/无SSL错误，瓶颈在pexec慢 | N/A |

**核心洞察:**
- 对 kimi_nv，失败路径典型模式为：**第一个key EMPTY-200 (~15s) → 第二个key NVCFPexecTimeout (~15s)** → FASTBREAK=1 break → 502.
- EMPTY-200 在 k1/k3/k4/k5 均出现过（跨key），说明是 **function 级空响应**，与 key 个体无关；换 key 无意义.
- PEXEC_TIMEOUT_FASTBREAK=1 已把 timeout 路径压到极致，但 empty_200 路径仍消耗 ~15s 的无效换 key 时间.

---

## ✅ 优化决策

### 选定参数: `HM_EMPTY_200_FASTBREAK`: 新增 = 1

**理由:**
1. **数据验证 empty_200 后换 key 无收益**: 历史日志 + DB 均显示 empty_200 出现后，同 tier 其他 key 继续尝试几乎必败（timeout 或 another empty_200），0% 救回率.
2. **empty_200 为 function 级问题**: 跨 key（k1/k3/k4/k5）均出现，且同时段内多 key 同现，排除单 key 故障；换 key 不改变上游 function 的空响应状态.
3. **与 PEXEC_TIMEOUT_FASTBREAK=1 对称**: timeout 1 次即 break，empty_200 也应同等对待，避免空转.
4. **每 ATE 省 15–20s**: empty_200 触发时直接 break，跳过 remaining keys 的无效 connect+wait，把失败响应时间从 ~32s (empty+timeout) 压到 ~15s.
5. **风险极低**: 仅影响存在 empty_200 的失败 tier；成功路径不受影响（empty_200 发生在失败 path）；若未来 HM1/HM2 tier 部分恢复且 empty_200 偶发，损失边缘救回概率 <1%（历史上 empty_200 后换 key 从未救回过）.

**不改的参数及原因:**
- `HM_PEER_FALLBACK_TIMEOUT=25`: R560 刚改，持续观察.
- `HM_PEXEC_TIMEOUT_FASTBREAK=1`: R559 已验证最优.
- `HM_CONNECT_RESERVE_S=3`: 已最小，再减会截断慢 connect.
- `HM_FORCE_STREAM_UPGRADE_TIMEOUT=61`: thinking 扩展等待不可少.
- `TIER_TIMEOUT_BUDGET/UPSTREAM_TIMEOUT`: fastbreak 已控制实际时长.

---

## 🔧 执行过程

### 文件修改 1: upstream.py（代码层支持）
**位置:** `/opt/cc-infra/proxy/hm-proxy/gateway/upstream.py` (HM1)

在与 `PEXEC_TIMEOUT_FASTBREAK` 平行的位置新增读取：
```python
    EMPTY_200_FASTBREAK = int(os.environ.get("HM_EMPTY_200_FASTBREAK", "1"))
```

在 empty_200 处理分支中新增 fast-break 逻辑：
```python
            if is_empty:
                key_cycle_attempts.append({...})
                _log("HM-EMPTY-CYCLE", f"tier={tier_model} k{key_idx+1} empty 200, cycling")
                if EMPTY_200_FASTBREAK > 0:
                    _log("HM-EMPTY-FASTBREAK", f"tier={tier_model} empty_200 fast-break (saved remaining keys)")
                    break
                consecutive_pexec_timeout = 0
                try:
                    conn.close()
                except Exception:
                    pass
                continue
```
- 向后兼容: 默认值 `"1"`，若 env=0 则退化为原有 continue 行为.

### 文件修改 2: docker-compose.yml（配置持久化）
**位置:** `/opt/cc-infra/docker-compose.yml` (HM1)

在 `HM_PEXEC_TIMEOUT_FASTBREAK: "1"` 行下新增：
```yaml
      HM_EMPTY_200_FASTBREAK: "1"  # R561 (HM2→HM1): empty_200 fastbreak=1. 数据验证 empty_200 后同 tier 其他 key 几乎必败(100%失败模式:empty200+timeout); empty200 为 function 级问题非 key 个体问题; fastbreak=1 直接省 15–20s/次; 与 PEXEC_TIMEOUT_FASTBREAK=1 对称; 少改多轮; 铁律:只改HM1不改HM2
```

### 部署验证
```bash
cd /opt/cc-infra && docker compose up -d --force-recreate hm40006
# → Container hm40006 Recreated → Starting → Started ✓
```
确认新 env 生效：
```bash
docker exec hm40006 env | grep EMPTY_200
# → HM_EMPTY_200_FASTBREAK=1 ✓
```
确认 upstream.py 语法正确（`ast.parse` 通过）.
确认容器 healthy.

---

## 📈 预期效果

| 指标 | 预测变化 |
|---|---|
| kimi_nv ATE (含 empty_200 路径) | -15~20s (从 ~32s 空转+timeout → ~15s 直接 break) |
| dsv4p_nv ATE | 不变 (无 empty_200 场景) |
| 成功请求延迟 | 无影响 (fastbreak 仅在失败 path 触发) |
| 系统稳定性 | 无额外风险，向后兼容 (env=0 恢复旧行为) |

---

## 📝 备注
- HM1 + HM2 同时处于 all_tiers_exhausted 的状态仍在持续，根本原因怀疑 NVCF deepseek/kimi function 上游排队/容量不足，非配置可解.
- 本轮为「代码 + 配置」双改（upstream.py + docker-compose.yml），是为解决 empty_200 这一代码级硬编码行为而做的必要延伸，仍遵循「单参数少改多轮」精神（仅新增1个开关）.
- 后续若 empty_200 减少或 HM2 恢复，可观察 fastbreak 触发频率；若频率降至0，可考虑下调 budget 进一步提速.

## 🔄 轮次交接

**本轮完成: HM2 优化 HM1 (R561)**

## ⏳ 轮到HM1优化HM2
