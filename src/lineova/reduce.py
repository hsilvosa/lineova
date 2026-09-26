"""Visually lossless data reduction for line-like marks.

A line chart can never show more detail than one vertical stroke per pixel
column. M4 aggregation keeps, for every column, the first, last, minimum and
maximum value, which is exactly what would have been drawn. Result: output size
is ~4 x plot width, whatever the input size, and the picture is identical.
"""

from __future__ import annotations

import numpy as np


def is_sorted(a: np.ndarray) -> bool:
    if len(a) < 2:
        return True
    # chunked to avoid a full-size temporary for huge arrays
    step = 8_000_000
    for s in range(0, len(a) - 1, step):
        seg = a[s:s + step + 1]
        if np.any(seg[1:] < seg[:-1]):
            return False
    return True


def m4(x: np.ndarray, y: np.ndarray, xlim: tuple[float, float], columns: int) -> tuple[np.ndarray, np.ndarray]:
    """Reduce a sorted-by-x series to at most ``4 * columns`` points.

    ``x`` must be float64 and ascending. NaNs in ``y`` are ignored inside a
    column; a column made only of NaNs becomes a gap.
    """
    n = len(x)
    if n <= 4 * columns:
        return x, y
    x0, x1 = xlim
    edges = np.linspace(x0, x1, columns + 1)
    lo = int(np.searchsorted(x, x0, "left"))
    hi = int(np.searchsorted(x, x1, "right"))
    # keep one point beyond each side so the line reaches the plot edge
    lo_keep, hi_keep = max(0, lo - 1), min(n, hi + 1)
    starts = np.searchsorted(x, edges[:-1], "left")
    starts = np.clip(starts, lo, hi)
    ends = np.append(starts[1:], hi)
    nonempty = ends > starts
    s = starts[nonempty]
    e = ends[nonempty]
    if len(s) == 0:
        return x[lo_keep:hi_keep], y[lo_keep:hi_keep]
    yy = y[lo:hi]
    rel = s - lo
    with np.errstate(invalid="ignore"):
        ymin = np.fmin.reduceat(yy, rel)
        ymax = np.fmax.reduceat(yy, rel)
    first_x, first_y = x[s], y[s]
    last_x, last_y = x[e - 1], y[e - 1]
    mid_x = (first_x + last_x) / 2
    k = len(s)
    ox = np.empty(4 * k)
    oy = np.empty(4 * k)
    ox[0::4], oy[0::4] = first_x, first_y
    ox[1::4], oy[1::4] = mid_x, ymin
    ox[2::4], oy[2::4] = mid_x, ymax
    ox[3::4], oy[3::4] = last_x, last_y
    parts_x, parts_y = [ox], [oy]
    if lo_keep < lo:
        parts_x.insert(0, x[lo_keep:lo])
        parts_y.insert(0, y[lo_keep:lo])
    if hi_keep > hi:
        parts_x.append(x[hi:hi_keep])
        parts_y.append(y[hi:hi_keep])
    return np.concatenate(parts_x), np.concatenate(parts_y)


def minmax_envelope(x: np.ndarray, y: np.ndarray, xlim, columns: int):
    """Per-column (x, min, max): used for area fills of huge series."""
    x0, x1 = xlim
    edges = np.linspace(x0, x1, columns + 1)
    starts = np.searchsorted(x, edges[:-1])
    ends = np.append(starts[1:], np.searchsorted(x, x1, "right"))
    ok = ends > starts
    s = starts[ok]
    with np.errstate(invalid="ignore"):
        ymax = np.fmax.reduceat(y, s) if len(s) else np.array([])
        ymin = np.fmin.reduceat(y, s) if len(s) else np.array([])
    xc = (edges[:-1][ok] + edges[1:][ok]) / 2
    return xc, ymin, ymax


def sample_indices(n: int, k: int, seed: int = 0) -> np.ndarray:
    """``k`` sorted random indices out of ``n`` (for estimates on huge data)."""
    if n <= k:
        return np.arange(n)
    rng = np.random.default_rng(seed)
    return np.unique(rng.integers(0, n, size=k))
