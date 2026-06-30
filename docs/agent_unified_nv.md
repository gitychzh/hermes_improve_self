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

## 共享出口的固有代价（已知悉）
三 agent 与 hermes 主链路共用 hm40006 的 5 key + 进程内串行锁（MIN_OUTBOUND_INTERVAL_S）
+ key cooldown。并发时 opencode/openclaw 会与 hermes 抢锁/key 配额，可能拖累 hermes
延迟与成功率。本次仅做配置统一与可用性验证，未做并发压力下的 hermes 回归对比
（建议后续补 30min 窗口 hermes 成功率/延迟对比 [[stageB-snapshot-2026-06-29]] 基线）。
