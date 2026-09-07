#!/usr/bin/env bash
# Gate 自測：確認三支 hook 在**該擋的時候真的擋**、該放的時候真的放。
#
# 為什麼要有這支：hook 寫壞的預設失敗模式是「靜默放行」——路徑錯、spawn 失敗、
# 退出碼用錯，全部只產生 non-blocking error，動作照常執行。裝好不等於守得住，
# 必須看過一次紅燈。詳見 docs/lessons/0002。
#
# 用法：bash .claude/hooks/selftest.sh
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
H="$ROOT/.claude/hooks"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0

check() { # expected actual label
  if [ "$1" = "$2" ]; then
    pass=$((pass + 1)); printf '  ok    %s\n' "$3"
  else
    fail=$((fail + 1)); printf '  FAIL  %s（期望 %s，實得 %s）\n' "$3" "$1" "$2"
  fi
}

run() { # script payload -> exit code
  printf '%s' "$2" | bash "$H/$1" >/dev/null 2>&1
  echo $?
}

bash_payload() { printf '{"tool_name":"Bash","tool_input":{"command":"%s"}}' "$1"; }
edit_payload='{"tool_name":"Edit","tool_input":{"file_path":"README.md"}}'

# ---------- guard-branch ----------
echo "guard-branch"
REPO="$TMP/repo"; mkdir -p "$REPO"
( cd "$REPO" && git init -q -b main . && git config user.email t@t && git config user.name t \
  && echo x > a.txt && git add . && git commit -qm init ) >/dev/null 2>&1
export CLAUDE_PROJECT_DIR="$REPO"

check 1 "$(run guard-branch.sh "$edit_payload")" "main（warn 模式）提示但不阻擋"
check 2 "$(printf '%s' "$edit_payload" | SE_GUARD_BRANCH_MODE=block bash "$H/guard-branch.sh" >/dev/null 2>&1; echo $?)" \
        "main（block 模式）阻擋"
( cd "$REPO" && git checkout -q -b feature/x )
check 0 "$(run guard-branch.sh "$edit_payload")" "feature 分支放行"

# ---------- guard-critical ----------
echo "guard-critical"
for c in "git reset --hard HEAD~1" \
         "git push --force origin main" \
         "git push -f origin main" \
         "git branch -D feature/x" \
         "git rebase -i main" \
         "git add . && git reset --hard HEAD"; do
  check 2 "$(run guard-critical.sh "$(bash_payload "$c")")" "無 tag 時攔下：$c"
done

for c in "git status" \
         "git push origin main" \
         "git branch -d feature/x" \
         "git reset HEAD~1" \
         "git commit -m 'docs: 說明 rebase 恢復策略'" \
         "echo git reset --hard is dangerous" \
         "grep -rn 'branch -D' docs/"; do
  check 0 "$(run guard-critical.sh "$(bash_payload "$c")")" "不該攔：$c"
done

( cd "$REPO" && git tag -a "backup/selftest" -m snap )
check 0 "$(run guard-critical.sh "$(bash_payload "git reset --hard HEAD~1")")" "已有指向 HEAD 的 backup tag 時放行"

# ---------- check-router ----------
echo "check-router"
FAKE="$TMP/fake"; mkdir -p "$FAKE/.claude/skills/se-a" "$FAKE/.claude/skills/se-b"
export CLAUDE_PROJECT_DIR="$FAKE"
commit_payload=$(bash_payload "git commit -m x")

printf '# INDEX\n\n- `se-a`\n' > "$FAKE/.claude/skills/INDEX.md"
check 2 "$(run check-router.sh "$commit_payload")" "目錄存在但 INDEX 未列出"

printf '# INDEX\n\n- `se-a`\n- `se-b`\n' > "$FAKE/.claude/skills/INDEX.md"
check 0 "$(run check-router.sh "$commit_payload")" "INDEX 與目錄一致"

printf '# INDEX\n\n- `se-a`\n- `se-b`\n- `se-ghost`\n' > "$FAKE/.claude/skills/INDEX.md"
check 2 "$(run check-router.sh "$commit_payload")" "INDEX 指向已刪 skill"

printf '# INDEX\n\n- `se-a`\n- `se-b`\n' > "$FAKE/.claude/skills/INDEX.md"
printf '跑 /se-nope 開始。\n' > "$FAKE/CLAUDE.md"
check 2 "$(run check-router.sh "$commit_payload")" "常駐檔指向不存在的 skill"

export CLAUDE_PROJECT_DIR="$ROOT"
check 0 "$(run check-router.sh "$commit_payload")" "本專案目前狀態一致"

# ---------- 結果 ----------
echo ""
echo "通過 $pass／失敗 $fail"
[ "$fail" -eq 0 ] || exit 1
