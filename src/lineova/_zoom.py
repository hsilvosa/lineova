"""Smart zoom for the interactive HTML page.

Plain line charts on a number or time axis get a zoom that works on the data, not on the picture:
the wheel, a shift-drag brush and a range strip below the chart change the visible x range, the lines
are redrawn from the data at the new resolution, and the axes get new ticks.

Everything here runs only while ``to_html`` builds the scene (``collecting()``), so SVG, PDF and PNG
output stays byte for byte the same. Ticks are prepared in Python at many densities ("levels") and
the page picks the level that fits the visible range, so the labels follow the same rules as the
static chart.
"""

from __future__ import annotations

import re
import threading
from contextlib import contextmanager

import numpy as np

from . import scene as S
from .reduce import m4

_state = threading.local()

BUDGET = 30_000          # data points embedded in the page, shared by all series of a plot
MAX_TICKS = 600          # finest tick level kept per axis
LEVELS = 18


@contextmanager
def collecting():
    prev = getattr(_state, "on", False)
    _state.on = True
    try:
        yield
    finally:
        _state.on = prev


def active() -> bool:
    return getattr(_state, "on", False)


def eligible(chart, xs, ys) -> bool:
    """Line layers only, linear or time x axis, ordinary y axis, no x-positioned annotations."""
    from .marks.line import LineLayer
    if not chart._layers or not all(type(l) is LineLayer for l in chart._layers):
        return False
    if any(l.band is not None for l in chart._layers):
        return False
    if any(getattr(l, "xy", None) is None or l.xy.x_kind not in ("num", "time") for l in chart._layers):
        return False
    if any(a.get("kind") != "hline" for a in chart._annotations):
        return False
    if getattr(xs, "kind", None) not in ("linear", "time") or getattr(ys, "kind", None) != "linear":
        return False
    if xs.scalar(xs.d1) <= xs.scalar(xs.d0) or ys.scalar(ys.d1) >= ys.scalar(ys.d0):   # reversed axes
        return False
    return True


def cls(tag, kind):
    """CSS class for an axis element of a zoomable plot, or None."""
    return f"{tag}-{kind}" if tag else None


def levels(chart, scale, axis, length, horizontal, theme) -> list:
    """Tick sets from coarse to fine over the full domain: ``[{"v": [...], "l": [...]}, ...]``."""
    out, seen = [], set()
    for j in range(LEVELS):
        vals, labs = chart._ticks(scale, axis, length * 1.5 ** j, horizontal, theme)
        vals = [float(v) for v in vals]
        key = tuple(round(v, 9) for v in vals)
        if len(vals) > MAX_TICKS:
            break
        if key in seen or not vals:
            continue
        seen.add(key)
        out.append({"v": vals, "l": [str(l) for l in labs]})
    chart._ticks(scale, axis, length, horizontal, theme)       # leave the scale in its original state
    return out


def _sig(a: np.ndarray, digits: int = 7) -> list:
    a = np.asarray(a, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        mag = np.where(a == 0, 0, np.floor(np.log10(np.abs(a))))
        q = 10.0 ** (digits - 1 - mag)
        r = np.round(a * q) / q
    r = np.where(np.isfinite(a), r, np.nan)
    return [None if not np.isfinite(v) else float(v) for v in r]


def series_payload(chart, colors, theme) -> list:
    out = []
    layers = chart._layers
    all_series = [(l, i, s) for l in layers for i, s in enumerate(l.xy.series)]
    budget = max(200, BUDGET // max(1, len(all_series)))
    for layer, i, s in all_series:
        x = np.asarray(s.x, float)
        y = np.asarray(s.y, float)
        if len(x) > budget:
            lo, hi = float(x[0]), float(x[-1])
            x, y = m4(x, y, (lo, hi), max(8, budget // 4))
        color = colors.get(s.name) or theme.color(i)
        dash = layer.dash if layer.dash is not None else (theme.dashes[i % len(theme.dashes)] if theme.dashes else None)
        lw = theme.line_width if str(layer.width) == "auto" else float(layer.width)
        muted = color == theme.muted and len(all_series) > 1
        out.append({"name": str(s.name), "color": color, "width": lw * (0.8 if muted else 1.0),
                    "dash": list(dash) if dash else None, "muted": muted,
                    "x": [float(v) for v in x] if layer.xy.x_kind == "time" else _sig(x, 9),
                    "y": _sig(y)})
    # muted series first so highlighted ones sit on top (the same order as the static drawing)
    out.sort(key=lambda d: 0 if d["muted"] else 1)
    return out


def plan(chart, tag, plot, xs, ys, xd_ticks_len, yd_ticks_len, theme, colors, offset, x_rot) -> dict:
    """Metadata the page needs to redraw this plot: all coordinates are local to the chart."""
    from .backends.svg import baseline_shift
    size = theme.font_size
    tl = theme.tick_length if theme.tick_direction == "out" else 0
    base = plot.bottom + offset
    lab_col = theme.ink_secondary if theme.axis_style == "range" else theme.ink_muted
    return {
        "id": tag,
        "plot": [plot.x, plot.y, plot.w, plot.h],
        "x": {"kind": xs.kind, "d0": xs.d0, "d1": xs.d1,
              "levels": levels(chart, xs, chart._x, xd_ticks_len, True, theme), "rot": bool(x_rot)},
        "y": {"d0": ys.d0, "d1": ys.d1, "levels": levels(chart, ys, chart._y, yd_ticks_len, False, theme)},
        "style": {
            "size": size, "label": lab_col, "ink": theme.axis_color, "axis_width": theme.axis_width,
            "axis_style": theme.axis_style, "tick_len": tl, "grid": _grid_style(chart, theme),
            "x_visible": bool(chart._x.visible), "y_visible": bool(chart._y.visible),
            "xt_y": base + (tl if theme.tick_direction == "out" else 0) + 6 + baseline_shift("hanging", size),
            "xk": [base, base + tl] if theme.tick_direction == "out" else None,
            "yt_x": plot.x - offset - (tl if theme.tick_direction == "out" else 0) - 7,
            "yk": [plot.x - offset - tl, plot.x - offset] if theme.tick_direction == "out" else None,
            "dy_mid": baseline_shift("middle", size), "offset": offset,
            "bg": theme.background, "plot_bg": theme.plot_background,
        },
        "series": series_payload(chart, colors, theme),
    }


def _grid_style(chart, theme) -> dict:
    gx = chart._x.grid if chart._x.grid != "auto" else ("x" in theme.grid)
    gy = chart._y.grid if chart._y.grid != "auto" else ("y" in theme.grid)
    return {"x": bool(gx), "y": bool(gy), "color": theme.grid_color, "width": theme.grid_width,
            "dash": list(theme.grid_dash) if theme.grid_dash else None}


def retag(scene, index: int) -> None:
    """Give a child chart's zoom classes a prefix that is unique inside a grid."""
    pat = re.compile(r"^lvz\d+-")

    def walk(ops):
        for op in ops:
            if isinstance(op, S.Group):
                walk(op.ops)
            elif getattr(op, "cls", None) and op.cls.startswith("lvz"):
                op.cls = pat.sub(f"lvz{index}-", op.cls)
    walk(scene.ops)
    for m in scene.meta:
        z = m.get("zoom")
        if z:
            z["id"] = f"lvz{index}"
