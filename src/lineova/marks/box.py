"""Box plots (Tukey), with optional raw points for small groups."""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._color import mix
from .._data import (Chunks, as_float, columns_of, DataError, factorize, get_column, is_auto, is_frame,
                     ordered_categories, series_name, to_array, value_kind)
from .._text import format_value, text_width
from ._base import Domain, DrawContext, Layer

_AUTO = "auto"
MAX_OUTLIERS = 150


def box_stats(v: np.ndarray, whisker: float = 1.5) -> dict:
    v = v[np.isfinite(v)]
    n = len(v)
    if n == 0:
        return {"n": 0}
    q1, med, q3 = np.percentile(v, [25, 50, 75])
    iqr = q3 - q1
    lo_f, hi_f = q1 - whisker * iqr, q3 + whisker * iqr
    inside = (v >= lo_f) & (v <= hi_f)
    lo_w = float(v[inside].min()) if inside.any() else float(q1)
    hi_w = float(v[inside].max()) if inside.any() else float(q3)
    out = v[~inside]
    total_out = len(out)
    if total_out > MAX_OUTLIERS:          # keep the most extreme ones on each side
        low, high = out[out < lo_f], out[out > hi_f]
        k = MAX_OUTLIERS // 2
        low = np.partition(low, k)[:k] if len(low) > k else low
        high = -np.partition(-high, k)[:k] if len(high) > k else high
        out = np.concatenate([low, high])
    return {"n": n, "q1": float(q1), "med": float(med), "q3": float(q3), "lo": lo_w, "hi": hi_w,
            "out": out, "n_out": total_out, "mean": float(v.mean()), "min": float(v.min()), "max": float(v.max())}


class BoxLayer(Layer):
    def __init__(self, data=None, x=None, y=None, *, orientation=_AUTO, points=_AUTO, whisker=1.5,
                 mean=False, color=None, label=None):
        self.data, self.x, self.y = data, x, y
        self.orientation, self.points, self.whisker = orientation, points, whisker
        self.mean, self.color_by, self.label = mean, color, label

    def prepare(self, chart) -> None:
        data, x, y = self.data, self.x, self.y
        groups: list[tuple[str, np.ndarray]] = []
        xl = yl = None
        true_n = None
        if isinstance(data, Chunks):
            # two streaming passes; each group becomes a quantile-preserving sample
            from .. import stream
            if not isinstance(y, str):
                raise DataError("Chunked box/violin plots need y='value column' (and x='group column').")
            res = stream.group_samples(data, y, x if isinstance(x, str) else None)
            from .bar import natural_order
            order = {name: i for i, name in enumerate(natural_order([r[0] for r in res]))}
            res.sort(key=lambda r: order[r[0]])
            groups = [(name, sample) for name, sample, _, _, _ in res]
            true_n = [n for _, _, n, _, _ in res]
            xl, yl = (str(x) if isinstance(x, str) else None), str(y)
        elif isinstance(data, dict):
            groups = [(str(k), as_float(to_array(v), "num")) for k, v in data.items()]
        elif is_frame(data):
            cols = columns_of(data)
            if y is None:
                y = next((c for c in cols if c != x and value_kind(to_array(get_column(data, c))) == "num"), None)
            if y is None:
                raise DataError("No numeric column for the box plot; pass y='column'.")
            vals = as_float(to_array(get_column(data, y)), "num")
            yl = str(y)
            if x is None:
                groups = [(yl, vals)]
            else:
                xcol = get_column(data, x)
                codes, names = factorize(to_array(xcol))
                hint = ordered_categories(xcol)
                order = np.argsort(codes, kind="stable")
                counts = np.bincount(codes[codes >= 0], minlength=len(names))
                start = int((codes < 0).sum())
                for i, nm in enumerate(names):
                    groups.append((nm, vals[order[start:start + counts[i]]]))
                    start += counts[i]
                if hint:
                    pos = {h: i for i, h in enumerate(hint)}
                    groups.sort(key=lambda g: pos.get(g[0], len(pos)))
                xl = str(x)
        else:
            src = data if data is not None else y
            if src is None:
                raise DataError("Nothing to plot: pass values, e.g. lv.box({'A': a, 'B': b}).")
            if isinstance(src, np.ndarray) and src.ndim == 2:
                groups = [(f"{i + 1}", as_float(src[:, i], "num")) for i in range(src.shape[1])]
            elif isinstance(src, (list, tuple)) and src and hasattr(src[0], "__len__"):
                groups = [(str(i + 1), as_float(to_array(v), "num")) for i, v in enumerate(src)]
            elif x is not None:
                codes, names = factorize(to_array(x))
                vals = as_float(to_array(src), "num")
                groups = [(nm, vals[codes == i]) for i, nm in enumerate(names)]
                xl, yl = series_name(x), series_name(src)
            else:
                groups = [(self.label or series_name(src) or "values", as_float(to_array(src), "num"))]
                yl = series_name(src)
        self.groups = groups
        self.stats = [box_stats(v, self.whisker) for _, v in groups]
        if true_n is not None:            # report the real group sizes, not the sample's
            for st, n in zip(self.stats, true_n):
                if st.get("n"):
                    st["n_out"] = int(round(st["n_out"] * n / st["n"]))
                    st["n"] = n
        theme = chart.resolved_theme
        longest = max((text_width(n, theme.font_size, theme.font_kind) for n, _ in groups), default=0)
        width = chart._opts["width"] if isinstance(chart._opts["width"], (int, float)) else 700
        if is_auto(self.orientation):
            self.horizontal = len(groups) > 10 or longest > (width - 80) / max(1, len(groups)) * 0.95
        else:
            self.horizontal = self.orientation in ("h", "horizontal")
        self.x_label, self.y_label = xl, yl
        self.cats = [n for n, _ in groups]

    def keys(self):
        return list(self.cats) if self.color_by == "group" else []

    def _value_domain(self):
        lo = min((s["min"] for s in self.stats if s["n"]), default=0.0)
        hi = max((s["max"] for s in self.stats if s["n"]), default=1.0)
        return Domain("num", lo, hi, nice=True, pad=0.02, extent=(lo, hi))

    def _cat_domain(self):
        return Domain("cat", categories=list(reversed(self.cats)) if self.horizontal else list(self.cats), gap=0.45)

    def x_domain(self):
        return self._value_domain() if self.horizontal else self._cat_domain()

    def y_domain(self):
        return self._cat_domain() if self.horizontal else self._value_domain()

    def axis_labels(self):
        return (self.y_label, None) if self.horizontal else (self.x_label if len(self.cats) > 1 else None, self.y_label)

    def values_for_reference(self, axis):
        want = "x" if self.horizontal else "y"
        return [v for _, v in self.groups] if axis == want else []

    def default_size(self, theme):
        if self.horizontal:
            return None, float(min(max(len(self.cats) * 34 + 140, 260), 1600))
        return None

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        cat = ctx.ys if self.horizontal else ctx.xs
        val = ctx.xs if self.horizontal else ctx.ys
        bw = min(cat.bandwidth, 64.0)
        hl = ctx.highlight
        for i, (name, values) in enumerate(self.groups):
            s = self.stats[i]
            if not s["n"]:
                continue
            if self.color_by == "group":
                color = ctx.color(name, i)
            elif hl:
                color = theme.accent if name in hl else theme.muted
            else:
                color = theme.palette[0] if theme.family != "folio" else theme.ink
            c = cat.center(cat.index[name])
            a, b = c - bw / 2, c + bw / 2
            fill = theme.background if theme.family == "folio" else (None if theme.dark else mix(color, theme.background, 0.78))
            stroke = color if theme.family != "folio" else theme.ink

            def seg(v0, p0, v1, p1, width=1.2, col=stroke):
                if self.horizontal:
                    ctx.scene.add(S.Line(val.scalar(v0), p0, val.scalar(v1), p1, col, width))
                else:
                    ctx.scene.add(S.Line(p0, val.scalar(v0), p1, val.scalar(v1), col, width))

            # raw points for small groups
            show_pts = self.points is True or (is_auto(self.points) and s["n"] <= 60)
            if show_pts:
                v = values[np.isfinite(values)]
                rng = np.random.default_rng(i)
                jit = c + (rng.random(len(v)) - 0.5) * bw * 0.7
                pv = val(v)
                px, py = (pv, jit) if self.horizontal else (jit, pv)
                ctx.scene.add(S.Markers(px, py, "circle", 2.2, fill=color, fill_opacity=0.45, opacity=0.9))
            # whiskers + caps
            seg(s["lo"], c, s["q1"], c)
            seg(s["q3"], c, s["hi"], c)
            seg(s["lo"], c - bw * 0.22, s["lo"], c + bw * 0.22)
            seg(s["hi"], c - bw * 0.22, s["hi"], c + bw * 0.22)
            # box
            q1p, q3p = val.scalar(s["q1"]), val.scalar(s["q3"])
            title = (f"{name}: median {format_value(s['med'])}, IQR {format_value(s['q1'])}–{format_value(s['q3'])}, "
                     f"n = {s['n']:,}")
            if self.horizontal:
                ctx.scene.add(S.Rect(min(q1p, q3p), a, abs(q3p - q1p), bw, fill=fill, stroke=stroke, stroke_width=1.2,
                                     rx=min(3.0, theme.bar_radius), title=title))
            else:
                ctx.scene.add(S.Rect(a, min(q1p, q3p), bw, abs(q3p - q1p), fill=fill, stroke=stroke, stroke_width=1.2,
                                     rx=min(3.0, theme.bar_radius), title=title))
            seg(s["med"], a, s["med"], b, width=2.4, col=theme.ink if not theme.dark else theme.accent)
            if self.mean:
                mp = val.scalar(s["mean"])
                mx, my = (mp, c) if self.horizontal else (c, mp)
                ctx.scene.add(S.Markers(np.array([mx]), np.array([my]), "diamond", 3.5, fill=theme.background,
                                        stroke=theme.ink, stroke_width=1.2))
            # outliers
            if len(s["out"]) and not show_pts:
                ov = val(s["out"])
                cc = np.full(len(ov), c)
                px, py = (ov, cc) if self.horizontal else (cc, ov)
                ctx.scene.add(S.Markers(px, py, "circle", 2.4, fill=theme.background, stroke=stroke, stroke_width=1.0))
