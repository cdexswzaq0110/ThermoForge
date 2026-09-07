# Skills 索引與路由

Skills 是 **Coroutine 庫**——任務語意命中才載入，不無條件常駐。

流程結構見 [../WORKFLOW.md](../WORKFLOW.md)；實際走查見 [../RUNBOOK.md](../RUNBOOK.md)；派發語彙見 [../EXECUTION_MODEL.md](../EXECUTION_MODEL.md)。

## 情境路由

| 你在做什麼 | 載入 | 別選錯 |
|---|---|---|
| 需求還模糊，要探索方案並定接縫 | `se-design` | 不是直接開寫——探索沒做完的實作會重寫 |
| 想法太大、**連要問什麼都不確定** | `se-discovery` | 不是 `se-design`——後者探索一個你握得住的問題；discovery 給你握不住的那種，而且只產決策不產方案 |
| 要被逼問到想清楚／想法要先被戳破／答案在別人身上 | `se-clarify` | 不是 `se-design`——clarify 只問不做，產的是共識不是計畫 |
| 不確定值不值得做 | `se-feasibility` | 不是 `se-clarify`——後者釐清「要什麼」，前者判斷「做不做得到、划不划算」 |
| 專案詞彙混亂、AI 一直用錯名詞 | `se-context-language` | 只是「讀 CONTEXT.md 拿詞彙」不需要載入它，那是一行提示 |
| 要寫程式 | `se-minimal-change` | |
| 有 bug、測試失敗、行為異常 | `se-debug` | 不是先猜著改——先要可重現的失敗 |
| 變更完成要審查 | `se-two-axis-review` | 不是 `se-minimal-change` 的過度工程審查——後者只管複雜度，正確性與安全明確在它範圍外 |
| 要任務分解、派發、管平行、處理卡住的並行 | `se-scheduling` | 不是 `se-design`——design 產切片，scheduling 派切片 |
| 外部 CLI／MCP／API 不確定能不能用 | `se-preflight` | |
| 開分支、worktree、收尾開 PR、救亂掉的歷史 | `se-branch-lifecycle` | |
| 回答太長太散 | `se-focus` | |
| 這一輪學到東西了／要召回舊教訓／帳本該回顧了 | `se-epiphany` | |
| 要新增或修改 skill、改常駐提示 | `se-skill-authoring` | |
| **要把這套配置帶進新專案** | **`se-bootstrap`** | 不是 `se-sdlc`——bootstrap 讓**配置**在新專案成立，sdlc 決定**專案**由誰負責哪一層 |
| **要從零啟動一個專案、盤點缺哪個角色的產出、決定某件事該誰負責** | **`se-sdlc`** | 不是 `se-scheduling`——sdlc 決定**由誰負責哪一層的正確性**，scheduling 決定**怎麼派**。先跑 sdlc 定角色，再用 scheduling 派工 |

## 特例領域（遇到相關問題才觸發）

這兩個不是每個專案都會用到，但一旦命中就整套接手——它們有自己的階段與 Gate。

| 你在做什麼 | 載入 | 別選錯 |
|---|---|---|
| 設計一個系統、拿到 PRD 要寫架構文件、被問怎麼擴展／怎麼避免超賣、評估既有架構瓶頸 | `se-system-design` | 不是 `se-design`——後者規劃**一個功能怎麼實作**並定測試接縫；system-design 決定**整個系統長什麼樣**並產出取捨總表。設計定案後才交給 `se-design` 拆片 |
| 做 ML 專案、訓練或改進模型、處理 split 與 leakage、選 metric、要上線 | `se-ml-lifecycle` | 不是 `se-debug`——模型分數不好不是 bug，先看 Gate 哪一道沒過。優先序：split ＞ leakage ＞ metric ＞ 語意 ＞ baseline ＞ 特徵 ＞ 模型 ＞ 調參 |
| 要說明模型靠什麼決定、某一筆為什麼是這個結果、要 reason code 或公平性檢查 | `se-ml-lifecycle` Stage 6 | 不是 `thread-ml-auditor`——後者問「分數可不可信」，Stage 6 問「模型依賴什麼、在哪會錯」。**Gate 1 沒過不要做解釋**，解釋出來的會是 leakage |

對應的 Agent：`thread-system-architect`（唯讀設計）· `process-ml-engineer`（實作）· `thread-ml-auditor`（分數可不可信）· `thread-ml-interpreter`（模型依賴什麼、在哪會錯）。

**兩個 ML 唯讀 Thread 不要搞混**：auditor 檢查**驗證設計**，interpreter 檢查**模型行為**。auditor 先跑——Gate 1 沒過的話，interpreter 解釋出來的是 leakage。

## 角色分工

專案要跑完整流程時，十個角色各自負責一層的正確性——定義、層級與執行單位對照見 [`../ROLE_MODEL.md`](../ROLE_MODEL.md)，操作程序見 `se-sdlc`。

| 角色 | 一句話 | 執行單位 |
|---|---|---|
| PM | 為什麼要做 | Scheduler 戴帽子 ＋ `se-clarify`／`se-feasibility` |
| UX / UI | 使用者怎麼走、長什麼樣 | `thread-ux` |
| SA | 系統怎麼判斷 | `thread-sa` |
| Architect | 系統怎麼活下去 | `thread-system-architect` |
| SD | 模組怎麼長 | Scheduler 戴帽子 ＋ `se-design` |
| DBA | 資料怎麼存 | `thread-dba` |
| Dev | 真的把它做出來 | `process-worker` |
| QA | 確認沒壞 | `thread-reviewer-spec` ＋ `thread-reviewer-standards` |
| DevOps / SRE | 活著 | `thread-devops` |

**UX、SA、DBA、DevOps 的分析階段寫入範圍不相交，是同一個 Thread Pool。** Architect 必須在 Barrier 之後——它要看齊四份分析才能取捨。

**不是每個專案都要十個角色。** 判準：這個角色不做，會由誰、在什麼時候、用什麼代價補？

## 能力庫

| 類別 | Skill | 使用時機 |
|---|---|---|
| 探索與設計 | `se-design` | 模糊問題、方案探索、接縫選擇、垂直切片 |
| 未知探索 | `se-discovery` | 太大又太模糊、一個 Process 裝不下的工作 |
| 需求釐清 | `se-clarify` | 設計樹／施壓／問卷三模式 |
| 可行性 | `se-feasibility` | 投入前的技術、成本、時間、風險評估 |
| 共享語言 | `se-context-language` | 建立與維護 `CONTEXT.md` |
| 最小變更 | `se-minimal-change` | 最小實作階梯、過度工程審查、`DEBT:` 債務帳 |
| 除錯 | `se-debug` | 紅→縮→猜→測→修→綠 |
| 審查 | `se-two-axis-review` | Spec 軸與 Standards 軸雙軌 |
| 排程 | `se-scheduling` | 切片、Ready Queue、寫入鎖、派發與驗證 |
| 前置檢查 | `se-preflight` | Connection Pool 的取得程序 |
| 分支 | `se-branch-lifecycle` | worktree、commit、PR、歷史恢復 |
| 輸出治理 | `se-focus` | 密度與收斂 |
| 長期記憶 | `se-epiphany` | 捕捉／召回／回顧領悟帳本 |
| Skill 作者工具 | `se-skill-authoring` | 寫給 Agent 看的文件、觸發測試、出貨門檻 |
| **角色分工** | `se-sdlc` | 十角色三道翻譯 Gate：PM → UX/UI/SA → Architect/SD/DBA → Dev/QA/DevOps |
| **系統設計** | `se-system-design` | 九階段：估算 → 實體與不變量 → API → 瓶頸深挖 → 資料層 → 取捨總表 |
| **ML 生命週期** | `se-ml-lifecycle` | 七階段六道 Gate：定義 → 切分 → Pipeline → 評估 → **可解釋性** → 上線與監控 |

**只載入當前步驟必要的能力**；不要為了「完整」一次預載全部。

## 四個權威，互不重疊

輸出行為由四個地方分工，衝突時照這張表仲裁：

| 權威 | 管什麼 |
|---|---|
| [../rules/thinking-boundary.md](../rules/thinking-boundary.md) | **誰思考**（速通／深思）、預算 |
| [../rules/register.md](../rules/register.md) | **何時換語域**（文件 L1/L2/L3；對話何時翻到決策層） |
| [../rules/evidence-grades.md](../rules/evidence-grades.md) | **每個結論的證據等級** |
| `se-focus` | **輸出密度與收斂** |

### 已知張力（刻意保留的仲裁點）

| 張力 | 仲裁 |
|---|---|
| `se-focus` 要 `file:line`，`register.md` 要「用動作講機制」 | `register.md`「何時不可以白話」第一條：使用者要**定位**時不白話 |
| `se-focus` 要簡短，`evidence-grades` 要標等級 | 等級不可省。省的是路徑、行號、推導過程 |
| `se-minimal-change` 要最短 diff，`core-rules` 4 要驗證證據 | 階梯本身：非平凡邏輯必須留一個可跑的檢查 |
| `se-scheduling` 要用滿並行，鎖規則要序列化 | 鎖優先。用滿的是**無衝突**的部分 |

## 責任檢查（新增內容前先判斷）

| 問題 | 是 → 放哪 |
|---|---|
| 每次任務都必須遵守，而且與模型預設行為不同？ | `rules/`——而且要能在 [../ABLATION.md](../ABLATION.md) 填出「失敗證據」 |
| 是知識、清單或可重用做法？ | Skill（Coroutine） |
| 需要獨立 context、工具或權限？ | Agent（Thread／Process），並預載現有 Skill |
| 是確定、快速、低頻且無隱性狀態的自動化？ | 才考慮 Hook |
| 曾被拒絕過？ | 先讀 `../.out-of-scope/` 對應檔再提案 |

## 擴充與來源

新增 Skill 時保留來源、授權與更新方式（維護契約第 4 條），並先檢查是否已有重疊能力。

每條規則為什麼存在，見 [../../docs/DESIGN_RATIONALE.md](../../docs/DESIGN_RATIONALE.md)。

**全域共用**：把 skill 目錄 symlink 到 `~/.claude/skills/`，檔案實體留在專案內（版控追得到），全域只放捷徑。

```bash
# Linux / WSL
ln -s "$(pwd)/.claude/skills/se-epiphany" ~/.claude/skills/se-epiphany
```
```powershell
# Windows（需要管理員或開發者模式）
New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.claude\skills\se-epiphany" -Target "$PWD\.claude\skills\se-epiphany"
```
