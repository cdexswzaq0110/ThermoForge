"""物理診斷的正確性。

**第一條測試是這個檔案的地基**：把求解器的解代進 PDE 殘差，必須得到零。
得不到零就代表殘差算子與求解器用了不同的離散化，而那個差異會被當成
「模型違反物理」報出去——一個看起來很有洞見、實際上在量自己的診斷。
（L0005：系統說壞了的時候，第一個嫌疑犯是你的判定條件。）
"""

import numpy as np
import pytest

from thermoforge.dataset import from_layouts
from thermoforge.diagnostics import (
    conservation_error,
    error_drivers,
    pde_residual,
    pde_residual_score,
    worst_underestimates,
)
from thermoforge.geometry import Component, Layout
from thermoforge.solver import solve_layout


def _layout(seed=0):
    return Layout(
        lx=0.20,
        ly=0.16,
        components=(
            Component(cx=0.06, cy=0.05, w=0.024, h=0.018, power=18.0),
            Component(cx=0.14, cy=0.11, w=0.016, h=0.016, power=9.0),
        ),
        kt=0.15,
        h_conv=40.0,
        t_amb=25.0,
    )


def test_true_solution_has_zero_residual():
    lay = _layout()
    power_map, temperature = solve_layout(lay, ny=64, nx=64)
    r = pde_residual(
        temperature - lay.t_amb, power_map, lay.kt, lay.h_conv, lay.ly / 64, lay.lx / 64
    )
    assert np.abs(r).max() / (power_map / lay.kt).max() < 1e-9


def test_perturbed_solution_has_nonzero_residual():
    """診斷要抓得到問題，不只是對正確解說 OK。"""
    lay = _layout()
    power_map, temperature = solve_layout(lay, ny=64, nx=64)
    bad = temperature * 1.02
    r = pde_residual(bad - lay.t_amb, power_map, lay.kt, lay.h_conv, lay.ly / 64, lay.lx / 64)
    assert np.abs(r).max() / (power_map / lay.kt).max() > 1e-3


def test_residual_score_is_zero_for_the_solver():
    """容忍度是 1e-6 而不是上一條的 1e-9，因為 `Dataset` 把功率圖存成 float32。

    實測值 3.1e-8【已確認：2026-09-07】，正好是 float32 相對精度（~1e-7）的量級。
    這不是缺陷，是資料層的精度預算——但它是這個診斷的**解析下限**：
    任何小於 1e-7 的殘差都分不出是模型好還是儲存精度。
    """
    lay = _layout()
    _, temperature = solve_layout(lay)
    ds = from_layouts([lay])
    assert pde_residual_score(ds, temperature[None])[0] < 1e-6


def test_conservation_error_is_zero_for_the_solver():
    lay = _layout()
    _, temperature = solve_layout(lay)
    ds = from_layouts([lay])
    assert conservation_error(ds, temperature[None])[0] < 1e-10


def test_conservation_error_catches_a_scaled_field():
    """整場乘 1.05 → 散熱量多 5%，守恆誤差必須是 5%。"""
    lay = _layout()
    _, temperature = solve_layout(lay)
    ds = from_layouts([lay])
    scaled = (temperature - lay.t_amb) * 1.05 + lay.t_amb
    assert conservation_error(ds, scaled[None])[0] == pytest.approx(0.05, rel=1e-6)


def _fake_dataset(n=200, seed=0):
    from thermoforge.data.sampler import ID_RANGES, derive_layout, sample_base_layout

    rng = np.random.default_rng(seed)
    layouts, temps = [], []
    for i in range(n):
        base = sample_base_layout(rng, ID_RANGES, i, "id")
        lay = derive_layout(base, rng, ID_RANGES)
        _, t = solve_layout(lay)
        layouts.append(lay)
        temps.append(t)
    ds = from_layouts(layouts)
    ds.arrays["temperature"] = np.stack(temps).astype(np.float32)
    ds.arrays["fold"] = np.arange(n) % 5
    return ds


def test_error_drivers_reports_bins_and_fold_agreement():
    ds = _fake_dataset()
    # 一個刻意在「靠近邊界」時低估的假預測，看診斷抓不抓得到。
    truth = ds.temperature.astype(np.float64)
    oof = truth.copy()
    hot_near_edge = ds.p_norm.reshape(len(ds), -1).max(axis=1) > np.median(
        ds.p_norm.reshape(len(ds), -1).max(axis=1)
    )
    oof[hot_near_edge] -= 4.0

    drivers = error_drivers(ds, oof)
    assert set(drivers) == {
        "hotspot_edge_distance_over_diffusion_length",
        "m_times_lx",
        "n_components",
        "power_concentration",
    }
    d = drivers["power_concentration"]
    assert len(d["mae"]) == len(d["edges"]) - 1
    assert d["mae"][-1] > d["mae"][0], "植入的偏差沒有被功率集中度那一軸抓到"
    assert -1.0 <= d["fold_rank_agreement"] <= 1.0


def test_worst_underestimates_only_returns_the_expensive_side():
    ds = _fake_dataset(n=60)
    truth = ds.temperature.astype(np.float64)
    oof = truth.copy()
    oof[3] -= 12.0   # 低估 12 度
    oof[7] += 20.0   # 高估 20 度——不該進榜
    cases = worst_underestimates(ds, oof, k=2)
    assert cases[0]["index"] == 3
    assert cases[0]["underestimate"] == pytest.approx(12.0, abs=1e-6)
    assert 7 not in [c["index"] for c in cases]
