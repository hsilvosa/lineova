"""Heatmaps from matrices, DataFrames or long-format tables. Huge matrices are block-averaged."""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._color import ramp_lut, to_hex
from .._data import (Chunks, aggregate, as_float, DataError, factorize, get_column, is_auto, is_frame,
                     ordered_categories, to_array)
from .._text import decimals_for_step, text_width
from ..raster import block_reduce, colormap
from ..scales import nice_step
from ._base import Domain, DrawContext, Layer
from .bar import _looks_ordered

_AUTO = "auto"
MAX_LABELLED = 80


class HeatmapLayer(Layer):
    def __init__(self, data=None, x=None, y=None, value=None, *, cmap=_AUTO, vmin=None, vmax=None,
                 annotate=_AUTO, format=None, agg="mean", label=None):
        self.data, self.x, self.y, self.value = data, x, y, value
        self.cmap, self.vmin, self.vmax = cmap, vmin, vmax
        self.annotate, self.fmt, self.agg, self.label = annotate, format, agg, label

    def prepare(self, chart) -> None:
        data = self.data
        xl = yl = None
        if isinstance(data, Chunks):
            # streaming group-by over (y, x): counts, or agg of value per cell
            from .. import stream
            if not (isinstance(self.x, str) and isinstance(self.y, str)):
                raise DataError("Chunked heatmaps need x='column' and y='column' (and value='column' or counts).")
            agg = "count" if self.value is None else self.agg
            st = stream.group_stats(data, [self.y, self.x], self.value, need_minmax=agg in ("min", "max"))
            yn = list(dict.fromkeys(t[0] for t in st))
            xn = list(dict.fromkeys(t[1] for t in st))
            from .bar import natural_order
            xn, yn = natural_order(xn), natural_order(yn)
            mat = np.full((len(yn), len(xn)), np.nan)
            xi, yi = {n: i for i, n in enumerate(xn)}, {n: i for i, n in enumerate(yn)}
            for (a, b), v in st.items():
                mat[yi[a], xi[b]] = stream.finish(v, agg)
            xl, yl = str(self.x), str(self.y)
            self.label = self.label or (str(self.value) if self.value else "count")
        elif is_frame(data) and self.value is not None:
            xv = to_array(get_column(data, self.x))
            yv = to_array(get_column(data, self.y))
            vv = to_array(get_column(data, self.value))
            cx, xn = factorize(xv)
            cy, yn = factorize(yv)
            xn, cx = _sort_labels(xn, cx, ordered_categories(get_column(data, self.x)))
            yn, cy = _sort_labels(yn, cy, ordered_categories(get_column(data, self.y)))
            ok = (cx >= 0) & (cy >= 0)
            names, vals = aggregate(cy[ok] * len(xn) + cx[ok], vv[ok], self.agg)
            mat = np.full((len(yn), len(xn)), np.nan)
            keys = np.array([int(n) for n in names], dtype=np.int64)
            mat[keys // len(xn), keys % len(xn)] = vals
            xl, yl = str(self.x), str(self.y)
            self.label = self.label or str(self.value)
        elif isinstance(data, dict) and data and all(isinstance(v, dict) for v in data.values()):
            yn = [str(k) for k in data]
            xn = list(dict.fromkeys(str(c) for v in data.values() for c in v))
            mat = np.array([[float({str(a): b for a, b in row.items()}.get(c, np.nan)) for c in xn]
                            for row in data.values()])
        elif is_frame(data) and not isinstance(data, dict) and hasattr(data, "index"):
            mat = as_float(np.asarray(data.to_numpy(dtype=float, na_value=np.nan) if hasattr(data, "to_numpy")
                                      else data), "num").reshape(len(data.index), -1)
            xn = [str(c) for c in data.columns]
            yn = [str(i) for i in data.index]
        else:
            mat = np.asarray(data, dtype=np.float64)
            if mat.ndim != 2:
                raise DataError(f"A heatmap needs a 2-D matrix; got shape {mat.shape}.")
            xn = [str(v) for v in self.x] if self.x is not None else None
            yn = [str(v) for v in self.y] if self.y is not None else None
        self.matrix = mat
        self.rows, self.cols = mat.shape
        self.xn, self.yn = xn, yn
        self.x_label, self.y_label = xl, yl
        self.x_band = xn is not None and self.cols <= MAX_LABELLED
        self.y_band = yn is not None and self.rows <= MAX_LABELLED
        if not self.x_band and xn is None:
            self.xn = None
        with np.errstate(invalid="ignore"):
            lo = float(np.nanmin(mat)) if np.isfinite(mat).any() else 0.0
            hi = float(np.nanmax(mat)) if np.isfinite(mat).any() else 1.0
        theme = chart.resolved_theme
        diverging = self.cmap == "diverging" or (is_auto(self.cmap) and lo < 0 < hi and min(-lo, hi) / max(-lo, hi) > 0.2)
        if isinstance(self.cmap, (list, tuple)):
            self.stops = tuple(self.cmap)
        elif diverging:
            self.stops = tuple(theme.diverging)
            m = max(abs(lo), abs(hi))
            lo, hi = -m, m
        else:
            self.stops = tuple(theme.sequential)
        self.lo = self.vmin if self.vmin is not None else lo
        self.hi = self.vmax if self.vmax is not None else hi
        if not self.y_band and chart._y.reverse is False:
            chart._y.reverse = True      # row 0 at the top, like a matrix

    def x_domain(self):
        if self.x_band:
            return Domain("cat", categories=self.xn, gap=0.0)
        return Domain("num", 0.0, float(self.cols), nice=False)

    def y_domain(self):
        if self.y_band:
            return Domain("cat", categories=list(reversed(self.yn)), gap=0.0)
        return Domain("num", 0.0, float(self.rows), nice=False)

    def axis_labels(self):
        return self.x_label, self.y_label

    def colorbar(self):
        return (self.stops, self.lo, self.hi, self.label)

    def default_size(self, theme):
        cell = min(44.0, max(12.0, 600.0 / max(1, self.cols)))
        h = self.rows * cell + 150 if self.y_band else 520
        w = 720 if self.cols * cell > 400 else max(420.0, self.cols * cell + 220)
        return w, float(min(max(h, 280), 1400))

    def _fmt(self, v):
        if self.fmt is not None:
            return self.fmt(v) if callable(self.fmt) else (self.fmt.format(v) if "{" in self.fmt else format(v, self.fmt))
        d = decimals_for_step(nice_step((self.hi - self.lo) or 1.0, 25))
        return f"{v:,.{d}f}".replace("-", "\u2212")

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        plot = ctx.plot
        lut = ramp_lut(self.stops)
        cw = plot.w / self.cols
        ch = plot.h / self.rows
        if self.rows * self.cols <= 6000 and cw >= 2 and ch >= 2:
            gap = 1.0 if min(cw, ch) >= 8 else 0.0
            span = (self.hi - self.lo) or 1.0
            t = np.clip((self.matrix - self.lo) / span, 0, 1)
            size = theme.font_size - 0.5
            want_text = self.annotate is True or (is_auto(self.annotate) and self.rows * self.cols <= 400)
            for r in range(self.rows):
                for c in range(self.cols):
                    v = self.matrix[r, c]
                    x0 = plot.x + c * cw
                    y0 = plot.y + r * ch
                    if not np.isfinite(v):
                        ctx.scene.add(S.Rect(x0 + gap / 2, y0 + gap / 2, cw - gap, ch - gap, fill=None,
                                             stroke=theme.grid_color, stroke_width=0.8))
                        continue
                    rgb = lut[int(t[r, c] * 255 + 0.5)] / 255
                    fill = to_hex(rgb)
                    title = f"{self.yn[r] if self.yn else r} · {self.xn[c] if self.xn else c}: {self._fmt(v)}"
                    ctx.scene.add(S.Rect(x0 + gap / 2, y0 + gap / 2, cw - gap, ch - gap, fill=fill,
                                         rx=min(2.0, gap * 2), title=title))
                    if want_text:
                        txt = self._fmt(v)
                        if text_width(txt, size, theme.font_kind) + 4 < cw and ch > size + 2:
                            lum = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
                            ctx.scene.add(S.Text(x0 + cw / 2, y0 + ch / 2, txt, size,
                                                 "#111111" if lum > 0.55 else "#ffffff", anchor="middle",
                                                 baseline="middle"))
            return
        # large: reduce to at most the device pixel grid, then draw one image
        rs = ctx.raster_scale
        m = block_reduce(self.matrix, int(plot.h * rs), int(plot.w * rs))
        img = colormap(m, lut, self.lo, self.hi)
        ctx.scene.add(S.Image(plot.x, plot.y, plot.w, plot.h, img, smooth=m.shape[1] >= plot.w))


def _sort_labels(names, codes, hint):
    """Order long-format labels: explicit category order, natural order, or first appearance."""
    if hint:
        order = [h for h in hint if h in set(names)] + [n for n in names if n not in set(hint)]
    elif _looks_ordered(names):
        def key(s):
            try:
                return (0, float(s.replace(",", "")))
            except ValueError:
                return (1, s)
        order = sorted(names, key=key) if all(_isnum(n) for n in names) else names
    else:
        order = names
    pos = {n: i for i, n in enumerate(order)}
    remap = np.array([pos[n] for n in names], dtype=np.int64)
    new = np.where(codes >= 0, remap[np.maximum(codes, 0)], -1) if len(remap) else codes
    return order, new


def _isnum(s):
    try:
        float(s.replace(",", ""))
        return True
    except ValueError:
        return False
