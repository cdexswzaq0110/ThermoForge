"""定版：把 champion 訓練成可部署的 artifact，並產出校準檔。

    python -m thermoforge.champion --variant residual --epochs 25 --seed 0

產出 `runs/champion/`：

| 檔 | 內容 | 誰要用 |
|---|---|---|
| `model.pt` | 在**全部** id 資料上 fit 的權重 ＋ 超參數 ＋ 正規化常數 | 設計副駕、frozen 評估 |
| `oof.npy` | 五折 OOF 溫度場預測 | Stage 6 可解釋性、校準 |
| `calibration.json` | OOF 熱點誤差的分位數 | 副駕的區間與「餘裕夠不夠」判斷 |

## 校準為什麼一定要用 OOF

用訓練殘差算區間，量到的是模型記住了多少，不是它在沒看過的板子上會差多少。
副駕拿那個區間去講「90% 落在 ±1.2 °C」會系統性過度自信，
而過度自信在一個**低估比高估貴**的問題上是最糟的失敗方向。

`oof.npy` 存的是每一列由**沒看過它**的 fold model 給出的預測，所以分位數是誠實的。
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from . import dataset
from .evaluate import run_oof, tmax
from .metrics import evaluate_fields


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="訓練並封裝 champion")
    p.add_argument("--variant", default="residual", choices=("direct", "norm", "residual"))
    p.add_argument("--epochs", type=int, default=25)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--under-weight", type=float, default=1.0)
    p.add_argument("--data", type=Path, default=Path("data/processed/v1.npz"))
    p.add_argument("--out", type=Path, default=Path("runs/champion"))
    p.add_argument(
        "--skip-oof",
        action="store_true",
        help="只做 final fit，不跑 OOF，也不產校準檔。用在 frozen 比較用的對照組——"
        "它們不需要校準，而 OOF 佔了這支程式六分之五的時間",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from .neural import NeuralPredictor

    ds = dataset.load(args.data).id_only

    def make():
        return NeuralPredictor(
            variant=args.variant,
            epochs=args.epochs,
            under_weight=args.under_weight,
            seed=args.seed,
        )

    t0 = time.perf_counter()

    if args.skip_oof:
        final = make()
        final.fit(ds)
        args.out.mkdir(parents=True, exist_ok=True)
        final.save(args.out / "model.pt")
        print(f"{final.name} → {args.out}/model.pt  {time.perf_counter() - t0:.0f}s（跳過 OOF，無校準檔）")
        return 0

    oof, per_fold = run_oof(make, ds)
    truth = ds.temperature.astype(np.float64)
    overall = evaluate_fields(oof, truth)

    err = tmax(oof) - tmax(truth)
    under = np.clip(-err, 0.0, None)

    # 最終 artifact 在全部 id 資料上 fit——校準已經由 OOF 給了，
    # 這一步不再需要留驗證集（`se-ml-lifecycle` Stage 7 的 final fit）。
    final = make()
    final.fit(ds)

    args.out.mkdir(parents=True, exist_ok=True)
    final.save(args.out / "model.pt")
    np.save(args.out / "oof.npy", oof.astype(np.float32))

    calibration = {
        "champion": final.name,
        "config": {
            "variant": args.variant,
            "epochs": args.epochs,
            "seed": args.seed,
            "under_weight": args.under_weight,
        },
        "data_sha256": ds.manifest["array_sha256"]["temperature"],
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "id": {
            "n": int(len(err)),
            "tmax_mae": overall.tmax_mae,
            "tmax_bias": overall.tmax_bias,
            "tmax_err_q05": float(np.percentile(err, 5)),
            "tmax_err_q50": float(np.percentile(err, 50)),
            "tmax_err_q95": float(np.percentile(err, 95)),
            "tmax_under_p95": float(np.percentile(under, 95)),
            "under_rate": overall.under_rate,
            "field_mae": overall.field_mae,
            "per_fold_tmax_mae": [m.tmax_mae for m in per_fold],
        },
        "ood": {},
        "note": "ood 由 thermoforge.frozen 填入；在那之前副駕對分佈外一律報未驗證",
    }
    (args.out / "calibration.json").write_text(
        json.dumps(calibration, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"champion {final.name}  {time.perf_counter() - t0:.0f}s")
    print("  " + overall.summary())
    print(
        "  Tmax 誤差分位數 q05 %.3f  q50 %.3f  q95 %.3f  低估 p95 %.3f"
        % (
            calibration["id"]["tmax_err_q05"],
            calibration["id"]["tmax_err_q50"],
            calibration["id"]["tmax_err_q95"],
            calibration["id"]["tmax_under_p95"],
        )
    )
    print(f"  → {args.out}/model.pt, oof.npy, calibration.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
