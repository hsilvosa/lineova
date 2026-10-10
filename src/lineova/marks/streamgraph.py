"""Streamgraph: stacked areas around a moving baseline, for the rise and fall of many categories over time."""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._color import readable_on
from .._data import DataError
from ..scales import BandScale
from ._base import Domain, DrawContext
from .line import AreaLayer

_AUTO = "auto"


class StreamLayer(AreaLayer):
    """Same input as ``lv.area`` (several series). ``offset`` is ``"wiggle"`` (default; keeps the slope
    of the layers small), ``"silhouette"`` (centred on the middle) or ``"zero"`` (an ordinary stacked area).
    Layers are ordered inside-out by peak time when ``order="inside-out"`` (default), or as given with ``"input"``.
    """

    legend_shape = "square"
    emphasize_zero = False

    def __init__(self, data=None, x=None, y=None, color=_AUTO, *, offset="wiggle", order="inside-out", **kw):
        kw.pop("stack", None)
        kw.pop("normalize", None)
        super().__init__(data, x, y, color, stack=True, normalize=False, **kw)
        if offset not in ("wiggle", "silhouette", "zero"):
            raise DataError("offset must be 'wiggle', 'silhouette' or 'zero'.")
        if order not in ("inside-out", "input"):
            raise DataError("order must be 'inside-out' or 'input'.")
        self.offset, self.order = offset, order

    def prepare(self, chart) -> None:
        super().prepare(chart)
        if self.xy.x_kind == "cat":
            raise DataError("A streamgraph needs a numeric or time x axis.")
        series = self.xy.series
        if len(series) < 2:
            raise DataError("A streamgraph needs at least 2 series (use lv.area for one).")
        # recover the per-series values from the stacked tops
        tops = self.tops
        vals = np.vstack([tops[0:1], np.diff(tops, axis=0)])
        if self.order == "inside-out" and len(series) > 2:
            peak = np.argmax(vals, axis=1)
            by_peak = np.argsort(peak, kind="stable")
            left, right = [], []
            weight_l = weight_r = 0.0
            for i in by_peak:
                w = float(vals[i].sum())
                if weight_l < weight_r:
                    left.append(i)
                    weight_l += w
                else:
                    right.append(i)
                    weight_r += w
            perm = list(reversed(left)) + right
            vals = vals[perm]
            self.perm = perm
        else:
            self.perm = list(range(len(series)))
        tops = np.cumsum(vals, axis=0)
        total = tops[-1]
        n, m = tops.shape
        if self.offset == "zero":
            base = np.zeros(m)
        elif self.offset == "silhouette":
            base = -total / 2
        else:
            base = np.zeros(m)
            y = 0.0
            for j in range(1, m):
                s1 = s2 = 0.0
                for i in range(n):
                    sij0, sij1 = tops[i, j], tops[i, j - 1]
                    s3 = (sij0 - sij1) / 2 + float(np.sum(tops[:i, j] - tops[:i, j - 1]))
                    s1 += sij0
                    s2 += s3 * sij0
                base[j - 1] = y
                if s1:
                    y -= s2 / s1
            base[m - 1] = y
            base = base - (base + total / 2).mean()          # centre the whole stream on zero
        self.vals = vals
        self.lower = base + np.vstack([np.zeros(m), tops[:-1]])
        self.upper = base + tops
        chart._y.visible = False             # the offsets are not data, so the axis would mislead
        if chart._y.zero == _AUTO:
            chart._y.zero = False

    def keys(self):
        names = [s.name for s in self.xy.series]
        return [names[i] for i in getattr(self, "perm", range(len(names)))]

    def y_domain(self):
        return Domain("num", float(self.lower.min()), float(self.upper.max()), nice=False, pad=0.04)

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        xs, ys = ctx.xs, ctx.ys
        if isinstance(xs, BandScale):
            raise DataError("A streamgraph needs a numeric or time x axis.")
        gx = xs(self.grid)
        names = [s.name for s in self.xy.series]
        order = self.perm
        for k, i in enumerate(order):
            color = ctx.color(names[i], i)
            hl = ctx.highlight
            if hl and names[i] not in hl:
                color = theme.muted
            top, bot = ys(self.upper[k]), ys(self.lower[k])
            ctx.scene.add(S.Polyline(np.concatenate((gx, gx[::-1])), np.concatenate((top, bot[::-1])), fill=color,
                                     fill_opacity=0.9, closed=True, hatch=ctx.texture(names[i], i)))
            ctx.scene.add(S.Polyline(gx, top, stroke=theme.background, stroke_width=0.8))
            peak = int(np.argmax(self.vals[k]))
            thick = float(bot[peak] - top[peak])
            if thick > theme.font_size * 2.0 and ctx.options.get("_legend_mode") != "none":
                ctx.scene.add(S.Text(float(gx[peak]), float((top[peak] + bot[peak]) / 2), str(names[i]),
                                     theme.font_size - 0.5, readable_on(color),
                                     anchor="middle", baseline="middle", weight=600))
