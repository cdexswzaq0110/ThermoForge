# 特徵、Pipeline、候選模型與評估

Gate 2D–3E 的細節。

---

## 1. 特徵工程

**用少量可解釋、可驗證、推論時可取得的特徵，降低模型自己發現關係的難度。**

| 家族 | 例子 | 風險／驗證 |
|---|---|---|
| 總量 | 總面積、總消費、總互動次數 | 避免重複計算或混入未來期間 |
| 比率 | 價格/面積、成功/嘗試、負債/收入 | 分母 0、極小值與截尾 |
| 時間差 | 帳戶年齡、距上次事件天數 | **reference time 必須是 prediction time** |
| 交互作用 | 品質×面積、方案×用量 | 高維爆炸；以假設與 ablation 篩選 |
| 狀態旗標 | HasGarage、IsNew、曾逾期 | 定義要穩定且可在線重建 |
| 群組聚合 | 客戶歷史平均、區域中位數 | **只能用當時可見的歷史**；用 OOF 建立 |
| 循環特徵 | sin/cos（月、星期、時間） | 先確認週期真的存在 |
| 類別有序副本 | 品質等級 → ordinal | 順序須由業務定義，不可亂編碼 |

### Feature SOP

1. **先寫假設**：這個特徵代表什麼機制？推論時何時取得？
2. 在 transformer 內實作 `fit/transform`；任何統計只在 training fold 建立。
3. 為除零、空值、未見 category 與日期邊界加入明確處理。
4. 建立 **feature manifest**：名稱、公式、來源、owner、online availability。
5. 用 **OOF ablation** 比較 baseline vs +feature family；保存 mean、std 與 segment 變化。
6. 沒有穩定改善、無法解釋或無法線上重建的特徵**就刪除**。

**Gate 2D**：每個正式特徵都有公式、資料來源、prediction-time 可用性與 ablation 證據；沒有 train/serve skew。

---

## 2. Pipeline

把 feature engineering、imputation、encoding、scaling 與模型封裝成**同一個可序列化 estimator**。

| 欄位類型 | 標準路徑 | 何時調整 |
|---|---|---|
| 穩定 numeric | median → scaler | tree 通常不需要 scale |
| 正偏且非負 | median → log1p → scaler | 含負值需 Yeo-Johnson |
| 有強 outlier | median → RobustScaler / clipping | clipping 門檻只由 train fold 學 |
| 低/中基數 category | mode/Missing → OneHot(handle_unknown) | 稀有類用 min_frequency |
| 高基數 category | native categorical、hashing、OOF target encoding | 嚴格防 leakage，評估記憶體 |
| ordinal | 明確順序映射 + unknown policy | 可同時保留 one-hot 供不同模型使用 |

- **Column list 若依統計或 cardinality 決定，也必須在 fold 內建立。**
- **保存完整 pipeline，不是只存 model。**
- 確認 sparse/dense 相容性、欄位順序與特徵名稱輸出。
- 對 unseen category、全空欄、單列 batch、多列 batch 寫 smoke test。

**Gate 2E**：Pipeline 可在 raw-like DataFrame 上直接 fit/predict，交叉驗證不需要任何預先 fit 的外部物件；序列化後預測一致。

---

## 3. Baseline

依序建立，**每一層都保存 fold scores、OOF、training time、model size、segment metrics**：

1. **Dummy**：mean/median、most_frequent，或現行業務規則
2. **Linear**：Ridge / Logistic —— 檢查 one-hot、scale 與線性訊號
3. **Sparse**：Lasso / Elastic Net —— 觀察正則化與特徵稀疏性
4. **Tree**：Random Forest / Extra Trees 或小型 boosting —— 確認非線性空間

**Gate 3A**：Baseline 全流程可重現，OOF 覆蓋每列且無 NaN；模型明顯優於 Dummy 與現行規則。否則**回到問題與資料**，不要往下調參。

---

## 4. 候選模型

| 模型家族 | 適用 | 優點 | 主要風險 |
|---|---|---|---|
| Ridge / Logistic | 高維 one-hot、近線性、小中型 | 快、穩、可解釋 | 欠擬合非線性與交互作用 |
| Lasso / Elastic Net | 稀疏特徵與變數篩選 | 壓縮係數、低成本 | 共線特徵選擇不穩 |
| Random / Extra Trees | 非線性、快速 baseline | 少前處理、robust | 外插差、模型較大 |
| XGBoost / LightGBM | 一般 tabular 強 baseline | 非線性、交互作用、效能高 | 小資料易過擬合，需調正則化 |
| CatBoost | 類別多或高基數 | native category、較少 encoding | 訓練成本與版本相容性 |
| SVR / Kernel Ridge | 小型資料、平滑非線性 | 不同誤差結構 | O(n²～n³)、scale 敏感 |
| GLM / Tweedie | count、rate、正值長尾 | 分布假設清楚 | 假設不合會偏誤 |
| Neural network | 資料量大、embedding、多模態 | 彈性與表示能力 | 小 tabular 常不划算 |

### 候選集原則

- 選 **3–5 個有不同 inductive bias** 的模型，不要把所有套件都跑一遍。
- 至少保留一個線性與一個 boosting；類別複雜時再加 CatBoost。
- **比較 OOF 誤差相關性**——ensemble 需要 error diversity，不是模型名字多。
- 同時比較 latency、memory、training cost、可解釋性與維護負擔。

**Gate 3B**：每個候選都有明確假設與成本預算；沒有提供分數、穩定性或誤差互補的模型不進 champion set。

---

## 5. CV / OOF 評估紀律

| 層級 | 必看 | 用途 |
|---|---|---|
| Overall | OOF primary metric、fold mean/std | 模型主比較 |
| Seeds | 不同 seed 的 mean/std、排名穩定性 | 估計 split variance |
| Segments | 價位、區域、客群、時間、缺失程度 | 發現局部退化 |
| Residual | bias、heteroscedasticity、大誤差案例 | 產生下一個特徵/損失假設 |
| Operations | latency、memory、coverage | 確認可部署 |

- 比較模型時用**相同 folds**；paired fold difference 比兩組獨立平均更有資訊。
- classification 的 **threshold 必須在 validation/OOF 選**；test/未來資料不能調 threshold。
- 決策重視機率時，另檢查 calibration curve、Brier score 與 ECE。

**Gate 3C**：Champion 改善大於 fold/seed noise，關鍵 segment 無法接受的退化不存在。否則視為未證實。

---

## 6. 調參

**有邊界、有預算、有驗證。**

1. 先確認 feature set、loss、split 與模型家族——**不要用調參掩蓋資料問題**。
2. 用 learning curve / overfitting gap 判斷該增加容量還是正則化。
3. 先粗範圍 Random Search / Optuna，再縮小；連續參數多用 log scale。
4. 每個 trial 完整走 fold-local pipeline；用 early stopping 時只看該 fold 的 validation。
5. 保留 search space、sampler seed、trial history、最佳與**次佳**區域。
6. 最後用 nested CV 或 frozen holdout 驗證整個選參流程。

**預算規則**：先給每個模型固定 trial/時間預算；只有穩定進入前段的模型才加碼。完整 nested tuning 很貴，**至少保留 frozen holdout 作誠實 Gate**。

**Gate 3D**：調參結果在多 folds/seeds 或 frozen evaluation 仍成立；search history 已保存，**沒有只報 best trial**。

---

## 7. Ensemble 與校準

**只有在 OOF 顯示穩定互補、且嚴格 meta evaluation 通過時，才增加第二層複雜度。**

1. 檢查候選 OOF 殘差相關性；高度相似的模型不必全留。
2. 先做固定平均，或非負、總和為 1 的 OOF weighted blend。
3. 用 meta cross-fit 學權重：meta-train 學 blend，meta-valid 評估。
4. **Stacking 的 base predictions 必須是 OOF**；stacker 也需要外層 cross-fit。
5. classification 機率校準用 Platt / Isotonic，仍須 cross-fit。

| 方法 | 複雜度 | 採用條件 |
|---|---|---|
| Simple mean | 低 | 模型尺度一致且互補 |
| Non-negative weighted blend | 低～中 | cross-fit 優於最佳單模且權重穩定 |
| Linear calibration | 中 | 獨立 meta folds 改善 bias |
| Ridge / linear stacking | 中 | 外層 cross-fit 穩定勝出 |
| Nonlinear stacker | 高 | 資料量足、嚴格 nested evaluation、明顯增益 |

**Gate 3E**：Ensemble 在 outer/meta cross-fit 穩定改善、權重不劇烈漂移、成本可接受。否則**回退最佳單模或 simple blend——拒絕複雜度也是成熟決策**。

---

## 8. 可解釋性與風險

**完整方法選型、十個陷阱、穩定性檢查與交付格式見 [`interpretability.md`](interpretability.md)。**

三條在這裡就要記住的：

1. **在 validation／OOF 上算，不是 train。** 在 train 上算的是模型記住了什麼。
2. **跨 folds／seeds 量 rank stability。** 不穩定的排序不是結論，是一張圖。
3. **重要性是模型行為，不是因果證據。** 不可寫「此特徵造成結果」。

前置條件：**Gate 1 未過就不要做這一步**——解釋一個有 leakage 的模型，解釋出來的就是那個洩漏源。

**Gate 3F**：見 `interpretability.md` 的完整檢查表。核心是能指出至少三種主要失敗模式、受影響 segment 與樣本量，且報告中沒有未標記的因果措辭。
