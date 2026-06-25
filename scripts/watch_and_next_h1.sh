#!/bin/bash
REPO_DIR="$HOME/hm_ps/hermes_improve_self"
MY_GIT_USER="opc_uname"
OPPONENT_USER="opc2_uname"
LOCK_FILE="$REPO_DIR/.hm1_processed_head"

cd "$REPO_DIR" || exit 1

git fetch origin main 2>&1
git reset --hard origin/main 2>&1

LATEST_AUTHOR=$(git log -1 --format='%an' HEAD)
LATEST_HASH=$(git rev-parse HEAD)
LATEST_MSG=$(git log -1 --format='%s' HEAD)
TS=$(date '+%Y-%m-%d %H:%M:%S')

if [ -f "$LOCK_FILE" ]; then
    PROCESSED_HASH=$(cat "$LOCK_FILE" 2>/dev/null)
    if [ "$LATEST_HASH" = "$PROCESSED_HASH" ]; then
        echo "[$TS] 已处理过此commit($LATEST_HASH), 等待新提交"
        exit 0
    fi
fi

if [ "$LATEST_AUTHOR" = "$MY_GIT_USER" ]; then
    echo "[$TS] 这是我提交的, 不触发"
    echo "$LATEST_HASH" > "$LOCK_FILE"
    exit 0
fi

LATEST_ROUND=$(ls -1t "$REPO_DIR/rounds"/R*_*.md 2>/dev/null | head -1)
if [ -z "$LATEST_ROUND" ]; then
    echo "[$TS] 无轮次记录"
    exit 0
fi

FILENAME=$(basename "$LATEST_ROUND")
LAST_LINE=$(tail -1 "$LATEST_ROUND")

echo "[$TS] 对端提交 $LATEST_HASH, 轮次: $FILENAME"
echo "[$TS] 标记: $LAST_LINE"

if echo "$LAST_LINE" | grep -q "轮到.*HM1.*优化.*HM2"; then
    echo "=================================================="
    echo "  ✅ 轮到我了 — HM1 立即执行优化！"
    echo "=================================================="
    echo "$LATEST_HASH" > "$LOCK_FILE"
    exit 3
fi

echo "$LATEST_HASH" > "$LOCK_FILE"
exit 0
