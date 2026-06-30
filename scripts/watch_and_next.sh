#!/bin/bash
# ============================================================
# 交替优化轮询脚本 (HM1/HM2 各部署一份, 统一版 R314)
# 核心:
#   - 每1min poll远程仓库
#   - 检测到"非本机提交"且最新round文件标记"轮到我了" → 写trigger文件+醒目日志, 通知CC手动执行
#   - 不自动改代码(铁律: 改前有数据/改后必验证, 由CC新session手动执行)
#   - LOCK_FILE防止重复触发: 只在"已通知"后写入该commit hash
# ============================================================
# 设计变更(R314):
#   - 旧版exit 3无人消费(systemd标Failed) → 改exit 0 + 写trigger文件
#   - 旧版LOCK_FILE在pull时即更新导致吞触发 → 改为只在"确认轮到我并通知后"更新
#   - 1min周期(原5min)
# ============================================================

REPO_DIR="$HOME/hm_ps/hermes_improve_self"
MY_HOSTNAME="$(hostname)"
MY_ROLE="${MY_ROLE:-HM1}"
if [ "$MY_ROLE" = "HM1" ] && [ "$MY_HOSTNAME" = "opc2sname" ]; then
    MY_ROLE="HM2"
fi

if [ "$MY_ROLE" = "HM1" ]; then
    MY_GIT_USER="opc_uname"
    OPPONENT_USER="opc2_uname"
    PEER="HM2"; PEER_USER="opc2_uname"; PEER_IP="100.109.57.26"
    LOCK_FILE="$REPO_DIR/.hm1_processed_head"
    MY_TURN_MARKER="轮到HM1.*优化.*HM2"
    ROLE_LABEL="HM1"
else
    MY_GIT_USER="opc2_uname"
    OPPONENT_USER="opc_uname"
    PEER="HM1"; PEER_USER="opc_uname"; PEER_IP="100.109.153.83"
    LOCK_FILE="$REPO_DIR/.hm2_processed_head"
    MY_TURN_MARKER="轮到HM2.*优化.*HM1"
    ROLE_LABEL="HM2"
fi

TRIGGER_FILE="$REPO_DIR/.my_turn_trigger"
cd "$REPO_DIR" || exit 1

TS=$(date '+%Y-%m-%d %H:%M:%S')

# fetch + fast-forward (不用reset --hard, 避免丢本地未提交改动)
git fetch origin main 2>&1 >/dev/null
BEFORE=$(git rev-parse HEAD 2>/dev/null)
git pull --ff-only origin main 2>/dev/null >/dev/null
AFTER=$(git rev-parse HEAD 2>/dev/null)

# 检查LOCK_FILE: 是否已处理过当前HEAD (已通知过则静默等待)
if [ -f "$LOCK_FILE" ]; then
    PROCESSED=$(cat "$LOCK_FILE" 2>/dev/null)
    if [ "$AFTER" = "$PROCESSED" ]; then
        # 已处理过此commit, 静默等待(不打印, 减少日志噪音)
        exit 0
    fi
fi

# 此时: 要么有新提交, 要么LOCK_FILE不存在/不匹配(首次运行或被重置)
# 都需要检查最新round文件是否轮到我
LATEST_AUTHOR=$(git log -1 --format='%an' HEAD)
LATEST_HASH="$AFTER"
LATEST_MSG=$(git log -1 --format='%s' HEAD)
# 找最新round文件: 按R号数字排序取最大号, 同号多个文件时用mtime取最新
# (R350/R352撞车教训: 抢跑方与正确方同号, 抢跑方commit更早mtime更旧, 取mtime最新=正确方)
# 排除RN占位文件
LATEST_ROUND=$(for f in "$REPO_DIR"/rounds/R*_*.md; do
        [ -e "$f" ] || continue
        case "$f" in *RN_*) continue;; esac
        r=$(printf '%s' "$f" | grep -oP 'R\K[0-9]+')
        m=$(stat -c %Y "$f" 2>/dev/null || echo 0)
        printf '%s %s %s\n' "$r" "$m" "$f"
    done | sort -k1,1n -k2,2nr | tail -1 | cut -d' ' -f3-)

if [ -z "$LATEST_ROUND" ]; then
    echo "[$TS] $ROLE_LABEL: 无round文件, 等待"
    echo "$LATEST_HASH" > "$LOCK_FILE"
    exit 0
fi

FILENAME=$(basename "$LATEST_ROUND")

# 是我自己提交的 → 需区分: round提交(翻轮了) vs 非round提交(工具链修复等,没翻轮)
if [ "$LATEST_AUTHOR" = "$MY_GIT_USER" ]; then
    # 判断本次commit是否改动了最新round文件(改了=我提交了round=应已翻轮到对端)
    if git show --stat "$LATEST_HASH" -- "$(basename "$LATEST_ROUND")" 2>/dev/null | grep -q "rounds/"; then
        # 我提交了round文件 → 应已翻轮到对端, 标记已处理, 不触发我
        echo "$LATEST_HASH" > "$LOCK_FILE"
        exit 0
    fi
    # 我提交的是非round文件(工具链修复/脚本改动等), round标记未变 → 继续往下检查标记
    # 不exit, 落到下面的标记检查(若仍轮到我, 应触发)
    :
fi

# 对端提交了, 检查是否轮到我
echo "[$TS] $ROLE_LABEL: 对端($OPPONENT_USER)提交 $LATEST_HASH, 轮次: $FILENAME"

# 检查是否轮到我了: 只看文件末尾5行(避免正文里引用标记的误匹配)
if tail -5 "$LATEST_ROUND" | grep -qE "$MY_TURN_MARKER"; then
    # R350/R352撞车根治: 触发前SSH查对端有无claude session在跑, 有则跳过避免跨机并发
    # (抢跑方=对端上一轮session commit后未退出, 本机这跳触发会和它撞号)
    # 注意 pgrep 自匹配陷阱: ssh远程命令行本身含pattern串会被pgrep匹配到自己.
    # 修复: 不用pgrep -f带字面pattern, 改用ps过滤. claude优化session真实进程命令行含
    # "/.npm-global/bin/claude -p" 且 "--allow-dangerously-skip-permissions", 用ps+awk排除
    # 含"pgrep"/"ssh"/当前shell的行, 只留真实claude进程.
    PEER_PIDS=$(ssh -p 222 -o ConnectTimeout=5 -o BatchMode=yes "$PEER_USER@$PEER_IP" \
        'ps -eo pid,args 2>/dev/null | awk "/[c]laude -p .*--allow-dangerously-skip-permissions/ && !/pgrep|watch_and_next/ {print \$1}" 2>/dev/null' 2>/dev/null)
    if [ -n "$PEER_PIDS" ]; then
        echo "[$TS] $ROLE_LABEL: 轮到我, 但对端($PEER)仍有session在跑(PID=$PEER_PIDS), 跳过本跳避免跨机撞号"
        echo "$AFTER" > "$LOCK_FILE"
        exit 0
    fi
    echo "=================================================="
    echo "  ✅[$TS] 轮到我了 — $ROLE_LABEL 执行优化 (CC请介入新session)"
    echo "  对端提交: $LATEST_MSG"
    echo "  round文件: $FILENAME"
    echo "  trigger: $TRIGGER_FILE"
    echo "=================================================="
    # 写trigger文件供CC检测 (含commit/round/时间)
    {
        echo "role=$ROLE_LABEL"
        echo "commit=$AFTER"
        echo "round=$FILENAME"
        echo "opponent=$OPPONENT_USER"
        echo "detected_at=$TS"
        echo "round_file=$LATEST_ROUND"
    } > "$TRIGGER_FILE"
    # 写LOCK_FILE: 已通知, 防止重复触发(直到下一个对端commit)
    echo "$AFTER" > "$LOCK_FILE"
    # R314: 自动执行 — 调用执行器在本机起claude session改对端
    EXECUTOR="$REPO_DIR/scripts/run_my_turn.sh"
    if [ -x "$EXECUTOR" ]; then
        echo "[$TS] $ROLE_LABEL: 调用执行器 $EXECUTOR 自动执行优化..."
        bash "$EXECUTOR" 2>&1
        EXIT_C=$?
        echo "[$TS] $ROLE_LABEL: 执行器退出 code=$EXIT_C"
        exit $EXIT_C
    else
        echo "[$TS] $ROLE_LABEL: 执行器不存在, 仅写trigger通知(CC手动介入)"
        exit 0
    fi
fi

# 对端提交但不是轮到我(我是反对者角色)
echo "[$TS] $ROLE_LABEL: 对端提交但未轮到我(我是反对者), 等待"
echo "$AFTER" > "$LOCK_FILE"
exit 0
