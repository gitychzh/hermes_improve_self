#!/bin/bash
# ============================================================
# HM2 交替优化轮询脚本 (HM2角色)
# ============================================================

REPO_DIR="$HOME/hm_ps/hermes_improve_self"
MY_HOSTNAME="$(hostname)"      # opc2sname
MY_GIT_USER="opc2_uname"       # HM2的git用户
OPPONENT_USER="opc_uname"      # HM1的git用户

cd "$REPO_DIR" || exit 1

# === 步骤1: 强制同步远端最新 ===
git fetch origin main 2>&1
git reset --hard origin/main 2>&1

# === 步骤2: 检查最新 commit 作者 — 必须是对端 (HM1) ===
LATEST_AUTHOR=$(git log -1 --format='%an' HEAD)
LATEST_MSG=$(git log -1 --format='%s' HEAD)

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 最新提交: $LATEST_AUTHOR → $LATEST_MSG"

# 如果提交者是本机(HM2)，这是我自己提交的 — 不触发
if [ "$LATEST_AUTHOR" = "$MY_GIT_USER" ]; then
    echo "这是我提交的，不触发。等待对方(HM1)行动。"
    exit 0
fi

# 如果不是HM1的提交，也是不相关
if [ "$LATEST_AUTHOR" != "$OPPONENT_USER" ]; then
    echo "最新提交者非对方，不触发。"
    exit 0
fi

# === 步骤3: HM1提交了! 检查 round 文件 ===
LATEST_ROUND=$(ls -1t "$REPO_DIR/rounds"/R*_*.md 2>/dev/null | head -1)

if [ -z "$LATEST_ROUND" ]; then
    echo "无轮次记录，等待初始化。"
    exit 0
fi

FILENAME=$(basename "$LATEST_ROUND")
LAST_LINE=$(tail -1 "$LATEST_ROUND")

echo "对端提交，最新轮次: $FILENAME"
echo "最后一行: $LAST_LINE"

# 检查 "轮到HM2" 标记
if echo "$LAST_LINE" | grep -q "轮到.*HM2.*优化.*HM1"; then
    echo "=================================================="
    echo "  ✅ 轮到我了 — HM2 立即执行优化！"
    echo "=================================================="
    exit 3  # 脚本返回3 → cron 触发 HM2 的优化流程
elif echo "$LAST_LINE" | grep -q "R1完成" || echo "$LAST_LINE" | grep -q "等待下一轮"; then
    echo "R1已完成，但标记不明确，等待下轮。"
    exit 0
fi

echo "无明确标记，等待。"
exit 0