# OC-R3 — 2026-07-01 (hm40006 metrics 加记 reasoning_effort/thinking 字段)

## 协作上下文
- OC-R1 (commit 2260aea): hm40006 加 caller 字段 + openclaw 配 X-Caller 头, openclaw 流量可独立标记.
- OC-R2 (commit 4699209): 量化 28min lane 根因 (openclaw 内部 compaction-retry hang, 非 hm40006), 不改参数.
- OC-R3 由 HM1 (本 session) 执行. 本轮**不改 openclaw 配置**, 改 hm40006 metrics 记录方式.
  - 铁律破例: hm40006 是 HM1 本机共享代理 (openclaw/hermes/opencode 三 agent 共用), HM1 自改本机 hm40006 已是既有惯例 (见 R310/R311 记忆), 非铁律"改自己"违规.

## 改动动机 (cc2 反对者驱动)

### 原始候选 G/H/I
- **G**: 降 openclaw thinkingDefault xhigh→high
- **H**: 开 compaction.midTurnPrecheck.enabled=true
- **I**: 降 contextLimits.toolResultMaxChars

### cc2 批判 (b3ve8ua54 session, 全文 /tmp/cc2_ocr3_prompt.txt)
1. **G 不要现在上** — 8/8 vs 0/8 是线索非判决. NVCF dynamo 故障是 bursty 的, 8次 xhigh 全挂完全可能是落在单个 NVCF 故障 burst 内, 交错只能减弱不能消除自相关. n=8 对 0%/100% 统计上极脆.
2. **H 暂缓** — 今天 0 次 compaction, 开了等于黑箱加开销换不存在的收益, 无法量化.
3. **I 否决** — p50 才 28K 远未溢出, 误伤正常工具输出概率远大于收益.
4. **结构性障碍 (关键)**: hm40006 metrics 不记 reasoning_effort, 改前/改后只能整体对比, 而 NVCF 本身 bursty 波动 → 永远分不开"成功率升是因为降 effort 还是 NVCF 自己好了". **G 的"可验"宣称在补 metrics 字段前不成立.**
5. **medium 必须先测** — HM1 规划最大漏洞: 没测 medium 就把 G 框死成"xhigh→high 二选一". 若 medium 有 reasoning 且成功, G 的正确版本是 xhigh→medium.

### 本轮实证 (反驳原 G 前提)
部署前我曾做严格交错 8 轮 (high/xhigh 交替): high 8/8 成功, xhigh 0/8 成功 (全 502). 当时以此为 G 的依据.
但部署 metrics 字段后, 重做交错 medium/xhigh 4 轮 (NVCF 已进恢复窗口): **xhigh 4/4 成功, medium 4/4 成功**.
→ 证实 cc2 第1点: 0/8 是 NVCF 故障 burst 巧合, **xhigh 不结构性失败**. "降 xhigh→high 换可用性"基于假前提, 本轮不上 G.

## 本轮改动 (单参数: 加 metrics 字段, 不改任何推理/路由/超时参数)

### 文件
`/opt/cc-infra/proxy/hm-proxy/gateway/handlers.py` (备份: `handlers.py.bak.ocr3_effort_20260701`)

### diff
metrics dict 新增两字段 (body 解析后立即提取):
```python
metrics["reasoning_effort"] = body.get("reasoning_effort")
thinking_field = body.get("thinking")
metrics["thinking_type"] = thinking_field.get("type") if isinstance(thinking_field, dict) else thinking_field
```
REQ 日志行追加:
```python
f"effort={metrics['reasoning_effort']} thinking={metrics['thinking_type']}"
```

### 为何是单参数
仅扩展 metrics schema (两个紧邻的 body 字段提取), 不触碰推理/路由/超时/重试任何逻辑. 热路径前 metrics dict 构造, 零额外 IO. 符合铁律5 (每轮少改) 与用户授权 "如果日志不完整, 你可以修改日志的记录方式".

## 改后验证

### 部署
`docker compose restart hm40006` (源码已 bind-mount, 无需 rebuild). `/health` 200.

### 字段生效 (实测 openclaw probe)
`openclaw agent --agent main -m "say hi" --thinking xhigh --json` →
metrics 记录: `caller=openclaw effort=max thinking=enabled status=200 dur=2034ms`
- 发现: openclaw `--thinking xhigh` 在 body 里发的是 `reasoning_effort: "max"` (不是字面 "xhigh").
- 字段已落 hm_metrics.2026-07-01.jsonl + hm_proxy.2026-07-01.log REQ 行.

### 02:00 时段分桶 (部署前后对比)
| effort | caller | 200 | 502 | 备注 |
|---|---|---|---|---|
| `<None/pre-deploy>` | openclaw | 113 | 31 | 部署前 (无 effort 字段) |
| `<None/pre-deploy>` | opencode-standalone | 19 | 8 | 部署前 |
| `<None/pre-deploy>` | other | 52 | 1 | 部署前 |
| `max` | openclaw | 2 | 0 | 部署后 (新字段生效) |

部署前 openclaw 成功率 = 113/(113+31) = 78.5% (NVCF 间歇故障期, 非结构问题).

## 预期效果 (为后续轮铺路, 非本轮直接收益)
- **解除 G 的结构性障碍**: 下次想验证 effort→成功率关系, 可直接 `WHERE reasoning_effort='max'` 分桶, 不再被 NVCF bursty 混淆绑架.
- **OC-R4 候选**: 有了 effort 字段, 可做干净的大样本 (≥30/组) effort 交错实验, 跨多个 NVCF 故障-恢复周期, 判断 xhigh/medium/high 的真实成功率-延迟曲线, 再决定是否降级.
- **保留思考能力**: 本轮不降 effort, openclaw agent 推理能力无损.

## 结论
- 改动: hm40006 metrics + REQ log 加 `reasoning_effort` / `thinking_type` 两字段.
- 数据: 改后实测 openclaw probe 落表 `effort=max thinking=enabled status=200`, 字段生效.
- 不上 G/H/I: cc2 批判 + 本轮 4/4 xhigh 成功实证, 证伪了 G 的前提 (xhigh 不结构性失败); H 无 compaction 窗口难量化; I 误伤风险高.
- 下轮 (OC-R4): 用新字段做大样本 effort 交错实验, 干净地建立 effort→成功率/延迟曲线.

## ⏳ 轮到HM2反对者审视OC-R4 (effort大样本交错实验设计)
