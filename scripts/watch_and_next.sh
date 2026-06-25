#!/bin/bash
# ============================================================
# 交替优化轮询脚本 (HM1/HM2 各部署一份)
# 核心:
#   - 检测远程仓库有 "非本机提交" 的新 commit → 轮到我了
#   - 一个在操作，另一个必须停止(但可参与计划讨论)
#   - 双方都有 cron 每5分钟轮询
# ============================================================

REPO_DIR="$HOME/hm_ps/hermes_improve_self"
MY_HOSTNAME="$(hostname)"   # opc2sname (HM2) 或 opc_uname (HM1)
MY_ROLE="${MY_ROLE:-HM1}"   # 通过环境变量传入

# 从主机名推断角色 (如果未设置)
if [ "$MY_ROLE" = "HM1" ] && [ "$MY_HOSTNAME" = "opc2sname" ]; then
    MY_ROLE="HM2"
fi

cd "$REPO_DIR" || exit 1

# 获取拉取前的 HEAD commit hash (远程修改前本地状态)
BEFORE_PULL=$(git rev-parse HEAD 2>/dev/null)

# === 步骤1: 拉取最新 ===
git pull --ff-only origin main 2>/dev/null

# === 步骤2: 检查是否有新提交 (不是我自己提交的) ===
AFTER_PULL=$(git rev-parse HEAD 2>/dev/null)

if [ -z "$BEFORE_PULL" ] || [ "$BEFORE_PULL" = "$AFTER_PULL" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 无新提交, 继续等待"
    exit 0  # 无变更, 正常退出
fi

# 有新提交! 检查最新 commit 的作者
LATEST_AUTHOR=$(git log -1 --format='%an' HEAD)
LATEST_COMMIT_MSG=$(git log -1 --format='%s' HEAD)

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 检测到新提交: ${LATEST_AUTHOR} → '${LATEST_COMMIT_MSG}'"

# 如果提交者不是本机用户, 说明是对端操作了
# HM1用户: opc_uname, HM2用户: opc2_uname
if [ "$MY_ROLE" = "HM1" ]; then
    MY_GIT_USER="opc_uname"
    OPPONENT_USER="opc2_uname"
elif [ "$MY_ROLE" = "HM2" ]; then
    MY_GIT_USER="opc2_uname"
    OPPONENT_USER="opc_uname"
fi

if [ "$LATEST_AUTHOR" = "$MY_GIT_USER" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 这是我提交的, 不是交替优化。等待对方行动。"
    exit 0
fi

# === 步骤3: 对端提交了! 检查最新 round 文件 ===
# 找到最新的轮次文件
LATEST_ROUND=$(ls -1t "$REPO_DIR/rounds"/R*_*.md 2>/dev/null | head -1)

if [ -z "$LATEST_ROUND" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 无轮次记录，等待初始化。"
    exit 0
fi

FILENAME=$(basename "$LATEST_ROUND")

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 对端($OPPONENT_USER)提交，最新轮次: $FILENAME"

# 提取最后一行判断是否轮到我了
LAST_LINE=$(tail -1 "$LATEST_ROUND")

# 检查 "轮到HM2优化HM1" 标记
if echo "$LAST_LINE" | grep -q "轮到.*优化"; then
    # 从标记中提取执行者
    TARGET=$(echo "$LAST_LINE" | grep -oP '(?<=轮到)(HM\d)' | head -1)
    
    if [ "$TARGET" = "$MY_ROLE" ]; then
        echo "=================================================="
        echo "  ✅ 轮到我了 — $MY_ROLE 立即执行优化！"
        echo "=================================================="
        exit 3  # 返回3 = 轮到我了, 触发优化 (cron会执行)
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 当前轮到 $TARGET, 我是 $MY_ROLE, 等待"
        # 我是质疑者角色, 可以输出参与计划讨论的建议
        if [ -n "$OPPONENT_USER" ]; then
            echo "质疑者提示: 我可以参与计划讨论，但等待执行者提交"
        fi
        exit 0
    fi
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 无明确轮到标记，等待"
exit 0