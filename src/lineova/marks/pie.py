"""Pie and donut charts.

Defaults steer toward readable pies: at most 6 slices (the rest fold into
"Other"), largest first from 12 o'clock, labels outside with name and share.
"""

from __future__ import annotations

import math
import warnings

import numpy as np

from .. import scene as S
from .._color import readable_on
from .._data import DataError, is_auto
from .._text import format_value, text_width, truncate
from ._base import DrawContext, Layer, LegendItem
from ._geom import spread_labels, wedge
from .bar import BarLayer

_AUTO = "auto"


class PieLayer(Layer):
    cartesian = False
    own_legend = True

    def __init__(self, data=None, x=None, y=None, *, donut=_AUTO, top=_AUTO, sort=_AUTO, labels=_AUTO,
                 center=_AUTO, format=None, agg="sum", start=90.0):
        self.data, self.x, self.y = data, x, y
        self.donut, self.top, self.sort, self.labels = donut, top, sort, labels
        self.center, self.fmt, self.agg, self.start = center, format, agg, start

    def prepare(self, chart) -> None:
        theme = chart.resolved_theme
        helper = BarLayer(self.data, self.x, self.y, None, agg=self.agg)
        cats, series, _, _, ordered = helper._resolve()
        if len(series) != 1:
            raise DataError("A pie shows one set of values. Pass {label: value} or a single value column.")
        values = np.nan_to_num(series[0][1].astype(float))
        if np.any(values < 0):
            raise DataError("Pie slices can't be negative. Use a bar chart for data with negative values.")
        if values.sum() <= 0:
            raise DataError("All pie values are zero.")
        order = np.arange(len(cats))
        if self.sort is True or (is_auto(self.sort) and not ordered):
            order = np.argsort(-values, kind="stable")
        cats = [cats[i] for i in order]
        values = values[order]
        limit = 6 if is_auto(self.top) else (int(self.top) if self.top else len(cats))
        if len(cats) > limit:
            if is_auto(self.top):
                warnings.warn(f"{len(cats)} slices are hard to compare; the smallest {len(cats) - limit + 1} are grouped "
                              "as 'Other'. A bar chart shows many categories better (lv.bar).", stacklevel=4)
            keep = np.argsort(-values, kind="stable")[: limit - 1]
            keep.sort()
            rest = np.setdiff1d(np.arange(len(cats)), keep)
            cats = [cats[i] for i in keep] + [f"Other ({len(rest)})"]
            values = np.append(values[keep], values[rest].sum())
        self.cats, self.values = cats, values
        self.total = float(values.sum())
        self.is_donut = (theme.family != "folio") if is_auto(self.donut) else bool(self.donut)

    def keys(self):
        return list(self.cats)

    def legend_items(self, ctx):
        return [LegendItem(c, c, ctx.color(c, i), "square") for i, c in enumerate(self.cats)]

    def default_size(self, theme):
        return 560.0, 380.0

    def _fmt(self, v):
        if self.fmt is not None:
            return self.fmt(v) if callable(self.fmt) else (self.fmt.format(v) if "{" in self.fmt else format(v, self.fmt))
        return format_value(v)

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        plot = ctx.plot
        size = theme.font_size
        show_labels = self.labels is not False and not (is_auto(self.labels) and len(self.cats) > 8)
        label_w = 0.0
        if show_labels:
            label_w = max(text_width(c, size, theme.font_kind, True) for c in self.cats) + 16
            label_w = min(label_w, plot.w * 0.28)
        r = max(20.0, min((plot.w - 2 * label_w - 40) / 2, plot.h / 2 - 8))
        cx, cy = plot.x + plot.w / 2, plot.y + plot.h / 2
        r_in = r * 0.58 if self.is_donut else 0.0
        a = -math.radians(self.start)        # 90° -> 12 o'clock (screen y points down)
        shares = self.values / self.total
        hl = ctx.highlight
        mids = []
        for i, (c, share) in enumerate(zip(self.cats, shares)):
            sweep = share * 2 * math.pi
            color = ctx.color(c, i)
            if hl and c not in hl:
                color = theme.muted
            if share > 0:
                ctx.scene.add(S.Path(wedge(cx, cy, r, r_in, a, a + sweep), fill=color, stroke=theme.background,
                                     stroke_width=2 if len(self.cats) > 1 else 0, join="round",
                                     title=f"{c}: {self._fmt(self.values[i])} ({share:.1%})"))
            mids.append((a + sweep / 2, share, color))
            a += sweep
        # labels: left and right columns, pushed apart so they never overlap
        if show_labels:
            gap = size * 2.6
            for side in (-1, 1):
                idx = [i for i, (m, _, _) in enumerate(mids) if (math.cos(m) >= 0) == (side > 0)]
                want = [cy + math.sin(mids[i][0]) * r * 1.08 for i in idx]
                got = spread_labels(want, gap, plot.y + size, plot.bottom - size)
                for i, ly in zip(idx, got):
                    m, share, color = mids[i]
                    ex, ey = cx + math.cos(m) * r, cy + math.sin(m) * r
                    bx = cx + side * (r + 14)
                    tx = cx + side * (r + 20)
                    ctx.scene.add(S.Path([("M", ex, ey), ("L", bx, ly), ("L", bx + side * 3, ly)],
                                         stroke=theme.ink_muted, stroke_width=0.8))
                    anchor = "start" if side > 0 else "end"
                    name = truncate(self.cats[i], label_w, size, theme.font_kind, True)
                    ctx.scene.add(S.Text(tx, ly - size * 0.2, name, size, theme.ink, anchor=anchor, weight=600,
                                         italic=theme.italic_labels))
                    ctx.scene.add(S.Text(tx, ly + size * 1.05, f"{share:.0%}" if share >= 0.01 else "<1%",
                                         size, theme.ink_secondary, anchor=anchor))
        elif len(self.cats) <= 8:
            # small inside labels when there's no room outside
            for m, share, color in mids:
                if share < 0.06:
                    continue
                rr = (r + r_in) / 2 if r_in else r * 0.62
                ctx.scene.add(S.Text(cx + math.cos(m) * rr, cy + math.sin(m) * rr, f"{share:.0%}", size,
                                     readable_on(color), anchor="middle", baseline="middle", weight=600))
        if self.is_donut and self.center is not False and self.center is not None:
            text = self._fmt(self.total) if is_auto(self.center) else str(self.center)
            big = min(theme.title_size * 1.9, r_in * 0.6)
            ctx.scene.add(S.Text(cx, cy + big * 0.1, text, big, theme.ink, anchor="middle", baseline="middle",
                                 weight=700))
            if is_auto(self.center):
                ctx.scene.add(S.Text(cx, cy + big * 0.1 + big * 0.75, "total", size, theme.ink_muted,
                                     anchor="middle", baseline="middle"))
