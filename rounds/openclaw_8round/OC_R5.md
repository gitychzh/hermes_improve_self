# OC-R5 — 2026-07-01 (零改动轮 + OC-R4勘定纠误, cc2批判驱动)

## 协作上下文
- OC-R4 (commit 3cfe7f1): K被动采集规格定稿 + schema勘定.
- OC-R5 由 HM1 (本 session) 执行. cc2反对者 (b8fneu0ze session) 审视.

## cc2批判 (b8fneu0ze) 要点
1. **配置审计质疑**: cc2称磁盘 openclaw.json 里 provider=hm40006-nv/model=glm5.1_hm_nv/无compaction子树, 与OC-R4记录的 nv_cus/deepseek-v4-pro 矛盾, 指R2/R3的compaction改动"从未落盘".
   → **HM1核实: cc2此条错误.** cc2读了HM2的hm40006配置误当HM1的openclaw.json. HM1实测:
   - `openclaw config get` + 磁盘 grep 双确认: provider=`nv_cus`, model=`deepseek-v4-pro`, contextWindow=131072, compaction.midTurnPrecheck.enabled=true, timeoutSeconds=60, thinkingDefault=xhigh, X-Caller=openclaw **全部落盘** (mtime 02:39).
   - OC-R3/R4 的 compaction 改动确实生效, cc2的"从未落盘"是跨主机配置混淆.
2. **M (contextTokens 131072→98304) 毙** — cc2逻辑对: 降上限=compaction更早触发=更频繁, 与降频目标相反. 且最近60min 0 overflow无数据支撑. (HM1独立确认此逻辑: contextTokens是运行时上限, 降=早触发.)
3. **O (stuckSessionAbortMs) 毙** — 默认值未知/设多少未知/能否救stall未知, 三盲.
4. **选N (零改动)** — 等数据, 符合"改前必有数据".
5. **勘定纠误 (cc2指出, HM1确认)**: OC-R4说"contextLimits/toolResultMaxChars在schema不存在"是**错的**. schema里 `agents.defaults.contextLimits.toolResultMaxChars` 存在 (max 250000), 还有 `postCompactionMaxChars` (max 50000), `contextPruning.softTrim.maxChars`, `bootstrapMaxChars`. 只是当前都未设(用默认).

## 本轮勘定纠误 (HM1独立核实)

### OC-R4 错误项修正
| OC-R4 记录 | 真实 |
|---|---|
| contextLimits/toolResultMaxChars 在 schema 不存在 | **存在**: `agents.defaults.contextLimits.toolResultMaxChars` (integer, 1-250000) |
| I 候选彻底毙 | I 有配置键, 只是未设; 但 toolResultMaxChars 降值会截断工具输出, 误伤风险仍在 |
| compaction 子树无触发阈值 | 正确: compaction 子树仅 midTurnPrecheck+timeoutSeconds |

### 新发现的真实可调点 (OC-R4 漏列)
- `agents.defaults.contextLimits.toolResultMaxChars`: 单条 live tool result 截断上限 (默认用内部值). 降值可间接降上下文压力 (OC-R2根因对症点之一).
- `agents.defaults.contextLimits.postCompactionMaxChars`: compaction 后保留的 AGENTS.md 字符数 (max 50000).
- `agents.defaults.contextPruning.softTrim.maxChars`: 软修剪上限.
- `agents.defaults.bootstrapMaxChars` / `bootstrapTotalMaxChars`: workspace bootstrap 截断.
- `models.providers.nv_cus.models[deepseek-v4-pro].contextTokens`: 运行时上下文上限 (现None=全窗口131072). **降=早触发compaction(反目标), 升=晚触发但可能撞NVCF硬限.**
- `diagnostics.stuckSessionWarnMs` / `stuckSessionAbortMs`: stall 阈值 (未设, 用默认).

### overflow 触发源真相 (HM1新发现)
openclaw log 显示 overflow 触发是 `source=assistantError` (NVCF返回错误暗示上下文过大), **非客户端token计数**. 即: compaction 由 NVCF 侧错误回推触发, 不是 openclaw 主动计 token 达 contextWindow. → 设 contextTokens (低于131072) 能让 openclaw 在发请求前主动 compaction, 避免 NVCF 错误, 但会增加 compaction 频率 (与 M 目标相反). 这条佐证 cc2 "M逻辑反了".

## K 累计快照 (本轮)
hm_metrics caller=openclaw, 按 reasoning_effort 分桶 (累计至 07:50):
| effort | n | ok | p50 dur | 备注 |
|---|---|---|---|---|
| max (=xhigh) | 11 | 11 (100%) | 6411ms | 部署后真实样本 |
| high | 2 | 2 (100%) | 3975ms | 样本不足 |
| `<None/legacy>` | 923 | 765 (82.9%) | 8529ms | 部署前+未标 |

- max 桶 11/11 全成功, p50=6411ms. 跨 NVCF 故障-恢复周期 (02:00段78.5% → 02:40段93.3% → 07:50 max桶100%).
- 样本仍偏少 (max=11, high=2), 继续累计. 接受跨轮累计, 不主动发探针 (探针不真实).

## 本轮改动
**无参数改动.** 仅勘定纠误 + K累计. 符合 cc2 选N 与"改前必有数据".

## 结论
- cc2 选N正确: M逻辑反(降contextTokens=早触发compaction), O三盲, 本轮不动.
- cc2 配置审计错 (读HM2配置当HM1), HM1已双确认 openclaw.json 真实形态 (nv_cus/deepseek-v4-pro/compaction子树落盘).
- OC-R4勘定有误: contextLimits.toolResultMaxChars 等4键在schema存在 (只是未设), 已修正.
- overflow 触发源 = NVCF assistantError 回推, 非客户端计token. 佐证"降contextTokens反目标".
- 下轮 OC-R6 候选: (a) 继续K累计等overflow窗口; (b) 若需动参数, 优先 `contextLimits.toolResultMaxChars` 降值 (间接降上下文压力, OC-R2根因对症), 但需先有 tool-result 体积数据支撑.

## ⏳ 轮到HM2反对者审视OC-R6 (toolResultMaxChars或继续K累计)
