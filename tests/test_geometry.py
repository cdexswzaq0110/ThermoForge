"""功率圖離散化的守恆契約。

這一組測試守的是 `docs/02-solver.md` 的前提：能量守恆檢查只有在
「離散化沒有偷改總功率」時才有鑑別力。
"""

import numpy as np
import pytest

from thermoforge.geometry import Component, Layout, rasterize_power


def _layout(components, lx=0.2, ly=0.16, kt=0.15, h=40.0, t_amb=25.0):
    return Layout(lx=lx, ly=ly, components=tuple(components), kt=kt, h_conv=h, t_amb=t_amb)


@pytest.mark.parametrize("cx,cy", [(0.1, 0.08), (0.1234, 0.0567), (0.05, 0.05)])
def test_rasterize_conserves_total_power(cx, cy):
    """元件邊界不對齊網格時，總功率仍然守恆。

    這是面積加權存在的唯一理由——最近鄰指派在這個案例會漏掉或多算功率。
    """
    lay = _layout([Component(cx=cx, cy=cy, w=0.021, h=0.013, power=17.0)])
    p = rasterize_power(lay, 64, 64)
    cell_area = (lay.lx / 64) * (lay.ly / 64)
    assert p.sum() * cell_area == pytest.approx(17.0, rel=1e-12)


def test_rasterize_subcell_component_conserves_power():
    """元件比一格還小時也不能被稀釋——這是最近鄰指派最容易錯的區間。"""
    lay = _layout([Component(cx=0.0731, cy=0.0417, w=0.001, h=0.001, power=5.0)])
    p = rasterize_power(lay, 32, 32)
    cell_area = (lay.lx / 32) * (lay.ly / 32)
    assert p.sum() * cell_area == pytest.approx(5.0, rel=1e-12)


def test_rasterize_component_fully_outside_is_dropped():
    """完全在板外的元件不進入這塊板，而不是被夾到最近的邊。"""
    lay = _layout([Component(cx=0.9, cy=0.9, w=0.01, h=0.01, power=30.0)])
    p = rasterize_power(lay, 32, 32)
    assert p.sum() == 0.0


def test_rasterize_partially_outside_keeps_only_inside_share():
    """一半在板外的元件，只有板內那一半的功率進來。"""
    lay = _layout([Component(cx=0.0, cy=0.08, w=0.02, h=0.02, power=10.0)], lx=0.2, ly=0.16)
    p = rasterize_power(lay, 200, 160)
    cell_area = (0.2 / 200) * (0.16 / 160)
    assert p.sum() * cell_area == pytest.approx(5.0, rel=2e-2)


def test_diffusion_length_matches_definition():
    lay = _layout([Component(cx=0.1, cy=0.08, w=0.01, h=0.01, power=1.0)], kt=0.2, h=50.0)
    assert lay.m_squared == pytest.approx(250.0)
    assert lay.diffusion_length == pytest.approx(1.0 / np.sqrt(250.0))
