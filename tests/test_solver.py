"""求解器的正確性契約。

分四層，由強到弱：

1. **解析解**：均勻功率下 θ = f/m²，逐點精確。
2. **兩份獨立實作一致**：DCT 與稀疏直接解。快的那份的特徵值公式錯了不會報錯，
   只會安靜地給出錯的場——需要一個不共用該假設的實作來對（L0005 的形狀）。
3. **守恆律**：h·∫θ dA ＝ P_total，絕熱邊界下是恆等式。
4. **算子性質**：線性、決定性、網格收斂。
"""

import numpy as np
import pytest

from thermoforge.geometry import Component, Layout
from thermoforge.solver import (
    energy_residual,
    neumann_laplacian_eigenvalues,
    solve_layout,
    solve_theta_dct,
    solve_theta_sparse,
)


def _layout(power=25.0, kt=0.15, h=40.0, lx=0.2, ly=0.16, t_amb=25.0):
    return Layout(
        lx=lx,
        ly=ly,
        components=(
            Component(cx=0.06, cy=0.05, w=0.024, h=0.018, power=power * 0.6),
            Component(cx=0.14, cy=0.11, w=0.016, h=0.016, power=power * 0.4),
        ),
        kt=kt,
        h_conv=h,
        t_amb=t_amb,
    )


def test_uniform_source_has_analytic_solution():
    """均勻功率 + 絕熱邊界 ⇒ 溫升處處相同，θ = f/m²。

    這是唯一一個能逐點對到解析解的案例，所以它是求解器的第一道門。
    """
    f = np.full((48, 40), 3.7)
    m2 = 260.0
    theta = solve_theta_dct(f, m2, dy=0.16 / 48, dx=0.2 / 40)
    np.testing.assert_allclose(theta, 3.7 / m2, rtol=1e-12, atol=1e-14)


def test_dct_matches_sparse():
    """兩份實作逐點一致。DCT 的特徵值公式是本檔最容易安靜出錯的地方。"""
    rng = np.random.default_rng(0)
    f = rng.gamma(shape=2.0, scale=40.0, size=(24, 30))
    m2 = 480.0
    dy, dx = 0.16 / 24, 0.2 / 30
    a = solve_theta_dct(f, m2, dy, dx)
    b = solve_theta_sparse(f, m2, dy, dx)
    np.testing.assert_allclose(a, b, rtol=1e-9, atol=1e-12)


def test_neumann_eigenvalues_are_nonpositive_with_zero_constant_mode():
    lam = neumann_laplacian_eigenvalues(16, 0.01)
    assert lam[0] == pytest.approx(0.0, abs=1e-15)
    assert np.all(lam <= 1e-15)


@pytest.mark.parametrize("h", [12.0, 45.0, 130.0])
@pytest.mark.parametrize("n", [32, 64])
def test_energy_conservation_is_exact(h, n):
    """絕熱邊界下能量守恆是恆等式，不是近似——容忍度設在浮點層級。"""
    lay = _layout(h=h)
    _, temperature = solve_layout(lay, ny=n, nx=n)
    assert energy_residual(lay, temperature) < 1e-10


def test_solution_is_linear_in_power():
    """算子是線性的：功率翻倍，溫升就翻倍。

    這條同時是後面 OOD 實驗的參照——功率外推的**正確答案已知**，
    所以「代理模型在功率 OOD 上崩掉」是模型沒學到線性，不是問題本身難。
    """
    lay1 = _layout(power=20.0)
    lay2 = _layout(power=40.0)
    _, t1 = solve_layout(lay1)
    _, t2 = solve_layout(lay2)
    np.testing.assert_allclose(t2 - lay2.t_amb, 2.0 * (t1 - lay1.t_amb), rtol=1e-10)


def test_solver_is_deterministic():
    lay = _layout()
    _, a = solve_layout(lay)
    _, b = solve_layout(lay)
    np.testing.assert_array_equal(a, b)


def test_grid_refinement_converges():
    """網格加密時解趨於穩定；粗細網格的熱點溫度差距隨解析度縮小。"""
    lay = _layout()
    peaks = []
    for n in (32, 64, 128):
        _, t = solve_layout(lay, ny=n, nx=n)
        peaks.append(float(t.max()))
    d1 = abs(peaks[1] - peaks[0])
    d2 = abs(peaks[2] - peaks[1])
    assert d2 < d1, f"未見收斂：{peaks}"


def test_zero_convection_is_rejected():
    """h=0 時穩態解不唯一（熱進得來出不去）——要在入口就擋，不是回傳 inf。"""
    with pytest.raises(ValueError, match="m²"):
        solve_theta_dct(np.ones((8, 8)), 0.0, 0.01, 0.01)
