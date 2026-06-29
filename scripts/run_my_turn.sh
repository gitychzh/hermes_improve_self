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
4. 基于数据找1个单参数/单逻辑改动点(改前有数据支撑)。如确无安全且有疗效的改动, 允许"⏸️无变更"轮(交付排查报告+翻轮)
5. 在对端实施改动(备份→改→重启/rebuild→验证实质数据流向)
6. 采集改后数据(短窗口对比)
7. 写round文件 $NEXT_ROUND_FILE (summary/参数表/改前数据/改动/预期/验证/结论), 末尾必须是 $NEXT_MARKER
8. git add + commit + push origin main
9. 翻轮完成

## 反对者机制
本轮你是工程师, 对端是反对者。如果你提出方案有数据漏洞, 反对者(下轮)会驳回。所以本轮方案必须数据扎实、逻辑严密、改后验证到位。

## 评判标准
稳定优先 > 越快越好 > 单位时间请求越多越好 > 成功率越高越好 > 延迟越低越好 > 429/空200等报错越少越好。

## 输出
全程在终端输出你的思考+操作。完成后round文件commit+push即结束。不要等待人工确认, 自主完成全流程。
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
"$CLAUDE_BIN" -p "$(cat "$PROMPT_FILE")" \
    --add-dir "$REPO_DIR" \
    --add-dir "$HOME/cc-infra" \
    --allow-dangerously-skip-permissions \
    2>&1 | tee -a "$RUN_LOG"

EXIT_CODE=${PIPESTATUS[0]}
echo "[$(date '+%Y%m%d_%H%M%S')] === claude session退出 code=$EXIT_CODE ===" | tee -a "$RUN_LOG"

# 清理trigger (已执行完)
rm -f "$TRIGGER_FILE"

# 保险: 收割残留claude子进程(防孤儿session继续commit撞号)
pkill -9 -f "claude -p.*优化工程师" 2>/dev/null || true

exit "$EXIT_CODE"
