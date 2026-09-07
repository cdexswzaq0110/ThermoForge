"""產出 README 與報告用的圖。

    .venv/Scripts/python scripts/make_figures.py

需要：`runs/ledger.jsonl`、`runs/champion/`（model.pt ＋ oof.npy）。
OOD 那張還需要 `runs/frozen_ledger.jsonl`——沒有就跳過，不畫空的。

## 配色的三條規則（來自 dataviz skill 的驗證過的預設盤）

1. **連續量用單一色相由淺到深。** 溫度場與功率圖各自一條 ramp，不用彩虹。
2. **有正負之分的量用雙色相 ＋ 中性灰中點。** 誤差圖是藍↔紅，0 落在灰。
   熱設計裡低估與高估的意義相反，用單色 ramp 會把這件事抹掉。
3. **類別色照固定順序取，不循環。** 藍 → 橙 → 青綠。

不畫雙 y 軸。兩個尺度不同的量就畫兩張圖。
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e3e2de"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]

SEQ_POWER = LinearSegmentedColormap.from_list("tf_power", ["#eef4fd", "#86b6ef", "#256abf", "#0d366b"])
SEQ_TEMP = LinearSegmentedColormap.from_list("tf_temp", ["#fdf0e9", "#f7b48f", "#eb6834", "#8a3113"])
DIVERGING = LinearSegmentedColormap.from_list("tf_err", ["#184f95", "#86b6ef", "#f0efec", "#f09190", "#a81f1e"])

OUT = Path("docs/images")


def _style(ax, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, color=INK, fontsize=11, loc="left", pad=10)
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.grid(True, color=GRID, linewidth=0.8, alpha=0.9)
    ax.set_axisbelow(True)


def _panel(ax, data, cmap, title, norm=None, unit=""):
    im = ax.imshow(data, origin="lower", cmap=cmap, norm=norm, interpolation="nearest")
    ax.set_title(title, color=INK, fontsize=10, loc="left", pad=6)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(GRID)
    cb = ax.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.ax.tick_params(colors=INK2, labelsize=8, length=0)
    cb.outline.set_visible(False)
    if unit:
        cb.set_label(unit, color=INK2, fontsize=8)
    return im


def figure_fields() -> None:
    from thermoforge import dataset
    from thermoforge.diagnostics import pde_residual
    from thermoforge.neural import NeuralPredictor

    ds = dataset.load("data/processed/pools_v1.npz").split("dev")
    model = NeuralPredictor.load("runs/champion/model.pt")
    pred = model.predict(ds)
    truth = ds.temperature.astype(np.float64)

    # 挑一筆誤差接近中位數的——展示典型行為，不是挑最好看的那一張。
    err = np.abs(pred - truth).mean(axis=(1, 2))
    i = int(np.argsort(err)[len(err) // 2])

    fig, axes = plt.subplots(1, 4, figsize=(15, 3.6))
    fig.patch.set_facecolor(SURFACE)

    _panel(axes[0], ds.power_map[i] / 1e3, SEQ_POWER, "功率圖", unit="kW/m²")
    tmin, tmax_ = float(truth[i].min()), float(truth[i].max())
    _panel(axes[1], truth[i], SEQ_TEMP, f"求解器（真值）  T_max {tmax_:.1f} °C", unit="°C")
    axes[1].images[0].set_clim(tmin, tmax_)
    _panel(axes[2], pred[i], SEQ_TEMP, f"代理模型  T_max {pred[i].max():.1f} °C", unit="°C")
    axes[2].images[0].set_clim(tmin, tmax_)

    d = pred[i] - truth[i]
    lim = max(float(np.abs(d).max()), 1e-6)
    _panel(
        axes[3],
        d,
        DIVERGING,
        f"誤差（預測 − 真值）  最大 |Δ| {lim:.2f} °C",
        norm=TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim),
        unit="°C",
    )

    fig.suptitle(
        "同一塊板：功率佈局 → 溫度場。第四張的藍色是低估——熱設計裡貴的那一側",
        color=INK, fontsize=11, x=0.01, ha="left", y=1.02,
    )
    fig.tight_layout()
    fig.savefig(OUT / "fields.png", dpi=140, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)

    # 物理殘差單獨一張：它問的是「輸出違反方程多少」，與誤差圖不同軸。
    theta = pred[i] - ds.t_amb[i]
    r = pde_residual(
        theta, ds.power_map[i].astype(np.float64), float(ds.kt[i]), float(ds.h_conv[i]),
        ds.ly[i] / 64, ds.lx[i] / 64,
    )
    scale = (ds.power_map[i] / ds.kt[i]).max()
    fig, ax = plt.subplots(figsize=(4.6, 3.8))
    fig.patch.set_facecolor(SURFACE)
    lim = float(np.abs(r / scale).max())
    _panel(ax, r / scale, DIVERGING, "PDE 殘差（正規化）",
           norm=TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim))
    fig.tight_layout()
    fig.savefig(OUT / "pde_residual.png", dpi=140, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def _ledger() -> dict[str, dict]:
    rows = {}
    for line in Path("runs/ledger.jsonl").read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        rows[e["run_id"]] = e
    return rows


def figure_models() -> None:
    rows = _ledger()
    order = [
        ("mean_field_s0", "平均場（下限）"),
        ("greens_free_s0", "Green's 自由空間"),
        ("greens_images_s0", "Green's ＋ 鏡像（物理基準）"),
        ("unet_direct_s0", "U-Net direct"),
        ("unet_norm_s0", "U-Net 無因次化"),
        ("unet_residual_s0", "U-Net 殘差（champion）"),
    ]
    order = [(k, lab) for k, lab in order if k in rows]
    labels = [lab for _, lab in order]
    tmax_mae = [rows[k]["result"]["oof"]["tmax_mae"] for k, _ in order]
    recall = [rows[k]["result"]["screening_recall_mean"] for k, _ in order]
    recall_std = [rows[k]["result"]["screening_recall_std"] for k, _ in order]
    colors = [SERIES[2] if "greens_images" in k else (SERIES[1] if k.startswith("unet") else SERIES[0])
              for k, _ in order]
    y = np.arange(len(order))

    fig, axes = plt.subplots(1, 2, figsize=(13, 0.62 * len(order) + 2.2))
    fig.patch.set_facecolor(SURFACE)

    ax = axes[0]
    ax.barh(y, tmax_mae, color=colors, height=0.62)
    ax.set_xscale("log")
    ax.set_yticks(y, labels, color=INK2)
    ax.invert_yaxis()
    _style(ax, "熱點溫度誤差（OOF，越低越好）", "Tmax MAE  °C（對數軸）")
    for yi, v in zip(y, tmax_mae):
        ax.text(v * 1.12, yi, f"{v:.2f}", va="center", color=INK, fontsize=9)
    ax.grid(axis="y", visible=False)

    ax = axes[1]
    ax.barh(y, recall, xerr=recall_std, color=colors, height=0.62,
            error_kw={"ecolor": INK2, "elinewidth": 1, "capsize": 3})
    ax.axvline(10 / 60, color=INK2, linestyle="--", linewidth=1)
    ax.text(10 / 60, -0.9, "機會水準 0.167", color=INK2, fontsize=8, ha="center")
    ax.set_yticks(y, ["" for _ in labels])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.05)
    _style(ax, "候選池篩選召回率 recall@10/60（越高越好）", "召回率")
    for yi, v in zip(y, recall):
        ax.text(v + 0.02, yi, f"{v:.3f}", va="center", color=INK, fontsize=9)
    ax.grid(axis="y", visible=False)

    fig.tight_layout()
    fig.savefig(OUT / "models.png", dpi=140, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def figure_ood() -> None:
    path = Path("runs/frozen_ledger.jsonl")
    if not path.exists():
        print("跳過 OOD 圖：還沒解凍 frozen holdout")
        return
    entry = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    series = {entry["champion"]: entry["ood"], **entry.get("ood_comparisons", {})}
    regimes = list(next(iter(series.values())).keys())

    fig, ax = plt.subplots(figsize=(10, 4.4))
    fig.patch.set_facecolor(SURFACE)
    width = 0.8 / len(series)
    x = np.arange(len(regimes))
    for j, (name, rep) in enumerate(series.items()):
        vals = [rep[r]["tmax_mae"] for r in regimes]
        pos = x + (j - (len(series) - 1) / 2) * width
        ax.bar(pos, vals, width=width * 0.9, color=SERIES[j], label=name)
        for p, v in zip(pos, vals):
            ax.text(p, v * 1.05, f"{v:.1f}", ha="center", color=INK, fontsize=8)
    ax.set_yscale("log")
    ax.set_xticks(x, regimes, color=INK2)
    _style(ax, "分佈外的熱點誤差：每個 regime 只把一個軸推出訓練範圍", "", "Tmax MAE  °C（對數軸）")
    ax.grid(axis="x", visible=False)
    leg = ax.legend(frameon=False, fontsize=9, loc="upper left")
    for t in leg.get_texts():
        t.set_color(INK2)
    fig.tight_layout()
    fig.savefig(OUT / "ood.png", dpi=140, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def figure_error_drivers() -> None:
    from thermoforge import dataset
    from thermoforge.diagnostics import error_drivers

    oof = np.load("runs/champion/oof.npy").astype(np.float64)
    ds = dataset.load("data/processed/v1.npz").id_only
    drivers = error_drivers(ds, oof)

    names = [
        ("hotspot_edge_distance_over_diffusion_length", "熱點到板緣距離 ÷ 擴散長度"),
        ("m_times_lx", "m · Lx（板子有幾個擴散長度寬）"),
        ("power_concentration", "功率集中度 max(p_norm)"),
        ("n_components", "元件數"),
    ]
    fig, axes = plt.subplots(1, len(names), figsize=(4 * len(names), 3.4), sharey=True)
    fig.patch.set_facecolor(SURFACE)
    for ax, (key, label) in zip(axes, names):
        d = drivers[key]
        edges = np.array(d["edges"])
        centres = 0.5 * (edges[:-1] + edges[1:])
        ax.plot(centres, d["mae"], color=SERIES[0], linewidth=2, marker="o", markersize=6)
        _style(ax, label, "", "Tmax MAE  °C" if ax is axes[0] else "")
        ax.text(
            0.02, 0.94, f"跨 fold 排序一致性 {d['fold_rank_agreement']:.2f}",
            transform=ax.transAxes, color=INK2, fontsize=8, va="top",
        )
    fig.suptitle("誤差的結構驅動因子（champion，OOF）", color=INK, fontsize=11, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT / "error_drivers.png", dpi=140, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    figure_models()
    figure_fields()
    figure_error_drivers()
    figure_ood()
    print("→", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
