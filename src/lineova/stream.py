"""Streaming reductions over ``Chunks``: each pass reads the data once, memory stays bounded."""

from __future__ import annotations

import numpy as np

from ._data import Chunks, DataError
from .reduce import m4

LINE_COLUMNS = 16384          # enough for any plot up to ~8000 px wide at 2x
GRID_2D = 2048


def extent(chunks: Chunks, *names):
    """(mins, maxs, count) of the named columns, ignoring NaN."""
    k = len(names)
    lo = np.full(k, np.inf)
    hi = np.full(k, -np.inf)
    n = 0
    for cols in chunks.columns(*names):
        n += len(cols[0])
        for i, a in enumerate(cols):
            if len(a):
                with np.errstate(invalid="ignore"):
                    amin, amax = np.nanmin(a), np.nanmax(a)
                if np.isfinite(amin):
                    lo[i], hi[i] = min(lo[i], amin), max(hi[i], amax)
    if n == 0:
        raise DataError("The chunked source produced no rows.")
    return lo, hi, n


def line(chunks: Chunks, x, y, columns: int = LINE_COLUMNS):
    """Two passes: extent, then per-chunk M4 on a shared column grid. Chunks must be in x order."""
    if x is None:
        # no x column: use the running row number
        lo, hi, n = extent(chunks, y)
        xs, ys, offset = [], [], 0
        for (yc,) in chunks.columns(y):
            xc = np.arange(offset, offset + len(yc), dtype=np.float64)
            offset += len(yc)
            rx, ry = m4(xc, yc, (0.0, float(n - 1)), columns)
            xs.append(rx)
            ys.append(ry)
        x_all, y_all = np.concatenate(xs), np.concatenate(ys)
        return (*m4(x_all, y_all, (0.0, float(n - 1)), columns), n)
    lo, hi, n = extent(chunks, x, y)
    xs, ys = [], []
    last = -np.inf
    for xc, yc in chunks.columns(x, y):
        if len(xc) and (xc[0] < last or np.any(np.diff(xc) < 0)):
            raise DataError("Chunked line data must arrive sorted by x.")
        if len(xc):
            last = xc[-1]
        rx, ry = m4(xc, yc, (lo[0], hi[0]), columns)
        xs.append(rx)
        ys.append(ry)
    # small chunks pass through M4 unreduced, so reduce once more over the whole range
    x_all, y_all = np.concatenate(xs), np.concatenate(ys)
    return (*m4(x_all, y_all, (lo[0], hi[0]), columns), n)


def points(chunks: Chunks, x, y, bins: int = GRID_2D):
    """Two passes: extent, then a fine 2-D histogram. Returns bin centres and counts (non-empty bins)."""
    lo, hi, n = extent(chunks, x, y)
    sx = bins / ((hi[0] - lo[0]) or 1.0)
    sy = bins / ((hi[1] - lo[1]) or 1.0)
    grid = np.zeros(bins * bins, dtype=np.int64)
    for xc, yc in chunks.columns(x, y):
        fx = (xc - lo[0]) * sx
        fy = (yc - lo[1]) * sy
        ok = np.isfinite(fx) & np.isfinite(fy)
        ix = np.clip(fx[ok].astype(np.int64), 0, bins - 1)
        iy = np.clip(fy[ok].astype(np.int64), 0, bins - 1)
        grid += np.bincount(iy * bins + ix, minlength=bins * bins)
    nz = np.flatnonzero(grid)
    cx = lo[0] + (nz % bins + 0.5) / sx
    cy = lo[1] + (nz // bins + 0.5) / sy
    # keep the true extremes on the axes
    cx = np.clip(cx, lo[0], hi[0])
    cy = np.clip(cy, lo[1], hi[1])
    return cx, cy, grid[nz].astype(np.float64), n, (lo, hi)


def first_kind(chunks: Chunks, name) -> str:
    """'time' if the column holds dates (checked on the first chunk), else 'num'."""
    from ._data import get_column, to_array, value_kind
    for chunk in chunks:
        if hasattr(chunk, "column") and hasattr(chunk, "schema"):
            a = np.asarray(chunk.column(name).to_numpy(zero_copy_only=False))
        else:
            a = to_array(get_column(chunk, name)) if name is not None else np.asarray(chunk)
        return value_kind(np.asarray(a))
    return "num"
