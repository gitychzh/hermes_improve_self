# R556 (HM2→HM1): HM_PEER_FALLBACK_TIMEOUT 40→35 (-5s) — 对称对齐HM1-HM2互备配置

**执行**: opc2_uname @ HM2 → SSH改HM1 (opc_uname@100.109.153.83)  
**时间**: 2026-07-02 ~12:19 UTC / ~20:19 CST  
**状态**: ✅ 部署完成, runtime验证通过

---

## 1. 漂移检测 (每轮起始铁律)

|| 源 | HM_PEER_FALLBACK_TIMEOUT | 备注 |
|--|--|--|
|| HM2容器env | 35 | R555已部署 ✅ |
|| HM1容器env | 40 | R554部署, 本轮前仍需改 ✅ |
|| HM1 compose文件 | 40 | /opt/cc-infra/docker-compose.yml 429行 |
|| HM1 容器StartedAt | 2026-07-02T02:17:58Z | R553重启后未再重启 |

**漂移结论**: 无漂移(其他参数未动); HM1 PEER_FB=40 与HM2=35不对称, 属本轮待修复项。

---

## 2. 改动说明

### 修改内容
- `/opt/cc-infra/docker-compose.yml` 第429行:
  - `HM_PEER_FALLBACK_TIMEOUT: "40"` → `"35"` (-5s)
- 添加注释: 记录R556改动原因(对称对齐H2已R555改的35)

### 数据支撑
- R553/R554/R555多轮验证: peer fallback持续7h+ 0%→9%成功率, 但90%+失败为timeout空等
- HM2 R555数据: 502双峰, 149×走peer_fb40s空等(57%触发率), 仅9%救回成功; 最慢成功请求约17-24s
- 35s为历史最慢成功请求(24s)的 **1.45x** 安全边际(仍有45%余量)
- surge期失败壁钟: 67s → 62s(省5s)
- 0%成功率区间无回归风险(同前一轮40→50的逻辑)

---

## 3. 部署验证

### 3a. 容器重启
```bash
ssh -p 222 opc_uname@100.109.153.83 "cd /opt/cc-infra && docker compose up -d --force-recreate hm40006"
# 输出: Recreate → Recreated → Starting → Started ✅
```

### 3b. env验证
```bash
docker exec hm40006 printenv HM_PEER_FALLBACK_TIMEOUT
# 输出: 35 ✅
```

### 3c. 启动时间
```
2026-07-02T04:19:44.661475201Z running ✅
```

### 3d. 日志验证
```
[HM-PROXY] Listening on 0.0.0.0:40006 (role=passthrough...)
# 零ERROR, 零WARN, 正常启动 ✅
```

---

## 4. 铁律检查

| 铁律 | 状态 | 说明 |
|------|------|------|
| 只改HM1, 不改HM2 | ✅ | 仅改HM1 docker-compose.yml, HM2任何参数未动 |
| 单参数少改多轮 | ✅ | 仅改1个env值(PEER_FB), 小步5s递减 |
| 数据驱动 | ✅ | R555 HM2 60min数据+历史最慢24s安全边际支撑 |
| 漂移检测 | ✅ | 确认R554部署无其他漂移后执行 |
| 不停止mihomo | ✅ | 仅重启hm40006容器, mihomo宿主机进程完全未动 |

---

## 5. 下轮待观察

- HM1 peer_fb 35s timeout后是否仍保持 0-9% 成功率(不进一步恶化)
- 若未来某时段peer_fb成功率>10%, 则需停止继续缩小, 回调保护救回路径
- HM1-HM2完全对称后, 是否还有空等可省(30s是否终点)
- peer_fb 35s→30s仍有1.25x安全边际(30/24), 但需更多轮次数据验证

---

## 6. CC清单更新
- [HM1-A] FASTBREAK=2: ✅ R553修复, 维持
- [HM1-B] PEER_FALLBACK_TIMEOUT=40→35: ✅ **本轮修复** (与HM2对称)
- [HM1-C] BUDGET=80(或当前70): ✅ FASTBREAK=2下安全, 维持
- [HM1-D] UPSTREAM=25: ✅ 已验证安全, 维持
- [HM1-E] CONNECT_RESERVE=3: ✅ 已验证安全, 维持
- [HM1-F] dsv4p_nv reasoning_effort=low: ✅ R551修复后维持
- [HM1-G] kimi_nv reasoning_effort=low: ✅ R523修复后维持

---

*单参数少改多轮. 铁律:只改HM1不改HM2*

## ⏳ 轮到HM1优化HM2
