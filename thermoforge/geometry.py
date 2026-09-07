"""佈局的資料結構，以及「佈局 → 功率圖」的離散化。

這一層唯一的硬性契約是**功率守恆**：不論元件邊界落在網格的哪個位置、
也不論元件有沒有超出板子，離散化後的總功率必須等於元件功率總和
（元件超出板外的部分不計，但計入的部分不得被稀釋或放大）。

理由見 `docs/02-solver.md`：能量守恆是本專案唯一的**精確**檢查，
而它的前提是這一步沒有偷偷改變總功率。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Component:
    """一個發熱元件，以板面座標系的軸對齊矩形表示。

    座標原點在板子左下角，單位一律 SI（公尺、瓦）。
    """

    cx: float
    cy: float
    w: float
    h: float
    power: float

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(x0, y0, x1, y1)。"""
        return (
            self.cx - 0.5 * self.w,
            self.cy - 0.5 * self.h,
            self.cx + 0.5 * self.w,
            self.cy + 0.5 * self.h,
        )

    @property
    def area(self) -> float:
        return self.w * self.h


@dataclass(frozen=True)
class Layout:
    """一個板級熱設計案例的完整輸入。

    `kt` 是**片導熱**（sheet conductance, W/K）＝ 導熱係數 × 板厚。
    直接用它而不用 (k, t) 兩個欄位，是因為方程只透過乘積依賴它們——
    分開存會製造一個模型永遠學不到差異的假自由度。

    `h_conv` 是上下表面對流係數的**總和**（W/m²K），`t_amb` 是環境溫度（°C）。

    `base_layout_id` 是**切分用的組別**：幾何與元件位置相同、只有 h／T_amb
    不同的樣本共用同一個 id。它們高度相關，切分時必須整組同進同出
    （`CLAUDE.md` 預設節奏第 4 條）。
    """

    lx: float
    ly: float
    components: tuple[Component, ...]
    kt: float
    h_conv: float
    t_amb: float
    base_layout_id: str = ""
    regime: str = "id"
    meta: dict = field(default_factory=dict, compare=False)

    @property
    def total_power(self) -> float:
        return float(sum(c.power for c in self.components))

    @property
    def area(self) -> float:
        return self.lx * self.ly

    @property
    def m_squared(self) -> float:
        """螢幕化參數 m² = h / kt，單位 1/m²。

        1/m 是熱擴散長度：功率注入點的影響大約衰減到這個尺度之外就可以忽略。
        它同時是代理模型最需要「看得懂」的那個量——它決定了核的寬度。
        """
        return self.h_conv / self.kt

    @property
    def diffusion_length(self) -> float:
        """1/m，公尺。"""
        return float(1.0 / np.sqrt(self.m_squared))


def _overlap_1d(lo: float, hi: float, n: int, step: float) -> np.ndarray:
    """[lo, hi] 與 n 個寬 step 的等距區間，各自的重疊長度。"""
    edges_lo = np.arange(n) * step
    edges_hi = edges_lo + step
    return np.clip(np.minimum(hi, edges_hi) - np.maximum(lo, edges_lo), 0.0, None)


def rasterize_power(layout: Layout, ny: int, nx: int) -> np.ndarray:
    """把佈局的元件功率打到 (ny, nx) 網格上，回傳**面功率密度** [W/m²]。

    採面積加權：每個元件的功率按它與各網格單元的實際重疊面積分配。
    這比「元件中心落在哪一格就全給哪一格」貴一點，但換到的是精確的功率守恆——
    後者在元件小於一格時會產生數十 % 的總功率誤差，而那個誤差會直接
    污染能量守恆檢查，讓唯一的精確檢查失去鑑別力。
    """
    dx = layout.lx / nx
    dy = layout.ly / ny
    cell_area = dx * dy

    power_per_cell = np.zeros((ny, nx), dtype=np.float64)
    for comp in layout.components:
        x0, y0, x1, y1 = comp.bounds
        ox = _overlap_1d(x0, x1, nx, dx)
        oy = _overlap_1d(y0, y1, ny, dy)
        weights = np.outer(oy, ox)
        if comp.area <= 0.0 or weights.sum() <= 0.0:
            # 元件退化或完全在板外：它的熱不進入這塊板，
            # 而不是被夾到最近的格子（那會憑空製造一個熱點）。
            continue
        # 分母是元件的**完整**面積，不是它落在板內的那一塊。
        # 用落在板內的面積當分母，等於把伸出板外那半塊的功率也塞回板上——
        # 一個 50% 懸空的元件會得到 100% 的熱，而測試會安靜通過，
        # 因為總功率看起來還是守恆的。
        power_per_cell += comp.power * (weights / comp.area)

    return power_per_cell / cell_area


def cell_centers(layout: Layout, ny: int, nx: int) -> tuple[np.ndarray, np.ndarray]:
    """回傳 (yc, xc)，各自形狀 (ny,) 與 (nx,)，單位公尺。"""
    dx = layout.lx / nx
    dy = layout.ly / ny
    return (np.arange(ny) + 0.5) * dy, (np.arange(nx) + 0.5) * dx
