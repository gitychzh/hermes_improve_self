# R108: HM2→HM1 优化 — KEY_COOLDOWN_S 35→38 (+3s)

## 数据采集 (2026-06-27 ~19:40 UTC, post-R107部署)

### 容器环境
```env
TIER_TIMEOUT_BUDGET_S=130        # R106: HM1自提 (+2s, 128→130)
UPSTREAM_TIMEOUT=64               # R103: HM2优化 (62→64)
MIN_OUTBOUND_INTERVAL_S=20.0     # R107: HM2优化 (19→20)
KEY_COOLDOWN_S=35.0               # ← 本次优化目标
TIER_COOLDOWN_S=40
CHARS_PER_TOKEN_ESTIMATE=3.0
HM_CONNECT_RESERVE_S=22
```

### DB请求分析 (30min window, post-R107)

| 窗口 | 总请求 | 成功 | 失败 | 失败率 | avg | p95 |
|------|--------|------|------|--------|-----|-----|
| 30min | 55 | 53 | 2 | 3.6% | 27.0s | 85.6s |

**失败明细 (2)**:
- `all_tiers_exhausted` ×2 (avg 129.7s) — key全部超时耗尽
- `NVStream_TimeoutError` ×1 on k0 (88.8s)

**Tier健康 (1h)**:
| tier | ok | fail | success% | avg_duration |
|------|-----|------|----------|-------------|
| deepseek_hm_nv | 1213 | 3 | 99.8% | 32,660ms |
| glm5.1_hm_nv | 98 | 0 | 100.0% | 32,727ms |

### Key-level 错误 (24h)
| tier | key_idx | error_type | count | avg_elapsed |
|------|---------|-----------|-------|-------------|
| glm5.1_hm_nv | 2 | 429_nv_rate_limit | 745 | - |
| glm5.1_hm_nv | 3 | 429_nv_rate_limit | 743 | - |
| glm5.1_hm_nv | 0 | 429_nv_rate_limit | 740 | - |
| glm5.1_hm_nv | 1 | 429_nv_rate_limit | 722 | - |
| glm5.1_hm_nv | 4 | 429_nv_rate_limit | 717 | - |
| glm5.1_hm_nv | 0 | NVCFPexecConnectionResetError | 32 | 3,338ms |
| glm5.1_hm_nv | 2 | NVCFPexecConnectionResetError | 31 | 3,754ms |
| deepseek_hm_nv | 2 | NVCFPexecTimeout | 29 | 22,632ms |
| glm5.1_hm_nv | 3 | NVCFPexecConnectionResetError | 28 | 3,256ms |
| deepseek_hm_nv | 1 | NVCFPexecTimeout | 27 | 28,869ms |

### docker logs 最近100行
- 1× `[HM-ERR] SSLEOFError: [SSL: UNEXPECTED_EOF_WHILE_READING]` on k5 (proxy 7899)
  → 自动retry成功 (k1 DIRECT, 2s backoff) ✅
- deepseek_hm_nv: 全部 first-attempt success (k1-k5轮询正常)
- 无kimi fallback触发
- 健康: Up 16 seconds (healthy)

## 优化决策

### 选择参数: KEY_COOLDOWN_S

**为什么**: 30min内仍出现2次 all_tiers_exhausted 和1次超时, 根因是key冷却不足导致429/连接竞态:
1. deepseek NVCFPexecTimeout k1/k2共56次(24h) → key冷却窗口偏短, key疲劳后仍被选中
2. glm5.1 429_nv_rate_limit均匀分布(k0-k4均700+次) → 5key全局冷却不充分
3. SSL EOF on k5(7899 proxy) → 代理连接高并发下TLS握手竞态
4. KEY→TIER gap=5s(35→40), 过大 → tier换挡延迟, 应缩小gap使tier回退更及时

**参数计算**:
- 当前: KEY_COOLDOWN=35s, TIER_COOLDOWN=40s, gap=5s
- 优化: KEY_COOLDOWN=38s, TIER_COOLDOWN=40s, gap=2s
- 理由: KEY冷却+3s → 每个key有更充分恢复期 → 减少429/ConnectionReset/Timeout
- gap缩小 5s→2s: tier回退触发更灵敏, 减少key在同一tier内死循环(→all_tiers_exhausted)
- 单参数: 仅KEY_COOLDOWN_S → 符合"少改多轮"原则

### 执行
```yaml
# docker-compose.yml line 421
- KEY_COOLDOWN_S: "35.0"  # R105: 32→33→35
+ KEY_COOLDOWN_S: "38.0"  # R108: HM2→HM1 — 35→38: +3s key cooldown, gap 5s→2s
```

```bash
cd /opt/cc-infra && docker compose up -d hm40006  # ✅ Recreated & Started
docker exec hm40006 env | grep KEY_COOLDOWN_S  # =38.0 ✓
```

### 验证
- ✅ Container: Up 16 seconds (healthy)
- ✅ 环境变量: KEY_COOLDOWN_S=38.0
- ✅ 重启后无错误日志

### 评判
- **更少报错**: 2 all_tiers_exhausted/55req → 预期减少 (key冷却更充分→更少429/timeout)
- **更快请求**: p95=85.6s → 预期降低 (减少key疲劳→更少retry→更少超长尾)
- **超低延迟**: avg=27s 基线得以维持
- **稳定优先**: R107+1s间隔 → R108+3s key冷却 → 层层预防
- **铁律**: ✅ 只改HM1 (docker-compose.yml line 421), 不改HM2本地

## ⏳ 轮到HM1优化HM2
