"""Bullet charts: a value against a target and qualitative ranges, in the space of a bar."""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._color import mix
from .._data import DataError, columns_of, get_column, is_frame, to_array
from .._text import format_value, text_width
from ._base import DrawContext, Layer

_AUTO = "auto"


class BulletLayer(Layer):
    """Rows of ``{"label": ..., "value": ..., "target": ..., "ranges": [poor_max, ok_max, good_max]}`` as a list
    of dicts, a ``{label: (value, target)}`` / ``{label: (value, target, ranges)}`` dict, or a DataFrame with
    label, value and target columns (``ranges=`` applies to every row then). Each row has its own scale,
    from 0 to the largest range (or value). ``lower_is_better=True`` shades the ranges the other way round.
    """

    cartesian = False
    own_legend = True

    def __init__(self, data=None, *, ranges=None, lower_is_better=False, format=None, shared=False):
        self.data, self.ranges, self.lower_is_better, self.fmt, self.shared = data, ranges, lower_is_better, format, shared

    def prepare(self, chart) -> None:
        data = self.data
        rows = []
        if isinstance(data, dict):
            for k, v in data.items():
                v = tuple(v) if isinstance(v, (list, tuple)) else (v,)
                rows.append({"label": str(k), "value": v[0], "target": v[1] if len(v) > 1 else None,
                             "ranges": v[2] if len(v) > 2 else None})
        elif is_frame(data) and not isinstance(data, list):
            names = [str(c) for c in columns_of(data)]
            low = {n.lower(): n for n in names}
            lab = low.get("label") or low.get("name") or names[0]
            val = low.get("value") or names[1]
            tgt = low.get("target") or (names[2] if len(names) > 2 else None)
            lv_ = to_array(get_column(data, lab))
            vv = np.asarray(to_array(get_column(data, val)), float)
            tv = np.asarray(to_array(get_column(data, tgt)), float) if tgt else np.full(len(vv), np.nan)
            for a, b, c in zip(lv_.tolist(), vv.tolist(), tv.tolist()):
                rows.append({"label": str(a), "value": b, "target": None if np.isnan(c) else c, "ranges": None})
        elif isinstance(data, (list, tuple)):
            for r in data:
                if not isinstance(r, dict):
                    raise DataError("Bullet rows are dicts with label, value, target and ranges.")
                rows.append({"label": str(r.get("label", "")), "value": r.get("value"), "target": r.get("target"),
                             "ranges": r.get("ranges")})
        else:
            raise DataError("Pass a list of dicts, a {label: (value, target)} dict or a DataFrame.")
        if not rows:
            raise DataError("No rows to draw.")
        for r in rows:
            if r["value"] is None or not np.isfinite(r["value"]):
                raise DataError(f"Row {r['label']!r} has no numeric value.")
            rg = r["ranges"] if r["ranges"] is not None else self.ranges
            if rg is not None:
                rg = sorted(float(v) for v in rg)
            r["ranges"] = rg
            top = max([float(r["value"]), float(r["target"]) if r["target"] is not None else 0.0] + (rg or [0.0]))
            r["max"] = top * 1.05 if top > 0 else 1.0
        if self.shared:
            m = max(r["max"] for r in rows)
            for r in rows:
                r["max"] = m
        self.rows = rows

    def keys(self):
        return []

    def default_size(self, theme):
        return 640.0, float(min(900, max(160, len(self.rows) * 52 + 90)))

    def _fmt(self, v):
        if self.fmt is not None:
            return self.fmt(v) if callable(self.fmt) else (self.fmt.format(v) if "{" in self.fmt else format(v, self.fmt))
        return format_value(v)

    def draw(self, ctx: DrawContext) -> None:
        theme, plot = ctx.theme, ctx.plot
        size = theme.font_size
        n = len(self.rows)
        lab_w = max(text_width(r["label"], size, theme.font_kind, True) for r in self.rows) + 14
        val_w = max(text_width(self._fmt(r["value"]), size, theme.font_kind, True) for r in self.rows) + 12
        x0, x1 = plot.x + lab_w, plot.right - val_w
        pitch = plot.h / n
        bar_h = min(26.0, pitch * 0.55)
        tint = [mix(theme.background, theme.ink, t) for t in (0.10, 0.18, 0.28)]
        if self.lower_is_better:
            tint = tint[::-1]
        for i, r in enumerate(self.rows):
            cy = plot.y + pitch * (i + 0.5)
            ctx.scene.add(S.Text(plot.x + lab_w - 8, cy, r["label"], size, theme.ink, anchor="end", baseline="middle",
                                 weight=600))
            sc = (x1 - x0) / r["max"]
            rg = r["ranges"]
            if rg:
                prev = 0.0
                for k, edge in enumerate(rg):
                    ctx.scene.add(S.Rect(x0 + prev * sc, cy - bar_h / 2, (edge - prev) * sc, bar_h,
                                         fill=tint[min(k, 2) if len(rg) <= 3 else int(k * 3 / len(rg))]))
                    prev = edge
            else:
                ctx.scene.add(S.Rect(x0, cy - bar_h / 2, r["max"] / 1.05 * sc, bar_h, fill=tint[0]))
            vcol = theme.palette[0] if theme.family != "folio" else theme.ink
            ctx.scene.add(S.Rect(x0, cy - bar_h * 0.17, float(r["value"]) * sc, bar_h * 0.34, fill=vcol,
                                 title=f"{r['label']}: {self._fmt(r['value'])}"
                                       + (f" (target {self._fmt(r['target'])})" if r["target"] is not None else "")))
            if r["target"] is not None:
                tx = x0 + float(r["target"]) * sc
                ctx.scene.add(S.Line(tx, cy - bar_h * 0.38, tx, cy + bar_h * 0.38, theme.ink, 2.2))
            ctx.scene.add(S.Text(x1 + 8, cy, self._fmt(r["value"]), size, theme.ink, baseline="middle", weight=600))
            # scale ticks at 0 and max
            ctx.scene.add(S.Text(x0, cy + bar_h / 2 + size * 0.9, "0", size - 2, theme.ink_muted, anchor="start"))
            ctx.scene.add(S.Text(x1, cy + bar_h / 2 + size * 0.9, self._fmt(r["max"] / 1.05), size - 2,
                                 theme.ink_muted, anchor="end"))
