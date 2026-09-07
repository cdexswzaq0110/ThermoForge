"""設計副駕 CLI。

    python -m thermoforge.copilot "CPU 拉到 60W 還安全嗎"
    python -m thermoforge.copilot --demo

`--demo` 跑一組固定的問句，涵蓋四種情況：分佈內、推出分佈、解析失敗、佈局最佳化。
它是給人看的示範，不是測試——測試在 `tests/test_copilot.py`，用 stub 預測器，不需要權重。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .answer import answer_query, load_calibration
from .board import load_board
from .query import parse

DEMO = [
    "現在這塊板的熱點多少度？",
    "如果把 CPU 從 25.5W 拉到 60W，還安全嗎？",
    "風扇加強一點會不會好一些？",
    "幫我把元件重新排一下，讓熱點低一點",
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ThermoForge 設計副駕")
    p.add_argument("question", nargs="*", help="自然語言問題")
    p.add_argument("--demo", action="store_true")
    p.add_argument("--board", type=Path, default=Path("configs/reference_board.yaml"))
    p.add_argument("--champion", type=Path, default=Path("runs/champion/model.pt"))
    p.add_argument("--no-llm", action="store_true", help="強制用規則解析")
    args = p.parse_args(argv)

    questions = DEMO if args.demo else [" ".join(args.question)]
    if not questions or not questions[0]:
        p.error("給一個問題，或用 --demo")

    if not args.champion.exists():
        print(f"找不到 champion 權重 {args.champion}——先跑 python -m thermoforge.champion")
        return 1

    from ..neural import NeuralPredictor

    predictor = NeuralPredictor.load(args.champion)
    board = load_board(args.board)
    calibration = load_calibration(args.champion.parent / "calibration.json")

    print(f"板：{board.name}  {1000 * board.lx:.0f}x{1000 * board.ly:.0f} mm，"
          f"元件 {', '.join(board.names)}")
    print(f"代理模型：{predictor.name}"
          + ("" if calibration else "（沒有校準檔，所有結論一律未驗證）"))

    for q in questions:
        print("\n" + "─" * 72)
        query = parse(q, board, prefer_llm=not args.no_llm)
        print(answer_query(query, board, predictor, calibration).render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
