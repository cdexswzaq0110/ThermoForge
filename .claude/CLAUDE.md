# 配置元件責任與維護契約

本檔管**元件責任與維護契約**——這套配置 由哪些元件組成、改動它時不能破壞什麼。

入口敘述（這是什麼、怎麼開始、預設節奏）在根目錄 [`CLAUDE.md`](../CLAUDE.md)，不在這裡重複。

## 設計原則：Skills 厚，Runtime 薄

常駐面只放**每次工作都成立、而且與模型預設行為不同**的約束。其餘一律下放到按需載入的 Skill。

## 元件責任

- 根目錄 `CLAUDE.md`：**常駐**入口。只放「這是什麼、怎麼開始、預設節奏」與路由連結；細節一律連結，不 paraphrase。
- `rules/`：**常駐**規則。條件性細則一律下放到對應 skill 的 `references/`。消融紀錄見 [ABLATION.md](ABLATION.md)。
- `skills/`：**Coroutine 庫**——按需載入的能力資料庫；路由見 [`skills/INDEX.md`](skills/INDEX.md)。
- `ROLE_MODEL.md`：十個 SDLC 角色、四個抽象層、三道翻譯 Gate。角色管「負責哪一層的正確性」，與執行單位正交。
- `agents/`：**Thread／Process 模板**——需要獨立 context、權限邊界、平行處理或第二意見時才使用。派發規則見 [EXECUTION_MODEL.md](EXECUTION_MODEL.md)。
- `templates/`：文件與交付物模板。**依需要取用，不強制填滿**。
- `../docs/lessons/`：領悟帳本。這套配置的長期記憶，由 `se-epiphany` 維護。
- `hooks/`：**確定性 Gate**——判定條件寫得成 shell 的規則放這裡，模型配不配合都會執行。清單見 [ABLATION.md](ABLATION.md)「機械化優先」。
- `.out-of-scope/`：已審視並拒絕的機制與理由；重新提案前先讀對應檔。
- `../.claude-plugin/plugin.json`：**發佈面**。`claude --plugin-dir <repo>` 裝得起來，帶 skills／agents／hooks；**帶不了 `rules/`**（常駐面是專案層的東西）。
- `../AGENTS.md`：非 Claude Code agent 的入口指標。只放指標與三條跨工具仍成立的約束，不重複內容。

## 維護契約（改動本配置時必須重新滿足的不變量）

1. **Router 不說謊**：新增、改名、刪除 skill 或改變其定位時，必須同步更新 `skills/INDEX.md`。索引漏列新 skill、或仍導向已刪 skill，視為缺陷而非疏漏。**由 `hooks/check-router.sh` 在 `git commit` 前強制**（三向：目錄未列入索引／索引指向已刪 skill／常駐檔指向不存在的 skill）。
2. **Frontmatter 與現實一致**：Skill 的 `description` 不得引用已退役的模板或檔名。
3. **大型 skill 分層**：SKILL.md 超過約 200 行時拆 `references/`（漸進揭露），不整檔常駐。
4. **來源可追**：新增第三方或社群 skill 必須在 `skills/INDEX.md` 記來源、授權與更新方式。
5. **拒絕有紀錄**：退役或否決一個機制時，在 `.out-of-scope/` 留一檔（概念、理由、先例）；重新提案前先讀它。
6. **常駐面要有證據**：新增任何常駐內容（根目錄 `CLAUDE.md`、本檔、`rules/*.md`）時，必須在 [ABLATION.md](ABLATION.md) 的分類表新增一列並填「失敗證據」。填不出證據的不該常駐，改寫成 skill 按需載入。
7. **調用軸不得混淆**：每個 skill 只能是「使用者調用」（`disable-model-invocation: true`，description 寫給人看）或「模型可調用」（description 保留觸發語，寫給模型看）之一。使用者調用的 skill 可以呼叫模型可調用的 skill，**不得呼叫另一個使用者調用的 skill**。
8. **改 skill 要跑觸發測試**：改動 description 後，跑 [`../docs/eval/trigger-cases.md`](../docs/eval/trigger-cases.md) 的案例集，確認該載入時載入、不該載入時不載入，並把命中率寫進該檔的執行紀錄。判準與寫法見 `skills/se-skill-authoring/references/eval-bar.md`。

## Runtime Context

不把每次對話或 Subagent 摘要寫成專案內的影子文件。Claude Code 的 session／task 機制處理暫態狀態；值得長期保存的內容進入 `docs/lessons/`、ADR、模板文件或測試證據。

純過渡的交接筆記寫到 OS 暫存目錄，**不進 repo**。
