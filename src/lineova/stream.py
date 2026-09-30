"""Streaming reductions over ``Chunks``: each pass reads the data once, memory stays bounded."""

from __future__ import annotations

import numpy as np

from ._data import Chunks, DataError, _chunk_column
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


def points(chunks: Chunks, x, y, bins: int = GRID_2D, xlim=None, ylim=None):
    """Two passes: extent, then a fine 2-D histogram. Returns bin centres and counts (non-empty bins).

    ``xlim``/``ylim`` (from the chart's axis ranges) focus the grid on the visible area, so a long
    tail of outliers doesn't make the grid coarse.
    """
    lo, hi, n = extent(chunks, x, y)
    for i, lim in enumerate((xlim, ylim)):
        if lim is not None:
            lo[i] = lim[0] if lim[0] is not None else lo[i]
            hi[i] = lim[1] if lim[1] is not None else hi[i]
    sx = bins / ((hi[0] - lo[0]) or 1.0)
    sy = bins / ((hi[1] - lo[1]) or 1.0)
    grid = np.zeros(bins * bins, dtype=np.int64)
    for xc, yc in chunks.columns(x, y):
        fx = (xc - lo[0]) * sx
        fy = (yc - lo[1]) * sy
        ok = np.isfinite(fx) & np.isfinite(fy) & (fx >= 0) & (fx <= bins) & (fy >= 0) & (fy <= bins)
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


# ---------------------------------------------------------------- grouped aggregation

def _raw(chunk, name) -> np.ndarray:
    """A column as-is (strings stay strings): for group keys."""
    from ._data import get_column, to_array
    if hasattr(chunk, "column") and hasattr(chunk, "schema"):            # pyarrow
        return np.asarray(chunk.column(name).to_numpy(zero_copy_only=False))
    return np.asarray(to_array(get_column(chunk, name)))


def _codes(chunk, keys):
    """Combined integer code per row for the key columns, and the key tuples of each code."""
    from ._data import factorize
    combined = None
    names_per = []
    for k in keys:
        c, names = factorize(_raw(chunk, k))
        names_per.append(names)
        combined = c.copy() if combined is None else np.where((combined < 0) | (c < 0), -1,
                                                             combined * max(len(names), 1) + c)
    ok = combined >= 0
    uniq, inv = np.unique(combined[ok], return_inverse=True)
    tuples = []
    sizes = [max(len(n), 1) for n in names_per]
    for u in uniq.tolist():
        parts = []
        for size, names in zip(reversed(sizes), reversed(names_per)):
            parts.append(names[u % size])
            u //= size
        tuples.append(tuple(reversed(parts)))
    return ok, inv, tuples


def group_stats(chunks: Chunks, keys, value=None, need_minmax: bool = False) -> dict:
    """One pass: per key tuple, ``[count, sum, sum of squares, min, max]`` of ``value`` (rows if None).

    Order of first appearance is kept. Memory is one small array per group.
    """
    acc: dict = {}
    seen_rows = 0
    for chunk in chunks:
        ok, inv, tuples = _codes(chunk, keys)
        k = len(tuples)
        if value is not None:
            v = _chunk_column(chunk, value)[ok]
            fin = np.isfinite(v)
            inv_f, v = inv[fin], v[fin]
        else:
            inv_f, v = inv, None
        seen_rows += int(ok.sum())
        cnt = np.bincount(inv_f, minlength=k).astype(np.float64)
        s = np.bincount(inv_f, weights=v, minlength=k) if v is not None else cnt
        ss = np.bincount(inv_f, weights=v * v, minlength=k) if v is not None else cnt
        if need_minmax and v is not None:
            mn = np.full(k, np.inf)
            mx = np.full(k, -np.inf)
            np.minimum.at(mn, inv_f, v)
            np.maximum.at(mx, inv_f, v)
        else:
            mn = mx = np.full(k, np.nan)
        for i, t in enumerate(tuples):
            a = acc.get(t)
            if a is None:
                acc[t] = np.array([cnt[i], s[i], ss[i], mn[i], mx[i]])
            else:
                a[0] += cnt[i]
                a[1] += s[i]
                a[2] += ss[i]
                if need_minmax:
                    a[3] = min(a[3], mn[i])
                    a[4] = max(a[4], mx[i])
    if seen_rows == 0:
        raise DataError("The chunked source produced no rows with those columns.")
    return acc


def finish(stats: np.ndarray, agg: str) -> float:
    n, s, ss, mn, mx = stats
    if agg == "count":
        return n
    if agg == "sum":
        return s
    if agg == "mean":
        return s / n if n else np.nan
    if agg == "min":
        return mn
    if agg == "max":
        return mx
    if agg == "std":
        return float(np.sqrt(max(ss / n - (s / n) ** 2, 0.0) * n / (n - 1))) if n > 1 else np.nan
    raise DataError(f"Chunked data supports agg='sum', 'mean', 'count', 'min', 'max' or 'std'; got {agg!r}.")


def group_samples(chunks: Chunks, value, key=None, bins: int = 4096, k: int = 20_000):
    """Distribution per group in two passes, for box plots and violins of data larger than memory.

    Pass 1 finds each group's range and size, pass 2 fills a fine histogram per group. Each group is
    then represented by ``k`` values placed at evenly spaced quantiles of that histogram (plus the true
    minimum and maximum), so percentiles are exact to 1/``bins`` of the range.
    Returns ``[(name, sample, n, min, max)]``.
    """
    keys = [key] if key is not None else []
    if keys:
        st = group_stats(chunks, keys, value, need_minmax=True)
    else:
        lo, hi, n = extent(chunks, value)
        st = {("values",): np.array([n, 0, 0, lo[0], hi[0]])}
    names = list(st)
    index = {t: i for i, t in enumerate(names)}
    lo = np.array([st[t][3] for t in names])
    hi = np.array([st[t][4] for t in names])
    span = np.where(hi > lo, hi - lo, 1.0)
    hist = np.zeros((len(names), bins))
    for chunk in chunks:
        v = _chunk_column(chunk, value)
        if keys:
            ok, inv, tuples = _codes(chunk, keys)
            g = np.array([index.get(t, -1) for t in tuples], dtype=np.int64)[inv] if len(tuples) else inv
            v = v[ok]
        else:
            g = np.zeros(len(v), dtype=np.int64)
        fin = np.isfinite(v) & (g >= 0)
        g, v = g[fin], v[fin]
        b = np.clip(((v - lo[g]) / span[g] * bins).astype(np.int64), 0, bins - 1)
        hist += np.bincount(g * bins + b, minlength=len(names) * bins).reshape(len(names), bins)
    out = []
    for i, t in enumerate(names):
        h = hist[i]
        n = h.sum()
        if n == 0:
            continue
        cdf = np.concatenate([[0.0], np.cumsum(h)]) / n
        edges = lo[i] + np.arange(bins + 1) / bins * span[i]
        m = int(min(k, n))
        p = (np.arange(m) + 0.5) / m
        sample = np.interp(p, cdf, edges)
        sample[0], sample[-1] = lo[i], hi[i]
        out.append((" · ".join(t), sample, int(n), float(lo[i]), float(hi[i])))
    return out
