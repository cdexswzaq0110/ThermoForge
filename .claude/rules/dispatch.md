# 派發規則（Dispatch）

完整的執行模型、Pool 與同步原語在 [`../EXECUTION_MODEL.md`](../EXECUTION_MODEL.md)。本檔只留**每次派發都成立、而且與模型預設行為不同**的四條。

## 1. 預設是 Coroutine

需要一套方法 → **載入 skill，繼續在同一個 context 做**。隔離有啟動成本，只有真的買到東西才付：

| 買到什麼 | 用哪個 |
|---|---|
| 沒買到隔離，只是想「分工看起來比較專業」 | Coroutine |
| 髒 context 隔離、唯讀第二意見、廣度 fan-out | **Thread** |
| 乾淨 context、要寫工作樹、跨切片邊界 | **Process** |

## 2. 一個 Process 一個切片，Process 之間必須換 Process

- **探索 → 規劃 → 切片：全程同一個 Process，不中斷、不 compact。** 這幾步互為前提，中途 swap 會讓切片建立在摘要過的推導上。
- **Process 之間：斷開。** 上一片的實作細節對下一片是雜訊。
- 跨 Process 靠**落地產出**接續（計畫檔、測試、commit、handoff 文字），不靠對話摘要。
- 規劃逼近 ~120k 就寫下結論、開新 Process，不硬撐。

## 3. 平行前先確認鎖

Ready Queue = `Depends on` 已全數完成的 Process。**能平行就全部立即派發，用滿平台並行數，不自行保守限制。**

但先確認沒有共用鎖。以下同時只能有一個持有者：

同一檔案或模組寫入 · Schema · Migration · Lockfile · 同分支 git 寫操作 · 正式資料／Runtime · GPU 等單一硬體 · 全專案測試

**任何 git 寫操作前先驗證 ref 沒被別的 session 推進**：`git branch --show-current`、`git log --oneline -3`、`git status`。

出現以下任一警訊就 **STOP 並詢問**：工作樹有不認得的變更、同 subject 不同 SHA 的 commit、分支 tip 與上次所見不同、出現未追蹤的 backup tag 或 sibling branch、HEAD 指向不認得的 commit。

寫入衝突**不是依賴**——標明衝突範圍讓排程器序列化，不要把它們串成 `Depends on` 鏈。

## 4. GIL：一次只問一個決策

人的決策是全域鎖。

- 能從程式庫、文件或工具確認的**事實**自己查，不丟回去問。
- 只把**決策**交給人，一次一個，附推薦答案、理由與主要代價。
- 發現多個缺口時，只問「猜錯要重做」的（上限 3 個），其餘宣告假設往下做。
- 需要人拍板的情況：需求有多種會產生不同可觀察結果的解讀、會改變已核准範圍或公開介面、涉及不可逆處置或安全接受程度。
