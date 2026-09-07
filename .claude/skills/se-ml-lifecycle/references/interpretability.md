# 模型可解釋性（Interpretability）

**解釋的對象不是模型，是決策。** 沒有指定讀者與用途的解釋，產出的是一張沒人看得懂的長條圖。

前置條件：**解釋一個驗證設計錯誤的模型，只會解釋它的 leakage。** Gate 1 未過就不要做這一步。

---

## 一、先問四題

| # | 問題 | 答錯的後果 |
|---|---|---|
| 1 | **誰要看？** 監管者／領域專家／工程師／末端使用者 | 給錯語域，對方看不懂或不能用 |
| 2 | **要回答什麼？** 「模型整體靠什麼」還是「這一筆為什麼是這個結果」 | Global 方法回答不了 Local 問題 |
| 3 | **看完要做什麼決定？** 上不上線／要不要人工複核／要不要改特徵／要不要申訴 | 產出無法驅動任何決定 |
| 4 | **需要因果嗎？** | **predictive importance 永遠不是因果**，需要因果就要另做實驗設計 |

### 語域對照（見 `rules/register.md`）

| 層 | 讀者 | 該給什麼 | 不該給什麼 |
|---|---|---|---|
| **L1** | 業務、末端使用者、監管 | Reason code、對比說明（「若收入再高 X，結果會翻轉」） | SHAP 數值、特徵名 |
| **L2** | 領域專家、審查者 | 特徵家族層級的貢獻、方向、與領域知識是否相符 | 原始 one-hot 欄位 |
| **L3** | 工程、資料科學 | 完整 attribution、rank stability、背景資料設定、方法參數 | — |

**L1 與 L3 之間唯一合法的通道是 L2。** 直接把 SHAP 圖丟給業務方是常見錯誤。

---

## 二、兩個層次

| | Global | Local |
|---|---|---|
| 問題 | 模型**整體**依賴什麼 | **這一筆**為什麼是這個結果 |
| 用途 | 特徵取捨、發現 leakage、與領域知識對照 | 人工複核、客訴回覆、申訴、除錯單筆 |
| 方法 | permutation importance、SHAP 全域彙總、PDP | SHAP local、LIME、counterfactual |
| 陷阱 | 平均會蓋掉 segment 差異 | 單筆解釋不能推論到全體 |

**兩個都要。** 只有 Global 無法回答客訴；只有 Local 看不出模型整體是否合理。

---

## 三、方法選型

### 依模型家族

| 模型 | 首選 | 為什麼 | 注意 |
|---|---|---|---|
| 線性／GLM | 係數 ＋ 標準化後的效應量 | 本身就是解釋 | 必須先 scale；one-hot 有 baseline 類別；共線性會讓係數不穩甚至變號 |
| 樹／Boosting | **TreeSHAP** | 精確、快 | `feature_perturbation` 選 `tree_path_dependent` 或 `interventional` **會得到不同答案**，要記錄選了哪個 |
| 任何模型 | Permutation importance | 模型無關、直接連到 metric | 在 **validation** 上做，不是 train；共線特徵會互相掩蓋 |
| 任何模型 | KernelSHAP | 模型無關 | 慢、且是近似；大資料要抽樣 |
| 黑箱 | Global surrogate | 用可解釋模型近似 | **必須報 fidelity**（surrogate 對原模型的 R²／accuracy）。fidelity 低的 surrogate 是在解釋另一個模型 |

### 依問題

| 你想知道 | 用 |
|---|---|
| 哪些特徵重要 | Permutation importance（連到 metric）＋ SHAP 全域（連到預測） |
| 特徵怎麼影響預測 | PDP（平均）＋ ICE（個體，看異質性） |
| 這一筆為什麼 | SHAP local ＋ 排序後的 top-k reason code |
| 要改什麼才會翻轉 | **Counterfactual／actionable recourse** |
| 模型在哪裡系統性出錯 | **Residual slices** — 通常最能產生下一個工程假設 |
| 兩個特徵有沒有交互 | SHAP interaction values ＋ 2D PDP |

---

## 四、十個陷阱

這一節是本文件最重要的部分。以下每一條都會產出「看起來很專業但錯誤」的結論。

1. **重要性不是因果。**
   模型依賴 X，不代表 X 造成 Y。可能 X 是 Y 的代理、下游結果，或共同原因的產物。
   → 措辭只能寫「模型依賴」，要因果就走實驗設計。

2. **共線特徵會分散重要性。**
   兩個相關性 0.95 的特徵，permutation importance 可能各自都接近 0——打亂一個，另一個補上了。
   → 先做特徵分群，對**群組**做 permutation，不要對單欄下結論。

3. **在 train 上算 importance。**
   會反映模型記住了什麼，不是它學到什麼。
   → **一律在 validation／OOF 上算。**

4. **PDP 在相關特徵下會造出不存在的樣本。**
   固定「坪數 = 200」掃過「房間數 = 1」，這種組合現實中不存在，模型在那裡的輸出沒有意義。
   → 檢查 PDP 掃過的區域是否有真實資料支撐；相關特徵改用 ALE 或限制在資料支撐區間。

5. **SHAP 的背景資料集會改變答案。**
   background 用全體、用某個 segment、用 zero baseline，得到的 attribution 不同。
   → **記錄 background 怎麼選的**，並在報告中說明。

6. **只報 `mean(|SHAP|)` 會丟掉方向。**
   一個特徵對一半的人是正貢獻、對另一半是負貢獻，取絕對值平均後看起來「很重要」，但你不知道它在做什麼。
   → 同時報方向分布，或直接看 beeswarm。

7. **單一模型的 importance 不穩定。**
   換個 seed、換個 fold，排序可能大幅改變。
   → **跨 folds／seeds 算 rank stability**，只報穩定的部分。

8. **解釋了一個無效的模型。**
   有 leakage 的模型，解釋出來的「重要特徵」就是那個洩漏源。
   → 這其實是**發現 leakage 的好方法**：一個不該這麼重要的欄位排第一，通常是洩漏。

9. **Post-hoc 解釋不等於模型真的那樣運作。**
   SHAP 是一個歸因框架的輸出，不是模型內部機制的實錄。兩個不同方法給出不同解釋是正常的。
   → 高風險場景優先選**本質可解釋**的模型，而不是黑箱＋事後解釋。

10. **拿全域解釋回答個案。**
    「整體來說收入最重要」回答不了「為什麼拒絕我」。
    → 個案要用 local ＋ counterfactual。

---

## 五、穩定性檢查（不做就不要報）

```
對每個候選解釋：
  1. 跨 folds 重算 → 前 10 名的 rank correlation（Spearman）
  2. 跨 seeds 重算 → 同上
  3. 分 segment 重算 → 主要 segment 的排序是否一致
  4. 換一種方法重算 → permutation vs SHAP 的前 5 名是否重疊
```

判準：

| 觀察 | 結論 |
|---|---|
| 跨 folds rank correlation 高、跨方法前 5 名重疊 | 可以報【已確認】 |
| 跨 folds 穩定但跨方法不一致 | 報【推論】，並說明兩種方法各自給了什麼 |
| 跨 folds 就不穩 | **不要報排序**。只說「沒有穩定的主導特徵」【已確認：跨 5 folds rank correlation 0.2】 |
| 只跑過一次 | 【未驗證】——這不是結論，是一張圖 |

---

## 六、證據等級怎麼掛（見 `rules/evidence-grades.md`）

```
模型主要依賴 loan_amount 與 credit_history
  【已確認：permutation importance on OOF，5 folds × 3 seeds，
   前 3 名 rank correlation 0.91，指令與輸出見 artifacts/run_0042/】

高負債比會提高違約預測值
  【推論：SHAP 在該區間單調上升，但未排除與收入的交互作用】

降低負債比可以降低實際違約率
  【候選 — 這是因果宣稱，predictive importance 無法支持。
   需要 A/B 或準實驗設計】

模型對 45 歲以上族群的解釋是否穩定
  【未知：該 segment OOF 樣本僅 87 筆，rank 不可信】
```

**最常見的錯誤是把第三行寫成第一行的語氣。**

---

## 七、法規與高風險場景

需要時才做，不要在雛型期前置。

| 情境 | 需要什麼 |
|---|---|
| 信用、雇用、保險等受規範決策 | 個案層級的 **reason code**（可讀、可申訴），以及模型不使用受保護屬性的證據 |
| 需要說明「為什麼被拒」 | Local 解釋 ＋ **counterfactual**（要改什麼才會翻轉），而且建議必須**可行動**（不能說「請降低年齡」） |
| 公平性審查 | 分群體的錯誤率、coverage、校準差異，而不只是整體 metric |
| 人工複核流程 | 解釋要能在複核者的時間預算內看完——通常是 **top-3 reason code**，不是完整 SHAP 圖 |

**受保護屬性的代理變數是重點**：拿掉性別欄位不代表模型沒用到性別，郵遞區號可能就是。檢查方式是看是否能從其餘特徵預測出受保護屬性。

---

## 八、交付物

一份可解釋性報告至少包含：

```markdown
## 方法與設定
- 模型家族、解釋方法、版本
- SHAP background 資料集怎麼選、feature_perturbation 設定
- 在哪一份資料上算（OOF／validation／frozen holdout）

## Global
- 前 10 特徵 ＋ 方向 ＋ 跨 folds/seeds 的 rank stability【證據等級】
- 與領域知識相符或衝突的地方（衝突通常是最有價值的發現）
- 特徵群組層級的結果（處理共線性後）

## Local
- 至少 3 個代表性個案：一個典型、一個邊界、一個大誤差
- 每個附 top-k reason code 與 counterfactual

## 失敗模式
- 至少三種：什麼樣的輸入會讓模型錯，錯的方向是什麼
- 受影響 segment 與樣本量

## 不適用範圍
- OOD 條件、低 coverage 區間、不該拿來做的決策

## 不能宣稱的
- 明確寫出：本報告不建立任何因果關係
```

同步寫入 **Model Card** 的 `Not intended`、`Limitations`、`Features` 三節。

---

## Gate 3F（強化版）

以下**全部**成立才算通過：

- [ ] Gate 1 已過（**解釋一個無效模型沒有意義**）
- [ ] 解釋方法與模型家族相符，且方法參數（background、perturbation 模式）已記錄
- [ ] Global importance 在 validation／OOF 上計算，**不是 train**
- [ ] 已做共線性處理：對特徵**群組**下結論，不對單欄
- [ ] 跨 folds／seeds 的 rank stability 已量化，不穩定的部分沒有被報成結論
- [ ] 至少 3 個 local 個案，含 counterfactual，且建議可行動
- [ ] 能指出**至少三種主要失敗模式**、受影響 segment 與樣本量
- [ ] 報告中**沒有任何因果措辭**，或因果宣稱明確標為【候選】並說明需要什麼實驗
- [ ] Model Card 的 `Limitations` 與 `Not intended` 已更新
