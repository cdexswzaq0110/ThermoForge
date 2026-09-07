"""二維穩態熱傳導求解器——本專案唯一的 ground truth 來源。

## 解的是什麼

板級熱傳導的薄板（fin）近似。板面內傳導、上下表面對流散熱到環境：

    ∇·(kt ∇θ) − h·θ + p(x, y) = 0

其中 θ = T − T_amb，kt 是片導熱 [W/K]，h 是上下表面對流係數總和 [W/m²K]，
p 是面功率密度 [W/m²]。除以 kt 之後得到**螢幕化 Poisson 方程**（modified Helmholtz）：

    ∇²θ − m²θ = −f,    m² = h/kt,    f = p/kt

四邊絕熱（Neumann, ∂θ/∂n = 0）——板子邊緣的傳導散熱相對於整面對流可忽略。

## 為什麼這個方程值得挑

1. **線性**：沒有迭代收斂的模糊地帶，同一輸入永遠同一輸出。
2. **有解析 Green's function**：G(r) = K₀(m·r)/(2π·kt)。所以物理基準不是玩具，
   它在遠離邊界處幾乎精確——神經網路要贏的對手是誠實的（見 `baselines.py`）。
3. **有精確的守恆律**：絕熱邊界下 h·∫θ dA ≡ P_total，沒有近似。
   這是本專案唯一能用來抓「求解器自己壞掉」的檢查。

## 兩份實作，互為對照

`solve_dct` 用離散餘弦轉換對角化算子，O(N log N)；`solve_sparse` 用稀疏直接解，
是慢但直白的參考實作。兩者必須逐點一致（`tests/test_solver.py::test_dct_matches_sparse`）。

留兩份不是重複——**一份實作的自我一致不構成證據**。快的那份有一個容易錯而且
不會報錯的地方（餘弦基底下的特徵值公式），需要一個不依賴同一個假設的東西來對。
"""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.fft import dctn, idctn

from .geometry import Layout, rasterize_power

__all__ = [
    "neumann_laplacian_eigenvalues",
    "solve_theta_dct",
    "solve_theta_sparse",
    "solve_layout",
    "energy_residual",
]


def neumann_laplacian_eigenvalues(n: int, step: float) -> np.ndarray:
    """cell-centered、鏡像（Neumann）邊界的一維二階差分算子在 DCT-II 基底下的特徵值。

    值皆 ≤ 0，第 0 個恰為 0（常數模態——絕熱板上的常數溫度不產生傳導通量）。
    """
    k = np.arange(n)
    return -4.0 * np.sin(np.pi * k / (2.0 * n)) ** 2 / step**2


def solve_theta_dct(f: np.ndarray, m_squared: float, dy: float, dx: float) -> np.ndarray:
    """解 ∇²θ − m²θ = −f，四邊絕熱。回傳溫升場 θ（形狀同 f）。

    在 DCT-II 正交基底下 5 點 Laplacian 是對角的，於是解退化成逐模態除法：

        θ̂ = f̂ / (m² − λ_y − λ_x)

    m² > 0 保證分母恆正，不會碰到常數模態的奇異性——物理上就是
    「有對流散熱時，穩態溫度是唯一的」。
    """
    if m_squared <= 0.0:
        raise ValueError("m² 必須為正：沒有對流散熱時穩態解不唯一")
    ny, nx = f.shape
    lam_y = neumann_laplacian_eigenvalues(ny, dy)[:, None]
    lam_x = neumann_laplacian_eigenvalues(nx, dx)[None, :]

    f_hat = dctn(f, type=2, norm="ortho")
    theta_hat = f_hat / (m_squared - lam_y - lam_x)
    return idctn(theta_hat, type=2, norm="ortho")


def _build_operator(ny: int, nx: int, m_squared: float, dy: float, dx: float) -> sp.csc_matrix:
    """(∇² − m²) 的稀疏矩陣，絕熱邊界以「略去該面」實作。"""
    inv_dx2 = 1.0 / dx**2
    inv_dy2 = 1.0 / dy**2

    idx = np.arange(ny * nx).reshape(ny, nx)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []
    diag = np.full((ny, nx), -m_squared, dtype=np.float64)

    for axis_shift, coeff in ((("x", +1), inv_dx2), (("x", -1), inv_dx2),
                              (("y", +1), inv_dy2), (("y", -1), inv_dy2)):
        axis, shift = axis_shift
        if axis == "x":
            src = idx[:, max(0, -shift):nx - max(0, shift)]
            dst = idx[:, max(0, shift):nx - max(0, -shift)]
        else:
            src = idx[max(0, -shift):ny - max(0, shift), :]
            dst = idx[max(0, shift):ny - max(0, -shift), :]
        rows.append(src.ravel())
        cols.append(dst.ravel())
        vals.append(np.full(src.size, coeff))
        # 該面存在才從對角扣掉：面不存在＝絕熱，通量為零。
        mask = np.zeros((ny, nx), dtype=bool)
        mask.ravel()[src.ravel()] = True
        diag -= coeff * mask

    rows.append(idx.ravel())
    cols.append(idx.ravel())
    vals.append(diag.ravel())

    return sp.coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(ny * nx, ny * nx),
    ).tocsc()


def solve_theta_sparse(f: np.ndarray, m_squared: float, dy: float, dx: float) -> np.ndarray:
    """參考實作：組稀疏矩陣直接解。慢，但不依賴任何轉換的特徵值假設。"""
    ny, nx = f.shape
    a = _build_operator(ny, nx, m_squared, dy, dx)
    theta = spla.spsolve(a, -f.ravel())
    return np.asarray(theta).reshape(ny, nx)


def solve_layout(
    layout: Layout,
    ny: int = 64,
    nx: int = 64,
    method: str = "dct",
) -> tuple[np.ndarray, np.ndarray]:
    """佈局 → (功率圖 [W/m²], 溫度場 [°C])。

    回傳的溫度場已加回環境溫度，是 `CONTEXT.md` 定義的「溫度場」。
    """
    power_map = rasterize_power(layout, ny, nx)
    f = power_map / layout.kt
    dy = layout.ly / ny
    dx = layout.lx / nx

    if method == "dct":
        theta = solve_theta_dct(f, layout.m_squared, dy, dx)
    elif method == "sparse":
        theta = solve_theta_sparse(f, layout.m_squared, dy, dx)
    else:
        raise ValueError(f"未知的 method: {method!r}（只有 'dct' 與 'sparse'）")

    return power_map, theta + layout.t_amb


def energy_residual(layout: Layout, temperature: np.ndarray) -> float:
    """回傳能量守恆的**相對**殘差 |h·∫θ dA − P_total| / P_total。

    參數是 `solve_layout` 回傳的**溫度場**（含環境溫度），不是溫升場——
    `CONTEXT.md` 只定義了「溫度場」這個詞，讓 API 收它可以少掉一整類
    「忘了減 T_amb」的呼叫端錯誤。

    絕熱邊界下這條是恆等式，不是近似——所以任何顯著非零的值都代表
    求解器、離散化或功率圖其中之一壞了，而不是「精度不夠」。
    """
    ny, nx = temperature.shape
    cell_area = (layout.lx / nx) * (layout.ly / ny)
    theta = temperature - layout.t_amb
    dissipated = layout.h_conv * float(theta.sum()) * cell_area
    total = layout.total_power
    if total <= 0.0:
        return abs(dissipated)
    return abs(dissipated - total) / total
