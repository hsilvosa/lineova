"""Geometry helpers shared by marks."""

from __future__ import annotations

import numpy as np


def finite_runs(xs: np.ndarray, ys: np.ndarray) -> list[tuple[int, int]]:
    ok = np.isfinite(xs) & np.isfinite(ys)
    if ok.all():
        return [(0, len(xs))] if len(xs) else []
    idx = np.flatnonzero(np.diff(np.concatenate(([0], ok.view(np.int8), [0]))))
    return [(a, b) for a, b in zip(idx[::2], idx[1::2]) if b > a]


def monotone_path(xs: np.ndarray, ys: np.ndarray) -> list:
    """Smooth path through the points that never overshoots (Fritsch–Carlson).

    Needs strictly increasing x; otherwise falls back to straight segments.
    """
    cmds: list = []
    for a, b in finite_runs(xs, ys):
        x, y = xs[a:b], ys[a:b]
        n = len(x)
        cmds.append(("M", x[0], y[0]))
        if n == 1:
            cmds.append(("L", x[0] + 0.01, y[0]))
            continue
        dx = np.diff(x)
        if np.any(dx <= 0):
            cmds.extend(("L", xi, yi) for xi, yi in zip(x[1:], y[1:]))
            continue
        d = np.diff(y) / dx
        m = np.empty(n)
        m[0], m[-1] = d[0], d[-1]
        m[1:-1] = (d[:-1] + d[1:]) / 2
        flat = np.concatenate(([False], (d[:-1] * d[1:]) <= 0, [False]))
        m[flat] = 0
        for i in range(n - 1):
            if d[i] == 0:
                m[i] = m[i + 1] = 0
                continue
            a_, b_ = m[i] / d[i], m[i + 1] / d[i]
            s = a_ * a_ + b_ * b_
            if s > 9:
                t = 3 / np.sqrt(s)
                m[i], m[i + 1] = t * a_ * d[i], t * b_ * d[i]
        for i in range(n - 1):
            h = dx[i] / 3
            cmds.append(("C", x[i] + h, y[i] + m[i] * h, x[i + 1] - h, y[i + 1] - m[i + 1] * h, x[i + 1], y[i + 1]))
    return cmds


def rounded_bar(x: float, y: float, w: float, h: float, r: float, end: str) -> list:
    """Rectangle with rounded corners only on the data end.

    ``end`` is where the value is: 'top', 'bottom', 'right', 'left', or 'both'
    (pill: round the whole thing).
    """
    r = max(0.0, min(r, w / 2 if end in ("top", "bottom", "both") else h / 2, h if end in ("top", "bottom") else w))
    if end == "both":
        r = min(w, h) / 2
    x1, y1 = x + w, y + h
    if r <= 0.01:
        return [("M", x, y), ("L", x1, y), ("L", x1, y1), ("L", x, y1), ("Z",)]
    if end == "top":
        return [("M", x, y1), ("L", x, y + r), ("Q", x, y, x + r, y), ("L", x1 - r, y), ("Q", x1, y, x1, y + r),
                ("L", x1, y1), ("Z",)]
    if end == "bottom":
        return [("M", x, y), ("L", x1, y), ("L", x1, y1 - r), ("Q", x1, y1, x1 - r, y1), ("L", x + r, y1),
                ("Q", x, y1, x, y1 - r), ("Z",)]
    if end == "right":
        return [("M", x, y), ("L", x1 - r, y), ("Q", x1, y, x1, y + r), ("L", x1, y1 - r), ("Q", x1, y1, x1 - r, y1),
                ("L", x, y1), ("Z",)]
    if end == "left":
        return [("M", x1, y), ("L", x1, y1), ("L", x + r, y1), ("Q", x, y1, x, y1 - r), ("L", x, y + r),
                ("Q", x, y, x + r, y), ("Z",)]
    # both: pill
    if w >= h:
        return [("M", x + r, y), ("L", x1 - r, y), ("Q", x1, y, x1, y + r), ("Q", x1, y1, x1 - r, y1),
                ("L", x + r, y1), ("Q", x, y1, x, y1 - r), ("Q", x, y, x + r, y), ("Z",)]
    return [("M", x, y + r), ("Q", x, y, x + r, y), ("Q", x1, y, x1, y + r), ("L", x1, y1 - r),
            ("Q", x1, y1, x + r, y1), ("Q", x, y1, x, y1 - r), ("Z",)]


def arc(cx: float, cy: float, r: float, a0: float, a1: float, move: bool = True) -> list:
    """Circular arc from angle a0 to a1 (radians, screen coordinates: 0 = 3 o'clock, clockwise positive)
    as cubic Béziers of at most 90° each."""
    cmds: list = []
    n = max(1, int(np.ceil(abs(a1 - a0) / (np.pi / 2) - 1e-9)))
    step = (a1 - a0) / n
    k = 4 / 3 * np.tan(step / 4)
    x0, y0 = cx + r * np.cos(a0), cy + r * np.sin(a0)
    if move:
        cmds.append(("M", x0, y0))
    for i in range(n):
        t0 = a0 + i * step
        t1 = t0 + step
        x1, y1 = cx + r * np.cos(t1), cy + r * np.sin(t1)
        c1 = (x0 - k * r * np.sin(t0), y0 + k * r * np.cos(t0))
        c2 = (x1 + k * r * np.sin(t1), y1 - k * r * np.cos(t1))
        cmds.append(("C", c1[0], c1[1], c2[0], c2[1], x1, y1))
        x0, y0 = x1, y1
    return cmds


def wedge(cx: float, cy: float, r_out: float, r_in: float, a0: float, a1: float) -> list:
    """Pie slice (r_in = 0) or donut segment as a closed path."""
    cmds = arc(cx, cy, r_out, a0, a1)
    if r_in > 0:
        cmds.append(("L", cx + r_in * np.cos(a1), cy + r_in * np.sin(a1)))
        cmds += arc(cx, cy, r_in, a1, a0, move=False)
    else:
        cmds.append(("L", cx, cy))
    cmds.append(("Z",))
    return cmds


def spread_labels(ys: list, gap: float, lo: float, hi: float) -> list:
    """Move label positions apart so neighbours are at least ``gap`` apart, staying inside [lo, hi]."""
    if not ys:
        return []
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    pos = [ys[i] for i in order]
    for i in range(1, len(pos)):
        pos[i] = max(pos[i], pos[i - 1] + gap)
    over = pos[-1] - hi
    if over > 0:
        pos[-1] -= over
        for i in range(len(pos) - 2, -1, -1):
            pos[i] = min(pos[i], pos[i + 1] - gap)
    under = lo - pos[0]
    if under > 0:
        pos = [p + under for p in pos]
    out = [0.0] * len(ys)
    for k, i in enumerate(order):
        out[i] = pos[k]
    return out
