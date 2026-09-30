"""Treemaps: nested rectangles with area proportional to value (squarified layout), any depth."""

from __future__ import annotations


from .. import scene as S
from .._color import mix, readable_on
from .._text import format_value, text_width, truncate
from ._base import DrawContext, Layer
from ._tree import build

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
    """Nested rectangles, area proportional to value. Any depth: nested dicts or ``path=[...]`` columns."""

    cartesian = False
    own_legend = False

    def __init__(self, data=None, *, path=None, value=None, labels=_AUTO, format=None, agg="sum", depth=None):
        self.data, self.path, self.value = data, path, value
        self.labels, self.fmt, self.agg, self.max_depth = labels, format, agg, depth

    def prepare(self, chart) -> None:
        self.root = build(self.data, self.path, self.value, self.agg)
        self.nested = self.root.height() > 1
        self.total = self.root.value
        # kept for backwards compatibility: (name, value, [(child, value)] | None) per top-level item
        self.items = [(c.name, c.value, [(k.name, k.value) for k in c.children] or None) for c in self.root.children]

    def keys(self):
        return [c.name for c in self.root.children] if self.nested else []

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
        kids = self.root.children
        rects = squarify([c.value for c in kids], plot.x, plot.y, plot.w, plot.h)
        n = len(kids)
        for i, (node, (x, y, w, h)) in enumerate(zip(kids, rects)):
            if self.nested:
                self._group(ctx, node, x, y, w, h, ctx.color(node.name, i))
            else:
                if theme.family == "folio":
                    fill = mix(theme.ink, theme.background, 0.25 + 0.6 * i / max(n - 1, 1))
                else:
                    on = ctx.highlight and node.name in ctx.highlight
                    fill = mix(theme.accent if on else theme.palette[0], theme.background,
                               0.0 if on else min(0.62, 0.62 * i / max(n - 1, 1)))
                    if ctx.highlight and not on:
                        fill = theme.muted
                self._cell(ctx, x, y, w, h, node.name, node.value, fill,
                           f"{node.name}: {self._fmt(node.value)} ({node.value / self.total:.1%})")

    def _group(self, ctx, node, x, y, w, h, base):
        """An internal node: tinted frame, a header with name and total, then its children."""
        theme = ctx.theme
        size = theme.font_size - (0 if node.depth == 1 else 1)
        gap = 2.0 if node.depth == 1 else 1.0
        limit = self.max_depth
        if node.is_leaf or (limit is not None and node.depth >= limit) or w < 12 or h < 12:
            idx = node.parent.children.index(node) if node.parent else 0
            shade = mix(base, theme.background, min(0.5, idx / max(len(node.parent.children), 1) * 0.6))
            self._cell(ctx, x, y, w, h, node.name, node.value, shade, " › ".join(node.path()) + f": {self._fmt(node.value)}")
            return
        tint = 0.82 if node.depth == 1 else max(0.35, 0.82 - 0.2 * (node.depth - 1))
        if ctx.highlight and node.top().name not in ctx.highlight:
            base = theme.muted
        ctx.scene.add(S.Rect(x + gap / 2, y + gap / 2, max(w - gap, 0), max(h - gap, 0),
                             fill=mix(base, theme.background, tint),
                             title=" › ".join(node.path()) + f": {self._fmt(node.value)}"))
        head = size + 8 if (h > size * 3 and w > 44) else 0
        if head:
            ink = theme.ink if tint > 0.5 else readable_on(mix(base, theme.background, tint))
            ctx.scene.add(S.Text(x + 6, y + size + 2 + gap, truncate(f"{node.name}  {self._fmt(node.value)}", w - 12, size,
                                                               theme.font_kind, True), size, ink,
                                 weight=700 if node.depth == 1 else 600))
        pad = 3.0 if node.depth == 1 else 2.0
        sub = squarify([c.value for c in node.children], x + pad, y + head + pad, w - 2 * pad, h - head - 2 * pad)
        for child, (sx, sy, sw, sh) in zip(node.children, sub):
            self._group(ctx, child, sx, sy, sw, sh, base)

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
