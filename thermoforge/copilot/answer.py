"""把設計查詢變成一個**帶證據等級**的回答。

## 三種等級，三種行動

| 等級 | 什麼情況 | 副駕怎麼講 |
|---|---|---|
| **已確認** | 數字來自求解器 | 直接給數字 |
| **推論** | 代理模型，且所有輸入都在訓練分佈內 | 給數字 ＋ OOF 校準出來的區間 |
| **未驗證** | 代理模型，但有軸推出訓練分佈 | **點名是哪一軸**，說這題要送求解器／CFD |

第三列是這個模組存在的理由。代理模型在外推區給出的數字不是「比較不準」——
它沒有證據支持。`.claude/rules/evidence-grades.md`：沒有新證據不得把推論寫成已確認，
而外推區連推論都不成立。

## 建議佈局時：代理模型排序，求解器確認

`optimize` 走的是問題定義第 1 題描述的那個流程：代理模型秒級掃過候選，
**取前幾名交給求解器確認**。回報的是求解器確認過的數字（已確認），
代理模型的預測只用來排序。這樣即使代理模型有偏差，最後給出去的溫度仍然是真的。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .. import dataset
from ..data.sampler import ID_RANGES, check_in_distribution, place_rects
from ..solver import solve_layout
from .board import ReferenceBoard
from .query import DesignQuery

__all__ = ["Answer", "answer_query", "load_calibration"]

_AXIS_LABEL = {
    "lx": "板長",
    "aspect": "長寬比",
    "kt": "片導熱 kt",
    "h_conv": "對流係數 h",
    "t_amb": "環境溫度",
    "peak_rise": "熱點溫升（估計）",
    "n_components": "元件數",
}


@dataclass
class Answer:
    query: DesignQuery
    grade: str
    t_max: float | None
    t_max_interval: tuple[float, float] | None
    margin: float | None
    out_of_distribution: dict
    lines: list[str] = field(default_factory=list)
    proposals: list[dict] = field(default_factory=list)

    def render(self) -> str:
        return "\n".join(self.lines)


def load_calibration(path: str | Path = "runs/champion/calibration.json") -> dict | None:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _apply(board: ReferenceBoard, q: DesignQuery) -> ReferenceBoard:
    out = board
    if q.set_power is not None and q.component_index is not None:
        out = out.with_power(q.component_index, q.set_power)
    if q.set_h_conv is not None or q.set_t_amb is not None:
        out = out.with_conditions(h_conv=q.set_h_conv, t_amb=q.set_t_amb)
    return out


def _predict_tmax(predictor, layouts) -> np.ndarray:
    ds = dataset.from_layouts(layouts)
    pred = predictor.predict(ds)
    return pred.reshape(len(pred), -1).max(axis=1)


def _solver_tmax(layout) -> float:
    _, temperature = solve_layout(layout)
    return float(temperature.max())


def _search_layouts(board: ReferenceBoard, n: int, seed: int) -> list:
    """同一組元件、同一組條件，只換位置。與候選池的定義一致。"""
    rng = np.random.default_rng(seed)
    sizes = [(nc.component.w, nc.component.h) for nc in board.components]
    layouts = []
    while len(layouts) < n:
        rects = place_rects(rng, board.lx, board.ly, sizes, ID_RANGES)
        if len(rects) != len(sizes):
            continue
        layouts.append(board.with_positions([(r[0], r[1]) for r in rects]).to_layout())
    return layouts


def answer_query(
    query: DesignQuery,
    board: ReferenceBoard,
    predictor,
    calibration: dict | None = None,
    n_candidates: int = 200,
    n_confirm: int = 3,
    seed: int = 0,
) -> Answer:
    lines: list[str] = []
    for note in query.unparsed:
        lines.append(f"⚠ 沒看懂的部分：{note}")

    after = _apply(board, query)
    layout = after.to_layout()
    ood = check_in_distribution(layout)

    if query.action == "optimize":
        return _answer_optimize(query, after, predictor, calibration, ood, lines, n_candidates, n_confirm, seed)

    t_max = float(_predict_tmax(predictor, [layout])[0])
    margin = after.t_max_allowed - t_max

    if ood:
        grade = "未驗證"
        interval = None
    elif calibration is None:
        grade = "未驗證"
        interval = None
        lines.append("⚠ 找不到校準檔（runs/champion/calibration.json），無法給區間")
    else:
        grade = "推論"
        q05 = calibration["id"]["tmax_err_q05"]
        q95 = calibration["id"]["tmax_err_q95"]
        # 預測誤差 = pred − true，所以真值的區間是 pred − q95 .. pred − q05。
        interval = (t_max - q95, t_max - q05)

    lines.append(f"問題：{query.raw}")
    if query.changes_anything:
        changed = []
        if query.set_power is not None:
            changed.append(f"{query.component_name} 功率 → {query.set_power:g} W")
        if query.set_h_conv is not None:
            changed.append(f"對流係數 h → {query.set_h_conv:g} W/m²K")
        if query.set_t_amb is not None:
            changed.append(f"環境溫度 → {query.set_t_amb:g} °C")
        lines.append("改動：" + "、".join(changed))

    lines.append(f"總功率 {layout.total_power:.1f} W，熱擴散長度 {1000 * layout.diffusion_length:.0f} mm")

    if grade == "推論":
        lines.append(
            f"熱點溫度 **{t_max:.1f} °C**【推論：代理模型，OOF 校準 90% 區間 "
            f"{interval[0]:.1f}–{interval[1]:.1f} °C】"
        )
        verdict = "在上限內" if margin > 0 else "**超過上限**"
        lines.append(f"對上限 {after.t_max_allowed:.0f} °C 的餘裕：{margin:+.1f} °C（{verdict}）")
        if 0 < margin < calibration["id"]["tmax_under_p95"]:
            lines.append(
                f"⚠ 餘裕 {margin:.1f} °C 小於代理模型的低估 p95 "
                f"（{calibration['id']['tmax_under_p95']:.1f} °C）——這個結論不夠穩，建議求解器確認"
            )
    else:
        lines.append(f"熱點溫度 {t_max:.1f} °C【**未驗證**——不要拿這個數字做決定】")
        for axis, (value, (lo, hi)) in ood.items():
            lines.append(
                f"  · {_AXIS_LABEL.get(axis, axis)} = {value:.3g}，訓練分佈只到 {lo:.3g}–{hi:.3g}"
            )
        if calibration and calibration.get("ood"):
            worst = max(calibration["ood"].values(), key=lambda d: d["tmax_mae"])
            lines.append(
                f"  · 代理模型在分佈外的實測 Tmax_MAE 最差到 {worst['tmax_mae']:.1f} °C，"
                "這個數字的誤差可能是同一個量級"
            )
        lines.append("  → 這題要送求解器／CFD，不要用代理模型的數字下結論")

    return Answer(
        query=query,
        grade=grade,
        t_max=t_max,
        t_max_interval=interval,
        margin=margin,
        out_of_distribution=ood,
        lines=lines,
    )


def _answer_optimize(
    query, board, predictor, calibration, ood, lines, n_candidates, n_confirm, seed
) -> Answer:
    current_layout = board.to_layout()
    current_solver = _solver_tmax(current_layout)

    candidates = _search_layouts(board, n_candidates, seed)
    pred_tmax = _predict_tmax(predictor, candidates)
    order = np.argsort(pred_tmax)[:n_confirm]

    proposals = []
    for rank, i in enumerate(order, start=1):
        confirmed = _solver_tmax(candidates[i])
        proposals.append(
            {
                "rank": rank,
                "surrogate_tmax": float(pred_tmax[i]),
                "solver_tmax": confirmed,
                "improvement": current_solver - confirmed,
                "positions": [(c.cx, c.cy) for c in candidates[i].components],
            }
        )

    lines.append(f"問題：{query.raw}")
    lines.append(
        f"現況熱點 {current_solver:.1f} °C【已確認：求解器】，"
        f"上限 {board.t_max_allowed:.0f} °C，餘裕 {board.t_max_allowed - current_solver:+.1f} °C"
    )
    lines.append(
        f"代理模型掃了 {n_candidates} 個佈局（只換位置，元件與散熱條件不變），"
        f"前 {n_confirm} 名交給求解器確認："
    )
    for p in proposals:
        lines.append(
            f"  #{p['rank']}  代理模型 {p['surrogate_tmax']:.1f} °C → "
            f"求解器 **{p['solver_tmax']:.1f} °C**【已確認】，比現況低 {p['improvement']:.1f} °C"
        )
    best = min(proposals, key=lambda p: p["solver_tmax"])
    lines.append(
        f"最佳建議把熱點降到 {best['solver_tmax']:.1f} °C。"
        "這是**建議**不是最佳解證明——搜尋是隨機重啟，沒有收斂保證。"
    )
    if ood:
        lines.append("⚠ 這塊板本身已經有軸落在訓練分佈外，排序的可信度未驗證：")
        for axis, (value, (lo, hi)) in ood.items():
            lines.append(f"  · {_AXIS_LABEL.get(axis, axis)} = {value:.3g}，訓練分佈 {lo:.3g}–{hi:.3g}")

    return Answer(
        query=query,
        grade="已確認",
        t_max=best["solver_tmax"],
        t_max_interval=None,
        margin=board.t_max_allowed - best["solver_tmax"],
        out_of_distribution=ood,
        lines=lines,
        proposals=proposals,
    )
