"""Waterfall (bridge) charts: how a starting value becomes an ending value."""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._color import mix
from .._data import DataError, is_auto
from .._text import MINUS, format_value, text_width
from ._base import Domain, DrawContext, Layer, LegendItem
from ._geom import rounded_bar
from .bar import BarLayer

_AUTO = "auto"


class WaterfallLayer(Layer):
    own_legend = False

    def __init__(self, data=None, x=None, y=None, *, start=None, total=_AUTO, subtotals=None, labels=_AUTO,
                 format=None, agg="sum"):
        self.data, self.x, self.y = data, x, y
        self.start, self.total, self.subtotals = start, total, set(map(str, subtotals or []))
        self.labels, self.fmt, self.agg = labels, format, agg

    def prepare(self, chart) -> None:
        helper = BarLayer(self.data, self.x, self.y, None, agg=self.agg)
        cats, series, _, yl, _ = helper._resolve()
        if len(series) != 1:
            raise DataError("A waterfall takes one column of changes.")
        deltas = np.nan_to_num(series[0][1].astype(float))
        steps = []                          # (label, kind, bottom, top, value)
        run = 0.0
        if self.start is not None:
            label, value = self.start if isinstance(self.start, tuple) else ("Start", self.start)
            run = float(value)
            steps.append((str(label), "total", 0.0, run, run))
        for c, d in zip(cats, deltas):
            if c in self.subtotals:
                steps.append((c, "total", 0.0, run, run))
                continue
            steps.append((c, "up" if d >= 0 else "down", run, run + d, d))
            run += d
        want_total = self.total is not False
        if want_total:
            name = "Total" if (is_auto(self.total) or self.total is True) else str(self.total)
            steps.append((name, "total", 0.0, run, run))
        self.steps = steps
        self.y_label = yl

    def keys(self):
        return ["Increase", "Decrease", "Total"]

    def legend_items(self, ctx):
        t = ctx.theme
        kinds = {k for _, k, *_ in self.steps}
        out = []
        if "up" in kinds:
            out.append(LegendItem("Increase", "Increase", t.positive))
        if "down" in kinds:
            out.append(LegendItem("Decrease", "Decrease", t.negative))
        return out

    def x_domain(self):
        return Domain("cat", categories=[s[0] for s in self.steps])

    def y_domain(self):
        v = [b for _, _, b, t, _ in self.steps] + [t for _, _, b, t, _ in self.steps]
        return Domain("num", min(v), max(v), zero=True, nice=True)

    def axis_labels(self):
        return None, self.y_label

    def _fmt(self, v, signed=False):
        if self.fmt is not None:
            s = self.fmt(abs(v) if signed else v) if callable(self.fmt) else \
                (self.fmt.format(abs(v) if signed else v) if "{" in self.fmt else format(abs(v) if signed else v, self.fmt))
        else:
            s = format_value(abs(v) if signed else v)
        if signed:
            return ("+" if v >= 0 else MINUS) + s
        return s

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        xs, ys = ctx.xs, ctx.ys
        band = xs.bandwidth
        size = theme.font_size - 0.5
        show = self.labels is True or (is_auto(self.labels) and len(self.steps) <= 20)
        total_col = theme.ink_secondary if theme.family != "instrument" else theme.ink_muted
        prev_end = None
        for i, (label, kind, lo, hi, value) in enumerate(self.steps):
            x0 = xs.band(i)
            y0, y1 = ys.scalar(lo), ys.scalar(hi)
            top, h = min(y0, y1), max(abs(y1 - y0), 0.8)
            color = {"up": theme.positive, "down": theme.negative, "total": total_col}[kind]
            end = "top" if hi >= lo else "bottom"
            r = min(theme.bar_radius, 3.0, band / 2)
            hatch = theme.ink if (theme.family == "folio" and kind == "down") else None
            fill = mix(theme.ink, theme.background, 0.75) if (theme.family == "folio" and kind == "down") else color
            ctx.scene.add(S.Path(rounded_bar(x0, top, band, h, r if kind == "total" else 0, end), fill=fill,
                                 hatch=hatch, stroke=theme.ink if theme.family == "folio" else None, stroke_width=0.7,
                                 title=f"{label}: {self._fmt(value, kind != 'total')}"))
            if prev_end is not None:
                px, pyv = prev_end
                ctx.scene.add(S.Line(px, pyv, x0, pyv, theme.ink_muted, 0.8, dash=(2, 2)))
            prev_end = (x0 + band, ys.scalar(hi))
            if show:
                txt = self._fmt(value, kind != "total")
                if text_width(txt, size, theme.font_kind) > band + 18:
                    continue
                above = hi >= lo
                ty = (top - 5) if above else (top + h + size + 3)
                ctx.overlay.append(S.Text(x0 + band / 2, ty, txt, size, theme.ink if kind == "total" else theme.ink_secondary,
                                     anchor="middle", weight=600 if kind == "total" else 400))
