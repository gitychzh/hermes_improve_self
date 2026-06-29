# 工程化改造：HM2 hm40006 源码挂载化 + secret 抽离

日期：2026-06-29
执行者：HM1（opc_uname）对 HM2 操作
性质：工程化维护（非参数调优轮次，不翻转交替优化标记）

## 背景与诊断

用户指出"config.py 构建时 COPY 进镜像，改一行源码就得 rebuild+翻墙拉 ghcr 镜像，
升级/迁移不方便"，要求从工程化角度重构两机 hermes 模型链路配置。

诊断 `/opt/cc-infra`（HM2）真实结构后确认痛点：
1. **源码烧进镜像**：Dockerfile `COPY gateway/` → 改任何 .py 都要 `docker compose build`，
   而 build 要拉 `ghcr.io/berriai/litellm:v1.83.14-stable.patch.1` 基础镜像 → 被墙 →
   必须挂 HM2 本地 mihomo 代理（docker0 网关 172.17.0.1:7892）才能 build。
   一次源码微调变成"网络+构建"双重依赖。
2. **`/opt/cc-infra` 非 git 仓库**：源码/compose/secret 全在裸目录，靠人工 `*.bak.R*`
   备份（30+ compose bak、4 源码 bak），无 diff/回滚语义。
3. **secret 明文散落**：5 个 HM_NV_KEY 明文写在 docker-compose.yml，跟着 bak 到处复制。
4. **deploy 脚本 `docker exec cp` 进容器打补丁**：运行态与源码态漂移，重建后补丁丢失。

## 用户决策（本轮范围）

- 工程化做到 **Layer1+3**（不做 Layer2 git 化，不做 Layer4 换基础镜像）。
- **只改 HM2**（铁律：只改对端，不改自己）。HM1 不动。
- Layer2 如未来做，**只本地 git init，不 push 任何 remote**（防 key 泄露）。

## 改造内容（仅 HM2 `/opt/cc-infra`）

### Layer1 — gateway 源码从"构建时 COPY"改"运行时 volume 挂载"

`docker-compose.yml` hm40006 块 volumes 增加：
```yaml
    volumes:
      - ./proxy/hm-proxy/gateway:/app/gateway   # Layer1: 源码挂载, 改 .py 只需 restart 不再 rebuild
      - ./logs/proxy40006:/app/logs
      - /etc/localtime:/etc/localtime:ro
```
Dockerfile 里的 `COPY gateway/` 保留作为镜像自带 fallback（挂载运行时覆盖它）。
效果：改 config.py/upstream.py 等 → `docker compose restart hm40006`（秒级）即生效，
**不再 build、不再依赖 ghcr 拉镜像**。

### Layer3 — hm40006 的 5 个 NV key 抽到 `.env`

`/opt/cc-infra/.env` 追加（已有的 POSTGRES_PASSWORD/HM_HOST_MACHINE 不动）：
```ini
HM_NV_KEY1=nvapi-...
HM_NV_KEY2=nvapi-...
HM_NV_KEY3=nvapi-...
HM_NV_KEY4=nvapi-...
HM_NV_KEY5=nvapi-...
```
compose hm40006 块改为引用：
```yaml
      HM_NV_KEY1: ${HM_NV_KEY1}   # Layer3: key 抽到 .env, 不再明文进 bak
      ...
```
效果：以后 compose 的 bak 不再携带明文 key；key 集中在 `.env`（权限 664，owner opc2_uname）。

### 范围边界（铁律第4条：聚焦 hm-40006--nv）

- **只抽 hm40006 的 HM_NV_KEY1-5**。ms_uni41001/41002 等 fallback 容器的 NV_KEY1-5
  （compose 行 232/287-291/426-427）**保持明文不动**——它们属于 40000/40001 等别的链路，
  铁律禁止碰。
- 调参（UPSTREAM_TIMEOUT 等）本轮**未抽**到独立 env 文件，仍留在 compose（轮次调参
  习惯于在 compose 注释里带 R 号历史，强行抽离反而打散追踪链）。未来可再分离。

## 部署与验证（改前备份 + 改后端到端验证）

- 备份：`docker-compose.yml.bak.20260629-183004`、`.env.bak.20260629-183004`（HM2 原地）。
- `docker compose up -d hm40006`（compose 变更触发 recreate，无需 build）。
- Layer1 验证：宿主机 `echo "# MARK" >> gateway/config.py` → 容器内 `tail` 立即可见，
  无需 restart（挂载实时）。Python 进程重载只需 `restart`。✅
- Layer3 验证：`docker exec hm40006 env | grep HM_NV_KEY1` → 值正确来自 .env。✅
- 链路验证：`POST /v1/chat/completions` model=glm5.1_hm_nv → 200，返回 z-ai/glm-5.1。✅
- health：5 keys、`nvcf_pexec_models=["glm5.1_hm_nv"]`、`hm_default_model="glm5.1_hm_nv"`。✅

## 未做（明确留待后续）

| 层 | 内容 | 未做原因 |
|---|---|---|
| Layer2 | /opt/cc-infra git 化，commit 替代 bak.R* | 用户选"只本地不入库"；需先定 remote 私密性。留待后续决策。 |
| Layer4 | 基础镜像 ghcr litellm → python:3.11-slim | 改动大，需重验依赖；Layer1 落地后 build 已不再是高频操作，迫切性下降。 |
| 调参分离 | UPSTREAM_TIMEOUT 等抽独立 hm40006.env | 与轮次注释追踪习惯耦合，暂留 compose。 |

## 改造后 hm40006 维护姿势对照

| 操作 | 改造前 | 改造后 |
|---|---|---|
| 改 gateway/*.py 源码 | rebuild（翻墙拉 ghcr）+ up -d | `docker compose restart hm40006` |
| 改 compose 调参 | up -d（recreate） | 不变 |
| 改 NV key | 改 compose（key 进 bak） | 改 `.env` + `up -d`（key 不进 compose bak） |
| 回滚源码 | 找 .bak.R* 手工覆盖 | git（待 Layer2）/ .bak.R*（现状） |

> 注：本改造不翻转交替优化标记，下一轮仍按 RN 既有约定继续。
