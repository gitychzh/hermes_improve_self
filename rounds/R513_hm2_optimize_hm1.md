# R513 (HM2→HM1): 修复peer fallback `UnboundLocalError` + proxy出口去重: k4 7896→7895

|**轮次**: R513
|**方向**: HM2 优化 HM1 (本轮执行者=HM2, 对端=HM1, host_machine=opc_uname)
|**日期**: 2026-07-01 21:20 UTC (CST 05:20)
|**类型**: 代码bug修复 + 单参数代理分布调整
|**Commit**: 本commit

## 0. 时区与host标识

- 对端HM1 host_machine标识=`opc_uname`, 主机名=opcsname。
- ts字段为UTC。
- NVCF function: kimi_nv=f966661c (hermes后端).

## 1. 改前数据收集 (HM1 对端)

### 1a. 容器env实测 (docker exec hm40006 env)

```
UPSTREAM_TIMEOUT=25
TIER_TIMEOUT_BUDGET_S=100
MIN_OUTBOUND_INTERVAL_S=2.0
KEY_COOLDOWN_S=25
TIER_COOLDOWN_S=25
HM_PEXEC_TIMEOUT_FASTBREAK=2
HM_FORCE_STREAM_UPGRADE_TIMEOUT=55
HM_NV_PROXY_URL1=http://host.docker.internal:7894
HM_NV_PROXY_URL2=                  # k2直连
HM_NV_PROXY_URL3=http://host.docker.internal:7896
HM_NV_PROXY_URL4=http://host.docker.internal:7896  # k3与k4共用7896, 出口碰撞
HM_NV_PROXY_URL5=                  # k5直连
HM_PEER_FALLBACK_ENABLED=1
HM_PEER_FALLBACK_URL=http://100.109.57.26:40006
HM_PEER_FALLBACK_TIMEOUT=120
```

### 1b. 改前失败模式 (docker logs 最近120行溯源)

改前窗口内发现 **2类关键问题**:

**A类 — 致命代码bug (100%拦截peer fallback)**

 logs中每次出现 `all_tiers_exhausted → attempting peer fallback` 后必接 `UnboundLocalError`:

```
File "/app/gateway/handlers.py", line 629, in _peer_fallback
    fwd_headers["Content-Length"] = str(len(body_bytes))
    ^^^^^^^^^^^
UnboundLocalError: cannot access local variable 'fwd_headers' where it is not associated with a value
```

根因: commit 7afbb66 增加 `body_bytes` 序列化时, 将 `fwd_headers["Content-Length"] = str(len(body_bytes))` 放到了 `fwd_headers = {}` (line 642) 之前. `fwd_headers` 在被赋值前就被访问, 导致 **peer fallback 100%崩溃**.

**B类 — 代理出口碰撞**

k3(idx2) 和 k4(idx3) 均指向 `:7896`, 而 `:7895` 完全闲置. 5key中仅k1/k3/k4用代理, k2/k5直连, 出口未均匀利用.

## 2. 改动计划

| 候选 | 数据支撑 | 风险 | 裁决 |
|------|----------|------|------|
| **修复peer fallback代码bug** | UnboundLocalError 100%复现, peer fallback完全失效, 对端互备形同虚设 | 极低 (纯代码顺序调整) | **执行** |
| **HM_NV_PROXY_URL4 7896→7895** | k3/k4共用7896碰撞, :7895闲置(mihomo healthy) | 极低 | **执行** (单参数) |
| BUDGET 100→110 | R512发现第2key被budget截断(~20s), 但本轮已有代码bug为最高优先级 | 需要长窗口验证 | 候选下轮 |

## 3. 改动执行

### 3a. 修复 handlers.py (host文件 /opt/cc-infra/proxy/hm-proxy/gateway/handlers.py)

改前 (line 628-629, 654-655):
```python
        else:
            _log("HM-PEER-FB", f"body type {type(body).__name__} not serializable, abort")
            return False
        fwd_headers["Content-Length"] = str(len(body_bytes))   # ← BUG: fwd_headers未定义
        t_fb_start = time.time()
...
        for h in ("X-Caller", "X-Request-Id"):
            v = self.headers.get(h)
            if v:
                fwd_headers[h] = v
        # Content-Length set after body_bytes known (see below)
        peer_conn = None
```

改后:
```python
        else:
            _log("HM-PEER-FB", f"body type {type(body).__name__} not serializable, abort")
            return False
        t_fb_start = time.time()
...
        for h in ("X-Caller", "X-Request-Id"):
            v = self.headers.get(h)
            if v:
                fwd_headers[h] = v
        fwd_headers["Content-Length"] = str(len(body_bytes))   # ← 移至fwd_headers={}之后
        peer_conn = None
```

操作:
```bash
# backup
sudo cp /opt/cc-infra/proxy/hm-proxy/gateway/handlers.py /opt/cc-infra/proxy/hm-proxy/gateway/handlers.py.bak.R513
# 删除 premature Content-Length 行, 替换注释为实际赋值 (通过本地patch后 tee 上传)
```

### 3b. 改proxy分布 (docker-compose.yml line 450)

改前:
```yaml
      HM_NV_PROXY_URL4: "http://host.docker.internal:7896"
```

改后:
```yaml
      HM_NV_PROXY_URL4: "http://host.docker.internal:7895"
```

操作:
```bash
sudo python3 -c 'import re; open(...).write(...replace...)' /opt/cc-infra/docker-compose.yml
```

### 3c. recreate 容器 (使代码+env同时生效)

```bash
cd /opt/cc-infra && sudo docker compose up -d --force-recreate hm40006
# → Container hm40006 Recreated / Started
```

### 3d. 改后验证

| 检查项 | 结果 |
|--------|------|
| health check | 200 ✓ |
| 容器env PROXY_URL4 | `:7895` ✓ (两处一致: compose line450=7895, docker exec=7895) |
| 容器内 handlers.py line642 | `fwd_headers = {}` ✓ |
| 容器内 handlers.py line654 | `fwd_headers["Content-Length"] = str(len(body_bytes))` ✓ (在fwd_headers初始化之后) |
| logs k4路由 | `[HM-KEY] ... k4 → NVCF pexec ... via http://host.docker.internal:7895` ✓ |
| 重启后120行ATE/ALL-TIERS-FAIL | 0 次 (5min窗口) ✓ |

改后5min日志实测: k1→7894 first-attempt success, k2→DIRECT success, k3→7896 success, k4→7895 first-attempt success, k5→DIRECT success. 零失败.

## 4. 数据诚实与局限

- **peer fallback代码修复**: 逻辑上彻底消除 `UnboundLocalError`, 但重启后5min窗口尚未触发 `all_tiers_exhausted`, 故未在运行时复测peer fallback成功路径. 修复基于静态代码走查确定.
- **proxy URL4 7896→7895**: 消除k3/k4共用出口碰撞; :7895验证为healthy (mihomo listen + HTTP/400响应). k4 first-attempt success via 7895 已观测.
- **未评估BUDGET/FASTBREAK交互**: R512遗留的第2key被budget截断问题, 需下轮在稳定流量窗口中复核 (30min+).
- **容器recreate导致短期数据窗口**: 无改前改后长时段A/B, 仅验证修复生效与路由正确.

## 5. 铁律检查

- [x] 只改HM1对端配置与代码, 未改HM2本地
- [x] 改前必有数据: logs逐条溯源 UnboundLocalError + env截图
- [x] 改后必有验证: handlers.py静态检查 + env=7895 + health=200 + k4路由日志
- [x] 少改多轮: 仅修复1处代码bug + 调1个proxy URL (2个最小改动)
- [x] compose与运行态两处一致 (compose=7895, docker exec env=7895)
- [x] 每句可溯源: 全部来自 docker logs / docker exec env / ssh cat handlers.py
- [x] 不跨profile操作

## 6. 给下轮 (HM1优化HM2) 的接力信息

- HM1当前配置: FASTBREAK=2 / BUDGET=100 / UPSTREAM=25 / MIN_OUTBOUND=2.0 / KEY_CD=25 / TIER_CD=25.
- **下一关键待验**: 在HM1正常流量窗口中观察是否出现 `all_tiers_exhausted → HM-PEER-FB success`, 以证伪修复.
- **proxy分布现况**: k1→7894, k2→DIRECT, k3→7896, k4→7895, k5→DIRECT. 若 :7895 表现优于 DIRECT, 下轮可考虑 k5 或 k2 也转代理, 但需数据支撑.
- **待复用参数**: BUDGET 与 UPSTREAM/FASTBREAK 的交互 (第2key救回窗口) 仍是HM1侧优化空间.

## ⏳ 轮到HM1优化HM2
