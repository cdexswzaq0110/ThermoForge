"""把無因次物理基準場算好存成 `<name>.greens.npy`。

    python -m thermoforge.precompute_greens --data data/processed/v1.npz

為什麼要快取：`residual` 變體每個 fold 都要用它，OOF 五折加上候選池會重算六次
同一批東西。它不是模型的一部分，是輸入的一部分——**輸入不該每次重算**。

它也不會造成 leakage：物理基準是一個解析公式，不含任何從資料估出來的參數，
所以「在全體資料上先算好」與「在 training fold 內算」得到的是同一個值。
這是 `CLAUDE.md` 節奏第 3 條的例外，而例外的判準只有一條——
**它有沒有 fit 任何東西**。這裡沒有。
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from . import dataset
from .neural import compute_greens_norm


def cache_path(npz_path: Path) -> Path:
    return npz_path.parent / f"{npz_path.stem}.greens.npy"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="預先計算無因次物理基準場")
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--images", type=int, default=1, choices=(0, 1))
    args = parser.parse_args(argv)

    ds = dataset.load(args.data)
    t0 = time.perf_counter()
    greens = compute_greens_norm(ds, images=args.images)
    out = cache_path(args.data)
    np.save(out, greens)
    print(f"{out}  {greens.shape}  {time.perf_counter() - t0:.1f}s  {out.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
