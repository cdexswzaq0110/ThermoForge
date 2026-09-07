"""物理基準——代理模型真正要打敗的對手。

`docs/01-problem-statement.md` 第 6 題：這題有解析近似解，拿「預測訓練集平均場」
當基準等於自欺。所以這裡實作的不是 dummy，是一個懂物理的工程師會手算的東西。

## 用的是什麼

方程 ∇²θ − m²θ = −f 在無限大平面上的 Green's function 是

    G(r) = K₀(m·r) / (2π)

於是自由空間近似解就是把每個網格單元的功率當點源疊加：

    θ(x) = Σⱼ fⱼ · A_cell · K₀(m·|x − xⱼ|) / (2π)

因為網格等距，這個疊加是一個**卷積**，用 FFT 算 O(N log N)——與求解器同一個量級，
所以它不只是理論基準，是一個真的可以拿來用的方法。

## 兩個已知弱點（也就是神經網路的機會）

1. **自作用項發散**：r → 0 時 K₀ → ∞。用等效圓盤上的解析積分取代對角項，
   而不是隨便填一個大數——填數字會讓熱點溫度變成一個可調參數。
2. **無視邊界**：自由空間解假設熱可以散到無限遠，但真板子四邊絕熱，熱被困在板內。
   所以它**系統性低估**溫度，而且離邊界越近低估越多。低估正是本專案最貴的錯誤方向
   （`docs/01-problem-statement.md` 第 5 題），因此 `images=1` 用一階鏡像源補這一項。

一階鏡像只反射四面牆各一次，不含角落與高階反射——它仍然是近似，
不是把求解器換個寫法重寫一遍。
"""

from __future__ import annotations

import numpy as np
from scipy.signal import fftconvolve
from scipy.special import k0, k1

__all__ = [
    "greens_kernel",
    "greens_temperature",
    "greens_theta_norm",
    "MeanFieldBaseline",
]


def greens_kernel(ny: int, nx: int, m: float, dy: float, dx: float) -> np.ndarray:
    """(2·ny−1, 2·nx−1) 的離散 Green's function 核，已含單元面積權重。

    對角項（r = 0）用等效圓盤 a = √(A_cell/π) 上的解析積分

        ∫₀^a K₀(m r) r dr = [1 − m·a·K₁(m·a)] / m²

    取代，避免 K₀ 的對數發散被一個任意常數蓋掉。
    """
    cell_area = dx * dy
    iy = np.arange(-(ny - 1), ny)[:, None] * dy
    ix = np.arange(-(nx - 1), nx)[None, :] * dx
    r = np.hypot(iy, ix)

    kernel = np.empty_like(r)
    off = r > 0.0
    kernel[off] = cell_area * k0(m * r[off]) / (2.0 * np.pi)

    a = np.sqrt(cell_area / np.pi)
    kernel[~off] = (1.0 - m * a * k1(m * a)) / m**2
    return kernel


def _mirror_extend(f: np.ndarray) -> np.ndarray:
    """一階鏡像：把源場對四面牆各反射一次，角落留空。

    角落不填是刻意的——填了就往「用鏡像把 Neumann 邊界解精確重建」的方向滑過去，
    那等於把求解器換個寫法再寫一次，基準就失去了「近似」的身分。
    """
    ny, nx = f.shape
    ext = np.zeros((3 * ny, 3 * nx), dtype=f.dtype)
    ext[ny : 2 * ny, nx : 2 * nx] = f
    ext[0:ny, nx : 2 * nx] = np.flipud(f)
    ext[2 * ny : 3 * ny, nx : 2 * nx] = np.flipud(f)
    ext[ny : 2 * ny, 0:nx] = np.fliplr(f)
    ext[ny : 2 * ny, 2 * nx : 3 * nx] = np.fliplr(f)
    return ext


def greens_temperature(
    power_map: np.ndarray,
    kt: float,
    h_conv: float,
    lx: float,
    ly: float,
    t_amb: float,
    images: int = 0,
) -> np.ndarray:
    """功率圖 → 溫度場（物理近似）。`images=0` 自由空間，`images=1` 加一階鏡像源。"""
    if images not in (0, 1):
        raise ValueError("images 只支援 0（自由空間）與 1（一階鏡像）")
    ny, nx = power_map.shape
    dy, dx = ly / ny, lx / nx
    m = np.sqrt(h_conv / kt)
    f = power_map / kt

    if images == 0:
        kernel = greens_kernel(ny, nx, m, dy, dx)
        theta = fftconvolve(f, kernel, mode="same")
    else:
        ext = _mirror_extend(f)
        kernel = greens_kernel(3 * ny, 3 * nx, m, dy, dx)
        theta = fftconvolve(ext, kernel, mode="same")[ny : 2 * ny, nx : 2 * nx]

    return theta + t_amb


class MeanFieldBaseline:
    """基準 A：不論輸入，一律預測訓練集的平均溫升場，再加上該樣本的環境溫度。

    它的存在只有一個用途——**下限**。贏不過它的模型代表什麼都沒學到。
    把它當成有意義的對手是本專案明確拒絕的框架（見 `docs/01-problem-statement.md`）。
    """

    def __init__(self) -> None:
        self.mean_theta_: np.ndarray | None = None

    def fit(self, temperatures: np.ndarray, t_amb: np.ndarray) -> "MeanFieldBaseline":
        """`temperatures` 形狀 (n, ny, nx)，`t_amb` 形狀 (n,)。**只能餵 training fold。**"""
        theta = temperatures - t_amb[:, None, None]
        self.mean_theta_ = theta.mean(axis=0)
        return self

    def predict(self, t_amb: np.ndarray) -> np.ndarray:
        if self.mean_theta_ is None:
            raise RuntimeError("尚未 fit")
        return self.mean_theta_[None, :, :] + t_amb[:, None, None]


def greens_theta_norm(
    p_norm: np.ndarray, m_ly: float, m_lx: float, images: int = 1
) -> np.ndarray:
    """無因次版本的物理基準：(p_norm, m·Ly, m·Lx) → θ/θ_ref。

    把 θ = G * (p/kt) 代進 θ_norm = θ·h·A/P 之後，kt、h、P、板子絕對尺寸
    全部消掉，只剩下 m·dx 與 m·dy 兩個無因次格距：

        θ_norm = Σⱼ p_normⱼ · (m·dx)(m·dy) · K₀(|ũᵢ − ũⱼ|) / (2π)

    這不只是省一次乘除。它讓物理基準可以在**代理模型的座標系裡**直接算出來，
    於是「學物理基準的殘差」變成一個乾淨的 image-to-image 問題，
    不需要為了算基準而把樣本還原成有因次的量再轉回去。
    """
    ny, nx = p_norm.shape
    mdy, mdx = m_ly / ny, m_lx / nx

    iy = np.arange(-(3 * ny - 1), 3 * ny)[:, None] * mdy
    ix = np.arange(-(3 * nx - 1), 3 * nx)[None, :] * mdx
    r = np.hypot(iy, ix)
    kernel = np.empty_like(r)
    off = r > 0.0
    kernel[off] = mdx * mdy * k0(r[off]) / (2.0 * np.pi)
    a = np.sqrt(mdx * mdy / np.pi)
    kernel[~off] = 1.0 - a * k1(a)

    if images == 0:
        centre = kernel[2 * ny - 1 : 4 * ny - 1, 2 * nx - 1 : 4 * nx - 1]
        return fftconvolve(p_norm, centre, mode="same")
    ext = _mirror_extend(p_norm)
    return fftconvolve(ext, kernel, mode="same")[ny : 2 * ny, nx : 2 * nx]
