# R41: HM2 → HM1 优化报告

**轮次**: R41 (HM2→HM1, 奇数编号)
**执行者**: HM2 (opc2_uname)
**时间**: 2026-06-26 12:35 UTC
**前一輪次**: R40 (HM1→HM2, HM_CONNECT_RESERVE_S 4→6)
**目標**: 提升HM1 deepseek fallback tier的2nd-attempt成功率，减少NVCFPexecTimeout

---

## 📊 采集数据 (30min窗口 ~12:05-12:35 UTC)

### 1.1 環境變數 (HM1 HM40006容器)

| 參數 | 值 |
|------|-----|
| UPSTREAM_TIMEOUT | 42 |
| TIER_TIMEOUT_BUDGET_S | 92 |
| HM_CONNECT_RESERVE_S | 22 |
| TIER_COOLDOWN_S | 84 |
| KEY_COOLDOWN_S | 38.0 |
| MIN_OUTBOUND_INTERVAL_S | 13.5 |

### 1.2 HM_TIER_ATTEMPTS 錯誤分佈 (30min)

| error_type | cnt | avg_elapsed_ms |
|---|---|---|
| 429_nv_rate_limit | 1112 | - |
| NVCFPexecTimeout | 135 | 28583 |
| NVCFPexecConnectionResetError | 17 | 2002 |
| budget_exhausted_after_connect | 4 | 677 |
| NVCFPexecRemoteDisconnected | 2 | 4151 |

**Total: 1258 error events**

### 1.3 按鍵分佈 — glm5.1 tier

| key | 429 errors | ConnectionResetError |
|-----|-----------|---------------------|
| k0 | 208 | 2 |
| k1 | 220 | 4 |
| k2 | 228 | 4 |
| k3 | 227 | 3 |
| k4 | 231 | 4 |

全部5鍵均勻分佈（±11%），確認function-level 429限流

### 1.4 HM_REQUESTS 路由分析

| 指標 | 值 |
|------|-----|
| 總請求數 | 1373 |
| Fallback請求數 | 1269 |
| **Fallback率** | **92.4%** |
| 直接成功 | 103 (7.5%) |

### 1.5 TIER_SKIP 分佈

| Tier | attempts | 說明 |
|------|---------|------|
| glm5.1_hm_nv | 1135 | 全部失敗（429+ConnectionReset） |
| deepseek_hm_nv | 139 | 135 timeout + 4 budget + 1 disconnect |
| kimi_hm_nv | 1 | rare |

### 1.6 Deepseek NVCFPexecTimeout Elapsed Bucket

| bucket | cnt | 佔比 |
|--------|-----|------|
| <20s | 46 | 34.1% |
| 20-25s | 11 | 8.1% |
| 25-30s | 8 | 5.9% |
| 30-35s | 19 | 14.1% |
| 35-40s | 10 | 7.4% |
| >40s | 40 | 29.6% |
| **Total** | **135** | |

### 1.7 Deepseek per-key timeout

| key | timeout cnt |
|-----|------------|
| k0 | 21 |
| k1 | 32 |
| k2 | 29 |
| k3 | 24 |
| k4 | 28 |

均勻分佈（±15%），無單鍵異常

### 1.8 日誌樣本

```
[12:27:53.5] [HM-FALLBACK] Tier glm5.1_hm_nv all-failed → falling back to deepseek_hm_nv
[12:28:00.9] [HM-FALLBACK-SUCCESS] Success on fallback tier deepseek_hm_nv after primary glm5.1_hm_nv failed
[12:29:45.4] [HM-FALLBACK] Tier glm5.1_hm_nv all-failed → falling back to deepseek_hm_nv
[12:29:59.7] [HM-FALLBACK-SUCCESS] Success on fallback tier deepseek_hm_nv after primary glm5.1_hm_nv failed
[12:31:18.5] [HM-SSL-RETRY] tier=glm5.1_hm_nv k5 SSL error — retrying same key after 2s backoff
[12:31:34.3] [HM-FALLBACK] Tier glm5.1_hm_nv all-failed → falling back to deepseek_hm_nv
[12:31:50.9] [HM-FALLBACK-SUCCESS] Success on fallback tier deepseek_hm_nv after primary glm5.1_hm_nv failed
[12:31:53.6] [HM-FALLBACK] Tier glm5.1_hm_nv all-failed → falling back to deepseek_hm_nv
[12:32:03.1] [HM-FALLBACK-SUCCESS] Success on fallback tier deepseek_hm_nv after primary glm5.1_hm_nv failed
```

日誌顯示：HM1的fallback模式正常工作（glm5.1全滅→deepseek成功），但SSL錯誤出現（k5）

---

## 🔍 診斷分析

### 根本原因

**HM1的TIER_BUDGET=92在UPSTREAM=42下只給deepseek 2nd attempt 28s，不足覆蓋30-40s區間**

預算計算：
- 1st attempt: min(42, 92-22=70) = **42s**
- 剩餘: 92-42 = 50
- 2nd attempt: max(10, min(42, 50-22=28)) = **28s** ❌

在28s headroom下：
- 「25-30s」bucket (8事件) 僅部份覆蓋（25-28s）
- 「30-35s」bucket (19事件, 14.1%) 全部無法覆蓋
- 「35-40s」bucket (10事件) 全部無法覆蓋
- 「>40s」bucket (40事件, 29.6%) 完全越過預算

**總計: 135個timeout中77個（57%）在第2次attempt時被28s budget截斷**

### 證據鏈

1. **R33 BUDGET=92 claim "30s headroom"是基於UPSTREAM=40計算的** — 在UPSTREAM=42下實際只有28s
2. **R10 UPSTREAM 40→42後2nd attempt變從30s降至28s** — 2s的upstream增加被1st attempt吃掉了
3. **30-35s bucket (19事件)** 是當前最大的capture target — BUDGET=94可給30s覆蓋這整段

### 優化向量

提升TIER_TIMEOUT_BUDGET_S 92→94 (+2s):
- 1st attempt: 42s (不變)
- 剩餘: 94-42 = 52
- 2nd attempt: max(10, min(42, 52-22=30)) = **30s** ✅ (+2s vs 現狀)

30s headroom覆蓋：
- 25-30s bucket 全覆蓋 ✅ (8事件)
- 30-35s bucket 前半覆蓋 (30-32s) ⚠️ (約10/19事件受益)
- 35-40s bucket 仍無法覆蓋 ❌

---

## ⚙️ 優化變更

| 參數 | Before | After | Δ | 理由 |
|------|--------|-------|---|------|
| **TIER_TIMEOUT_BUDGET_S** | 92 | **94** | +2s | 在UPSTREAM=42下擴展2nd attempt從28s→30s，覆蓋25-30s全區間+30-35s前半。30s是deepseek timeout的關鍵headroom值 |

**單參數變更** — 符合少改多輪原則。

---

## 🚀 執行記錄

```bash
# 備份
ssh HM1: cp /opt/cc-infra/docker-compose.yml → .bak.R41

# 變更值
ssh HM1: sed -i '418s/"92"/"94"/' docker-compose.yml

# 變更註釋
ssh HM1: sed -i '418s/# R33:.*$/# R41: HM2优化 — 92→94: +2s tier budget .../' docker-compose.yml

# 部署
ssh HM1: docker compose up -d hm40006

# 驗證
docker exec hm40006 env | grep TIER_TIMEOUT_BUDGET_S → 94 ✅
docker ps → hm40006 Up 14 seconds (healthy) ✅
```

---

## 📈 預期效果

| 指標 | 預測 |
|------|------|
| NVCFPexecTimeout | ↓ 從135→目標110-120（15% improvement）|
| 25-30s bucket | ↓ 從8→3-4（50% captured）|
| 30-35s bucket | ↓ 從19→14-16（前半captured）|
| Fallback率 | 不變（92.4% — 結構性） |
| ConnectionResetError | 不變（17 — 不影響） |
| 429_nv_rate_limit | 不變（function-level 限流） |

---

## ⚠️ 觀察事項

1. **BUDGET上限再確認**: R33說92=上限但30s headroom是在UPSTREAM=40。現在UPSTREAM=42, 30s需要BUDGET=94
2. **TIER_COOLDOWN_S=84是否維持**: 若30-35s bucket改善後仍高，可考慮降低cooldown
3. **SSL錯誤持續**: k5 SSL retry仍在出現，需關注mihomo連接健康
4. **>40s timeout=40 (29.6%)**: 這些完全越過2nd attempt budget，需在R42調查根本原因（可能是NVCF基礎設施級瓶頸）

---

## ⏳ 輪到HM1優化HM2  ← 脚本检测此标记