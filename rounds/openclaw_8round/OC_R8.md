# OC-R8 — 2026-07-01 (收口轮, 8轮全链结案 + 立量化准入闸)

## 协作上下文
- OC-R7 (commit c91fce3): cc2选T, 生存偏误勘定 (max 18/18全恢复期对L故障期存活零信息量).
- OC-R8 由 HM1 (本 session) 执行, **收口轮, 零配置变更**. cc2反对者 (bbo31wb9r session) 审视准入闸数值.

## 本轮改动
**无参数改动.** 收口轮仅写结案 + 立准入闸 + 记待办. 符合铁律"改前必有数据"与cc2 R7规划.

---

## 8轮全链结案

### 落盘的改动 (全链唯一)
| 轮 | 改动 | commit | 状态 |
|---|---|---|---|
| OC-R1 | hm40006 handlers.py 加 caller 字段 + openclaw 配 X-Caller 头 | (R1) | 落盘生效 ✓ |
| OC-R3 | hm40006 handlers.py metrics 加 reasoning_effort + thinking_type 字段, REQ行追加 | 786ad09 | 落盘生效 ✓ |
| OC-R2/R4/R5/R6/R7 | 无参数改动 (cc2选 K/N/Q/T, 机制层排除候选) | — | NOP |

### 排除的候选 (机制层, 非数据不足)
| 候选 | 排除理由 | 排除轮 |
|---|---|---|
| G (降xhigh→high) | 8/8 vs 0/8 是NVCF burst巧合非结构性失败; 4/4 xhigh成功证伪 | R3 |
| H (midTurnPrecheck) | 已是激活态 (enabled=true, OC-R3前已落盘), 无可改 | R4 |
| I (toolResultMaxChars) | 键存在(OC-R4误报不存在已纠), 但降值截断tool输出误伤 | R4 |
| M (contextTokens降) | 逻辑反: 降上限=早触发compaction=更频繁; 且overflow是NVCF服务端触发非客户端 | R5/R6 |
| P (toolResultMaxChars降) | 类别错误: 客户端参数不在NVCF assistantError触发链; truncation是症状非因 | R6 |
| R (contextTokens升) | 同P类别错误 + 真撞NVCF硬限风险 | R6 |
| O (stuckSessionAbortMs) | 三盲: 默认值/设多少/能否救stall全未知 | R5 |
| L (降xhigh→medium) | 生存偏误: 18/18全恢复期对故障期存活零信息量; 且medium→body high不产reasoning=丢全部思考 | R4/R7 |

### 关键机制勘定 (留给未来重试者)
1. **overflow触发源** = NVCF `assistantError` 回推 (服务端), 非openclaw客户端计token达contextWindow. 客户端侧参数 (toolResultMaxChars/contextTokens) 不在主触发链. 详见 [[openclaw-overflow-trigger-mechanism-2026-07-01]].
2. **openclaw thinking→body映射** (硬编码, 非配置): `--thinking xhigh`→body `reasoning_effort:"max"`; `--thinking medium`→body `reasoning_effort:"high"`. medium/high都不产reasoning_content, 唯max产生. 详见 [[openclaw-thinking-to-reasoning-effort-mapping-2026-07-01]].
3. **cc2跨主机配置混淆教训**: cc2在OC-R5审视时读了HM2的hm40006配置(glm5.1_hm_nv)误当HM1 openclaw.json(deepseek-v4-pro). 未来cc2审视前须先SSH确认目标主机配置路径.

### 最终结论
- **xhigh 维持** (thinkingDefault=xhigh 不变). 理由: 故障期max样本=0, R6/R7安全闸条件全程未达成, 数据不充分不切. 8轮(除R1/R3日志字段)全NOP是合法且正确收尾.
- **hm40006 metrics 新增 caller/reasoning_effort/thinking_type 三字段** (R1/R3) — 这是全链唯一实质落盘改动, 为未来effort分桶回溯解了结构性障碍.
- **不为轮数压力改参数**: 8轮下来条件始终没满足, 在零信息量数据上强制切L才是真失败. NOP是"安全闸没被数据打开所以没动", 正是铁律体现.

---

## 量化准入闸 (给未来重试者, 硬条件非建议)

**动机挂钩 (R7生存偏误)**: 此闸要求"故障期max样本"正是R7认定"18/18恢复期100%≠故障期存活, 恢复期数据对L零信息量". 门槛高不是过度保守可放宽, 是因为降xhigh=丢全部reasoning(高成本不可逆), 必须用故障期难样本证medium能扛.

**准入条件**: 允许进入"考虑降 thinkingDefault xhigh→medium"阶段, 须**全部**满足:
1. **故障期max样本 ≥ 30**, 拆解: **≥2 独立NVCF故障事件 × 每事件 ≥15 样本**.
2. **事件间隔 ≥ 4h, 且间隔期内须有连续≥30min 零502作恢复证据** (用恢复证据比固定时长诚实, 防把一次长故障劈成两段或合并两次短故障).
3. **每事件内样本时间跨度 ≥ 30min** (排除瞬间密集采样无信息量, 15样本+30min≈均隔2min防burst).
4. **故障期定义 (双条件, 须同时满足)**:
   - (a) 窗口内 `all_tiers_exhausted` (status=502) 绝对数 ≥ M, **AND**
   - (b) 窗口内 502率 ≥ 3× 历史非故障期 p99 基线.
   - 阈值不拍脑袋: M 与基线须从历史 hm_metrics 非故障窗口统计得出 (如取近7天 all_tiers_exhausted 计数的 p99 作为 (b) 的基线乘3, 取非故障窗口 502 绝对数 p95 作为 M). 结案时不拍具体数, 但未来重试者**必须先算基线再定M**, 不得用"超阈值"含糊.
5. **对照样本 (case-control)**: 同窗口内 high effort 须有等量样本 (≥15/事件) 以隔离"是medium不行还是这窗口谁都不行". high都死→降级无意义; high没样本→归因不可信.
   - **by-design 安全锁明示**: 条件5意味着, 除非未来 high 自然流量在故障窗口显著上升, 或接受主动 high 探针 (违背 R7 U 决议: 探针不真实+无法预知故障时机), 否则 L 路径**实质关闭**. 这是 by-design 安全锁非 bug, 不留含糊后门 (同 R7 S 坍缩教训).
6. **接受质量代价**: 降xhigh→medium=丢全部reasoning (medium→body high不产reasoning_content), 须明确这是"换故障期存活率"的交易, 非无损优化.

**当前状态**: 故障期max样本=0 → 闸1锁死, 任何人在数据满足前不得动 thinkingDefault.

**数据前置 (闸可执行性基础)**: 闸1的"故障期max样本≥30"依赖 OC-R1/R3 落盘的 caller/reasoning_effort/thinking_type 三字段 — 不落盘, 未来连"故障期max样本"都数不出来. 三字段不是孤立收尾, 是准入闸的可执行性基础.

---

## 待办 (不落地, 记入结案 — 注意依赖关系)

**故障态触发器** (未来若需故障期max样本): 建议方案——监听 hm40006 `error_type=all_tiers_exhausted` 出现率>阈值 → 该窗口内对 caller=openclaw + reasoning_effort=max 的请求追加详细reasoning日志字段 (reasoning_content是否落表/reasoning_tokens数), 攒真实难样本. **非主动探针** (探针不真实), 是被动+条件触发. 落地需改hm40006错误分支+采样逻辑, 违反"每轮少改", 留给未来专门一轮做, R8不实施.

**依赖关系 (必须标注)**: 此触发器是准入闸条件1的前置 — 没有它, NVCF故障稀少+openclaw自然流量低 → 故障期max样本永远攒不到30 → 闸1永久不满足 → L路径永久关闭. 待办不是"以后再说", 是"L路径唯一钥匙". 未来重试者若想开L路径, 须先专门一轮做此触发器.

---

## cc2再审结论 (bbo31wb9r 限审 → blk4q108h 复审)
- 准入闸 X=30 (2事件×15): cc2确认合理 (准入门槛非决策门槛, 15/事件做Fisher exact只检大效应量, 低限够用).
- 事件间隔: cc2要求加"间隔期连续≥30min零502作恢复证据" (已补入条件2).
- 故障期定义: cc2指出"超阈值"未闭合, 要求双条件(绝对数≥M AND 502率≥3×历史p99基线)+先算基线再定M (已补入条件4).
- 条件5 case-control: cc2确认是by-design安全锁, 要求明写"L路径实质关闭除非high流量上升或接受探针" (已补入条件5明示句).
- 漏写补入: R7生存偏误动机挂钩(已补)、待办依赖链(已补)、三字段→闸1可执行性(已补).
- 结案事实不再审 (8轮定谳). 复审通过, 不开R9.

## ⏳ 8轮全链收口完成 (无下一轮翻转标记)
