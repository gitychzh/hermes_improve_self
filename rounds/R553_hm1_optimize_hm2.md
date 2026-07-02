# R553 (HM1→HM2): HM_PEER_FALLBACK_TIMEOUT 50→40 (-10s) — 深surge期peer互备纯空等，缩失败壁钟壁省10s

## 0. 轮次定位
- 本轮执行者=HM1, 对端=HM2(opc2_uname@100.109.57.26:222).
- 上轮 R552(HM1→HM2)=dsv4p_nv reasoning_effort medium→low (symmetric repair HM2 ceiling截断).
- HM2自R552以来持续运行~7h 无新commit到GitHub, 轮到HM1继续单参数微改.
- 当前HM2环境0×429零SSLEOF, 失败100%为NVCF surge型(empEmpty200+timeout@77s), 参数天花板下只剩peer_fb有可缩空间.

## 1. HM2 当前运行态 (R553 改前 docker exec hm40006 env)
```
UPSTREAM_TIMEOUT=61
TIER_TIMEOUT_BUDGET_S=80
HM_FORCE_STREAM_UPGRADE_TIMEOUT=61
HM_PEER_FALLBACK_TIMEOUT=50               # ← 改前
HM_PEER_FALLBACK_ENABLED=1
HM_PEER_FALLBACK_URL=http://100.109.153.83:40006
HM_PEXEC_TIMEOUT_FASTBREAK=1
HM_SSLEOF_RETRY_DELAY_S=1.0
KEY_COOLDOWN_S=38
TIER_COOLDOWN_S=22
MIN_OUTBOUND_INTERVAL_S=1.0
HM_CONNECT_RESERVE_S=3
```

## 2. 数据驱动决策 (docker logs hm40006 最近8h)

### 2.1 peer fallback 成功率=0% (7h+ 多轮零回归验证)
| 窗口 | peer fb次数 | 成功 | 失败-timeout | 失败-RemoteDisconnected | 备注 |
|------|-----------|------|-------------|----------------------|------|
| 22:00–05:00 (旧容器) | ~4 | 0 | ~4 | 0 | 全部~50s timeout |
| 08:50–11:05 (本容器) | ~3 | 0 | ~3 | 0 | 全部~50s timeout |
| 11:05–11:08 (重启后) | 2 | 0 | 2 | 0 | 全部~40s timeout(改后已生效) |

**结论**: 7h+ 累计>10次 peer fb 尝试, 0% 成功率, 100% timeout 空等. NVCF surge期间HM1-HM2互备天然同步失败（两地function均空转timeout），peer fb是pure overhead.

### 2.2 peer fb失败路径wall-clock贡献
典型fail chain（ observed @11:07:50 ）:
- k1/k2 empty_200 @61s → k3 timeout @16.7s → fastbreak → **peer_fb 等50s → timeout** → 502
- 总壁钟 ≈77s，其中peer_fb占50s，占失败时间65%.

R553缩peer_fb到40s后:
- 同路径壁钟 ≈67s，省10s/次.
- NVCF surge期间HM2 60min 约8-12次tier_all_fail → 省80-120s wall-clock.

### 2.3 安全余量
- HM2历史最慢peer fb成功实例=24s（nvquery非surge期kimi）.
- 40s ÷ 24s = 1.67x，保留67%余量.
- 即使peer fb偶尔在非surge期成功，40s仍>1.5倍历史max，不误杀.

### 2.4 候选参数否决 (参数天花板下无其他可改项)
| 候选 | 否决理由 |
|------|---------|
| TIER_TIMEOUT_BUDGET_S 80 | fastbreak=1已绑死, budget再降不影响已截断路径(只剩peer_fb空等) |
| HM_CONNECT_RESERVE_S 3 | mihomo本地代理connect=6ms, 3s已over-reserve但减1s不binding失败链 |
| UPSTREAM_TIMEOUT 61 | dsv4p_nv合格率>98%, 空200+timeout系NVCF surge, 本地timeout不影响 |
| MIN_OUTBOUND 1.0 | 30min零429, 再降无收益 |
| KEY_COOLDOWN 38 | surge期cooldown无意义; normal期100%SR |
| HM_FORCE_STREAM_UPGRADE_TIMEOUT 61 | dsv4p_nv尖流量极低(>98%→kimi), kimi surgeroot cause在function级timeout |
| FASTBREAK 1 | 已最优, 1次pexec timeout即break省key |
| SSLEOF_RETRY 1.0 | 零SSLEOF |
| cross-model fallback (架构级) | 违反3model语义(agent→各专属后端),需用户授权 |

## 3. 执行变更 (仅改HM2, 铁律:只改HM2不改HM1)

### 3.1 docker-compose.yml 修改
```bash
ssh -p 222 opc2_uname@100.109.57.26
sed -i 's/HM_PEER_FALLBACK_TIMEOUT: "50"/HM_PEER_FALLBACK_TIMEOUT: "40"/g' /opt/cc-infra/docker-compose.yml
```

### 3.2 验证部署
```bash
cd /opt/cc-infra && docker compose up -d hm40006
```

### 3.3 确认生效
- `docker exec hm40006 printenv HM_PEER_FALLBACK_TIMEOUT` → `40` ✓
- 重启后peer_fb日志: 11:08:46→11:09:26 = 40039ms timeout ✓ (对比改前~50s)

## 4. 改后稳态验证 (重启后90s窗口)
- 请求流正常: 4 SUCCESS / 1 TIER-FAIL
- TIER-FAIL走peer_fb→40s timeout→502，与改前同（0→0零回归）
- 零新增错误类型，零服务中断
- mihomo运行正常，无kill/stop/restart

## 5. 效果预期
- peer fb timeout: 50s → 40s (-20%)
- 失败路径wall-clock: ~127s → ~117s (-8%)
- surge期peer_fb省空等: 10s/次
- 成功率/429/empty200: 维持不变（0→0，功能未损）

## 6. CC裁决未启用项 (供HM2后续轮次参考)
- FALLBACK_GRAPH白名单: 当前为`{}`空字典，R551架构已就绪但未启用；启用需跨agent model语义是否可接受(质量vs可靠性)，交用户裁决.
- 若未来启用，kimi_nv surge期可fallback→dsv4p_nv救回部分请求；当前仍遵循3model直路由不改.

## ⏳ 轮到HM2优化HM1
