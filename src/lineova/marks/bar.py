"""Bar charts: single, grouped, stacked and 100%-stacked; vertical or horizontal."""

from __future__ import annotations

import re

import numpy as np

from .. import scene as S
from .._color import mix, readable_on
from .._data import (aggregate, as_float, columns_of, DataError, factorize, get_column, is_auto, is_frame,
                     ordered_categories, series_name, to_array, value_kind)
from .._text import format_value, text_width
from ._base import Domain, DrawContext, Layer, LegendItem
from ._geom import rounded_bar

_AUTO = "auto"
_MONTHS = {m.lower() for m in ("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec January February March April "
                               "June July August September October November December").split()}
_DAYS = {d.lower() for d in "Mon Tue Wed Thu Fri Sat Sun Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split()}


def _looks_ordered(labels: list[str]) -> bool:
    """Numbers, years, months, weekdays, ranges ('0-9'), quarters: keep their order."""
    if not labels:
        return True
    low = [l.strip().lower() for l in labels]
    if all(l in _MONTHS for l in low) or all(l in _DAYS for l in low):
        return True
    num = re.compile(r"^[<>≤≥~]?\s*[-−+]?\d[\d.,]*\s*(%|[a-z]{0,3})?(\s*[-–to]+\s*[-−+]?\d[\d.,]*\s*(%|[a-z]{0,3})?)?\+?$")
    if all(num.match(l) for l in low):
        return True
    if all(re.match(r"^(q[1-4]|h[12]|fy\s?\d+|\d{4}[-/ ]?(q[1-4]|\d{1,2})?)$", l) for l in low):
        return True
    return False


class BarLayer(Layer):
    def __init__(self, data=None, x=None, y=None, color=None, *, orientation=_AUTO, stack=_AUTO,
                 normalize=False, sort=_AUTO, agg="sum", top=_AUTO, labels=_AUTO, format=None,
                 reference=None, label=None, error=None):
        self.data, self.x, self.y, self.color = data, x, y, color
        self.error = error
        self.orientation, self.stack, self.normalize = orientation, stack, normalize
        self.sort, self.agg, self.top, self.labels, self.fmt = sort, agg, top, labels, format
        self.reference, self.label = reference, label

    # ---------------------------------------------------------------- data
    def prepare(self, chart) -> None:
        self.theme = theme = chart.resolved_theme
        cats, series, xl, yl, ordered = self._resolve()
        self._input_order = list(cats)
        if self.label and len(series) == 1:
            series = [(str(self.label), series[0][1])]
        values = np.vstack([v for _, v in series]) if series else np.zeros((0, 0))
        self.stacked = self.stack is True or bool(self.normalize)
        n_cats = len(cats)
        # fold a long tail into "Other"
        if (is_auto(self.top) and n_cats > 30 and len(series) == 1 and self.agg in ("sum", "count")) or \
                isinstance(self.top, int) and not isinstance(self.top, bool) and n_cats > self.top:
            keep = 25 if is_auto(self.top) else int(self.top)
            order = np.argsort(-np.nan_to_num(values.sum(axis=0)), kind="stable")
            head, tail = order[:keep], order[keep:]
            other = np.nansum(values[:, tail], axis=1, keepdims=True)
            cats = [cats[i] for i in head] + [f"Other ({len(tail)})"]
            values = np.hstack([values[:, head], other])
            ordered = True
        # orientation
        width = chart._opts["width"] if isinstance(chart._opts["width"], (int, float)) else 700
        longest = max((text_width(c, theme.font_size, theme.font_kind) for c in cats), default=0)
        if is_auto(self.orientation):
            per_bar = (width - 80) / max(1, len(cats))
            horizontal = len(cats) > 12 or longest > per_bar * 0.95
        else:
            horizontal = self.orientation in ("h", "horizontal")
        # sorting
        do_sort = self.sort is True or (is_auto(self.sort) and horizontal and not ordered and len(cats) > 2)
        if self.sort in ("ascending", "descending"):
            do_sort = True
        if do_sort:
            totals = np.nan_to_num(values.sum(axis=0))
            order = np.argsort(totals if self.sort == "ascending" else -totals, kind="stable")
            if cats and cats[-1].startswith("Other ("):
                order = np.array([i for i in order if i != len(cats) - 1] + [len(cats) - 1])
            cats = [cats[i] for i in order]
            values = values[:, order]
        if self.normalize:
            tot = np.nansum(np.clip(values, 0, None), axis=0)
            values = values / np.where(tot == 0, 1, tot)
        self.cats, self.values = cats, values
        self.names = [n for n, _ in series]
        self.horizontal = horizontal
        self.x_label, self.y_label = xl, yl
        self.errors = self._errors() if self.error is not None else {}
        if self.reference is not None and not getattr(self, "_ref_added", False):
            self._ref_added = True
            val = float(np.nanmean(values)) if self.reference == "mean" else (
                float(np.nanmedian(values)) if self.reference == "median" else float(self.reference))
            label = f"{'Mean' if self.reference == 'mean' else 'Median' if self.reference == 'median' else 'Target'} " \
                    f"{self._fmt(val)}"
            (chart.vline if horizontal else chart.hline)(val, label)

    def _raw_xy(self):
        """Ungrouped (labels, values) rows, for error statistics."""
        data, x, y = self.data, self.x, self.y
        if is_frame(data) and isinstance(x, str) and isinstance(y, str):
            return to_array(get_column(data, x)), to_array(get_column(data, y))
        if x is not None and y is not None and not isinstance(x, str):
            return to_array(x), to_array(y)
        return None

    def _errors(self) -> dict:
        """{category: (low, high)} absolute bounds for single-series bars."""
        err, cats = self.error, self.cats
        if len(self.names) != 1:
            raise DataError("error= works on single-series bars; for grouped data use one chart per group or facet=.")
        v = self.values[0]
        if isinstance(err, str):
            raw = self._raw_xy()
            if raw is None:
                raise DataError(f"error={err!r} needs raw rows: pass bar(df, x='group', y='value', error={err!r}).")
            names, sd = aggregate(raw[0], raw[1], "std")
            _, n = aggregate(raw[0], raw[1], "count")
            stat = dict(zip(names, sd))
            cnt = dict(zip(names, n))
            k = {"std": lambda c: stat[c], "sem": lambda c: stat[c] / np.sqrt(cnt[c]),
                 "ci": lambda c: 1.96 * stat[c] / np.sqrt(cnt[c])}
            if err not in k:
                raise DataError("error= must be 'std', 'sem', 'ci', an array, a {category: value} dict or (low, high).")
            return {c: (vi - k[err](c), vi + k[err](c)) for c, vi in zip(cats, v) if c in stat}
        if isinstance(err, tuple) and len(err) == 2:
            lo, hi = (np.asarray(list(e.values()) if isinstance(e, dict) else e, float) for e in err)
            order = list(err[0].keys()) if isinstance(err[0], dict) else None
            base = [str(k) for k in order] if order else self._input_order
            return {c: (lo[i], hi[i]) for i, c in enumerate(base)}
        if isinstance(err, dict):
            by_name = {str(k): abs(float(e)) for k, e in err.items()}
            return {c: (vi - by_name[c], vi + by_name[c]) for c, vi in zip(cats, v) if c in by_name}
        e = np.abs(np.asarray(err, float))
        vals = dict(zip(cats, v))
        return {c: (vals[c] - e[i], vals[c] + e[i]) for i, c in enumerate(self._input_order) if c in vals}

    def _resolve(self):
        data, x, y, color, agg = self.data, self.x, self.y, self.color, self.agg
        # {category: number}
        if isinstance(data, dict) and x is None and y is None and data and \
                all(np.ndim(v) == 0 and not isinstance(v, dict) for v in data.values()):
            cats = [str(k) for k in data]
            return cats, [(self.label or "value", as_float(np.array(list(data.values())), "num"))], None, None, \
                _looks_ordered(cats)
        # {series: {category: number}}
        if isinstance(data, dict) and x is None and y is None and data and all(isinstance(v, dict) for v in data.values()):
            cats = list(dict.fromkeys(str(c) for v in data.values() for c in v))
            series = []
            for k, v in data.items():
                sv = {str(a): b for a, b in v.items()}
                series.append((str(k), np.array([float(sv.get(c, np.nan)) for c in cats])))
            return cats, series, None, None, _looks_ordered(cats)
        if is_frame(data) and not (isinstance(data, dict) and x is None):
            cols = columns_of(data)
            if x is None:
                idx = getattr(data, "index", None)
                if idx is not None and type(idx).__name__ != "RangeIndex":
                    xv = to_array(idx)
                    xl = series_name(idx)
                    ycols = [y] if isinstance(y, str) else (list(y) if y else
                                                            [c for c in cols if value_kind(to_array(get_column(data, c))) == "num"])
                    cats = [str(v) for v in xv]
                    return cats, [(str(c), as_float(to_array(get_column(data, c)), "num")) for c in ycols], xl, \
                        (str(ycols[0]) if len(ycols) == 1 else None), _looks_ordered(cats)
                x = next((c for c in cols if value_kind(to_array(get_column(data, c))) == "cat"), None)
                if x is None:
                    raise DataError("Pass x='category column' for a bar chart.")
            xcol = get_column(data, x)
            xv = to_array(xcol)
            order_hint = ordered_categories(xcol)
            if y is None:
                names, vals = aggregate(xv, None, "count")
                return self._ordered(names, [("count", vals)], order_hint, str(x), "count")
            ycols = list(y) if isinstance(y, (list, tuple)) else [y]
            if color is not None:
                gv = to_array(get_column(data, color))
                yv = to_array(get_column(data, ycols[0]))
                return self._pivot(xv, gv, yv, agg, order_hint, str(x), str(ycols[0]), ordered_categories(get_column(data, color)))
            series = []
            names = None
            for c in ycols:
                nm, vals = aggregate(xv, to_array(get_column(data, c)), agg)
                if names is None:
                    names = nm
                series.append((str(c), vals))
            return self._ordered(names, series, order_hint, str(x), str(ycols[0]) if len(ycols) == 1 else None)
        # plain arrays
        if data is not None and y is None and x is None:
            arr = data
            if type(arr).__module__.split(".")[0] == "pandas" and hasattr(arr, "index"):
                cats = [str(v) for v in to_array(arr.index)]
                return cats, [(series_name(arr) or "value", as_float(to_array(arr), "num"))], \
                    series_name(arr.index), series_name(arr), _looks_ordered(cats)
            a = to_array(arr)
            if value_kind(a) == "cat":          # raw labels -> counts
                names, vals = aggregate(a, None, "count")
                order = np.argsort(-vals, kind="stable")
                return [names[i] for i in order], [("count", vals[order])], None, "count", False
            cats = [str(i) for i in range(len(a))]
            return cats, [(self.label or "value", as_float(a, "num"))], None, None, True
        if data is not None and y is None:
            y, data = data, None
        if x is not None and y is not None:
            xv, yv = to_array(x), to_array(y)
            if len(xv) != len(yv):
                raise DataError(f"x has {len(xv)} labels but y has {len(yv)} values.")
            if color is not None:
                return self._pivot(xv, to_array(color), yv, agg, None, series_name(x), series_name(y), None)
            names, vals = aggregate(xv, yv, agg)
            return self._ordered(names, [(series_name(y) or "value", vals)], None, series_name(x), series_name(y))
        raise DataError("Couldn't read bar data. Try lv.bar({'A': 3, 'B': 5}) or lv.bar(df, x='col', y='value').")

    def _ordered(self, names, series, hint, xl, yl):
        if hint:
            pos = {n: i for i, n in enumerate(names)}
            order = [pos[h] for h in hint if h in pos]
            names = [names[i] for i in order]
            series = [(n, v[order]) for n, v in series]
            return names, series, xl, yl, True
        return names, series, xl, yl, _looks_ordered(names)

    def _pivot(self, xv, gv, yv, agg, hint, xl, yl, ghint):
        cx, xn = factorize(xv)
        cg, gn = factorize(gv)
        if ghint:
            pos = {n: i for i, n in enumerate(gn)}
            gn = [h for h in ghint if h in pos] + [n for n in gn if n not in set(ghint)]
            remap = np.array([gn.index(n) for n in [*pos]])
            cg = np.where(cg >= 0, remap[np.maximum(cg, 0)], -1)
        ok = (cx >= 0) & (cg >= 0)
        combo = cx[ok] * len(gn) + cg[ok]
        labels = combo.astype(np.int64)
        names, vals = aggregate(labels, None if yv is None else yv[ok], agg)
        mat = np.full((len(xn), len(gn)), np.nan)
        for n, v in zip(names, vals):
            k = int(n)
            mat[k // len(gn), k % len(gn)] = v
        series = [(g, mat[:, j]) for j, g in enumerate(gn)]
        return self._ordered(xn, series, hint, xl, yl)

    # ---------------------------------------------------------------- domains
    def keys(self):
        return self.names

    def _value_domain(self):
        v = self.values
        if self.stacked:
            pos = np.nansum(np.clip(v, 0, None), axis=0)
            neg = np.nansum(np.clip(v, None, 0), axis=0)
            lo, hi = float(neg.min(initial=0)), float(pos.max(initial=0))
        else:
            with np.errstate(invalid="ignore"):
                lo = float(np.nanmin(v)) if v.size else 0.0
                hi = float(np.nanmax(v)) if v.size else 1.0
        if self.errors:
            bounds = np.array(list(self.errors.values()), float)
            lo, hi = min(lo, float(np.nanmin(bounds))), max(hi, float(np.nanmax(bounds)))
        if self.normalize:
            return Domain("num", 0.0, 1.0, zero=True, nice=False)
        return Domain("num", lo, hi, zero=True, nice=True, extent=(min(lo, 0), max(hi, 0)))

    def _cat_domain(self):
        cats = list(reversed(self.cats)) if self.horizontal else list(self.cats)
        return Domain("cat", categories=cats)

    def x_domain(self):
        return self._value_domain() if self.horizontal else self._cat_domain()

    def y_domain(self):
        return self._cat_domain() if self.horizontal else self._value_domain()

    def axis_labels(self):
        if self.horizontal:
            return (self.y_label if len(self.names) == 1 else None), None
        return None, (self.y_label if len(self.names) == 1 else None)

    def values_for_reference(self, axis):
        return [self.values.ravel()] if (axis == "x") == self.horizontal else []

    def default_size(self, theme):
        if self.horizontal:
            n = len(self.cats) * max(1, 1 if self.stacked else len(self.names))
            h = 70 + n * (24 if len(self.names) == 1 else 16) + 60
            return None, float(min(max(h, 260), 1800))
        return None

    def _fmt(self, v):
        if self.fmt is not None:
            return self.fmt(v) if callable(self.fmt) else (self.fmt.format(v) if "{" in self.fmt else format(v, self.fmt))
        if self.normalize:
            return f"{v:.0%}"
        return format_value(v)

    # ---------------------------------------------------------------- drawing
    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        cat_scale = ctx.ys if self.horizontal else ctx.xs
        val_scale = ctx.xs if self.horizontal else ctx.ys
        k = len(self.names)
        band = cat_scale.bandwidth
        base_px = val_scale.scalar(0.0)
        single = k == 1
        hl = ctx.highlight
        hatch = theme.bar_highlight == "hatch"
        show_labels = self.labels is True or (is_auto(self.labels) and theme.bar_value_labels != "none"
                                              and len(self.cats) * (1 if self.stacked else k) <= 24)
        label_mode = theme.bar_value_labels if theme.bar_value_labels in ("inside", "outside") else "outside"
        pill = theme.bar_radius >= 100
        size = theme.font_size
        thickness = band if (single or self.stacked) else max(1.0, (band - (k - 1) * 2) / k)
        if single and pill:
            thickness = min(thickness, 26.0)
        radius = min(theme.bar_radius, thickness / 2)
        track = pill and single and self.horizontal and not self.normalize
        for ci, cat in enumerate(self.cats):
            pos_i = cat_scale.index[cat]
            b0 = cat_scale.band(pos_i) + (band - thickness) / 2 if (single or self.stacked) else cat_scale.band(pos_i)
            if track:
                tip = val_scale.scalar(max(val_scale.d0, val_scale.d1))
                self._bar(ctx, base_px, tip, b0, thickness, mix(theme.background, theme.ink, 0.07), "both")
            acc_pos = acc_neg = 0.0
            for si, name in enumerate(self.names):
                v = self.values[si, ci]
                if not np.isfinite(v):
                    continue
                if single:
                    if hl:
                        on = cat in hl
                        color = (theme.accent if not hatch else theme.background) if on else theme.muted
                    else:
                        on = False
                        color = theme.muted if hatch else ctx.color(name, si)
                else:
                    color = ctx.color(name, si)
                    on = False
                if self.stacked:
                    start = acc_pos if v >= 0 else acc_neg
                    end_v = start + v
                    if v >= 0:
                        acc_pos = end_v
                    else:
                        acc_neg = end_v
                    p0, p1 = val_scale.scalar(start), val_scale.scalar(end_v)
                    outer = si == max(i for i in range(k) if np.isfinite(self.values[i, ci]) and
                                      (self.values[i, ci] >= 0) == (v >= 0))
                    pos0 = b0
                else:
                    p0, p1 = base_px, val_scale.scalar(v)
                    outer = True
                    pos0 = b0 if (single or self.stacked) else b0 + si * (thickness + 2)
                end = ("both" if pill else (("right" if v >= 0 else "left") if self.horizontal
                                            else ("top" if v >= 0 else "bottom"))) if outer else "none"
                path = self._bar(ctx, p0, p1, pos0, thickness, color, end, radius=radius if outer else 0,
                                 hatch=theme.ink if (single and on and hatch) else None,
                                 stroke=theme.ink if (single and on and hatch) else None,
                                 sep=self.stacked, title=f"{cat} · {name}: {self._fmt(v)}" if k > 1 else f"{cat}: {self._fmt(v)}")
                if single and cat in self.errors:
                    self._whisker(ctx, val_scale, *self.errors[cat], pos0 + thickness / 2, min(thickness * 0.3, 8))
                if show_labels and not self.stacked and not self.errors:
                    self._value_label(ctx, v, p0, p1, pos0, thickness, color, label_mode, size,
                                      bold=(single and on) or pill)
                elif show_labels and self.stacked and abs(p1 - p0) > text_width(self._fmt(v), size - 1, theme.font_kind) + 8 \
                        and (thickness > size + 4):
                    cx = (p0 + p1) / 2
                    cy = pos0 + thickness / 2
                    x, yy = (cx, cy) if self.horizontal else (cy, cx)
                    ctx.scene.add(S.Text(x, yy, self._fmt(v), size - 1, readable_on(color), anchor="middle",
                                         baseline="middle"))

    def _bar(self, ctx, p0, p1, pos0, thick, color, end, radius=None, hatch=None, stroke=None, sep=False, title=None):
        theme = ctx.theme
        lo, hi = min(p0, p1), max(p0, p1)
        length = hi - lo
        if length < 0.3:
            length = 0.3
        r = theme.bar_radius if radius is None else radius
        if self.horizontal:
            x, y, w, h = lo, pos0, length, thick
            e = end if end != "none" else "right"
        else:
            x, y, w, h = pos0, lo, thick, length
            e = end if end != "none" else "top"
        cmds = rounded_bar(x, y, w, h, r if end != "none" else 0, e)
        ctx.scene.add(S.Path(cmds, fill=color, stroke=stroke or (theme.background if sep else None),
                             stroke_width=0.9 if stroke else 1.0, hatch=hatch, title=title))

    def _whisker(self, ctx, scale, lo, hi, c, cap):
        theme = ctx.theme
        a, b = scale.scalar(lo), scale.scalar(hi)
        col = theme.ink if not theme.dark else theme.ink_secondary
        if self.horizontal:
            segs = [(a, c, b, c), (a, c - cap, a, c + cap), (b, c - cap, b, c + cap)]
        else:
            segs = [(c, a, c, b), (c - cap, a, c + cap, a), (c - cap, b, c + cap, b)]
        for x1, y1, x2, y2 in segs:
            ctx.scene.add(S.Line(x1, y1, x2, y2, col, 1.1))

    def _value_label(self, ctx, v, p0, p1, pos0, thick, color, mode, size, bold=False):
        theme = ctx.theme
        text = self._fmt(v)
        tw = text_width(text, size, theme.font_kind, bold)
        cy = pos0 + thick / 2
        length = abs(p1 - p0)
        sign = 1 if p1 >= p0 else -1
        if not self.horizontal:
            sign = -sign  # screen y grows downward
        weight = 600 if bold else 400
        if self.horizontal:
            if mode == "inside" and length > tw + 18 and thick >= size + 2:
                ctx.overlay.append(S.Text(p1 - sign * 10, cy, text, size, readable_on(color), anchor="end" if sign > 0 else "start",
                                     baseline="middle", weight=700))
            else:
                ctx.overlay.append(S.Text(p1 + sign * 6, cy, text, size, theme.ink if bold else theme.ink_secondary,
                                     anchor="start" if sign > 0 else "end", baseline="middle", weight=weight))
        else:
            if thick < tw * 0.8 and thick < 16:
                return
            if mode == "inside" and length > size * 2.2 and thick > tw + 6:
                ctx.overlay.append(S.Text(pos0 + thick / 2, p1 + (size + 4 if v >= 0 else -6), text, size, readable_on(color),
                                     anchor="middle", weight=700))
            else:
                y = p1 - 6 if v >= 0 else p1 + size + 4
                ctx.overlay.append(S.Text(pos0 + thick / 2, y, text, size, theme.ink if bold else theme.ink_secondary,
                                     anchor="middle", weight=weight))

    def legend_items(self, ctx):
        return [LegendItem(n, n, ctx.color(n, i), "square") for i, n in enumerate(self.names)]
