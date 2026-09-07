# 封裝、MLOps、測試與上線

Gate 4A–4C 的細節。

---

## 1. Final Fit 與 Inference Contract

1. 鎖定 champion config、資料版本、code commit 與 dependencies。
2. 依已確認策略在完整 training data fit。**禁止再看 frozen holdout 調參。**
3. 保存完整 pipeline、feature manifest、schema、label mapping 與 threshold。
4. 建立 batch/online inference contract：欄位、dtype、order、nullable、輸出與 **error behavior**。
5. 執行 **golden dataset regression test**：序列化前後 prediction 一致。
6. 輸出 Model Card、metrics、segment risk、latency、size、owner 與 rollback 版本。

| Artifact | 至少包含 |
|---|---|
| model / pipeline | transformers + estimator + threshold / calibrator |
| run summary | data / code / env / config / metrics / cost / decision |
| OOF prediction | row id、fold、truth、prediction、segment |
| feature manifest | 名稱、型別、公式、來源、online availability |
| 可解釋性報告 | 方法與參數、Global/Local、stability、失敗模式、不適用範圍 |
| inference contract | request/response schema、錯誤與缺失政策 |
| model card | 用途、不適用範圍、風險、公平性、監控與 owner |

**Gate 4A**：乾淨環境能載入 artifact，對 raw-like sample 產生有限、符合 schema 的 prediction；hash、版本與 golden test 一致。

---

## 2. Experiment Ledger

每個 run 都要能回答「這次改了什麼、為什麼、結果如何、決定怎樣」。

| 欄位 | 內容 |
|---|---|
| run_id / time | 唯一識別、起訖時間、owner |
| data | dataset hash、schema version、rows、time range |
| code / env | Git commit / dirty、Python、套件、硬體 |
| **hypothesis** | 為什麼這個改動可能改善哪一類錯誤 |
| **change** | feature / model / param / split 的**唯一**主要差異 |
| evaluation | folds、seeds、primary/secondary/segment metrics |
| cost | training time、inference latency、model size |
| decision | accept / reject、原因、下一個實驗 |

### Review 問句

- 這個提升是否來自**相同 folds**？
- 是否**大於 noise**？
- **哪個 segment 變差**？
- 是否增加 train/serve gap？
- **若拿掉最複雜的部分，還剩多少增益？**

---

## 3. MLOps 追蹤層級

| 層級 | 追蹤內容 |
|---|---|
| Data | source、hash、schema、rows、time range、missing、label distribution |
| Code / Env | Git branch/commit/dirty、Python、library、container/hardware |
| Config | features、split、folds、seeds、model params、thresholds |
| Metrics | fold/OOF、std、CI、segments、calibration、latency、size |
| Artifacts | pipeline、OOF/test prediction、importance、plots、summary |
| Decision | hypothesis、accept/reject、champion/challenger、owner |

**工具選擇**：單人專案先用實驗追蹤 + local artifacts + Git + hashes；多人與 production 再加 remote store、registry、DVC/feature store、CI/CD。**先解 lineage，不先堆平台。**

### Promotion Gate

| 檢查 | 通過條件 |
|---|---|
| Correctness | schema、unit、integration、golden prediction 測試通過 |
| Performance | frozen/nested evaluation 達標，改善大於 noise |
| Segments | 關鍵群體無超過門檻的退化 |
| Operations | latency、throughput、memory、cost、availability 達標 |
| Risk | privacy、security、fairness、fallback、human review 完成 |
| Reproducibility | data/code/env/model artifacts 與 lineage 完整 |
| Rollback | 上一版可部署、切換方式與 owner 明確 |

---

## 4. 測試策略

**用最少的測試守住最大的風險。**

| 測試層 | 最小必要案例 |
|---|---|
| Schema | 缺欄、多欄、dtype、range、duplicate ID、target invalid |
| Cleaning | semantic missing、未知類別、不可能值、日期邊界 |
| Feature | 公式、除零、fit-before-transform、prediction-time availability |
| Pipeline | raw frame fit/predict、sparse/dense、序列化 round-trip |
| CV / OOF | 每列 held-out 次數、fold 無交疊、group/time boundary |
| Metric | 小型已知輸入的手算結果、sample weight |
| Inference | 單列/批次、欄位順序、NaN/inf、輸出 schema |
| Regression | golden dataset prediction tolerance |

**Gate 4B**：測試失敗**不可以**用刪測試、放寬到無意義的 tolerance、或 hard-code prediction 來解決。修正共同根因後重跑。

> 這條與 `se-debug` 的紀律一致：先做出可重現的失敗，再改。

---

## 5. 部署、監控、Retraining、Rollback

| 監控類型 | 範例 | 回應 |
|---|---|---|
| Service | latency、error、timeout、throughput、resource | scale、降級、回滾 |
| Schema / quality | 缺欄、dtype、range、missing、unknown category | 阻擋或 quarantine batch |
| Covariate drift | PSI、KS、JS distance、category ratio | 調查來源與 segment |
| Prediction drift | 分數分布、coverage、threshold rate | 檢查產品/資料變更 |
| Performance | MAE/AUC/log loss、calibration、segment | 有 label 後 challenger / retrain |
| Concept drift | 相同 X→y 關係改變 | 新資料、特徵、模型或規則 |
| Fairness | 群體錯誤率/coverage 差異 | 風險評估、閾值/流程修正 |

### Retraining policy（四選一或組合）

- **Time-based**：固定每週/月重訓。適合穩定且資料持續累積。
- **Performance-based**：label 回來後跌破門檻才啟動。
- **Drift-based**：**只有 drift 不等於 performance 一定下降**，需 challenger 驗證。
- **Event-based**：產品、定價、流程、感測器或資料來源改版時強制重驗。

**任何 retrain 都是新 run，不覆蓋舊 model。** 先 shadow/canary，再 promote。

### Rollback

保存上一個 production artifact、schema 與設定；定義自動/人工觸發門檻、切換步驟、資料回補與事後分析 owner。

**Gate 4C**：上線前已有 dashboard、alert owner、label feedback、retrain rule、fallback 與 **rollback 演練**。**沒有監控的模型不算 production-ready。**

---

## 6. Model Card 最小模板

| 章節 | 內容 |
|---|---|
| Model details | 名稱、版本、owner、日期、framework、artifact URI |
| Intended use | 使用者、決策、prediction time、適用範圍 |
| **Not intended** | 禁止用途、OOD、低 coverage、高風險情境 |
| Training data | 來源、期間、樣本、hash、label、清洗與 split |
| Evaluation | metric、folds、frozen result、segments、uncertainty |
| Features | 主要家族、敏感欄位、availability、leakage controls |
| **Interpretability** | 解釋方法與參數、Global 前 10 與 rank stability、代表性 local 個案、受保護屬性代理檢查結果 |
| **Limitations** | 已知失敗模式、偏誤、資料不足、外插 |
| Operations | latency、threshold、monitor、retrain、fallback、rollback |
| Governance | reviewer、promotion record、privacy/security/fairness |

「Not intended」與「Limitations」兩節是 Model Card 的重點。寫「無已知限制」通常代表沒認真想。

---

## 7. 專案骨架

```
project/
├─ README.md            # 問題、資料、執行、結果、限制
├─ requirements.txt     # 固定依賴版本
├─ config/              # 實驗設定；不放 secrets
├─ data/raw/            # 原始資料，通常不 commit
├─ data/processed/      # 可重建的處理後資料
├─ notebooks/           # 探索；正式邏輯移入 src
├─ src/data.py          # schema、cleaning、features、pipeline
├─ src/train.py         # CV、模型、tuning、artifacts
├─ src/predict.py       # batch / online inference
├─ tests/               # 最小但關鍵的資料與 pipeline 測試
├─ reports/             # EDA、model card、decision log
└─ artifacts/<run_id>/  # model、OOF、metrics、predictions
```

- 固定 Python 與套件版本；**seed 只保證部分可重現**，仍要記錄硬體與 library。
- 設定檔管理 folds、seed、feature set、model params；token/API key **只放環境變數**。
- **原始資料只讀**；任何清洗都由程式重建，不手動覆蓋 CSV。
- 先用函式與標準 Pipeline；需求穩定後才增加額外抽象（`se-minimal-change`）。

**Gate 1A**：新環境可依 README 安裝、讀 sample data、跑一個 smoke test；`git status` 不含 raw data、token、模型大檔與本機資料庫。

---

## 8. 本流程的邊界

以下情境沿用治理與驗證原則，但**切分、特徵與模型必須另行設計**：

- **時間序列**：seasonality、forecast horizon、backtesting、lag availability、hierarchy。
- **NLP / CV**：標註品質、augmentation、pretrained model、GPU、內容安全。
- **因果推論**：treatment、counterfactual、identification assumptions。**不能用一般 predictive importance 取代。**
- **推薦 / Ranking**：user-item split、negative sampling、ranking metric、線上實驗。
- **高風險領域**（醫療、金融、人事）：更嚴格的法規、審查、fairness、privacy 與 human-in-the-loop。

> 先把流程完整跑通一次，再依專案風險與規模增加工具。**不要因為想做 MLOps 就先建平台**——先證明資料、驗證與模型流程正確。
