"""Histograms with automatic, round-numbered bins. O(n), chunked, any size."""

from __future__ import annotations

import math

import numpy as np

from .. import scene as S
from .._data import (as_float, columns_of, DataError, factorize, get_column, is_auto, is_frame, series_name,
                     to_array, value_kind)
from .._text import format_value
from ..raster import CHUNK
from ..reduce import sample_indices
from ..scales import nice_step
from ._base import Domain, DrawContext, Layer
from ._geom import rounded_bar

_AUTO = "auto"


def auto_edges(groups: list[np.ndarray], bins=_AUTO, rng=None) -> np.ndarray:
    """Round-numbered bin edges. Freedman–Diaconis on a sample, snapped to a 1-2-2.5-5 step."""
    if isinstance(bins, (list, tuple, np.ndarray)):
        return np.asarray(bins, dtype=float)
    lo, hi = np.inf, -np.inf
    for g in groups:
        if len(g):
            with np.errstate(invalid="ignore"):
                a, b = np.nanmin(g), np.nanmax(g)
            if np.isfinite(a):
                lo, hi = min(lo, a), max(hi, b)
    if rng is not None:
        lo, hi = float(rng[0]), float(rng[1])
    if not np.isfinite(lo):
        return np.array([0.0, 1.0])
    if lo == hi:
        return np.array([lo - 0.5, hi + 0.5])
    n = sum(len(g) for g in groups)
    sample = np.concatenate([g[sample_indices(len(g), max(1, 1_000_000 * len(g) // max(n, 1)))] for g in groups])
    sample = sample[np.isfinite(sample)]
    span = hi - lo
    # integer data over a short range: one bin per integer
    if is_auto(bins) and len(sample) and span <= 60 and np.all(sample == np.round(sample)):
        return np.arange(math.floor(lo) - 0.5, math.ceil(hi) + 1.0, 1.0)
    if isinstance(bins, int) and not isinstance(bins, bool):
        target = bins
    else:
        q75, q25 = np.percentile(sample, [75, 25]) if len(sample) else (hi, lo)
        iqr = q75 - q25
        if iqr > 0:
            width = 2 * iqr / max(n, 1) ** (1 / 3)
            target = span / width
        else:
            target = math.log2(max(n, 1)) + 1
        target = min(max(target, 6), 80)
    step = nice_step(span, target)
    e0 = math.floor(lo / step) * step
    e1 = math.ceil(hi / step) * step
    if e1 <= hi:
        e1 += step
    return e0 + step * np.arange(int(round((e1 - e0) / step)) + 1)


def count_bins(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    nb = len(edges) - 1
    out = np.zeros(nb, dtype=np.int64)
    widths = np.diff(edges)
    uniform = np.allclose(widths, widths[0])
    for s in range(0, len(values), CHUNK):
        v = np.asarray(values[s:s + CHUNK], dtype=np.float64)
        if uniform:
            idx = np.floor((v - edges[0]) / widths[0])
            ok = (idx >= 0) & (idx <= nb)
            idx = idx[ok].astype(np.int64)
            idx[idx == nb] = nb - 1   # right edge inclusive
            # values exactly on the top edge belong in the last bin only if <= edge
            out += np.bincount(idx, minlength=nb)[:nb]
        else:
            idx = np.searchsorted(edges, v, side="right") - 1
            idx[v == edges[-1]] = nb - 1
            ok = (idx >= 0) & (idx < nb)
            out += np.bincount(idx[ok], minlength=nb)
    return out


class HistogramLayer(Layer):
    def __init__(self, data=None, x=None, color=None, *, bins=_AUTO, range=None, stat="count",
                 cumulative=False, label=None):
        self.data, self.x, self.color = data, x, color
        self.bins, self.range, self.stat, self.cumulative, self.label = bins, range, stat, cumulative, label

    def prepare(self, chart) -> None:
        data, x = self.data, self.x
        groups: list[tuple[str, np.ndarray]] = []
        xl = None
        if is_frame(data) and not isinstance(data, dict):
            if x is None:
                x = next((c for c in columns_of(data) if value_kind(to_array(get_column(data, c))) == "num"), None)
                if x is None:
                    raise DataError("No numeric column found; pass x='column'.")
            vals = as_float(to_array(get_column(data, x)), "num")
            xl = str(x)
            if self.color is not None:
                codes, names = factorize(to_array(get_column(data, self.color)))
                order = np.argsort(codes, kind="stable")
                counts = np.bincount(codes[codes >= 0], minlength=len(names))
                start = int((codes < 0).sum())
                for i, nm in enumerate(names):
                    groups.append((nm, vals[order[start:start + counts[i]]]))
                    start += counts[i]
            else:
                groups.append((self.label or xl, vals))
        elif isinstance(data, dict):
            groups = [(str(k), as_float(to_array(v), "num")) for k, v in data.items()]
        else:
            src = data if data is not None else x
            if src is None:
                raise DataError("Nothing to plot: pass values, e.g. lv.histogram(values).")
            vals = as_float(to_array(src), "num")
            xl = series_name(src)
            if self.color is not None:
                codes, names = factorize(to_array(self.color))
                for i, nm in enumerate(names):
                    groups.append((nm, vals[codes == i]))
            else:
                groups.append((self.label or xl or "values", vals))
        self.groups = groups
        self.edges = auto_edges([g for _, g in groups], self.bins, self.range)
        self.counts = []
        for _, g in groups:
            c = count_bins(g, self.edges).astype(np.float64)
            total = np.count_nonzero(np.isfinite(g)) or 1
            if self.stat == "percent":
                c = c / total * 100
            elif self.stat == "density":
                c = c / (total * np.diff(self.edges))
            elif self.stat != "count":
                raise ValueError("stat must be 'count', 'percent' or 'density'.")
            if self.cumulative:
                c = np.cumsum(c)
            self.counts.append(c)
        self.x_label = xl
        self.y_label = {"count": "Count", "percent": "Percent", "density": "Density"}[self.stat]
        self.theme = chart.resolved_theme

    def keys(self):
        return [n for n, _ in self.groups]

    def x_domain(self):
        return Domain("num", float(self.edges[0]), float(self.edges[-1]), nice=False,
                      extent=(float(self.edges[0]), float(self.edges[-1])))

    def y_domain(self):
        hi = max((float(c.max()) for c in self.counts if len(c)), default=1.0)
        return Domain("num", 0.0, hi, zero=True, nice=True)

    def axis_labels(self):
        return self.x_label, self.y_label

    def values_for_reference(self, axis):
        return [g for _, g in self.groups] if axis == "x" else []

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        overlay = len(self.groups) > 1
        xe = ctx.xs(self.edges)
        base = ctx.ys.scalar(0.0)
        nb = len(self.edges) - 1
        gap = 1.0 if (xe[-1] - xe[0]) / max(nb, 1) > 4 else 0.0
        for gi, (name, _) in enumerate(self.groups):
            color = ctx.color(name, gi)
            counts = self.counts[gi]
            top = ctx.ys(counts)
            if overlay:
                # translucent fill + crisp step outline
                sx = np.repeat(xe, 2)[1:-1]
                sy = np.repeat(top, 2)
                ctx.scene.add(S.Polyline(np.concatenate(([sx[0]], sx, [sx[-1]])),
                                         np.concatenate(([base], sy, [base])), fill=color, fill_opacity=0.35,
                                         closed=True))
                ctx.scene.add(S.Polyline(sx, sy, stroke=color, stroke_width=1.6, join="miter", cap="butt"))
                continue
            fill = theme.muted if theme.bar_highlight == "hatch" else color
            r = min(theme.bar_radius, 3.0)
            for i in range(nb):
                if counts[i] <= 0:
                    continue
                x0, x1 = xe[i] + gap / 2, xe[i + 1] - gap / 2
                h = base - top[i]
                cmds = rounded_bar(x0, top[i], max(x1 - x0, 0.5), max(h, 0.5), r if x1 - x0 > 6 else 0, "top")
                title = f"{format_value(self.edges[i])} – {format_value(self.edges[i + 1])}: {format_value(counts[i])}" \
                    if nb <= 200 else None
                ctx.scene.add(S.Path(cmds, fill=fill, stroke=theme.ink if theme.bar_highlight == "hatch" else None,
                                     stroke_width=0.6, title=title))
