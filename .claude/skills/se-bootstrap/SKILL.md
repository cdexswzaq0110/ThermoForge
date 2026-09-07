---
name: se-bootstrap
description: 把這套 harness 帶進一個新專案——建版控、複製配置、問清楚四個 Phase 的問題、產出那個專案自己的 CLAUDE.md 與 CONTEXT.md，最後跑機械化檢查確認沒漏。當要在新專案啟用這套配置、剛複製完 .claude/ 不知道下一步、或使用者說「新專案要怎麼開始」「bootstrap 一下」時使用。
---

# Bootstrap — 帶進新專案

**這個 skill 只做一件事：讓一個新專案從「複製了一堆檔案」變成「配置真的成立」。**

完整說明在 [`templates/_meta/new_project_bootstrap.md`](../../../templates/_meta/new_project_bootstrap.md)。
這裡是可執行的順序。

## Phase 0 — 先進版控（不可逆的那一條）

```bash
cd <新專案>
git init -b main
printf '.claude/settings.local.json\n' > .gitignore
git add -A && git commit -m "chore: bootstrap"
```

**在複製任何檔案之前做完。** 2026-09-02 第一次把這套配置帶進真實專案時，因為還沒
init，一個檔案被工具毀掉之後只能整份重寫（`docs/lessons/0004`）。

⚠ **檢查上層目錄**。新專案若開在一個已經是 git repo 的目錄底下（家目錄本身被版控就會這樣），
`git status` 會有反應，但那是**上層的**版控。Phase 3 的檢查腳本會抓這種情況。

## Phase 1 — 四個基礎問題

```
1. 專案名稱？
2. 一句話：這個專案解決什麼問題？
3. 主要語言與框架？
4. 這是雛型驗證，還是要往 production 走？
```

第 4 題決定後面所有的深度。**不確定就填雛型**——用 production 的標準卡住雛型是最常見的浪費。

## Phase 2 — 七問澄清

核心問題 · 核心功能（3–5 個）· 技術約束 · 使用體驗 · 規模需求 · 時程資源 · 成功標準。

**答不出來的題目載入 `se-clarify` 的決策樹模式，不要猜著填。**

## Phase 3 — 前置檢查

跑 `se-preflight`：這台機器上有什麼 CLI、什麼 MCP、什麼 API key、平台並行數多少。
**在寫第一行程式碼之前做完。**

## Phase 4 — 產出三份檔案

1. **專案的 `CLAUDE.md`**——只放**環境查不到**的東西。`package.json` 已有的 script 不要抄一份。
2. **`CONTEXT.md`**——用 `templates/CONTEXT.md`。一開始只填三到五個詞，這時候你猜的比知道的多。
3. **`docs/lessons/INDEX.md`**——空索引，等第一則。

## Phase 5 — 機械化驗收

**不要用眼睛核對：**

```bash
bash templates/_meta/bootstrap_check.sh <新專案路徑>
```

八項檢查，任一不過 exit 1。**核取方塊靠人記得，腳本不會忘**——這份清單原本是七個方塊，
第一次被真的執行時就漏掉了最重要的那一條（版控）。

腳本判不了、要人自己確認的兩項：

- 專案的 `CLAUDE.md` 只放環境查不到的東西
- 新專案裡用不到的 templates 已刪掉

## 兩種安裝方式，選一種

| 方式 | 拿到什麼 | 適合 |
|---|---|---|
| **複製 `.claude/`** | 完整：常駐規則 ＋ skills ＋ agents ＋ hooks | 要完整紀律的專案 |
| **裝成 plugin**（`claude --plugin-dir <repo>`） | skills ＋ agents ＋ hooks，**不含常駐規則** | 只想要能力、不想要常駐約束 |

**plugin 帶不了 `rules/`**——那是專案層的東西。要常駐紀律就得用複製。

## 完成條件

- `bootstrap_check.sh` 八項全過
- 專案 `CLAUDE.md` 的「實際指令」表只寫環境查不到的
- `CONTEXT.md` 有三到五個真的會用到的詞
- 第一輪之後跑一次消融（見 `.claude/ABLATION.md`）——繼承來的規則有一部分是在補一個已經不存在的模型缺陷
