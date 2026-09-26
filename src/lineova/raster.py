"""Aggregation and rasterisation for very large datasets.

Drawing ten million circles is slow and produces an unreadable blob, so above a
threshold the library aggregates points into a pixel grid instead. Cost is one
vectorised pass over the data (processed in chunks to bound memory), and the
output size depends only on the plot size, never on the number of points.
"""

from __future__ import annotations

import struct
import zlib

import numpy as np

CHUNK = 4_000_000


# --------------------------------------------------------------------------- PNG

def encode_png(rgba: np.ndarray, level: int = 6) -> bytes:
    """Encode an ``(h, w, 4)`` uint8 array as PNG (no dependencies)."""
    a = np.ascontiguousarray(rgba, dtype=np.uint8)
    if a.ndim != 3 or a.shape[2] not in (3, 4):
        raise ValueError("expected an (h, w, 3|4) uint8 array")
    h, w, c = a.shape
    raw = np.empty((h, w * c + 1), dtype=np.uint8)
    raw[:, 0] = 0  # filter type: none
    raw[:, 1:] = a.reshape(h, w * c)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6 if c == 4 else 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw.tobytes(), level)) + chunk(b"IEND", b""))


# --------------------------------------------------------------------------- binning

def bin_points(x, y, xlim, ylim, shape, *, categories=None, n_categories: int = 0,
               x_transform=None, y_transform=None) -> np.ndarray:
    """Count points per pixel.

    Returns ``(rows, cols)`` counts, or ``(n_categories, rows, cols)`` when
    ``categories`` (integer codes) is given. Row 0 is the top of the plot.
    NaN and out-of-range points are ignored.
    """
    rows, cols = shape
    x0, x1 = xlim
    y0, y1 = ylim
    sx = cols / (x1 - x0) if x1 != x0 else 0.0
    sy = rows / (y1 - y0) if y1 != y0 else 0.0
    ncell = rows * cols
    size = ncell * max(1, n_categories) if categories is not None else ncell
    total = np.zeros(size, dtype=np.int64)
    n = len(x)
    for s in range(0, n, CHUNK):
        xc = np.asarray(x[s:s + CHUNK], dtype=np.float64)
        yc = np.asarray(y[s:s + CHUNK], dtype=np.float64)
        if x_transform is not None:
            xc = x_transform(xc)
        if y_transform is not None:
            yc = y_transform(yc)
        fx = (xc - x0) * sx
        fy = (y1 - yc) * sy
        ok = (fx >= 0) & (fx < cols) & (fy >= 0) & (fy < rows)
        # points exactly on the upper edge belong to the last pixel
        idx = fy[ok].astype(np.int64) * cols + fx[ok].astype(np.int64)
        if categories is not None:
            cc = np.asarray(categories[s:s + CHUNK], dtype=np.int64)[ok]
            idx = cc * ncell + idx
        total += np.bincount(idx, minlength=size)
    if categories is not None:
        return total.reshape(max(1, n_categories), rows, cols)
    return total.reshape(rows, cols)


def bin_segments(x0, y0, x1, y1, xlim, ylim, shape, samples_per_px: float = 1.0,
                 budget: int = 12_000_000) -> np.ndarray:
    """Rasterise many straight segments (network edges) by sampling along each one.

    The total number of samples is capped at ``budget``; long edges are then
    sampled more sparsely, which keeps the cost bounded for any edge count.
    """
    rows, cols = shape
    sx = cols / (xlim[1] - xlim[0])
    sy = rows / (ylim[1] - ylim[0])
    total_len = float(np.hypot((np.asarray(x1) - np.asarray(x0)) * sx, (np.asarray(y1) - np.asarray(y0)) * sy).sum())
    if total_len * samples_per_px > budget:
        samples_per_px = budget / total_len
    grid = np.zeros(rows * cols, dtype=np.float64)
    n = len(x0)
    step = max(1, CHUNK // 64)
    for s in range(0, n, step):
        ax = (np.asarray(x0[s:s + step]) - xlim[0]) * sx
        ay = (ylim[1] - np.asarray(y0[s:s + step])) * sy
        bx = (np.asarray(x1[s:s + step]) - xlim[0]) * sx
        by = (ylim[1] - np.asarray(y1[s:s + step])) * sy
        length = np.hypot(bx - ax, by - ay)
        k = np.maximum(2, np.ceil(length * samples_per_px)).astype(np.int64)
        seg = np.repeat(np.arange(len(k)), k)
        start = np.repeat(np.cumsum(k) - k, k)
        t = (np.arange(len(seg)) - start) / np.maximum(1, k[seg] - 1)
        px = ax[seg] + (bx[seg] - ax[seg]) * t
        py = ay[seg] + (by[seg] - ay[seg]) * t
        ok = (px >= 0) & (px < cols) & (py >= 0) & (py < rows)
        idx = py[ok].astype(np.int64) * cols + px[ok].astype(np.int64)
        grid += np.bincount(idx, minlength=rows * cols)
    return grid.reshape(rows, cols)


# --------------------------------------------------------------------------- shading

def normalize(counts: np.ndarray, how: str = "eq_hist") -> np.ndarray:
    """Map counts to 0..1 intensity. Zero stays zero.

    ``eq_hist`` (histogram equalisation) reveals structure at every density,
    ``log`` is smoother, ``linear`` is literal.
    """
    c = counts.astype(np.float64, copy=False)
    out = np.zeros_like(c)
    nz = c > 0
    if not nz.any():
        return out
    vals = c[nz]
    if how == "linear":
        out[nz] = vals / vals.max()
    elif how == "log":
        out[nz] = np.log1p(vals) / np.log1p(vals.max())
    elif how == "eq_hist":
        uniq, inv, freq = np.unique(vals, return_inverse=True, return_counts=True)
        if len(uniq) == 1:
            out[nz] = 1.0
        else:
            cdf = np.cumsum(freq).astype(np.float64)
            cdf = (cdf - cdf[0]) / (cdf[-1] - cdf[0])
            out[nz] = cdf[inv]
    else:
        raise ValueError(f"unknown normalisation {how!r}")
    return out


def spread(alpha: np.ndarray, radius: int = 1) -> np.ndarray:
    """Grow isolated pixels so sparse regions stay visible (max filter)."""
    out = alpha.copy()
    rows, cols = alpha.shape
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx == 0 and dy == 0:
                continue
            ys = slice(max(0, dy), rows + min(0, dy))
            yd = slice(max(0, -dy), rows + min(0, -dy))
            xs = slice(max(0, dx), cols + min(0, dx))
            xd = slice(max(0, -dx), cols + min(0, -dx))
            np.maximum(out[yd, xd], alpha[ys, xs] * 0.85, out=out[yd, xd])
    return out


def shade(counts: np.ndarray, colors: np.ndarray, how: str = "eq_hist",
          min_alpha: float = 0.28, spread_px: int | str = "auto") -> np.ndarray:
    """Turn counts into an RGBA image.

    ``counts`` is ``(rows, cols)`` with ``colors`` shape ``(3,)`` (0..1), or
    ``(k, rows, cols)`` with ``colors`` ``(k, 3)``: pixels then take the
    count-weighted mix of the category colours.
    """
    if counts.ndim == 2:
        total = counts
        rgb = np.broadcast_to(np.asarray(colors, float)[:3], counts.shape + (3,))
    else:
        total = counts.sum(axis=0)
        w = counts.astype(np.float64) / np.maximum(total, 1)
        rgb = np.einsum("kyx,kc->yxc", w, np.asarray(colors, float))
    t = normalize(total, how)
    alpha = np.where(total > 0, min_alpha + (1 - min_alpha) * t, 0.0)
    if spread_px == "auto":
        coverage = float((total > 0).mean())
        spread_px = 1 if coverage < 0.08 else 0
    if spread_px:
        r = int(spread_px)
        a0 = alpha
        alpha = spread(a0, r)
        if counts.ndim == 3:
            # spread premultiplied colour too, so grown pixels take their neighbour's hue
            prem = rgb * a0[..., None]
            prem = np.stack([spread(prem[..., c], r) for c in range(3)], axis=-1)
            rgb = np.clip(prem / np.maximum(alpha[..., None], 1e-9), 0, 1)
    img = np.empty(total.shape + (4,), dtype=np.uint8)
    img[..., :3] = np.clip(rgb * 255 + 0.5, 0, 255).astype(np.uint8)
    img[..., 3] = np.clip(alpha * 255 + 0.5, 0, 255).astype(np.uint8)
    return img


def colormap(values: np.ndarray, lut: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    """Map a 2-D array through a ``(256, 3)`` LUT. NaN becomes transparent."""
    v = np.asarray(values, dtype=np.float64)
    span = (vmax - vmin) or 1.0
    t = np.clip((v - vmin) / span, 0, 1)
    finite = np.isfinite(v)
    idx = np.where(finite, t * (len(lut) - 1) + 0.5, 0).astype(np.intp)
    img = np.empty(v.shape + (4,), dtype=np.uint8)
    img[..., :3] = lut[idx]
    img[..., 3] = np.where(finite, 255, 0)
    return img


def block_reduce(a: np.ndarray, rows: int, cols: int, how: str = "mean") -> np.ndarray:
    """Shrink a 2-D array to at most ``rows x cols`` by averaging blocks (NaN-aware)."""
    r, c = a.shape
    fr, fc = max(1, -(-r // rows)), max(1, -(-c // cols))
    if fr == 1 and fc == 1:
        return a
    pr, pc = (-r) % fr, (-c) % fc
    b = np.pad(a.astype(np.float64), ((0, pr), (0, pc)), constant_values=np.nan)
    b = b.reshape(b.shape[0] // fr, fr, b.shape[1] // fc, fc)
    with np.errstate(invalid="ignore"):
        if how == "max":
            return np.nanmax(b, axis=(1, 3))
        if how == "sum":
            return np.nansum(b, axis=(1, 3))
        return np.nanmean(b, axis=(1, 3))
