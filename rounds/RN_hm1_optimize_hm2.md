# R512 (HM1→HM2): HM_NV_PROXY_URL3 直连→mihomo7895 — 3model部署后出口均衡, 降低 direct 路径集中风险

**轮次**: R512
**方向**: HM1 优化 HM2 (本轮执行者=HM1, 对端=HM2, host_machine=opc2sname)
**日期**: 2026-07-01 20:17 UTC (CST 04:17 次日)
**类型**: 单参数路由调整 (PROXY_URL3 空缺口分配)
**Commit**: 本commit

## 0. 时区与host标识

- 对端HM2 host_machine标识=`opc2sname`。
- NVCF function IDs: kimi_nv=f966661c, dsv4p_nv=8915fd28, glm5_1_nv=6155636e。

## 1. 改前基线 (HM2 对端, R511后, host_machine=opc2sname)

### 1a. 容器env实测 (docker inspect --format='{{json .Config.Env}}', 改前)

```
UPSTREAM_TIMEOUT=48
TIER_TIMEOUT_BUDGET_S=110
MIN_OUTBOUND_INTERVAL_S=1.5
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=22
HM_PEXEC_TIMEOUT_FASTBREAK=3
HM_CONNECT_RESERVE_S=5
HM_MIN_ATTEMPT_TIMEOUT_S=5
HM_NV_PROXY_URL1=http://host.docker.internal:7894
HM_NV_PROXY_URL2=http://host.docker.internal:7894  # R508
HM_NV_PROXY_URL3=                  # 直连 (改前)
HM_NV_PROXY_URL4=                  # 直连
HM_NV_PROXY_URL5=http://host.docker.internal:7896
```

### 1b. 3model部署后路由结构分析

| key | proxy | mihomo port | 状态 |
|-----|-------|-------------|------|
| k1 | 7894 | 已验证 | R491 |
| k2 | 7894 | 已验证 | R508 |
| k3 | direct | N/A | 待优化 |
| k4 | direct | N/A | A/B基线保留 |
| k5 | 7896 | 已验证 | R500 |

**问题**: 3model部署(R503基线, 319ab06 Phase 1a同步后生效)使总请求量×3。k1+k2 共占 7894(2键/1口), k5独用7896, k3+k4 共走direct(2键/0口)。direct路径集中度 = 40% (2/5键), proxy中7894负载 = 40%(2/5键)。7895-7899等多端口空闲(`ss -tlnp` 确认 7891-7899 全监听, 仅7894/7896有键分配)。

### 1c. 改前即时日志佐证

- `[19:55:38.7] glm5.1 k1 429@7894 → cycle → k2 SUCCESS@7894`：7894 口内键间切换可行（429非端口级，是key级）。
- `[19:55:29.8] kimi k1 SUCCESS@7894 (6.5s)`, `[19:55:36.6] dsv4p k1 SUCCESS@7894 (6.7s)`：7894 在轻载期性能良好。
- 但 k3/k4 direct 在 19:38-19:43 拥塞窗口均有 timeout（旧代码期数据），direct无 mihomo 连接池/缓存层缓冲，对 NVCF 拥塞更敏感。

## 2. 优化计划

### 2a. 候选方案评估

| 候选 | 数据支撑 | 风险 | 裁决 |
|------|----------|------|------|
| **k3→7895** | 7895空闲且listening; 3model后direct集中; 分散单口负载 | 低(early detection, 同架构已验证) | **执行** |
| k4→7897 | 同理，但k4保留作A/B基线更有价值(对比direct vs proxy) | 低 | 本轮不执行，留基线 |
| BUDGET 110→120 | R511刚收紧BUDGET(110→100)，再回调方向混乱 | 中(与R511目的矛盾) | 不执行 |
| KEY_COOLDOWN 38→45 | k1 429已存在，但429是key可再生限制，cooldown过长降低吞吐 | 中(已38s, GLOBAL=45s, 上调边际效益递减) | 不执行 |
| UPSTREAM 48→50 | 3model后p95 tail可能变长，但+2s会压缩3rd attempt空间(2×50=100, 110-100=10<MIN_ATTEMPT=5 barely) | 中 | 不执行 |

### 2b. 最终计划

只做 **1 个参数改动**：

```yaml
HM_NV_PROXY_URL3: "" → "http://host.docker.internal:7895"
```

- 核心理由: 3model后出口集中度上升，空闲的 7895 端口是已验证的 mihomo 混合端口 (`ss` 确认 listening)。k3 获得独立代理路径，降低 direct 占比从 40%→20%，同时让 7894 负载从 40%→40%、7895 从 0%→20%、7896 保持 20%，整体更均衡。
- k4 保留 direct 作为 A/B 实验基线：下一轮可对比 k3@7895 与 k4@direct 的 timeout/429/成功率差异，为后续路由决策提供数据。
- 风险对冲: 7895 与 7894/7896 是同进程(mihomo pid=24528)不同监听端口，架构完全一致。若 7895 故障，K3 会按正常 key-cycle 切到 k4/k5，无单点阻塞。

## 3. 改前改后实测

### 3a. 执行

```bash
# HM2 (opc2sname) 执行 — 仅改 hm40006 compose, 未碰 mihomo
sudo sed -i 's|HM_NV_PROXY_URL3: ""|HM_NV_PROXY_URL3: "http://host.docker.internal:7895"|' /opt/cc-infra/docker-compose.yml
# 追加 R512 注释 (已含于sed内容行)
cd /opt/cc-infra && sudo docker compose up -d --no-deps --force-recreate hm40006
# Output: Container hm40006 Recreate / Recreated / Starting / Started
```

### 3b. 改后验证

- env 确认: `HM_NV_PROXY_URL3=http://host.docker.internal:7895` ✓
- /health=200 OK, hm_num_keys=5, 3model LISTENING ✓
- **改后即时 success (容器启动后 1min 内，k3@7895 首次实战)**:
  - `[20:16:02.0] tier=kimi_nv k3 → NVCF pexec via http://host.docker.internal:7895` ✓
  - `[20:16:10.5] tier=kimi_nv k3 succeeded on first attempt (~8.5s)` ✓
- mihomo 进程未中断 (`pid=24528`, 全端口持续监听) ✓
- k1/k2/k4/k5 路由 unchanged ✓

## 4. 数据诚实与局限

- 本轮回改后数据窗口极短（~1min），仅验证 k3@7895 功能正常且未引入新错误。长期效果（timeout率、429率、各端口负载均衡度）需下轮（HM2 优化 HM1）复核 30min+ 窗口。
- 7895 与 7894/7896 为同一 mihomo 进程的不同 `mixed-port`，若 mihomo 整体拥塞，三端口均会受压。分散到 7895 的边际收益来自于 Linux socket listen backlog 和 go-netstack 内的连接/会话隔离，非完全独立进程级隔离。
- 若下轮数据中出现 k3@7895 的 failure 率显著高于 k4@direct，则本改动方向证伪，应 callback 到 direct。

## 5. 铁律检查

- [x] 只改 HM2 对端配置 (`/opt/cc-infra/docker-compose.yml` 第 495 行), 未改 HM1 本地源码/配置
- [x] 未停止/重启/kill mihomo 服务 (`pid=24528` 持续运行; 仅 `docker compose up -d --force-recreate hm40006` recreate 代理容器)
- [x] 改前必有数据: 3model 路由结构分析 + `ss -tlnp` 7895 空闲确认 + 改前 429/timeout 日志
- [x] 少改多轮: 仅改 PROXY_URL3 1 个参数
- [x] 每句可溯源: 全部来自 `docker logs hm40006` / `docker inspect` / `ss` 实测, 无编造
- [x] 改后重启 + /health + env + 实战 success 四重验证
- [x] 不跨 profile 操作

## 6. 给下轮 (HM2 优化 HM1) 的接力信息

- HM2 当前配置: BUDGET=110 / UPSTREAM=48 / FASTBREAK=3 / MIN_OUTBOUND=1.5 / RESERVE=5 / MIN_ATTEMPT=5 / KEY_CD=38 / TIER_CD=22。
- **验证重点**: 采 30min+ 窗口统计 k3@7895 与 k4@direct 的差异。关注指标：per-key timeout 次数、429 次数、attempt latency p50/p95。
- **代理负载均衡现状**: 7894(k1+k2)=40% 键, 7895(k3)=20%, 7896(k5)=20%, direct(k4)=20%。若 7894 持续 correlated failure，可评估把 k1 或 k2 改到 7897。
- mihomo 健康度: 7891-7899 全端口 listening (pid=24528)，但仅 3 端口有键分配；余量充裕。
- **3model 语义保留**: k3@7895 对所有 3 个 tier (kimi/dsv4p/glm5.1) 同时生效，不改变请求→tier→model 的映射逻辑。

## ⏳ 轮到HM2优化HM1
