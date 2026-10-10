"""Horizon charts: many time series stacked in thin rows, large values folded into darker bands."""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._color import mix
from .._data import DataError, interval_spec, resolve_xy
from .._text import format_value
from ._base import Domain, DrawContext, Layer
from .line import _nanrange

_AUTO = "auto"


class HorizonLayer(Layer):
    """Same input as ``lv.line`` (several series). Each series gets one row. The value range is cut into
    ``bands`` equal slices; slice *k* is drawn over slice *k − 1* in a darker tone, so a row of height *h*
    shows values up to ``bands`` times higher than a plain area would. Values below ``baseline`` use the
    negative colour. ``scale="shared"`` (default) uses one step for all rows, ``"each"`` one step per row.
    """

    legend_shape = "square"

    def __init__(self, data=None, x=None, y=None, color=_AUTO, *, bands=3, baseline=0.0, scale="shared",
                 label=None):
        self.data, self.x, self.y, self.color = data, x, y, color
        self.bands, self.baseline, self.scale, self.label = bands, baseline, scale, label

    def prepare(self, chart) -> None:
        if not 1 <= int(self.bands) <= 6:
            raise DataError("bands must be between 1 and 6.")
        if self.scale not in ("shared", "each"):
            raise DataError("scale must be 'shared' or 'each'.")
        xy = resolve_xy(self.data, self.x, self.y, self.color, extra=interval_spec(None))
        if xy.x_kind == "cat":
            raise DataError("A horizon chart needs a numeric or time x axis.")
        if self.label and len(xy.series) == 1:
            xy.series[0].name = str(self.label)
        for s in xy.series:
            ok = np.isfinite(s.x) & np.isfinite(s.y)
            order = np.argsort(s.x[ok], kind="stable")
            s.x, s.y = s.x[ok][order], s.y[ok][order]
        self.xy = xy
        base = float(self.baseline)
        dev = [np.abs(s.y - base) for s in xy.series if len(s.y)]
        if not dev:
            raise DataError("No data to draw.")
        self.step_shared = (max(float(d.max()) for d in dev) or 1.0) / int(self.bands)
        self.steps = [((float(np.abs(s.y - base).max()) or 1.0) / int(self.bands)) if self.scale == "each"
                      else self.step_shared for s in xy.series]

    def keys(self):
        return [s.name for s in self.xy.series]

    def legend_items(self, ctx):
        return []

    def x_domain(self):
        lo, hi = _nanrange(s.x for s in self.xy.series)
        return Domain(self.xy.x_kind, lo, hi, nice=False, extent=(lo, hi))

    def y_domain(self):
        return Domain("cat", categories=list(reversed(self.keys())), gap=0.08)

    def axis_labels(self):
        note = (f"Each row: {int(self.bands)} bands of {format_value(self.step_shared)}" if self.scale == "shared"
                else f"Each row: {int(self.bands)} bands, step set per row")
        lab = self.xy.x_label
        return (f"{lab}  ·  {note}" if lab else note), None

    def default_size(self, theme):
        rows = len(self.xy.series)
        return None, float(min(max(rows * 38 + 120, 220), 1600))

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        xs, ys = ctx.xs, ctx.ys
        nb = int(self.bands)
        base = float(self.baseline)
        pos_col = theme.palette[0] if theme.family != "folio" else theme.ink_secondary
        neg_col = theme.negative
        size = theme.font_size - 1
        cols = max(32, int(ctx.plot.w * ctx.raster_scale))
        for i, s in enumerate(self.xy.series):
            if len(s.x) == 0:
                continue
            x, y = s.x, s.y
            if len(x) > 2 * cols:                    # resample to the pixel grid; a horizon needs no more
                g = np.linspace(x[0], x[-1], 2 * cols)
                y = np.interp(g, x, y)
                x = g
            px = xs(x)
            h = abs(ys.bandwidth)                    # a reversed axis gives a negative bandwidth
            y0 = min(ys.band(ys.index[s.name]), ys.band(ys.index[s.name]) + ys.bandwidth)    # top edge of the row
            step = self.steps[i]
            dev = y - base
            for sign, color in ((1.0, pos_col), (-1.0, neg_col)):
                d = np.clip(sign * dev, 0, None)
                if not d.any():
                    continue
                for k in range(nb):
                    part = np.clip(d - k * step, 0, step) / step
                    if not part.any():
                        break
                    tone = mix(theme.background, color, 0.30 + 0.70 * (k + 1) / nb)
                    py = y0 + h - part * h
                    ctx.scene.add(S.Polyline(np.concatenate(([px[0]], px, [px[-1]])),
                                             np.concatenate(([y0 + h], py, [y0 + h])),
                                             fill=tone if nb > 1 else color, closed=True))
            ctx.scene.add(S.Line(float(px[0]), y0 + h, float(px[-1]), y0 + h, theme.grid_color, 0.8))
            peak = float(np.max(np.abs(s.y - base)))
            ctx.overlay.append(S.Text(ctx.plot.right - 4, y0 + size * 1.1, "±" + format_value(peak), size,
                                      theme.ink_muted, anchor="end", halo=theme.background))
