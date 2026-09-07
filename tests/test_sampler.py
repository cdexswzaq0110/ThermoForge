"""取樣器的分佈契約，以及 OOD regime 真的在分佈外。

最後兩條測試分別守住兩個「看起來沒問題但會讓整個 OOD 實驗失效」的錯誤：

- OOD 範圍其實與 ID 重疊 → 量到的是尾部表現，不是外推能力。
- 取樣器算的 θ̄ 與求解器實際解出來的平均溫升對不上 → 無因次化的尺度是錯的，
  而模型會把那個錯誤學進去，在任何 in-distribution 評估上都看不出來。
"""

from dataclasses import asdict

import numpy as np
import pytest

from thermoforge.data.sampler import (
    ID_RANGES,
    OOD_REGIMES,
    derive_layout,
    sample_base_layout,
)
from thermoforge.solver import solve_layout


def _base(seed=0, ranges=ID_RANGES):
    rng = np.random.default_rng(seed)
    return rng, sample_base_layout(rng, ranges, base_id=0, regime="id")


@pytest.mark.parametrize("seed", range(8))
def test_components_are_fully_inside_the_board(seed):
    rng, base = _base(seed)
    for cx, cy, w, h in base.rects:
        assert cx - w / 2 >= ID_RANGES.edge_margin - 1e-12
        assert cy - h / 2 >= ID_RANGES.edge_margin - 1e-12
        assert cx + w / 2 <= base.lx - ID_RANGES.edge_margin + 1e-12
        assert cy + h / 2 <= base.ly - ID_RANGES.edge_margin + 1e-12


@pytest.mark.parametrize("seed", range(8))
def test_components_do_not_overlap(seed):
    """重疊的元件會讓「元件數」這個標籤說謊，而 ood_ncomp 整個 regime 靠它成立。"""
    _, base = _base(seed)
    for i, a in enumerate(base.rects):
        for b in base.rects[i + 1 :]:
            gap_x = abs(a[0] - b[0]) - 0.5 * (a[2] + b[2])
            gap_y = abs(a[1] - b[1]) - 0.5 * (a[3] + b[3])
            assert max(gap_x, gap_y) >= ID_RANGES.comp_gap - 1e-12


def test_power_fractions_sum_to_one():
    _, base = _base()
    assert sum(base.power_fractions) == pytest.approx(1.0)


def test_derived_layouts_share_the_same_geometry():
    """同一個 base 衍生出來的樣本幾何完全相同——這正是它們必須同組的理由。"""
    rng, base = _base()
    a = derive_layout(base, rng, ID_RANGES)
    b = derive_layout(base, rng, ID_RANGES)
    assert a.base_layout_id == b.base_layout_id
    assert [(c.cx, c.cy, c.w, c.h) for c in a.components] == [
        (c.cx, c.cy, c.w, c.h) for c in b.components
    ]
    assert (a.h_conv, a.kt, a.t_amb) != (b.h_conv, b.kt, b.t_amb)


def _intervals_disjoint(a, b):
    return a[1] <= b[0] or b[1] <= a[0]


@pytest.mark.parametrize("regime", sorted(OOD_REGIMES))
def test_ood_regime_moves_exactly_one_axis_out_of_distribution(regime):
    """每個 OOD regime 只動一軸，而且動到的那一軸與 ID 區間**不相交**。

    重疊的話量到的是尾部表現而不是外推；動兩軸的話崩掉之後無法歸因。
    """
    ood = asdict(OOD_REGIMES[regime])
    idr = asdict(ID_RANGES)
    changed = [k for k in idr if ood[k] != idr[k]]
    assert len(changed) == 1, f"{regime} 動了 {changed}，應該只動一軸"
    axis = changed[0]
    assert _intervals_disjoint(ood[axis], idr[axis]), (
        f"{regime} 的 {axis} 範圍 {ood[axis]} 與 ID 的 {idr[axis]} 重疊"
    )


@pytest.mark.parametrize("seed", range(5))
def test_sampled_theta_avg_matches_the_solver(seed):
    """取樣器宣稱的板面平均溫升，必須等於求解器實際解出來的平均值。

    這條靠的是能量守恆 θ̄ = P/(h·A)，所以它同時在驗證取樣器與求解器。
    對不上就代表無因次化的尺度是錯的——而那個錯誤會被模型學進去，
    在任何 in-distribution 評估上都不會現形。
    """
    rng = np.random.default_rng(seed)
    base = sample_base_layout(rng, ID_RANGES, base_id=0, regime="id")
    layout = derive_layout(base, rng, ID_RANGES)
    _, temperature = solve_layout(layout, ny=64, nx=64)
    solved_theta_avg = float((temperature - layout.t_amb).mean())
    assert solved_theta_avg == pytest.approx(layout.meta["theta_avg"], rel=1e-9)
