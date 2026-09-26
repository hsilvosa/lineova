"""Violin and ridgeline plots: smoothed distributions per group.

The density is a Gaussian KDE computed on a fine histogram (binned KDE): one
O(n) pass over the data, then a small convolution, so it works for any size.
"""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._color import mix
from .._text import format_value
from ..raster import CHUNK
from ..reduce import sample_indices
from ._base import Domain, DrawContext
from .box import BoxLayer

_AUTO = "auto"
GRID = 256


def bandwidth(v: np.ndarray) -> float:
    """Silverman's rule of thumb (robust to outliers via the IQR)."""
    n = len(v)
    if n < 2:
        return 1.0
    s = v[sample_indices(n, 200_000)]
    sd = float(np.std(s, ddof=1))
    q75, q25 = np.percentile(s, [75, 25])
    spread = min(sd, (q75 - q25) / 1.34) if q75 > q25 else sd
    if spread <= 0:
        spread = abs(float(np.mean(s))) * 0.05 or 1.0
    return 0.9 * spread * n ** -0.2


def kde(values: np.ndarray, lo: float, hi: float, bw: float | None = None, points: int = GRID):
    """Density of ``values`` on ``points`` evenly spaced positions between lo and hi (binned KDE)."""
    v = values[np.isfinite(values)]
    grid = np.linspace(lo, hi, points)
    if len(v) == 0:
        return grid, np.zeros(points)
    bw = bw or bandwidth(v)
    fine = points * 4
    span = hi - lo or 1.0
    counts = np.zeros(fine)
    for s in range(0, len(v), CHUNK):
        c = v[s:s + CHUNK]
        idx = np.clip(((c - lo) / span * (fine - 1) + 0.5).astype(np.int64), 0, fine - 1)
        counts += np.bincount(idx, minlength=fine)
    dx = span / (fine - 1)
    half = int(min(fine, np.ceil(4 * bw / dx)))
    k = np.exp(-0.5 * (np.arange(-half, half + 1) * dx / bw) ** 2)
    dens = np.convolve(counts, k, mode="same") if half > 0 else counts
    dens = dens / (dens.sum() * dx or 1.0)
    return grid, np.interp(grid, np.linspace(lo, hi, fine), dens)


class ViolinLayer(BoxLayer):
    """Mirrored density per group with a slim box (quartiles) and a median dot inside."""

    def __init__(self, data=None, x=None, y=None, *, orientation=_AUTO, inner=_AUTO, bw=None, scale="width",
                 color=None, label=None):
        super().__init__(data, x, y, orientation=orientation, points=False, color=color, label=label)
        self.inner, self.bw, self.scale = inner, bw, scale

    def prepare(self, chart) -> None:
        super().prepare(chart)
        self.dens = []
        for (_, v), st in zip(self.groups, self.stats):
            if st["n"] < 2 or st["min"] == st["max"]:
                self.dens.append(None)
                continue
            self.dens.append(kde(v, st["min"], st["max"], self.bw))

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        cat = ctx.ys if self.horizontal else ctx.xs
        val = ctx.xs if self.horizontal else ctx.ys
        half = min(cat.bandwidth, 90.0) / 2
        peak_all = max((d[1].max() for d in self.dens if d is not None), default=1.0)
        hl = ctx.highlight
        for i, (name, _) in enumerate(self.groups):
            d = self.dens[i]
            st = self.stats[i]
            if d is None:
                continue
            grid, dens = d
            if self.color_by == "group":
                color = ctx.color(name, i)
            elif hl:
                color = theme.accent if name in hl else theme.muted
            else:
                color = theme.palette[0] if theme.name != "folio" else theme.ink_secondary
            c = float(cat.center(cat.index[name]))
            peak = dens.max() if self.scale == "width" else peak_all
            w = dens / (peak or 1.0) * half
            pv = val(grid)
            if self.horizontal:
                xs = np.concatenate((pv, pv[::-1]))
                ys = np.concatenate((c - w, (c + w)[::-1]))
            else:
                xs = np.concatenate((c - w, (c + w)[::-1]))
                ys = np.concatenate((pv, pv[::-1]))
            fill = color if theme.name != "folio" else mix(theme.ink, theme.background, 0.82)
            ctx.scene.add(S.Polyline(xs, ys, fill=fill, fill_opacity=0.35 if theme.name != "folio" else 1.0,
                                     stroke=color if theme.name != "folio" else theme.ink, stroke_width=1.2,
                                     closed=True))
            if self.inner is False:
                continue
            q1, q3, med = val.scalar(st["q1"]), val.scalar(st["q3"]), val.scalar(st["med"])
            lo, hi = val.scalar(st["lo"]), val.scalar(st["hi"])
            ink = theme.ink if not theme.dark else theme.ink_secondary
            bw_ = max(3.0, min(8.0, half * 0.12))
            title = (f"{name}: median {format_value(st['med'])}, IQR {format_value(st['q1'])}–{format_value(st['q3'])}, "
                     f"n = {st['n']:,}")
            if self.horizontal:
                ctx.scene.add(S.Line(lo, c, hi, c, ink, 1.0))
                ctx.scene.add(S.Rect(min(q1, q3), c - bw_ / 2, abs(q3 - q1), bw_, fill=ink, title=title))
                mx, my = med, c
            else:
                ctx.scene.add(S.Line(c, lo, c, hi, ink, 1.0))
                ctx.scene.add(S.Rect(c - bw_ / 2, min(q1, q3), bw_, abs(q3 - q1), fill=ink, title=title))
                mx, my = c, med
            ctx.scene.add(S.Markers(np.array([mx]), np.array([my]), "circle", max(2.2, bw_ * 0.45),
                                    fill=theme.background, stroke=ink, stroke_width=1.0))


class RidgeLayer(BoxLayer):
    """One density curve per group, stacked vertically and slightly overlapping (joyplot)."""

    def __init__(self, data=None, x=None, y=None, *, overlap=1.6, bw=None, color=None, label=None):
        super().__init__(data, x, y, orientation="h", points=False, color=color, label=label)
        self.overlap, self.bw = overlap, bw

    def prepare(self, chart) -> None:
        super().prepare(chart)
        self.horizontal = True
        lo = min((s["min"] for s in self.stats if s["n"]), default=0.0)
        hi = max((s["max"] for s in self.stats if s["n"]), default=1.0)
        pad = (hi - lo) * 0.05
        self.data_lo, self.data_hi = lo, hi
        self.lo, self.hi = lo - pad, hi + pad
        bws = [bandwidth(v[np.isfinite(v)]) for _, v in self.groups if np.isfinite(v).sum() > 1]
        bw = self.bw or (float(np.median(bws)) if bws else None)
        self.dens = [kde(v, self.lo, self.hi, bw) if np.isfinite(v).sum() > 1 else None for _, v in self.groups]

    def _value_domain(self):
        return Domain("num", self.lo, self.hi, nice=False, extent=(self.data_lo, self.data_hi))

    def _cat_domain(self):
        # an empty row on top leaves room for the first curve to rise above its baseline
        return Domain("cat", categories=list(reversed(self.cats)) + [""], gap=0.0)

    def default_size(self, theme):
        return None, float(min(max(len(self.cats) * 42 + 140, 280), 1600))

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        cat, val = ctx.ys, ctx.xs
        peak = max((d[1].max() for d in self.dens if d is not None), default=1.0)
        step = abs(cat.step)
        height = step * self.overlap
        hl = ctx.highlight
        # back to front: top rows first so lower curves overlap the ones above
        for i, (name, _) in enumerate(self.groups):
            d = self.dens[i]
            if d is None:
                continue
            grid, dens = d
            base = float(cat.center(cat.index[name])) + step / 2 - 2      # bottom of the row
            if self.color_by == "group":
                color = ctx.color(name, i)
            elif hl:
                color = theme.accent if name in hl else theme.muted
            else:
                color = theme.palette[0] if theme.name != "folio" else theme.ink
            px = val(grid)
            py = base - dens / peak * height
            xs = np.concatenate(([px[0]], px, [px[-1]]))
            ys = np.concatenate(([base], py, [base]))
            fill = mix(color, theme.background, 0.55) if theme.name != "folio" else theme.background
            ctx.scene.add(S.Polyline(xs, ys, fill=fill, stroke=None, closed=True))
            ctx.scene.add(S.Polyline(px, py, stroke=color, stroke_width=1.4))
            ctx.scene.add(S.Line(px[0], base, px[-1], base, theme.axis_color, 0.8))
