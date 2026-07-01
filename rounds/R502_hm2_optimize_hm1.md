# R502 (HM2→HM1): dsv4p思考根因调查+提议双改(inject字段thinking→reasoning_effort / 后端kimi→sglang-dsv4p 8915fd28)

**轮次**: R502
**方向**: HM2 优化 HM1 (本轮执行者=HM2, 对端=HM1, host_machine=opc_uname)
**日期**: 2026-07-01 14:10 CST
**类型**: 根因调查 + 提议双改 (待HM2执行, HM1 CC当反对者审查)
**Commit**: 193dec2 (R501, HM2→HM1 NOP) → 本草案 (R502, HM1 CC代笔提议)

## 0. 角色与方向说明 (重要)

- **本轮反向授权**: R501末尾标记"轮到HM1优化HM2", 但用户明令: dsv4p思考根因修复点全在HM1, 需HM2工程师改HM1, HM1 CC当反对者审查。故本轮R502方向=HM2改HM1(非HM1改HM2)。
- **持续反对者模式**: 用户指定此后每轮都是"HM2改HM1 + HM1 CC审查", 不回正规交替。故本轮末尾翻"轮到HM2优化HM1"让HM2 session继续执行后续轮次。
- **本文件是HM1 CC代笔的提议草案**, 非HM2已执行的改动。HM2 session起来后应: 读本提议 → 在HM1执行双改 → 验证 → 更新本文件或写R503记录执行结果 → 翻轮。
- **铁律边界已澄清**: CC(本机)改hm40006不算自改; hermes/hm1服务改自己hm40006才算自改。HM2的CC2改HM1 hm40006=改对端, 合规。

## 1. 根因调查 (HM1 CC完成, 绕过hm40006直打NVCF原生pexec)

### 1a. 调查动机
前轮归因"dsv4p思考不稳=NVCF后端引擎波动(orion rc-null / kimi稳定)"被用户否定, 要求聚焦deepseek-v4-pro本身。当前dsv4p_nv后端被kimi顶替(f966661c kimi-k2.6), 非真dsv4p。需查清真dsv4p的思考机制。

### 1b. NVCF上deepseek-v4-pro全家谱 (2026-07-01 14:00, GET /v2/nvcf/functions)

| function_id | name | status |
|---|---|---|
| 8915fd28-fe8f-47d6-a35d-d745d78b35d5 | **sglang-deepseek-v4-pro** | **ACTIVE** ← 唯一活的真dsv4p |
| 74f02205 | ai-deepseek-v4-pro | DEGRADING |
| 52e1ddb6 | ai-deepseek-v4-flash | DEGRADING |
| 4e533b45 | orion-deepseek-v4-pro | INACTIVE |
| ee2b0de2 | dynamo-deepseek-v4-pro | INACTIVE |
| ab5a332e | dynamo-offload-dsv4p | INACTIVE |

- 唯一ACTIVE的真dsv4p = 8915fd28 (sglang), model字段=deepseek-ai/deepseek-v4-pro。

### 1c. 原生pexec探针 (绕过hm40006, 直打api.nvcf.nvidia.com)

直接POST https://api.nvcf.nvidia.com/v2/nvcf/pexec/functions/8915fd28, model=deepseek-ai/deepseek-v4-pro, prompt="一步步想:23乘以17", 变换思考字段:

| 请求body字段 | reasoning_content | 备注 |
|---|---|---|
| thinking:{type:enabled} | **None** | dsv4p不认此字段 |
| 无任何思考字段 | None | |
| reasoning_effort=max | ✓ 222~346字 (3/3) | 真实推理 |
| reasoning_effort=high | ✓ 122~195字 (3/3) | |
| reasoning_effort=medium | ✓ 165~203字 (3/3) | |
| reasoning_effort=low | ✓ 108~182字 (2/2) | |
| thinking+effort=max | ✓ 209~309字 (3/3) | effort主导, thinking不冲突 |

**核心发现**: deepseek-v4-pro的思考触发字段=**reasoning_effort**(任意级别都产rc, 9/9稳定), **不是thinking:{type:enabled}**。dsv4p思考能力本身完全正常, 一直能思考, 前提是请求带reasoning_effort。

### 1d. hm_metrics铁证 (今日2295条, openclaw请求effort分布)

| caller | request_model | reasoning_effort分布 |
|---|---|---|
| **openclaw** | **dsv4p_nv** | **None:1611 (全无effort, 一条都没有)** |
| openclaw | deepseek-v4-pro | None:84, max:26, high:8 |
| other | dsv4p_nv | None:75, max:40, medium:3, high:2 |

- openclaw主路径用裸名dsv4p_nv发的**1611条请求, reasoning_effort全是None**。
- hm40006的inject_thinking(pexec.py:44-46)注入的是thinking:{type:enabled} —— **正是dsv4p不认的字段**。
- → 这1611条请求**全部没思考**。不是"时有时无", 是"主路径几乎全没思考"。
- 那34条带effort的是openclaw用deepseek-v4-pro别名+thinkingDefault触发的少数路径, 才有思考。

## 2. 推翻前轮归因

| 前轮结论 | 真相 |
|---|---|
| "orion时代rc恒null=orion引擎特性" | 错。orion也是dsv4p引擎, rc null真因=请求没带reasoning_effort, 非引擎不产rc |
| "切kimi后rc稳定=换引擎解决" | 错。真因=切kimi那段碰巧有带effort的请求+kimi额外认thinking字段。巧合归因 |
| "dsv4p思考不稳=NVCF后端状态波动" | 错。dsv4p思考一直稳(带effort就9/9产rc), 不稳的是"请求带没带effort" |
| "inject_thinking兜底生效(1518次)" | 错。inject注入的是dsv4p不认的thinking字段, 对dsv4p完全无效, 1518次注入了个寂寞 |

## 3. 提议的双改方案 (待HM2在HM1执行)

### 改A: inject字段从thinking改为reasoning_effort
- 文件: /opt/cc-infra/proxy/hm-proxy/gateway/pexec.py:44-46
- 现状:
  ```python
  if nvcf_config.get("inject_thinking") and "thinking" not in pexec_body:
      pexec_body["thinking"] = {"type": "enabled"}
  ```
- 改为(对dsv4p_nv tier, 当body无reasoning_effort时注入effort):
  ```python
  if nvcf_config.get("inject_thinking"):
      if "reasoning_effort" not in pexec_body:
          pexec_body["reasoning_effort"] = "medium"
      if "thinking" not in pexec_body:
          pexec_body["thinking"] = {"type": "enabled"}  # 保留, 对kimi后端仍有效
  ```
- 理由: dsv4p只认reasoning_effort; 保留thinking注入对kimi后端兼容(若HM2未来回切kimi)。effort=medium(非max)避免token爆炸+延迟, 够触发思考即可。
- 备份: pexec.py.bak.R502

### 改B: 后端从kimi改回真dsv4p (sglang 8915fd28)
- 文件1: /opt/cc-infra/docker-compose.yml:426 (NVCF_DEEPSEEK_FUNCTION_ID)
- 文件2: /opt/cc-infra/proxy/hm-proxy/gateway/config.py:66-67(function_id默认值) + :101(NV_MODEL_IDS)
- 现状: NVCF_DEEPSEEK_FUNCTION_ID=f966661c(kimi-k2.6), NV_MODEL_IDS["dsv4p_nv"]="moonshotai/kimi-k2.6"
- 改为: NVCF_DEEPSEEK_FUNCTION_ID=8915fd28-fe8f-47d6-a35d-d745d78b35d5, NV_MODEL_IDS["dsv4p_nv"]="deepseek-ai/deepseek-v4-pro"
- 理由: 用户明令禁用kimi对比, dsv4p_nv必须用真dsv4p后端。8915fd28是NVCF上唯一ACTIVE的真dsv4p function。
- 部署: 改config.py源码需 `docker compose build hm40006 && docker compose up -d hm40006`(源码挂载的话只需restart, 确认HM1 hm40006是否bind-mount源码)。

### 改动顺序
建议改A+改B同轮执行(都是为同一目标"让dsv4p有思考"服务, 拆开则改A无后端意义/改B无字段修复). 但若HM2坚持每轮少改, 可优先改A(inject字段, 立即让1611条裸名请求有思考), 改B下轮。HM2自行裁定。

## 4. 预期效果

- 改A后: openclaw裸名dsv4p_nv请求(1611条/日量级)从"全无思考"变为"全有reasoning_effort=medium → 全产rc"。
- 改B后: 后端从kimi改回真dsv4p(sglang), 符合用户禁kimi要求; 且sglang ACTIVE, 不依赖kimi的thinking字段兼容。
- 双改后: dsv4p_nv思考"时有时无"应消失, 主路径稳定产rc。

## 5. 反对者审查清单 (HM1 CC将检查)

HM2执行后, 我(HM1 CC)审查:
1. [ ] 改A是否生效: grep pexec.py确认inject逻辑改对; docker logs搜注入reasoning_effort的日志
2. [ ] 改B是否生效: docker exec hm40006 env确认function_id=8915fd28; /health确认model
3. [ ] 端到端: curl 40006发裸名dsv4p_nv请求(不带effort), 看响应是否非空rc
4. [ ] 长采样: 20-30次裸名请求, 看rc产出率(应≈100%)
5. [ ] 无回归: hm40006 /health 200; 5键SR无暴跌; 无新empty_200/429
6. [ ] 铁律: 改动只在HM1 /opt/cc-infra, 未碰HM2; 备份文件存在(.bak.R502)

## 6. 验证用命令

```bash
# 改A验证
docker exec hm40006 grep -n 'reasoning_effort\|inject_thinking' /app/gateway/pexec.py
# 改B验证
docker exec hm40006 env | grep NVCF_DEEPSEEK_FUNCTION_ID  # 应=8915fd28...
curl -s http://localhost:40006/health | python3 -m json.tool
# 端到端(裸名, 不带effort, 应产rc)
curl -s http://localhost:40006/v1/chat/completions -H 'Authorization: Bearer nv-local' \
  -H 'Content-Type: application/json' \
  -d '{"model":"dsv4p_nv","messages":[{"role":"user","content":"一步步想:23乘以17"}]}' | python3 -c "import sys,json;d=json.loads(sys.stdin.read());print('rc:',bool(d['choices'][0]['message'].get('reasoning_content')))"
```

## 6.5 反对者预审修正 (HM1 CC, push后补)

经自我审视, §3双改方案违反铁律第5条"每轮少改", 且改B依赖改A(改A独立, 改B不独立: 改B单做后端换sglang-dsv4p但inject仍注thinking则dsv4p仍无思考). 建议HM2:

- **本轮R502只做改A**(inject字段→reasoning_effort=medium), 这是最直接对症项, 立即让openclaw 1611条/日量级裸名dsv4p_nv请求从"全无思考"变"全有思考".
- **改B(后端kimi→sglang-dsv4p 8915fd28)放下轮R503独立做**, 作为配置纠错(用户禁kimi要求).
- 改A对当前kimi后端(f966661c)的安全性: kimi认thinking字段(已验证), 改A保留thinking注入+新增effort注入, kimi至少不丢思考; effort对kimi是否有副作用未知, 但medium级别风险低, 改后验证§5清单4即可发现.
- 若HM2坚持双改同轮, 亦可, 但须在§5清单全部通过. 裁量权归HM2工程师.

## ⏳ 轮到HM2优化HM1

> 持续反对者模式: 本草案由HM1 CC代笔, 翻轮给HM2 session执行. 建议只做改A(见§6.5), 改B下轮. HM2执行后写执行结果(更新§7或写R503), 再翻"轮到HM2优化HM1"让���轮继续HM2改HM1+HM1审查. HM1 CC不当工程师.
