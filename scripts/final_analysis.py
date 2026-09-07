"""Stage 6 的數字來源：物理診斷、失敗模式、以及主要 metric 飽和後的加嚴版本。

    .venv/Scripts/python scripts/final_analysis.py

需要 `runs/champion/`（model.pt ＋ oof.npy）。輸出印到 stdout，
由人抄進 `docs/06-interpretability.md`——這一份不自動改文件，
因為它的產出需要**判讀**（哪個驅動因子跨 fold 穩、哪個不穩、要不要報），
而判讀不該被自動化掉。
"""

from __future__ import annotations

import numpy as np

import sys
from pathlib import Path as _Path

# 直接跑 `python scripts/x.py` 時，repo 根目錄不在 sys.path 上。
# 加在這裡而不是要求使用者設 PYTHONPATH——README 的指令要能照抄就跑。
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))


from thermoforge import dataset
from thermoforge.diagnostics import (
    conservation_error,
    error_drivers,
    pde_residual_score,
    worst_underestimates,
)
from thermoforge.metrics import screening_recall_within_pools
from thermoforge.neural import NeuralPredictor
from thermoforge.predictors import make_baseline

RULE = "─" * 74


def main() -> int:
    ds = dataset.load("data/processed/v1.npz").id_only
    pools = dataset.load("data/processed/pools_v1.npz")
    dev = pools.split("dev")
    model = NeuralPredictor.load("runs/champion/model.pt")
    oof = np.load("runs/champion/oof.npy").astype(np.float64)

    print(RULE)
    print("1. 主要 metric 飽和之後，把 K 收緊才看得出差距")
    print(RULE)
    truth = dev.temperature.astype(np.float64)
    t_true = truth.reshape(len(truth), -1).max(axis=1)
    pid = dev.arrays["pool_id"]
    preds = {
        "greens_images（物理基準）": make_baseline("greens_images").predict(dev),
        f"{model.name}（champion）": model.predict(dev),
    }
    rng = np.random.default_rng(0)
    preds["隨機排序"] = None

    print(f"{'預測器':30s} " + "  ".join(f"recall@{k}/60" for k in (10, 5, 3, 1)))
    for name, p in preds.items():
        if p is None:
            t_pred = rng.uniform(size=len(t_true))
        else:
            t_pred = p.reshape(len(p), -1).max(axis=1)
        cells = []
        for k in (10, 5, 3, 1):
            m, s = screening_recall_within_pools(t_pred, t_true, pid, k=k)
            cells.append(f"{m:.3f}±{s:.3f}")
        print(f"{name:30s} " + "  ".join(f"{c:>13s}" for c in cells))
    print("機會水準：" + "  ".join(f"@{k} = {k/60:.3f}" for k in (10, 5, 3, 1)))

    print()
    print(RULE)
    print("2. 物理一致性（不需要真值，上線後也算得出來）")
    print(RULE)
    for label, sub, pred in (
        ("id（OOF）", ds, oof),
        ("pool-dev", dev, preds[f"{model.name}（champion）"]),
    ):
        ce = conservation_error(sub, pred)
        pr = pde_residual_score(sub, pred)
        print(
            f"  {label:10s} 守恆誤差 median {np.median(ce):.5f} p95 {np.percentile(ce, 95):.5f}"
            f"   PDE 殘差 median {np.median(pr):.5f} p95 {np.percentile(pr, 95):.5f}"
        )
    base = make_baseline("greens_images").predict(dev)
    ce = conservation_error(dev, base)
    print(
        f"  {'（物理基準對照）':10s} 守恆誤差 median {np.median(ce):.5f} p95 {np.percentile(ce, 95):.5f}"
    )

    print()
    print(RULE)
    print("3. 誤差的結構驅動因子（跨 fold 一致性 < 0.5 的不要報）")
    print(RULE)
    for key, d in error_drivers(ds, oof).items():
        edges = np.array(d["edges"])
        centres = 0.5 * (edges[:-1] + edges[1:])
        print(f"  {key}   跨 fold 排序一致性 {d['fold_rank_agreement']:+.2f}")
        print("     分箱中心 " + "  ".join(f"{c:7.2f}" for c in centres))
        print("     Tmax MAE " + "  ".join(f"{v:7.3f}" for v in d["mae"]))
        print("     bias     " + "  ".join(f"{v:+7.3f}" for v in d["bias"]))

    print()
    print(RULE)
    print("4. 低估最嚴重的三筆（貴的那一側）")
    print(RULE)
    for c in worst_underestimates(ds, oof, k=3):
        print(
            f"  idx {c['index']:4d} fold {c['fold']}  真值 {c['tmax_true']:6.1f} °C  "
            f"預測 {c['tmax_pred']:6.1f} °C  低估 {c['underestimate']:5.2f} °C"
        )
        print(
            f"          m·Lx {c['m_lx']:.2f}   熱點到邊界 {c['hotspot_edge_distance_over_diffusion_length']:.2f} 個擴散長度"
            f"   元件數 {c['n_components']}   功率集中度 {c['power_concentration']:.1f}"
            f"   守恆誤差 {c['conservation_error']:.4f}"
        )

    print()
    print(RULE)
    print("5. 守恆誤差能不能當「這一筆可不可信」的線上訊號")
    print(RULE)
    ce_all = conservation_error(ds, oof)
    err = np.abs(
        oof.reshape(len(oof), -1).max(axis=1) - ds.temperature.reshape(len(ds), -1).max(axis=1)
    )
    q = np.quantile(ce_all, [0.0, 0.25, 0.5, 0.75, 0.9, 1.0])
    idx = np.clip(np.digitize(ce_all, q[1:-1]), 0, len(q) - 2)
    print("  守恆誤差分位   " + "  ".join(f"{a:.4f}-{b:.4f}" for a, b in zip(q[:-1], q[1:])))
    print("  該箱 Tmax MAE  " + "  ".join(f"{err[idx == b].mean():13.3f}" for b in range(len(q) - 1)))
    r = np.corrcoef(ce_all, err)[0, 1]
    print(f"  Spearman 式相關（Pearson on raw）{r:+.3f}")

    print()
    print(RULE)
    print("6. Local counterfactual：在參考板上，把驅動因子直接動一動")
    print(RULE)
    _counterfactuals(model)
    return 0


def _counterfactuals(model) -> None:
    """三個可行動的 counterfactual。

    第 3–5 節的驅動因子是**相關**，不是因果——分箱只說明「這一類佈局誤差大」。
    這一節在同一塊板上直接改一個量再量一次，所以它是**干預**：
    誤差的變化是那個改動造成的，不是別的東西共變。

    這仍然不是對「真實世界」的因果宣稱，是對**模型行為**的因果宣稱。
    """
    from thermoforge import dataset
    from thermoforge.copilot.board import load_board
    from thermoforge.solver import solve_layout

    board = load_board("configs/reference_board.yaml")
    hot = board.index_of("cpu")

    def err_of(b) -> tuple[float, float]:
        layout = b.to_layout()
        _, truth = solve_layout(layout)
        pred = model.predict(dataset.from_layouts([layout]))[0]
        return float(pred.max() - truth.max()), float(truth.max())

    print("  (a) 把 CPU 從貼邊移到板中央 —— 驅動因子「熱點到邊界距離」")
    m = np.sqrt(board.h_conv / board.kt)
    base_positions = [(nc.component.cx, nc.component.cy) for nc in board.components]
    w = board.components[hot].component.w
    for cx in (w / 2 + 0.005, 0.030, 0.055, 0.085, 0.110):
        pos = list(base_positions)
        pos[hot] = (cx, board.ly / 2)
        e, t = err_of(board.with_positions(pos))
        d_edge = min(cx, board.lx - cx, board.ly / 2, board.ly / 2) * m
        print(f"      CPU 中心 x={1000*cx:5.1f} mm（距邊界 {d_edge:.2f} 擴散長度）"
              f"  真值 {t:6.2f} °C  誤差 {e:+.3f} °C")

    print("  (b) 把 CPU 的功率往上集中（其餘元件不動）—— 驅動因子「功率集中度」")
    for p_cpu in (10.0, 25.5, 35.0, 45.0):
        e, t = err_of(board.with_power(hot, p_cpu))
        print(f"      CPU {p_cpu:5.1f} W  真值 {t:6.2f} °C  誤差 {e:+.3f} °C")

    print("  (c) 改變對流係數 —— 驅動因子「m·Lx」")
    for h in (20.0, 40.0, 70.0, 80.0, 110.0):
        e, t = err_of(board.with_conditions(h_conv=h))
        note = "" if 15 <= h <= 80 else "  ← 已推出訓練分佈"
        print(f"      h={h:6.1f} W/m²K（m·Lx {np.sqrt(h/board.kt)*board.lx:.2f}）"
              f"  真值 {t:6.2f} °C  誤差 {e:+.3f} °C{note}")


if __name__ == "__main__":
    raise SystemExit(main())
