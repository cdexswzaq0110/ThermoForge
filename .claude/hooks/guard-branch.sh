#!/usr/bin/env bash
# PreToolUse gate：受保護分支上不得直接修改工作樹。
# 對應 rules/git-workflow.md「鐵律：先開分支，再動程式碼」。
#
# 模式（改這一行就能切換）：
#   warn  → exit 1，transcript 顯示 hook error 提示，動作照常進行
#   block → exit 2，直接阻擋工具呼叫
# 第一輪先跑 warn，累積「擋幾次、擋得對不對」的證據，再改 block。
set -uo pipefail

MODE="${SE_GUARD_BRANCH_MODE:-warn}"
PROTECTED="main master"

cd "${CLAUDE_PROJECT_DIR:-$PWD}" 2>/dev/null || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

branch=$(git branch --show-current 2>/dev/null)
[ -z "$branch" ] && exit 0

for p in $PROTECTED; do
  if [ "$branch" = "$p" ]; then
    cat >&2 <<EOF
[guard-branch] 目前在受保護分支 '$branch'，不可直接修改工作樹。

先開分支再繼續：
  git checkout -b feature/<task-name>

（rules/git-workflow.md 鐵律，由 .claude/hooks/guard-branch.sh 檢查；目前模式 $MODE）
EOF
    [ "$MODE" = "block" ] && exit 2
    exit 1
  fi
done

exit 0
