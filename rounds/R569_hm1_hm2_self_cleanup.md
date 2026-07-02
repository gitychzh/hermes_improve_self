# R569 HM1+HM2 自改 — 框架冗余清理 + 定时任务全停

**轮次**: R569
**方向**: HM1+HM2 自改 (用户授权本次两机自改, 铁律"只改对端"暂停)
**角色**: CC 直接操作两机
**日期**: 2026-07-02

## 背景

用户要求整理两机框架冗余(源码冗余 + agent自身配置冗余),停掉所有定时任务,彻底清理干净。
明确授权: "两台设备都由你来做"。
本次不属于交替优化轮(交替优化机制本身在本轮停止)。

## 改动清单 (两机对等)

### 1. 定时任务全停 (只留开机自启)

**两机各:**
- `hermes_alt_optimize.timer`: disable + stop (was `OnCalendar=*:0/1` 每分钟, 交替优化引擎)
- `hermes_alt_optimize.service`: stop
- user crontab 清空, 只保留一条:
  ```
  @reboot sleep 15 && cd /opt/cc-infra && docker compose up -d >> /opt/cc-infra/logs/crontab.log 2>&1
  ```
- HM2 原无 @reboot, 补一条保持对等
- `/etc/cron.d/tailscale-monitor` 保留 (系统级)
- 停掉的 cron: nv_proxy_selector(死代码)/ts-keepalive/log_cleanup/check_429_alert/job51-scraper/openclaw .so清理/alt_optimize.sh(已注释)

**状态确认**: 两机 `systemctl is-active hermes_alt_optimize.timer` = inactive, `is-enabled` = disabled

### 2. HM1 crash loop 容器清理

HM1 有 4 个 `llm_glm51_4110x` 容器反复 Restarting (proxy_server.py SyntaxError: unterminated string literal line 24)。
- `docker stop + rm` 41101/41102/41103/41104/41105
- 从 `/opt/cc-infra/docker-compose.yml` 删除 R40 块 (5 个 llm_glm51_4110x 服务定义, 行 488-615, -128 行)
- `docker compose config --quiet` 校验 VALID
- 这些是早期 LiteLLM glm5.1 fallback 容器, hm40006 走 pexec 后早已不在热路径, hm40006 不 depends_on 它们

### 3. .bak 文件全删 (git 已有完整历史)

| 位置 | HM1 | HM2 |
|---|---|---|
| gateway/*.bak* | 60 | 62 |
| docker-compose.yml.bak* | 62 | 58 |
| **合计** | **122** | **120** |

两机 gateway 各保留 13 个 live .py, compose 保留 1 个 live docker-compose.yml。

### 4. 历史脚本目录 + 死代码删除

**HM1 删:**
- `~/cc_ps/cc_repair_cx` (904K)
- `~/cc_ps/cc_repair_opclaw` (4.0M)
- `~/cc_ps/cc_repair_self` (36M, sudo — 含 root 属主日志)
- `~/cc_ps/cc_repair_tai` (604K)
- `~/cc_ps/cc_repair_tail` (240K)
- `~/oc_ps/oc_repair_cc` (80K)
- **保留** `~/cc_ps/cc_repair_hm` (当前工作目录, 含 CLAUDE.md)

**两机删:**
- `/opt/cc-infra/scripts/nv_proxy_selector.py` + `.sh` (mihomo 已去, 死代码)
- `/opt/cc-infra/mihomo/` 配置目录 (mihomo 已去)

**HM2 删:** `~/cc_ps/cc_repair_self` (sudo)

### 5. 仓库 (hermes_improve_self) 清理

git rm + commit + push (3 commits: `3ebe54d`, `d6708b9`, `ba44853`):
- 删 16 个 `tmp_db_*.py` / `tmp_check_*.py` 临时调试脚本
- 删散落 `R46_*.patch` / `R46_*.md` / `R47_*` / `R50_*` / `R522_*` (rounds/ 保留完整历史)
- 删 `deploy_k1k2_direct.py` (早期部署脚本, 被 deploy_artifacts/ 取代)
- 删 `logs/prompt_*.txt` + `logs/run_turn_*.log` 历史 session 日志
- `.gitignore` 新增: `.run_my_turn.lock` / `__pycache__/` / `*.pyc` / `llm_requests.db` / `logs/prompt_*.txt` / `logs/run_turn_*.log` / `tmp_*.py`
- HM2 补提交 4 个未跟踪 round 文件 (R508/R513/R515/R568_hm2_optimize_hm1.md, `f25b916`)

**rounds/ 保留** (240 个 round 文件, 2.4M, 完整历史记录本体, 不动内容)

### 6. agent config 残留清理

**两机 openclaw.json:**
- `agents.defaults.models.alias` 文本 `8915fd28` → `74f02205` (name 字段已是 74f02205)
- 删 `openclaw.json.bak` / `.bak2` / `.last-good` (openclaw 内部旧快照, 含 deepseek-v4-pro/proxy40002 时代残留)

**两机 hermes config:**
- 删 `~/.hermes/config.yaml.bak.*` (4 个 HM1, 1 个 HM2)

### 7. agent 定义核对 (单一干净)

| agent | model | baseUrl | 状态 |
|---|---|---|---|
| openclaw | `nv_cus/dsv4p_nv` | `127.0.0.1:40006/v1` | ✅ 单一 |
| hermes | `kimi_nv` (provider nv_cus/litellm-nv-hm) | `127.0.0.1:40006/v1` | ✅ 单一 |
| opencode | `nv_cus/glm5_1_nv` | `127.0.0.1:40006/v1` | ✅ 单一 |

其它模型引用已彻底删除, fallback 仅跨机 (FALLBACK_GRAPH 默认空=不跨 model, HM_PEER_FALLBACK_ENABLED=1 两机互备)。

## 验证 (改后必有验证)

### hm40006 健康
- HM1: `{"status":"ok",...}` Up 11min (healthy), nvcf_pexec_models=["kimi_nv","dsv4p_nv","glm5_1_nv"]
- HM2: `{"status":"ok",...}` Up 49min (healthy), 同上
- HM1 crash loop 容器 (llm_glm51_4110x) 已消失, 容器列表干净

### 三模型思考模式 e2e (网关注入, 不带手动 thinking 字段)

| model | HM1 rc len | HM2 rc len | 状态 |
|---|---|---|---|
| kimi_nv | 1554 | 1401 | ✅ |
| dsv4p_nv | 381 | 566 | ✅ (74f02205 + thinking:{type:enabled}) |
| glm5_1_nv | 1583 | 1579 | ✅ |

dsv4p 思考已修复: config.py dsv4p inject = `{"thinking":{"type":"enabled"}}` (74f02205 ai-deepseek 实测触发字段, 非 reasoning_effort)。多候选 function_ids 已配 (dsv4p=[74f02205,8915fd28])。

### FALLBACK 范围
- `FALLBACK_GRAPH` = `{}` (空, 不跨 model fallback)
- `HM_PEER_FALLBACK_ENABLED=1` (仅跨机同 model fallback, HM1→HM2 / HM2→HM1)
- 符合用户要求: "fallback 也只是在两台设备(不同IP地址间fallback)"

## 数据 (改前必有数据)

- HM1 41101 crash 日志: `SyntaxError: unterminated string literal (detected at line 24)` × 多次 restart
- hm40006 不 depends_on llm_glm51_* (grep 确认)
- .bak 文件计数: HM1 122 / HM2 120 (git log 已含全部历史快照)
- gateway live .py: 13 个 (app/config/cooldown/db/error_mapping/func_health/handlers/__init__/logger/nvcf_conn/pexec/rr_counter/upstream)

## 总结

两机框架已整洁:
1. 定时任务: 只剩 @reboot 开机自启, 交替优化引擎停止
2. 源码: gateway 13 .py 无 .bak, compose 1 live 无 .bak
3. 脚本: 只留 cc_repair_hm (当前工作目录), 死代码 nv_proxy_selector/mihomo 删除
4. 仓库: tmp 调试脚本/散落 patch/历史 session 日志全清, .gitignore 防再生
5. agent config: openclaw=dsv4p/hermes=kimi/opencode=glm5.1 各自单一, 无 backup 残留, 无旧 model 引用
6. 容器: HM1 crash loop 清除, 两机容器列表干净
7. 三模型思考全通, fallback 仅跨机

## ⏳ 轮到HM2优化Hm1
