# R576: dsv4p_nv 关闭 force-stream 升级 (修复 content 丢失 90%)

**日期**: 2026-07-03
**方向**: CC 直接改两机(取消交替优化后首轮, 见 rule.md 931eb9f)
**链路**: hm-40006--nv / nv_40006_uni

## 背景

用户反馈"本机 openclaw 还是很卡"。系统性排查发现 openclaw 自身的 dsv4p_nv 请求
表面成功(200),但 **content 字段为空**,导致 openclaw 收到空响应 → 卡/重试。

## 改前数据 (HM1 nv_40006_uni, 2026-07-02 当日)

FORCE-STREAM-OK 日志统计 (force_stream_upgrade 把非流升级成流式累积):

```
19x content=0c   (content 完全为空)
 1x content=3c
 1x content=12c
```

**90% (19/21) 的 force-stream 累积后 content=0c**。dsv4p_nv 占 59 条 (kimi 4 条)。

典型:
- `[NV-FORCE-STREAM-OK] accumulated 0 chunks, content=0c reasoning=211c in 31458ms`
- `[NV-FORCE-STREAM-OK] accumulated 0 chunks, content=0c reasoning=2c in 2-19s` (pexec surge 期)

## 根因 (抓包 + 原始 chunk 复现)

deepseek-ai/deepseek-v4-pro 在 **流式 + thinking:{type:enabled}** 模式下:
- 6 个 chunk 全部 `delta.content=None`,内容只在 `delta.reasoning_content`
- `finish_reason=length` (思考消耗 max_tokens, 正式 content 从不产生)
- 即使 finish=stop (思考短),content 在最后一个末尾 chunk,易被 sse_buffer 残留丢弃

对比直连 integrate 裸测:
- 非流 max_tokens=200: `finish=stop content='Hi.'` ✓ (26-35s)
- 流式 max_tokens=50: `finish=length content=None` ✗ (思考用完 token)

**force-stream 升级对 dsv4p 反而有害**: 把原本能正常返回 content 的非流请求,
升级成流式后 content 丢失。

## 改动 (两个文件)

### 1. config.py — 新增 per-model 排除配置
```python
NVU_FORCE_STREAM_EXCLUDE_MODELS = [m for m in os.environ.get(
    'NVU_FORCE_STREAM_EXCLUDE_MODELS', 'dsv4p_nv').split(',') if m]
```
默认排除 dsv4p_nv。env 可覆盖。

### 2. handlers.py
- import 增加 `NVU_FORCE_STREAM_EXCLUDE_MODELS`
- `mapped_model = detect_nv_model(request_model)` 提前到 force_stream 判断之前
- force_stream_upgrade 判断加 per-model 排除:
  ```python
  force_stream_upgrade = (NVU_FORCE_STREAM_UPGRADE == "1"
                          and not is_stream
                          and mapped_model not in NVU_FORCE_STREAM_EXCLUDE_MODELS)
  ```
- **附带修复** (sse_buffer 残留): force-stream 累积循环 `while "\n" in sse_buffer`
  只处理含换行的完整行, 最后一行无 trailing newline 会残留被丢. 循环 break 后
  补一段处理 sse_buffer 残留. (非本 bug 主因, 但代码质量改进.)

kimi_nv / glm5_1_nv 仍走 force-stream (其流式 content 正常)。

## 验证 (改后)

HM1 连测 3 次 dsv4p (非流, thinking):
```
#1: status=200 30.0s finish=stop content='4'
#2: status=200 23.5s finish=stop content='4'
#3: status=200 34.6s finish=stop content='4'
```
✅ content 全部有值, finish=stop.

kimi 仍 force-stream 不受影响:
```
kimi status=200 11.0s finish=stop content=' Hi there! 👋'
```

日志确认 dsv4p `[REQ] stream=False` + 无 NV-FORCE-STREAM 标记。

HM2 同步部署后端到端:
```
HM2 dsv4p: status=200 22.8s finish=stop content='4'
```
✅ 通过。

## 回滚

`NVU_FORCE_STREAM_EXCLUDE_MODELS=""` (空) → dsv4p 恢复 force-stream, 零代码改动。
或还原 `handlers.py.bak.R576` / `config.py.bak.R576`。

## 待观察

openclaw 真实流量下 dsv4p 非流 latency 稳态 (实测 23-35s, 接近但低于 61s timeout)。
若 openclaw 大 context 请求接近 timeout, 可考虑提高 NVU_FORCE_STREAM_UPGRADE_TIMEOUT
或对 dsv4p 单独调优。
