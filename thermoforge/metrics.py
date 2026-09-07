"""評估指標——每一個都連回 `docs/01-problem-statement.md` 的某一問。

## 為什麼不是只報 MAE

第 5 題：錯誤成本**不對稱**。低估熱點會讓過熱的板子通過篩選、一路走到量產；
高估只是多花散熱成本。一個整場 MAE 0.3 °C、但在高功率佈局上系統性低估 8 °C 的模型，
用 MAE 看是好模型，用決策看是危險模型。

所以這裡的契約是：**任何回報都必須同時帶 under_rate。**
`CONTEXT.md` 的 flagged ambiguity 第 2 條把這件事寫成專案詞彙層的規定。

## 主要 metric 是篩選召回率，不是誤差

第 1 題：代理模型負責的是**篩選**，不是判定。所以真正要量的是
「用預測排序取前 K 名，真實最優 K 名留住了幾個」。

這個 metric 有一個誤差指標沒有的性質：它對**單調的**系統性偏差免疫。
一個把所有溫度都高估 5 °C 的模型，MAE 很差，但篩選能力完好。
反過來，一個 MAE 很低但在熱點附近排序錯亂的模型，篩選能力是壞的。
量錯了會導向完全相反的模型選擇。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

__all__ = [
    "FieldMetrics",
    "evaluate_fields",
    "screening_recall_at_k",
    "screening_recall_within_pools",
]

#: 低估容忍值（°C）。小於這個幅度的低估不計入 under_rate——
#: 求解器本身的網格離散化誤差就在這個量級，把它算成模型缺陷會製造假訊號。
DEFAULT_UNDER_TOL = 1.0


@dataclass(frozen=True)
class FieldMetrics:
    """一組預測溫度場對上真值的評估結果。單位一律 °C。"""

    n: int
    field_mae: float
    field_rmse: float
    field_max_abs: float
    tmax_mae: float
    tmax_bias: float
    under_rate: float
    under_p95: float

    def as_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        """一行摘要。**永遠同時帶低估率**——這是這個型別存在的理由之一。"""
        return (
            f"n={self.n} field_MAE={self.field_mae:.3f}C "
            f"Tmax_MAE={self.tmax_mae:.3f}C bias={self.tmax_bias:+.3f}C "
            f"under_rate={self.under_rate:.1%} under_p95={self.under_p95:.2f}C"
        )


def evaluate_fields(
    pred: np.ndarray,
    true: np.ndarray,
    under_tol: float = DEFAULT_UNDER_TOL,
) -> FieldMetrics:
    """`pred`、`true` 形狀皆為 (n, ny, nx)，單位 °C。"""
    if pred.shape != true.shape:
        raise ValueError(f"形狀不符：pred {pred.shape} vs true {true.shape}")
    if pred.ndim != 3:
        raise ValueError("需要 (n, ny, nx)；單筆請先 reshape 成 (1, ny, nx)")

    err = pred - true
    tmax_pred = pred.reshape(len(pred), -1).max(axis=1)
    tmax_true = true.reshape(len(true), -1).max(axis=1)
    tmax_err = tmax_pred - tmax_true

    # 低估幅度：只取 pred < true 的那一側，正值代表低估了幾度。
    under = np.clip(-tmax_err, 0.0, None)

    return FieldMetrics(
        n=int(len(pred)),
        field_mae=float(np.abs(err).mean()),
        field_rmse=float(np.sqrt((err**2).mean())),
        field_max_abs=float(np.abs(err).max()),
        tmax_mae=float(np.abs(tmax_err).mean()),
        tmax_bias=float(tmax_err.mean()),
        under_rate=float((under > under_tol).mean()),
        under_p95=float(np.percentile(under, 95)),
    )


def screening_recall_at_k(
    pred_tmax: np.ndarray,
    true_tmax: np.ndarray,
    k: int = 20,
    pool_size: int = 200,
    n_pools: int = 200,
    seed: int = 0,
) -> tuple[float, float]:
    """主要 metric：篩選召回率的 (平均, 標準差)。

    模擬第 1 題描述的實際用法——從 `pool_size` 個候選佈局中，用**預測**熱點溫度
    取最涼的 K 個送求解器確認，問**真實**最涼的 K 個留住了幾成。

    重複抽 `n_pools` 個 pool 而不是只算一次全體排名，是因為單一數字看不出
    「這個召回率有多穩」。回傳標準差讓 Gate 3 能判斷改善是否大於噪音
    （`se-ml-lifecycle` Stage 4）。
    """
    pred_tmax = np.asarray(pred_tmax).ravel()
    true_tmax = np.asarray(true_tmax).ravel()
    if pred_tmax.shape != true_tmax.shape:
        raise ValueError("pred_tmax 與 true_tmax 長度不符")
    n = len(pred_tmax)
    if n < 2:
        raise ValueError("至少需要兩個候選才談得上排序")

    pool_size = min(pool_size, n)
    k = min(k, pool_size)
    rng = np.random.default_rng(seed)

    recalls = np.empty(n_pools)
    for t in range(n_pools):
        idx = rng.choice(n, size=pool_size, replace=False)
        chosen = idx[np.argsort(pred_tmax[idx], kind="stable")[:k]]
        best = idx[np.argsort(true_tmax[idx], kind="stable")[:k]]
        recalls[t] = len(set(chosen.tolist()) & set(best.tolist())) / k

    return float(recalls.mean()), float(recalls.std())


def screening_recall_within_pools(
    pred_tmax: np.ndarray,
    true_tmax: np.ndarray,
    pool_id: np.ndarray,
    k: int = 10,
) -> tuple[float, float]:
    """主要 metric 的**正式**版本：在候選池內算召回率，回傳跨池的 (平均, 標準差)。

    與 `screening_recall_at_k` 的差別不是實作細節，是效度。後者從一個混合了
    不同板子、不同功率、不同散熱條件的資料集裡隨機抽 pool，於是「哪一列比較涼」
    大部分由 P/(h·A) 決定——一個完全不看佈局的公式在那裡能拿到 0.6
    【已確認：見 thermoforge/data/pools.py 的實測數字】。

    候選池內那些條件全部固定，所以這個函式量到的只剩佈局。**報告主要 metric 一律用這一個。**
    """
    pred_tmax = np.asarray(pred_tmax).ravel()
    true_tmax = np.asarray(true_tmax).ravel()
    pool_id = np.asarray(pool_id).ravel()
    if not (pred_tmax.shape == true_tmax.shape == pool_id.shape):
        raise ValueError("pred_tmax、true_tmax 與 pool_id 長度必須一致")

    recalls = []
    for pid in np.unique(pool_id):
        idx = np.flatnonzero(pool_id == pid)
        kk = min(k, len(idx))
        chosen = set(idx[np.argsort(pred_tmax[idx], kind="stable")[:kk]].tolist())
        best = set(idx[np.argsort(true_tmax[idx], kind="stable")[:kk]].tolist())
        recalls.append(len(chosen & best) / kk)

    arr = np.asarray(recalls)
    return float(arr.mean()), float(arr.std())
