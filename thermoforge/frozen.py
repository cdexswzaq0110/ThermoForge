"""解凍 frozen holdout。**整個專案應該只跑一次。**

    python -m thermoforge.frozen --confirm

`--confirm` 不是禮貌性確認。每次執行都往 `runs/frozen_ledger.jsonl` 追加一列，
記錄時間、git commit、champion 的 sha 與當時的結果。跑第二次不會被擋，
但**帳本上會有兩列**，而 PR 裡要解釋為什麼。

擋不住的東西改成記錄下來，是因為真正的風險不是有人惡意偷看，
是**忘記自己看過**。忘不掉的帳本比擋得住的鎖有用。

評估兩件事：

| 資料 | 回答 |
|---|---|
| OOD holdout（5 個 regime，各推一軸） | 外推會不會崩，崩在哪一軸 |
| pool-frozen（20 個候選池） | 篩選能力的最終判定 |

結果同時寫回 `runs/champion/calibration.json` 的 `ood` 區塊——
設計副駕在報「未驗證」時要引用這些數字說明誤差可能有多大。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import numpy as np

from . import dataset
from .evaluate import tmax
from .metrics import evaluate_fields, screening_recall_within_pools


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5
        ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="解凍 frozen holdout（會寫進帳本）")
    p.add_argument("--confirm", action="store_true", required=True,
                   help="必須明確加上。每次執行都會在 runs/frozen_ledger.jsonl 留一列")
    p.add_argument("--champion", type=Path, default=Path("runs/champion"))
    p.add_argument(
        "--also",
        type=Path,
        nargs="*",
        default=(),
        help="一起評估的對照組模型目錄。**在同一次解凍裡評估多個模型是刻意的**——"
        "「無因次化改善外推」這個宣稱需要 direct 與 residual 在同一份 holdout 上的數字，"
        "分兩次跑就變成看了兩次。要比什麼在解凍前就決定好，一次看完",
    )
    p.add_argument("--data", type=Path, default=Path("data/processed/v1.npz"))
    p.add_argument("--pools", type=Path, default=Path("data/processed/pools_v1.npz"))
    p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from .neural import NeuralPredictor

    model = NeuralPredictor.load(args.champion / "model.pt")
    ds = dataset.load(args.data)
    pools_frozen = dataset.load(args.pools).split("frozen")

    def ood_of(m) -> dict[str, dict]:
        out = {}
        for name in ds.regime_names[1:]:
            sub = ds.regime(name)
            out[name] = evaluate_fields(m.predict(sub), sub.temperature.astype(np.float64)).as_dict()
        return out

    ood_report = ood_of(model)
    comparisons = {}
    for extra in args.also:
        other = NeuralPredictor.load(Path(extra) / "model.pt")
        comparisons[other.name] = ood_of(other)

    # in-distribution 的對照：同一個模型在 id 上的分數。champion 是在全部 id 上 fit 的，
    # 所以這個數字是**樂觀的**（模型看過這些列）——它只用來當外推退化的比例尺，
    # 不可以拿來當泛化分數。真正的 id 分數在 calibration.json 的 OOF。
    id_pred = model.predict(ds.id_only)
    id_fit = evaluate_fields(id_pred, ds.id_only.temperature.astype(np.float64))

    pool_pred = model.predict(pools_frozen)
    pool_truth = pools_frozen.temperature.astype(np.float64)
    pool_metrics = evaluate_fields(pool_pred, pool_truth)
    recall_mean, recall_std = screening_recall_within_pools(
        tmax(pool_pred), tmax(pool_truth), pools_frozen.arrays["pool_id"], k=10
    )

    entry = {
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": _git_commit(),
        "champion": model.name,
        "champion_dir": str(args.champion),
        "data_sha256": ds.manifest["array_sha256"]["temperature"],
        "ood": ood_report,
        "ood_comparisons": comparisons,
        "id_refit_reference": id_fit.as_dict(),
        "pool_frozen": pool_metrics.as_dict(),
        "pool_frozen_recall_mean": recall_mean,
        "pool_frozen_recall_std": recall_std,
    }
    args.runs_dir.mkdir(parents=True, exist_ok=True)
    with (args.runs_dir / "frozen_ledger.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    cal_path = args.champion / "calibration.json"
    if cal_path.exists():
        cal = json.loads(cal_path.read_text(encoding="utf-8"))
        cal["ood"] = ood_report
        cal["frozen_pool_recall"] = [recall_mean, recall_std]
        cal_path.write_text(json.dumps(cal, indent=2, ensure_ascii=False), encoding="utf-8")

    n_prev = sum(1 for _ in (args.runs_dir / "frozen_ledger.jsonl").open(encoding="utf-8"))
    print(f"champion {model.name}   （這是第 {n_prev} 次解凍）")
    print(f"  id（已 fit 過，僅供比例尺）  {id_fit.summary()}")
    for name, m in ood_report.items():
        print(
            "  %-12s field_MAE %6.3f  Tmax_MAE %6.3f  bias %+7.3f  under %5.1f%%"
            % (name, m["field_mae"], m["tmax_mae"], m["tmax_bias"], 100 * m["under_rate"])
        )
    for other_name, rep in comparisons.items():
        print(f"  -- 對照 {other_name} --")
        for name, m in rep.items():
            print(
                "  %-12s field_MAE %6.3f  Tmax_MAE %6.3f  bias %+7.3f  under %5.1f%%"
                % (name, m["field_mae"], m["tmax_mae"], m["tmax_bias"], 100 * m["under_rate"])
            )
    print(f"  pool-frozen  recall@10/60 {recall_mean:.3f} +- {recall_std:.3f}   {pool_metrics.summary()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
