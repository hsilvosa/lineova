"""Sunburst: a hierarchy as concentric rings; angle is proportional to value."""

from __future__ import annotations

import math

from .. import scene as S
from .._color import mix, readable_on
from .._data import is_auto
from .._text import format_value, text_width, truncate
from ._base import DrawContext, Layer
from ._geom import wedge
from ._tree import build

_AUTO = "auto"


def _upright(deg: float) -> float:
    """Rotation that keeps text readable (never upside down)."""
    d = deg % 360
    return d - 180 if 90 < d < 270 else d


class SunburstLayer(Layer):
    cartesian = False
    own_legend = True

    def __init__(self, data=None, *, path=None, value=None, depth=None, labels=_AUTO, format=None, agg="sum",
                 center=_AUTO, start=90.0):
        self.data, self.path, self.value, self.max_depth = data, path, value, depth
        self.labels, self.fmt, self.agg, self.center, self.start = labels, format, agg, center, start

    def prepare(self, chart) -> None:
        self.root = build(self.data, self.path, self.value, self.agg)
        h = self.root.height()
        self.levels = min(h, int(self.max_depth)) if self.max_depth else h
        self.total = self.root.value

    def keys(self):
        return [c.name for c in self.root.children]

    def legend_items(self, ctx):
        return []

    def default_size(self, theme):
        return 560.0, 520.0

    def _fmt(self, v):
        if self.fmt is not None:
            return self.fmt(v) if callable(self.fmt) else (self.fmt.format(v) if "{" in self.fmt else format(v, self.fmt))
        return format_value(v)

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        plot = ctx.plot
        size = theme.font_size - 0.5
        R = max(30.0, min(plot.w, plot.h) / 2 - 4)
        cx, cy = plot.x + plot.w / 2, plot.y + plot.h / 2
        hole = R * (0.3 if self.levels <= 2 else 0.22)
        ring = (R - hole) / self.levels
        hl = ctx.highlight
        show = self.labels is not False
        folio = theme.name == "folio"
        tops = self.root.children

        def colour(node, i_top):
            if folio:
                base = mix(theme.ink, theme.background, 0.15 + 0.55 * i_top / max(len(tops) - 1, 1))
            else:
                base = ctx.color(node.top().name, i_top)
            if hl and node.top().name not in hl and not any(p in hl for p in node.path()):
                base = theme.muted
            if node.depth == 1:
                return base
            idx = node.parent.children.index(node)
            return mix(base, theme.background, min(0.7, 0.2 * (node.depth - 1) + 0.25 * idx / max(len(node.parent.children), 1)))

        def visit(node, a0, a1, i_top):
            if node.depth > self.levels:
                return
            r_in, r_out = hole + ring * (node.depth - 1), hole + ring * node.depth
            fill = colour(node, i_top)
            sweep = a1 - a0
            if sweep > 1e-4:
                ctx.scene.add(S.Path(wedge(cx, cy, r_out, r_in, a0, a1), fill=fill, stroke=theme.background,
                                     stroke_width=1.2 if sweep * r_out > 3 else 0, join="round",
                                     title=" › ".join(node.path()) + f": {self._fmt(node.value)} "
                                                                     f"({node.value / self.total:.1%})"))
                if show:
                    self._label(ctx, node, cx, cy, r_in, r_out, a0, a1, fill, size)
            a = a0
            for child in node.children:
                s = sweep * child.value / (node.value or 1)
                visit(child, a, a + s, i_top)
                a += s

        a = -math.radians(self.start)       # 90° -> 12 o'clock, clockwise
        for i, top in enumerate(tops):
            s = 2 * math.pi * top.value / self.total
            visit(top, a, a + s, i)
            a += s
        if self.center is not False and self.center is not None:
            text = self._fmt(self.total) if is_auto(self.center) else str(self.center)
            big = min(theme.title_size * 1.6, hole * 0.55)
            ctx.scene.add(S.Text(cx, cy + big * 0.1, text, big, theme.ink, anchor="middle", baseline="middle", weight=700))
            if is_auto(self.center):
                ctx.scene.add(S.Text(cx, cy + big * 0.1 + big * 0.8, "total", size, theme.ink_muted,
                                     anchor="middle", baseline="middle"))

    def _label(self, ctx, node, cx, cy, r_in, r_out, a0, a1, fill, size):
        theme = ctx.theme
        mid = (a0 + a1) / 2
        rm = (r_in + r_out) / 2
        thick = r_out - r_in
        arc_len = (a1 - a0) * rm
        name = node.name
        tw = text_width(name, size, theme.font_kind, node.depth == 1)
        x, y = cx + rm * math.cos(mid), cy + rm * math.sin(mid)
        ink = readable_on(fill)
        weight = 600 if node.depth == 1 else 400
        if arc_len >= tw + 10 and thick >= size + 4:
            # along the ring
            rot = _upright(math.degrees(mid) + 90)
            ctx.scene.add(S.Text(x, y, name, size, ink, anchor="middle", baseline="middle", rotate=rot, weight=weight))
        elif arc_len >= size + 3 and thick >= min(tw, 40) + 8:
            # across the ring (radial), shortened to fit
            rot = _upright(math.degrees(mid))
            txt = truncate(name, thick - 8, size, theme.font_kind)
            ctx.scene.add(S.Text(x, y, txt, size, ink, anchor="middle", baseline="middle", rotate=rot, weight=weight))
