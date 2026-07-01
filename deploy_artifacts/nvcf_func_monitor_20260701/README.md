# NVCF function health monitor (2026-07-01)

## 为什么需要这个

NVCF (api.nvcf.nvidia.com) 的 pexec function 有生命周期: ACTIVE → DEGRADING →
DEGRADED → INACTIVE。dynamo-deepseek-v4-pro (ee2b0de2) 在 2026-07-01 已 INACTIVE
(404),之前导致 openclaw 全 502。这种下架是平台侧行为,我们改不了代码,只能**尽早
发现并切到替代 function**。

本脚本每 10 分钟跑一次,检查 hm40006 当前指向的 function 状态,异常时给出可切换的
替代候选并实测它们是否支持 reasoning_content (思考链)。

## 文件

- `nvcf_func_monitor.py` — 监控脚本
- `nvcf_func_monitor.service` — systemd oneshot service (system-level)
- `nvcf_func_monitor.timer` — 每 10 分钟触发

## 部署 (HM1)

```bash
# 脚本已在 scripts/nvcf_func_monitor.py, systemd unit 已装在 /etc/systemd/system/
sudo systemctl enable --now nvcf_func_monitor.timer
systemctl list-timers nvcf_func_monitor.timer
# 日志: logs/nvcf_func_monitor.log
```

## 退出码 (供 alert/告警用)

- 0 = ACTIVE,正常
- 1 = DEGRADING (即将下架,告警但还能用)
- 2 = INACTIVE/DEGRADED/MISSING (必须切换) 或无可用替代
- 3 = 脚本本身异常 (容器/网络问题)

## 关键发现 (写代码踩过的坑)

**ncaId 不能作筛选器**。NVCF 平台级共享部署 (ownedByDifferentAccount=true) 的所有
function 共享同一 ncaId — 包括不相关的 ai-riva/ai-gemma/ai-mistral 等。169 个 function
里 144 个共享同一 ncaId。早期版本用 "同 ncaId 优先" 当筛选器,结果 INACTIVE 时返回
145 个候选 (基本是全部 ACTIVE),探针去测 ai-riva-translate 全失败。

正确筛选靠 **name 前缀** (WATCH_PREFIXES = deepseek-v4 / kimi),引擎区分靠前缀第一段
(dynamo/orion/sglang/nvquery-kimi/ai-kimi/ai-deepseek)。修正后候选只有 4 个。

## 当前 watched ACTIVE 候选 (2026-07-01)

| name | id | model 字段 | 思考链 |
|---|---|---|---|
| nvquery-kimi-k2_6 | f966661c | moonshotai/kimi-k2.6 | ✅ (当前在用) |
| ai-deepseek-v4-pro | 74f02205 | deepseek-ai/deepseek-v4-pro | ✅ |
| sglang-deepseek-v4-pro | 8915fd28 | deepseek-ai/deepseek-v4-pro | ✅ |
| ai-kimi-k2_6 | 23d4f03a | moonshotai/kimi-k2.6 | ✅ |

切换 = 改 docker-compose.yml 的 `NVCF_DEEPSEEK_FUNCTION_ID` + gateway/config.py 的
`NV_MODEL_IDS['dsv4p_nv']` model 字段,然后 `docker compose up -d hm40006`。
