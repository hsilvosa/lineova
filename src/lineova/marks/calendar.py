"""Calendar heatmaps: one cell per day, a week per column, a block per year."""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._color import mix, ramp_lut, to_hex
from .._data import DataError, as_float, columns_of, get_column, is_frame, to_array, value_kind
from .._text import format_value
from ._base import DrawContext, Layer

_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_DAYS = ["Mon", "", "Wed", "", "Fri", "", ""]


class CalendarLayer(Layer):
    cartesian = False
    own_legend = True

    def __init__(self, data=None, x=None, y=None, *, agg="sum", label=None, format=None):
        self.data, self.x, self.y, self.agg, self.label, self.fmt = data, x, y, agg, label, format

    def prepare(self, chart) -> None:
        data, x, y = self.data, self.x, self.y
        if is_frame(data) and not isinstance(data, dict):
            cols = columns_of(data)
            x = x or next((c for c in cols if value_kind(to_array(get_column(data, c))) == "time"), None)
            if x is None and hasattr(data, "index"):
                dates = to_array(data.index)
            else:
                dates = to_array(get_column(data, x))
            y = y or next((c for c in cols if c != x and value_kind(to_array(get_column(data, c))) == "num"), None)
            vals = as_float(to_array(get_column(data, y)), "num") if y is not None else None
            self.label = self.label or (str(y) if y is not None else "count")
        elif isinstance(data, dict):
            dates = np.array(list(data.keys()))
            vals = as_float(np.array(list(data.values()), dtype=float), "num")
        else:
            src = data if data is not None else x
            if src is None:
                raise DataError("Pass dates (counted per day) or dates with values: calendar(dates, y=values).")
            dates = to_array(src)
            vals = as_float(to_array(y), "num") if y is not None else None
        days = np.asarray(dates).astype("datetime64[D]")
        ok = ~np.isnat(days)
        days = days[ok]
        if vals is not None:
            vals = vals[ok]
        if not len(days):
            raise DataError("No valid dates.")
        d0, d1 = days.min(), days.max()
        first = np.datetime64(f"{str(d0)[:4]}-01-01")
        last = np.datetime64(f"{str(d1)[:4]}-12-31")
        n = int((last - first).astype(int)) + 1
        idx = (days - first).astype(int)
        if vals is None:
            per_day = np.bincount(idx, minlength=n).astype(float)
            has = per_day > 0
        else:
            good = ~np.isnan(vals)
            if self.agg == "mean":
                s = np.bincount(idx[good], vals[good], minlength=n)
                c = np.bincount(idx[good], minlength=n)
                with np.errstate(invalid="ignore"):
                    per_day = s / c
                has = c > 0
            else:
                per_day = np.bincount(idx[good], vals[good], minlength=n)
                has = np.bincount(idx[good], minlength=n) > 0
        self.first, self.per_day, self.has = first, per_day, has
        self.years = list(range(int(str(first)[:4]), int(str(last)[:4]) + 1))
        v = per_day[has]
        self.vmin, self.vmax = (float(v.min()), float(v.max())) if len(v) else (0.0, 1.0)
        self.theme = chart.resolved_theme

    def colorbar(self):
        return (self.theme.sequential, self.vmin, self.vmax, self.label or "")

    def default_size(self, theme):
        return 860.0, float(90 + 132 * len(self.years))

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        plot = ctx.plot
        size = theme.font_size - 1
        left = 46.0
        cell = min((plot.w - left) / 53.0, (plot.h / len(self.years) - size * 2.2) / 7.0)
        cell = max(cell, 3.0)
        gap = 1.5 if cell >= 8 else 0.5
        lut = ramp_lut(tuple(theme.sequential))
        empty = mix(theme.background, theme.ink, 0.06 if not theme.dark else 0.12)
        span = (self.vmax - self.vmin) or 1.0
        y = plot.y
        for year in self.years:
            jan1 = np.datetime64(f"{year}-01-01")
            dec31 = np.datetime64(f"{year}-12-31")
            wd0 = int((jan1.astype("datetime64[D]").astype(int) + 3) % 7)     # 0 = Monday
            top = y + size * 1.8
            ctx.scene.add(S.Text(plot.x, top + cell * 3.5, str(year), size + 2, theme.ink, weight=700, baseline="middle"))
            for r, name in enumerate(_DAYS):
                if name:
                    ctx.scene.add(S.Text(plot.x + left - 6, top + r * cell + cell / 2, name, size - 0.5,
                                         theme.ink_muted, anchor="end", baseline="middle"))
            n_days = int((dec31 - jan1).astype(int)) + 1
            off = int((jan1 - self.first).astype(int))
            for k in range(n_days):
                pos = wd0 + k
                col, row = pos // 7, pos % 7
                x0 = plot.x + left + col * cell
                y0 = top + row * cell
                day = jan1 + np.timedelta64(k, "D")
                if str(day)[8:10] == "01":          # month label above the column of its first day
                    ctx.scene.add(S.Text(x0, y + size, _MON[int(str(day)[5:7]) - 1], size, theme.ink_secondary))
                i = off + k
                if self.has[i]:
                    t = (self.per_day[i] - self.vmin) / span
                    fill = to_hex(lut[int(np.clip(t, 0, 1) * 255)] / 255)
                    title = f"{day}: {format_value(self.per_day[i])}"
                else:
                    fill, title = empty, f"{day}: no data"
                ctx.scene.add(S.Rect(x0 + gap / 2, y0 + gap / 2, cell - gap, cell - gap, fill=fill,
                                     rx=min(2.0, cell / 5), title=title))
            y = top + 7 * cell + size * 1.6
