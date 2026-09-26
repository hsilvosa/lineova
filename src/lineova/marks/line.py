"""Line and area charts."""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._data import Chunks, interval_bounds, interval_spec, is_auto, resolve_xy
from .._text import format_value
from ..reduce import is_sorted, m4, minmax_envelope
from ..scales import BandScale
from ._base import Domain, DrawContext, Layer, LegendItem
from ._geom import finite_runs, monotone_path, spread_labels

_AUTO = "auto"


def _nanrange(arrays) -> tuple[float, float]:
    lo, hi = np.inf, -np.inf
    for a in arrays:
        if len(a):
            with np.errstate(invalid="ignore"):
                amin, amax = np.nanmin(a), np.nanmax(a)
            if np.isfinite(amin):
                lo, hi = min(lo, float(amin)), max(hi, float(amax))
    return lo, hi


class LineLayer(Layer):
    """One line per series. Handles any number of points (M4-reduced to the pixel grid)."""

    supports_direct_labels = True
    wants_readout = True
    legend_shape = "line"

    def __init__(self, data=None, x=None, y=None, color=_AUTO, *, width=_AUTO, curve=_AUTO, markers=_AUTO,
                 dash=None, label=None, render=_AUTO, values=_AUTO, band=None):
        self.data, self.x, self.y, self.color = data, x, y, color
        self.band = band
        self.width, self.curve, self.markers, self.dash = width, curve, markers, dash
        self.label, self.render, self.values = label, render, values

    # ---------------------------------------------------------------- data
    def prepare(self, chart) -> None:
        data, x, y, color = self.data, self.x, self.y, self.color
        if isinstance(data, Chunks):
            from .. import stream
            xv, yv, _ = stream.line(data, x, y)
            if x is not None and stream.first_kind(data, x) == "time":
                xv = xv.astype(np.int64).astype("datetime64[ns]")
            data, x, y, color = None, xv, yv, None
        xy = resolve_xy(data, x, y, color, extra=interval_spec(self.band))
        if isinstance(self.data, Chunks) and isinstance(self.y, str):
            xy.series[0].name = self.label or str(self.y)
            xy.y_label = str(self.y)
            xy.x_label = str(self.x) if isinstance(self.x, str) else None
        if self.label and len(xy.series) == 1:
            xy.series[0].name = str(self.label)
        for s in xy.series:
            if xy.x_kind != "cat":
                bad = np.isnan(s.x)
                if bad.any():
                    s.x, s.y = s.x[~bad], s.y[~bad]
                    s.extra = {k: v[~bad] for k, v in s.extra.items()}
                if not is_sorted(s.x):
                    order = np.argsort(s.x, kind="stable")
                    s.x, s.y = s.x[order], s.y[order]
                    s.extra = {k: v[order] for k, v in s.extra.items()}
            b = interval_bounds(s.y, s.extra)
            if b is not None:
                s.extra["_lo"], s.extra["_hi"] = b
        self.xy = xy
        self.theme = chart.resolved_theme

    def keys(self):
        return [s.name for s in self.xy.series]

    def x_domain(self):
        xy = self.xy
        if xy.x_kind == "cat":
            return Domain("cat", categories=xy.categories, gap=0.0)
        lo, hi = _nanrange(s.x for s in xy.series)
        return Domain(xy.x_kind, lo, hi, nice=False, extent=(lo, hi))

    def y_domain(self):
        arrays = [s.y for s in self.xy.series] + [s.extra[k] for s in self.xy.series for k in ("_lo", "_hi")
                                                   if k in s.extra]
        lo, hi = _nanrange(arrays)
        return Domain("num", lo, hi, nice=True, extent=(lo, hi))

    def _draw_bands(self, ctx: DrawContext) -> None:
        """Shaded interval (confidence band, min-max range) under each line."""
        theme = ctx.theme
        xs, ys = ctx.xs, ctx.ys
        for i, s in enumerate(self.xy.series):
            if "_lo" not in s.extra:
                continue
            color = ctx.color(s.name, i)
            lo, hi = s.extra["_lo"], s.extra["_hi"]
            if isinstance(xs, BandScale):
                idx = np.array([xs.index.get(v, -1) for v in s.x])
                ok = idx >= 0
                px, lo, hi = xs.center(idx[ok]).astype(float), lo[ok], hi[ok]
            else:
                x = s.x
                cols = max(32, int(ctx.plot.w * ctx.raster_scale))
                if len(x) > 4 * cols and self.render != "exact":
                    xlim = (min(xs.d0, xs.d1), max(xs.d0, xs.d1))
                    x, lo, _ = minmax_envelope(x, lo, xlim, cols)
                    _, _, hi = minmax_envelope(s.x, hi, xlim, cols)
                px = xs(x)
            fill = theme.ink if theme.name == "folio" and len(self.xy.series) == 1 else color
            op = 0.12 if theme.name == "folio" else theme.area_opacity * (0.9 if theme.dark else 0.8)
            for a, b in finite_runs(px, (lo + hi)):
                pxs = np.concatenate((px[a:b], px[a:b][::-1]))
                pys = np.concatenate((ys(hi[a:b]), ys(lo[a:b])[::-1]))
                ctx.scene.add(S.Polyline(pxs, pys, fill=fill, fill_opacity=op, closed=True))

    def axis_labels(self):
        y = self.xy.y_label if (len(self.xy.series) == 1 or self.xy.grouped_by) else None
        return self.xy.x_label, y

    def values_for_reference(self, axis):
        return [s.y if axis == "y" else s.x for s in self.xy.series if axis == "y" or self.xy.x_kind != "cat"]

    # ---------------------------------------------------------------- drawing
    def _pixels(self, ctx: DrawContext, s):
        xs, ys = ctx.xs, ctx.ys
        if isinstance(xs, BandScale):
            idx = np.array([xs.index.get(v, -1) for v in s.x])
            ok = idx >= 0
            return xs.center(idx[ok]).astype(float), ys(s.y[ok])
        x, y = s.x, s.y
        if self.render != "exact":
            cols = max(32, int(ctx.plot.w * ctx.raster_scale))
            x, y = m4(x, y, (min(xs.d0, xs.d1), max(xs.d0, xs.d1)), cols)
        return xs(x), ys(y)

    def _order(self, ctx):
        """Muted series first so highlighted ones sit on top."""
        items = list(enumerate(self.xy.series))
        muted = ctx.theme.muted
        return sorted(items, key=lambda it: 0 if ctx.color(it[1].name, it[0]) == muted else 1)

    def draw(self, ctx: DrawContext) -> None:
        self._draw_bands(ctx)
        theme = ctx.theme
        n_series = len(self.xy.series)
        lw = theme.line_width if is_auto(self.width) else float(self.width)
        smooth = (theme.curve == "smooth") if is_auto(self.curve) else self.curve in (True, "smooth")
        legend_mode = ctx.options.get("_legend_mode")
        self._last = {}
        end_vals: list = []
        for i, s in self._order(ctx):
            color = ctx.color(s.name, i)
            is_muted = color == theme.muted and n_series > 1
            px, py = self._pixels(ctx, s)
            if len(px) == 0:
                continue
            dash = self.dash if self.dash is not None else (theme.dashes[i % len(theme.dashes)] if theme.dashes else None)
            if theme.lead_area and i == 0 and n_series <= 4 and not isinstance(self, AreaLayer):
                self._lead_area(ctx, px, py, color, smooth)
            width = lw * (0.8 if is_muted else 1.0)
            if smooth and len(px) <= 600:
                ctx.scene.add(S.Path(monotone_path(px, py), stroke=color, stroke_width=width, dash=dash))
            else:
                ctx.scene.add(S.Polyline(px, py, stroke=color, stroke_width=width, dash=dash))
            show_markers = (self.markers is True) or (is_auto(self.markers) and theme.series_markers
                                                     and len(s.y) <= 60)
            if show_markers:
                shape = theme.series_markers[i % len(theme.series_markers)] if theme.series_markers else "circle"
                ctx.scene.add(S.Markers(px, py, shape, theme.marker_size, fill=theme.background, stroke=color,
                                        stroke_width=max(1.0, lw * 0.8)))
            last = _last_finite(px, py)
            if last is None:
                continue
            lx, ly = last
            self._last[s.name] = (lx, ly, s.y[np.isfinite(s.y)][-1] if np.isfinite(s.y).any() else np.nan)
            if theme.end_markers and n_series <= 6 and not is_muted:
                ctx.scene.add(S.Markers(np.array([lx]), np.array([ly]), "circle", 4.0, fill=color,
                                        stroke=theme.background, stroke_width=2))
                if self._show_values(theme, legend_mode):
                    end_vals.append((lx, ly, format_value(self._last[s.name][2])))
            if legend_mode == "direct":
                ctx.end_labels.append((s.name, s.name, lx, ly))
        if end_vals:
            size = theme.font_size
            ys = spread_labels([v[1] for v in end_vals], size * 1.2, ctx.plot.y, ctx.plot.bottom)
            for (lx, ly, txt), y in zip(end_vals, ys):
                ctx.overlay.append(S.Text(lx + 8, y, txt, size, theme.ink, baseline="middle", weight=600,
                                          halo=theme.background))

    def _show_values(self, theme, legend_mode) -> bool:
        n = len(self.xy.series)
        if self.values is True:
            return True
        return is_auto(self.values) and theme.end_markers and n <= 4 and legend_mode not in ("direct", "readout") \
            and not isinstance(self, AreaLayer)

    def end_value_texts(self, theme, legend_mode) -> list[str]:
        if not self._show_values(theme, legend_mode):
            return []
        out = []
        for s in self.xy.series:
            ok = np.isfinite(s.y)
            if ok.any():
                out.append(format_value(s.y[ok][-1]))
        return out

    def _lead_area(self, ctx, px, py, color, smooth):
        ys = ctx.ys
        lo = min(ys.d0, ys.d1)
        base = ys.scalar(0.0 if lo <= 0 <= max(ys.d0, ys.d1) else lo)
        for a, b in finite_runs(px, py):
            if smooth and b - a <= 600:
                cmds = monotone_path(px[a:b], py[a:b])
                cmds += [("L", px[b - 1], base), ("L", px[a], base), ("Z",)]
                ctx.scene.add(S.Path(cmds, fill=color, fill_opacity=ctx.theme.area_opacity * 0.75, stroke=None))
            else:
                xs = np.concatenate(([px[a]], px[a:b], [px[b - 1]]))
                yv = np.concatenate(([base], py[a:b], [base]))
                ctx.scene.add(S.Polyline(xs, yv, fill=color, fill_opacity=ctx.theme.area_opacity * 0.75, closed=True))

    def legend_items(self, ctx):
        theme = ctx.theme
        out = []
        for i, k in enumerate(self.keys()):
            dash = theme.dashes[i % len(theme.dashes)] if theme.dashes else None
            out.append(LegendItem(k, k, ctx.color(k, i), self.legend_shape if theme.legend_marker == "line"
                                  else theme.legend_marker, dash))
        return out

    def readout(self, ctx):
        last = getattr(self, "_last", {})
        return [(k, ctx.color(k, i), format_value(last[k][2]) if k in last else "–")
                for i, k in enumerate(self.keys())]


def _last_finite(px, py):
    ok = np.flatnonzero(np.isfinite(px) & np.isfinite(py))
    if not len(ok):
        return None
    j = ok[-1]
    return float(px[j]), float(py[j])


class AreaLayer(LineLayer):
    """Filled areas. Several series stack by default; ``normalize=True`` shows shares (100%)."""

    legend_shape = "square"
    wants_readout = False

    def __init__(self, data=None, x=None, y=None, color=_AUTO, *, stack=_AUTO, normalize=False, **kw):
        super().__init__(data, x, y, color, **kw)
        self.stack, self.normalize = stack, normalize

    def prepare(self, chart) -> None:
        super().prepare(chart)
        series = self.xy.series
        stacked = (len(series) > 1) if is_auto(self.stack) else bool(self.stack)
        self.stacked = stacked or self.normalize
        if not self.stacked:
            return
        if self.xy.x_kind == "cat":
            cats = self.xy.categories
            grid = np.arange(len(cats), dtype=float)
            vals = []
            for s in series:
                pos = {c: i for i, c in enumerate(cats)}
                v = np.zeros(len(cats))
                for xv, yv in zip(s.x, s.y):
                    v[pos[xv]] += 0 if np.isnan(yv) else yv
                vals.append(v)
        else:
            total = sum(len(s.x) for s in series)
            if total > 400_000:
                lo, hi = _nanrange(s.x for s in series)
                grid = np.linspace(lo, hi, 4096)
            else:
                grid = np.unique(np.concatenate([s.x for s in series]))
            vals = [np.interp(grid, s.x, np.nan_to_num(s.y), left=0, right=0) if len(s.x) else np.zeros_like(grid)
                    for s in series]
        stack = np.vstack(vals) if vals else np.zeros((0, len(grid)))
        if np.any(stack < 0):
            stack = np.clip(stack, 0, None)  # stacking negative values is not meaningful
        tops = np.cumsum(stack, axis=0)
        if self.normalize:
            tot = np.where(tops[-1] == 0, 1, tops[-1])
            tops = tops / tot
            if chart._y.format is None:
                chart._y.format = lambda v: f"{v:.0%}"
        self.grid, self.tops = grid, tops

    def x_domain(self):
        d = super().x_domain()
        if d.kind == "cat":
            d.gap = 0.0
        return d

    def y_domain(self):
        if self.stacked:
            hi = float(np.nanmax(self.tops)) if self.tops.size else 1.0
            return Domain("num", 0.0, 1.0 if self.normalize else hi, zero=True, nice=not self.normalize)
        d = super().y_domain()
        d.zero = True
        return d

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        if not self.stacked:
            ys = ctx.ys
            base = ys.scalar(0.0)
            for i, s in self._order(ctx):
                color = ctx.color(s.name, i)
                px, py = self._pixels(ctx, s)
                for a, b in finite_runs(px, py):
                    xs = np.concatenate(([px[a]], px[a:b], [px[b - 1]]))
                    yv = np.concatenate(([base], py[a:b], [base]))
                    ctx.scene.add(S.Polyline(xs, yv, fill=color, fill_opacity=theme.area_opacity + 0.1, closed=True))
                ctx.scene.add(S.Polyline(px, py, stroke=color, stroke_width=theme.line_width * 0.85))
                last = _last_finite(px, py)
                if last and ctx.options.get("_legend_mode") == "direct":
                    ctx.end_labels.append((s.name, s.name, last[0], last[1]))
            return
        xs_scale, ys = ctx.xs, ctx.ys
        if isinstance(xs_scale, BandScale):
            gx = xs_scale.center(self.grid.astype(int)).astype(float)
        else:
            gx = xs_scale(self.grid)
        prev = np.full(len(gx), ys.scalar(0.0))
        for i, s in enumerate(self.xy.series):
            color = ctx.color(s.name, i)
            top = ys(self.tops[i])
            xs = np.concatenate((gx, gx[::-1]))
            yv = np.concatenate((top, prev[::-1]))
            ctx.scene.add(S.Polyline(xs, yv, fill=color, fill_opacity=0.88, closed=True))
            ctx.scene.add(S.Polyline(gx, top, stroke=theme.background, stroke_width=1.0))
            if ctx.options.get("_legend_mode") == "direct" and len(gx):
                ctx.end_labels.append((s.name, s.name, float(gx[-1]), float((top[-1] + prev[-1]) / 2)))
            prev = top
