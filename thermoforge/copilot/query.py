"""自然語言 → `DesignQuery`。

## 解析失敗要說出來，不要補完

`unparsed` 欄位存在的理由：使用者說「把顯卡拉到 60W」而板上沒有叫顯卡的元件時，
正確行為是回報「不認得『顯卡』」，不是挑一個最像的元件然後算出一個**正確的、
但回答了另一個問題**的數字。後者比錯誤答案更難發現。

## 兩個後端

- `RuleBasedParser`：正規表達式。離線、決定性、有測試覆蓋。**預設**。
- `LLMParser`：用 Anthropic tool-use 取結構化輸出。處理得了規則寫不完的說法
  （「散熱片再大一號」「兩顆一起降 20%」）。

`LLMParser` 在本機**從未實際執行過**——沒有 API key【已確認：env 只有
ANTHROPIC_BASE_URL，沒有 ANTHROPIC_API_KEY】。所以它的狀態是**未驗證**，
而不是「應該可以動」。`parse()` 沒有 key 時直接走規則後端。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

__all__ = ["DesignQuery", "RuleBasedParser", "LLMParser", "parse", "QUERY_SCHEMA"]

_NUM = r"(\d+(?:\.\d+)?)"

_OPTIMIZE = re.compile(
    r"(優化|最佳化|重新排|重排|換個?位置|挪|搬|找.{0,4}佈局|optimi[sz]e|rearrange|relayout)",
    re.I,
)
_TO = r"(?:拉到|提高到|提升到|調到|改成|設成|升到|加到|增加到|降到|減到|to)"
# 「從 25.5W 拉到 60W」有兩個數字，目標是**後面**那個。先找帶「拉到」的，
# 找不到才退回單一數字。這是模組 docstring 說的那類錯誤的具體防線：
# 取錯數字會得到一個正確計算、卻回答了現況而不是提問的答案。
_POWER_TO = re.compile(rf"{_TO}\s*{_NUM}\s*(?:w\b|瓦|watt)", re.I)
_POWER = re.compile(rf"{_NUM}\s*(?:w\b|瓦|watt)", re.I)
_H_CONV = re.compile(rf"(?:h\s*=\s*|對流(?:係數)?\s*(?:提高到|拉到|改成|設成|到)?\s*){_NUM}", re.I)
_T_AMB = re.compile(rf"(?:環境溫度|機殼溫度|ambient)\s*(?:提高到|拉到|改成|到)?\s*{_NUM}", re.I)
_LIMIT = re.compile(
    rf"(?:不(?:能|得|可)超過|上限|限制在|最高|must stay under|below|<=?)\s*{_NUM}\s*(?:°|度|c\b)?",
    re.I,
)
_FAN_UP = re.compile(r"(風扇(?:轉速)?(?:加強|提高|開大|拉高)|加強散熱|better cooling|more airflow)", re.I)


@dataclass(frozen=True)
class DesignQuery:
    """一次設計提問的結構化形式。**所有數值都是輸入，沒有一個是答案。**"""

    action: str = "evaluate"  # evaluate | what_if | optimize
    component_index: int | None = None
    component_name: str | None = None
    set_power: float | None = None
    set_h_conv: float | None = None
    set_t_amb: float | None = None
    t_max_limit: float | None = None
    raw: str = ""
    parser: str = "rule"
    unparsed: tuple[str, ...] = field(default_factory=tuple)

    @property
    def changes_anything(self) -> bool:
        return any(
            v is not None for v in (self.set_power, self.set_h_conv, self.set_t_amb)
        )


#: 給 LLM 後端的工具 schema。與 `DesignQuery` 的欄位一一對應——
#: 兩邊漂掉的話，語言模型會回傳一個解析得了但意義不同的物件。
QUERY_SCHEMA = {
    "name": "design_query",
    "description": "把一句熱設計提問轉成結構化查詢。不要回答問題，只做轉換。",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["evaluate", "what_if", "optimize"]},
            "component_name": {"type": "string", "description": "元件名稱，原文提到的那個"},
            "set_power": {"type": "number", "description": "把該元件功率改成幾瓦"},
            "set_h_conv": {"type": "number", "description": "把對流係數改成多少 W/m^2K"},
            "set_t_amb": {"type": "number", "description": "把環境溫度改成幾度 C"},
            "t_max_limit": {"type": "number", "description": "熱點溫度上限（度 C）"},
        },
        "required": ["action"],
    },
}


class RuleBasedParser:
    """正規表達式解析。看不懂的片段一律進 `unparsed`。"""

    name = "rule"

    def parse(self, text: str, board) -> DesignQuery:
        raw = text.strip()
        unparsed: list[str] = []

        # 元件：掃過板上每個名字與別名，取最早出現的那一個。
        hit_index, hit_name, hit_pos = None, None, len(raw) + 1
        lowered = raw.lower()
        for i, nc in enumerate(board.components):
            for token in (nc.name.lower(), *nc.aliases):
                pos = lowered.find(token)
                if 0 <= pos < hit_pos:
                    hit_index, hit_name, hit_pos = i, nc.name, pos

        set_power = None
        m = _POWER_TO.search(raw) or _POWER.search(raw)
        if m:
            if hit_index is None:
                unparsed.append(f"看到功率 {m.group(1)} W，但沒認出是哪個元件")
            else:
                set_power = float(m.group(1))

        set_h = None
        m = _H_CONV.search(raw)
        if m:
            set_h = float(m.group(1))
        elif _FAN_UP.search(raw):
            # 「加強散熱」沒有數字。**不要自己編一個倍率**——問清楚比猜便宜。
            unparsed.append("「加強散熱」沒有給對流係數，需要一個數字（h，W/m^2K）")

        set_t_amb = None
        m = _T_AMB.search(raw)
        if m:
            set_t_amb = float(m.group(1))

        limit = None
        m = _LIMIT.search(raw)
        if m:
            limit = float(m.group(1))

        if _OPTIMIZE.search(raw):
            action = "optimize"
        elif set_power is not None or set_h is not None or set_t_amb is not None:
            action = "what_if"
        else:
            action = "evaluate"

        return DesignQuery(
            action=action,
            component_index=hit_index,
            component_name=hit_name,
            set_power=set_power,
            set_h_conv=set_h,
            set_t_amb=set_t_amb,
            t_max_limit=limit,
            raw=raw,
            parser=self.name,
            unparsed=tuple(unparsed),
        )


class LLMParser:
    """Anthropic tool-use 後端。**未驗證：本機沒有 API key，這條路徑沒跑過。**

    只做「自然語言 → 結構化查詢」這一步。溫度、餘裕與建議一律不經過語言模型——
    那是 `answer.py` 用代理模型算出來的。
    """

    name = "llm"

    def __init__(self, model: str = "claude-sonnet-5") -> None:
        self.model = model

    def parse(self, text: str, board) -> DesignQuery:
        import anthropic  # 延遲載入：沒有 key 的環境不該因為這個 import 就壞掉

        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=self.model,
            max_tokens=512,
            tools=[QUERY_SCHEMA],
            tool_choice={"type": "tool", "name": "design_query"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"板上的元件：{', '.join(board.names)}。\n"
                        f"把下面這句話轉成 design_query，不要回答它：\n{text}"
                    ),
                }
            ],
        )
        payload = next(b.input for b in resp.content if b.type == "tool_use")

        name = payload.get("component_name")
        index = board.index_of(name) if name else None
        unparsed = () if (name is None or index is not None) else (f"不認得元件「{name}」",)
        return DesignQuery(
            action=payload.get("action", "evaluate"),
            component_index=index,
            component_name=name,
            set_power=payload.get("set_power"),
            set_h_conv=payload.get("set_h_conv"),
            set_t_amb=payload.get("set_t_amb"),
            t_max_limit=payload.get("t_max_limit"),
            raw=text.strip(),
            parser=self.name,
            unparsed=unparsed,
        )


def parse(text: str, board, prefer_llm: bool = True) -> DesignQuery:
    """有 `ANTHROPIC_API_KEY` 就用 LLM，否則規則。**失敗時退回規則，不退回猜測。**"""
    if prefer_llm and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return LLMParser().parse(text, board)
        except Exception:
            pass
    return RuleBasedParser().parse(text, board)
