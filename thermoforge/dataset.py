"""資料集載入與**無因次化**。

## 無因次化：本專案最重要的一個建模決策

原始問題有六個會變的量（板長寬、kt、h、總功率、T_amb），但方程

    ∇²θ − m²θ = −p/kt

只透過兩件事依賴它們：核的寬度 1/m，以及整體的溫度尺度。把它們除掉之後，
模型只需要學一個**形狀函數**。

兩個尺度都是精確可算的，不是估的：

- **溫度尺度** θ_ref = P/(h·A)。這是能量守恆的直接結果（絕熱邊界下
  h·∫θ dA ≡ P），所以無因次目標 θ/θ_ref 的**空間平均恆等於 1**。
  這條可以拿來驗模型輸出（見 `mean_of_normalised_target_is_one`）。
- **長度尺度** 1/m = √(kt/h)，以 m·Lx、m·Ly 兩個無因次數進入模型。

## 它換到什麼

功率外推變成**恆等式**而不是學習問題：θ 對 P 線性，除以 θ_ref 之後 P 就完全消失了。
所以做完無因次化的模型在 `ood_power` 上的表現，理論上應該與 id 相同。

這句話是可證偽的，而且 `experiments/` 裡的 `direct` 對照組就是為了證偽它而存在——
少了無因次化的同一個網路在同一份 folds 上跑，兩邊的 `ood_power` 分數差多少，
就是這個決策實際值多少。**不做這個對照，無因次化就只是一個聽起來合理的說法。**
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

__all__ = ["Dataset", "load", "from_layouts"]

#: 每一份資料集都必須有的欄位。npz 裡多出來的欄位（`pool_id`、`split_code` …）
#: 一律照收——白名單會讓候選池那種帶額外欄位的資料集安靜地掉欄位，
#: 而掉欄位的症狀是後面某個 KeyError，指不回這裡。
REQUIRED_KEYS = (
    "power_map",
    "temperature",
    "kt",
    "h_conv",
    "t_amb",
    "lx",
    "ly",
    "total_power",
)


@dataclass(frozen=True)
class Dataset:
    """一份資料集（或它的子集）。所有陣列的第 0 維對齊。"""

    arrays: dict[str, np.ndarray]
    regime_names: list[str]
    manifest: dict

    def __len__(self) -> int:
        return len(self.arrays["kt"])

    def __getattr__(self, name: str) -> np.ndarray:
        try:
            return self.arrays[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    # --- 子集 -------------------------------------------------------------

    def subset(self, mask: np.ndarray) -> "Dataset":
        mask = np.asarray(mask)
        return Dataset(
            arrays={k: v[mask] for k, v in self.arrays.items()},
            regime_names=self.regime_names,
            manifest=self.manifest,
        )

    def regime(self, name: str) -> "Dataset":
        if name not in self.regime_names:
            raise KeyError(f"未知 regime {name!r}，可用：{self.regime_names}")
        return self.subset(self.arrays["regime_code"] == self.regime_names.index(name))

    def split(self, name: str) -> "Dataset":
        """候選池專用：取 `dev` 或 `frozen` 半邊。"""
        names = self.manifest.get("split_names", [])
        if name not in names:
            raise KeyError(f"未知 split {name!r}，可用：{names}")
        return self.subset(self.arrays["split_code"] == names.index(name))

    @property
    def id_only(self) -> "Dataset":
        """只有 in-distribution 的部分。OOD 的 fold 一律是 -1。"""
        return self.subset(self.arrays["fold"] >= 0)

    @property
    def ood_only(self) -> "Dataset":
        return self.subset(self.arrays["fold"] < 0)

    @property
    def folds(self) -> np.ndarray:
        """每列的 validation fold 編號；OOD 為 -1。"""
        return self.arrays["fold"]

    def select_fold(self, f: int, invert: bool = False) -> "Dataset":
        """`invert=True` 取「這個 fold 以外的 in-distribution 資料」，也就是 training fold。

        名字不叫 `fold` 是因為陣列本身也叫 fold——同名的屬性與方法會讓
        `ds.fold` 這個看起來最自然的寫法安靜地回傳一個 bound method。"""
        mask = self.arrays["fold"] == f
        return self.subset(~mask & (self.arrays["fold"] >= 0) if invert else mask)

    # --- 無因次化 ----------------------------------------------------------

    @property
    def area(self) -> np.ndarray:
        return self.arrays["lx"] * self.arrays["ly"]

    @property
    def theta_ref(self) -> np.ndarray:
        """溫度尺度 P/(h·A)。與 `theta_avg` 恆等——留兩個名字是因為
        一個是取樣時的**輸入**，一個是推論時可從已知量算出的**特徵**。"""
        return self.arrays["total_power"] / (self.arrays["h_conv"] * self.area)

    @property
    def m(self) -> np.ndarray:
        """1/擴散長度，單位 1/m。"""
        return np.sqrt(self.arrays["h_conv"] / self.arrays["kt"])

    @property
    def p_norm(self) -> np.ndarray:
        """無因次功率圖，空間平均恆為 1。形狀 (n, ny, nx)。"""
        scale = (self.arrays["total_power"] / self.area)[:, None, None]
        return self.arrays["power_map"] / scale

    @property
    def theta_norm(self) -> np.ndarray:
        """無因次溫升場，空間平均恆為 1（能量守恆）。形狀 (n, ny, nx)。"""
        theta = self.arrays["temperature"] - self.arrays["t_amb"][:, None, None]
        return theta / self.theta_ref[:, None, None]

    @property
    def scalars(self) -> np.ndarray:
        """給模型的無因次純量特徵：(m·Lx, m·Ly)。形狀 (n, 2)。

        只有兩個，而且都無因次——這不是簡化，是方程真正依賴的全部。
        再多餵 kt、h、P 進去只會給模型機會去記住訓練分佈的邊界。
        """
        return np.stack([self.m * self.arrays["lx"], self.m * self.arrays["ly"]], axis=1)

    def to_temperature(self, theta_norm: np.ndarray) -> np.ndarray:
        """無因次預測 → 溫度場 [°C]。推論路徑的最後一步。"""
        return (
            theta_norm * self.theta_ref[:, None, None]
            + self.arrays["t_amb"][:, None, None]
        )


def load(npz_path: str | Path) -> Dataset:
    npz_path = Path(npz_path)
    manifest_path = npz_path.with_suffix("").with_suffix(".manifest.json")
    if not manifest_path.exists():
        manifest_path = npz_path.parent / f"{npz_path.stem}.manifest.json"

    with np.load(npz_path) as z:
        arrays = {k: z[k] for k in z.files}

    # 物理基準場的快取（`thermoforge.precompute_greens`）。它是輸入的一部分，
    # 不是從資料估出來的參數，所以整批算好不構成 leakage——見那個模組的 docstring。
    greens_path = npz_path.parent / f"{npz_path.stem}.greens.npy"
    if greens_path.exists():
        greens = np.load(greens_path)
        if len(greens) != len(arrays["kt"]):
            raise ValueError(
                f"{greens_path} 有 {len(greens)} 列，資料集有 {len(arrays['kt'])} 列——"
                "資料重生成過但快取沒更新，重跑 thermoforge.precompute_greens"
            )
        arrays["greens_norm"] = greens
    missing = [k for k in REQUIRED_KEYS if k not in arrays]
    if missing:
        raise ValueError(f"{npz_path} 缺欄位 {missing}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return Dataset(arrays=arrays, regime_names=list(manifest["regime_names"]), manifest=manifest)


def from_layouts(layouts, ny: int = 64, nx: int = 64) -> Dataset:
    """把一組 `Layout` 包成可以餵給 `Predictor.predict` 的 `Dataset`。**不呼叫求解器。**

    `temperature` 填 NaN——推論路徑上真值本來就不存在，填 0 會讓
    「不小心拿它算 metric」變成一個安靜的錯誤（分數會很難看但不會報錯）。
    NaN 會讓那個錯誤立刻現形。
    """
    from .geometry import rasterize_power

    n = len(layouts)
    power_map = np.stack([rasterize_power(lay, ny, nx) for lay in layouts]).astype(np.float32)
    arrays = {
        "power_map": power_map,
        "temperature": np.full((n, ny, nx), np.nan, dtype=np.float32),
        "kt": np.array([lay.kt for lay in layouts], dtype=np.float64),
        "h_conv": np.array([lay.h_conv for lay in layouts], dtype=np.float64),
        "t_amb": np.array([lay.t_amb for lay in layouts], dtype=np.float64),
        "lx": np.array([lay.lx for lay in layouts], dtype=np.float64),
        "ly": np.array([lay.ly for lay in layouts], dtype=np.float64),
        "total_power": np.array([lay.total_power for lay in layouts], dtype=np.float64),
        "n_components": np.array([len(lay.components) for lay in layouts], dtype=np.int64),
        "base_id": np.arange(n, dtype=np.int64),
        "fold": np.full(n, -1, dtype=np.int64),
    }
    return Dataset(arrays=arrays, regime_names=["inference"], manifest={"regime_names": ["inference"]})
