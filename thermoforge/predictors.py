"""預測器的統一介面，以及三個不需要學習的基準。

所有候選——基準與神經網路——都實作同一個介面：

    fit(train: Dataset) -> None      # 只能看 training fold
    predict(ds: Dataset) -> (n, ny, nx) 溫度場 [°C]

`fit` 收 `Dataset` 而不是預先算好的張量，是為了讓「fit 型處理只能在 training fold 內」
這條（`CLAUDE.md` 預設節奏第 3 條）在型別層就成立：預測器拿不到全體資料，
想洩漏也沒有管道。正規化常數、平均場、任何統計量都必須在這個方法裡算。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from .baselines import greens_temperature
from .dataset import Dataset

__all__ = ["Predictor", "MeanFieldPredictor", "GreensPredictor", "make_baseline"]


@runtime_checkable
class Predictor(Protocol):
    name: str

    def fit(self, train: Dataset) -> None: ...

    def predict(self, ds: Dataset) -> np.ndarray: ...


class MeanFieldPredictor:
    """基準 A：預測 training fold 的平均**無因次**溫升場，再乘回這一筆的尺度。

    在無因次空間取平均而不是直接平均溫度場，是刻意讓這個 dummy 也拿到
    能量守恆帶來的那份資訊——否則它會弱到沒有鑑別力，而一個太弱的下限
    會讓任何模型看起來都很成功。
    """

    name = "mean_field"

    def __init__(self) -> None:
        self.mean_theta_norm_: np.ndarray | None = None

    def fit(self, train: Dataset) -> None:
        self.mean_theta_norm_ = train.theta_norm.mean(axis=0)

    def predict(self, ds: Dataset) -> np.ndarray:
        if self.mean_theta_norm_ is None:
            raise RuntimeError("尚未 fit")
        return ds.to_temperature(np.broadcast_to(self.mean_theta_norm_, ds.power_map.shape))


class GreensPredictor:
    """基準 B／B+：Green's function 疊加。不需要訓練，`fit` 是空操作。

    `fit` 留著空的而不是刪掉，是因為評估迴圈對所有候選一視同仁——
    一旦某個候選需要特別對待，「這個模型有沒有偷看驗證集」就變成要靠讀程式碼判斷。
    """

    def __init__(self, images: int = 0) -> None:
        self.images = images
        self.name = "greens_free" if images == 0 else "greens_images"

    def fit(self, train: Dataset) -> None:  # noqa: ARG002 - 見 docstring
        return None

    def predict(self, ds: Dataset) -> np.ndarray:
        out = np.empty_like(ds.power_map, dtype=np.float64)
        for i in range(len(ds)):
            out[i] = greens_temperature(
                ds.power_map[i].astype(np.float64),
                float(ds.kt[i]),
                float(ds.h_conv[i]),
                float(ds.lx[i]),
                float(ds.ly[i]),
                float(ds.t_amb[i]),
                images=self.images,
            )
        return out


def make_baseline(name: str) -> Predictor:
    if name == "mean_field":
        return MeanFieldPredictor()
    if name == "greens_free":
        return GreensPredictor(images=0)
    if name == "greens_images":
        return GreensPredictor(images=1)
    raise KeyError(f"未知基準 {name!r}")
