# 開發工作流（結構）

這裡定義**誰負責什麼**。實際怎麼跑一輪見 [RUNBOOK.md](RUNBOOK.md)；任務怎麼切、派給誰見 [EXECUTION_MODEL.md](EXECUTION_MODEL.md)。

**這個 配置 不規定流程順序。** 它只保證四件事：常駐約束永遠生效、能力隨叫隨到、需要隔離時有對應的派發單位、每一輪的領悟不會蒸發。

## 三層 ＋ 一個帳本

| 層 | 執行模型對應 | 什麼時候作用 | 誰觸發 | 不放什麼 |
|---|---|---|---|---|
| `rules/` | **Kernel** | 永遠 | 自動載入 | 方法論 |
| `skills/` | **Coroutine 庫** | 任務語意命中 | 模型判斷或 `/skill-name` | 不變的鐵律 |
| `agents/` | **Thread／Process 模板** | 需要隔離 context、權限、平行或第二意見 | 主 Process 委派 | Skills 的知識 |
| `docs/lessons/` | **持久化儲存** | 跨輪、跨專案 | `se-epiphany` | 這一輪才有意義的暫態 |

## 三個角色

| 角色 | 誰 | 做什麼 | 不做什麼 |
|---|---|---|---|
| **Scheduler** | 主 Process（你正在對話的這個） | 規劃、派發、驗證、收斂 | 不自己做 worker 級的工作 |
| **Supervisor** | 最強模型的唯讀 Thread | 只在**承諾邊界**被諮詢：策略、分解批判、風險、品味 | **從不執行** |
| **Worker** | Thread Pool／Process Pool 成員 | 通過驗證的最便宜配置就好 | 不自我核准、不接下一個 Process |

**承諾邊界**——這四種情況才升級到 Supervisor：

1. 兩個 Worker 的結果互相矛盾，且超出已提供的 context
2. 同一個子任務驗證失敗兩次
3. 判斷落在成功條件之外
4. 計畫需要結構性改變

其餘時候 Supervisor 不進熱路徑。**模型是旋鈕，層級才是不變的部分**——模型 ID 會換代，「Supervisor 用你能拿到最強的推理模型、Worker 用能通過驗證的最便宜配置」這條不會。

### 降級模式

某個角色沒有可用路徑時：說清楚怎麼設定，然後提供降級——由 Scheduler 暫代該角色，**同樣預算**，受影響的段落與最終結果標記 `[降級: <角色>]`，並註明 context 隔離已失效。

降級最多涵蓋一個角色。兩個以上不可用時，就沒有團隊了——直說，然後當普通單模型工作繼續。

## Context 邊界

| 邊界 | 規則 |
|---|---|
| 探索 → 規劃 → 切片 | **不斷開、不 compact** |
| 規劃 → 實作 | **斷開**，每片從全新 Process |
| Process 之間 | **斷開** |
| Review 與驗證 | 獨立 Thread，首輪不互相參照 |

**水位線 ~120k**：規劃沒完成就逼近它，寫進計畫檔、開新 Process，**不要硬撐**。

## 驗證紀律

**驗證必須碰到交付物本身。**

grep 一下 README、測一個相鄰的東西、印出 `True` 然後 exit 0、再確認一次檔案存在——這些都證明不了任何事。跑真正的指令，讀真正的輸出。

每個結果三選一：**PASS** ／ **FIX**（重新派發，指名具體失敗）／ **ESCALATE**。

- 不得默默接受部分通過。
- 不得手動補丁一個實質失敗——重新派發。
- 多個 Worker 結果衝突時**顯式解決，不取平均**。

## 狀態板

每個派發步驟後印一行：

```
T2: FIX → PASS | claude→codex | 重試 1 次
P4: DISPATCHED | opus-5/high | 鎖: src/auth/**
```

欄位：子任務、狀態（PENDING／DISPATCHED／PASS／FIX／ESCALATED）、實際派發路徑、重試次數、持有的鎖。

## 該載哪個 Coroutine

| 你在做什麼 | 載入 |
|---|---|
| 需求還模糊，要探索 | `se-design` |
| 專案詞彙混亂、AI 一直用錯名詞 | `se-context-language` |
| 想法太大、連要問什麼都不確定 | `se-discovery` |
| 要被逼問到想清楚 | `se-clarify` |
| 動手前想確認值不值得做 | `se-feasibility` |
| 要寫程式 | `se-minimal-change` |
| 卡在 bug | `se-debug` |
| 變更完成要審查 | `se-two-axis-review` |
| 要任務分解、派發、管平行 | `se-scheduling` |
| 外部工具／CLI／MCP 不確定能不能用 | `se-preflight` |
| 收尾開 PR | `se-branch-lifecycle` |
| 回答太長太散 | `se-focus` |
| 這一輪學到東西了 | `se-epiphany` |
| 要新增或修改 skill 本身 | `se-skill-authoring` |

完整路由與區辨見 [skills/INDEX.md](skills/INDEX.md)。

## 常駐約束

| 規則 | 管什麼 |
|---|---|
| [core-rules](rules/core-rules.md) | 來源優先、可追溯、保護使用者工作、以證據宣告完成、最小變更、留下領悟 |
| [evidence-grades](rules/evidence-grades.md) | 每個結論帶等級：已確認／推論／候選／未知／未驗證 |
| [dispatch](rules/dispatch.md) | 預設 Coroutine、切片換 Process、平行前確認鎖、GIL 一次一問 |
| [git-workflow](rules/git-workflow.md) | 先開分支、Critical Section 先 backup tag、commit→push→PR 連貫 |
| [thinking-boundary](rules/thinking-boundary.md) | 速通／深思、雛型期不前置治理、預算超支不得靜默 |
| [register](rules/register.md) | 文件的 L1／L2／L3；對話何時翻到決策層 |

**新增常駐規則前先讀 [ABLATION.md](ABLATION.md)**——填不出失敗證據的不該常駐。
