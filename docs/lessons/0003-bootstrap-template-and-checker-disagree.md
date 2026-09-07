---
id: L0003
date: 2026-09-07
outcome: useful
tags: [serendipity, bootstrap, 模板, 上游缺陷]
anchors:
  - CONTEXT.md
  - .claude/skills/se-bootstrap/SKILL.md
supersedes:
hits: 0
generalizes_to: 任何「模板 ＋ 驗收腳本」成對出現的配置
validated:
---

# Serendipity 的 `templates/CONTEXT.md` 照著填會過不了 `bootstrap_check.sh`

## 觸發情境

用 `se-bootstrap` 把 Serendipity 帶進新專案，走到 Phase 4「用 `templates/CONTEXT.md` 產出 `CONTEXT.md`」。

## 領悟

**模板產出的格式，過不了驗收腳本。**

`templates/_meta/bootstrap_check.sh` 判 `CONTEXT.md` 是否夠充實的方式是
數以 `|` 開頭的行（`grep -c '^|'`），要求 ≥ 5——也就是**要一張表格**。

而 `templates/CONTEXT.md` 的 Language 段落用的是粗體加冒號的散文格式：

```markdown
**<詞>**：
<一句話定義。用領域語言，不用實作細節。>
```

照著填，`grep -c '^|'` 回傳 **0**【已確認：2026-09-07 對
`Serendipity-Epiphany/templates/CONTEXT.md` 實測，exit code 1】，八項檢查失敗一項。

本專案是因為改用表格才過的（13 列），不是因為模板對。

## 為什麼會撞到

錯誤假設是：**模板與驗收腳本是同一份規格的兩種表達，所以會一致。**

它們是分別寫的，而且沒有任何機制要求它們一致。腳本的註解寫得很清楚
「核取方塊靠人記得，腳本不會忘」——正確，但腳本自己也需要一個東西來確認
它量的是模板真的會產出的形狀。

這與繼承來的 L0003（量尺自己要先被量）是同一族，但更具體：
**驗收腳本的第一個測試案例，應該是它自己那個模板的空白填充結果。**

## 下次怎麼做

**在 Serendipity 上游改一邊**，兩個選項擇一：

- 把 `templates/CONTEXT.md` 的 Language 段改成表格（`| 詞 | 定義 | 避免的舊叫法 |`），或
- 把 `bootstrap_check.sh` 的判準從「數 `|` 開頭的行」改成「數粗體詞條」，例如
  `grep -cE '^\*\*.+\*\*'`。

改哪一邊是取捨：表格好機械化驗收但擠得慌；散文好讀但難數。
本專案選了表格，而且發現表格的「避免的舊叫法」那一欄實際上很好用——
它逼你寫下**被取代掉的那個叫法**，那正是 `CONTEXT.md` 要防的歧義來源。

**在改上游之前**：新專案的 `CONTEXT.md` 就直接用表格寫，不要照模板填了再回頭修。

更一般的做法：**任何「模板 ＋ 驗收腳本」成對出現的地方，加一個把模板本身
餵給腳本的測試。** 兩份文件會漂，只有可執行的東西不會。

## 失效條件

- Serendipity 上游修掉其中一邊——這一則就完成任務，改標 `corrected` 或封存。
- `bootstrap_check.sh` 改成不檢查 `CONTEXT.md` 的充實度——這一則不再適用，
  但「模板要能通過自己的驗收腳本」那一句仍然成立。
