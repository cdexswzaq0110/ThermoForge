# 資料契約、切分與 EDA

Gate 1 的細節。**這一階段做錯，後面所有分數都沒有意義。**

---

## 1. 資料盤點

- 記錄來源系統、抽取時間、查詢版本、授權與負責人。
- 計算 row/column 數、主鍵唯一性、target 缺失、資料期間與 SHA-256。
- 建立 data dictionary：欄位型別、單位、允許值、**產生時間**與業務意義。
- 標記 ID、target、時間、group、敏感欄位、**推論時不可用欄位**。

## 2. Data Contract

| 契約欄位 | 範例 | 驗證方式 |
|---|---|---|
| row grain | 每列是一筆已完成交易 | 主鍵與重複列檢查 |
| target | 成交後才知道的 SalePrice | train 必須非空且合法 |
| prediction time | 掛牌當下 | **移除成交後才產生的欄位** |
| event time | 交易日期 | 切分與延遲標籤檢查 |
| group | customer_id / device_id | 同 group 不跨 train/valid |
| schema version | v1.2 | 欄位、dtype、range diff |

Schema 驗證要涵蓋：欄位集合、dtype、range、nullable、unique、category policy。

**資料版本**：小型專案先用 `SHA-256 + row count + extract timestamp`；團隊或大資料再加 DVC / LakeFS / feature store。**不要為工具而工具。**

---

## 3. Split SOP

**在看模型以前先固定驗證設計。**

1. 先決定 split unit、時間界線與 group，**再**做 EDA 與特徵統計。
2. 保存 fold assignment，所有候選模型使用同一份切分。
3. 小資料優先 5-fold；variance 高時重複 2–3 seeds，但控制成本。
4. 建立 OOF：每列都由沒看過它的 fold model 預測。
5. 另保留 frozen holdout，或用 nested CV 評估完整的模型選擇流程。

### 硬規則

Imputer · scaler · encoder · feature selection · target encoding · PCA · rare pooling · outlier threshold —— **全部在 training fold fit**。

### Target encoding 特別注意

只能在 training fold 內計算再套到 validation；**training row 的編碼需要 OOF 或 leave-one-out + smoothing**。全資料 target mean encoding 是典型 leakage。

**Gate 2A**：可用程式重建相同 folds；每列 validation 次數符合預期；group/time/leakage 單元測試通過。

---

## 4. EDA：每一個圖都要導向一個決策

| 圖／分析 | 要回答的問題 | 可能決策 |
|---|---|---|
| Target histogram / ECDF | 偏態、長尾、零值、class balance？ | log/Box-Cox、metric、stratification、class weight |
| Missing bar + heatmap | 缺失是沒有設施、未知，還是流程問題？ | None/0、indicator、group median、資料修復 |
| Numeric distribution | 極端值、截尾、量綱、非線性？ | log1p、winsorize、robust scaler、tree |
| Category frequency | 高基數、稀有類、拼字、新類別？ | pool rare、one-hot、native categorical |
| Feature vs target | 單調性、交互作用、異常點？ | interaction、transform、殘差分析 |
| Correlation / redundancy | 共線性與重複訊號？ | regularization、刪除重複特徵 |
| Train/valid/test drift | 缺失率、分布、類別比例是否改變？ | 重切資料、sample weighting、監控 |
| Segment metric | 哪個區域、價位、客群最差？ | 新特徵、分群模型、風險揭露 |

- 每個圖旁寫 **Observation → Hypothesis → Action**，不只寫「有相關」。
- target 變換要以 metric 與殘差分布證明，不是因為圖比較漂亮。
- correlation 不代表因果；one-hot 後的重要性也不能直接轉成商業因果。
- **test 沒有 label 時只能檢查 covariate drift**，不能宣稱 performance 沒有 drift。

**Gate 2B**：每個資料問題都有處理決策或明確接受風險；沒有用全資料 target 做特徵選擇後再假裝 CV。

---

## 5. 清洗：先語意，再數值

### 順序

```
1 Schema        欄位、dtype、主鍵、target、時間、必要欄位
2 重複          完全重複 / 主鍵衝突 / 同事件多版本 —— 不要直接 drop_duplicates
3 型別          郵遞區號、月份、類型代碼即使是數字，也可能該視為 categorical
4 缺失語意      區分「設施不存在」「有設施但未知」「資料未蒐集」
5 不可能值      負面積、事件早於出生日期、超出業務邊界
6 類別正規化    空白、大小寫、拼字、同義詞、未知類別政策
7 Outlier       先查資料錯誤，再決定保留 / 轉換 / 加權 / robust loss / 排除
```

| 問題 | 推薦 | 不推薦 |
|---|---|---|
| 設施不存在 | categorical=`'None'`；對應數量=0 | 所有 NaN 一律 mean/0 |
| 一般 numeric 缺失 | training-fold median；必要時加 missing flag | 用全資料 mean |
| 群組相關 numeric | fold 內 group median → fold global median | 先在全資料聚合 |
| 未知 category | mode / `Missing` + `handle_unknown` | test 出現新類就失敗 |
| 極端值 | 查來源、log/robust loss/segment、敏感度分析 | 只因模型分數差就刪 |
| target outlier | 先定義業務範圍與客觀規則，做含／不含比較 | 根據 test/leaderboard 反推 |

**Gate 2C**：清洗器能處理空值、未見類別、額外/缺少欄位與極端輸入；規則只用 training data fit，且有最小單元測試。
