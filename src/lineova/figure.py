"""Multi-panel figures: ``lv.grid([...])`` and small multiples (``facet=``)."""

from __future__ import annotations

import copy
import math
import string
from typing import Any, Optional
from collections.abc import Sequence

from . import scene as S
from . import themes
from ._data import DataError, factorize, get_column, ordered_categories, subset, to_array
from ._output import Renderable
from .marks._base import DrawContext, Plot

_AUTO = "auto"


def _auto_cols(n: int) -> int:
    if n <= 3:
        return n
    if n == 4:
        return 2
    if n <= 9:
        return 3
    return 4


class Grid(Renderable):
    """Several charts laid out in rows and columns, with one title, one legend and aligned sizes.

    ``share="both" | "x" | "y" | "none"`` makes panels use the same axis ranges, so they can be compared.
    """

    def __init__(self, charts: Sequence, cols: Any = _AUTO, *, title: Optional[str] = None,
                 subtitle: Optional[str] = None, caption: Optional[str] = None, source: Optional[str] = None,
                 number: Optional[int] = None, theme: Any = None, width: Any = _AUTO, height: Any = _AUTO,
                 gap: float = 12.0, legend: Any = _AUTO, share: str = "none", labels: Any = _AUTO):
        if not charts:
            raise ValueError("grid() needs at least one chart.")
        self.charts = list(charts)
        self.cols = cols
        self.opts = dict(title=title, subtitle=subtitle, caption=caption, source=source, number=number)
        self.theme_opt, self.width, self.height, self.gap = theme, width, height, gap
        self.legend, self.share, self.labels = legend, share, labels
        self._page_title = title

    def _theme(self):
        if self.theme_opt is not None:
            return themes.get(self.theme_opt)
        return self.charts[0].resolved_theme

    def build(self, raster_scale: float = 2.0) -> S.Scene:
        from .chart import Chart
        theme = self._theme()
        n = len(self.charts)
        ncol = _auto_cols(n) if self.cols == _AUTO else max(1, int(self.cols))
        nrow = math.ceil(n / ncol)
        pad = theme.padding
        W = float(self.width) if self.width != _AUTO else float(min(1320, max(640, 380 * ncol + 2 * pad)))
        cell_w = (W - 2 * pad - self.gap * (ncol - 1)) / ncol + 2 * pad   # children keep their own padding
        cell_w_inner = cell_w - 2 * pad

        # children: same theme, prepared once so we can share colours, legends and axes
        kids = []
        for i, ch in enumerate(self.charts):
            k = copy.copy(ch)
            k._opts = dict(ch._opts)
            k._layers = [copy.copy(l) for l in ch._layers]
            k._annotations = list(ch._annotations)
            k._x, k._y = copy.copy(ch._x), copy.copy(ch._y)
            if ch._opts["theme"] is None or self.theme_opt is not None:
                k._opts["theme"] = theme
            k._opts["width"] = cell_w_inner + 2 * pad
            if self.height != _AUTO:
                k._opts["height"] = float(self.height)
            if self.labels is not False and k._opts.get("title") is not None:
                k._opts["panel"] = string.ascii_lowercase[i % 26]
            if not k._layers and k.data is not None:
                k.line()
            for layer in k._layers:
                layer.prepare(k)
            kids.append(k)
        # shared colours: every series keeps one colour across panels
        keys = list(dict.fromkeys(key for k in kids for l in k._layers for key in l.keys()))
        own = all(getattr(l, "own_legend", False) for k in kids for l in k._layers)
        # panels showing the same series (e.g. facets) share colours and one legend
        key_sets = [frozenset(key for l in k._layers for key in l.keys()) for k in kids]
        same_series = len(set(key_sets)) == 1 or (self.share != "none" and all(ks <= set(keys) for ks in key_sets)
                                                   and len({type(l) for k in kids for l in k._layers}) == 1)
        shared_legend = (same_series and self.legend is not False and self.legend != "none" and len(keys) > 1
                         and not own and all(k._opts["legend"] in (_AUTO, "none") for k in kids))
        if keys and same_series:
            colors, _ = kids[0]._assign_colors(theme, keys)
            for k in kids:
                if kids[0]._opts["palette"] in (_AUTO, None) or isinstance(kids[0]._opts["palette"], (list, tuple)):
                    k._opts["palette"] = colors
                if shared_legend:
                    k._opts["legend"] = "none"
        # shared axes
        share = self.share
        if share in ("both", "x", "y", True):
            for which in ("x", "y"):
                if share not in ("both", True, which):
                    continue
                doms = [k._domain(which) for k in kids if all(l.cartesian for l in k._layers)]
                if not doms:
                    continue
                merged = doms[0]
                for d in doms[1:]:
                    merged = merged.merge(d)
                for k in kids:
                    k._forced = dict(getattr(k, "_forced", {}) or {}, **{which: merged})
        # shared axes only need one title: bottom row for x, first column for y
        for i, k in enumerate(kids):
            r, c = divmod(i, ncol)
            last_row = r == nrow - 1 or i + ncol >= n
            if share in ("both", "x", True) and not last_row and k._x.label == _AUTO:
                k._x.label = None
            if share in ("both", "y", True) and c > 0 and k._y.label == _AUTO:
                k._y.label = None
        # sizes: each row as tall as its tallest panel
        sizes = [k._resolve_size(k.resolved_theme) for k in kids]
        row_h = [max(sizes[r * ncol + c][1] for c in range(ncol) if r * ncol + c < n) for r in range(nrow)]
        if self.height == _AUTO:
            for i, k in enumerate(kids):
                k._opts["height"] = row_h[i // ncol]

        # header, legend, footer via a helper chart that owns only the figure-level text
        helper = Chart(theme=theme, **{k: v for k, v in self.opts.items() if v is not None})
        H_body = sum(row_h) + self.gap * (nrow - 1)
        probe = S.Scene(W, 10_000, theme.background, theme.font, theme.font_kind)
        top = helper._draw_header(probe, theme, W, pad)
        items = []
        if shared_legend:
            dummy = DrawContext(probe, theme, Plot(0, 0, 1, 1), None, None, kids[0]._opts["palette"], set())
            seen = set()
            for k in kids:
                for layer in k._layers:
                    for it in layer.legend_items(dummy):
                        if it.key not in seen:
                            seen.add(it.key)
                            items.append(it)
            top = helper._draw_legend_row(probe, theme, items, pad, top, W - 2 * pad) if items else top
        foot_probe = S.Scene(W, 10_000, theme.background, theme.font, theme.font_kind)
        foot_h = 10_000 - helper._draw_footer(foot_probe, theme, W, 10_000)
        H = top - pad * 0.5 + H_body + (foot_h if foot_h > 0 else pad)
        scene = S.Scene(W, H, theme.background, theme.font, theme.font_kind, description=self.opts["title"] or "")
        scene.ops.extend(probe.ops)
        if foot_h > 0:
            helper._draw_footer(scene, theme, W, H - pad)
        y = top - pad * 0.5
        for r in range(nrow):
            for c in range(ncol):
                i = r * ncol + c
                if i >= n:
                    break
                sub = kids[i]._build_prepared(raster_scale)
                dx = c * (cell_w_inner + self.gap)
                scene.add(S.Group(dx, y, sub.ops))
            y += row_h[r] + self.gap
        return scene

    def __repr__(self) -> str:
        return f"<lineova.Grid {len(self.charts)} panels>"


def grid(charts: Sequence, cols: Any = _AUTO, **options) -> Grid:
    """Arrange charts in a grid: ``lv.grid([c1, c2, c3], cols=3, title="...")``."""
    return Grid(charts, cols, **options)


def facet_grid(chart) -> Grid:
    """Split ``chart`` into one panel per value of its ``facet`` column."""
    col = chart._opts["facet"]
    data = chart.data
    if data is None:
        raise DataError("facet= needs the chart's data to be a DataFrame or dict of columns.")
    values = to_array(get_column(data, col)) if isinstance(col, str) else to_array(col)
    codes, names = factorize(values)
    hint = ordered_categories(get_column(data, col)) if isinstance(col, str) else None
    if hint:
        names = [h for h in hint if h in set(names)]
        lookup = {v: i for i, v in enumerate(factorize(values)[1])}
        order = [lookup[nm] for nm in names]
    else:
        order = list(range(len(names)))
    if len(names) > 36:
        raise DataError(f"{len(names)} facets is too many to read; filter the data or pick a coarser column.")
    panels = []
    for j in order:
        mask = codes == j
        sub = subset(data, mask)
        k = copy.copy(chart)
        k._opts = dict(chart._opts, facet=None, title=str(factorize(values)[1][j]), subtitle=None, caption=None,
                       source=None, number=None, width="auto", height="auto", size=None)
        k.data = sub
        k._layers = []
        for l in chart._layers:
            l2 = copy.copy(l)
            if l.data is data:
                l2.data = sub
            k._layers.append(l2)
        k._annotations = list(chart._annotations)
        k._x, k._y = copy.copy(chart._x), copy.copy(chart._y)
        panels.append(k)
    from .chart import SIZES
    width = chart._opts["width"] if chart._opts["width"] != _AUTO else _AUTO
    if chart._opts.get("size") in SIZES:
        width = SIZES[chart._opts["size"]][0]
    share = chart._opts.get("share", "both")
    return Grid(panels, chart._opts.get("facet_cols", _AUTO), title=chart._opts["title"],
                subtitle=chart._opts["subtitle"], caption=chart._opts["caption"], source=chart._opts["source"],
                number=chart._opts["number"], theme=chart._opts["theme"], width=width, share=share,
                legend=chart._opts["legend"] if chart._opts["legend"] in (False, "none") else _AUTO)
