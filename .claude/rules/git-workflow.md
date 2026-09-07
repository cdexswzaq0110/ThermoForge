# Git 工作流

只留**每次 git 操作都成立、而且與模型預設行為不同**的約束。commit message 細則、PR 前置檢查與 body 結構、worktree、tangled history 恢復策略見 [`../skills/se-branch-lifecycle/SKILL.md`](../skills/se-branch-lifecycle/SKILL.md)——要 commit／開 PR 時才載入。

多 session 並行的 ref 驗證與警訊清單在 [`dispatch.md`](dispatch.md) 第 3 條，不在這裡重複。

## 鐵律：先開分支，再動程式碼

- 收到開發任務的第一步：`git branch --show-current` + `git status`。
- 在 main/master 上、有未提交變更、或使用者沒指定分支就要改 code → **停止並詢問**。
- 不用 `git stash` 當工作流替代品。分支命名 `<type>/<short-description>`。由 `hooks/guard-branch.sh` 檢查（目前 warn 模式，只提示不阻擋）。

## Critical Section 先打 backup tag

`reset --hard`、`push --force`、`branch -D`、`rebase` 之前：

```bash
git tag -a backup/<branch>-<YYYY-MM-DD> -m '安全快照, tip <oid>'
```

恢復路徑：`git reset --hard backup/<branch>-<YYYY-MM-DD>`。**由 `hooks/guard-critical.sh` 強制**——HEAD 沒有對應的 `backup/*` tag 時，上述四種操作一律擋下。

## Commit → Push → PR 為單一連貫操作

使用者說「commit」「提交」「PR 這個」「推上去」或表達「這段工作做完」時，預設**一氣呵成**執行 `git commit` → `git push -u origin <branch>` → `gh pr create`。**禁止在中間插入「要不要 push？」「要不要開 PR？」。**

例外（明確中斷）：使用者明說只要 commit 或只要 push；merge 到共享分支；destructive 操作。

## Commit Message

寫之前先 `git log --oneline -10` 對齊該專案的既有風格。

## 程式碼 ↔ 文件同步

實作 code 與更新 docs 屬**同一個任務、同一個 PR**，不接受「以後再補文件」。

判準一條：**這次改動讓哪份已填寫的文件失真，就一起改。** 沒填過的模板不需要為了這條去填。`CONTEXT.md` 的詞彙若被這次改動推翻，同一個 PR 一起改——它是共享記憶體，過期比不存在更貴。
