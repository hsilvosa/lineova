"""Hexagonal binning: counts (or an aggregated value) per hexagon.

Binning is one vectorised pass over the points (chunked, and streamed for
``lv.Chunks``), so the cost is linear in the rows and the drawing cost depends
only on the number of hexagons. The lattice is laid out in data units but
shaped from the expected plot size, so hexagons come out regular on screen.
"""

from __future__ import annotations

import math

import numpy as np

from .. import scene as S
from .._color import ramp_lut, to_hex
from .._data import Chunks, DataError, as_float, get_column, is_auto, is_frame, to_array
from .._text import format_value
from ..raster import CHUNK
from ._base import Domain, DrawContext, Layer
from .scatter import ScatterLayer

_AUTO = "auto"
SQ3 = math.sqrt(3.0)
AGGS = ("count", "sum", "mean", "max", "min")


def hex_bin(x, y, x0, y0, dx, dy, weights=None, values=None, agg="count"):
    """Assign points to a pointy-top hex lattice.

    ``dx`` is the hexagon width (data units of x); ``dy`` the row spacing (data units of y).
    Returns ``(col, row, aggregate)`` for every non-empty hexagon. Each chunk is accumulated into
    a dense (rows x columns) grid with ``bincount``, so the cost is one linear pass and no sort.
    """
    n = len(x)
    if n == 0:
        return np.array([], np.int64), np.array([], np.int64), np.array([])
    # lattice extent from the data range (finite values only)
    fx = np.asarray(x, dtype=np.float64)
    fy = np.asarray(y, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        xmax, ymax = np.nanmax(fx), np.nanmax(fy)
    ncol = int(np.ceil((xmax - x0) / dx)) + 3
    nrow = int(np.ceil((ymax - y0) / dy)) + 3
    size = nrow * ncol
    cnt = np.zeros(size)
    tot = np.zeros(size) if values is not None and agg in ("sum", "mean") else None
    ext = None
    if values is not None and agg in ("max", "min"):
        ext = np.full(size, -np.inf if agg == "max" else np.inf)
    for s in range(0, n, CHUNK):
        xc = fx[s:s + CHUNK]
        yc = fy[s:s + CHUNK]
        ok = np.isfinite(xc) & np.isfinite(yc)
        # regular coordinates: hexagon width 1, rows sqrt(3)/2 apart
        X = (xc[ok] - x0) / dx
        Y = (yc[ok] - y0) / dy * (SQ3 / 2)
        # two offset rectangular lattices (even and odd rows); the nearer centre wins
        ia, ja = np.rint(X), np.rint(Y / SQ3)
        ib, jb = np.rint(X - 0.5), np.rint((Y - SQ3 / 2) / SQ3)
        use_a = (X - ia) ** 2 + (Y - ja * SQ3) ** 2 <= (X - ib - 0.5) ** 2 + (Y - jb * SQ3 - SQ3 / 2) ** 2
        col = np.where(use_a, ia, ib).astype(np.int64) + 1
        row = np.where(use_a, 2 * ja, 2 * jb + 1).astype(np.int64) + 1
        inside = (col >= 0) & (col < ncol) & (row >= 0) & (row < nrow)
        key = (row * ncol + col)[inside]
        w = np.asarray(weights[s:s + CHUNK], np.float64)[ok][inside] if weights is not None else None
        v = np.asarray(values[s:s + CHUNK], np.float64)[ok][inside] if values is not None else None
        if v is not None:
            good = np.isfinite(v)
            key_v, v = key[good], v[good]
            if tot is not None:
                tot += np.bincount(key_v, weights=v, minlength=size)
            if ext is not None:
                (np.maximum if agg == "max" else np.minimum).at(ext, key_v, v)
            cnt += np.bincount(key_v, minlength=size)
        else:
            cnt += np.bincount(key, weights=w, minlength=size)
    nz = np.flatnonzero(cnt)
    if agg == "count" or values is None:
        out = cnt[nz]
    elif agg == "sum":
        out = tot[nz]
    elif agg == "mean":
        out = tot[nz] / cnt[nz]
    else:
        out = ext[nz]
    row = nz // ncol - 1
    col = nz % ncol - 1
    return col.astype(np.int64), row.astype(np.int64), out


class HexbinLayer(Layer):
    """Hexagon density map for large point clouds, or an aggregated value per hexagon."""

    emphasize_zero = False

    def __init__(self, data=None, x=None, y=None, *, value=None, agg=_AUTO, gridsize=_AUTO, mincount=1,
                 log=_AUTO, cmap=_AUTO, label=None, border=_AUTO):
        self.data, self.x, self.y = data, x, y
        self.value, self.agg, self.gridsize, self.mincount = value, agg, gridsize, mincount
        self.log, self.cmap, self.label, self.border = log, cmap, label, border

    # ---------------------------------------------------------------- data
    def prepare(self, chart) -> None:
        theme = chart.resolved_theme
        agg = ("mean" if self.value is not None else "count") if is_auto(self.agg) else str(self.agg)
        if agg not in AGGS:
            raise DataError(f"hexbin agg must be one of {', '.join(AGGS)}; got {agg!r}.")
        if agg != "count" and self.value is None:
            raise DataError(f"agg={agg!r} needs value='column' to aggregate.")
        helper = ScatterLayer(self.data, self.x, self.y, None, render="vector")
        helper.prepare(chart)
        if helper.x_kind != "num":
            raise DataError("Hexbin needs numeric x and y.")
        xs = np.concatenate([g.x for g in helper.groups])
        ys = np.concatenate([g.y for g in helper.groups])
        weights = None
        if isinstance(self.data, Chunks):
            if self.value is not None:
                raise DataError("hexbin(value=...) isn't available for chunked data yet; counts are.")
            weights = np.concatenate([g.extra["_w"] for g in helper.groups])
        values = None
        if self.value is not None:
            if isinstance(self.value, str) and is_frame(self.data):
                values = as_float(to_array(get_column(self.data, self.value)), "num")
            else:
                values = as_float(to_array(self.value), "num")
            if len(values) != len(xs):
                raise DataError("value must have one entry per point.")
        # axis ranges focus the binning (points outside them would only make hexagons nobody sees)
        keep = np.ones(len(xs), bool)
        for arr, rng_ in ((xs, chart._x.range), (ys, chart._y.range)):
            if rng_ is not None:
                lo_r, hi_r = rng_
                if lo_r is not None:
                    keep &= arr >= float(lo_r)
                if hi_r is not None:
                    keep &= arr <= float(hi_r)
        if not keep.all():
            xs, ys = xs[keep], ys[keep]
            weights = weights[keep] if weights is not None else None
            values = values[keep] if values is not None else None
        self.n = helper.n
        self.x_label, self.y_label = helper.x_label, helper.y_label
        fin = np.isfinite(xs) & np.isfinite(ys)
        if not fin.any():
            raise DataError("No finite x/y points to bin.")
        self._xs, self._ys, self._w, self._v = xs, ys, weights, values
        self.agg_name = agg
        self._theme = theme
        self.data_ext = (float(np.min(xs[fin])), float(np.max(xs[fin])), float(np.min(ys[fin])), float(np.max(ys[fin])))
        # hexagon size at the expected plot size, for the axis extent; binning waits for draw(),
        # which knows the real plot size (or runs on demand for describe()/colorbar())
        W, H = chart._resolve_size(theme)
        self._est = (max(W - 2 * theme.padding - 60, 100), max(H - 150, 100),
                     self.data_ext[1] - self.data_ext[0], self.data_ext[3] - self.data_ext[2])
        dx, dy = self._geometry(*self._est)
        self.val = None
        x_lo, x_hi, y_lo, y_hi = self.data_ext
        self.ext = (x_lo - dx / 2, x_hi + dx / 2, y_lo - dy * 2 / 3, y_hi + dy * 2 / 3)

    def _geometry(self, pw, ph, x_span, y_span):
        g = int(self.gridsize) if not is_auto(self.gridsize) else int(np.clip(pw / 15, 12, 80))
        px_w = pw / g                                   # hexagon width on screen
        return px_w * (x_span or 1.0) / pw, (SQ3 / 2) * px_w * (y_span or 1.0) / ph

    def _ensure(self):
        if self.val is None:
            self._bin(*self._est)

    def _bin(self, pw: float, ph: float, x_span: float, y_span: float) -> None:
        """Bin for a plot ``pw`` x ``ph`` pixels showing ``x_span`` x ``y_span`` data units."""
        theme, agg = self._theme, self.agg_name
        xs, ys, weights, values = self._xs, self._ys, self._w, self._v
        x_lo, _, y_lo, _ = self.data_ext
        dx, dy = self._geometry(pw, ph, x_span, y_span)
        col, row, val = hex_bin(xs, ys, x_lo, y_lo, dx, dy, weights, values, agg)
        if agg == "count":
            keep = val >= self.mincount
        else:
            cnt = hex_bin(xs, ys, x_lo, y_lo, dx, dy, weights)[2]
            keep = (cnt >= self.mincount) & np.isfinite(val)
        self.col, self.row, self.val = col[keep], row[keep], val[keep]
        self.x0, self.y0, self.dx, self.dy = x_lo, y_lo, dx, dy
        v = self.val[np.isfinite(self.val)]
        self.vmin = float(v.min()) if len(v) else 0.0
        self.vmax = float(v.max()) if len(v) else 1.0
        positive = len(v) and self.vmin > 0
        self.use_log = bool(positive and self.vmax / max(np.median(v), 1e-12) > 30) if is_auto(self.log) \
            else bool(self.log and positive)
        if self.label:
            self.cbar_label = str(self.label)
        elif agg == "count":
            self.cbar_label = "count"
        else:
            self.cbar_label = f"{agg} of {self.value}" if isinstance(self.value, str) else agg
        lo, hi = self.vmin, self.vmax
        self.diverging = self.cmap == "diverging" or (
            is_auto(self.cmap) and agg != "count" and lo < 0 < hi and min(-lo, hi) / max(-lo, hi) > 0.2)
        if isinstance(self.cmap, (list, tuple)):
            self.stops = tuple(self.cmap)
        elif self.diverging:
            self.stops = tuple(theme.diverging)
            m = max(abs(lo), abs(hi))
            self.vmin, self.vmax, self.use_log = -m, m, False
        else:
            self.stops = tuple(theme.sequential)
        if self.use_log:
            self.cbar_label += " (log)"

    # ---------------------------------------------------------------- axes
    def x_domain(self):
        return Domain("num", self.ext[0], self.ext[1], nice=True, pad=0.01, extent=(self.ext[0], self.ext[1]))

    def y_domain(self):
        return Domain("num", self.ext[2], self.ext[3], nice=True, pad=0.01, extent=(self.ext[2], self.ext[3]))

    def axis_labels(self):
        return self.x_label, self.y_label

    def colorbar(self):
        self._ensure()
        return (self.stops, self.vmin, self.vmax, self.cbar_label)

    def has_colorbar(self) -> bool:
        return True

    def values_for_reference(self, axis):
        return []

    # ---------------------------------------------------------------- draw
    def _t(self, v):
        if self.use_log:
            lo, hi = math.log10(self.vmin), math.log10(self.vmax)
            return (np.log10(np.maximum(v, self.vmin)) - lo) / ((hi - lo) or 1.0)
        return (v - self.vmin) / ((self.vmax - self.vmin) or 1.0)

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        self._theme = theme
        # re-bin at the final pixel size so hexagons are regular whatever the panel shape
        self._bin(ctx.plot.w, ctx.plot.h, abs(ctx.xs.d1 - ctx.xs.d0), abs(ctx.ys.d1 - ctx.ys.d0))
        if not len(self.val):
            return
        lut = ramp_lut(self.stops)
        t = np.clip(self._t(self.val), 0, 1)
        # a floor so the faintest hexagons stay visible on the background
        idx = (t if self.diverging else 0.12 + 0.88 * t) * (len(lut) - 1)
        cols = lut[np.nan_to_num(idx).astype(int)]
        # centres in data units, then pixels
        cx = self.x0 + (self.col + 0.5 * (self.row & 1)) * self.dx
        cy = self.y0 + self.row * self.dy
        px, py = ctx.xs(cx), ctx.ys(cy)
        # corner offsets in pixels: pointy-top hexagon of width dx, circumradius = dy * 2/3 in y
        hw = abs(ctx.xs.scalar(self.x0 + self.dx / 2) - ctx.xs.scalar(self.x0))
        hr = abs(ctx.ys.scalar(self.y0 + self.dy * 2 / 3) - ctx.ys.scalar(self.y0))
        offs = [(0, -hr), (hw, -hr / 2), (hw, hr / 2), (0, hr), (-hw, hr / 2), (-hw, -hr / 2)]
        border = (len(self.val) < 2500) if is_auto(self.border) else bool(self.border)
        titles = len(self.val) <= 4000
        label = "count" if self.agg_name == "count" else self.agg_name
        for i in range(len(self.val)):
            x, y = float(px[i]), float(py[i])
            cmds = [("M", x + offs[0][0], y + offs[0][1])] + [("L", x + a, y + b) for a, b in offs[1:]] + [("Z",)]
            ctx.scene.add(S.Path(cmds, fill=to_hex(cols[i] / 255.0), stroke=theme.background if border else None,
                                 stroke_width=0.6, join="miter",
                                 title=f"{label}: {format_value(self.val[i])}" if titles else None))
