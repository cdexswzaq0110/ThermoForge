"""資料集生成 CLI。

    python -m thermoforge.data.generate --config configs/dataset_v1.yaml

產出兩個檔：`<name>.npz`（陣列）與 `<name>.manifest.json`（指紋與統計）。

## manifest 為什麼要存陣列的 sha256

`se-ml-lifecycle` Stage 5 要求每個實驗記錄 data hash。沒有它的話，
「這一輪比上一輪好 0.4 °C」這句話無法排除「因為我中途重生成了資料」。
資料指紋是實驗帳本裡唯一能把兩次 run 真正對齊的東西。

## 生成時就檢查能量守恆

守恆殘差在生成迴圈裡逐樣本檢查，超標直接中止而不是寫進檔案。理由是
`docs/02-solver.md` 說的：這條是恆等式，不是精度指標——它一旦不成立，
壞掉的是求解器或離散化，而不是「這批資料比較難」。
把壞資料寫進 npz，後面每一個實驗都會在一個沒人記得的錯誤上跑。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import yaml

from ..geometry import Layout
from ..solver import energy_residual, solve_layout
from .sampler import ID_RANGES, OOD_REGIMES, Ranges, derive_layout, sample_base_layout
from .splits import check_no_group_leakage, group_kfold_assign

#: 能量守恆殘差的中止門檻。求解器在 float64 下的實測值約 1e-13
#: （`tests/test_solver.py::test_energy_conservation_is_exact` 用 1e-10），
#: 留三個數量級的餘裕給不同網格與 m² 組合。
ENERGY_ABORT_THRESHOLD = 1e-9


def _sha256_array(a: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()[:16]


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


SCALAR_KEYS = (
    "kt",
    "h_conv",
    "t_amb",
    "lx",
    "ly",
    "total_power",
    "theta_avg",
    "energy_residual",
)
INT_KEYS = ("n_components", "base_id")


def solve_row(layout: Layout, ny: int, nx: int, group_id: int) -> dict:
    """解一個佈局並打包成一列。能量守恆超標就中止——見模組 docstring。"""
    power_map, temperature = solve_layout(layout, ny=ny, nx=nx)
    residual = energy_residual(layout, temperature)
    if residual > ENERGY_ABORT_THRESHOLD:
        raise RuntimeError(
            f"能量守恆殘差 {residual:.3e} 超過門檻 {ENERGY_ABORT_THRESHOLD:.1e}"
            f"（group={group_id}, h={layout.h_conv:.1f}, kt={layout.kt:.3f}）。"
            "求解器或離散化壞了，不是資料難——先修再生成。"
        )
    return {
        "power_map": power_map.astype(np.float32),
        "temperature": temperature.astype(np.float32),
        "kt": layout.kt,
        "h_conv": layout.h_conv,
        "t_amb": layout.t_amb,
        "lx": layout.lx,
        "ly": layout.ly,
        "total_power": layout.total_power,
        "theta_avg": layout.meta["theta_avg"],
        "n_components": len(layout.components),
        "base_id": group_id,
        "energy_residual": residual,
    }


def rows_to_arrays(rows: list[dict]) -> dict[str, np.ndarray]:
    block = {
        "power_map": np.stack([r["power_map"] for r in rows]),
        "temperature": np.stack([r["temperature"] for r in rows]),
    }
    for key in SCALAR_KEYS:
        block[key] = np.array([r[key] for r in rows], dtype=np.float64)
    for key in INT_KEYS:
        block[key] = np.array([r[key] for r in rows], dtype=np.int64)
    return block


def _generate_block(
    rng: np.random.Generator,
    ranges: Ranges,
    regime: str,
    n_base: int,
    conditions_per_base: int,
    ny: int,
    nx: int,
    base_id_start: int,
) -> tuple[dict[str, np.ndarray], int]:
    rows: list[dict] = []
    base_id = base_id_start
    for _ in range(n_base):
        base = sample_base_layout(rng, ranges, base_id, regime)
        for _ in range(conditions_per_base):
            rows.append(solve_row(derive_layout(base, rng, ranges), ny, nx, base_id))
        base_id += 1
    return rows_to_arrays(rows), base_id


def build_dataset(config: dict) -> tuple[dict[str, np.ndarray], dict]:
    ny, nx = config["grid"]["ny"], config["grid"]["nx"]
    rng = np.random.default_rng(config["seed"])

    regimes: list[tuple[str, Ranges, int]] = [
        ("id", ID_RANGES, config["id"]["n_base"]),
    ]
    for name, ranges in OOD_REGIMES.items():
        regimes.append((name, ranges, config["ood"]["n_base_per_regime"]))

    blocks: list[dict[str, np.ndarray]] = []
    regime_codes: list[np.ndarray] = []
    regime_names = [name for name, _, _ in regimes]
    next_base_id = 0
    t0 = time.perf_counter()

    for code, (name, ranges, n_base) in enumerate(regimes):
        cpb = config["id" if name == "id" else "ood"]["conditions_per_base"]
        block, next_base_id = _generate_block(
            rng, ranges, name, n_base, cpb, ny, nx, next_base_id
        )
        blocks.append(block)
        regime_codes.append(np.full(len(block["kt"]), code, dtype=np.int8))

    data = {k: np.concatenate([b[k] for b in blocks]) for k in blocks[0]}
    data["regime_code"] = np.concatenate(regime_codes)

    # fold 只給 id；OOD 一律 -1，讓「不小心把 OOD 拿去訓練」在索引層就成立不了。
    is_id = data["regime_code"] == 0
    folds = np.full(len(is_id), -1, dtype=np.int64)
    folds[is_id] = group_kfold_assign(
        data["base_id"][is_id], n_splits=config["folds"], seed=config["seed"]
    )
    check_no_group_leakage(data["base_id"][is_id], folds[is_id])
    data["fold"] = folds

    elapsed = time.perf_counter() - t0
    manifest = {
        "name": config["name"],
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": _git_commit(),
        "config": config,
        "grid": {"ny": ny, "nx": nx},
        "n_rows": int(len(data["kt"])),
        "n_base_layouts": int(len(np.unique(data["base_id"]))),
        "regime_names": regime_names,
        "regime_counts": {
            name: int((data["regime_code"] == code).sum())
            for code, name in enumerate(regime_names)
        },
        "fold_counts": {
            str(f): int((data["fold"] == f).sum()) for f in sorted(set(folds.tolist()))
        },
        "energy_residual_max": float(data["energy_residual"].max()),
        "energy_abort_threshold": ENERGY_ABORT_THRESHOLD,
        "ranges": {
            "id": asdict(ID_RANGES),
            **{k: asdict(v) for k, v in OOD_REGIMES.items()},
        },
        "array_sha256": {
            k: _sha256_array(v) for k, v in sorted(data.items())
        },
        "generation_seconds": round(elapsed, 2),
        "solver": "modified Helmholtz, DCT diagonalisation, adiabatic edges",
    }
    return data, manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 ThermoForge 資料集")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("data/processed"))
    args = parser.parse_args(argv)

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    data, manifest = build_dataset(config)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    npz_path = args.out_dir / f"{config['name']}.npz"
    manifest_path = args.out_dir / f"{config['name']}.manifest.json"

    np.savez_compressed(npz_path, **data)
    manifest["npz_bytes"] = npz_path.stat().st_size
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"{npz_path}  {manifest['n_rows']} rows / {manifest['n_base_layouts']} base layouts")
    print(f"  regimes        {manifest['regime_counts']}")
    print(f"  folds          {manifest['fold_counts']}")
    print(f"  energy max res {manifest['energy_residual_max']:.3e}")
    print(f"  {manifest['generation_seconds']}s, {manifest['npz_bytes'] / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
