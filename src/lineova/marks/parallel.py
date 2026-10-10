"""Parallel coordinates: one vertical axis per variable, one polyline per row."""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._color import ramp_lut, to_hex
from .._data import (DataError, as_float, columns_of, factorize, get_column, is_auto, is_frame, to_array,
                     value_kind)
from .._text import format_value, truncate
from ._base import DrawContext, Layer, LegendItem

_AUTO = "auto"
MAX_LINES = 30_000


class ParallelLayer(Layer):
    """A DataFrame or dict of columns. ``dims=`` picks and orders the axes (numeric columns by default);
    ``color=`` is a column: text colours by group, numbers colour on a ramp. ``invert=[...]`` flips axes.
    ``normalize="range"`` (default) scales each axis to its own min-max; ``"zscore"`` uses standard scores.
    """

    cartesian = False
    own_legend = False

    def __init__(self, data=None, *, dims=None, color=None, invert=(), normalize="range", opacity=_AUTO,
                 label=None, cmap=_AUTO, seed=0):
        self.data, self.dims, self.color_col, self.invert = data, dims, color, tuple(invert or ())
        self.normalize, self.opacity, self.label, self.cmap, self.seed = normalize, opacity, label, cmap, seed

    def prepare(self, chart) -> None:
        data = self.data
        if isinstance(data, dict):
            cols = {str(k): to_array(v) for k, v in data.items()}
        elif is_frame(data):
            cols = {str(c): to_array(get_column(data, c)) for c in columns_of(data)}
        else:
            raise DataError("Pass a DataFrame or a dict of columns.")
        color_name = None if self.color_col is None else str(self.color_col)
        if color_name is not None and color_name not in cols:
            raise DataError(f"color={color_name!r} is not a column.")
        if self.dims is not None:
            dims = [str(d) for d in self.dims]
            for d in dims:
                if d not in cols:
                    raise DataError(f"dims= names an unknown column {d!r}.")
        else:
            dims = [c for c, v in cols.items() if c != color_name and value_kind(v) in ("num", "time")]
        for d in dims:
            if value_kind(cols[d]) == "cat":
                raise DataError(f"Column {d!r} is not numeric. Encode it first, or leave it out of dims=.")
        if len(dims) < 2:
            raise DataError("Parallel coordinates need at least 2 numeric columns.")
        if self.normalize not in ("range", "zscore"):
            raise DataError("normalize must be 'range' or 'zscore'.")
        mat = np.column_stack([as_float(cols[d], value_kind(cols[d])) for d in dims])
        n = len(mat)
        self.total = n
        sel = np.arange(n)
        if n > MAX_LINES:
            sel = np.sort(np.random.default_rng(self.seed).choice(n, MAX_LINES, replace=False))
        self.mat_raw = mat[sel]
        self.dims_used = dims
        self.raw_lo = np.nanmin(mat, axis=0)
        self.raw_hi = np.nanmax(mat, axis=0)
        if self.normalize == "zscore":
            mu, sd = np.nanmean(mat, axis=0), np.nanstd(mat, axis=0)
            sd[sd == 0] = 1.0
            z = (self.mat_raw - mu) / sd
            self.lo_z = float(np.nanmin(z)) if z.size else -1.0
            self.hi_z = float(np.nanmax(z)) if z.size else 1.0
            span = (self.hi_z - self.lo_z) or 1.0
            self.scaled = (z - self.lo_z) / span
        else:
            span = np.where(self.raw_hi > self.raw_lo, self.raw_hi - self.raw_lo, 1.0)
            self.scaled = (self.mat_raw - self.raw_lo) / span
        for d in self.invert:
            if str(d) not in dims:
                raise DataError(f"invert= names {d!r}, which is not one of the axes.")
            j = dims.index(str(d))
            self.scaled[:, j] = 1.0 - self.scaled[:, j]
        self.group_names: list = []
        self.group_of = None
        self.color_values = None
        if color_name is not None:
            cv = cols[color_name]
            kind = value_kind(cv)
            if kind == "cat":
                codes, names = factorize(np.asarray(cv, dtype=object))
                self.group_of = codes[sel]
                self.group_names = [str(x) for x in names]
            else:
                self.color_values = as_float(cv, kind)[sel]
                theme = chart.resolved_theme
                self.stops = tuple(self.cmap) if isinstance(self.cmap, (list, tuple)) else tuple(theme.sequential)
                finite = self.color_values[np.isfinite(self.color_values)]
                self.cmin = float(finite.min()) if len(finite) else 0.0
                self.cmax = float(finite.max()) if len(finite) else 1.0
        self.color_label = color_name if self.label is None else self.label

    def keys(self):
        return list(self.group_names)

    def legend_items(self, ctx):
        return [LegendItem(g, g, ctx.color(g, i), "line") for i, g in enumerate(self.group_names)]

    def colorbar(self):
        if self.color_values is None:
            return None
        return (self.stops, self.cmin, self.cmax, self.color_label)

    def default_size(self, theme):
        return float(min(1200, max(560, len(self.dims_used) * 130 + 120))), 440.0

    def draw(self, ctx: DrawContext) -> None:
        theme, plot = ctx.theme, ctx.plot
        size = theme.font_size - 0.5
        k = len(self.dims_used)
        top = plot.y + size * 2.4
        bottom = plot.bottom - size * 1.2
        xs = plot.x + 20 + (plot.w - 40) * np.arange(k) / (k - 1)
        py = bottom - self.scaled * (bottom - top)
        n = len(self.scaled)
        op = (float(np.clip(5.0 / np.sqrt(max(n, 1)), 0.04, 0.8)) if is_auto(self.opacity) else float(self.opacity))
        hl = ctx.highlight
        base = theme.palette[0] if theme.family != "folio" else theme.ink_secondary
        if self.group_of is not None:
            colors = [ctx.color(self.group_names[g], int(g)) if g >= 0 else theme.muted for g in self.group_of]
        elif self.color_values is not None:
            lut = ramp_lut(self.stops)
            t = np.clip((self.color_values - self.cmin) / ((self.cmax - self.cmin) or 1.0), 0, 1)
            t = np.nan_to_num(t)
            idx = (t * 255).astype(int)
            colors = [to_hex(lut[i] / 255.0) for i in idx]
        else:
            colors = [base] * n
        names = self.group_names
        # draw each colour group in one pass, highlighted groups last
        order = np.arange(n)
        if hl and self.group_of is not None:
            on = np.array([names[g] in hl if g >= 0 else False for g in self.group_of])
            order = np.concatenate((order[~on], order[on]))
            op_of = np.where(on, min(1.0, op * 2), op * 0.5)
            colors = [colors[i] if on[i] else theme.muted for i in range(n)]
        else:
            op_of = np.full(n, op)
        lw = 1.2 if n < 2000 else 0.8
        for i in order.tolist():
            row = py[i]
            ok = np.isfinite(row)
            if ok.sum() < 2:
                continue
            ctx.scene.add(S.Polyline(np.where(ok, xs, np.nan), row, stroke=colors[i], stroke_width=lw,
                                     opacity=float(op_of[i]), join="round", cap="round"))
        # axes
        for j, dname in enumerate(self.dims_used):
            x = float(xs[j])
            ctx.scene.add(S.Line(x, top, x, bottom, theme.axis_color, 1.0))
            label = truncate(dname, max(40.0, (plot.w - 40) / k - 6), size, theme.font_kind, True)
            ctx.scene.add(S.Text(x, top - size * 1.1, label, size, theme.ink, anchor="middle", weight=600,
                                 halo=theme.background))
            inverted = dname in self.invert
            if self.normalize == "range":
                lo_txt, hi_txt = format_value(self.raw_lo[j]), format_value(self.raw_hi[j])
                if inverted:
                    lo_txt, hi_txt = hi_txt, lo_txt
                ctx.scene.add(S.Text(x, bottom + size * 1.1, lo_txt, size - 1, theme.ink_muted, anchor="middle",
                                     halo=theme.background))
                ctx.scene.add(S.Text(x, top - size * 2.2, hi_txt, size - 1, theme.ink_muted, anchor="middle",
                                     halo=theme.background))
        if n < self.total:
            ctx.notes.append(f"{n:,} of {self.total:,} rows shown")
