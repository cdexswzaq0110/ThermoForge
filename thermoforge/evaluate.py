"""評估迴圈——OOF、候選池、OOD holdout 三種評估的唯一入口。

## 三種評估各自回答什麼

| 評估 | 資料 | 回答 | 可以看幾次 |
|---|---|---|---|
| **OOF** | id 的 5 個 fold | 場預測有多準、低估多不多 | 無限次 |
| **pool-dev** | 候選池 dev 半邊 | **主要 metric**：篩選能力 | 無限次 |
| **frozen** | OOD holdout ＋ pool-frozen | 外推會不會崩 | **整個專案一次** |

前兩者由 `evaluate_development` 一起跑；第三個在 `thermoforge.frozen`，
需要 `--confirm` 並寫進解凍帳本。分成兩個入口不是禮貌，是讓
「不小心看了 holdout」變成一件要刻意做才做得到的事。

## OOF 的實作契約

每一列都由**沒看過它的那個 fold model** 預測。predictor 每個 fold 都重新建立，
`fit` 只拿得到 training fold 的 `Dataset`——想洩漏也沒有管道（見 `predictors.py`）。
"""

from __future__ import annotations

import time
from typing import Callable

import numpy as np

from .dataset import Dataset
from .metrics import FieldMetrics, evaluate_fields, screening_recall_within_pools
from .predictors import Predictor

__all__ = ["run_oof", "evaluate_development", "tmax"]

MakePredictor = Callable[[], Predictor]


def tmax(fields: np.ndarray) -> np.ndarray:
    """(n, ny, nx) → (n,) 熱點溫度。"""
    return fields.reshape(len(fields), -1).max(axis=1)


def run_oof(make: MakePredictor, ds_id: Dataset, n_folds: int = 5) -> tuple[np.ndarray, list[FieldMetrics]]:
    """回傳 (OOF 預測, 每個 fold 的 metrics)。

    每個 fold 的 metrics 分開回傳，是因為 Gate 3 要判斷「改善是否大於 fold noise」——
    只給一個總分的話那個判斷做不了，而不做那個判斷就會把噪音當成進步。
    """
    folds = ds_id.folds
    oof = np.full(ds_id.temperature.shape, np.nan, dtype=np.float64)
    per_fold: list[FieldMetrics] = []

    present = set(int(f) for f in np.unique(folds))
    expected = set(range(n_folds))
    if present != expected:
        raise ValueError(
            f"資料集的 fold 是 {sorted(present)}，但要求跑 {n_folds} 折。"
            "空的 fold 會讓 metrics 變成 NaN 而不是報錯——那種綠燈最貴。"
        )

    for f in range(n_folds):
        val_mask = folds == f
        train = ds_id.subset(~val_mask)
        val = ds_id.subset(val_mask)

        model = make()
        model.fit(train)
        pred = model.predict(val)

        oof[val_mask] = pred
        per_fold.append(evaluate_fields(pred, val.temperature.astype(np.float64)))

    if np.isnan(oof).any():
        raise AssertionError("有列沒有被任何 fold 預測到——fold 指派不完整")
    return oof, per_fold


def evaluate_development(
    make: MakePredictor,
    ds_id: Dataset,
    pools_dev: Dataset,
    n_folds: int = 5,
) -> dict:
    """開發期的完整評估。**不碰 frozen 的任何東西。**

    候選池的預測器在**全部 id 資料**上 fit——候選池的 base layout 與 id 不相交，
    而且池只用來評估、永遠不進訓練，所以這裡不需要 fold。
    """
    t0 = time.perf_counter()
    oof, per_fold = run_oof(make, ds_id, n_folds=n_folds)
    oof_time = time.perf_counter() - t0

    truth = ds_id.temperature.astype(np.float64)
    overall = evaluate_fields(oof, truth)

    model = make()
    model.fit(ds_id)
    t1 = time.perf_counter()
    pool_pred = model.predict(pools_dev)
    pool_latency_ms = 1000.0 * (time.perf_counter() - t1) / max(len(pools_dev), 1)

    pool_truth = pools_dev.temperature.astype(np.float64)
    recall_mean, recall_std = screening_recall_within_pools(
        tmax(pool_pred), tmax(pool_truth), pools_dev.arrays["pool_id"], k=10
    )

    fold_tmax_mae = [m.tmax_mae for m in per_fold]
    return {
        "oof": overall.as_dict(),
        "oof_per_fold_tmax_mae": fold_tmax_mae,
        "oof_fold_noise_std": float(np.std(fold_tmax_mae)),
        "pool_dev": evaluate_fields(pool_pred, pool_truth).as_dict(),
        "screening_recall_mean": recall_mean,
        "screening_recall_std": recall_std,
        "inference_ms_per_layout": pool_latency_ms,
        "oof_seconds": round(oof_time, 2),
    }
