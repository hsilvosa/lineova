"""Treemaps: nested rectangles with area proportional to value (squarified layout)."""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._color import mix, readable_on
from .._data import DataError, aggregate, as_float, get_column, is_frame, to_array
from .._text import format_value, text_width, truncate
from ._base import DrawContext, Layer

_AUTO = "auto"


def squarify(values, x, y, w, h) -> list[tuple[float, float, float, float]]:
    """Squarified treemap (Bruls, Huizing, van Wijk). ``values`` sorted descending, all > 0."""
    vals = [float(v) for v in values]
    total = sum(vals)
    if total <= 0 or w <= 0 or h <= 0:
        return [(x, y, 0.0, 0.0) for _ in vals]
    scale = w * h / total
    areas = [v * scale for v in vals]
    rects: list = []
    i = 0
    while i < len(areas):
        short = min(w, h)
        row = [areas[i]]
        j = i + 1

        def worst(r, short=short):
            s = sum(r)
            return max(max(s * s / (short * short * a), short * short * a / (s * s)) for a in r if a > 0) if s else 1e9

        while j < len(areas) and worst(row + [areas[j]]) <= worst(row):
            row.append(areas[j])
            j += 1
        s = sum(row)
        if w >= h:                        # lay the row out as a column on the left
            cw = s / h if h else 0
            yy = y
            for a in row:
                rh = a / cw if cw else 0
                rects.append((x, yy, cw, rh))
                yy += rh
            x, w = x + cw, w - cw
        else:                             # as a row on top
            rh = s / w if w else 0
            xx = x
            for a in row:
                rw = a / rh if rh else 0
                rects.append((xx, y, rw, rh))
                xx += rw
            y, h = y + rh, h - rh
        i = j
    return rects


class TreemapLayer(Layer):
    cartesian = False
    own_legend = False

    def __init__(self, data=None, *, path=None, value=None, labels=_AUTO, format=None, agg="sum"):
        self.data, self.path, self.value = data, path, value
        self.labels, self.fmt, self.agg = labels, format, agg

    def prepare(self, chart) -> None:
        data = self.data
        tree: dict = {}
        if is_frame(data) and not isinstance(data, dict):
            path = [self.path] if isinstance(self.path, str) else list(self.path or [])
            if not path or self.value is None and len(path) == 0:
                raise DataError("Pass path=['group', 'item'] (or one column) and value='column'.")
            vals = as_float(to_array(get_column(data, self.value)), "num") if self.value else None
            if len(path) == 1:
                names, v = aggregate(to_array(get_column(data, path[0])), vals, self.agg)
                tree = dict(zip(names, v))
            else:
                parent = to_array(get_column(data, path[0]))
                child = to_array(get_column(data, path[1]))
                key = np.array([f"{p}\x1f{c}" for p, c in zip(parent, child)], dtype=object)
                names, v = aggregate(key, vals, self.agg)
                for k, val in zip(names, v):
                    p, c = k.split("\x1f", 1)
                    tree.setdefault(p, {})[c] = val
        elif isinstance(data, dict):
            tree = data
        else:
            try:
                idx = data.index
                tree = dict(zip(map(str, idx), to_array(data)))
            except AttributeError:
                raise DataError("Pass {label: value}, {group: {label: value}}, or a DataFrame with path= and value=.") \
                    from None
        self.nested = any(isinstance(v, dict) for v in tree.values())
        items = []
        for k, v in tree.items():
            if isinstance(v, dict):
                kids = sorted(((str(a), float(b)) for a, b in v.items() if b and b > 0), key=lambda t: -t[1])
                if kids:
                    items.append((str(k), sum(b for _, b in kids), kids))
            elif v is not None and float(v) > 0:
                items.append((str(k), float(v), None))
        if not items:
            raise DataError("A treemap needs positive values.")
        items.sort(key=lambda t: -t[1])
        self.items = items
        self.total = sum(t[1] for t in items)

    def keys(self):
        return [k for k, _, _ in self.items] if self.nested else []

    def legend_items(self, ctx):
        return []

    def default_size(self, theme):
        return 720.0, 440.0

    def _fmt(self, v):
        if self.fmt is not None:
            return self.fmt(v) if callable(self.fmt) else (self.fmt.format(v) if "{" in self.fmt else format(v, self.fmt))
        return format_value(v)

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        plot = ctx.plot
        size = theme.font_size
        gap = 2.0
        rects = squarify([v for _, v, _ in self.items], plot.x, plot.y, plot.w, plot.h)
        n = len(self.items)
        for i, ((name, value, kids), (x, y, w, h)) in enumerate(zip(self.items, rects)):
            if self.nested:
                base = ctx.color(name, i)
                head = size + 8 if h > size * 3 and w > 40 else 0
                ctx.scene.add(S.Rect(x + gap / 2, y + gap / 2, w - gap, h - gap, fill=mix(base, theme.background, 0.82)))
                if head:
                    ctx.scene.add(S.Text(x + 6, y + size + 2, truncate(f"{name}  {self._fmt(value)}", w - 12, size,
                                                                     theme.font_kind, True), size, theme.ink, weight=700))
                sub = squarify([b for _, b in kids], x + 3, y + head + 3, w - 6, h - head - 6)
                for j, ((kn, kv), (sx, sy, sw, sh)) in enumerate(zip(kids, sub)):
                    shade = mix(base, theme.background, min(0.5, j / max(len(kids), 1) * 0.6))
                    self._cell(ctx, sx, sy, sw, sh, kn, kv, shade, f"{name} › {kn}: {self._fmt(kv)}")
            else:
                if theme.name == "folio":
                    fill = mix(theme.ink, theme.background, 0.25 + 0.6 * i / max(n - 1, 1))
                else:
                    fill = mix(ctx.theme.accent if ctx.highlight and name in ctx.highlight else theme.palette[0],
                               theme.background, 0.0 if (ctx.highlight and name in ctx.highlight) else
                               min(0.62, 0.62 * i / max(n - 1, 1)))
                    if ctx.highlight and name not in ctx.highlight:
                        fill = theme.muted
                self._cell(ctx, x, y, w, h, name, value, fill, f"{name}: {self._fmt(value)} "
                                                             f"({value / self.total:.1%})")

    def _cell(self, ctx, x, y, w, h, name, value, fill, title):
        theme = ctx.theme
        gap = 2.0
        ctx.scene.add(S.Rect(x + gap / 2, y + gap / 2, max(w - gap, 0), max(h - gap, 0), fill=fill,
                             rx=min(3.0, theme.bar_radius), title=title))
        size = theme.font_size
        if w < 34 or h < size + 8 or self.labels is False:
            return
        ink = readable_on(fill)
        ctx.scene.add(S.Text(x + 7, y + size + 5, truncate(name, w - 12, size, theme.font_kind, True), size, ink,
                             weight=600))
        if h > size * 2.8 and text_width(self._fmt(value), size, theme.font_kind) < w - 12:
            ctx.scene.add(S.Text(x + 7, y + size * 2.3 + 5, self._fmt(value), size - 0.5, ink))
