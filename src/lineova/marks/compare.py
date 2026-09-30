"""Before/after comparisons: dumbbell (dot plot with two ends) and slope charts."""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._data import (DataError, aggregate, as_float, factorize, get_column, is_auto, is_frame, to_array)
from .._text import format_value, text_width, truncate
from ._base import Domain, DrawContext, Layer, LegendItem
from ._geom import spread_labels

_AUTO = "auto"


def resolve_pairs(data, y=None, x=None, color=None, labels=None, agg="mean"):
    """-> (categories, start values, end values, (start name, end name))."""
    if isinstance(data, dict) and data and all(np.ndim(v) == 1 and len(v) == 2 for v in data.values()):
        cats = [str(k) for k in data]
        a = np.array([float(v[0]) for v in data.values()])
        b = np.array([float(v[1]) for v in data.values()])
        return cats, a, b, tuple(labels or ("Before", "After"))
    if is_frame(data):
        if y is None:
            raise DataError("Pass y='category column'.")
        cat_v = to_array(get_column(data, y))
        if isinstance(x, (tuple, list)) and len(x) == 2:
            names, a = aggregate(cat_v, to_array(get_column(data, x[0])), agg)
            _, b = aggregate(cat_v, to_array(get_column(data, x[1])), agg)
            return names, a, b, tuple(labels or (str(x[0]), str(x[1])))
        if isinstance(x, str) and color is not None:
            period = to_array(get_column(data, color))
            codes, periods = factorize(period)
            if len(periods) != 2:
                raise DataError(f"{color!r} must have exactly two values (e.g. two years); found {len(periods)}.")
            try:
                periods_sorted = sorted(periods, key=float)
            except ValueError:
                periods_sorted = periods
            vals = as_float(to_array(get_column(data, x)), "num")
            out = []
            for p in periods_sorted:
                sel = codes == periods.index(p)
                names, v = aggregate(cat_v[sel], vals[sel], agg)
                out.append(dict(zip(names, v)))
            cats = [c for c in dict.fromkeys(list(out[0]) + list(out[1]))]
            a = np.array([out[0].get(c, np.nan) for c in cats])
            b = np.array([out[1].get(c, np.nan) for c in cats])
            return cats, a, b, tuple(labels or periods_sorted)
    raise DataError("Pass {category: (before, after)}, or a DataFrame with y='category' and x=('before', 'after').")


class DumbbellLayer(Layer):
    """Two dots per row joined by a line: shows the gap or change between two values."""

    def __init__(self, data=None, x=None, y=None, color=None, *, labels=None, sort=_AUTO, values=_AUTO, agg="mean"):
        self.data, self.x, self.y, self.color = data, x, y, color
        self.labels, self.sort, self.values, self.agg = labels, sort, values, agg

    def prepare(self, chart) -> None:
        cats, a, b, names = resolve_pairs(self.data, self.y, self.x, self.color, self.labels, self.agg)
        if self.sort is True or is_auto(self.sort):
            order = np.argsort(-np.nan_to_num(b), kind="stable")
            cats, a, b = [cats[i] for i in order], a[order], b[order]
        self.cats, self.a, self.b, self.names = cats, a, b, [str(n) for n in names]

    def keys(self):
        return list(self.names)

    def legend_items(self, ctx):
        return [LegendItem(n, n, ctx.color(n, i), "circle") for i, n in enumerate(self.names)]

    def x_domain(self):
        v = np.concatenate([self.a, self.b])
        lo, hi = float(np.nanmin(v)), float(np.nanmax(v))
        return Domain("num", lo, hi, nice=True, pad=0.04, extent=(lo, hi))

    def y_domain(self):
        return Domain("cat", categories=list(reversed(self.cats)), gap=0.0)

    def default_size(self, theme):
        return None, float(min(max(len(self.cats) * 30 + 150, 240), 1600))

    def values_for_reference(self, axis):
        return [self.a, self.b] if axis == "x" else []

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        ca, cb = ctx.color(self.names[0], 0), ctx.color(self.names[1], 1)
        show = self.values is True or (is_auto(self.values) and len(self.cats) <= 16)
        size = theme.font_size - 0.5
        hl = ctx.highlight
        for c, va, vb in zip(self.cats, self.a, self.b):
            if not (np.isfinite(va) and np.isfinite(vb)):
                continue
            y = float(ctx.ys.center(ctx.ys.index[c]))
            xa, xb = ctx.xs.scalar(va), ctx.xs.scalar(vb)
            dim = bool(hl) and c not in hl
            ctx.scene.add(S.Line(xa, y, xb, y, theme.muted if not dim else theme.grid_color, 3.0, cap="round"))
            ctx.scene.add(S.Markers(np.array([xa, xb]), np.array([y, y]), "circle", 5.5,
                                    fill=[theme.muted if dim else ca, theme.muted if dim else cb],
                                    stroke=theme.background, stroke_width=1.5,
                                    titles=[f"{c} · {self.names[0]}: {format_value(va)}",
                                            f"{c} · {self.names[1]}: {format_value(vb)}"]))
            if show:
                left, right = (xa, va), (xb, vb)
                if xa > xb:
                    left, right = right, left
                ctx.scene.add(S.Text(left[0] - 9, y, format_value(left[1]), size, theme.ink_secondary,
                                     anchor="end", baseline="middle"))
                ctx.scene.add(S.Text(right[0] + 9, y, format_value(right[1]), size, theme.ink,
                                     baseline="middle", weight=600))


class SlopeLayer(Layer):
    """Two vertical axes (before, after) with one line per item: rank and direction at a glance."""

    cartesian = False
    own_legend = True

    def __init__(self, data=None, x=None, y=None, color=None, *, labels=None, agg="mean", format=None):
        self.data, self.x, self.y, self.color = data, x, y, color
        self.labels, self.agg, self.fmt = labels, agg, format

    def prepare(self, chart) -> None:
        cats, a, b, names = resolve_pairs(self.data, self.y, self.x, self.color, self.labels, self.agg)
        ok = np.isfinite(a) & np.isfinite(b)
        self.cats = [c for c, k in zip(cats, ok) if k]
        self.a, self.b = a[ok], b[ok]
        self.names = [str(n) for n in names]

    def keys(self):
        return list(self.cats)

    def default_size(self, theme):
        return 560.0, float(min(max(len(self.cats) * 26 + 160, 320), 1200))

    def _fmt(self, v):
        if self.fmt is not None:
            return self.fmt(v) if callable(self.fmt) else (self.fmt.format(v) if "{" in self.fmt else format(v, self.fmt))
        return format_value(v)

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        plot = ctx.plot
        size = theme.font_size
        kind = theme.font_kind
        lw = max(text_width(f"{c}  {self._fmt(v)}", size, kind) for c, v in zip(self.cats, self.a)) + 12
        rw = max(text_width(f"{self._fmt(v)}  {c}", size, kind) for c, v in zip(self.cats, self.b)) + 12
        lw, rw = min(lw, plot.w * 0.34), min(rw, plot.w * 0.34)
        x0, x1 = plot.x + lw, plot.right - rw
        top, bottom = plot.y + size * 2.4, plot.bottom - size
        v = np.concatenate([self.a, self.b])
        lo, hi = float(v.min()), float(v.max())
        span = (hi - lo) or 1.0

        def py(val):
            return bottom - (val - lo) / span * (bottom - top)

        for x, name in ((x0, self.names[0]), (x1, self.names[1])):
            ctx.scene.add(S.Line(x, top - 4, x, bottom + 4, theme.axis_color, theme.axis_width))
            ctx.scene.add(S.Text(x, plot.y + size, name, size + 1, theme.ink, anchor="middle", weight=600))
        hl = ctx.highlight
        ya = spread_labels([py(t) for t in self.a], size * 1.25, top, bottom)
        yb = spread_labels([py(t) for t in self.b], size * 1.25, top, bottom)
        items = list(range(len(self.cats)))
        # muted lines first so coloured ones sit on top
        items.sort(key=lambda i: 1 if (not hl or self.cats[i] in hl) else 0)
        for i in items:
            c, va, vb = self.cats[i], self.a[i], self.b[i]
            if hl:
                col = theme.accent if c in hl else theme.muted
            elif theme.family == "folio":
                col = theme.ink if vb >= va else theme.ink_muted
            else:
                col = theme.positive if vb >= va else theme.negative
            ctx.scene.add(S.Line(x0, py(va), x1, py(vb), col, 2.0 if (not hl or c in hl) else 1.2, cap="round"))
            ctx.scene.add(S.Markers(np.array([x0, x1]), np.array([py(va), py(vb)]), "circle", 3.5, fill=col,
                                    stroke=theme.background, stroke_width=1.2,
                                    titles=[f"{c}: {self._fmt(va)}", f"{c}: {self._fmt(vb)}"]))
            ink = theme.ink if (not hl or c in hl) else theme.ink_muted
            ctx.scene.add(S.Text(x0 - 8, ya[i], truncate(f"{c}  {self._fmt(va)}", lw - 10, size, kind), size, ink,
                                 anchor="end", baseline="middle"))
            ctx.scene.add(S.Text(x1 + 8, yb[i], truncate(f"{self._fmt(vb)}  {c}", rw - 10, size, kind), size, ink,
                                 baseline="middle"))
