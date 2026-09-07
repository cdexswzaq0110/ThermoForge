#!/usr/bin/env bash
# PreToolUse gate（git commit 時觸發）：強制 .claude/CLAUDE.md 維護契約 #1「Router 不說謊」。
#
# 三向檢查：
#   1. skills/ 有目錄，INDEX.md 沒列       → 索引漏列
#   2. INDEX.md 用反引號提到，目錄不存在   → 索引指向已刪 skill
#   3. 常駐檔提到 /se-xxx，skill 不存在    → 常駐面斷鏈（INDEX 掃不到的那一類）
set -uo pipefail

MODE="${SE_CHECK_ROUTER_MODE:-block}"
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
INDEX="$ROOT/.claude/skills/INDEX.md"
SKILL_DIR="$ROOT/.claude/skills"

# 不是這個 repo 就放行
[ -f "$INDEX" ] || exit 0
[ -d "$SKILL_DIR" ] || exit 0

missing=""
stale=""
dangling=""

for d in "$SKILL_DIR"/*/; do
  [ -d "$d" ] || continue
  name=$(basename "$d")
  grep -q -- "$name" "$INDEX" || missing="$missing $name"
done

for name in $(grep -o '`se-[a-z0-9-]*`' "$INDEX" 2>/dev/null | tr -d '`' | sort -u); do
  [ -d "$SKILL_DIR/$name" ] || stale="$stale $name"
done

for f in "$ROOT/CLAUDE.md" "$ROOT/.claude/CLAUDE.md" "$ROOT"/.claude/rules/*.md; do
  [ -f "$f" ] || continue
  for name in $(grep -o '/se-[a-z0-9-]*' "$f" 2>/dev/null | sed 's|^/||' | sort -u); do
    [ -d "$SKILL_DIR/$name" ] || dangling="$dangling $(basename "$f"):$name"
  done
done

if [ -n "$missing$stale$dangling" ]; then
  {
    echo "[check-router] 維護契約 #1 違反：Router 與實際目錄不一致。"
    [ -n "$missing" ]  && echo "  目錄存在但 INDEX 未列出:$missing"
    [ -n "$stale" ]    && echo "  INDEX 提到但目錄不存在:$stale"
    [ -n "$dangling" ] && echo "  常駐檔指向不存在的 skill:$dangling"
    echo ""
    echo "先同步 .claude/skills/INDEX.md（或修正常駐檔的引用）再 commit。"
    echo "（由 .claude/hooks/check-router.sh 強制；目前模式 $MODE）"
  } >&2
  [ "$MODE" = "block" ] && exit 2
  exit 1
fi

exit 0
