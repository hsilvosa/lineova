"""2-D density plots: smoothed point density with contour lines.

Points are binned onto a grid (one O(n) pass, chunked) and smoothed with a
Gaussian via FFT, so the cost doesn't grow with the number of points beyond the
binning pass. Contours are traced with vectorised marching squares.
"""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._color import ramp_lut
from .._data import DataError, is_auto
from ..raster import bin_points
from ..reduce import sample_indices
from ._base import DrawContext, LegendItem
from .scatter import ScatterLayer

_AUTO = "auto"
GRID = 160


def smooth(counts: np.ndarray, sigma_x: float, sigma_y: float) -> np.ndarray:
    """Gaussian blur (sigmas in cells) via FFT with zero padding."""
    rows, cols = counts.shape
    pr, pc = int(np.ceil(4 * sigma_y)) + 1, int(np.ceil(4 * sigma_x)) + 1
    R, C = rows + 2 * pr, cols + 2 * pc
    fy = np.fft.fftfreq(R)[:, None]
    fx = np.fft.rfftfreq(C)[None, :]
    kernel = np.exp(-2 * np.pi ** 2 * ((fy * sigma_y) ** 2 + (fx * sigma_x) ** 2))
    padded = np.zeros((R, C))
    padded[pr:pr + rows, pc:pc + cols] = counts
    out = np.fft.irfft2(np.fft.rfft2(padded) * kernel, s=(R, C))
    return np.clip(out[pr:pr + rows, pc:pc + cols], 0, None)


def contour_segments(z: np.ndarray, level: float) -> tuple[np.ndarray, np.ndarray]:
    """Marching squares. Returns x, y (grid index units) as NaN-separated segments."""
    a = z[:-1, :-1]
    b = z[:-1, 1:]
    c = z[1:, 1:]
    d = z[1:, :-1]
    rows, cols = a.shape
    ii, jj = np.meshgrid(np.arange(rows, dtype=float), np.arange(cols, dtype=float), indexing="ij")

    def cross(p, q):
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (level - p) / (q - p)
        hit = (p > level) != (q > level)
        return np.where(hit, t, np.nan)

    # crossing points on the 4 edges of every cell: top (a-b), right (b-c), bottom (d-c), left (a-d)
    t_top, t_right, t_bot, t_left = cross(a, b), cross(b, c), cross(d, c), cross(a, d)
    pts = [
        (jj + t_top, ii),
        (jj + 1, ii + t_right),
        (jj + t_bot, ii + 1),
        (jj, ii + t_left),
    ]
    has = [~np.isnan(t) for t in (t_top, t_right, t_bot, t_left)]
    n_hit = sum(h.astype(int) for h in has)
    segs_x, segs_y = [], []
    # cells with exactly two crossings: join them
    two = n_hit == 2
    if two.any():
        idx = np.nonzero(two)
        firsts, seconds = [], []
        order = np.stack([h[idx] for h in has], axis=1)
        e1 = np.argmax(order, axis=1)
        order2 = order.copy()
        order2[np.arange(len(e1)), e1] = False
        e2 = np.argmax(order2, axis=1)
        px = np.stack([p[0][idx] for p in pts], axis=1)
        py = np.stack([p[1][idx] for p in pts], axis=1)
        r = np.arange(len(e1))
        firsts = (px[r, e1], py[r, e1])
        seconds = (px[r, e2], py[r, e2])
        nan = np.full(len(e1), np.nan)
        segs_x.append(np.column_stack((firsts[0], seconds[0], nan)).ravel())
        segs_y.append(np.column_stack((firsts[1], seconds[1], nan)).ravel())
    # saddle cells (4 crossings): decide by the cell-centre value
    four = n_hit == 4
    if four.any():
        idx = np.nonzero(four)
        centre = (a[idx] + b[idx] + c[idx] + d[idx]) / 4 > level
        a_hi = a[idx] > level
        P = [(p[0][idx], p[1][idx]) for p in pts]
        nan = np.full(len(centre), np.nan)
        # if centre matches corner a: connect top-right & bottom-left, else top-left & right-bottom
        same = centre == a_hi
        for (e1, e2), (f1, f2) in (((0, 1), (2, 3)), ((0, 3), (1, 2))):
            sel = same if (e1, e2) == (0, 1) else ~same
            for u, v in ((e1, e2), (f1, f2)):
                segs_x.append(np.column_stack((P[u][0][sel], P[v][0][sel], nan[sel])).ravel())
                segs_y.append(np.column_stack((P[u][1][sel], P[v][1][sel], nan[sel])).ravel())
    if not segs_x:
        return np.array([]), np.array([])
    return np.concatenate(segs_x), np.concatenate(segs_y)


def mass_levels(z: np.ndarray, fractions) -> list[float]:
    """Density thresholds enclosing the given fractions of the total mass (e.g. 50% / 90%)."""
    flat = np.sort(z.ravel())[::-1]
    cum = np.cumsum(flat)
    total = cum[-1] if len(cum) else 0
    if total <= 0:
        return []
    out = []
    for f in fractions:
        k = int(np.searchsorted(cum, f * total))
        out.append(float(flat[min(k, len(flat) - 1)]))
    return out


class DensityLayer(ScatterLayer):
    """Smoothed 2-D density. One group: shaded image + contours. Several groups: coloured contours."""

    def __init__(self, data=None, x=None, y=None, color=None, *, levels=_AUTO, fill=_AUTO, points=_AUTO,
                 bandwidth=None, grid=GRID):
        super().__init__(data, x, y, color if color is not None else None, render="vector")
        self.levels, self.fill, self.show_points = levels, fill, points
        self.bw, self.grid_n = bandwidth, grid

    def prepare(self, chart) -> None:
        super().prepare(chart)
        if self.x_kind != "num":
            raise DataError("Density plots need numeric x and y.")

    def _robust(self, axis):
        """Domain from the 0.5–99.5% quantiles: a few far outliers shouldn't shrink the density to a dot."""
        d = super().x_domain() if axis == "x" else super().y_domain()
        vals = [g.x if axis == "x" else g.y for g in self.groups]
        v = np.concatenate([np.asarray(a, float)[sample_indices(len(a), 200_000)] for a in vals if len(a)])
        v = v[np.isfinite(v)]
        if len(v) > 50:
            lo, hi = np.quantile(v, [0.005, 0.995])
            span = (hi - lo) or 1.0
            d.lo, d.hi = float(lo - span * 0.12), float(hi + span * 0.12)
            d.extent = (d.lo, d.hi)
        d.pad = 0.0
        return d

    def x_domain(self):
        return self._robust("x")

    def y_domain(self):
        return self._robust("y")

    def legend_items(self, ctx):
        if len(self.groups) < 2:
            return []
        return [LegendItem(g.name, g.name, ctx.color(g.name, i), "line") for i, g in enumerate(self.groups)]

    def _field(self, g, xlim, ylim, rows, cols):
        counts = bin_points(g.x, g.y, xlim, ylim, (rows, cols)).astype(float)
        # Scott's rule, per axis, measured in cells
        n = max(len(g.x), 2)
        s = sample_indices(len(g.x), 200_000)
        sx = np.nanstd(g.x[s]) or (xlim[1] - xlim[0]) / 20
        sy = np.nanstd(g.y[s]) or (ylim[1] - ylim[0]) / 20
        f = n ** (-1 / 6) * (self.bw if self.bw else 1.0)
        sig_x = sx * f / ((xlim[1] - xlim[0]) / cols)
        sig_y = sy * f / ((ylim[1] - ylim[0]) / rows)
        return smooth(counts, max(sig_x, 0.8), max(sig_y, 0.8))

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        xs, ys = ctx.xs, ctx.ys
        xlim = (min(xs.d0, xs.d1), max(xs.d0, xs.d1))
        ylim = (min(ys.d0, ys.d1), max(ys.d0, ys.d1))
        aspect = ctx.plot.h / max(ctx.plot.w, 1)
        cols = int(self.grid_n)
        rows = max(16, int(cols * aspect))
        single = len(self.groups) == 1
        fracs = (0.25, 0.5, 0.75, 0.9) if is_auto(self.levels) else tuple(self.levels)
        if (self.show_points is True) or (is_auto(self.show_points) and self.n <= 3000):
            for i, g in enumerate(self.groups):
                ctx.scene.add(S.Markers(xs(g.x), ys(g.y), "circle", 1.6, fill=ctx.color(g.name, i) if not single
                                        else theme.ink_muted, opacity=0.5))
        for i, g in enumerate(self.groups):
            z = self._field(g, xlim, ylim, rows, cols)
            color = ctx.color(g.name, i) if not single else (theme.accent if theme.family != "ledger" else theme.palette[0])
            if theme.family == "folio" and single:
                color = theme.ink
            want_fill = single if is_auto(self.fill) else bool(self.fill)
            if want_fill:
                lut = ramp_lut(tuple(theme.sequential))
                t = z / (z.max() or 1)
                img = np.empty(z.shape + (4,), np.uint8)
                img[..., :3] = lut[(t * 255).astype(int)]
                img[..., 3] = (np.clip(t * 1.6, 0, 1) * 235).astype(np.uint8)
                ctx.scene.add(S.Image(ctx.plot.x, ctx.plot.y, ctx.plot.w, ctx.plot.h, img))
            for j, level in enumerate(mass_levels(z, fracs)):
                cx, cy = contour_segments(z, level)
                if not len(cx):
                    continue
                # grid index -> pixels (row 0 of the grid is the top of the plot)
                px = ctx.plot.x + (cx + 0.5) / cols * ctx.plot.w
                py = ctx.plot.y + (cy + 0.5) / rows * ctx.plot.h
                dash = theme.dashes[i % len(theme.dashes)] if (theme.dashes and not single) else None
                ctx.scene.add(S.Polyline(px, py, stroke=color, stroke_width=1.0 + 0.4 * (len(fracs) - j) / len(fracs),
                                         opacity=0.95, join="round", cap="round", dash=dash))
