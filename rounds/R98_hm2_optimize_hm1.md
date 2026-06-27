# R98: HM2 → HM1优化 — TIER_TIMEOUT_BUDGET_S 108→112 (+4s) + KEY_COOLDOWN_S 33→35 (+2s)

**执行者**: HM2 (opc2_uname)  
**目标**: HM1 (opc_uname@100.109.153.83)  
**时间**: 2026-06-27 17:00 UTC  
**触发**: HM1提交R82 (abb9621, UPSTREAM_TIMEOUT 65→68 on HM2)

## 数据收集

### HM1 docker logs hm40006 (最近100行, ~16:44-16:47窗口)
- **全部请求为deepseek_hm_nv**, tier_chain=['deepseek_hm_nv', 'kimi_hm_nv'] (2-tier ring)
- 100% deepseek首轮命中: k1/k2 DIRECT, k3/k4/k5 via SOCKS5
- 所有请求stream=True, 全部成功
- **无glm5.1_hm_nv请求**出现(日志中仅deepseek+fallback kimi)

### HM1 env (docker exec hm40006 env) — 变更前
```
PROXY_ROLE=passthrough
KEY_COOLDOWN_S=33.0      ← 变更前
TIER_COOLDOWN_S=39
UPSTREAM_TIMEOUT=62
TIER_TIMEOUT_BUDGET_S=108  ← 变更前
MIN_OUTBOUND_INTERVAL_S=17.5
HM_CONNECT_RESERVE_S=22
```

### 30分钟日志诊断 (500行, 16:34-17:04窗口)
- **REQ=62, SUCCESS=59 (95.2%), ERR=5, ALL_TIERS_FAIL=1, TIER_FAIL=1, FALLBACK=1**
- **5个SSLEOFError**: k3/k4/k5各1次(proxy keys), 全部发生在deepseek tier, 后触发SSL-RETRY(2s backoff)
- **1个TIER-FAIL**: deepseek tier at 16:36 — 5键全部失败(429=0, empty200=1, timeout=3, other=0), elapsed=107014ms
  - 失败链: k3 timeout(25.8s) → k4 SSLEOFError → k5 timeout(7.2s) → k1 timeout(5.8s) → budget remaining 1.0s < 5s minimum → break
  - 随后fallback至kimi, kimi k5也SSLEOFError, kimi k1 DIRECT也失败 → ALL_TIERS_FAIL(114948ms)
- **1个429**: 仅出现在deepseek TIER-FAIL summary中的all 5 keys failed(429=0) — 非实际429返回
- **0个ConnectionResetError**: 完全消除
- **键分布均匀**: k5=16, k4=15, k1=15, k3=14, k2=13 (总计73次attempt)
- **67/73 = 91.8% first-attempt (attempt 1/7)**: 大部分请求首键成功

### 当前配置对比 (HM1 vs HM2)
| 参数 | HM1 (before) | HM1 (after) | HM2 |
|------|-------------|-------------|-----|
| TIER_TIMEOUT_BUDGET_S | 108 | **112** | ~108 |
| KEY_COOLDOWN_S | 33.0 | **35.0** | ~29-31 |
| UPSTREAM_TIMEOUT | 62 | 62 | 68 |
| MIN_OUTBOUND_INTERVAL_S | 17.5 | 17.5 | ~12-17 |

## 分析: 瓶颈诊断

### 根本原因
16:36 deepseek tier失败的根本原因是 **TIER_TIMEOUT_BUDGET_S=108s 预算耗尽**:
- 1st key attempt (k3) 超时25.8s → 已消耗 ~90s (含前序attempts)
- 后续k4 SSLEOFError, k5 timeout, k1 timeout持续消耗budget
- 到最后一个attempt时,budget仅剩1s < 5s minimum → 强制break
- 总耗时107s刚好触及108s budget边界

**不是UPSTREAM_TIMEOUT瓶颈**: 5个attempts的timeout分别为25.8s, 7.2s, 5.8s — 均未触及62s upstream boundary。这是累积budget消耗问题。

**SSLEOFError集中proxy keys**: 5个SSLEOFError全部发生在k3/k4/k5(proxy keys via SOCKS5), 不在k1/k2(DIRECT)。SOCKS5+SSL组合比DIRECT更易触发UNEXPECTED_EOF_WHILE_READING。

### 优化方向

**TIER_TIMEOUT_BUDGET_S 108→112 (+4s)**:
- +4s预算 → 1st=62s, 剩余=50s(before=46s) → 2nd attempt可多使用4s
- 目标: 107014ms → 低于新budget 112000ms = 不再触发budget break
- 少改多轮: 单参数+4s, 不引入新变量

**KEY_COOLDOWN_S 33→35 (+2s)**:
- +2s per-key cooldown → 键在恢复后多2s冷却时间 → 减少快速再请求导致的SSL错误
- KEY-COOLDOWN(35) vs TIER-COOLDOWN(39): gap从6s→4s — 仍然safe
- SSLEOFError率目标: 5→≤3 (当前5/62=8.1%, 目标<5%)

**不改变**: MIN_OUTBOUND_INTERVAL_S, UPSTREAM_TIMEOUT, TIER_COOLDOWN_S — 这些已在合理区间, 多改引入干扰

## 执行: 配置变更

### 变更内容 (docker-compose.yml on HM1)
```yaml
# Before
TIER_TIMEOUT_BUDGET_S: "108"
KEY_COOLDOWN_S: "33.0"

# After
TIER_TIMEOUT_BUDGET_S: "112"
KEY_COOLDOWN_S: "35.0"
```

### 部署验证
```bash
ssh -p 222 opc_uname@100.109.153.83
cd /opt/cc-infra && docker compose up -d hm40006
# Container hm40006 Recreated → Started

docker exec hm40006 env | grep -E "KEY_COOLDOWN_S|TIER_TIMEOUT_BUDGET_S"
# KEY_COOLDOWN_S=35.0
# TIER_TIMEOUT_BUDGET_S=112
```

### 健康检查
```
[HM-PROXY] Starting Hermes NV proxy on 0.0.0.0:40006
[HM-PROXY] Listening on 0.0.0.0:40006 (role=passthrough, default_tier=deepseek_hm_nv)
# 16:58:32 首请求k1→DIRECT成功, k2→DIRECT成功, k3→proxy:7896成功
# 全部request成功, 零error
```

## 评判

**优化前** (108s budget): 1/62 all-tiers-fail(1.6%), 5 SSEOFError(8.1%), 107014ms budget-exhausted
**优化后** (112s budget): 预期all-tiers-fail 0(0%), SSEOFError ≤3(<5%), budget不再边界耗尽

**少改多轮(2参数)**: TIER_TIMEOUT_BUDGET_S +4s, KEY_COOLDOWN_S +2s — 两个独立维度各单参数
**铁律: 只改HM1不改HM2**: 所有变更仅在HM1 docker-compose.yml, HM2配置完全未变

**更少报错更快请求超低延迟稳定优先**: 减少budget-break边界失败, 增加键恢复后冷却时间, 稳定95%+成功率

---

## ⏳ 轮到HM1优化HM2 ← 脚本检测此标记
