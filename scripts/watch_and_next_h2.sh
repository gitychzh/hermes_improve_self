#!/bin/bash
# ============================================================
# HM2 交替优化轮询脚本 (HM2角色)
# 逻辑:
#   1. 先同步远端最新 (git fetch + reset)
#   2. 检查最新commit是不是对端(HM1)提交的
#   3. 如果是, 再读R1文件的最后一行
#   4. 如果标记"轮到HM2", 返回 exit 3
# ============================================================

REPO_DIR="$HOME/hm_ps/hermes_improve_self"
MY_GIT_USER="opc2_uname"
OPPONENT_USER="opc_uname"

cd "$REPO_DIR" || exit 1

# === 步骤1: 强制同步 ===
git fetch origin main 2>&1
git reset --hard origin/main 2>&1

# === 步骤2: 检查最新commit作者 ===
LATEST_AUTHOR=$(git log -1 --format='%an' HEAD)
LATEST_MSG=$(git log -1 --format='%s' HEAD)
TS=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TS] 最新: $LATEST_AUTHOR → $LATEST_MSG"

# 如果是自己的提交 (HM2), 不触发
if [ "$LATEST_AUTHOR" = "$MY_GIT_USER" ]; then
    echo "[$TS] 这是我提交的, 不触发。"
    exit 0
fi

# === 步骤3: 对端提交了 → 检查轮次文件 ===
LATEST_ROUND=$(ls -1t "$REPO_DIR/rounds"/R*_*.md 2>/dev/null | head -1)
if [ -z "$LATEST_ROUND" ]; then
    echo "[$TS] 无轮次记录。"
    exit 0
fi

FILENAME=$(basename "$LATEST_ROUND")
LAST_LINE=$(tail -1 "$LATEST_ROUND")

echo "[$TS] 对端提交, 轮次: $FILENAME"
echo "[$TS] 标记: $LAST_LINE"

# 判断是否轮到我
if echo "$LAST_LINE" | grep -q "轮到.*HM2.*优化.*HM1"; then
    echo "=================================================="
    echo "  ✅ 轮到我了 — HM2 立即执行优化！"
    echo "=================================================="
    exit 3
fi

exit 0