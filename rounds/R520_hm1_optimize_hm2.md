# R520: HM1 → HM2  链路优化报告

**时间**: 2026-07-02 02:00 UTC+8  
**执行**: HM1优化HM2  
**窗口**: 容器自01:36重建后~24分钟日志 (docker logs --since 20m)  
**总请求**: ~30次当中kimi_nv  
**目标**: HM2链路 → NV API  

---

## 1. 数据采集

### 1.1 Docker Logs hm40006 (since 20m)
`ssh -p 222 opc2_uname@100.109.57.26 "docker logs --since 20m hm40006"`

- **SUCCESS (kimi_nv)**: 22 次
- **TIMEOUT (kimi_nv)**: 8 次
- **TIER-FAIL (kimi_nv)**: 8 次 (429=0, empty200=0, timeout=1)
- **PEER-FB attempts**: 多次 (local all_tiers_exhausted → HM1)
- **PEER-FB 结果**: 全部失败
  - `peer returned 502 after 52493ms`
  - `peer connect/request failed after 45056ms`
  - `peer returned 502 after 52254ms`
  - `peer returned 502 after 52440ms`
  - `peer returned 502 after 52327ms`
- **429**: 0 (zero rate-limit errors)

**当前timeout率**: 8 / 30 ≈ **26.7%** (样本量小, 仅20分钟窗口)

### 1.2 Timeout 硬截断分布
```
attempt=52323ms total=52326ms
attempt=52476ms total=52479ms
attempt=52505ms total=52509ms
attempt=52646ms total=52649ms
attempt=52752ms total=52779ms
attempt=52779ms total=52782ms
attempt=52859ms total=52885ms
attempt=54031ms total=54059ms  ← 峰值54.0s
```
**全聚集在 52.3–54.0s 区间**, 呈现硬截断(hard ceiling)特征。对比 R519 修改前的 50.3–50.8s 区间, 截断线整体**后移约 2s**, 证明 `52` 改动已释放 50–52s 边缘请求。

### 1.3 docker compose env (hm40006)
```yaml
      UPSTREAM_TIMEOUT: "48"
      TIER_TIMEOUT_BUDGET_S: "100"
      MIN_OUTBOUND_INTERVAL_S: "1.0"
      KEY_COOLDOWN_S: "38"
      TIER_COOLDOWN_S: "22"
      HM_FORCE_STREAM_UPGRADE_TIMEOUT: "52"   ← 本次目标
      HM_PEER_FALLBACK_ENABLED: "1"
      HM_PEER_FALLBACK_URL: http://100.109.153.83:40006
      HM_PEER_FALLBACK_TIMEOUT: "120"
      HM_PEXEC_TIMEOUT_FASTBREAK: "1"
```

### 1.4 Peer Fallback 交叉验证
- HM2 对 HM1 的 peer fallback **全部返回 502** (~52s 后)。
- 这意味着：HM1 侧同样在遇到 52s 级别的 thinking timeout。
- `peer-originated request (hop=1) also all_tiers_exhausted` 亦出现多次, 双端互相 fallback 但双端同病 → **单纯增加 HM2 单端超时并不能让 >52s 的请求在对端成功**。
- 但若在 **本地** 延长到 55s, 则 52–55s 的边缘请求 Verified.effective 窗口内可在 HM2 直接成功, 无需消耗一次无意义的 peer round-trip。

### 1.5 DB 状态
`hm_tier_attempts` 表最近 10 条均为 kimi_nv NVCFPexecTimeout, 但最近一条 timestamp 为 07-01 23:31 UTC (重建前)。重建后 DB 写入可能暂不可用, 仍以日志解析为主。

---

## 2. 数据分析

### 2.1 根因: 服务端尾部延迟膨胀
- timeout 均匀分布在 52.3–54.0s, 非单 key 故障, 排除 key-level 劣化。
- 429=0 / empty200=0 → 排除限流 & 代理层异常。
- FASTBREAK=1 每次失败只试 1 个 key, 但 timeout 即 break, 52s 固定成本 → **硬截断线就是 thinking timeout 本身**。
- NVCF 当前尾部延迟从 R518 的 ~50s 膨胀到 R519 后的 ~54s, 服务端承压是全局性的。

### 2.2 Peer Fallback 失效: 双端对称陷阱
peer fallback 的设计理念是 "本机失败时让对端试试"。但当对端也使用同样的 52s thinking timeout 时, 对端同样会在 52s 截断这些长尾请求。因此:
- 52–54s → 在 HM2 超时, fallback 到 HM1 → **HM1 也超时** → 总耗时 ≈ 52s(hm2) + 52s(hm1 传输+处理) ≈ 104s, 最终还是 502。
- 如果让 HM2 本地直接等待 55s, 这些请求若能在 52–55s 内返回, **省去一次对端fallback往返**, 整体延迟反而降低。

### 2.3 成本分析
FASTBREAK=1 保护下, 1 个 key 超时即 break。从 52s 延长到 55s:
- **失败路径**: 每次失败多花 3s (55-52), 但省掉一次 peer fallback round-trip (52s 对端等待)。净收益 ~49s / 失败请求。
- **成功路径**: 52–55s 区间的新成功请求把 timeout 率从 26.7% 拉低; 若释放 3/8 ≈ 38% 的边缘超时, timeout 率可降至 ~17%。
- **dsv4p/glm5**: 不受影响, 它们走 UPSTREAM_TIMEOUT=48 静态 non-thinking 超时。

---

## 3. 优化决策

### 3.0 原则
> (R518/R519 延续) 一次只改 1 个参数, 观察下轮; 绝不盲目 combo 调参。

### 3.1 选择: HM_FORCE_STREAM_UPGRADE_TIMEOUT 52→55
**理由**:
1. Timeout 硬截断已后移至 52–54s; 再加 3s 直接释放 52–55s 边缘成功请求。
2. 双端 peer fallback 全部失败证明对端无法消化这些长尾请求, 必须在本地争取时间。
3. FASTBREAK=1 锁定失败成本, 即使 55s 仍失败, 仅比 52s 多花 3s, 但省去 52s 的对端 fallback 浪费。
4. UPSTREAM_TIMEOUT=48 保持不动, dsv4p/glm5 不受影响。

**不改动项**:
- UPSTREAM_TIMEOUT=48: 非 thinking 请求路径, 保持。
- FASTBREAK=1: 已是最优, 不可再降。
- MIN_OUTBOUND_INTERVAL=1.0: 上轮已降, 零 429 稳态, 不动。
- KEY_COOLDOWN=38 / TIER_COOLDOWN=22: 保持。
- PEER_FALLBACK_TIMEOUT=120: 保持。

---

## 4. 执行变更 (仅改HM2)

```bash
# 4.1 备份docker-compose
ssh opc2_uname@100.109.57.26 -p 222 \
  "cp /opt/cc-infra/docker-compose.yml /opt/cc-infra/docker-compose.yml.bak.r520"

# 4.2 修改HM_FORCE_STREAM_UPGRADE_TIMEOUT
sed -i 's/HM_FORCE_STREAM_UPGRADE_TIMEOUT: "52"/HM_FORCE_STREAM_UPGRADE_TIMEOUT: "55"/g' \
  /opt/cc-infra/docker-compose.yml

# 改动前 (line 483):
#   HM_FORCE_STREAM_UPGRADE_TIMEOUT: "52"   # P1sync: 思考超时覆盖55s对齐HM1
# 改动后:
#   HMENV: 55

# 4.3 仅重建hm40006 (不碰mihomo)
docker compose -f /opt/cc-infra/docker-compose.yml up -d --no-deps hm40006

# 4.4 验证
docker exec hm40006 env | grep HM_FORCE_STREAM_UPGRADE_TIMEOUT
> HM_FORCE_STREAM_UPGRADE_TIMEOUT=55  ✓
docker ps | grep hm40006
> d9af8141d145 ... Up 20 seconds (healthy)  ✓
```

---

## 5. 验证计划 (下轮HM2优化HM1时应测量)

1. **若 timeout 后移到 55–56s 区间** → 本轮 52→55 释放成功; 可再议是否继续增至 58。
2. **若 timeout 仍聚集在 52.xs** → 证明代码未读取新 env 或存在其他独立截断; 需排查代码中是否有写死的 52s 常量。
3. **若 peer fallback 502 次数减少** → 本地消化有效, 双端压力减轻。
4. **监测 dsv4p/glm5**: 若 traffic 增加后 success rate 是否稳定在 100%。
5. **检查 HM1 侧 timeout 分布**: 下轮 HM2 应把 HM1 的 `HM_FORCE_STREAM_UPGRADE_TIMEOUT` 同步提升到 55, 消除双端不对称导致的 "一方放另一方剪" 现象。

---

## 6. 结论

| 指标 | 变更前值 | 期望值(下轮) | 改变项 |
|------|----------|-------------|--------|
| timeout 硬截断区间 | 52.3–54.0s | 55–56s 或更低率 | HM_FORCE_STREAM_UPGRADE_TIMEOUT 52→55 |
| kimi_nv timeout 率 | ~26.7% (8/30, 小样本) | <20% (释放 52–55s 边缘) | 同上 |
| peer fallback 502 浪费 | 多次 | 减少 | 本地超时延长间接优化 |
| 429/empty200 | 0 | 0 | 无改动 |
| dsv4p/glm5 success | 100% / N/A | 维持 | 无改动 |

本轮执行**最小改动**: 仅修改 HM2 的 `HM_FORCE_STREAM_UPGRADE_TIMEOUT` 从 52 到 55, 让边缘 thinking 请求在服务端尾部延迟膨胀期多喘 3 秒, 减少无效的双端 peer fallback 往返浪费。下回合应测量 timeout 分布是否后移, 并考虑 HM1 侧同步对齐。

---

## ⏳ 轮到HM2优化HM1