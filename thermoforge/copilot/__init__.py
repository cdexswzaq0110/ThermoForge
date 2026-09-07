"""設計副駕：自然語言 → 結構化設計查詢 → 代理模型評估 → **帶證據等級的回答**。

## 這一層的唯一規則

**副駕不產生任何沒有代理模型支撐的數字。**（`CLAUDE.md` 預設節奏第 5 條）

語言模型在這裡只做一件事：把「CPU 拉到 60 W 還安全嗎」翻成
`DesignQuery(action=what_if, component=CPU, set_power=60)`。溫度、餘裕、建議
全部來自一次實際的 `Predictor.predict` 呼叫，並且要通過分佈內檢查才會被當成數字報出去。

推出訓練分佈的查詢**不會**得到一個比較不確定的數字，會得到「未驗證」與
「這題要送 CFD」。這不是保守，是 `.claude/rules/evidence-grades.md` 說的
「沒有新證據不得把推論寫成已確認」——外推區沒有證據，任何數字都是編的。

## 兩個解析後端

| 後端 | 何時 | 狀態 |
|---|---|---|
| `RuleBasedParser` | 預設，離線可跑 | 已確認：`tests/test_copilot.py` 覆蓋 |
| `LLMParser` | 有 `ANTHROPIC_API_KEY` 時 | **未驗證**：本機沒有 key，這條路徑從未實際執行過 |

沒有 key 時退化成規則解析，**不是**改成讓語言模型自己猜溫度。
"""

from .answer import Answer, answer_query
from .board import ReferenceBoard, load_board
from .query import DesignQuery, RuleBasedParser, parse

__all__ = [
    "Answer",
    "answer_query",
    "ReferenceBoard",
    "load_board",
    "DesignQuery",
    "RuleBasedParser",
    "parse",
]
