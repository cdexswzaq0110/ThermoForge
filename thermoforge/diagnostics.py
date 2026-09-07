"""Stage 6：可解釋性——但問的是**物理**，不是特徵重要性。

## 開始前的四題（`se-ml-lifecycle` Stage 6）

| 題 | 答 |
|---|---|
| 誰要看 | 熱設計工程師（領域專家，L2 語域） |
| 要回答什麼 | 「模型整體靠什麼、在哪會錯」——不是「這一筆為什麼」 |
| 看完做什麼決定 | **哪一類佈局可以信代理模型，哪一類一定要送求解器** |
| 需要因果嗎 | 不需要。這裡只講模型依賴什麼，不講改了會怎樣 |

第三題有答案，所以這一階段值得做。答不出來的話產出的是一張沒人看的長條圖。

## 為什麼不是 SHAP

輸入是一張 64×64 的場，不是一組欄位。對 4096 個像素做 attribution 得到的是
「熱點附近的像素比較重要」——真的，但沒有資訊量，因為物理已經說了。

場預測有一個表格模型沒有的東西：**它應該滿足一個方程**。所以更有力的問法是
「模型的輸出違反那個方程多少、違反在哪裡」。這是 SHAP 給不了的，
而且它直接對應第三題的決策。

三個診斷：

1. **PDE 殘差場** —— 把預測代回 ∇²θ − m²θ + f，看哪裡不等於零。
2. **能量守恆誤差** —— 預測的 h·∫θ dA 與實際總功率差多少。無因次空間裡
   這等於「θ_norm 的空間平均偏離 1 多少」，是一個精確的純量。
3. **誤差的結構驅動因子** —— 把 OOF 熱點誤差依幾何與物理量分箱，
   找出模型在哪一類佈局上會錯，並檢查那個排序**跨 fold 穩不穩**。

## 前置條件

**Gate 1 沒過不要做這一階段。** 解釋一個有 leakage 的模型，解釋出來的是那個洩漏源。
本專案的 Gate 1 證據在 `docs/03-data-contract.md`。
"""

from __future__ import annotations

import numpy as np

from .dataset import Dataset

__all__ = [
    "pde_residual",
    "pde_residual_score",
    "conservation_error",
    "error_drivers",
    "worst_underestimates",
]


def pde_residual(
    temperature: np.ndarray, power_map: np.ndarray, kt: float, h_conv: float, dy: float, dx: float
) -> np.ndarray:
    """把一個溫度場代回 ∇²θ − m²θ + f，回傳殘差場（單位 1/m² × K）。

    用與求解器**相同**的離散算子與邊界處理（鏡像 ghost cell ＝ Neumann）。
    相同不是偷懶——不同的離散化會讓真解也產生殘差，那個殘差會被誤讀成模型的問題。
    `tests/test_diagnostics.py::test_true_solution_has_zero_residual` 釘住這一條。
    """
    theta = temperature
    padded = np.pad(theta, 1, mode="edge")
    lap = (
        (padded[1:-1, 2:] - 2 * theta + padded[1:-1, :-2]) / dx**2
        + (padded[2:, 1:-1] - 2 * theta + padded[:-2, 1:-1]) / dy**2
    )
    return lap - (h_conv / kt) * theta + power_map / kt


def pde_residual_score(ds: Dataset, pred_temperature: np.ndarray) -> np.ndarray:
    """每一筆的**無因次**殘差範數：‖r‖∞ / max(f)。0 代表完全滿足方程。

    除以 max(f) 是為了讓不同功率尺度的樣本可比——沒有正規化的話，
    這個分數會只是在排「哪一塊板比較燙」。
    """
    n = len(ds)
    out = np.empty(n)
    theta = pred_temperature - ds.t_amb[:, None, None]
    for i in range(n):
        dy, dx = ds.ly[i] / theta.shape[1], ds.lx[i] / theta.shape[2]
        f = ds.power_map[i] / ds.kt[i]
        r = pde_residual(
            theta[i], ds.power_map[i].astype(np.float64), float(ds.kt[i]), float(ds.h_conv[i]), dy, dx
        )
        scale = np.abs(f).max()
        out[i] = np.abs(r).max() / scale if scale > 0 else np.nan
    return out


def conservation_error(ds: Dataset, pred_temperature: np.ndarray) -> np.ndarray:
    """每一筆的相對能量守恆誤差：|h·∫θ̂ dA − P| / P。

    這是一個**精確**的物理約束，模型沒有被要求滿足它。所以它同時是
    「模型有沒有學到守恆」的量尺，與「這一筆可不可信」的一個獨立訊號——
    獨立於真值，因此推論時也算得出來。
    """
    theta = pred_temperature - ds.t_amb[:, None, None]
    cell_area = (ds.lx / theta.shape[2]) * (ds.ly / theta.shape[1])
    dissipated = ds.h_conv * theta.sum(axis=(1, 2)) * cell_area
    return np.abs(dissipated - ds.total_power) / ds.total_power


def _edge_distance(ds: Dataset) -> np.ndarray:
    """功率最大的格點到最近板緣的距離，以熱擴散長度 1/m 為單位。

    用無因次距離而不是公釐：熱被邊界困住的程度取決於「離邊界幾個擴散長度」，
    公釐在不同 h 之下不可比。
    """
    n, ny, nx = ds.power_map.shape
    flat = ds.power_map.reshape(n, -1).argmax(axis=1)
    iy, ix = np.unravel_index(flat, (ny, nx))
    y = (iy + 0.5) * ds.ly / ny
    x = (ix + 0.5) * ds.lx / nx
    d = np.minimum(np.minimum(x, ds.lx - x), np.minimum(y, ds.ly - y))
    return d * ds.m


def error_drivers(ds: Dataset, oof: np.ndarray, n_bins: int = 5) -> dict:
    """把 OOF 熱點誤差依四個結構因子分箱，並檢查排序跨 fold 穩不穩。

    回傳 `{factor: {"edges", "mae", "bias", "n", "fold_rank_agreement"}}`。

    `fold_rank_agreement` 是「用單一 fold 的資料算出的分箱 MAE 排序，
    與用全部資料算出的排序，Spearman 相關的平均」。**跨 fold 不穩的排序不要報**
    （Stage 6 硬規則第 2 條）——不穩就只能說「沒有穩定的主導因子」。
    """
    err = oof.reshape(len(oof), -1).max(axis=1) - ds.temperature.reshape(len(ds), -1).max(axis=1)
    factors = {
        "hotspot_edge_distance_over_diffusion_length": _edge_distance(ds),
        "m_times_lx": ds.m * ds.lx,
        "n_components": ds.n_components.astype(float),
        "power_concentration": ds.p_norm.reshape(len(ds), -1).max(axis=1),
    }

    out: dict[str, dict] = {}
    for name, values in factors.items():
        edges = np.unique(np.quantile(values, np.linspace(0, 1, n_bins + 1)))
        idx = np.clip(np.digitize(values, edges[1:-1]), 0, len(edges) - 2)
        mae = np.array([np.abs(err[idx == b]).mean() if (idx == b).any() else np.nan
                        for b in range(len(edges) - 1)])
        bias = np.array([err[idx == b].mean() if (idx == b).any() else np.nan
                         for b in range(len(edges) - 1)])
        counts = np.array([int((idx == b).sum()) for b in range(len(edges) - 1)])

        agreements = []
        for f in np.unique(ds.folds):
            mask = ds.folds == f
            fold_mae = np.array(
                [np.abs(err[mask & (idx == b)]).mean() if (mask & (idx == b)).any() else np.nan
                 for b in range(len(edges) - 1)]
            )
            ok = ~np.isnan(fold_mae) & ~np.isnan(mae)
            if ok.sum() >= 3:
                agreements.append(_spearman(fold_mae[ok], mae[ok]))
        out[name] = {
            "edges": edges.tolist(),
            "mae": mae.tolist(),
            "bias": bias.tolist(),
            "n": counts.tolist(),
            "fold_rank_agreement": float(np.mean(agreements)) if agreements else float("nan"),
        }
    return out


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    denom = np.sqrt((ra**2).sum() * (rb**2).sum())
    return float((ra * rb).sum() / denom) if denom > 0 else float("nan")


def worst_underestimates(ds: Dataset, oof: np.ndarray, k: int = 3) -> list[dict]:
    """低估最嚴重的 k 筆，附上可行動的說明。

    只看低估側，因為那是貴的那一側（問題定義第 5 題）。每一筆給出
    「這個模型在這種佈局上不可信」需要的具體特徵，讓工程師認得出下一次遇到同類型。
    """
    tmax_pred = oof.reshape(len(oof), -1).max(axis=1)
    tmax_true = ds.temperature.reshape(len(ds), -1).max(axis=1)
    err = tmax_pred - tmax_true
    edge = _edge_distance(ds)
    order = np.argsort(err)[:k]

    cases = []
    for i in order:
        cases.append(
            {
                "index": int(i),
                "fold": int(ds.folds[i]),
                "tmax_true": float(tmax_true[i]),
                "tmax_pred": float(tmax_pred[i]),
                "underestimate": float(-err[i]),
                "m_lx": float(ds.m[i] * ds.lx[i]),
                "hotspot_edge_distance_over_diffusion_length": float(edge[i]),
                "n_components": int(ds.n_components[i]),
                "power_concentration": float(ds.p_norm[i].max()),
                "conservation_error": float(conservation_error(ds.subset(np.array([i])), oof[i][None])[0]),
            }
        )
    return cases
