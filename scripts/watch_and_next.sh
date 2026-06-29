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
    LOCK_FILE="$REPO_DIR/.hm1_processed_head"
    MY_TURN_MARKER="轮到HM1.*优化.*HM2"
    ROLE_LABEL="HM1"
else
    MY_GIT_USER="opc2_uname"
    OPPONENT_USER="opc_uname"
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
LATEST_ROUND=$(ls -1t "$REPO_DIR/rounds"/R*_*.md 2>/dev/null | head -1)

if [ -z "$LATEST_ROUND" ]; then
    echo "[$TS] $ROLE_LABEL: 无round文件, 等待"
    echo "$LATEST_HASH" > "$LOCK_FILE"
    exit 0
fi

FILENAME=$(basename "$LATEST_ROUND")

# 是我自己提交的(且round文件标记不是我轮次) → 标记已处理
if [ "$LATEST_AUTHOR" = "$MY_GIT_USER" ]; then
    # 即使我提交的, 也要看round标记(可能我提交了round标记轮到对端, 此时不应触发我)
    if grep -qE "$MY_TURN_MARKER" "$LATEST_ROUND"; then
        # 我提交的但标记说轮到我? 不应发生(我提交应标记轮到对端)。安全起见不触发, 标记已处理
        :
    fi
    echo "$LATEST_HASH" > "$LOCK_FILE"
    # 静默(避免自己push后每分钟打印)
    exit 0
fi

# 对端提交了, 检查是否轮到我
echo "[$TS] $ROLE_LABEL: 对端($OPPONENT_USER)提交 $LATEST_HASH, 轮次: $FILENAME"

# 检查是否轮到我了(grep整个文件, 标记可能在文件末尾)
if grep -qE "$MY_TURN_MARKER" "$LATEST_ROUND"; then
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
    exit 0  # 退出码0, 不让systemd标Failed
fi

# 对端提交但不是轮到我(我是反对者角色)
echo "[$TS] $ROLE_LABEL: 对端提交但未轮到我(我是反对者), 等待"
echo "$AFTER" > "$LOCK_FILE"
exit 0
