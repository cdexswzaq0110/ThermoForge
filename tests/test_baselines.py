"""物理基準的正確性，以及它與求解器的關係。

這一組測試同時在驗證兩件事：基準寫對了，**而且**求解器與基準是兩條獨立的路徑，
在它們都該成立的區間裡會對得上。兩份實作互相對照，比任何一份的自我一致都強。
"""

import numpy as np
import pytest

from thermoforge.baselines import MeanFieldBaseline, greens_kernel, greens_temperature
from thermoforge.geometry import Component, Layout, rasterize_power
from thermoforge.solver import solve_layout


def _far_from_edges_layout(kt=0.15, h=40.0):
    """單一小元件放在一塊**遠大於熱擴散長度**的板子正中央。

    這是自由空間近似該成立的唯一區間：邊界遠到熱還沒傳到就已經被對流帶走。
    """
    lay = Layout(
        lx=0.6,
        ly=0.6,
        components=(Component(cx=0.3, cy=0.3, w=0.02, h=0.02, power=15.0),),
        kt=kt,
        h_conv=h,
        t_amb=25.0,
    )
    assert lay.diffusion_length < 0.15, "板子必須遠大於擴散長度，否則這個測試沒有意義"
    return lay


def test_greens_kernel_is_finite_and_peaked_at_origin():
    kernel = greens_kernel(16, 16, m=20.0, dy=0.01, dx=0.01)
    assert np.all(np.isfinite(kernel)), "自作用項沒有被等效圓盤積分取代"
    centre = kernel[15, 15]
    assert centre == kernel.max()
    assert centre > 0.0


def test_free_space_greens_matches_solver_far_from_boundaries():
    """遠離邊界時，自由空間近似與求解器應該對得上。

    這條同時保護兩邊：核寫錯或求解器寫錯，都會讓這裡分開。
    """
    lay = _far_from_edges_layout()
    power_map, t_solver = solve_layout(lay, ny=128, nx=128)
    t_greens = greens_temperature(
        power_map, lay.kt, lay.h_conv, lay.lx, lay.ly, lay.t_amb, images=0
    )
    peak_rise = float((t_solver - lay.t_amb).max())
    err = float(np.abs(t_greens - t_solver).max())
    assert err / peak_rise < 0.05, f"最大偏差 {err:.3f} 度 對上峰值溫升 {peak_rise:.3f} 度"


def test_free_space_greens_underestimates_on_a_confined_board():
    """板子小到熱散不掉時，自由空間解**系統性低估**——這是它的已知弱點。

    低估正是本專案最貴的錯誤方向，所以這個弱點要被寫成測試釘住，
    而不是等到比較表出來才發現基準偏在哪一邊。
    """
    lay = Layout(
        lx=0.08,
        ly=0.08,
        components=(Component(cx=0.04, cy=0.04, w=0.02, h=0.02, power=20.0),),
        kt=0.2,
        h_conv=20.0,
        t_amb=25.0,
    )
    assert lay.diffusion_length > 0.08, "板子必須小於擴散長度，熱才會被困住"
    power_map, t_solver = solve_layout(lay, ny=64, nx=64)
    t_free = greens_temperature(power_map, lay.kt, lay.h_conv, lay.lx, lay.ly, lay.t_amb, images=0)
    assert t_free.max() < t_solver.max()


def test_mirror_images_reduce_the_confinement_error():
    """一階鏡像把熱困回板內，因此在受限板上應該比自由空間更接近求解器。"""
    lay = Layout(
        lx=0.08,
        ly=0.08,
        components=(Component(cx=0.04, cy=0.04, w=0.02, h=0.02, power=20.0),),
        kt=0.2,
        h_conv=20.0,
        t_amb=25.0,
    )
    power_map, t_solver = solve_layout(lay, ny=64, nx=64)
    err_free = np.abs(
        greens_temperature(power_map, lay.kt, lay.h_conv, lay.lx, lay.ly, lay.t_amb, images=0)
        - t_solver
    ).mean()
    err_img = np.abs(
        greens_temperature(power_map, lay.kt, lay.h_conv, lay.lx, lay.ly, lay.t_amb, images=1)
        - t_solver
    ).mean()
    assert err_img < err_free, f"鏡像沒有改善：free={err_free:.4f} images={err_img:.4f}"


def test_greens_is_linear_in_power():
    lay = _far_from_edges_layout()
    p1 = rasterize_power(lay, 64, 64)
    a = greens_temperature(p1, lay.kt, lay.h_conv, lay.lx, lay.ly, 0.0)
    b = greens_temperature(2 * p1, lay.kt, lay.h_conv, lay.lx, lay.ly, 0.0)
    np.testing.assert_allclose(b, 2 * a, rtol=1e-10)


def test_mean_field_baseline_rejects_predict_before_fit():
    with pytest.raises(RuntimeError):
        MeanFieldBaseline().predict(np.array([25.0]))


def test_mean_field_baseline_learns_mean_rise():
    rng = np.random.default_rng(1)
    theta = rng.normal(10.0, 1.0, size=(50, 8, 8))
    t_amb = rng.uniform(20.0, 40.0, size=50)
    model = MeanFieldBaseline().fit(theta + t_amb[:, None, None], t_amb)
    pred = model.predict(np.array([30.0]))
    assert pred.shape == (1, 8, 8)
    assert pred.mean() == pytest.approx(30.0 + theta.mean(), abs=0.3)
