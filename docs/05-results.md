# 05 — 結果

> 表格由 `python -m thermoforge.report --update docs/05-results.md` 從
> `runs/ledger.jsonl` 與 `runs/frozen_ledger.jsonl` 產生。**不要手改表格**——
> 手寫的數字會過期，而過期的數字看起來跟正確的一模一樣。

## 怎麼讀這些數字

| 欄 | 是什麼 | 陷阱 |
|---|---|---|
| **OOF field MAE** | 整場平均誤差，五折 out-of-fold | 整場很低不代表熱點準——熱點只佔 4096 格裡的一格 |
| **OOF Tmax MAE** | 熱點溫度誤差 | 決策真正看的那個數字 |
| **Tmax bias** | 平均的 (預測 − 真值)。**負數 = 系統性低估** | 低估是貴的那一側（問題定義第 5 題） |
| **低估率** | 低估超過 1 °C 的樣本比例 | 對稱指標看不到它。**任何回報都必須帶這一欄** |
| **池內 recall@10/60** | **主要 metric**。候選池內只有佈局在變 | 機會水準是 0.167。低於 0.2 等於沒有篩選能力 |
| **推論 ms/佈局** | 批次推論的每筆時間 | 求解器本身是 0.263 ms，見 [02-solver.md](02-solver.md) 的誠實段落 |

**所有 OOF 數字都是「推論」等級**（對未見資料的估計），只有 frozen holdout 那一段
更接近「已確認」。這是 `.claude/rules/evidence-grades.md` 對 CV 分數的定位。

<!-- BEGIN generated:results -->
<!-- END generated:results -->

## 判定

見下方各節。判定的依據是 `se-ml-lifecycle` Gate 3：
**改善必須大於 fold/seed 噪音，且關鍵 segment 沒有不可接受的退化。**
