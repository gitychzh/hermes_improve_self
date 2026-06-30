# 三 Agent 统一接入 hm40006 deepseek-v4-pro（unify-nv）

> 日期：2026-06-30  ·  主机：HM1（opc_uname）  ·  铁律破例自改（用户授权）

## 目标
将 hermes / opencode / openclaw 三个 agent 的模型出口统一收敛到本机 hm40006 的
deepseek-v4-pro（NVCF pexec），统一命名，清理原有第三方模型，工程化便于长期维护。

## 统一命名规范

| 项 | 统一值 |
|---|---|
| base_url | `http://127.0.0.1:40006/v1` |
| model id | `dsv4p_nv` |
| api_key | `nv-local` |
| provider 名 | `nv_cus` |
| 显示名 | `DeepSeek V4 Pro (NVCF pexec via hm40006)` |

注：opencode 顶层 `model` 字段格式必须为 `nv_cus/dsv4p_nv`（provider/model），单写
`dsv4p_nv` 会被解析成 providerID 报 ProviderModelNotFoundError。

## N+1 全局跨 agent 轮询机制（已就绪，无需新开发）

hm40006 容器内 `gateway/rr_counter.py` 维护单一计数器 `hm_nv_deepseek`，持久化到
宿主机 bind-mount 文件 `/opt/cc-infra/logs/proxy40006/rr_counter.json`，atexit + SIGTERM
落盘。三 agent 共用 40006 = 共用此计数器，天然满足：

- 跨 agent 连续递进：hm→k1, opencode→k2, hm→k3, openclaw→k4 ...（实测 key 序列
  k2→k3→k4→k5→k1→k2→k3→k4 严格 N+1 环绕）
- 重启续接：rr_counter.json 在宿主机，`docker restart` 不归零，从当前位置续
  （实测 1094 重启后继续递增，未归零）

**hm40006 容器零逻辑改动**，仅 model_map 加一行 alias。

## 改动清单

### 1. hm40006 容器源码（1 行）
`gateway/config.py` 的 `MODEL_MAP` 增加：
```python
"dsv4p_nv": "deepseek_hm_nv",  # unify-nv: 三 agent 统一规范 model id
```
- HM1 hm40006 gateway 源码是 **build 进镜像**（非 bind-mount，与 HM2 工程化不同），
  因此本机改 host 源码不生效。本次用容器内 patch + restart 生效：
  - 备份：容器内 `/app/gateway/config.py.bak.unify_nv_20260630_184548`
  - host 源码 `/opt/cc-infra/proxy/hm-proxy/gateway/config.py` 也同步改了（镜像 rebuild 时用）
- **待办**：下次有网络时 `cd /opt/cc-infra && docker compose build hm40006` 把变更烧入镜像
  （本次 rebuild 因 ghcr.io TLS timeout 失败，基础镜像拉不下来）。rebuild 前容器内 patch
  已生效，不影响运行。

### 2. hermes `~/.hermes/config.yaml`（model + providers 段）
- `model.default`: deepseek_hm_nv → `dsv4p_nv`
- `model.provider`: litellm-nv-hm → `nv_cus`
- `providers` 顶层 key → `nv_cus`，api_key `nv-local`，default_model `dsv4p_nv`
- models key `deepseek_hm_nv` → `dsv4p_nv`，aliases 含 deepseek-v4-pro/deepseek/dsv4p/deepseek_hm_nv
- 备份：`~/.hermes/config.yaml.bak.unify_nv_20260630_184358`

### 3. opencode `~/.config/opencode/opencode.json`（清理 + 新配）
- 删除第三方 provider：`proxy40003`（glm5.1/40003）、`uni41001`（glm5.1/41001）
- 新增 `nv_cus` provider：baseURL 40006，apiKey nv-local
- model `dsv4p_nv`：family deepseek，reasoning true，interleaved.field `reasoning_content`
  （实测 deepseek-v4-pro 返回含 reasoning_content 字段，配置正确），context 131072
- 顶层 `model`: `nv_cus/dsv4p_nv`
- 备份：`~/.config/opencode/opencode.json.bak.unify_nv_20260630_184358`

### 4. openclaw `~/.openclaw/openclaw.json`（清理 + 新配）
- `agents.defaults.model.primary`: litellm/glm5.1_ol → `nv_cus/dsv4p_nv`
- `models.providers`: 删除 `litellm`（40003），新增 `nv_cus`（40006），api `openai-completions`
- `models.mode` 保持 `replace`（只留新 provider）
- 备份：`~/.openclaw/openclaw.json.bak.unify_nv_20260630_184358`
- openclaw gateway 为 systemd user 服务（openclaw-gateway），改配置后需重启 gateway 生效

## 实测结果（2026-06-30 18:47-18:49）

| 测试项 | 结果 |
|---|---|
| 7a curl 直测 dsv4p_nv | ✅ 200，content="pong"，含 reasoning_content/tool_calls 字段 |
| 7b hermes `-z "Reply: hermes-pong"` | ✅ 返回 hermes-pong，rr +1 |
| 7c opencode `run "Reply: opencode-pong"` | ✅ 返回 opencode-pong，`> build · dsv4p_nv` |
| 7d openclaw `agent -m "Reply: openclaw-pong"` | ✅ 返回 openclaw-pong |
| 7e N+1 跨请求连续 | ✅ key 序列 k2→k3→k4→k5→k1→k2→k3→k4，rr 严格递增 |
| 7f 重启续接 | ✅ docker restart 后 rr 不归零，从 1094 续接 |
| 7g 端到端流量 | ✅ hm40006 日志 22 条 `model=dsv4p_nv→deepseek_hm_nv`，三 agent 真实跑新链路 |

## 回滚
三处 `.bak.unify_nv_*` 备份保留，回滚 = cp 回原文件 + restart 对应服务：
- hermes: `cp ~/.hermes/config.yaml.bak.unify_nv_* ~/.hermes/config.yaml`
- opencode: `cp ~/.config/opencode/opencode.json.bak.unify_nv_* ~/.config/opencode/opencode.json`
- openclaw: `cp ~/.openclaw/openclaw.json.bak.unify_nv_* ~/.openclaw/openclaw.json` + 重启 gateway
- 容器 config.py: `docker exec hm40006 cp /app/gateway/config.py.bak.unify_nv_* /app/gateway/config.py && docker restart hm40006`

## 压力测试结果（2026-06-30 19:09-19:13）

30 条并发 curl（3 批 × 10）+ 期间 hermes cron 6 条 = 压测窗口 36 条。

| 指标 | 结果 |
|---|---|
| 成功率 | **100%**（36/36 全 200） |
| 错误 | 0（零 429 / 零 ATE / 零 timeout） |
| key 轮询均匀度 | k0=7/k1=7/k2=6/k3=9/k4=7，N+1 均匀环绕 ✅ |
| 压测请求 P50/P95 | 38s/——（deepseek reasoning + 串行锁 6s 排队，非错误） |
| agent 请求 P50 | 69s（hermes/oc/ol 长会话 stream） |
| 接入前 vs 接入后(今日) | before 99.48%/P50 7.3s → after 100%/P50 11.2s（+3.9s 抢锁，可接受） |

结论：三 agent 共享出口在 30 并发下零错误，hermes 主链路成功率未退化（仍 100%），
延迟因串行锁排队略升但可接受。零 429 证明 5 key 配额充足。

## 5 key 走向最终核实表（unify-nv 2026-06-30 实测）

| key | idx | proxy_url | 出口方式 | 出口IP | 路由 |
|---|---|---|---|---|---|
| k1 | 0 | 7894 | mihomo | 美国动态节点 | 海外冗余 |
| k2 | 1 | (空) | DIRECT | 本机直连(南京电信) | 直连 |
| k3 | 2 | 7896 | mihomo | 美国动态节点 | 海外冗余 |
| k4 | 3 | (空) | DIRECT | 本机直连 | 直连 |
| k5 | 4 | (空) | DIRECT | 本机直连 | 直连 |

mihomo 节点 IP 动态变化（曾 .193/.194，实测已变 .197/.193），不在注释固化。
compose 注释已规范化（去掉过时固定 IP，改为"实测见日志"）。

## 工程化对比：build 进镜像 vs bind-mount 源码（HM1 vs HM2）

| 维度 | HM1（build 进镜像） | HM2（bind-mount 源码） |
|---|---|---|
| compose volume | 仅挂 /app/logs | 额外挂 `./proxy/hm-proxy/gateway:/app/gateway` |
| 改 .py 后生效 | 需 `docker compose build && up -d`（rebuild 镜像） | 只需 `docker restart`（源码实时挂载） |
| 改动追踪 | 镜像层不可见，需 docker exec diff | 宿主机源码即真实，git diff 可见 |
| 网络依赖 | rebuild 需拉基础镜像（ghcr.io 易 TLS timeout） | 无网络依赖 |
| 一致性 | 镜像与 host 源码可能漂移（本次容器内 patch 未烧入镜像） | 宿主机=容器，零漂移 |
| 回滚 | 需 rebuild 旧镜像或 cp 容器内 bak | cp 宿主机 bak + restart |

**结论：HM2 的 bind-mount 方式工程化更优**——改源码只需 restart、零网络依赖、零漂移、
回滚快。HM1 当前 build 进镜像的方式每次改 .py 都要 rebuild（且本次因 ghcr.io 网络问题
rebuild 失败，只能容器内 patch 临时生效）。

## 第2阶段：HM1 补 bind-mount + 命名规范化（2026-06-30 20:00）

### bind-mount 落地（对齐 HM2）
compose hm40006 volumes 加一行：
```yaml
- ./proxy/hm-proxy/gateway:/app/gateway   # Layer1: 源码挂载, 改 .py 只需 restart
```
`docker compose up -d hm40006` 重建容器。验证 host==容器 config.py 零漂移。
以后改 .py 只需 `docker restart hm40006`，不再 rebuild。

### 命名规范化（全面改名 dsv4p_nv）
内部 model key `deepseek_hm_nv` → `dsv4p_nv`（反映通用语义，非 Hermes 专属）：

| 符号 | 旧 | 新 |
|---|---|---|
| 内部 model key | `deepseek_hm_nv` | `dsv4p_nv` |
| NV_MODEL_TIERS | `["deepseek_hm_nv"]` | `["dsv4p_nv"]` |
| DEFAULT_NV_MODEL | `deepseek_hm_nv` | `dsv4p_nv` |
| AGENT_SUFFIXES key | `_hm_nv` | `_nv` |
| AGENT_SUFFIXES name | `HermesNV` | `NVCus` |
| 函数 `_next_hm_nv_key` | (旧) | `_next_nv_key` |
| agent_type (DB) | `_hm_nv` | `_nv` |
| rr_counter.json key | `hm_nv_deepseek` | `nv_dsv4p` |

旧名 `deepseek_hm_nv` 在 MODEL_MAP 保留为 alias（向后兼容 hermes config 与 DB 历史查询）。
rr_counter.json 的 `hm_nv_deepseek` 由 `_OLD_RR_KEY_MAP` 自动迁移到 `nv_dsv4p`，值保留
（1415 不归零）。

### 实测结果（20:00-20:05）
- /health: `nvcf_pexec_models=["dsv4p_nv"]`, `hm_default_model=dsv4p_nv` ✅
- curl dsv4p_nv → 200；curl deepseek_hm_nv(alias) → 200 ✅
- 三 agent: hermes-pong / opencode-pong / openclaw-pong 全 200 ✅
- DB 新数据: mapped_model=dsv4p_nv, agent_type=_nv（重建容器后 20:02 起）✅
- N+1 跨 agent: key 序列 k3→k4→k5→k1→k2→k3 严格环绕 ✅
- 重启续接: rr 1422→1423 不归零 ✅
- rr_counter 迁移: hm_nv_deepseek→nv_dsv4p 值保留 ✅
- bind-mount 零漂移: host==容器 config.py ✅

### 改动文件清单
- `gateway/config.py` — model key/suffix/函数 re-export 全改名 + docstring
- `gateway/rr_counter.py` — _TIER_RR_KEYS/_OLD_RR_KEY_MAP/函数名 + 迁移映射
- `gateway/handlers.py` — agent_type/_hm_nv→_nv + 注释
- `gateway/upstream.py` — import/调用 _next_nv_key + 注释
- `gateway/pexec.py` / `error_mapping.py` / `__init__.py` / `gateway_main.py` — docstring
- `docker-compose.yml` — 加 bind-mount volume + 注释规范化（5 key 走向）
- 删除嵌套垃圾目录 `gateway/gateway/`（旧多模型版本，已备份到 deploy_artifacts/）
- 各 .py 有 `.bak.rename_20260630_195550` 备份；rr_counter.json.bak.rename_* 备份

### DB 历史数据连续性
mapped_model 历史是 `deepseek_hm_nv`（1376条），新是 `dsv4p_nv`。查询近期用新名，
跨历史用 OR 两名。db.py 不改，无 schema 变更。agent_type 同理 _hm_nv→_nv。

## 共享出口的固有代价（已知悉）
三 agent 与 hermes 主链路共用 hm40006 的 5 key + 进程内串行锁（MIN_OUTBOUND_INTERVAL_S）
+ key cooldown。并发时 opencode/openclaw 会与 hermes 抢锁/key 配额，可能拖累 hermes
延迟与成功率。压测显示 30 并发下 hermes 仍 100% 成功率，P50 +3.9s 可接受。
