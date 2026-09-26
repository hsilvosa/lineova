"""Scatter / bubble plots, with automatic density rendering for big data."""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._color import rgb_array, ramp_lut
from .._data import (Chunks, as_float, interval_bounds, interval_spec, columns_of, DataError, factorize, get_column, guess_group, is_auto, is_frame,
                     resolve_xy, to_array, value_kind)
from .._text import format_value
from ..raster import CHUNK, bin_points, shade
from ._base import Domain, DrawContext, Layer, LegendItem
from .line import _nanrange

_AUTO = "auto"
DENSITY_THRESHOLD = 50_000


class _Group:
    __slots__ = ("name", "x", "y", "size", "value", "extra")

    def __init__(self, name, x, y, size=None, value=None, extra=None):
        self.name, self.x, self.y, self.size, self.value = name, x, y, size, value
        self.extra = extra or {}


def _column_or_array(data, spec):
    if spec is None:
        return None
    if isinstance(spec, str) and is_frame(data):
        return to_array(get_column(data, spec))
    return to_array(spec)


class ScatterLayer(Layer):
    legend_shape = "circle"

    def __init__(self, data=None, x=None, y=None, color=_AUTO, *, size=None, label=None, fit=False,
                 render=_AUTO, opacity=_AUTO, marker=_AUTO, tooltips=_AUTO, shade=_AUTO, sizes=(2.5, 16.0),
                 error=None, x_error=None):
        self.data, self.x, self.y, self.color = data, x, y, color
        self.error, self.x_error = error, x_error
        self.size, self.label, self.fit, self.render = size, label, fit, render
        self.opacity, self.marker, self.tooltips = opacity, marker, tooltips
        self.shade_how = "eq_hist" if is_auto(shade) else shade
        self.size_range = sizes

    # ---------------------------------------------------------------- data
    def _prepare_chunked(self, chart) -> None:
        from .. import stream
        cx, cy, w, n, _ = stream.points(self.data, self.x, self.y)
        name = self.label or (str(self.y) if isinstance(self.y, str) else "points")
        self.groups = [_Group(name, cx, cy, extra={"_w": w})]
        self.n = n
        self.x_kind = "num"
        self.x_label = str(self.x) if isinstance(self.x, str) else None
        self.y_label = str(self.y) if isinstance(self.y, str) else None
        self.continuous = None
        self.size_lim = None
        self.density = True
        self.fit_result = None

    def prepare(self, chart) -> None:
        self.theme = chart.resolved_theme
        if isinstance(self.data, Chunks):
            return self._prepare_chunked(chart)
        data, color = self.data, self.color
        if is_auto(color):
            color = guess_group(data, columns_of(data), {v for v in (self.x, self.y, self.size) if isinstance(v, str)}) if (
                is_frame(data) and isinstance(self.y, str)) else None
        cvals = _column_or_array(data, color) if color is not None and not (
            isinstance(color, str) and color.startswith("#")) else None
        extra = {**interval_spec(self.error), **interval_spec(self.x_error, "x")}
        xy = resolve_xy(data, self.x, self.y, None, extra=extra)
        if xy.x_kind == "cat":
            raise DataError("Scatter plots need numeric or date x values. For categories use bar() or box().")
        self.x_kind = xy.x_kind
        self.x_label, self.y_label = xy.x_label, xy.y_label
        size = _column_or_array(data, self.size)
        groups: list[_Group] = []
        self.continuous = None
        if len(xy.series) == 1:
            s = xy.series[0]
            if size is not None:
                size = as_float(size, "num")
            if cvals is not None and value_kind(cvals) == "num":
                v = as_float(cvals, "num")
                self.continuous = (float(np.nanmin(v)), float(np.nanmax(v)), str(color) if isinstance(color, str) else "")
                groups.append(_Group(self.label or s.name, s.x, s.y, size, v, s.extra))
            elif cvals is not None:
                codes, names = factorize(cvals)
                order = np.argsort(codes, kind="stable")
                counts = np.bincount(codes[codes >= 0], minlength=len(names))
                start = int((codes < 0).sum())
                for i, nm in enumerate(names):
                    sel = order[start:start + counts[i]]
                    start += counts[i]
                    groups.append(_Group(nm, s.x[sel], s.y[sel], None if size is None else size[sel],
                                         extra={k: v[sel] for k, v in s.extra.items()}))
                self.group_label = str(color) if isinstance(color, str) else None
            else:
                groups.append(_Group(self.label or s.name, s.x, s.y, size, extra=s.extra))
        else:
            groups = [_Group(s.name, s.x, s.y, extra=s.extra) for s in xy.series]
        for g in groups:
            yb = interval_bounds(g.y, g.extra)
            xb = interval_bounds(g.x, g.extra, "x")
            if yb is not None:
                g.extra["_lo"], g.extra["_hi"] = yb
            if xb is not None:
                g.extra["_xlo"], g.extra["_xhi"] = xb
        self.groups = groups
        self.n = sum(len(g.x) for g in groups)
        if size is not None:
            self.size_lim = _nanrange([g.size for g in groups if g.size is not None])
        else:
            self.size_lim = None
        self.density = self.render == "density" or (is_auto(self.render) and self.n > DENSITY_THRESHOLD)
        self.fit_result = _fit(groups) if self.fit else None

    def keys(self):
        if self.continuous:
            return []
        return [g.name for g in self.groups]

    def x_domain(self):
        lo, hi = _nanrange([g.x for g in self.groups] + [g.extra[k] for g in self.groups for k in ("_xlo", "_xhi")
                                                            if k in g.extra])
        return Domain(self.x_kind, lo, hi, nice=self.x_kind != "time", pad=self._pad(), extent=(lo, hi))

    def y_domain(self):
        lo, hi = _nanrange([g.y for g in self.groups] + [g.extra[k] for g in self.groups for k in ("_lo", "_hi")
                                                            if k in g.extra])
        return Domain("num", lo, hi, nice=True, pad=self._pad(), extent=(lo, hi))

    def _pad(self) -> float:
        # leave room for marker radius so edge points aren't cut in half
        big = self.size_lim is not None or self.theme.scatter_style == "bubble"
        return 0.09 if big else 0.03

    def axis_labels(self):
        return self.x_label, self.y_label

    def values_for_reference(self, axis):
        return [g.y if axis == "y" else g.x for g in self.groups]

    def colorbar(self):
        if self.continuous:
            lo, hi, label = self.continuous
            return (self.theme.sequential, lo, hi, label)
        return None

    # ---------------------------------------------------------------- drawing
    def _radius(self, g, theme):
        if g.size is None or self.size_lim is None:
            return theme.marker_size if theme.scatter_style != "bubble" else theme.marker_size + 0.5
        lo, hi = self.size_lim
        rmin, rmax = self.size_range
        t = (g.size - lo) / ((hi - lo) or 1.0)
        return rmin + (rmax - rmin) * np.sqrt(np.clip(np.nan_to_num(t), 0, 1))

    def draw(self, ctx: DrawContext) -> None:
        if self.density:
            self._draw_density(ctx)
        else:
            self._draw_vector(ctx)
        if self.fit_result:
            self._draw_fit(ctx)

    def _draw_errors(self, ctx, g, color):
        """Error bars as one path per group (NaN-separated segments)."""
        ok = np.isfinite(g.x) & np.isfinite(g.y)
        n = int(ok.sum())
        caps = n <= 200
        for lo_k, hi_k, vertical in (("_lo", "_hi", True), ("_xlo", "_xhi", False)):
            if lo_k not in g.extra:
                continue
            lo, hi = g.extra[lo_k][ok], g.extra[hi_k][ok]
            px, py = ctx.xs(g.x[ok]), ctx.ys(g.y[ok])
            if vertical:
                a, b = ctx.ys(lo), ctx.ys(hi)
                xs = np.column_stack((px, px, np.full(n, np.nan))).ravel()
                ys = np.column_stack((a, b, np.full(n, np.nan))).ravel()
                if caps:
                    c = 3.0
                    xs = np.concatenate((xs, np.column_stack((px - c, px + c, np.full(n, np.nan), px - c, px + c,
                                                              np.full(n, np.nan))).ravel()))
                    ys = np.concatenate((ys, np.column_stack((a, a, np.full(n, np.nan), b, b, np.full(n, np.nan))).ravel()))
            else:
                a, b = ctx.xs(lo), ctx.xs(hi)
                ys = np.column_stack((py, py, np.full(n, np.nan))).ravel()
                xs = np.column_stack((a, b, np.full(n, np.nan))).ravel()
                if caps:
                    c = 3.0
                    ys = np.concatenate((ys, np.column_stack((py - c, py + c, np.full(n, np.nan), py - c, py + c,
                                                              np.full(n, np.nan))).ravel()))
                    xs = np.concatenate((xs, np.column_stack((a, a, np.full(n, np.nan), b, b, np.full(n, np.nan))).ravel()))
            ctx.scene.add(S.Polyline(xs, ys, stroke=color, stroke_width=1.0, opacity=0.75, cap="butt"))

    def _draw_vector(self, ctx):
        theme = ctx.theme
        style = theme.scatter_style if is_auto(self.marker) else self.marker
        n = self.n
        auto_op = 1.0 if n < 300 else (0.8 if n < 3000 else 0.55)
        op = auto_op if is_auto(self.opacity) else float(self.opacity)
        want_tips = self.tooltips is True or (is_auto(self.tooltips) and n <= 1500)
        order = sorted(range(len(self.groups)),
                       key=lambda i: 0 if ctx.color(self.groups[i].name, i) == theme.muted else 1)
        lut = ramp_lut(tuple(theme.sequential)) if self.continuous else None
        for i in order:
            g = self.groups[i]
            color = ctx.color(g.name, i) if not self.continuous else theme.accent
            if g.extra:
                self._draw_errors(ctx, g, color if theme.name != "folio" else theme.ink_secondary)
            ok = np.isfinite(g.x) & np.isfinite(g.y)
            px, py = ctx.xs(g.x[ok]), ctx.ys(g.y[ok])
            r = self._radius(g, theme)
            if np.ndim(r):
                r = r[ok]
                idx = np.argsort(-r, kind="stable")      # big bubbles underneath
                px, py, r = px[idx], py[idx], r[idx]
            else:
                idx = None
            fills = color
            if self.continuous:
                lo, hi, _ = self.continuous
                v = g.value[ok] if idx is None else g.value[ok][idx]
                t = np.clip((v - lo) / ((hi - lo) or 1), 0, 1)
                rgb = lut[np.nan_to_num(t * 255).astype(int)]
                fills = [f"#{a:02x}{b:02x}{c:02x}" for a, b, c in rgb]
            titles = None
            if want_tips:
                xv, yv = g.x[ok], g.y[ok]
                if idx is not None:
                    xv, yv = xv[idx], yv[idx]
                xl, yl = self.x_label or "x", self.y_label or "y"
                pre = f"{g.name} · " if len(self.groups) > 1 else ""
                titles = [f"{pre}{xl}: {_fmt_x(a, self.x_kind)} · {yl}: {format_value(b)}" for a, b in zip(xv, yv)]
            sized = np.ndim(r) > 0
            if style == "hollow":
                op_ = S.Markers(px, py, "circle", r, fill=theme.background, stroke=fills if self.continuous else color,
                                stroke_width=1.0, opacity=op, titles=titles)
            elif style == "cross":
                op_ = S.Markers(px, py, "cross", r, fill=None, stroke=fills if self.continuous else color,
                                stroke_width=1.4, opacity=op, titles=titles)
            elif style == "bubble" or sized:
                op_ = S.Markers(px, py, "circle", r, fill=fills, stroke=fills if self.continuous else color,
                                stroke_width=1.2, fill_opacity=0.3 if style == "bubble" else 0.6, opacity=op,
                                titles=titles)
            else:
                op_ = S.Markers(px, py, "circle", r, fill=fills, stroke=theme.background, stroke_width=1.2,
                                opacity=op, titles=titles)
            ctx.scene.add(op_)
            if theme.extra.get("rug", theme.name == "instrument") and n <= 5000:
                self._rug(ctx, px, py, color)

    def _rug(self, ctx, px, py, color):
        """Short ticks along both axes showing where the points fall."""
        plot = ctx.plot
        b, l_ = plot.bottom, plot.x
        xs = np.repeat(px, 3)
        ys = np.tile([b, b - 6, np.nan], len(px))
        ctx.overlay.append(S.Polyline(xs, ys, stroke=color, stroke_width=1.0, opacity=0.7, cap="butt"))
        ys2 = np.repeat(py, 3)
        xs2 = np.tile([l_, l_ + 6, np.nan], len(py))
        ctx.overlay.append(S.Polyline(xs2, ys2, stroke=color, stroke_width=1.0, opacity=0.7, cap="butt"))

    def _draw_density(self, ctx):
        theme = ctx.theme
        xs, ys = ctx.xs, ctx.ys
        rs = ctx.raster_scale
        rows, cols = max(1, int(round(ctx.plot.h * rs))), max(1, int(round(ctx.plot.w * rs)))
        xlim = (min(xs.d0, xs.d1), max(xs.d0, xs.d1))
        ylim = (min(ys.d0, ys.d1), max(ys.d0, ys.d1))
        xt = xs.transform if xs.kind == "log" else None
        yt = ys.transform if ys.kind == "log" else None
        grids = [bin_points(g.x, g.y, xlim, ylim, (rows, cols), x_transform=xt, y_transform=yt,
                            weights=g.extra.get("_w")) for g in self.groups]
        colors = rgb_array([ctx.color(g.name, i) for i, g in enumerate(self.groups)])
        if len(grids) == 1:
            img = shade(grids[0], colors[0], self.shade_how)
        else:
            img = shade(np.stack(grids), colors, self.shade_how)
        if ys.r0 < ys.r1:                 # reversed y axis
            img = img[::-1]
        if xs.r0 > xs.r1:
            img = img[:, ::-1]
        ctx.scene.add(S.Image(ctx.plot.x, ctx.plot.y, ctx.plot.w, ctx.plot.h, img))
        ctx.notes.append(f"{self.n:,} points · density")

    def _draw_fit(self, ctx):
        theme = ctx.theme
        a, b, r2, ci, lo, hi = self.fit_result
        grid = np.linspace(lo, hi, 64)
        yhat = a + b * grid
        band = ci(grid)
        px = ctx.xs(grid)
        color = theme.accent if theme.accent != theme.palette[0] else theme.ink_secondary
        xs = np.concatenate((px, px[::-1]))
        yv = np.concatenate((ctx.ys(yhat + band), ctx.ys((yhat - band)[::-1])))
        ctx.scene.add(S.Polyline(xs, yv, fill=theme.ink if not theme.dark else color,
                                 fill_opacity=0.08 if not theme.dark else 0.14, closed=True))
        ctx.scene.add(S.Polyline(px, ctx.ys(yhat), stroke=color, stroke_width=1.6 if not theme.dark else 1.4,
                                 dash=(5, 3) if theme.dark else None))
        if self.x_kind == "num":
            sign = "+" if a >= 0 else "−"
            ctx.notes.append(f"y = {format_value(b)}x {sign} {format_value(abs(a))} · R² = {r2:.2f}")

    def legend_items(self, ctx):
        if self.continuous:
            return []
        shape = "circle"
        return [LegendItem(g.name, g.name, ctx.color(g.name, i), shape) for i, g in enumerate(self.groups)]


def _fmt_x(v, kind):
    if kind == "time":
        return str(np.datetime64(int(v), "ns").astype("datetime64[s]")).replace("T", " ")
    return format_value(v)


def _fit(groups):
    """Least-squares line over all points, streamed in chunks (constant memory)."""
    n = sx = sy = sxx = sxy = syy = 0.0
    lo, hi = np.inf, -np.inf
    for g in groups:
        for s in range(0, len(g.x), CHUNK):
            x = g.x[s:s + CHUNK]
            y = g.y[s:s + CHUNK]
            ok = np.isfinite(x) & np.isfinite(y)
            x, y = x[ok], y[ok]
            if not len(x):
                continue
            n += len(x)
            sx += x.sum()
            sy += y.sum()
            lo, hi = min(lo, x.min()), max(hi, x.max())
    if n < 3:
        return None
    mx, my = sx / n, sy / n
    for g in groups:  # second pass on centred data for numerical stability
        for s in range(0, len(g.x), CHUNK):
            x = g.x[s:s + CHUNK]
            y = g.y[s:s + CHUNK]
            ok = np.isfinite(x) & np.isfinite(y)
            dx, dy = x[ok] - mx, y[ok] - my
            sxx += float(dx @ dx)
            sxy += float(dx @ dy)
            syy += float(dy @ dy)
    if sxx == 0:
        return None
    b = sxy / sxx
    a = my - b * mx
    sse = max(syy - b * sxy, 0.0)
    r2 = 1 - sse / syy if syy else 1.0
    se = np.sqrt(sse / (n - 2))

    def ci(x):
        return 1.96 * se * np.sqrt(1 / n + (np.asarray(x) - mx) ** 2 / sxx)

    return a, b, r2, ci, lo, hi
