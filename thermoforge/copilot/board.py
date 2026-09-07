"""參考板：帶名字的元件清單，以及「套用一個設計改動」的路徑。

元件有名字，是因為使用者說的是「CPU」而不是「第 0 個元件」。名字→索引的對照
留在這一層，`DesignQuery` 只帶索引——這樣解析層錯了會在這裡就爆，
而不是變成一個對錯誤元件做的正確計算。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from ..geometry import Component, Layout

__all__ = ["ReferenceBoard", "load_board"]


@dataclass(frozen=True)
class NamedComponent:
    name: str
    aliases: tuple[str, ...]
    component: Component


@dataclass(frozen=True)
class ReferenceBoard:
    name: str
    lx: float
    ly: float
    kt: float
    h_conv: float
    t_amb: float
    t_max_allowed: float
    components: tuple[NamedComponent, ...]

    def index_of(self, token: str) -> int | None:
        """名字或別名 → 索引。找不到回傳 None，不猜。"""
        t = token.strip().lower()
        for i, nc in enumerate(self.components):
            if t == nc.name.lower() or t in nc.aliases:
                return i
        return None

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(nc.name for nc in self.components)

    def to_layout(self, regime: str = "reference") -> Layout:
        return Layout(
            lx=self.lx,
            ly=self.ly,
            components=tuple(nc.component for nc in self.components),
            kt=self.kt,
            h_conv=self.h_conv,
            t_amb=self.t_amb,
            base_layout_id="reference",
            regime=regime,
        )

    def with_power(self, index: int, power: float) -> "ReferenceBoard":
        comps = list(self.components)
        comps[index] = replace(comps[index], component=replace(comps[index].component, power=power))
        return replace(self, components=tuple(comps))

    def with_conditions(
        self, h_conv: float | None = None, t_amb: float | None = None, kt: float | None = None
    ) -> "ReferenceBoard":
        return replace(
            self,
            h_conv=self.h_conv if h_conv is None else h_conv,
            t_amb=self.t_amb if t_amb is None else t_amb,
            kt=self.kt if kt is None else kt,
        )

    def with_positions(self, positions: list[tuple[float, float]]) -> "ReferenceBoard":
        comps = [
            replace(nc, component=replace(nc.component, cx=cx, cy=cy))
            for nc, (cx, cy) in zip(self.components, positions)
        ]
        return replace(self, components=tuple(comps))


def load_board(path: str | Path = "configs/reference_board.yaml") -> ReferenceBoard:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    comps = tuple(
        NamedComponent(
            name=c["name"],
            aliases=tuple(str(a).lower() for a in c.get("aliases", ())),
            component=Component(cx=c["cx"], cy=c["cy"], w=c["w"], h=c["h"], power=c["power"]),
        )
        for c in raw["components"]
    )
    return ReferenceBoard(
        name=raw["name"],
        lx=raw["lx"],
        ly=raw["ly"],
        kt=raw["kt"],
        h_conv=raw["h_conv"],
        t_amb=raw["t_amb"],
        t_max_allowed=raw["t_max_allowed"],
        components=comps,
    )
