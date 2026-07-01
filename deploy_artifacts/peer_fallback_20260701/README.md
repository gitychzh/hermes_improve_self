# 跨机 peer fallback (2026-07-01)

## 背景

用户要求两台机器互为后备: 当一台 hm40006 的单 tier 5 key 全失败 (all_tiers_exhausted)
时, 不直接返回 502 给 agent, 而是转发请求到对端 hm40006 同模型, 由对端再试一遍.
对端也失败才真正返回 502. 这是框架代码互保的一层.

## cc2 三轮仲裁的安全约束 (用户选择"做自动跨机fallback"而非cc2建议的"探针+手动切")

1. **网关侧实现, 单点** — 不在三个 agent 客户端各实现一遍.
2. **只在 all_tiers_exhausted 时转发** — 不在单 key SSL error 转发, 否则 F-fix
   (commit d8aa479) 删掉的"跨机重试"会以转发形式复活, 且两次跨机往返比本地重试慢.
3. **429 (all_429) 不转发** — 429 是 key 级限流, 跨机不增加 key 池, 转发无用, 直接返回
   让客户端退避.
4. **循环防护 X-Fallback-Hop** — 转发请求带 `X-Fallback-Hop: 1` 头, 对端收到 hop≥1 时
   不再二次转发 (无状态 hop count). 即"对端也 all_tiers_exhausted"时直接返回 502.

## 改动文件

- `gateway/config.py`: 新增 3 个 env 变量
  - `HM_PEER_FALLBACK_ENABLED` (默认 '0')
  - `HM_PEER_FALLBACK_URL` (默认 '')
  - `HM_PEER_FALLBACK_TIMEOUT` (默认 '120')
- `gateway/handlers.py`:
  - imports 增加 3 个 peer fallback config.
  - `all_keys_exhausted` 分支: 在返回 502 之前, 检查 hop<1 且非 429 → 调用 `_peer_fallback`.
  - 新增 `_peer_fallback(self, body, mapped_model, is_stream, metrics)` 方法:
    - `http.client.HTTPConnection` 到对端, POST /v1/chat/completions, 带原 body.
    - 注入 `X-Fallback-Hop: 1`, `Authorization: Bearer <HM_GATEWAY_API_KEY>`,
      透传 `X-Caller`/`X-Request-Id`.
    - 对端 5xx/429 → 不转发, 返回 False, 让调用方返回本地 502.
    - 对端 2xx → send_response + 流式 relay body (8192 chunk, SSE 和 buffered JSON 都适用).
    - 异常 (connect/relay) → 返回 False.
- 双机 `docker-compose.yml` hm40006 env 增加:
  - HM1: `HM_PEER_FALLBACK_URL=http://100.109.57.26:40006` (HM1→HM2)
  - HM2: `HM_PEER_FALLBACK_URL=http://100.109.153.83:40006` (HM2→HM1)
  - 双机 `HM_PEER_FALLBACK_ENABLED=1`, `HM_PEER_FALLBACK_TIMEOUT=120`

## 验证 (已做)

- 双机 hm40006 restart 后 /health OK, env 注入成功 (ENABLED=1, URL 各自指向对端).
- 跨机连通双向 OK: HM1 容器 → HM2:40006 /health = 200; HM2 容器 → HM1:40006 /health = 200.
- 循环防护 hop 头: 向 HM1 发带 `X-Fallback-Hop: 1` 的请求, 正常服务 (成功路径不看 hop);
  失败路径会读 hop, hop≥1 不再转发 — 代码在 handlers.py `all_keys_exhausted` 分支.
- 正常流量无副作用: 7 req/2min 全部本地成功, 无 HM-PEER-FB 日志 (只在失败时触发).

## 验证 (待真实故障触发)

- 真实 all_tiers_exhausted 时转发生效: 用户选择"等真实故障"而非强制触发测试.
  监控器 watch `HM-PEER-FB` 日志行, 第一次 NVCF 故障窗口会捕获.
- 预期日志: `[HM-PEER-FB] local all_tiers_exhausted (model=...), attempting peer fallback to ...`
  成功: `[HM-PEER-FB] peer fallback OK: status=200 bytes=... ttfb=...ms`

## 铁律

- 改自己 (HM1) 是破例自改 (用户授权框架互保工作, 与 unify-nv/bind-mount/auth-layer 先例一致).
- HM2 侧改动 (compose env + gateway 源码 rsync) 是 HM1 作为 optimizer 改对端, 符合"只改对端".
- 所有改动已写入本仓库 deploy_artifacts/peer_fallback_20260701/.
