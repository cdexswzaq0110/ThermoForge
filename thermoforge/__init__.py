"""ThermoForge — 板級熱設計的秒級代理模型。

模組邊界（`CONTEXT.md` 的詞彙對應）：

    geometry  佈局 → 功率圖
    solver    功率圖 → 溫度場（ground truth）
    baselines 功率圖 → 溫度場（物理近似，代理模型的品質底線）
"""

__version__ = "0.1.0"
