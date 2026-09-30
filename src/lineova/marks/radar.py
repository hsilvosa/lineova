"""Radar (spider) charts: several measures per item on spokes around a circle."""

from __future__ import annotations

import math
import warnings

import numpy as np

from .. import scene as S
from .._data import DataError, columns_of, get_column, is_auto, is_frame, to_array
from .._text import format_value, text_width
from ..scales import linear_ticks
from ._base import DrawContext, Layer, LegendItem

_AUTO = "auto"


class RadarLayer(Layer):
    cartesian = False
    legend_shape = "square"

    def __init__(self, data=None, *, axes=None, normalize=False, fill=_AUTO, range=None):
        self.data, self.axes_opt, self.normalize, self.fill, self.rng = data, axes, normalize, fill, range

    def prepare(self, chart) -> None:
        data = self.data
        series: dict = {}
        if isinstance(data, dict) and data and all(isinstance(v, dict) for v in data.values()):
            series = {str(k): {str(a): float(b) for a, b in v.items()} for k, v in data.items()}
        elif isinstance(data, dict):
            series = {"": {str(a): float(b) for a, b in data.items()}}
        elif is_frame(data):
            # rows are items, numeric columns are the measures; a text column names the rows
            cols = columns_of(data)
            name_col = next((c for c in cols if to_array(get_column(data, c)).dtype.kind in "OUS"), None)
            names = [str(v) for v in to_array(get_column(data, name_col))] if name_col is not None else \
                [str(v) for v in getattr(data, "index", range(len(to_array(get_column(data, cols[0])))))]
            measures = [c for c in cols if c != name_col and to_array(get_column(data, c)).dtype.kind in "iuf"]
            for r, nm in enumerate(names):
                series[nm] = {str(m): float(to_array(get_column(data, m))[r]) for m in measures}
        else:
            raise DataError("Pass {item: {measure: value}} or a DataFrame with one row per item.")
        axes = list(self.axes_opt or dict.fromkeys(a for v in series.values() for a in v))
        if len(axes) < 3:
            raise DataError("A radar chart needs at least 3 measures.")
        if len(series) > 6:
            warnings.warn(f"{len(series)} overlapping shapes are hard to read on a radar chart; consider small "
                          "multiples (lv.grid) or a bar chart.", stacklevel=4)
        self.axes = [str(a) for a in axes]
        self.series = series
        vals = np.array([[series[s].get(a, np.nan) for a in self.axes] for s in series], float)
        self.vals = vals
        if self.normalize:
            mx = np.nanmax(np.abs(vals), axis=0)
            self.scaled = vals / np.where(mx == 0, 1, mx)
            self.lo, self.hi = 0.0, 1.0
        else:
            lo = 0.0 if np.nanmin(vals) >= 0 else float(np.nanmin(vals))
            hi = float(np.nanmax(vals))
            if self.rng:
                lo, hi = self.rng
            else:
                ticks, step = linear_ticks(lo, hi, 4)
                hi = float(ticks[-1] + (step if ticks[-1] < hi else 0))
            self.lo, self.hi = lo, hi
            self.scaled = (vals - lo) / ((hi - lo) or 1)

    def keys(self):
        return [s for s in self.series if s]

    def legend_items(self, ctx):
        return [LegendItem(k, k, ctx.color(k, i), "square") for i, k in enumerate(self.keys())]

    def default_size(self, theme):
        return 600.0, 460.0

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        plot = ctx.plot
        size = theme.font_size
        k = len(self.axes)
        lab_w = max(text_width(a, size, theme.font_kind) for a in self.axes) + 12
        r = max(30.0, min(plot.w / 2 - lab_w, plot.h / 2 - size * 2))
        cx, cy = plot.x + plot.w / 2, plot.y + plot.h / 2
        ang = [-math.pi / 2 + 2 * math.pi * i / k for i in range(k)]
        # grid rings (polygons) and spokes
        rings = 4
        for j in range(1, rings + 1):
            rr = r * j / rings
            xs = np.array([cx + rr * math.cos(a) for a in ang + ang[:1]])
            ys = np.array([cy + rr * math.sin(a) for a in ang + ang[:1]])
            ctx.scene.add(S.Polyline(xs, ys, stroke=theme.grid_color if j < rings else theme.axis_color,
                                     stroke_width=1.0, dash=theme.grid_dash if j < rings else None))
            if not self.normalize:
                val = self.lo + (self.hi - self.lo) * j / rings
                ctx.scene.add(S.Text(cx + 5, cy - rr + size * 0.9, format_value(val), size - 1.5, theme.ink_muted,
                                     halo=theme.background))
        for a, name in zip(ang, self.axes):
            ctx.scene.add(S.Line(cx, cy, cx + r * math.cos(a), cy + r * math.sin(a), theme.grid_color, 1.0))
            lx, ly = cx + (r + 10) * math.cos(a), cy + (r + 10) * math.sin(a)
            anchor = "middle" if abs(math.cos(a)) < 0.2 else ("start" if math.cos(a) > 0 else "end")
            base = "hanging" if math.sin(a) > 0.5 else ("alphabetic" if math.sin(a) < -0.5 else "middle")
            ctx.scene.add(S.Text(lx, ly, name, size, theme.ink_secondary, anchor=anchor, baseline=base,
                                 italic=theme.italic_labels))
        # shapes
        fill = (theme.family != "folio") if is_auto(self.fill) else bool(self.fill)
        names = list(self.series)
        hl = ctx.highlight
        order = sorted(range(len(names)), key=lambda i: 1 if (not hl or names[i] in hl) else 0)
        for i in order:
            name = names[i]
            color = ctx.color(name, i) if name else theme.accent if theme.family != "ledger" else theme.palette[0]
            if hl and name not in hl:
                color = theme.muted
            t = np.clip(np.nan_to_num(self.scaled[i]), 0, 1.05)
            xs = np.array([cx + r * v * math.cos(a) for v, a in zip(t, ang)])
            ys = np.array([cy + r * v * math.sin(a) for v, a in zip(t, ang)])
            dash = theme.dashes[i % len(theme.dashes)] if theme.dashes else None
            ctx.scene.add(S.Polyline(np.append(xs, xs[0]), np.append(ys, ys[0]), stroke=color,
                                     stroke_width=theme.line_width, fill=color if fill else None,
                                     fill_opacity=0.14, dash=dash, closed=True))
            ctx.scene.add(S.Markers(xs, ys, "circle", 3.2, fill=color, stroke=theme.background, stroke_width=1.2,
                                    titles=[f"{name + ' · ' if name else ''}{a}: {format_value(v)}"
                                            for a, v in zip(self.axes, self.vals[i])]))
