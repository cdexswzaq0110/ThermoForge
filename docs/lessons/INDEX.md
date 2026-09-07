# 領悟帳本索引

**一則一行。內容留在各自的檔案裡。**

這份索引每次召回都會被讀，長度就是成本。維護方式見
[`.claude/skills/se-epiphany`](../../.claude/skills/se-epiphany/SKILL.md)。

繼承自 Serendipity 的五則（L0001–L0005）留在那個 repo，本檔只記本專案撞出來的。
其中 L0002 與 L0005 在這一輪都被引用過——分別是
「gate 的預設失敗模式是靜默放行」與「第一個嫌疑犯是你的判定條件」。

## 現行

| ID | 一句話 | tags | outcome | hits |
|---|---|---|---|---|
| [L0001](0001-metric-saturation-needs-a-cheating-baseline.md) | 決策型指標定案前先寫一個作弊 baseline 去打它 | metric, 評估設計 | useful | 0 |
| [L0002](0002-physical-plausibility-belongs-in-the-parameterisation.md) | 合成資料的合理性在參數化裡解決，過濾會洩漏 target | 合成資料, 取樣設計 | useful | 0 |
| [L0003](0003-bootstrap-template-and-checker-disagree.md) | Serendipity 的 CONTEXT 模板過不了自己的驗收腳本 | serendipity, 上游缺陷 | useful | 0 |
| [L0004](0004-integral-properties-are-learned-local-ones-are-not.md) | 代理模型學得到積分性質，學不到局部微分性質 | physics-ml, 代理模型 | useful | 0 |
| [L0005](0005-a-project-does-not-modify-its-tooling.md) | 專案 session 不改工具 repo，即使缺陷是在這裡撞到的 | 邊界, 上游, 授權 | corrected | 0 |

## 已升級（`outcome: promoted`）

| ID | 升級到哪 | 日期 |
|---|---|---|
| — | — | — |

## 已封存

| ID | 原因 | 取代者 |
|---|---|---|
| — | — | — |

---

## 統計

- 現行：5 則
- 距離下次回顧：15 則（滿 20 則觸發）
- `no-trigger`（沒填失效條件）：0 則
