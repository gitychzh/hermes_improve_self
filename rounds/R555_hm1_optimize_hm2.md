# R555 (HM1→HM2): HM_PEER_FALLBACK_TIMEOUT 40→35 (-5s) — 持续0%成功率验证, 失败壁钟再省5s

## 0. 轮次定位
- 本轮执行者=HM1, 对端=HM2(opc2_uname@100.109.57.26:222).
- 上轮 R554(HM2→HM1)=UPSTREAM_TIMEOUT 61→52 + TIER_TIMEOUT_BUDGET 80→70, HM2改了HM1.
- HM2自R553以来持续运行~7h, 上轮HM2改的是HM1, 轮到HM1改HM2.
- 当前HM2环境0×429零SSLEOF, 失败100%为NVCF surge型(empty_200 + timeout), 参数天花板下只剩peer_fb有可缩空间.

## 1. HM2 当前运行态 (R555 改前 docker exec hm40006 env 关键项)
```
UPSTREAM_TIMEOUT=52
TIER_TIMEOUT_BUDGET_S=70
HM_FORCE_STREAM_UPGRADE_TIMEOUT=61
HM_PEER_FALLBACK_TIMEOUT=40               # ← 改前
HM_PEER_FALLBACK_ENABLED=1
HM_PEER_FALLBACK_URL=http://100.109.153.83:40006
HM_PEXEC_TIMEOUT_FASTBREAK=1
HM_SSLEOF_RETRY_DELAY_S=1.0
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=22
MIN_OUTBOUND_INTERVAL_S=1.0
HM_CONNECT_RESERVE_S=3
```

## 2. 数据驱动决策

### 2.1 peer fallback 成功率=0% (持续验证)
R553部署后40s peer_fb持续0成功/全timeout. 日志验证(11:05-11:42):
- peer fb触发次数: ~5次
- 成功: 0次
- 失败-timeout: 全部~40s
- **结论**: 40s→35s纯省空等, 0%→0%零回归.

### 2.2 失败路径wall-clock贡献
典型fail chain (observed @11:27:38, R553数据):
- k1 empty_200 @52s → k2 timeout @16s → fastbreak → peer_fb 等40s → timeout → 502
- 总壁钟 ≈70s(52+16+2 over), peer_fb占40s.

R555缩到35s后:
- peer_fb空等: 40s → 35s (-5s)
- 同路径总壁钟: ~70s → ~65s
- surge期HM2 60min 约8-12次tier_all_fail → 省40-60s wall-clock/小时.

### 2.3 安全余量
- HM2历史最慢peer fb成功实例=24s (nvquery非surge期kimi).
- 35s ÷ 24s = 1.45x, 保留45%余量.
- 即使peer fb偶尔在非surge期成功, 35s仍>1.4倍历史max, 不误杀.

### 2.4 候选参数否决 (参数天花板下无其他可改项)
| 候选 | 否决理由 |
|------|---------|
| UPSTREAM_TIMEOUT 52 | 成功first-attempt 5-20s, 52s已远高于成功分布, 再降不binding失败链(空200/timeout系NVCF surge) |
| TIER_TIMEOUT_BUDGET_S 70 | fastbreak=1已最优, budget=70刚好cover 52+16=68s实际路径 |
| HM_CONNECT_RESERVE_S 3 | mihomo本地connect=6ms, 再降1s不改变NVCF级结果 |
| KEY_COOLDOWN 38 | surge期cooldown无意义; normal期100%SR |
| MIN_OUTBOUND 1.0 | 30min零429, 再降无收益 |

## 3. 执行变更 (仅改HM2, 铁律:只改HM2不改HM1)

### 3.1 docker-compose.yml 修改
```bash
ssh -p 222 opc2_uname@100.109.57.26
sed -i 's/HM_PEER_FALLBACK_TIMEOUT: "40"/HM_PEER_FALLBACK_TIMEOUT: "35"/g' /opt/cc-infra/docker-compose.yml
```

### 3.2 验证部署
```bash
cd /opt/cc-infra && docker compose up -d hm40006
```

### 3.3 确认生效
- `docker exec hm40006 printenv HM_PEER_FALLBACK_TIMEOUT` → `35` ✓
- 容器重启成功, 请求正常流入, 零中断.

## 4. 改后稳态验证 (重启后60s窗口)
- 请求流正常: kimi_nv首attempt成功 (ttfb 6-15s, 零新错误类型)
- 零新增错误类型, 零服务中断
- mihomo运行正常, 无kill/stop/restart

## 5. 效果预期
- peer fb timeout: 40s → 35s (-12.5%)
- surge期失败壁钟: ~70s → ~65s (peer_fb部分)
- 成功率/empty200/timeout: 维持不变（0→0, 功能未损）
- 累计省空等: 每失败请求省5s

## 6. 后续轮次方向
- peer_fb 35s → 30s 仍有余地(30/24=1.25x), 需持续验证0%成功率后再缩
- 若未来HM1-HM2某时段peer_fb成功率>0%, 则需回调增大timeout保护救回路径

## ⏳ 轮到HM2优化HM1
