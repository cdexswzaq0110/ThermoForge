---
name: se-branch-lifecycle
description: 分支的一生——開始工作時開出隔離的分支或 worktree，結束時走 commit、push、PR 或 merge 並收乾淨。含 commit message 慣例、PR 前置檢查與 body 結構、糾纏歷史的恢復策略。當要開始一段需要隔離的工作、要收尾提交、要開 PR、或 git 歷史亂掉需要救回來時使用。
---

# Branch Lifecycle — 分支的一生

常駐鐵律（先開分支、Critical Section 先 backup tag、commit→push→PR 連貫）在 [`../../rules/git-workflow.md`](../../rules/git-workflow.md)，本檔不重述。

## 開始

```bash
git branch --show-current && git status --short
```

在 main 上、有未提交變更、或使用者沒指定分支 → **停下來問**。

分支命名：`<type>/<short-description>`（`feat` / `fix` / `chore` / `refactor` / `docs`）。

### 什麼時候用 worktree

多個切片要**真正同時**跑（Process Pool）→ 每個 Process 一個 worktree，各自獨立的工作樹，避免搶同一個 checkout。

```bash
git worktree add ../<repo>-<slice> -b feat/<slice>
```

單一切片、或 Process 之間是序列的 → 不需要 worktree，多開一個目錄只是多一份要同步的狀態。

收工：`git worktree remove ../<repo>-<slice>`。**不要留孤兒 worktree**——那是 Connection 洩漏的一種。

## Commit

### 兩條常駐約束

1. 寫之前先 `git log --oneline -10` 對齊該專案的既有風格。
2. **Body 按需寫，不是必填**——diff 已經是 WHAT 的單一真相源。

### Subject

```
<type>(<scope>): <一句話，祈使句，不加句號>
```

- 一個 commit 做一件事。做了兩件就拆成兩個。
- 祈使句：`add rate limiting`，不是 `added` 或 `adds`。
- 50 字以內。講不完代表這個 commit 太大。

### Body（需要時才寫）

需要的情況：**為什麼**不明顯、有反直覺的取捨、或這個改動會讓讀者困惑。

```
<為什麼要改：問題或動機>

<如果有取捨：選了什麼、放棄了什麼>

<如果有影響：呼叫端要注意什麼>
```

**不要**在 body 裡複述 diff 做了什麼——那是 diff 的工作。

## PR 前置檢查

開 PR 之前，這五項跑過：

```bash
git log --oneline <base>..HEAD     # 1. commit 歷史乾淨嗎
git diff <base>...HEAD --stat      # 2. 動到的範圍符合預期嗎
<專案的測試指令>                    # 3. 測試真的跑過（不是「應該會過」）
<專案的 lint／type 指令>            # 4. 靜態檢查
git status --short                 # 5. 沒有該進去卻沒進去的檔案
```

第 3 項是 `core-rules` 第 4 條的落地：**沒實際跑過的檢查不得描述為通過。**

## PR Body 四段

```markdown
## 這個 PR 做什麼
<一到三句，讀者不看 diff 也知道發生什麼事>

## 為什麼
<問題、或這個改動解決的痛點。連到 issue／spec>

## 怎麼驗證
<Reviewer 可以照做的步驟或指令，含預期結果>

## 已知限制
<沒做的、留給後續的、有 `DEBT:` 標記的地方。沒有就寫「無」>
```

第四段最常被跳過，而它最省 review 的來回——**Reviewer 最想知道的是你知不知道自己沒做什麼。**

## 糾纏歷史的恢復

**動任何東西之前先打 backup tag**（`rules/git-workflow.md`）。

| 症狀 | 處置 |
|---|---|
| commit 訊息寫錯（還沒 push） | `git commit --amend` |
| commit 訊息寫錯（已 push、且只有你在用） | amend + `push --force-with-lease`（**不是 `--force`**） |
| 一個 commit 該拆成兩個 | `git reset HEAD~1` 然後分次 `add -p` + commit |
| 幾個 commit 順序或內容要整理 | 先 backup tag，再 rebase |
| 分支落後 base 太多 | 優先 `merge base`；只有在歷史還沒被別人依賴時才 rebase |
| 跨 session 出現同 subject 不同 SHA | **停**。這是 race condition，問人，不要自行 cherry-pick |
| 誤刪分支 | `git reflog` 找回 SHA，`git branch <name> <sha>` |

**`--force-with-lease` 永遠優於 `--force`**：前者在遠端被別人推進時會拒絕，後者會直接輾過去。

## 收尾

使用者表達「這段工作做完」→ 一氣呵成：

```bash
git commit
git push -u origin <branch>
gh pr create
```

**中間不要問「要不要 push」「要不要開 PR」。**

例外（明確中斷）：使用者明說只要 commit 或只要 push；merge 到共享分支；destructive 操作。

PR 開完 → `se-epiphany` 判斷有沒有 Lesson。

## 完成條件

- 工作在非 main 的分支上完成。
- 五項前置檢查**實際跑過**，結果如實回報。
- PR body 四段完整，含「已知限制」。
- 用到的 worktree 已移除。
- destructive 操作前都有 backup tag。
