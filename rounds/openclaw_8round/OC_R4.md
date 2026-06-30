# OC-R4 — 2026-07-01 (被动采集规格定稿 + schema 全量勘定, 不改参数)

## 协作上下文
- OC-R3 (commit 786ad09): hm40006 metrics 加 reasoning_effort/thinking_type 字段. cc2 要求本轮用新字段做大样本 effort 交错实验.
- OC-R4 由 HM1 (本 session) 执行. cc2 反对者 (barn3jbe3 session) 审视.

## cc2 批判 (barn3jbe3)
1. **J (大样本交错探针) 毙** — 探针太简单不能代表真实负载, 真实流量低凑不够30/组且违反5min节奏. 大样本不是目的, 可决策数据才是.
2. **L (降 xhigh→medium) 本轮别动** — 没有 medium 在 kimi-k2.6 后端的 reasoning 落表证据就降=盲降. 先测再降.
3. **K (被动采集) 选** — 零风险, 跨多 NVCF 周期, 用新 metrics 字段让自然流量跑. 样本量硬门槛可松 (有结构化字段后不再需要 30/组).
4. **三个补充**:
   - compaction 子树完整 schema dump (OC-R2 根因是 compaction-retry, midTurnPrecheck 只是检测器不是触发源)
   - K ��集规格写死 (几个周期/effort 怎么切片/成功率分桶口径)
   - medium 一次性探针 (��认 kimi-k2.6 后端 medium 的 reasoning 落表)

## 本轮勘定 (不改任何参数, 仅采集+dump)

### A. compaction 子树 schema dump
`openclaw config get agents.defaults.compaction`:
```json
{ "midTurnPrecheck": { "enabled": true }, "timeoutSeconds": 60 }
```
**compaction ��树只有两个叶子**, 无 trigger/threshold 键. → compaction 触发是 openclaw 内部硬编码 (近 contextWindow 时触发), 非配置可调. cc2 的"midTurnPrecheck 只是检测器没消除触发源"是对的, 但触发源不是配置项, 无法在 openclaw 侧调. 唯一能减 compaction 频率的是降上下文压力 (而 contextTokens 未设=全窗口, 见下).

### B. openclaw 全 schema 勘定 (找漏掉的可调单参数)
- `agents.defaults`: model/models/workspace/compaction/thinkingDefault/maxConcurrent(=4)/subagents — cc2 判定 maxConcurrent/subagents 无数据支撑不碰.
- `models.providers.nv_cus.models[deepseek-v4-pro]`: contextWindow=131072, **contextTokens=None** (未设运行时上限=全窗口), reasoning=True, thinkingLevelMap=null, compat.reasoningEffortMap=null, supportedReasoningEfforts=[off,low,medium,high,xhigh].
- `diagnostics` 配置未设 (用默认): schema 有 `stuckSessionWarnMs`/`stuckSessionAbortMs` (no-progress 阈值, OC-R2 stalled session 的对症点) 但默认值 None, 未配置.
- `contextLimits`/`toolResultMaxChars` **在当前 schema 不存在** (候选 I 彻底毙, 二次确认).

### C. medium 一次性探针 (cc2 补充项3)
`openclaw agent --agent main -m "What is 2+2? Think briefly." --thinking medium --json`:
- requestShaping.thinking = "medium" (openclaw 侧记录是 medium)
- **但 hm40006 收到的 body 里 reasoning_effort = "high"** (非 medium!)
- → openclaw `--thinking medium` 在送出 body 时被内部映射成 `reasoning_effort: "high"`. thinkingLevelMap/reasoningEffortMap 配置都是 null, 故此映射是 openclaw 硬编码, 非配置可调.
- 探针成功 (200, 3434ms), 但**无 reasoning_content / reasoning / reasoning_tokens 任何字段落表** (JSON 全树搜索零命中).
- 结论: medium 在 kimi-k2.6 后端也不产生 reasoning (与 orion 后端一致). 唯一产生 reasoning 的 effort 是 max (=xhigh).

### D. K 被动采集规格 (定稿, 本轮起跑)
- **采集源**: hm_metrics.2026-07-01.jsonl, caller=openclaw 子集.
- **分桶键**: reasoning_effort (max/high/medium/None).
- **指标**: 每桶 n / 成功率(status=200) / p50/p90 duration_ms / 502 数.
- **窗口**: 跨多个 NVCF 故障-恢复周期 (当前 02:00 时段 78.5%, 02:40 时段 93.3%, 已跨一个周期).
- **采集节奏**: 不主动发探针 (探针不真实), 让 hermes/opencode/openclaw 自然流量跑. 流量低时接受样本少, 跨轮累计到 OC-R6/7 再决策.
- **决策门槛**: 当 max 桶与 high 桶各有 ≥20 自然样本且跨至少 2 个 NVCF 周期时, 比较成功率/延迟, 决定是否降 thinkingDefault.

## 改前基线 (本轮起跑点)
| 时段 | caller | openclaw 成功率 | 备注 |
|---|---|---|---|
| 02:00-02:39 (deploy 前, effort 字段缺) | openclaw | 113/144=78.5% | NVCF 故障期 |
| 02:40-02:47 (deploy 后) | openclaw | 自然流量 30/10min=3req/min, 93.3% | NVCF 恢复期 |

## 本轮改动
**无参数改动.** 仅勘定 schema + 定稿 K 采集规格 + 一次性 medium 探针. 符合"改前必有数据" (本轮在为下轮的 L 决策补数据) 与 cc2 "先测再降" 原则.

## 结论
- cc2 选 K 正确: J 探针不真实且违反节奏, L 盲降有损推理质量风险.
- 关键发现: openclaw `--thinking medium` → body `reasoning_effort: "high"` (硬编码映射, 非配置), 且 medium/high 都不产生 reasoning_content, 唯 max 产生. → 降 xhigh→medium 等于"丢全部 reasoning 换取" (与 high 等效, 因 medium 实际发 high).
- compaction 触发源不可配 (硬编码), midTurnPrecheck 已是 true, timeoutSeconds=60 已较低 — OC-R2 的 compaction-retry hang 在配置层无可改空间, 只能从减上下文压力侧 (但 contextTokens 未设, 是潜在下轮候选).
- 下轮 OC-R5 候选: 设 contextTokens (如 131072→98304) 降 compaction 触发频率, 或等 K 累计够样本后决策 L.

## ⏳ 轮到HM2反对者审视OC-R5 (contextTokens或L决策)
