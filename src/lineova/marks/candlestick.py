"""Candlestick and OHLC charts for open/high/low/close data.

When there are more candles than fit (about one per 4 px), consecutive rows are
merged into wider periods (first open, max high, min low, last close), so a
decade of minute bars still draws as clean candles.
"""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._data import DataError, as_float, columns_of, get_column, is_auto, is_frame, to_array, value_kind
from .._text import format_value
from ._base import Domain, DrawContext, Layer, LegendItem

_AUTO = "auto"
_NAMES = {"open": ("open", "o", "opening"), "high": ("high", "h", "max"), "low": ("low", "l", "min"),
          "close": ("close", "c", "closing", "adj close", "adj_close", "price")}


def _find(cols, key):
    low = {str(c).lower(): c for c in cols}
    for n in _NAMES[key]:
        if n in low:
            return low[n]
    return None


class CandlestickLayer(Layer):
    def __init__(self, data=None, x=None, *, open=None, high=None, low=None, close=None, style=_AUTO,
                 max_candles=_AUTO):
        self.data, self.x = data, x
        self.cols = {"open": open, "high": high, "low": low, "close": close}
        self.style, self.max_candles = style, max_candles

    def prepare(self, chart) -> None:
        data = self.data
        arrays = {}
        if is_frame(data):
            cols = columns_of(data)
            for k in _NAMES:
                spec = self.cols[k] if self.cols[k] is not None else _find(cols, k)
                if spec is None:
                    raise DataError(f"No {k!r} column found. Pass {k}='column name'.")
                arrays[k] = as_float(to_array(get_column(data, spec) if isinstance(spec, str) else spec), "num")
            if self.x is not None:
                xv = to_array(get_column(data, self.x)) if isinstance(self.x, str) else to_array(self.x)
            else:
                tcol = next((c for c in cols if value_kind(to_array(get_column(data, c))) == "time"), None)
                if tcol is not None:
                    xv = to_array(get_column(data, tcol))
                elif hasattr(data, "index") and type(data).__module__.split(".")[0] == "pandas":
                    xv = to_array(data.index)
                else:
                    xv = np.arange(len(arrays["close"]))
        else:
            for k in _NAMES:
                if self.cols[k] is None:
                    raise DataError("Pass a DataFrame with open/high/low/close columns, or open=, high=, low=, close= arrays.")
                arrays[k] = as_float(to_array(self.cols[k]), "num")
            xv = to_array(self.x) if self.x is not None else np.arange(len(arrays["close"]))
        kind = value_kind(xv)
        if kind == "cat":
            raise DataError("Candlestick x must be dates or numbers.")
        self.x_kind = kind
        x = as_float(xv, kind)
        order = np.argsort(x, kind="stable")
        self.x = x[order]
        self.o, self.h, self.l, self.c = (arrays[k][order] for k in ("open", "high", "low", "close"))

    def keys(self):
        return ["Up", "Down"]

    def legend_items(self, ctx):
        return []

    def x_domain(self):
        x = self.x
        step = float(np.median(np.diff(x))) if len(x) > 1 else 1.0
        return Domain(self.x_kind, float(x[0]) - step, float(x[-1]) + step, nice=False)

    def y_domain(self):
        lo, hi = float(np.nanmin(self.l)), float(np.nanmax(self.h))
        return Domain("num", lo, hi, nice=True, pad=0.02, extent=(lo, hi))

    def _bucket(self, n_max):
        n = len(self.x)
        if n <= n_max:
            return self.x, self.o, self.h, self.l, self.c
        k = int(np.ceil(n / n_max))
        starts = np.arange(0, n, k)
        ends = np.minimum(starts + k, n) - 1
        with np.errstate(invalid="ignore"):
            h = np.fmax.reduceat(self.h, starts)
            lo = np.fmin.reduceat(self.l, starts)
        x = (self.x[starts] + self.x[ends]) / 2
        return x, self.o[starts], h, lo, self.c[ends]

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        n_max = int(ctx.plot.w / 4) if is_auto(self.max_candles) else int(self.max_candles)
        x, o, h, lo, c = self._bucket(max(10, n_max))
        px = ctx.xs(x)
        step = float(np.median(np.diff(px))) if len(px) > 1 else 10.0
        body = max(1.0, step * 0.68)
        up = c >= o
        style = ("ohlc" if theme.name == "folio" else "candle") if is_auto(self.style) else self.style
        tips = len(x) <= 600
        for sel, color in ((up, theme.positive), (~up, theme.negative)):
            if not sel.any():
                continue
            xs, hs, ls, os_, cs = px[sel], ctx.ys(h[sel]), ctx.ys(lo[sel]), ctx.ys(o[sel]), ctx.ys(c[sel])
            nan = np.full(len(xs), np.nan)
            wick_x = np.column_stack((xs, xs, nan)).ravel()
            wick_y = np.column_stack((hs, ls, nan)).ravel()
            if style == "ohlc":
                t = body / 2
                wick_x = np.concatenate((wick_x, np.column_stack((xs - t, xs, nan, xs, xs + t, nan)).ravel()))
                wick_y = np.concatenate((wick_y, np.column_stack((os_, os_, nan, cs, cs, nan)).ravel()))
                ctx.scene.add(S.Polyline(wick_x, wick_y, stroke=color, stroke_width=1.2, cap="butt", join="miter"))
                continue
            ctx.scene.add(S.Polyline(wick_x, wick_y, stroke=color, stroke_width=1.0, cap="butt"))
            idx = np.flatnonzero(sel)
            for j, i in enumerate(idx):
                top, bot = min(os_[j], cs[j]), max(os_[j], cs[j])
                title = (f"O {format_value(o[i])}  H {format_value(h[i])}  L {format_value(lo[i])}  "
                         f"C {format_value(c[i])}") if tips else None
                hollow = theme.name == "folio" and up[i]
                ctx.scene.add(S.Rect(xs[j] - body / 2, top, body, max(bot - top, 0.8),
                                     fill=theme.background if hollow else color, stroke=color if hollow else None,
                                     stroke_width=1.0, title=title))
