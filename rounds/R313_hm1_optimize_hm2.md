# R313: HM1→HM2 — ⏸️ 无逻辑变更 (NVCF硬限制确证 + 修正compose误导注释)

**时间**: 2026-06-29 23:20 UTC
**角色**: HM1 (opc_uname) 工程师 / HM2 (opc2_uname) 反对者 / CC 总指挥+托底验证
**前轮**: R312 (HM2→HM1 无操作稳定态确认), HEAD `346233e`, 标记 `⏳ 轮到HM1优化HM2`
**本轮重新设计**: CC 作为总指挥重新启动交替优化, HM1 工程师出方案 → HM2 反对者碰撞 → CC 独立托底核实

## 1. 本轮流程 (两轮碰撞)

### 1a. 第一方案 (HM1 提出, 已作废)
empty_200 分支实现"同key重试一次再换key" (兑现 R1 注释)。
**HM2 反对者驳回 (CC 核实三条证据全属实)**:
1. HM1 数据口径错 (把全表2h当30min; empty_200 "60min 12次"实为全表)
2. 失败请求 23/23 结构: 首 attempt empty_200(秒返) + 后续 NVCFPexecTimeout(40-52s, mean 45.5s) = NVCF 持续故障窗口, 非瞬态抖动, 同key重试救不回
3. 成功请求里 empty_200 后换 key 12/12=100% 救回 (key_cycle_details 含 empty_200 且 status=200 共12个全成功), 当前 continue 换 key 已是最优, 同key重试会破坏已验证路径

### 1b. 第二方案 (HM1 提出, 反对者二审反对)
"tier 整体退避逻辑": 检测 empty_200+紧邻timeout 模式 → tier 退避 12s 重试。
**HM2 反对者二审驳回 (CC 核实)**:
- 推翻 HM1 核心推断"NVCF 窗口>120s": 失败请求间隔121s 是 Hermes 每~2min 发请求节奏, 不是窗口长度
- **决定性反证 (CC 独立核实部分属实)**: 失败请求 b2f10f9a 挣扎118s 窗口内有9个成功请求穿插 → NVCF 故障是单请求/单连接局部 hang, 非纯全局窗口 (退避对下一key是否hang零预测力)
- 退避确定性把失败耗时从128s拉到176s+, 违背低延迟; 触发条件漏掉3个无empty_200的纯timeout失败; 工程复杂违反"每轮少改"

### 1c. 方向A (反对者提出, CC 核实数据属实但不本轮做)
empty_200 后首 timeout mean 47s vs 后续 timeout mean 14s (budget被压)。
若让 empty_200 后首 timeout 走更短超时可把失败 128s→60-70s 降 P95。
**CC 核实**: 数据属实(首26个mean46897ms/后35个mean14484ms), 但会误伤13个 empty_200 后慢成功请求(63-120s, 占>45s成功请求30个中的13个), 需A/B验证可截断性, 非单参数, 留待后续轮次。

## 2. NVCF function_id 排查 (CC 按用户指令做)

实测 (curl 经 mihomo 7894 + key1, model=z-ai/glm-5.1):
| function_id | 响应 | 结论 |
|---|---|---|
| 4e533b45 (当前在用) | 200, `"model":"z-ai/glm-5.1"`, 有效content | ✅ 正确路由 glm5.1 |
| 822231fa (config.py 默认) | **404 Not Found** | ❌ 已被 NVCF 下架 |

**修正历史认知**: compose 注释 "R275: revert to deepseek function; 822231fa causes universal SSLEOF" 是误导。4e533b45 不是 deepseek 专属 (实测返回 glm5.1); 822231fa 换掉的真实原因是已 404 下架 (非 SSLEOF)。function_id 不是失败根因, 当前 4e533b45 是对的, 无更好可换。

## 3. NVCF 平台层同步故障确证 (系统级排查)

HM1(deepseek) 与 HM2(glm5.1) 失败时间精确同步 (不同模型不同 function_id 却同分钟失败):
- 重合分钟: 21:54, 22:53, 22:58, 22:59, 23:01 (5个)
- HM2 失败率 8.21% (23/280, 180min), HM1 4.83% (10/207)
- 失败低频散布, 非宕机 → NVCF 平台层间歇整批不可用

## 4. 本轮实际改动 (仅注释, 不动逻辑)

HM2 `/opt/cc-infra/docker-compose.yml` line 478 注释修正:
- 旧: `# R275: HM1→HM2 — revert to deepseek function; 822231fa causes universal SSLEOF on all keys`
- 新: `# R313: HM1→HM2 — 实测4e533b45配z-ai/glm-5.1正确返回glm5.1响应(非deepseek专属); 822231fa已404下架(非SSLEOF); 修正R275误导注释; 仅改注释不动值`
- function_id 值不变 (4e533b45-dc54-4e3a-a69a-6ff24e048cb5)
- 备份: `docker-compose.yml.bak.R313_20260629_comment_fix`

## 5. 验证 (实质数据流向, 非表面)

| 项 | 结果 |
|---|---|
| compose 语法 (docker compose config --services) | ✅ hm40006, 无error |
| 容器健康 (/health) | ✅ status=ok, glm5.1_hm_nv |
| function_id 值未变 (容器env) | ✅ 4e533b45... |
| **实测链路** (curl 4e533b45 + glm5.1) | ✅ 200, `"model":"z-ai/glm-5.1"`, 有效中文content |
| 注释改动不影响运行容器 | ✅ 注释不进env, 无需restart |

## 6. 结论

HM2 hm40006 gateway 在**代码逻辑**和**配置(function_id)**两个维度均已是最优:
- empty_200/timeout 处理: 换key 12/12 救回, 同key重试/退避均被数据证伪
- function_id: 4e533b45 实测正确, 822231fa 已下架
- ~8% 失败是 NVCF 平台层间歇整批不可用 (HM1/HM2 同步), gateway 层无法消除

**铁律: 只改HM2不改HM1** ✅ (本轮只改 HM2 compose 注释, 未动 HM1)
**改前有数据** ✅ (两轮碰撞+CC三次独立核实+function_id实测)
**改后有验证** ✅ (compose语法+健康+function_id值+实测链路)
**聚焦 hm-40006--nv** ✅
**每轮少改** ✅ (仅注释, 0逻辑变更, 0参数变更)

## 7. 后续建议 (供下轮 HM2 优化 HM1 参考)
- HM1/HM2 gateway 层已碰 NVCF 硬限制, 继续单参数微调无意义
- 唯一可能有疗效的 gateway 新逻辑: 方向A (empty_200后首timeout短超时), 但需先A/B验证可截断性, 且会误伤慢成功请求, 非单参数
- 建议: 守稳模式 + 紧急修复, 或转向 NVCF 侧反馈/换时段避峰

## ⏳ 轮到HM2优化HM1  ← 脚本检测此标记(交替优化序列)
