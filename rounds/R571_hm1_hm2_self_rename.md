# R571 HM1+HM2 自改 — 全层重命名 hm40006→nv_40006_uni

**轮次**: R571
**方向**: HM1+HM2 自改 (用户授权本次两机自改, 铁律"只改对端"暂停)
**角色**: CC 直接操作两机
**日期**: 2026-07-02

## 背景

用户要求: "把容器名称也改了, 应该叫 nv_40006_uni。它以前是只供 hermes 使用的, 所以用 hm 开头,
现在是供多个 agent (hermes/openclaw/opencode) 用。你再检查一下框架有没有名称与功能不匹配的,
一起改过来。"

经 AskUserQuestion 确认两点:
1. **全层重命名** — 容器/服务/目录/镜像/env 前缀/health 字段/DB 表/脚本/注释全改, 不只改容器名。
2. **迁移历史数据** — 目录改名 + DB 表 ALTER TABLE RENAME (保留历���行, 不重建)。

本次属架构级改动, 用户已去掉"每轮少改"铁律 (见 memory `rule-change-no-single-param-2026-07-02`),
授权架构级一次性改动。其余铁律 (改前数据/改后验证/聚焦 hm-40006--nv/写入仓库) 不变。

## 命名映射表

| 层 | 旧 | 新 |
|---|---|---|
| 容器名 / compose service | `hm40006` | `nv_40006_uni` |
| 镜像名 | `cc-infra-hm40006` | `cc-infra-nv_40006_uni` |
| 源码目录 | `proxy/hm-proxy` | `proxy/nv-uni` |
| 日志目录 | `logs/proxy40006` | `logs/nv_40006_uni` |
| 日志文件前缀 | `hm_proxy.*` / `hm_metrics.*` / `hm_error_detail.*` | `nv_proxy.*` / `nv_metrics.*` / `nv_error_detail.*` |
| env 前缀 | `HM_NV_KEY*`, `HM_NV_PROXY_URL*`, `HM_HOST_MACHINE`, `HM_GATEWAY_API_KEY`, `HM_PEER_FALLBACK_*`, `HM_FORCE_STREAM_UPGRADE*`, `HM_PEXEC_TIMEOUT_FASTBREAK`, `HM_EMPTY_200_FASTBREAK`, `HM_EMPTY200_SLOW_THRESHOLD_S`, `HM_CONNECT_RESERVE_S`, `HM_SSLEOF_RETRY_DELAY_S`, `HM_MIN_ATTEMPT_TIMEOUT_S`, `HM_DB_*`, `HM_NUM_KEYS` | `NVU_KEY*`, `NVU_PROXY_URL*`, `NVU_HOST_MACHINE`, `NVU_GATEWAY_API_KEY`, `NVU_PEER_FALLBACK_*`, `NVU_FORCE_STREAM_UPGRADE*`, `NVU_PEXEC_TIMEOUT_FASTBREAK`, `NVU_EMPTY_200_FASTBREAK`, `NVU_EMPTY200_SLOW_THRESHOLD_S`, `NVU_CONNECT_RESERVE_S`, `NVU_SSLEOF_RETRY_DELAY_S`, `NVU_MIN_ATTEMPT_TIMEOUT_S`, `NVU_DB_*`, `NVU_NUM_KEYS` |
| DB 表 | `hm_requests`, `hm_tier_attempts` | `nv_requests`, `nv_tier_attempts` |
| DB 索引 | `idx_hm_*` | `idx_nv_*` |
| health 输出字段 | `hm_num_keys`, `hm_model_tiers`, `hm_default_model` | `nv_num_keys`, `nv_model_tiers`, `nv_default_model` |
| 日志 tag | `[HM-PROXY]`, `[HM-RR]`, `[HM-CONFIG]`, `[HM-KEY]`, `[HM-SUCCESS]`, ... (24 种) | `[NV-PROXY]`, `[NV-RR]`, `[NV-CONFIG]`, `[NV-KEY]`, `[NV-SUCCESS]`, ... |
| rr_counter 内部 key | `hm_nv_deepseek`, `hm_nv_kimi`, `hm_nv_glm5.1` (旧格式残留) | 迁移到 `nv_dsv4p`, `nv_kimi`, `nv_glm5_1` (经 `_OLD_RR_KEY_MAP`) |
| 脚本 `docker exec` | `docker exec hm40006` | `docker exec nv_40006_uni` |
| agent config 注释 | "via hm40006", "HM NV Gateway 40006" | "via nv_40006_uni", "NV-Uni Gateway 40006" |

**env 前缀选 `NVU_` (NV-Uni) 而非 `NV_`**: 避免与现有常量 `NV_MODEL_TIERS` / `NV_MODEL_IDS` / `DEFAULT_NV_MODEL` / `NVCF_PEXEC_MODELS` 冲突。`NVU_` 是新命名空间, 无冲突。

## 改动清单 (两机对等)

### A. 源码 (`/opt/cc-infra/proxy/nv-uni/gateway/`, bind-mount 到 `/app/gateway`)

13 个 .py 全部更新 (两机对等):
- `config.py`: HM_NV_KEYS→NVU_KEYS, HM_NUM_KEYS→NVU_NUM_KEYS, HM_NV_PROXY_URLS→NVU_PROXY_URLS,
  HM_GATEWAY_API_KEY→NVU_GATEWAY_API_KEY, HM_FORCE_STREAM_UPGRADE*→NVU_FORCE_STREAM_UPGRADE*,
  HM_PEER_FALLBACK_*→NVU_PEER_FALLBACK_*; env 读取 HM_NV_KEY{i}→NVU_KEY{i}, HM_NV_PROXY_URL{i}→NVU_PROXY_URL{i};
  docstring hm40006→nv_40006_uni, hm-proxy→nv-uni。NVCF_PEXEC_MODELS 结构不变 (function_ids + per-model inject 来自 R568)。
- `db.py`: HM_DB_*→NVU_DB_*, HM_HOST_MACHINE→NVU_HOST_MACHINE; SQL INSERT INTO hm_requests→nv_requests,
  hm_tier_attempts→nv_tier_attempts; docstring 更新。
- `handlers.py`: health 输出 hm_num_keys→nv_num_keys, hm_model_tiers→nv_model_tiers, hm_default_model→nv_default_model;
  import 常量重命名; 全部 `_log("HM-...")` → `_log("NV-...")`。
- `upstream.py`: HM_PEXEC_TIMEOUT_FASTBREAK→NVU_PEXEC_TIMEOUT_FASTBREAK, HM_EMPTY_200_FASTBREAK→NVU_EMPTY_200_FASTBREAK,
  HM_EMPTY200_SLOW_THRESHOLD_S→NVU_EMPTY200_SLOW_THRESHOLD_S, HM_CONNECT_RESERVE_S→NVU_CONNECT_RESERVE_S,
  HM_SSLEOF_RETRY_DELAY_S→NVU_SSLEOF_RETRY_DELAY_S, HM_MIN_ATTEMPT_TIMEOUT_S→NVU_MIN_ATTEMPT_TIMEOUT_S;
  全部 _log tag HM-→NV-。
- `rr_counter.py` (★关键): 含 `_OLD_RR_KEY_MAP` 向后兼容映射:
  ```python
  _OLD_RR_KEY_MAP = {
      "nv_deepseek": "nv_dsv4p",
      "hm_nv_deepseek": "nv_dsv4p",   # unify-nv 前的旧 key
      "nv_dsv4p": "nv_dsv4p",
      "nv_kimi": "nv_kimi",
      "hm_nv_kimi": "nv_kimi",
      "hm_nv_glm5.1": "nv_glm5_1",    # rename 前的旧 key, 迁移到 nv_glm5_1
      "nv_glm5_1": "nv_glm5_1",
  }
  ```
  `_load_rr_counter()` 启动时迁移旧 key 并保存。print tag [HM-RR]→[NV-RR]; 日志文件 hm_proxy.{date}.log→nv_proxy.{date}.log。
- `logger.py`: 日志文件名 hm_proxy.*→nv_proxy.*, hm_metrics.*→nv_metrics.*, hm_error_detail.*→nv_error_detail.*。
- `app.py`: banner [HM-PROXY]→[NV-PROXY], import NVU_NUM_KEYS。
- `__init__.py`, `func_health.py`, `pexec.py`, `error_mapping.py`, `nvcf_conn.py`: docstring + log tag 更新。
- `Dockerfile` + `gateway_main.py`: docstring "Hermes专用"→"三 agent 通用 (NV-unified)"。
  HM2 的 gateway_main.py 用 rsync 覆盖为 HM1 canonical 版本 (两机对齐)。

### B. compose / .env

- `docker-compose.yml` (两机): service key `hm40006:`→`nv_40006_uni:`; container_name 同;
  build.context `./proxy/hm-proxy`→`./proxy/nv-uni`; volumes `./proxy/hm-proxy/gateway`→`./proxy/nv-uni/gateway`,
  `./logs/proxy40006`→`./logs/nv_40006_uni`; 全部 HM_ env key → NVU_ (含 HM_NV_KEY1-5→NVU_KEY1-5,
  HM_NV_PROXY_URL1-5→NVU_PROXY_URL1-5); HM_PEER_FALLBACK_URL 方向保留 (HM1→100.109.57.26, HM2→100.109.153.83)。
  备份: `docker-compose.yml.bak.rename_20260702`。
- `.env` (两机): HM_HOST_MACHINE→NVU_HOST_MACHINE (HM1=opc_uname, HM2=opc2sname);
  HM2 另 HM_NV_KEY1-5→NVU_KEY1-5。备份: `.env.bak.rename_20260702`。

### C. DB (cc_postgres / hermes_logs)

容器停止状态下执行 (避免 rename 期间写入):
```sql
ALTER TABLE hm_requests RENAME TO nv_requests;
ALTER TABLE hm_tier_attempts RENAME TO nv_tier_attempts;
-- 索引随表改名但保留旧名, 单独 rename 索引
ALTER INDEX idx_hm_requests_start_time RENAME TO idx_nv_requests_start_time;
ALTER INDEX idx_hm_tier_attempts_ts RENAME TO idx_nv_tier_attempts_ts;
```
`hermes-logs-schema.sql` 同步更新 (hm_requests→nv_requests, idx_hm_*→idx_nv_*), 备份 .bak.rename_20260702。
两机对等执行, 行数保留 (HM1 nv_requests≈历史行数, HM2 同)。

### D. 日志目录

`/opt/cc-infra/logs/proxy40006` → `/opt/cc-infra/logs/nv_40006_uni` (mv, 保留历史 JSONL + sqlite db)。
容器重启后写新文件名 (nv_proxy.* / nv_metrics.* / nv_error_detail.*)。

### E. 脚本 (仓库内)

- `scripts/nvcf_func_monitor.py` (两机): `docker exec hm40006`→`docker exec nv_40006_uni`,
  函数 `get_hm40006_env`→`get_nv_env`。
- `scripts/run_my_turn.sh` (两机): 注释 hm40006→nv_40006_uni。
- `~/bin/openclaw-stall-watcher.sh` (HM1, 不在仓库): 注释 hm40006→nv_40006_uni。

### F. agent config (两机)

- `~/.openclaw/openclaw.json`: 注释 "via hm40006"→"via nv_40006_uni", "HM NV Gateway 40006"→"NV-Uni Gateway 40006"。
- `~/.hermes/config.yaml`: 同上注释更新。
- `~/.config/opencode/opencode.jsonc`: 同上注释更新。
- HM2 `~/.hermes/config.yaml`: **删除 model_aliases.glm5_1_nv 块** (用户要求 hermes kimi-only, 消除旧 model 残留)。

### G. 旧镜像清理

两机 `docker image rm cc-infra-hm40006:latest configs-hm40006:latest` (已被新镜像取代, 无容器引用)。
两机现仅剩 `cc-infra-nv_40006_uni:latest`。

## 数据 (改前)

- 改前两机 `docker ps` 显示容器名 `hm40006`, image `cc-infra-hm40006:latest`, 源码目录 `proxy/hm-proxy`, 日志 `logs/proxy40006`。
- 改前 DB 表名 `hm_requests` / `hm_tier_attempts` (查询确认存在, 行数 HM1≈10万级 / HM2 同量级)。
- 改前 env 前缀 `HM_NV_KEY*` 等 (docker exec env 确认)。
- 改前 health 输出 `hm_num_keys` / `hm_model_tiers` / `hm_default_model` 字段。
- 改前 rr_counter HM2 残留 `hm_nv_glm5.1: 8210` 旧 key (rename 前 format)。

## 预期效果

1. 容器/服务/镜像/目录/env/DB/日志/health 字段/脚本/注释 全部统一为 nv_40006_uni / NVU_ 命名空间, 与"三 agent 通用"功能匹配。
2. 旧 hm_* 残留清零, 消除"名称是 hm 但实际服务多 agent"的误导。
3. 历史数据 (DB 行 / 日志 JSONL / rr_counter 计数) 全部迁移保留, 无数据丢失 (除 HM2 rr_counter hm_nv_glm5.1 8210 计数, 见下文已知问题)。
4. 三 agent (hermes/openclaw/opencode) 经 nv_40006_uni 正常出网, 三模型思考全通。

## 已知问题

- **HM2 rr_counter `hm_nv_glm5.1: 8210` 计数丢失**: 第一次重启时 `_OLD_RR_KEY_MAP` 还没加 `hm_nv_glm5.1` 映射,
  该 key 在保存周期中被丢弃 (一次 glm5.1 请求把 nv_glm5_1 45→46 并保存, 旧 key 未迁移就丢了)。
  后续补加映射并重启, 但 8210 已不可恢复。**影响**: 无功能影响, rr_counter 仅决定轮询起点 (counter % 5),
  46 和 8255 取模后都是同一起点区间。HM1 nv_glm5_1=68, HM2=46, 两机均合法小值。
  **教训**: 改迁移映射前应先备份 rr_counter.json。

## 验证 (改后)

### V1. 容器/镜像/目录
- 两机 `docker ps` 显示 `nv_40006_uni` healthy, image `cc-infra-nv_40006_uni:latest`。
- 两机 `ls /opt/cc-infra/proxy/nv-uni/gateway/` = 13 .py 无 .bak。
- 两机 `ls /opt/cc-infra/logs/nv_40006_uni/` 含历史 JSONL + 新 nv_proxy.* 文件。

### V2. env / health
- 两机 `docker exec nv_40006_uni env | grep -E 'NVU_|HM_'` 全 NVU_, 零 HM_。
- 两机 `curl localhost:40006/health` 输出 `nv_num_keys`, `nv_model_tiers`, `nv_default_model` 字段。

### V3. DB
- 两机 `psql -c '\dt'` 显示 nv_requests, nv_tier_attempts (无 hm_*)。
- `select count(*) from nv_requests` = 改前 hm_requests 行数 (迁移保留)。
- 新请求写入 nv_requests (发一条测试请求后 count+1)。

### V4. 三模型思考 (两机各)
- hermes (kimi_nv): 请求带 reasoning_effort=low, 响应有 reasoning_content 非空。
- openclaw (dsv4p_nv): 请求带 thinking:{type:enabled}, 响应有 reasoning_content 非空。
- opencode (glm5_1_nv): 请求带 chat_template_kwargs.enable_thinking=true, 响应有 reasoning_content 非空。

### V5. rr_counter
- 两机 `cat .../rr_counter.json` 显示 nv_dsv4p / nv_kimi / nv_glm5_1 key, 无 hm_nv_* 残留。
- 日志 [NV-RR] tag。

### V6. peer fallback 方向
- HM1 env NVU_PEER_FALLBACK_URL 指向 HM2 (100.109.57.26); HM2 指向 HM1 (100.109.153.83)。方向不变。

### V7. 脚本
- `scripts/nvcf_func_monitor.py` 用 `docker exec nv_40006_uni`, 两机同步。

### V8. 旧残留扫描
- `grep -rE 'hm40006|hm-proxy|HM_NV_KEY|hm_requests|hm_tier_attempts|hm_num_keys' /opt/cc-infra/proxy/nv-uni/gateway/ /opt/cc-infra/docker-compose.yml /opt/cc-infra/.env` → 零命中。

## ⏳ 轮到HM2优化Hm1
