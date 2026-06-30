#!/bin/bash
# ============================================================
# 交替优化执行器 (R314, 两机共用)
# 被 watch_and_next.sh 在检测到"轮到我"后调用, 或由service链式触发
# 作用: 在本机启动一个 claude CLI 非交互session, 自主完成对端优化
# 铁律: 只改对端不改自己 (本机session改对端, 天然满足)
# ============================================================

REPO_DIR="$HOME/hm_ps/hermes_improve_self"
TRIGGER_FILE="$REPO_DIR/.my_turn_trigger"
LOG_DIR="$REPO_DIR/logs"
mkdir -p "$LOG_DIR"
TS=$(date '+%Y%m%d_%H%M%S')
RUN_LOG="$LOG_DIR/run_turn_${TS}.log"

cd "$REPO_DIR" || exit 1

# ============================================================
# 互斥锁 (R317fix): 防止同host并发起多个claude session撞号
# 根因: systemd oneshot service 1min一跳, 若上一跳的claude session
# 还在跑(或被kill后成孤儿), 下一跳可能再起一个session, 两session
# 几乎同时commit同R号 → 同号双发(R314/R315/R316均因此).
# flock非阻塞锁: 同host已有session在跑→立即退出, 不撞号.
# ============================================================
MUTEX_LOCK="$REPO_DIR/.run_my_turn.lock"
exec 9>"$MUTEX_LOCK"
if ! flock -n 9; then
    echo "[$TS] 已有run_my_turn在跑(互斥锁占用), 跳过本次避免撞号" >> "$RUN_LOG"
    exit 0
fi
# 起session前收割本机残留claude孤儿进程(上一跳被kill后可能残留)
ORPHAN_PIDS=$(pgrep -f "claude -p.*优化工程师" 2>/dev/null | grep -v "^$$\$")
if [ -n "$ORPHAN_PIDS" ]; then
    echo "[$TS] 收割残留claude孤儿进程: $ORPHAN_PIDS" >> "$RUN_LOG"
    kill -9 $ORPHAN_PIDS 2>/dev/null
    sleep 1
fi

# 读trigger
if [ ! -f "$TRIGGER_FILE" ]; then
    echo "[$TS] 无trigger文件, 退出" >> "$RUN_LOG"
    exit 0
fi
source "$TRIGGER_FILE" 2>/dev/null
ROLE="${role:-UNKNOWN}"
ROUND_FILE="${round_file:-}"
ROUND_NAME="${round:-}"
COMMIT="${commit:-}"

if [ "$ROLE" = "HM1" ]; then
    PEER="HM2"; PEER_USER="opc2_uname"; PEER_IP="100.109.57.26"
    MY_GIT_USER="opc_uname"
    NEXT_MARKER="## ⏳ 轮到HM2优化HM1"
    MY_MODEL="deepseek_hm_nv"
    PEER_MODEL="glm5.1_hm_nv"
elif [ "$ROLE" = "HM2" ]; then
    PEER="HM1"; PEER_USER="opc_uname"; PEER_IP="100.109.153.83"
    MY_GIT_USER="opc2_uname"
    NEXT_MARKER="## ⏳ 轮到HM1优化HM2"
    MY_MODEL="glm5.1_hm_nv"
    PEER_MODEL="deepseek_hm_nv"
else
    echo "[$TS] 未知role=$ROLE, 退出" >> "$RUN_LOG"
    exit 1
fi

# 下一个round编号: 找最大R号+1
NEXT_R=$(( $(ls "$REPO_DIR/rounds"/R*_*.md 2>/dev/null | grep -oP 'R\K[0-9]+' | sort -n | tail -1) + 1 ))
NEXT_ROUND_FILE="rounds/R${NEXT_R}_${ROLE,,}_optimize_${PEER,,}.md"

cat > "$LOG_DIR/prompt_${TS}.txt" <<PROMPT
你是 ${ROLE} 的优化工程师, 在双机交替优化中本轮担任执行者。CC(总指挥)已确认轮到你。

## 铁律(最高优先级,违反即失败)
1. 只改对端(${PEER}), 不改自己(${ROLE})。本session跑在${ROLE}上, 通过 ssh -p 222 ${PEER_USER}@${PEER_IP} 改对端。
2. 改前必有数据: 从对端hermes_logs DB/错误JSONL取30min窗口数据, 禁止猜测。对端DB: ssh ... 'docker exec cc_postgres psql -U litellm -d hermes_logs -c "SQL"' (host_machine字段: HM1='opc*'/HM1主机名, HM2='opc2sname')。表hm_requests(status,error_type,duration_ms,ts,nv_key_idx,key_cycle_details), hm_tier_attempts(error_type,elapsed_ms,nv_key_idx)。
3. 改后必有验证: 实质数据流向, 非表面。改源码要docker compose重启/rebuild后, curl /health + docker exec env + 实测请求确认新配置生效(不是旧配置)。
4. 聚焦 hm-40006--nv 链路。${ROLE}后端模型=${MY_MODEL}(不能改), ${PEER}后端=${PEER_MODEL}(不能改)。
5. 每轮少改: 单参数或单逻辑点, 积累多轮。
6. 所有修改写入仓库: 改完写round文件+commit+push, 翻转标记。
7. 网络问题用对端mihomo代理(socks5://127.0.0.1:9090或http端口7894-7899)。

## 上一轮上下文
最新round文件: ${ROUND_NAME} (commit ${COMMIT})
请先读 $REPO_DIR/rounds/${ROUND_NAME} 和最近3个round文件了解历史。
git log --oneline -10 看近期变更。

## 本轮任务
1. 拉取最新: cd $REPO_DIR && git pull --ff-only origin main
2. 读最新round文件, 理解上轮做了什么、留下了什么待办/反对者建议
3. 采集对端30min数据(成功率/错误结构/per-key/延迟P50/P95/empty_200/timeout分布)
4. **CC定向指令(必读)**: 本轮不再"自己找改动点", 改为执行下列CC已勘定的定向改动清单。优先执行清单第1项, 若第1项本轮无法实施(如已被前轮做过/数据不支撑), 顺延下一项。每轮只做1项, A/B验证后翻轮。
5. 在对端实施改动(备份→改→重启/rebuild→验证实质数据流向)
6. 采集改后数据(短窗口对比, 至少15min或20req, 对比改前同窗口)
7. 写round文件 $NEXT_ROUND_FILE (summary/参数表/改前数据/改动/预期/验证/结论), 末尾必须是 $NEXT_MARKER
8. git add + commit + push origin main
9. 翻轮完成

## CC定向改动清单(对端${PEER}的已勘定问题, 按优先级)
CC(总指挥)已基于对端60min实测数据勘定下列改动点, 每项都有数据支撑, 非猜测。本轮选第1个未完成的执行:

### 若对端是HM1(deepseek, ${PEER}==HM1时本节生效)
- **[HM1-A] MIN_OUTBOUND_INTERVAL_S 18.2→9.0** (最高优先): 实测HM1吞吐=3.3req/min=200req/h, 被18.2s全局throttle锁死(是HM2的4.5s的4倍). 降到9.0→吞吐翻倍. 风险: k2/k4 direct可能429. A/B: 对比改前改后30min的reqs+429数. 若429升则回调到12.0.
- **[HM1-B] k4(direct, idx=3)路由劣化修复**: 实测k4 avg28.5s vs其他~25s, p95=72.9s vs~55s, max=162.9s. 同为direct的k2正常→非direct通病, 是k4本机IP被NVCF标记/限速. 改法: 将HM_NV_PROXY_URL4从空(direct)改为mihomo端口(如7897, 需先确认HM2 mihomo 7897是否启用, 或借用对端mihomo). A/B: 对比k4改前改后30min p95.
- **[HM1-C] all_tiers_exhausted早fail**: 实测22次失败avg104s(p50=89s=BUDGET上限), 共耗2288s. 改upstream.py: 前3个key全NVCFPexecTimeout即fast-fail(不试k4/k5), 省~50s/次. 风险: 误杀k4/k5救回. A/B: 对比失败耗时+成功率. (此条需改源码, 比env风险高, 排在A/B后)

### 若对端是HM2(glm5.1, ${PEER}==HM2时本节生效)
- **[HM2-A] MIN_OUTBOUND_INTERVAL_S 4.5→2.5**: HM2 throttle=4.5s已较低但仍可降. 实测HM2吞吐受throttle影响. 降到2.5→吞吐+80%. 风险: NVCF同IP 429. A/B: 30min对比.
- **[HM2-B] HM2失败模式数据补采**: HM2近轮多"无操作", 需采60min per-key延迟+失败结构, 看是否有像HM1-k4那样的劣化key, 若有则改其路由.
- **[HM2-C] TIER_TIMEOUT_BUDGET_S 128→100**: HM2 BUDGET=128偏大(HM1=90), 失败请求会耗满128s. 降到100→失败早结束28s. 风险: 误杀100-128s慢成功(需先查HM2有无此区间成功). A/B: 对比.

执行规则: 优先A, A不可行或已做则B, 再C. 每轮1项. 改完必须A/B数据对比(改前窗口vs改后窗口), 在round文件里给出改前改后的 reqs/min, p50, p95, 成功率, 429数 对比表. 不允许"无操作"轮, 除非三项都已做完或数据证伪(证伪需给出具体数据).

## R320教训(必读, 避免重蹈)
R320 session犯了3个错, 后续轮次严防:
1. **一轮两改**: 同时改k3路由+throttle, 违反铁律5单参数. → 本轮严格只做清单1项, 不搭车.
2. **A/B验证空**: 改后数据全填"-"就commit翻轮. → 改后必须等≥15min或≥20req, 采真实数据填表, 不许"待部署后采集". 若流量低采不够, 显式说明并标"待观察", 不填"-".
3. **编造数据来源**: 称"MIN_OUTBOUND已在R318fix改compose", 实际R318fix只改prompt模板. → round文件里每句话都要可溯源, 改了什么就写什么, 不许把责任推给不存在的"前轮已改".
4. **compose必须同步**: 改容器env后必须同步改compose文件, 否则docker compose up会回退. → 改env类参数, compose文件和容器运行态两边都要改, round文件里贴两处的grep证据.
5. **DB时区陷阱**: hm_requests.ts是UTC, NOW()在DB里可能错位(实测差8h). → 查窗口一律用 `WITH t AS (SELECT MAX(ts) AS latest FROM hm_requests) SELECT ... FROM hm_requests, t WHERE ts > t.latest - INTERVAL '30 min'`, 禁止用 NOW()-interval.

## R322教训(必读, 避免重蹈)
R322 session犯了4个错, 后续轮次严防:
1. **live compose未同步(重演R320#4)**: 改了容器运行态env(PROXY_URL4=""→7897)但live `/opt/cc-infra/docker-compose.yml` line 438还是空. 下次docker compose up会回退. → 改env类参数, 必须改live compose文件并对端`docker compose up -d --force-recreate hm40006`(或rm -f后up)重建, 再`docker exec env`验证从compose读到的值. 不许只改容器运行态.
2. **commit改错文件**: live `/opt/cc-infra/docker-compose.yml` **不在git仓库**. 仓库里只有归档副本`deploy_artifacts/hm1_gateway_modular_R310/docker-compose.hm1.R310.yml`(R310快照,非live). 改归档副本对运行态无影响. → 改完live compose后, round文件里**显式说明"live compose不在git, 本次改动已部署生效但未入git, CC托底时会同步"**, 不要把改动commit到归档副本冒充live.
3. **round文件命名错**: 写到`rounds/RN_hm2_optimize_hm1.md`(模板)而非`rounds/R322_hm2_optimize_hm1.md`. → round文件必须命名`R<N>_hmX_optimize_hmY.md`, 不许写到RN模板.
4. **一轮三改+中途改动未记录**: 同时改k4路由+UPSTREAM_TIMEOUT+BUDGET(后两项称"同步误配"仍算改), 且CONNECT_RESERVE 24→16中途改了但round文件和commit都没提. → 一轮严格1参数; 任何中途试探改动(即使最终没用)都必须记入round文件, 不可溯源=违规.

## 反对者机制
本轮你是工程师, 对端是反对者。如果你提出方案有数据漏洞, 反对者(下轮)会驳回。所以本轮方案必须数据扎实、逻辑严密、改后验证到位。

## 评判标准
稳定优先 > 越快越好 > 单位时间请求越多越好 > 成功率越高越好 > 延迟越低越好 > 429/空200等报错越少越好。

## 输出
全程在终端输出你的思考+操作。完成后round文件commit+push即结束。不要等待人工确认, 自主完成全流程。

## R350教训(必读, 避免重蹈)
R350 session(HM2)在commit+push R349后**没有退出**,继续跑又做了下一轮R350(commit dce8e80,方向标反HM2→HM1,写到R350_hm2_optimize_hm1.md),与HM1正确触发的R350(83af387)撞号,且末尾标记相反导致watch选错文件误触发HM1 session 640125. CC已删除抢跑文件+杀误触发session. 根因:同一个claude session commit后不退出,自己又跑下一轮. → **本轮铁律: git push成功后必须立即停止, 不得继续执行任何操作(不得再读round文件/不得再改代码/不得再commit). 一轮一session, push完即结束. 反对者下轮会接手, 不需要你继续.** 违反此条=造成跨机撞号.
PROMPT

PROMPT_FILE="$LOG_DIR/prompt_${TS}.txt"

echo "[$TS] === 启动 ${ROLE} 优化 ${PEER} 自动执行 ===" | tee -a "$RUN_LOG"
echo "trigger: role=$ROLE round=$ROUND_NAME commit=$COMMIT" | tee -a "$RUN_LOG"
echo "next round file: $NEXT_ROUND_FILE" | tee -a "$RUN_LOG"
echo "prompt: $PROMPT_FILE" | tee -a "$RUN_LOG"
echo "" | tee -a "$RUN_LOG"

# 启动claude非交互session
# --allow-dangerously-skip-permissions: 无人值守必须(否则权限拦截)
# --add-dir: 允许访问仓库目录
# systemd service的PATH不含npm-global, 需显式找claude
CLAUDE_BIN="$(command -v claude 2>/dev/null || echo "$HOME/.npm-global/bin/claude")"
if [ ! -x "$CLAUDE_BIN" ]; then
    echo "[$(date '+%Y%m%d_%H%M%S')] claude未找到($CLAUDE_BIN), 退出" | tee -a "$RUN_LOG"
    rm -f "$TRIGGER_FILE"
    exit 127
fi
cd "$REPO_DIR"
# R350/R352/R354/R361教训: claude session可能卡住不退出(孤儿), 导致跨机撞车+抢跑下轮.
# 硬超时25min强制杀(nop轮~5-10min, 真实改动轮<20min, 25min足够). timeout杀claude后run_my_turn继续走pkill兜底.
SESSION_TIMEOUT_S="${SESSION_TIMEOUT_S:-1500}"
echo "[$(date '+%Y%m%d_%H%M%S')] 启动claude (硬超时${SESSION_TIMEOUT_S}s)" | tee -a "$RUN_LOG"
timeout --signal=KILL "$SESSION_TIMEOUT_S" "$CLAUDE_BIN" -p "$(cat "$PROMPT_FILE")" \
    --add-dir "$REPO_DIR" \
    --add-dir "$HOME/cc-infra" \
    --allow-dangerously-skip-permissions \
    2>&1 | tee -a "$RUN_LOG"

EXIT_CODE=${PIPESTATUS[0]}
echo "[$(date '+%Y%m%d_%H%M%S')] === claude session退出 code=$EXIT_CODE (124=超时) ===" | tee -a "$RUN_LOG"

# 清理trigger (已执行完)
rm -f "$TRIGGER_FILE"

# 保险: 收割残留claude子进程(防孤儿session继续commit撞号). timeout已杀主进程, 此处收割可能的子shell残留.
pkill -9 -f "claude -p.*优化工程师" 2>/dev/null || true

exit "$EXIT_CODE"
