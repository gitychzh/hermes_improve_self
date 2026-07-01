# HM2 hm40006 三模型对齐 Phase 1a (2026-07-01)

HM1→HM2 同步, 让 HM2 摆脱单 glm5.1_hm_nv 坍缩态, 对齐 HM1 三模型 pass-through + 思考 + F-fix.

## Phase 1a (HM1 做, hm40006 源码+env)

### 源码 (rsync 整目录, 12 .py IDENTICAL)
HM1 /opt/cc-infra/proxy/hm-proxy/gateway → HM2 同路径.
新增模块: cooldown.py/nvcf_conn.py/pexec.py/rr_counter.py (HM2 R310 模块化未同步, 之前缺).
backup: HM2 *.bak.p1sync_20260701_195020

### env (HM2 compose)
新增: NVCF_KIMI/DEEPSEEK_FUNCTION_ID, NVCF_BASE_URL, HM_FORCE_STREAM_UPGRADE=1/+TIMEOUT=55
改值: HM_DEFAULT_NV_MODEL→dsv4p_nv, HM_NV_MODEL_TIERS→三模型, HM_MIN_ATTEMPT_TIMEOUT_S=8→5
删死env: HM_SSLEOF_RETRY_ENABLED (代码不读)
保留差异(cc2裁决 A/B): UPSTREAM_TIMEOUT=48(HM1=25)/TIER_BUDGET=110(80)/KEY_COOLDOWN=38(25)/FASTBREAK=3(2)/路由URL1-5
backup: docker-compose.yml.bak.p1env_*

## Phase 1b (cc2 做, agent config 改+自审)
hermes→kimi_nv, openclaw→dsv4p_nv(删5旧别名), opencode→glm5_1_nv(灰度40006 default+40003 fallback观察24h)
model 名用 glm5_1_nv (下划线), apiKey=nv-local.

## 验证 (Phase 1a)
/health 三模型 ✓, F-fix 3处 ✓, inject dict 5处 ✓, 端到端思考 kimi rc846/dsv4p rc335/glm5.1 rc1495 全★.

## cc2 三轮仲裁要点
- 只对齐代码不对齐 timeout/路由 (HM2 慢链路调出来的值保留 A/B 价值)
- Phase 2 跨机 fallback 降级为探针+手动切 (零循环风险零自改), 不做自动 fallback
- opencode 40003 灰度迁移 (auth_to_api_40003 活但近1h无热流量)
- 审视分工: HM1 同步 hm40006 源码+env (机械操作), cc2 改 agent config 自审 (路由决策分离)

## snapshot
hm2_docker-compose.yml.snapshot = Phase 1a 改完后 HM2 compose 全量 (供参考, 非live).
