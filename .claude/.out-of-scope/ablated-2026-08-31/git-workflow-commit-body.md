# `git-workflow.md`「Body 按需寫，不是必填」

- **加入日期**：2026-08-14（建立基線時）
- **移除日期**：2026-08-31
- **狀態**：已消融（可撈回）

## 原文

```markdown
## Commit Message 的兩條常駐約束

1. 寫之前先 `git log --oneline -10` 對齊該專案的既有風格。
2. **Body 按需寫，不是必填**——diff 已經是 WHAT 的單一真相源。
```

第 1 條保留，第 2 條移除。

## 它原本在解什麼問題

`ABLATION.md` 登記的理由是：**與全域 `~/.claude/CLAUDE.md` 的 WHY/WHAT/IMPACT 要求衝突**。全域要求每個 commit 都寫結構化 body，這條把它覆寫成「按需」。處置欄寫「全域同步後刪除」。

## 為什麼移除

**衝突對象不存在。**

全域指令檔的實際檔名是 `~/.claude/CLAUDE.md.md`——副檔名重複。Claude Code 載入的是 `~/.claude/CLAUDE.md`，所以那 666 行從來沒有進過任何 session 的 context。【已確認：2026-08-31 `ls -la ~/.claude/` 只有 `CLAUDE.md.md`；本次 session 注入的 CLAUDE.md 也只有專案的三份】

一條常駐規則的存在理由是覆寫另一條規則，而那條規則從未生效——這條就是純粹的 context 成本。

## 什麼情況下該撈回來

**條件很明確**：`~/.claude/CLAUDE.md.md` 被改名為 `~/.claude/CLAUDE.md`（或另外建立一份全域指令）**且**該檔要求 commit body 必填。

那時候先讀這一份，再決定是撈回這條、還是改全域。
