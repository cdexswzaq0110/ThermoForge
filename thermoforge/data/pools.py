"""篩選候選池——主要 metric 唯一站得住腳的評估場景。

    python -m thermoforge.data.pools --config configs/pools_v1.yaml

## 為什麼不能直接在一般資料集上算篩選召回率

`docs/01-problem-statement.md` 第 1 題說模型負責的是「從候選佈局裡篩出最涼的幾個」。
第一版直接在 dataset v1 的 3600 列上算這個指標，結果是：

    完全不看佈局的預測（T_amb + P/(h·A)）  recall@20/200 = 0.609 ± 0.088
    隨機排序                              recall@20/200 = 0.108 ± 0.066
    機會水準 k/pool                        = 0.100

【已確認：2026-09-07 在 data/processed/v1.npz 的 id 子集上實測】

也就是說，那個指標有六成是被一個**根本沒看佈局**的公式贏走的。原因很簡單：
一般資料集裡每一列的板子、功率、對流條件都不一樣，所以候選之間的溫差主要來自
「這塊板的功率密度多高」，而不是「元件擺在哪」。一個什麼都沒學到的模型只要
把能量守恆算對就能拿到 0.6。

**這個指標在那個場景下是飽和的，任何在它上面做出來的模型比較都會誤導。**

## 候選池的定義

真實的設計迭代是：板子、元件清單、功率預算、散熱方案**全部固定**，工程師只換佈局。
所以候選池必須是——

| 在一個池內固定 | 在一個池內變動 |
|---|---|
| 板長寬、kt、h、T_amb | **元件位置** |
| 元件尺寸、功率比例、總功率 | 僅此而已 |

於是 P/(h·A) 在池內是常數，那個作弊的預測退化成隨機排序。
留下來的訊號**只剩佈局**，這正是要量的東西。

## 兩份池，兩種身分

- `dev`：與 id 同分佈，開發期可以反覆看，用來選模型。
- `frozen`：與 OOD holdout 一起解凍，整個專案看一次。

兩份的 pool_id 不相交，且都不參與訓練。
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import yaml

from .generate import _git_commit, _sha256_array, rows_to_arrays, solve_row
from .sampler import ID_RANGES, BaseLayout, Ranges, build_layout, place_rects

__all__ = ["build_pools"]


def _place_all(
    rng: np.random.Generator,
    lx: float,
    ly: float,
    sizes: list[tuple[float, float]],
    ranges: Ranges,
    attempts: int = 50,
) -> list[tuple[float, float, float, float]] | None:
    """把**全部**元件放進去，否則回傳 None。

    `place_rects` 允許放不下就少放一個。在候選池裡那是不能接受的——
    少一個元件會同時改變元件數與總功率，池內就不再是「只有佈局在變」，
    而這個池存在的全部理由就是那個不變量。
    """
    for _ in range(attempts):
        rects = place_rects(rng, lx, ly, sizes, ranges)
        if len(rects) == len(sizes):
            return rects
    return None


def build_pools(config: dict) -> tuple[dict[str, np.ndarray], dict]:
    ny, nx = config["grid"]["ny"], config["grid"]["nx"]
    variants = config["variants_per_pool"]
    ranges = ID_RANGES
    rng = np.random.default_rng(config["seed"])

    rows: list[dict] = []
    pool_ids: list[int] = []
    split_codes: list[int] = []
    split_names = ["dev", "frozen"]
    t0 = time.perf_counter()

    pool_id = 0
    for split_code, split in enumerate(split_names):
        for _ in range(config[f"n_pools_{split}"]):
            # 一個池 = 一組固定條件 + 一組固定元件尺寸與功率比例。
            while True:
                lx = float(rng.uniform(*ranges.lx))
                ly = lx / float(rng.uniform(*ranges.aspect))
                n = int(rng.integers(ranges.n_components[0], ranges.n_components[1] + 1))
                sizes = [
                    (float(rng.uniform(*ranges.comp_size)), float(rng.uniform(*ranges.comp_size)))
                    for _ in range(n)
                ]
                if _place_all(rng, lx, ly, sizes, ranges) is not None:
                    break

            fractions = tuple(float(f) for f in rng.dirichlet(np.full(n, 2.0)))
            kt = float(rng.uniform(*ranges.kt))
            h_conv = float(rng.uniform(*ranges.h_conv))
            t_amb = float(rng.uniform(*ranges.t_amb))
            peak_target = float(rng.uniform(*ranges.peak_rise))

            for _ in range(variants):
                rects = _place_all(rng, lx, ly, sizes, ranges)
                if rects is None:  # pragma: no cover — 上面的 while 已確認放得下
                    raise RuntimeError("池內某個變體放不下全部元件")
                base = BaseLayout(
                    base_id=pool_id,
                    lx=lx,
                    ly=ly,
                    rects=tuple(rects),
                    power_fractions=fractions,
                    regime=f"pool_{split}",
                )
                layout = build_layout(base, kt, h_conv, t_amb, peak_target)
                rows.append(solve_row(layout, ny, nx, pool_id))
                pool_ids.append(pool_id)
                split_codes.append(split_code)
            pool_id += 1

    data = rows_to_arrays(rows)
    data["pool_id"] = np.array(pool_ids, dtype=np.int64)
    data["split_code"] = np.array(split_codes, dtype=np.int8)

    # 池內不變量的機械化驗收：條件與總功率在池內必須逐位元相同。
    for pid in np.unique(data["pool_id"]):
        mask = data["pool_id"] == pid
        for key in ("lx", "ly", "kt", "h_conv", "t_amb", "total_power", "n_components"):
            if len(np.unique(data[key][mask])) != 1:
                raise AssertionError(
                    f"pool {pid} 的 {key} 在池內不是常數——這個池量不出佈局的貢獻"
                )

    elapsed = time.perf_counter() - t0
    manifest = {
        "name": config["name"],
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": _git_commit(),
        "config": config,
        "grid": {"ny": ny, "nx": nx},
        "n_rows": int(len(rows)),
        "n_pools": int(pool_id),
        "variants_per_pool": variants,
        "regime_names": ["pool_dev", "pool_frozen"],
        "split_names": split_names,
        "split_counts": {
            name: int((data["split_code"] == code).sum())
            for code, name in enumerate(split_names)
        },
        "ranges": {"pool": asdict(ranges)},
        "energy_residual_max": float(data["energy_residual"].max()),
        "array_sha256": {k: _sha256_array(v) for k, v in sorted(data.items())},
        "generation_seconds": round(elapsed, 2),
        "invariant": "板、元件尺寸、功率比例、總功率、kt、h、T_amb 在池內固定；只有元件位置變動",
    }
    return data, manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 ThermoForge 篩選候選池")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("data/processed"))
    args = parser.parse_args(argv)

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    data, manifest = build_pools(config)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    npz_path = args.out_dir / f"{config['name']}.npz"
    np.savez_compressed(npz_path, **data)
    manifest["npz_bytes"] = npz_path.stat().st_size
    (args.out_dir / f"{config['name']}.manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"{npz_path}  {manifest['n_rows']} rows / {manifest['n_pools']} pools")
    print(f"  splits         {manifest['split_counts']}")
    print(f"  energy max res {manifest['energy_residual_max']:.3e}")
    print(f"  {manifest['generation_seconds']}s, {manifest['npz_bytes'] / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
