# R551 (HM1): hm40006 动态 surge fallback 机制 (架构级, 用户授权去掉"每轮少改"规则)

## 背景
R550 发现 NVCF function 动态 surge 轮换 (kimi/dsv4p 互替), 静态路由 tier_order=[mapped_model]
(R503) 下首选 function surge → 全挂, peer fallback 6h 零成功 (对端同 surge).
用户决定: ①hermes timer 继续跑 ②去掉"每轮少改"铁律, 授权架构级改动.
本轮实现 func_health 健康度感知的动态 fallback 机制 (默认关闭, 零回归).

## 机制设计
- 新增 `gateway/func_health.py`: per-model 滑动窗口 (WINDOW=20) 成功率计数器, 线程安全.
  - 冷启动 (样本<5) 视作健康=1.0 (避免误判).
  - 健康度阈值 0.80 (HEALTH_THRESHOLD), is_healthy(model) = health>=阈值.
- `config.py` 加 `FALLBACK_GRAPH` 白名单 dict (默认空=保持R503行为):
  - `{"kimi_nv": ["dsv4p_nv"], "dsv4p_nv": ["kimi_nv"]}` 可启用.
  - 空graph → tier_order=[mapped_model] 单元素, 零行为变化.
- `upstream.py execute_request` 改动:
  - tier_order = [mapped_model] + [FALLBACK_GRAPH里健康度达标的备选]
  - 双重保护: 白名单 (FALLBACK_GRAPH) + 实时健康度 (surge中的function不会被选)
  - 成功/失败路径都调 func_health.record_result() 更新滑动窗口
  - 跨model fallback仍受"各agent各后端语义"约束: 只在白名单显式配置的model对之间启用

## 改动文件 (HM1, 本机)
- 新增 `/opt/cc-infra/proxy/hm-proxy/gateway/func_health.py` (96行)
- 改 `/opt/cc-infra/proxy/hm-proxy/gateway/config.py` (+FALLBACK_GRAPH配置块, ~15行)
- 改 `/opt/cc-infra/proxy/hm-proxy/gateway/upstream.py`:
  - import func_health + FALLBACK_GRAPH/FALLBACK_HEALTH_THRESHOLD
  - tier_order 动态计算 (L460-478)
  - 成功路径 record_result(True) (L528)
  - 失败路径 record_result(False) (L535)

## 验证
### 1. AST + import 检查
- func_health.py/config.py/upstream.py 全 AST OK
- 容器内 `from gateway import func_health,config,upstream` 全 OK
### 2. 默认行为零回归 (空graph)
- 重启 hm40006, health ok, /v1/models 三模型齐全
- kimi_nv 请求 200 1.2s, 日志 `tier_chain=['kimi_nv'] (no fallback, 3model)` — 与R503完全一致
### 3. 机制逻辑验证 (monkeypatch模拟)
- 模拟 kimi_nv 20次失败 → health=0.0, is_healthy=False
- 模拟 dsv4p_nv 20次成功 → health=1.0, is_healthy=True
- 启用 FALLBACK_GRAPH['kimi_nv']=['dsv4p_nv'] → computed tier_order=['kimi_nv','dsv4p_nv'] ✅
- 断言通过: kimi surge + dsv4p健康 → 自动加入dsv4p作备选
### 4. 重启后冷启动干净
- snapshot={} (无残留), is_healthy(kimi_nv)=True (冷启动)

## 未做 (待用户决策)
**FALLBACK_GRAPH 默认空 (关闭), 未启用跨model fallback.** 启用需用户授权, 因为:
- kimi surge → fallback dsv4p: hermes 的 thinking 产出从 rc 500tok 降到 159tok (质量退化)
- dsv4p surge → fallback kimi: opencode 的模型语义从 deepseek 变 kimi (违反"各agent各后端")
- 这是 质量vs可靠性 的权衡, 不该CC替用户定.
启用方式: config.py 取消注释 `{"kimi_nv": ["dsv4p_nv"], "dsv4p_nv": ["kimi_nv"]}` 两行 + restart.

## 铁律
- 改前必有数据: R550 评估轮已坐实 NVCF动态surge + 6h零peer fallback成功
- 改后必有验证: AST/import/默认零回归/机制模拟 全通过
- 只改对端: 本轮改HM1本机 (用户授权破例自改, 同R519); HM2源码待下轮同步 (HM2也是对端, CC改HM2合规)
- 聚焦hm-40006--nv: 仅改 hm40006 gateway
- 写入仓库: 本round + 源码快照 commit
- "每轮少改"已去掉 (用户2026-07-02决定), 本轮多文件架构级改动

## 备份清单
- 无 .bak (新增文件 + 小改; func_health.py 是全新; config/upstream 可git回滚)

## ⏳ 轮到HM2优化HM1
