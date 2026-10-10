"""Marimekko (mosaic) charts: column width is one total, segment height is a share inside the column."""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._color import readable_on
from .._data import DataError, columns_of, get_column, is_frame, to_array
from .._text import format_value, text_width, truncate
from ._base import DrawContext, Layer, LegendItem

_AUTO = "auto"


class MarimekkoLayer(Layer):
    """Nested dict ``{column: {segment: value}}``, or long data: ``x=`` (column), ``y=`` (segment), ``value=``.

    Both dimensions carry information: the width of a column is its share of the grand total, the height
    of a segment its share of the column. Hard to read beyond ~6 columns and ~5 segments.
    """

    cartesian = False

    def __init__(self, data=None, x=None, y=None, value=None, *, labels=_AUTO, format=None, gap=2.0, sort=False):
        self.data, self.x, self.y, self.value = data, x, y, value
        self.labels, self.fmt, self.gap, self.sort = labels, format, float(gap), sort

    def prepare(self, chart) -> None:
        data = self.data
        cols: dict = {}
        if isinstance(data, dict):
            for c, seg in data.items():
                if not isinstance(seg, dict):
                    raise DataError("Pass {column: {segment: value}}.")
                cols[str(c)] = {str(k): float(v) for k, v in seg.items()}
        elif is_frame(data):
            names = [str(c) for c in columns_of(data)]
            xc = self.x if self.x is not None else names[0]
            yc = self.y if self.y is not None else names[1]
            vc = self.value if self.value is not None else names[2]
            xv = to_array(get_column(data, xc))
            yv = to_array(get_column(data, yc))
            vv = np.asarray(to_array(get_column(data, vc)), float)
            for a, b, v in zip(xv.tolist(), yv.tolist(), vv.tolist()):
                cols.setdefault(str(a), {})
                cols[str(a)][str(b)] = cols[str(a)].get(str(b), 0.0) + float(v)
        else:
            raise DataError("Pass a nested dict or a DataFrame with x, y and value columns.")
        segs = list(dict.fromkeys(k for seg in cols.values() for k in seg))
        mat = np.array([[cols[c].get(s, 0.0) for s in segs] for c in cols], float)
        if np.any(mat < 0):
            raise DataError("Marimekko values can't be negative.")
        totals = mat.sum(axis=1)
        keep = totals > 0
        if not keep.any():
            raise DataError("All values are zero.")
        names = [c for c, k in zip(cols, keep) if k]
        mat, totals = mat[keep], totals[keep]
        if self.sort:
            o = np.argsort(-totals, kind="stable")
            names, mat, totals = [names[i] for i in o], mat[o], totals[o]
        self.cols, self.segs, self.mat, self.totals = names, segs, mat, totals

    def keys(self):
        return list(self.segs)

    def legend_items(self, ctx):
        return [LegendItem(k, k, ctx.color(k, i), "square") for i, k in enumerate(self.segs)]

    def default_size(self, theme):
        return 680.0, 480.0

    def _fmt(self, v):
        if self.fmt is not None:
            return self.fmt(v) if callable(self.fmt) else (self.fmt.format(v) if "{" in self.fmt else format(v, self.fmt))
        return format_value(v)

    def draw(self, ctx: DrawContext) -> None:
        theme, plot = ctx.theme, ctx.plot
        size = theme.font_size - 0.5
        left, bottom, top = plot.x + 38, plot.bottom - size * 2.6, plot.y + 4
        width = plot.right - left
        H = bottom - top
        n = len(self.cols)
        grand = float(self.totals.sum())
        usable = width - self.gap * (n - 1)
        # y axis in percent
        for p in (0, 0.25, 0.5, 0.75, 1.0):
            y = bottom - p * H
            ctx.scene.add(S.Text(left - 6, y, f"{p:.0%}", size, theme.ink_muted, anchor="end", baseline="middle"))
        x = left
        hl = ctx.highlight
        for ci, c in enumerate(self.cols):
            w = usable * self.totals[ci] / grand
            share = self.mat[ci] / self.totals[ci]
            y = bottom
            for si, s in enumerate(self.segs):
                h = H * share[si]
                if h <= 0:
                    continue
                y -= h
                color = ctx.color(s, si)
                if hl and s not in hl:
                    color = theme.muted
                ctx.scene.add(S.Rect(x, y, w, h, fill=color, stroke=theme.background, stroke_width=1.0,
                                     hatch=ctx.texture(s, si),
                                     title=f"{c} · {s}: {self._fmt(self.mat[ci, si])} ({share[si]:.0%} of {c})"))
                want = self.labels is True or (self.labels == _AUTO and h > size * 1.6 and w > 34)
                if want:
                    txt = f"{share[si]:.0%}"
                    if text_width(txt, size, theme.font_kind) < w - 6:
                        ctx.scene.add(S.Text(x + w / 2, y + h / 2, txt, size, readable_on(color), anchor="middle",
                                             baseline="middle", weight=600))
            lab = truncate(str(c), max(24.0, w + self.gap - 2), size, theme.font_kind, True)
            ctx.scene.add(S.Text(x + w / 2, bottom + size * 1.2, lab, size, theme.ink, anchor="middle", weight=600))
            ctx.scene.add(S.Text(x + w / 2, bottom + size * 2.4, self._fmt(self.totals[ci]), size - 0.5,
                                 theme.ink_muted, anchor="middle"))
            x += w + self.gap
