---
name: se-ml-lifecycle
description: 機器學習專案端到端流程，七階段六道 Gate——問題定義、資料契約與切分、清洗與特徵、Pipeline 與 baseline、CV/OOF 與調參、模型可解釋性與風險、封裝上線與監控。核心是先定義、再驗證、最後自動化，且驗證設計錯了任何分數都沒意義。當要做 ML 專案、訓練或改進模型、處理資料切分與 leakage、選 metric、做特徵工程、比較候選模型、要解釋模型依賴什麼或某一筆預測為什麼是這個結果、或要把模型推上線時使用。
---

# ML Lifecycle — 七階段六道 Gate

**這不是要求所有專案用同一個模型，是一套「先定義、再驗證、最後自動化」的決策順序。** 每個階段有輸入、動作、產出與 Gate；**只有 Gate 通過才進下一階段**。

適用：表格型監督式學習（regression / classification）。時間序列、ranking、影像、文字、RL 可沿用治理與驗證原則，但**切分、特徵與模型必須另行設計**。

## 優先順序（最重要的一個表）

```
正確的 split ＞ 防 leakage ＞ metric 對齊 ＞ 資料語意 ＞ baseline
              ＞ 特徵 ＞ 模型選擇 ＞ 調參 ＞ ensemble
```

**模型複雜度通常不是第一個瓶頸。** 有人想直接跳到調參時，指出他跳過了左邊哪幾項。

## 使用順序

| 情境 | 怎麼走 |
|---|---|
| 第一次做這個專案 | 依序走完六階段，先完成 MVP baseline，再進優化 |
| **模型已經存在** | **從資料契約、split 與 leakage 重新稽核**，不要直接跳到調參 |
| 每次實驗 | 只改一個主要假設，保存 config、資料指紋、OOF、結果 |
| 準備上線 | 執行 production readiness、監控與 rollback Gate |

## 總流程與 Gate

```
問題定義與決策
   ↓ Gate 0  target / prediction time / metric / owner 明確
資料契約 → split 策略 → EDA
   ↓ Gate 1  schema、leakage、missing、drift 風險已確認
清洗 → 特徵工程 → fold-local 前處理
   ↓ Gate 2  pipeline 可 fit/predict，未知類別與缺失測試通過
Baseline → 候選模型 → CV/OOF → 殘差分析
   ↓ Gate 3  改善跨 folds / seeds / segments 穩定
調參 → ensemble / 校準 → frozen evaluation
   ↓ Gate 3F 可解釋性：方法相符、跨 folds 穩定、失敗模式已指出、無因果誤述
   ↓ Gate 4  champion 通過品質、成本、公平與延遲門檻
Final fit → 封裝 → registry → 部署 → 監控 → retrain / rollback
```

---

## Stage 1 — 問題定義：先確認模型值不值得做

### 必答七問

```
1 決策       誰會在什麼時間，根據預測做什麼？
2 預測單位   一列代表客戶、交易、房屋、裝置，還是事件？
3 Target     標籤如何產生？何時才會知道？是否可靠且可回填？
4 預測時點   推論當下真正可取得哪些欄位？
5 錯誤成本   FP、FN、過高估與過低估各有何代價？
6 基準       現行人工規則、平均值或舊模型表現是多少？
7 限制       延遲、成本、解釋性、公平性、法規、隱私、部署環境？
```

第 1 題答不出來就不要建模。**「預測準」不是商業目標。**

**Gate 0**：Problem Statement 至少寫出輸入、target、預測時間、使用者、主要 metric、baseline、成本與**不做範圍**。

**常見錯誤**：先拿資料再找題目 · 把「預測準」當商業目標 · 用推論時不存在的欄位 · 只選容易提高的 metric。

---

## Stage 2 — 資料契約與切分

細節見 [`references/data-and-split.md`](references/data-and-split.md)。這裡只留最容易錯的三條：

### 硬規則：所有 fit 型處理都在 training fold 內

Imputer、scaler、encoder、feature selection、target encoding、PCA、rare pooling、outlier threshold ——**全部只能在 training fold fit**。

全資料先 fit 是最常見、也最難察覺的 leakage：validation 分數會樂觀，上線後才發現。

### split 要模擬未來推論情境

完整對照表見 `references/data-and-split.md`。三個最常錯的：**同客戶多列 → GroupKFold**（不是 StratifiedKFold）· **未來預測 → 禁止 random shuffle** · **最終驗證 → frozen holdout 或 nested CV**，不可重複偷看再改模型。

**保存 fold assignment**，讓所有候選模型使用同一份切分。

### OOF 是所有比較的共同語言

每一列都必須由**沒看過它**的 fold model 預測。OOF 用於模型比較、殘差分析與 ensemble；**不可在同一份 OOF 上無限制反覆選擇後，還當成 unbiased 的最終分數**。

**Gate 1**：可用程式重建相同 folds；每列 validation 次數符合預期；group/time/leakage 單元測試通過；一列資料的真實世界含義說得出來。

---

## Stage 3 — 清洗、特徵、Pipeline

細節見 [`references/modeling.md`](references/modeling.md)。三條原則：

1. **先處理語意，再處理數值。** 區分「設施不存在」「有設施但未知」「資料未蒐集」——全部 `fillna(0)` 會破壞業務語意。
2. **每個特徵先寫假設**：它代表什麼機制、推論時何時取得？結束於 ablation 證據。沒有穩定改善、無法解釋或無法線上重建的特徵就刪除。
3. **保存完整 pipeline，不是只存 model。** 推論才能重現相同處理。

**Gate 2**：Pipeline 可在 raw-like DataFrame 上直接 fit/predict，`cross_validate` 不需要任何預先 fit 的外部物件；序列化後預測一致；未知類別、全空欄、單列 batch 都有 smoke test。

---

## Stage 4 — Baseline 與候選模型

**Baseline 不是初學者模型，是每次改動的品質底線。**

依序建立：Dummy（mean/median/most_frequent 或現行業務規則）→ 線性 → 稀疏 → tree。保存 fold scores、OOF、training time、model size、segment metrics。

複雜模型若只微幅領先、variance 更大或成本更高 → **問題可能在資料與驗證，不是模型不夠高階**。

候選集原則：**3–5 個有不同 inductive bias 的模型**，不要把所有套件都跑一遍。至少保留一個線性與一個 boosting。比較 OOF 誤差**相關性**——ensemble 需要 error diversity，不是模型名字多。

**Gate 3**：Champion 改善**大於 fold/seed noise**，關鍵 segment 沒有無法接受的退化。否則視為未證實。

---

## Stage 5 — 優化迴圈

**把每次優化變成可追蹤的小實驗，而不是同時修改資料、特徵、模型與 folds。**

```
檢查殘差 / segment / learning curve
  → 寫一個假設
  → 只改一個主要因素
  → 用相同 folds + seeds 跑
  → 比較 OOF、std、segment、成本
  → accept / reject / revise
  → 記錄決策與 artifact
  → 重複，直到邊際收益 < 成本或風險上升
```

診斷優先序（P0 最高）：**leakage／split／schema 錯 → 停止優化先修驗證** · underfit → 特徵與容量 · overfit → 正則化與 split · 單一 segment 差 → 資料品質與 coverage · **改善只在 1 個 seed 出現 → 拒絕**。完整對照見 [`references/principles.md`](references/principles.md)。

**停止條件**：連續多輪改善小於 CV noise、成本明顯上升、segment 退化、或需求已達成。**更複雜不等於更專業。**

每個實驗填 Experiment Ledger（欄位見 [`references/delivery-and-ops.md`](references/delivery-and-ops.md)）：run_id、data hash、code/env、hypothesis、**唯一的主要改動**、evaluation、cost、decision。

### 調參與 ensemble 的兩條邊界

- **調參只能微調正確方向，不能修復錯誤的 target 或 leakage。**
- **Ensemble 只有在 outer/meta cross-fit 穩定勝出時才採用。** 拒絕複雜度也是成熟決策——simple blend 常更可靠。

---

## Stage 6 — 可解釋性與風險

**解釋的對象不是模型，是決策。** 方法選型、十個陷阱、穩定性檢查與交付格式見 [`references/interpretability.md`](references/interpretability.md)。

### 開始前先答四題

```
1 誰要看        監管者 / 領域專家 / 工程師 / 末端使用者
2 要回答什麼    「模型整體靠什麼」還是「這一筆為什麼」
3 看完做什麼決定 上線 / 人工複核 / 改特徵 / 申訴
4 需要因果嗎    需要的話，predictive importance 一律不夠
```

**第 3 題答不出來就不要做**——沒有驅動任何決定的解釋，產出的是一張沒人看的長條圖。

### 前置條件

**Gate 1 未過就不要做。** 解釋一個有 leakage 的模型，解釋出來的就是那個洩漏源。

反過來這是**發現 leakage 的好方法**：一個不該這麼重要的欄位排第一，通常是洩漏。

### 三條硬規則

1. **在 validation／OOF 上算，不是 train。** 在 train 上算的是模型記住了什麼。
2. **跨 folds／seeds 量 rank stability。** 跨 folds 就不穩的排序**不要報**——只說「沒有穩定的主導特徵」。
3. **重要性不是因果。** 只能寫「模型依賴 X」；要因果就走實驗設計。

### Global 與 Local 都要，語域要分開

只有 Global 回答不了客訴；只有 Local 看不出模型整體是否合理。

給誰看決定給什麼：**L1**（業務、監管）給 reason code 與 counterfactual · **L2**（領域專家）給特徵**家族**層級的貢獻與方向 · **L3**（工程）給完整 attribution 與方法參數。**直接把 SHAP 圖丟給業務方**是最常見的語域錯誤（`rules/register.md`）。

**Gate 3F**：方法與模型家族相符且參數已記錄 · 在 validation／OOF 上算 · 共線性按**群組**處理 · rank stability 已量化 · 至少 3 個 local 個案含可行動的 counterfactual · 至少三種失敗模式與受影響 segment · **報告中沒有未標記的因果措辭** · Model Card 的 `Limitations` 與 `Not intended` 已更新。

---

## Stage 7 — 封裝、上線、監控

細節見 [`references/delivery-and-ops.md`](references/delivery-and-ops.md)。

- **Final fit**：鎖定 champion config、資料版本、code commit 與 dependencies；依已確認策略在完整 training data fit；**禁止再看 frozen holdout 調參**。
- **交付 artifact**：完整 pipeline（transformers + estimator + threshold/calibrator）、run summary、OOF、feature manifest、inference contract、**可解釋性報告**、Model Card。
- **golden dataset regression test**：序列化前後 prediction 一致。
- **監控七類**：service、schema/quality、covariate drift、prediction drift、performance、concept drift、fairness。
- **任何 retrain 都是新 run，不覆蓋舊 model**；先 shadow/canary 再 promote。
- **沒有監控的模型不算 production-ready。**

**Gate 4**：乾淨環境能載入 artifact 並對 raw-like sample 產生符合 schema 的 prediction；hash、版本與 golden test 一致；dashboard、alert owner、retrain rule、fallback 與 rollback 演練都到位。

---

## 判斷原則

**完整的十二條判斷、Metric 選擇表與常見錯誤對照見 [`references/principles.md`](references/principles.md)。** 最常用的三條：

1. **驗證設計錯了，任何漂亮分數都沒有意義。**
2. **Baseline 不是初學者模型，是每次改動的品質底線。**
3. **當改善小於噪音或維護成本時，停止就是最佳優化。** 更複雜不等於更專業。

> 成熟的 ML 工程不是找到最花俏的模型，而是讓每個資料與模型決策都有**可信驗證、可重現紀錄與可回復邊界**。

## 與其他能力的關係

- 每個結論帶證據等級（`rules/evidence-grades.md`）：CV 分數是**推論**（對未來資料的估計），frozen holdout 才更接近**已確認**。
- 目標值不值得做 → `se-feasibility`。
- 問題定義答不出七問 → `se-clarify` 設計樹模式。
- 實驗要平行跑 → `se-scheduling`，注意 GPU 與資料集是 **Connection Pool** 資源，同時只能一個持有。
- 撞到坑 → `se-epiphany` 寫 Lesson，尤其是 `dead_end`（試過 A、因為 B 不行）。

## 完成條件

- 七問已答，Gate 0 的 Problem Statement 已寫。
- fold assignment 已保存且可用程式重建；leakage 測試通過。
- Pipeline 可在 raw input 上 fit/predict，序列化後預測一致。
- Champion 的改善大於 fold/seed noise，且有 segment 檢查。
- Experiment Ledger 每個 run 都有唯一的主要改動與決策。
- 可解釋性報告含 Global／Local、rank stability 與至少三種失敗模式，且無未標記的因果宣稱。
- Model Card、inference contract、golden test、rollback 路徑齊備。
