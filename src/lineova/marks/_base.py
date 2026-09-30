"""Shared types for marks (chart layers)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from ..scene import Scene
from ..themes import Theme


@dataclass
class Domain:
    """What a layer needs from one axis."""
    kind: str = "num"                   # num | time | cat
    lo: float = np.inf
    hi: float = -np.inf
    categories: Optional[list] = None
    zero: bool = False                  # must include 0 (bars, areas, histograms)
    nice: bool = True                   # extend to round tick values
    pad: float = 0.0                    # fractional padding when not nice
    log_ok: bool = True
    gap: Optional[float] = None         # band gap for categorical axes (None = theme default)
    extent: Optional[tuple] = None      # raw data extent, for range-frame axes
    min_positive: Optional[float] = None  # smallest value > 0 (lower end of a log axis)

    def merge(self, other: Domain) -> Domain:
        if other is None:
            return self
        kind = self.kind if self.kind == other.kind else ("cat" if "cat" in (self.kind, other.kind) else other.kind)
        cats = None
        if self.categories or other.categories:
            seen = dict.fromkeys((self.categories or []) + (other.categories or []))
            cats = list(seen)
        ext = None
        if self.extent or other.extent:
            e = [v for v in (self.extent, other.extent) if v]
            ext = (min(a for a, _ in e), max(b for _, b in e))
        gap = self.gap if self.gap is not None else other.gap
        mp = [v for v in (self.min_positive, other.min_positive) if v]
        return Domain(kind, min(self.lo, other.lo), max(self.hi, other.hi), cats,
                      self.zero or other.zero, self.nice and other.nice, max(self.pad, other.pad),
                      self.log_ok and other.log_ok, gap, ext, min(mp) if mp else None)


@dataclass
class LegendItem:
    key: str
    label: str
    color: str
    shape: str = "square"               # square | circle | line | hatch
    dash: Any = None


@dataclass
class Plot:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


@dataclass
class DrawContext:
    scene: Scene
    theme: Theme
    plot: Plot
    xs: Any                             # x scale (horizontal)
    ys: Any                             # y scale (vertical)
    colors: dict                        # series key -> colour
    highlight: set
    raster_scale: float = 2.0
    options: dict = field(default_factory=dict)
    end_labels: list = field(default_factory=list)   # (key, label, x_px, y_px) for direct labels
    notes: list = field(default_factory=list)        # small annotations (e.g. fit equation)
    overlay: list = field(default_factory=list)      # ops drawn after the plot clip (outside labels)
    readout: list = field(default_factory=list)      # series samples for the HTML crosshair readout

    def color(self, key: str, i: int = 0) -> str:
        return self.colors.get(key) or self.theme.color(i)

    def texture(self, key: str, i: int = 0) -> Optional[str]:
        """Texture for a series when ``texture=True`` (a second encoding besides colour), else None."""
        return texture_for(self.options.get("texture"), list(self.colors), key, i, self.theme)


TEXTURES = ("/", "\\", ".", "x", "-", "|")


def texture_for(setting, keys, key, i, theme) -> Optional[str]:
    if not setting:
        return None
    kinds = tuple(setting) if isinstance(setting, (list, tuple)) else TEXTURES
    idx = keys.index(key) if key in keys else i
    return f"{theme.background}|{kinds[idx % len(kinds)]}"


class Layer:
    """Base class. Subclasses fill in ``prepare`` and ``draw``."""

    cartesian = True
    legend_shape = "square"
    supports_direct_labels = False
    wants_readout = False
    emphasize_zero = True      # draw y = 0 as a baseline (off for point clouds)

    def prepare(self, chart) -> None:            # resolve data; called once per build
        raise NotImplementedError

    def keys(self) -> list[str]:                 # series identities, in order
        return []

    def x_domain(self) -> Optional[Domain]:
        return None

    def y_domain(self) -> Optional[Domain]:
        return None

    def draw(self, ctx: DrawContext) -> None:
        raise NotImplementedError

    def legend_items(self, ctx: DrawContext) -> list[LegendItem]:
        return [LegendItem(k, k, ctx.color(k, i), self.legend_shape) for i, k in enumerate(self.keys())]

    def colorbar(self):                          # (lut_stops, vmin, vmax, label) or None
        return None

    def default_size(self, theme: Theme) -> Optional[tuple[float, float]]:
        return None

    def axis_labels(self) -> tuple[Optional[str], Optional[str]]:
        return None, None

    def readout(self, ctx: DrawContext) -> list[tuple[str, str, str]]:
        """(key, colour, value text) for the instrument-style readout panel."""
        return []
