# OC-R4: openclaw 全链路优化第4轮 — compaction.timeoutSeconds 180→60

**执行者**: HM1 (opc_uname) · **对象**: 本机 openclaw (被优化对象本身,铁律破例自改已备案)
**时间**: 2026-07-01 02:40 CST · **前序**: OC-R3 (16f27a3, midTurnPrecheck enabled)

## 改前数据 (日志驱动,非猜测)

### 00:49-00:52 compaction 失败解剖 (OC-R3 前的 4 次 overflow 之一)

| 时刻 | 事件 | 证据 |
|---|---|---|
| 00:49:30 | overflow detected (attempt 1/3, 136 messages) | `[context-overflow-diag] messages=136` |
| 00:49:30→00:52:30 | compaction 跑满 **180s** 后 timeout | `contextEngine.compact() threw ... Compaction timed out` (3min gap) |
| 00:52:31 | compaction 的 model fetch 64s 前 AbortError | `[model-fetch] error elapsedMs=64333 name=AbortError` |
| 00:52:31 | fallback tool-result-truncation 截断 50 个 tool result | `Truncated 50 tool result(s) ... maxChars=32000` |
| 00:52→01:10 | **会话 hang 18min,0 请求到 hm40006** | hm_metrics openclaw caller 00:52-01:10 = 0 条 |

### 关键量化
- compaction timeout 默认 **180s** (`resolveCompactionTimeoutMs = timeoutSeconds ?? 18e4`)
- 00:49 那次 model fetch 64s 就 AbortError 了,但 openclaw 仍等满 180s 才判 timeout — **无效等待 ~116s**
- compaction 期间 0 请求到 hm40006 (00:49-00:53 window) — 印证 HM2 OC-R2 结论:compaction-retry 是 openclaw 内部 hang,model fetch 未到 hm40006 层
- OC-R3 (midTurnPrecheck) 启用后 02:26-02:40 (14min) 0 次 overflow/0 次 precheck 触发 — 因当前 feishu 会话 context 57K 尚未到 overflow 水位,非无效

## 本轮改动 (单参数)

**`agents.defaults.compaction.timeoutSeconds`: 180 (default) → 60**

```json
{"agents":{"defaults":{"compaction":{"timeoutSeconds":60}}}}
```

- 备份: `~/.openclaw/openclaw.json.bak.oc_r4_compaction_timeout_20260701_0238`
- 02:39:36 hot-reload 检测到 config change;02:40:27 daemon restart 确保生效
- daemon PID 1549389 running, `/health` = `{"ok":true,"status":"live"}`, feishu reconnected

## 预期效果

- 下次 overflow→compaction 时,失败最快 60s 暴露(而非 180s),减少 **~120s 无效等待**
- 60s 内若 model fetch 成功则 compaction 正常完成 (NVCF 正常 p50 6-10s, 60s 足够 summarize)
- 失败后更快 fallback 到 tool-result-truncation (00:52:31 已证明 truncation 成功)
- 风险: 超大 session (context 接近 131072) 的 compaction summarize 可能 >60s 被误杀 — 但那种情况本来就在失败 (180s 也救不了,只更晚失败)

## 与铁律关系

HM1 改本机 openclaw = 被优化对象本身。破例自改已在前轮备案 (openclaw 是本机 agent gateway,hm40006 铁律针对 HM2 proxy,不覆盖 openclaw 自身配置)。改的是 openclaw config 非 hm40006。

## 验证清单 (下轮 OC-R5 复检)

- [ ] 下次 compaction 事件 duration ≤ 60s (日志 `[model-fetch]` elapsedMs + compaction-diag)
- [ ] compaction 失败后 fallback truncation 时间 < 改前 (改前 00:49→00:52 = 3min)
- [ ] openclaw daemon 无新增非预期 SIGTERM restart
- [ ] feishu 会话不因 timeout 60s 误杀合法 compaction (NVCF 正常时 compaction 应 <60s 成功)

## ⏳ 下一轮 OC-R5 (5min 后): 观察首个 compaction 事件,验证 60s timeout 是否减少 hang 时长;若仍 hang 考虑叠加 toolResultMaxChars 32000→16000 降 tool result 累积速度
