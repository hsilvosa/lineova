"""Timelines and Gantt charts: tasks as bars from start to end, milestones as diamonds."""

from __future__ import annotations

import datetime as _dt

import numpy as np

from .. import scene as S
from .._color import mix
from .._data import (DataError, as_float, columns_of, factorize, get_column, is_auto, is_frame, to_array,
                     value_kind)
from ._base import Domain, DrawContext, Layer, LegendItem
from ._geom import rounded_bar

_AUTO = "auto"
_TASK = ("task", "name", "label", "activity", "item", "title")
_START = ("start", "begin", "from", "start_date", "starts")
_END = ("end", "finish", "to", "end_date", "due", "ends")


def _pick(cols, names, given):
    if given is not None:
        return given
    low = {str(c).lower(): c for c in cols}
    return next((low[n] for n in names if n in low), None)


class TimelineLayer(Layer):
    def __init__(self, data=None, *, task=None, start=None, end=None, color=None, progress=None, today=_AUTO,
                 labels=_AUTO):
        self.data, self.task, self.start, self.end = data, task, start, end
        self.color_col, self.progress, self.today, self.labels = color, progress, today, labels

    def prepare(self, chart) -> None:
        data = self.data
        groups = prog = None
        if is_frame(data) and not isinstance(data, list):
            cols = columns_of(data)
            t = _pick(cols, _TASK, self.task) or cols[0]
            s = _pick(cols, _START, self.start)
            e = _pick(cols, _END, self.end)
            if s is None:
                raise DataError("No start column found; pass start='column'.")
            tasks = [str(v) for v in to_array(get_column(data, t))]
            sv = to_array(get_column(data, s))
            ev = to_array(get_column(data, e)) if e is not None else sv
            if self.color_col is not None:
                groups = to_array(get_column(data, self.color_col))
            if self.progress is not None:
                prog = as_float(to_array(get_column(data, self.progress)), "num")
        else:
            rows = list(data)
            if not rows:
                raise DataError("No tasks to draw.")
            tasks = [str(r[0]) for r in rows]
            sv = np.array([r[1] for r in rows], dtype=object)
            ev = np.array([r[2] if len(r) > 2 and r[2] is not None else r[1] for r in rows], dtype=object)
            if rows and len(rows[0]) > 3:
                groups = np.array([r[3] for r in rows], dtype=object)
        kind = value_kind(np.asarray(sv))
        if kind == "cat":
            try:
                sv = np.array(sv, dtype="datetime64[ns]")
                ev = np.array(ev, dtype="datetime64[ns]")
                kind = "time"
            except (ValueError, TypeError):
                raise DataError("Start/end must be dates or numbers.") from None
        self.kind = kind
        self.s = as_float(np.asarray(sv), kind)
        self.e = as_float(np.asarray(ev), kind)
        if np.any(self.e < self.s):
            bad = tasks[int(np.argmax(self.e < self.s))]
            raise DataError(f"Task {bad!r} ends before it starts.")
        self.tasks = tasks
        self.rows = list(dict.fromkeys(tasks))
        self.group_names: list = []
        self.group_of = None
        if groups is not None:
            codes, self.group_names = factorize(np.asarray(groups, dtype=object))
            self.group_of = codes
        self.prog = prog

    def keys(self):
        return list(self.group_names)

    def legend_items(self, ctx):
        return [LegendItem(g, g, ctx.color(g, i), "square") for i, g in enumerate(self.group_names)]

    def x_domain(self):
        lo, hi = float(np.nanmin(self.s)), float(np.nanmax(self.e))
        pad = (hi - lo) * 0.02 or (86400e9 if self.kind == "time" else 1.0)
        return Domain(self.kind, lo - pad, hi + pad, nice=False, extent=(lo, hi))

    def y_domain(self):
        return Domain("cat", categories=list(reversed(self.rows)), gap=0.35)

    def default_size(self, theme):
        return None, float(min(max(len(self.rows) * 30 + 150, 220), 1800))

    def _now(self):
        now = np.datetime64(_dt.datetime.now(), "ns").astype(np.int64)
        return float(now)

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        xs, ys = ctx.xs, ctx.ys
        band = ys.bandwidth
        size = theme.font_size - 0.5
        base_col = theme.palette[0] if theme.family != "folio" else theme.ink_secondary
        if self.kind == "time" and (self.today is True or is_auto(self.today)):
            now = self._now()
            if min(xs.d0, xs.d1) <= now <= max(xs.d0, xs.d1):
                px = xs.scalar(now)
                ctx.scene.add(S.Line(px, ctx.plot.y, px, ctx.plot.bottom, theme.negative, 1.2, dash=(3, 3)))
                ctx.overlay.append(S.Text(px + 4, ctx.plot.y + size, "Today", size, theme.negative, weight=600,
                                          halo=theme.background))
        for i, task in enumerate(self.tasks):
            y0 = ys.band(ys.index[task])
            x0, x1 = xs.scalar(self.s[i]), xs.scalar(self.e[i])
            color = base_col
            if self.group_of is not None and self.group_of[i] >= 0:
                color = ctx.color(self.group_names[self.group_of[i]], int(self.group_of[i]))
            if ctx.highlight and task not in ctx.highlight:
                color = theme.muted
            if x1 - x0 < 1.0:                  # milestone
                cy = y0 + band / 2
                r = min(band * 0.42, 8.0)
                ctx.scene.add(S.Markers(np.array([x0]), np.array([cy]), "diamond", r, fill=color,
                                        stroke=theme.background, stroke_width=1.2, titles=[f"{task} (milestone)"]))
                continue
            r = min(theme.bar_radius, band / 2, 4.0)
            title = task
            if self.prog is not None and np.isfinite(self.prog[i]):
                title += f" · {self.prog[i]:.0%} done"
                light = mix(color, theme.background, 0.62)
                ctx.scene.add(S.Path(rounded_bar(x0, y0, x1 - x0, band, r, "both" if r >= band / 2 else "right"),
                                     fill=light, title=title))
                done = x0 + (x1 - x0) * float(np.clip(self.prog[i], 0, 1))
                if done > x0 + 0.5:
                    ctx.scene.add(S.Path(rounded_bar(x0, y0, done - x0, band, min(r, (done - x0) / 2),
                                                     "both" if r >= band / 2 else "right"), fill=color))
            else:
                ctx.scene.add(S.Path(rounded_bar(x0, y0, x1 - x0, band, r, "both" if r >= band / 2 else "right"),
                                     fill=color, title=title))
