"""實驗入口與帳本。

    python -m thermoforge.experiments --model greens_images \\
        --hypothesis "一階鏡像補掉自由空間解的受限誤差" --change "images=1"

每一次執行寫一列到 `runs/ledger.jsonl`，欄位照 `se-ml-lifecycle` Stage 5 的
Experiment Ledger：run_id、資料指紋、code commit、假設、**唯一的主要改動**、
評估結果、成本、決策。

`--hypothesis` 與 `--change` 是必填。理由不是形式主義：一輪實驗跑完之後，
「我這次改了什麼、為什麼覺得會有用」是最先被遺忘、也最難從 diff 重建的東西。
留白的欄位比沒有欄位更糟——它讓帳本看起來完整。

**這個入口碰不到 frozen holdout。** 那條路徑在 `thermoforge.frozen`，要另外確認。
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import time
from pathlib import Path

from . import dataset
from .evaluate import evaluate_development
from .predictors import make_baseline

BASELINES = ("mean_field", "greens_free", "greens_images")


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        return (out.stdout.strip() or "unknown") + ("+dirty" if dirty else "")
    except Exception:
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="跑一次 ThermoForge 實驗並寫入帳本")
    p.add_argument("--model", required=True, choices=(*BASELINES, "unet"))
    p.add_argument("--variant", default="norm", choices=("direct", "norm", "residual"))
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--lr", type=float, default=2e-3)
    p.add_argument("--base-channels", type=int, default=32)
    p.add_argument("--under-weight", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--data", type=Path, default=Path("data/processed/v1.npz"))
    p.add_argument("--pools", type=Path, default=Path("data/processed/pools_v1.npz"))
    p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    p.add_argument("--hypothesis", required=True, help="這一次要檢驗什麼")
    p.add_argument("--change", required=True, help="相對於上一輪，唯一的主要改動")
    p.add_argument("--note", default="")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    ds = dataset.load(args.data).id_only
    pools_dev = dataset.load(args.pools).split("dev")

    if args.model in BASELINES:
        name = args.model

        def make():
            return make_baseline(name)

        config = {"model": args.model}
    else:
        from .neural import NeuralPredictor  # torch 只在需要時才載入

        def make():
            return NeuralPredictor(
                variant=args.variant,
                epochs=args.epochs,
                batch_size=args.batch_size,
                lr=args.lr,
                base_channels=args.base_channels,
                under_weight=args.under_weight,
                seed=args.seed,
            )

        name = make().name
        config = {
            "model": "unet",
            "variant": args.variant,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "base_channels": args.base_channels,
            "under_weight": args.under_weight,
        }

    run_id = f"{name}_s{args.seed}"
    t0 = time.perf_counter()
    result = evaluate_development(make, ds, pools_dev, n_folds=args.folds)
    wall = time.perf_counter() - t0

    entry = {
        "run_id": run_id,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": _git_commit(),
        "data": {
            "npz": str(args.data),
            "sha256": ds.manifest["array_sha256"],
            "pools": str(args.pools),
        },
        "env": {"python": platform.python_version(), "platform": platform.platform()},
        "config": {**config, "seed": args.seed, "folds": args.folds},
        "hypothesis": args.hypothesis,
        "main_change": args.change,
        "note": args.note,
        "result": result,
        "wall_seconds": round(wall, 1),
        "decision": "pending",
    }

    run_dir = args.runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "metrics.json").write_text(
        json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    args.runs_dir.mkdir(parents=True, exist_ok=True)
    with (args.runs_dir / "ledger.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    o = result["oof"]
    print(f"[{run_id}] {wall:.0f}s")
    print(
        "  OOF   field_MAE %.3f  Tmax_MAE %.3f  bias %+.3f  under %.1f%%  under_p95 %.2f"
        % (o["field_mae"], o["tmax_mae"], o["tmax_bias"], 100 * o["under_rate"], o["under_p95"])
    )
    print(
        "  pool  recall@10/60 %.3f +- %.3f   latency %.2f ms   fold-noise(Tmax_MAE) %.4f"
        % (
            result["screening_recall_mean"],
            result["screening_recall_std"],
            result["inference_ms_per_layout"],
            result["oof_fold_noise_std"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
