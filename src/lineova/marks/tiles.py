"""Dashboard pieces: sparklines and stat tiles."""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._color import mix
from .._data import DataError, as_float, is_auto, resolve_xy
from .._text import MINUS, format_value, text_width, truncate
from ..reduce import is_sorted, m4
from ._base import DrawContext, Layer

_AUTO = "auto"


def _spark(ctx, xs, ys, x, y, w, h, color, *, area=True, dots=True, band=None):
    """Draw a sparkline into the box (x, y, w, h). Returns the last point in pixels."""
    theme = ctx.theme
    ok = np.isfinite(xs) & np.isfinite(ys)
    xs, ys = xs[ok], ys[ok]
    if len(xs) < 2:
        return None
    x0, x1 = float(xs.min()), float(xs.max())
    y0, y1 = float(ys.min()), float(ys.max())
    if band is not None:
        y0, y1 = min(y0, band[0]), max(y1, band[1])
    if y0 == y1:
        y0, y1 = y0 - 1, y1 + 1
    pad = 3.0
    if len(xs) > 4 * w * 2:
        xs, ys = m4(xs, ys, (x0, x1), int(w * 2))

    def px(v):
        return x + pad + (v - x0) / ((x1 - x0) or 1) * (w - 2 * pad)

    def py(v):
        return y + h - pad - (v - y0) / (y1 - y0) * (h - 2 * pad)

    X, Y = px(xs), py(ys)
    if band is not None:
        ctx.scene.add(S.Rect(x, py(band[1]), w, py(band[0]) - py(band[1]), fill=theme.grid_color, opacity=0.7))
    if area:
        ctx.scene.add(S.Polyline(np.concatenate(([X[0]], X, [X[-1]])), np.concatenate(([y + h], Y, [y + h])),
                                 fill=color, fill_opacity=0.12, closed=True))
    ctx.scene.add(S.Polyline(X, Y, stroke=color, stroke_width=1.5))
    if dots:
        lo, hi = int(np.argmin(ys)), int(np.argmax(ys))
        ctx.scene.add(S.Markers(np.array([X[lo], X[hi]]), np.array([Y[lo], Y[hi]]), "circle", 1.8,
                                fill=theme.ink_muted))
    ctx.scene.add(S.Markers(np.array([X[-1]]), np.array([Y[-1]]), "circle", 3.0, fill=color,
                            stroke=theme.background, stroke_width=1.2))
    return X[-1], Y[-1]


class SparklineLayer(Layer):
    """Tiny line, no axes: fits in a table cell or next to a number."""

    cartesian = False
    own_legend = True

    def __init__(self, data=None, x=None, *, value=_AUTO, area=_AUTO, dots=True, band=None, color=None):
        self.data, self.x, self.value, self.area, self.dots, self.band, self.color = data, x, value, area, dots, band, color

    def prepare(self, chart) -> None:
        xy = resolve_xy(self.data, self.x, None, None)
        s = xy.series[0]
        x, y = (s.x, s.y) if xy.x_kind != "cat" else (np.arange(len(s.y), dtype=float), s.y)
        if not is_sorted(x):
            o = np.argsort(x, kind="stable")
            x, y = x[o], y[o]
        self.xv, self.yv = x.astype(float), y
        self.theme = chart.resolved_theme

    def default_size(self, theme):
        return 200.0, 48.0

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        plot = ctx.plot
        color = self.color or (theme.palette[0] if theme.name != "folio" else theme.ink)
        size = theme.font_size
        show_val = self.value is True or is_auto(self.value)
        last = self.yv[np.isfinite(self.yv)][-1] if np.isfinite(self.yv).any() else np.nan
        label = format_value(last) if np.isfinite(last) else ""
        lw = text_width(label, size, theme.font_kind, True) + 8 if show_val and label else 0
        end = _spark(ctx, self.xv, self.yv, plot.x, plot.y, plot.w - lw, plot.h, color,
                     area=(theme.name != "folio") if is_auto(self.area) else bool(self.area), dots=self.dots,
                     band=self.band)
        if end and lw:
            ctx.scene.add(S.Text(plot.right - lw + 6, end[1], label, size, theme.ink, baseline="middle", weight=600))


class StatLayer(Layer):
    """A headline number with a label, the change against a previous value and an optional sparkline."""

    cartesian = False
    own_legend = True

    def __init__(self, data=None, *, label=None, delta=None, previous=None, spark=None, format=None,
                 delta_format=_AUTO, good="up", note=None):
        self.value, self.label, self.delta, self.previous = data, label, delta, previous
        self.spark, self.fmt, self.delta_fmt, self.good, self.note = spark, format, delta_format, good, note

    def prepare(self, chart) -> None:
        if self.value is None:
            if self.spark is None:
                raise DataError("stat() needs a value (or spark= with a series whose last value is shown).")
            s = as_float(np.asarray(self.spark, dtype=float), "num")
            self.value = float(s[np.isfinite(s)][-1])
        self.theme = chart.resolved_theme

    def default_size(self, theme):
        return 280.0, 150.0 if self.spark is not None else 118.0

    def _fmt(self, v):
        if self.fmt is not None:
            return self.fmt(v) if callable(self.fmt) else (self.fmt.format(v) if "{" in self.fmt else format(v, self.fmt))
        if isinstance(v, str):
            return v
        return format_value(v)

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        plot = ctx.plot
        size = theme.font_size
        y = plot.y
        if self.label:
            ctx.scene.add(S.Text(plot.x, y + size, truncate(str(self.label).upper() if theme.uppercase_header
                                                              else str(self.label), plot.w, size, theme.font_kind),
                                 size, theme.ink_secondary, letter_spacing=0.3 if theme.uppercase_header else 0))
            y += size * 1.5
        big = min(theme.title_size * 2.4, plot.h * 0.42)
        text = self._fmt(self.value)
        ctx.scene.add(S.Text(plot.x, y + big * 0.95, text, big, theme.ink, weight=700))
        y += big * 1.25
        delta = self.delta
        if delta is None and self.previous is not None and not isinstance(self.value, str):
            prev = float(self.previous)
            delta = (float(self.value) - prev) / abs(prev) if prev else None
        if delta is not None:
            d = float(delta)
            up = d >= 0
            good = (up and self.good == "up") or (not up and self.good == "down")
            color = theme.positive if good else theme.negative
            if self.good is None:
                color = theme.ink_secondary
            arrow = "▲" if up else "▼"
            if is_auto(self.delta_fmt):
                body = f"{abs(d):.1%}" if (self.previous is not None and self.delta is None) else format_value(abs(d))
            elif callable(self.delta_fmt):
                body = self.delta_fmt(abs(d))
            else:
                body = (self.delta_fmt.format(abs(d)) if "{" in self.delta_fmt else format(abs(d), self.delta_fmt))
            sign = "+" if up else MINUS
            txt = f"{arrow} {sign}{body}"
            w = text_width(txt, size, theme.font_kind, True) + 14
            h = size + 8
            ctx.scene.add(S.Rect(plot.x, y, w, h, fill=mix(color, theme.background, 0.84), rx=h / 2))
            ctx.scene.add(S.Text(plot.x + 7, y + h / 2, txt, size, color, baseline="middle",
                                 weight=700))
            if self.note:
                ctx.scene.add(S.Text(plot.x + w + 8, y + h / 2, str(self.note), size - 0.5, theme.ink_muted,
                                     baseline="middle"))
            y += h + 8
        elif self.note:
            ctx.scene.add(S.Text(plot.x, y + size, str(self.note), size - 0.5, theme.ink_muted))
            y += size * 1.6
        if self.spark is not None and plot.bottom - y > 14:
            s = as_float(np.asarray(self.spark, dtype=float), "num")
            color = theme.palette[0] if theme.name != "folio" else theme.ink
            _spark(ctx, np.arange(len(s), dtype=float), s, plot.x, y + 2, plot.w, plot.bottom - y - 2, color,
                   area=theme.name != "folio", dots=False)
