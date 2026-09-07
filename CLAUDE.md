# ThermoForge

**板級熱設計的秒級代理模型，外加一個不替你編數字的 LLM 設計副駕。**

一塊 PCB 的元件功率佈局進去，穩態溫度場出來。用神經代理模型取代每改一次佈局就要重跑一次的
數值求解，讓「換個位置再看一次」從一天試五個方案變成一分鐘掃上千個方案。

上面疊一層 LLM：把「CPU 拉到 250W 還安全嗎」翻成代理模型看得懂的查詢，跑完之後
**帶著證據等級回答**——落在訓練分佈內就給數字與區間，超出去就明說「未驗證，這題要送 CFD」。

## 證據邊界（先讀這一條）

訓練資料由本 repo 內建的**二維穩態熱傳導有限差分求解器**生成，不是 CFD。
它不解流場、不算輻射、不做暫態、不處理三維堆疊。

因此本專案能證明的是「代理模型學不學得會這個求解器、在分佈外會不會崩、崩在哪」，
**不是**「能不能取代 FloTHERM／Icepak」。任何把後者寫進結論的說法都是越界，
在 review 時視為缺陷而不是行銷語言。

## 這一輪要做什麼 → 去哪

| 要知道什麼 | 去哪 |
|---|---|
| 這個問題為什麼值得建模、target／metric／不做範圍 | [docs/01-problem-statement.md](docs/01-problem-statement.md) |
| 求解器在解什麼方程、離散化與收斂判準 | [docs/02-solver.md](docs/02-solver.md) |
| 資料契約、split 策略、leakage 防線 | [docs/03-data-contract.md](docs/03-data-contract.md) |
| ML 流程本身怎麼跑（七階段六道 Gate） | `.claude/skills/se-ml-lifecycle` |
| 怎麼跑一輪工作、派給誰、怎麼收尾 | [.claude/RUNBOOK.md](.claude/RUNBOOK.md) |
| 專案詞彙的精確定義 | [CONTEXT.md](CONTEXT.md) |
| 這一輪撞出來的領悟 | [docs/lessons/INDEX.md](docs/lessons/INDEX.md) |

## 預設節奏

只列**與模型預設行為不同**的六條。通用工程紀律在 `.claude/rules/`，不在這裡重複。

1. **這是物理問題，baseline 就要是物理解。** 品質底線不是「預測訓練集平均場」，是
   Green's function 疊加這種解析近似。贏不過物理近似的神經網路不叫成果。
2. **報任何分數都要指名 split。** 本專案有兩層：`id-val`（同分佈，可反覆看，用來調參）與
   `ood-holdout`（功率／元件數／板型超出訓練範圍，**整個專案只解凍一次**）。
   不指名 split 的分數等於沒有分數。
3. **所有 fit 型處理只能在 training fold 內**——正規化常數、統計量、PCA、閾值全部包含。
   全資料先 fit 是本專案最可能的 leakage 來源，因為場資料看起來「沒有欄位可洩漏」。
4. **同一個 base layout 衍生的樣本必須同組。** 一個佈局會用不同對流係數 h 生成多筆，
   隨機切分會把兄弟樣本拆到兩邊 → 用 `GroupKFold(groups=base_layout_id)`。
5. **LLM 層不得產生沒有代理模型支撐的數字。** 溫度、餘裕、建議都必須來自一次實際的
   surrogate 呼叫，並附上該 regime 的不確定度與是否在訓練分佈內。
   沒有 API key 時退化成 rule-based parser，**不是**改成讓模型自己猜。
6. **Windows：不要用 PowerShell 讀寫含中文的原始碼。** 會雙重編碼且不可逆
   （見 `.claude/` 繼承的 L0004）。用 Edit／Write 工具或 Bash heredoc。

先雛型 → 打掉 → 重構是正常路徑。衝突時使用者的直接要求與 `.claude/rules/core-rules.md` 優先。

## 環境查不到的指令

```bash
uv venv --python 3.11              # .venv/Scripts/python（Windows 是 Scripts 不是 bin）
uv pip install -r requirements.txt
```

Windows 主控台預設 cp950，跑任何會印中文的指令前加 `PYTHONIOENCODING=utf-8`
（檔案是 UTF-8，壞的只有顯示，但看不懂的錯誤訊息會浪費一輪除錯）。

| 要做什麼 | 指令 |
|---|---|
| 跑測試 | `.venv/Scripts/python -m pytest -q` |
| 生資料集 | `.venv/Scripts/python -m thermoforge.data.generate --config configs/dataset_v1.yaml` |
| 生篩選候選池 | `.venv/Scripts/python -m thermoforge.data.pools --config configs/pools_v1.yaml` |
| 快取物理基準場 | `.venv/Scripts/python -m thermoforge.precompute_greens --data data/processed/v1.npz` |
| 跑全部實驗 | `bash scripts/run_experiments.sh` |
| 跑一次實驗 | `.venv/Scripts/python -m thermoforge.experiments --model unet --variant residual --hypothesis ... --change ...` |
| 定版 champion | `.venv/Scripts/python -m thermoforge.champion --variant residual` |
| 解凍 frozen holdout | `.venv/Scripts/python -m thermoforge.frozen --confirm` |
| 設計副駕 | `.venv/Scripts/python -m thermoforge.copilot --demo` |

`--confirm` 不是禮貌性確認，是第 2 條的機械化：holdout 每被解凍一次就寫一筆到
`runs/frozen_ledger.jsonl`，超過一次就要在 PR 裡解釋為什麼。

`--hypothesis` 與 `--change` 是必填，理由見 `thermoforge/experiments.py`。
