"""佈局取樣器——資料集的來源分佈定義在這裡。

## 用「熱點溫升」定義設計空間，而不是直接抽總功率

第一版是各自獨立抽總功率 P 與對流係數 h。跑出來的資料集熱點溫度中位數 104 °C、
p99 是 314 °C、最大值 1087 °C【已確認：2026-09-07 dataset v1 的實測分佈】。
1087 °C 的板子在任何材料下都不存在，而那些樣本會直接主導 field MAE——
模型會把容量花在一段不會出現在真實產品裡的分佈上。

現在改成：先抽一個目標**熱點溫升** θ_peak ∈ [15, 90] K，再用解析估計回推總功率。

    P = θ_peak / (per_watt),   per_watt = 1/(h·A) + max_i fracᵢ·K₀(m·aᵢ)/(2π·kt)

兩項各自對應一個機制，缺一個就會在某個角落失控：

- `1/(h·A)` 是**受限項**：熱擴散長度大於板子時，熱散不出去，整塊板一起升溫。
  自由空間解完全看不到這一項，於是在 m·L < 1 的角落估出來的功率會高一個量級。
- `K₀` 項是**局部項**：元件自己那一塊的額外溫升。

這個估計只用來**定義設計空間的尺度**，不參與標籤——真正的熱點永遠由求解器決定。
用它做 rejection sampling 才會變成對 target 做篩選，那是另一回事，本檔沒有做。

## base layout 與衍生條件的分界

- **base layout**：板子尺寸、元件位置與大小、功率**比例**。切分的組別（group）。
- **衍生條件**：kt、h、T_amb、θ_peak。同一個 base 配不同條件 → 多個高度相關的樣本。

這條界線就是 `CLAUDE.md` 預設節奏第 4 條的實作依據。把它們隨機切開，
模型等於在驗證集上看過幾乎一模一樣的幾何，分數會樂觀到沒有參考價值。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.special import k0

from ..geometry import Component, Layout

__all__ = [
    "Ranges",
    "ID_RANGES",
    "OOD_REGIMES",
    "BaseLayout",
    "sample_base_layout",
    "derive_layout",
    "place_rects",
    "peak_rise_per_watt",
    "check_in_distribution",
]


@dataclass(frozen=True)
class Ranges:
    """一個 regime 的取樣範圍。長度單位公尺，溫度單位 K/°C。"""

    lx: tuple[float, float] = (0.12, 0.25)
    aspect: tuple[float, float] = (0.80, 1.25)
    kt: tuple[float, float] = (0.08, 0.30)
    h_conv: tuple[float, float] = (15.0, 80.0)
    t_amb: tuple[float, float] = (20.0, 45.0)
    peak_rise: tuple[float, float] = (15.0, 90.0)
    n_components: tuple[int, int] = (3, 7)
    comp_size: tuple[float, float] = (0.008, 0.030)
    edge_margin: float = 0.004
    comp_gap: float = 0.002


#: 訓練與 id-val 的分佈。
ID_RANGES = Ranges()

#: 五個 OOD regime，每個只把**一個軸**推出訓練範圍。
#:
#: 一次只動一軸是刻意的：如果同時改對流、功率與幾何，模型崩掉之後
#: 沒有辦法歸因是哪一個外推害的，整個 OOD 實驗就只剩一個「會崩」的結論。
OOD_REGIMES: dict[str, Ranges] = {
    # 對流係數推出範圍：改變的是熱擴散長度 1/m，也就是核的寬度。
    "ood_h_low": replace(ID_RANGES, h_conv=(5.0, 15.0)),
    "ood_h_high": replace(ID_RANGES, h_conv=(80.0, 150.0)),
    # 元件數推出範圍：改變的是空間結構的複雜度，不是尺度。
    "ood_ncomp": replace(ID_RANGES, n_components=(8, 11)),
    # 板型長寬比推出範圍：改變的是邊界的形狀。
    "ood_aspect": replace(ID_RANGES, aspect=(1.60, 2.40)),
    # 功率推出範圍：算子對功率是線性的，所以**正確答案已知**——
    # 模型在這裡崩掉代表它沒學到線性，不代表這個外推本身很難。
    "ood_power": replace(ID_RANGES, peak_rise=(90.0, 170.0)),
}


@dataclass(frozen=True)
class BaseLayout:
    """幾何與功率比例——切分時的組別單位。"""

    base_id: int
    lx: float
    ly: float
    rects: tuple[tuple[float, float, float, float], ...]  # (cx, cy, w, h)
    power_fractions: tuple[float, ...]
    regime: str

    @property
    def n_components(self) -> int:
        return len(self.rects)


def _rects_overlap(a, b, gap: float) -> bool:
    acx, acy, aw, ah = a
    bcx, bcy, bw, bh = b
    return (
        abs(acx - bcx) < 0.5 * (aw + bw) + gap
        and abs(acy - bcy) < 0.5 * (ah + bh) + gap
    )


def place_rects(
    rng: np.random.Generator,
    lx: float,
    ly: float,
    sizes: list[tuple[float, float]],
    ranges: Ranges,
) -> list[tuple[float, float, float, float]]:
    """把給定尺寸的元件不重疊地放進板內，回傳 (cx, cy, w, h) 串列。

    放不下就**少放一個**而不是讓它們疊起來——重疊的元件在這個物理模型裡
    等於一個功率加總的大元件，會讓「元件數」這個標籤說謊，
    而 `ood_ncomp` 整個 regime 的意義就建立在那個標籤上。
    """
    rects: list[tuple[float, float, float, float]] = []
    for w, h in sizes:
        if w + 2 * ranges.edge_margin >= lx or h + 2 * ranges.edge_margin >= ly:
            continue
        for _ in range(200):
            cx = rng.uniform(ranges.edge_margin + w / 2, lx - ranges.edge_margin - w / 2)
            cy = rng.uniform(ranges.edge_margin + h / 2, ly - ranges.edge_margin - h / 2)
            cand = (cx, cy, w, h)
            if any(_rects_overlap(cand, r, ranges.comp_gap) for r in rects):
                continue
            rects.append(cand)
            break
    return rects


def sample_base_layout(
    rng: np.random.Generator, ranges: Ranges, base_id: int, regime: str
) -> BaseLayout:
    """抽一個幾何配置。元件不重疊、完全落在板內並留邊界餘裕。"""
    lx = rng.uniform(*ranges.lx)
    ly = lx / rng.uniform(*ranges.aspect)
    n_target = int(rng.integers(ranges.n_components[0], ranges.n_components[1] + 1))
    sizes = [
        (float(rng.uniform(*ranges.comp_size)), float(rng.uniform(*ranges.comp_size)))
        for _ in range(n_target)
    ]
    rects = place_rects(rng, lx, ly, sizes, ranges)
    if not rects:
        raise RuntimeError(f"板 {lx:.3f}x{ly:.3f} m 放不下任何元件；檢查 comp_size 與 edge_margin")

    # Dirichlet(2) 而不是均勻：真實板子上功率是不均的（一顆 CPU 加幾顆小 IC），
    # 但也不該極端到單一元件吃掉 99%——alpha=2 給的是「有主次但不極端」。
    fractions = rng.dirichlet(np.full(len(rects), 2.0))
    return BaseLayout(
        base_id=base_id,
        lx=lx,
        ly=ly,
        rects=tuple(rects),
        power_fractions=tuple(float(f) for f in fractions),
        regime=regime,
    )


def peak_rise_per_watt(
    rects, fractions, lx: float, ly: float, kt: float, h_conv: float
) -> float:
    """每一瓦**總**功率造成的熱點溫升估計 [K/W]。只用輸入，不碰求解器。

    受限項 ＋ 局部項，見模組 docstring。這個估計唯一的用途是設定設計空間的尺度；
    它有系統性誤差（忽略元件之間的交互作用與邊界的高階效應），
    而那個誤差正好是代理模型要學的東西之一。
    """
    confined = 1.0 / (h_conv * lx * ly)
    m = np.sqrt(h_conv / kt)
    local = 0.0
    for (_, _, w, h), frac in zip(rects, fractions):
        a = np.sqrt(w * h / np.pi)
        local = max(local, float(frac * k0(m * a) / (2.0 * np.pi * kt)))
    return confined + local


def derive_layout(base: BaseLayout, rng: np.random.Generator, ranges: Ranges) -> Layout:
    """在一個 base layout 上抽一組操作條件，得到一個完整的佈局。"""
    kt = float(rng.uniform(*ranges.kt))
    h_conv = float(rng.uniform(*ranges.h_conv))
    t_amb = float(rng.uniform(*ranges.t_amb))
    peak_target = float(rng.uniform(*ranges.peak_rise))
    return build_layout(base, kt, h_conv, t_amb, peak_target)


def build_layout(
    base: BaseLayout, kt: float, h_conv: float, t_amb: float, peak_target: float
) -> Layout:
    """條件已定時的組裝路徑。篩選候選池（`pools.py`）要固定條件、只換佈局，走這一支。"""
    per_watt = peak_rise_per_watt(
        base.rects, base.power_fractions, base.lx, base.ly, kt, h_conv
    )
    total_power = peak_target / per_watt
    components = tuple(
        Component(cx=cx, cy=cy, w=w, h=h, power=total_power * frac)
        for (cx, cy, w, h), frac in zip(base.rects, base.power_fractions)
    )
    return Layout(
        lx=base.lx,
        ly=base.ly,
        components=components,
        kt=kt,
        h_conv=h_conv,
        t_amb=t_amb,
        base_layout_id=str(base.base_id),
        regime=base.regime,
        meta={
            "peak_target": peak_target,
            "total_power": total_power,
            "theta_avg": total_power / (h_conv * base.lx * base.ly),
        },
    )


def check_in_distribution(layout, ranges: Ranges = ID_RANGES) -> dict[str, tuple[float, tuple[float, float]]]:
    """回傳**超出**訓練分佈的軸：{軸名: (實際值, ID 區間)}。全部在內就是空 dict。

    這個函式是設計副駕的守門員。代理模型在分佈外給出的數字不是「比較不準」，
    是**沒有證據支持**——`.claude/rules/evidence-grades.md` 不允許把它寫成推論。
    所以副駕需要一個機械化的判準來決定該說「約 78 度」還是「未驗證，送 CFD」。

    軸的選擇對應 `OOD_REGIMES`：每一個 OOD regime 推的那一軸，這裡都查得到。
    """
    m = np.sqrt(layout.h_conv / layout.kt)
    per_watt = peak_rise_per_watt(
        [(c.cx, c.cy, c.w, c.h) for c in layout.components],
        [c.power / layout.total_power for c in layout.components],
        layout.lx,
        layout.ly,
        layout.kt,
        layout.h_conv,
    )
    actual = {
        "lx": layout.lx,
        "aspect": layout.lx / layout.ly,
        "kt": layout.kt,
        "h_conv": layout.h_conv,
        "t_amb": layout.t_amb,
        "peak_rise": per_watt * layout.total_power,
        "n_components": float(len(layout.components)),
    }
    limits = {
        "lx": ranges.lx,
        "aspect": ranges.aspect,
        "kt": ranges.kt,
        "h_conv": ranges.h_conv,
        "t_amb": ranges.t_amb,
        "peak_rise": ranges.peak_rise,
        "n_components": (float(ranges.n_components[0]), float(ranges.n_components[1])),
    }
    return {
        k: (v, limits[k])
        for k, v in actual.items()
        if not (limits[k][0] <= v <= limits[k][1])
    }
