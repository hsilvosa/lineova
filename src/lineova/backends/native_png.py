"""Scene -> PNG with a rasteriser written in NumPy: no SVG renderer and no system fonts needed.

Shapes are filled by exact-area coverage accumulation (the scanline method used by font rasterisers), so
edges are anti-aliased without supersampling. Text is drawn from the bundled Liberation subsets
(``backends/fonts``), whose widths match the layout metrics. Strokes are built from quads and round
joins, dashes are cut along the path, and rectangular clips and group offsets are applied directly.

Limits compared with ``resvg``: the canvas is opaque (a transparent background becomes white), text is
not hinted and glyphs sit on a quarter-pixel grid, and blending happens in sRGB (as in browsers).
"""

from __future__ import annotations

import math

import numpy as np

from .. import scene as S
from .._color import parse
from ..raster import encode_png
from . import _ttf
from .svg import baseline_shift

_AA = 0.5          # half a pixel: the half-width of the anti-aliasing ramp used by the hatch patterns
_COLORS: dict = {}


def _rgba(color) -> tuple:
    got = _COLORS.get(color)
    if got is None:
        got = parse(color)
        _COLORS[color] = got
    return got


# --------------------------------------------------------------------------- coverage

def _accumulate(polys: list, w: int, h: int) -> np.ndarray:
    """Signed area coverage of closed polygons (arrays of x, y in region pixels) as an (h, w) float array."""
    stride = w + 2
    acc = [0.0] * (stride * h)
    fw = float(w)
    floor, ceil = math.floor, math.ceil
    for poly in polys:
        pts = poly.tolist()
        n = len(pts)
        if n < 3:
            continue
        px, py = pts[-1]
        for qx, qy in pts:
            x0, y0, x1, y1 = px, py, qx, qy
            px, py = qx, qy
            if y0 == y1:
                continue
            if y0 < y1:
                d = 1.0
            else:
                d = -1.0
                x0, y0, x1, y1 = x1, y1, x0, y0
            if y1 <= 0.0 or y0 >= h:
                continue
            dxdy = (x1 - x0) / (y1 - y0)
            x = x0
            if y0 < 0.0:
                x -= y0 * dxdy
                y0 = 0.0
            if y1 > h:
                y1 = float(h)
            for row in range(int(y0), min(h, int(ceil(y1)))):
                top = y0 if y0 > row else float(row)
                bot = y1 if y1 < row + 1 else row + 1.0
                dy = bot - top
                if dy <= 0:
                    continue
                xn = x + dxdy * dy
                dd = d * dy
                if x < xn:
                    xa, xb = x, xn
                else:
                    xa, xb = xn, x
                if xa < 0.0:
                    xa = 0.0
                elif xa > fw:
                    xa = fw
                if xb < 0.0:
                    xb = 0.0
                elif xb > fw:
                    xb = fw
                base = row * stride
                xf = floor(xa)
                x0i = int(xf)
                x1i = int(ceil(xb))
                if x1i <= x0i + 1:
                    xmf = 0.5 * (xa + xb) - xf
                    acc[base + x0i] += dd - dd * xmf
                    acc[base + x0i + 1] += dd * xmf
                else:
                    s = 1.0 / (xb - xa)
                    x0f = xa - xf
                    a0 = 0.5 * s * (1.0 - x0f) * (1.0 - x0f)
                    x1f = xb - x1i + 1.0
                    am = 0.5 * s * x1f * x1f
                    acc[base + x0i] += dd * a0
                    if x1i == x0i + 2:
                        acc[base + x0i + 1] += dd * (1.0 - a0 - am)
                    else:
                        a1 = s * (1.5 - x0f)
                        acc[base + x0i + 1] += dd * (a1 - a0)
                        for xi in range(x0i + 2, x1i - 1):
                            acc[base + xi] += dd * s
                        a2 = a1 + (x1i - x0i - 3) * s
                        acc[base + x1i - 1] += dd * (1.0 - a2 - am)
                    acc[base + x1i] += dd * am
                x = xn
    a = np.asarray(acc, dtype=np.float32).reshape(h, stride)
    return np.cumsum(a[:, :w], axis=1)


def _shape_cov(raw: np.ndarray, evenodd: bool) -> np.ndarray:
    c = np.abs(raw)
    if evenodd:
        c = 1.0 - np.abs((c % 2.0) - 1.0)
    return np.minimum(c, 1.0)


def _orient(poly: np.ndarray, negative: bool = True) -> np.ndarray:
    x, y = poly[:, 0], poly[:, 1]
    area = float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))
    return poly[::-1] if (area < 0) != negative and area != 0 else poly


def _circle(cx: float, cy: float, r: float) -> np.ndarray:
    """Regular polygon with the area of the circle (the radius is nudged out so small markers are not undersized)."""
    n = int(min(48, max(10, 6 * math.sqrt(max(r, 0.25)) + 6)))
    r = r * math.sqrt((2 * math.pi / n) / math.sin(2 * math.pi / n))
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return np.column_stack((cx + r * np.cos(t), cy + r * np.sin(t)))


# --------------------------------------------------------------------------- strokes

def _dash_runs(pts: np.ndarray, dash, closed: bool) -> list:
    """Cut a polyline into the 'on' pieces of a dash pattern."""
    pattern = [max(float(d), 0.01) for d in dash]
    if len(pattern) % 2:
        pattern = pattern * 2
    if closed:
        pts = np.vstack((pts, pts[:1]))
    runs, cur = [], [pts[0]]
    idx, left, on = 0, pattern[0], True
    for a, b in zip(pts[:-1], pts[1:]):
        seg = float(np.hypot(*(b - a)))
        if seg == 0:
            continue
        pos = 0.0
        while seg - pos > left:
            pos += left
            p = a + (b - a) * (pos / seg)
            if on:
                cur.append(p)
                runs.append(np.array(cur))
                cur = []
            else:
                cur = [p]
            on = not on
            idx = (idx + 1) % len(pattern)
            left = pattern[idx]
        left -= seg - pos
        if on:
            cur.append(b)
    if on and len(cur) > 1:
        runs.append(np.array(cur))
    return runs


def _stroke_polys(runs: list, width: float, closed: bool, cap: str, join: str) -> list:
    """Polygons (all with the same orientation) covering the stroke of each polyline run."""
    hw = width / 2.0
    out: list = []
    for pts in runs:
        pts = np.asarray(pts, dtype=np.float64)
        if closed and len(pts) > 2 and not np.allclose(pts[0], pts[-1]):
            pts = np.vstack((pts, pts[:1]))
        keep = np.r_[True, np.any(np.diff(pts, axis=0) != 0, axis=1)]
        pts = pts[keep]
        if len(pts) == 1:
            if cap == "round":
                out.append(_orient(_circle(pts[0, 0], pts[0, 1], hw)))
            else:
                x, y = pts[0]
                out.append(_orient(np.array([[x - hw, y - hw], [x + hw, y - hw], [x + hw, y + hw], [x - hw, y + hw]])))
            continue
        d = np.diff(pts, axis=0)
        ln = np.hypot(d[:, 0], d[:, 1])
        u = d / ln[:, None]
        nx, ny = -u[:, 1] * hw, u[:, 0] * hw
        p, q = pts[:-1], pts[1:]
        if cap == "square" and not closed:
            p = p.copy()
            q = q.copy()
            p[0] -= u[0] * hw
            q[-1] += u[-1] * hw
        quads = np.stack((np.column_stack((p[:, 0] + nx, p[:, 1] + ny)), np.column_stack((q[:, 0] + nx, q[:, 1] + ny)),
                          np.column_stack((q[:, 0] - nx, q[:, 1] - ny)), np.column_stack((p[:, 0] - nx, p[:, 1] - ny))), axis=1)
        out.extend(list(quads))
        if hw >= 0.45:                                   # round joins where the line turns, round caps at the ends
            if len(pts) > 2 and join != "bevel":
                dots = np.einsum("ij,ij->i", u[:-1], u[1:])
                for i in np.flatnonzero(dots < 0.985):
                    out.append(_orient(_circle(pts[i + 1, 0], pts[i + 1, 1], hw)))
            if cap == "round" and not closed:
                out.append(_orient(_circle(pts[0, 0], pts[0, 1], hw)))
                out.append(_orient(_circle(pts[-1, 0], pts[-1, 1], hw)))
    return out


# --------------------------------------------------------------------------- the canvas

class Canvas:
    def __init__(self, width: float, height: float, background: str, scale: float):
        self.scale = scale
        self.W = max(1, int(math.ceil(width * scale)))
        self.H = max(1, int(math.ceil(height * scale)))
        r, g, b, a = _rgba(background)
        if a < 1:
            r, g, b = r * a + (1 - a), g * a + (1 - a), b * a + (1 - a)
        self.rgb = np.empty((self.H, self.W, 3), dtype=np.float32)
        self.rgb[:] = (r, g, b)
        self.clips = [(0, 0, self.W, self.H)]
        self.offsets = [(0.0, 0.0)]
        self.glyph_cache: dict = {}
        self.font_kind = "sans"

    # -- state
    @property
    def clip(self):
        return self.clips[-1]

    def to_px(self, x, y):
        ox, oy = self.offsets[-1]
        s = self.scale
        return (np.asarray(x, dtype=np.float64) + ox) * s, (np.asarray(y, dtype=np.float64) + oy) * s

    def pts_px(self, xs, ys) -> np.ndarray:
        px, py = self.to_px(xs, ys)
        return np.column_stack((px, py))

    # -- compositing
    def composite(self, cov: np.ndarray, x0: int, y0: int, color: tuple, alpha: float = 1.0) -> None:
        h, w = cov.shape
        cx0, cy0, cx1, cy1 = self.clip
        ix0, iy0 = max(x0, cx0), max(y0, cy0)
        ix1, iy1 = min(x0 + w, cx1), min(y0 + h, cy1)
        if ix1 <= ix0 or iy1 <= iy0:
            return
        a = cov[iy0 - y0:iy1 - y0, ix0 - x0:ix1 - x0] * (alpha * color[3])
        sub = self.rgb[iy0:iy1, ix0:ix1]
        sub += (np.asarray(color[:3], dtype=np.float32) - sub) * a[..., None]

    def fill(self, polys: list, color: tuple, alpha: float = 1.0, evenodd: bool = False, hatch=None):
        """Fill closed polygons given in canvas pixels. Returns (coverage, x0, y0) or None."""
        if not polys or alpha <= 0:
            return None
        pts = np.vstack([p for p in polys if len(p)])
        if not np.isfinite(pts).all():
            polys = [p for p in polys if np.isfinite(p).all()]
            if not polys:
                return None
            pts = np.vstack(polys)
        cx0, cy0, cx1, cy1 = self.clip
        x0 = max(int(math.floor(pts[:, 0].min())) - 1, cx0)
        y0 = max(int(math.floor(pts[:, 1].min())) - 1, cy0)
        x1 = min(int(math.ceil(pts[:, 0].max())) + 1, cx1)
        y1 = min(int(math.ceil(pts[:, 1].max())) + 1, cy1)
        if x1 <= x0 or y1 <= y0:
            return None
        shifted = [p - (x0, y0) for p in polys]
        cov = _shape_cov(_accumulate(shifted, x1 - x0, y1 - y0), evenodd)
        if color is not None:
            self.composite(cov, x0, y0, color, alpha)
        if hatch:
            self.hatch(cov, x0, y0, hatch, alpha)
        return cov, x0, y0

    def fill_rect(self, x0, y0, x1, y1, color, alpha: float = 1.0, hatch=None) -> None:
        """Axis-aligned rectangle in canvas pixels, anti-aliased analytically."""
        cx0, cy0, cx1, cy1 = self.clip
        ix0, iy0 = max(int(math.floor(x0)), cx0), max(int(math.floor(y0)), cy0)
        ix1, iy1 = min(int(math.ceil(x1)), cx1), min(int(math.ceil(y1)), cy1)
        if ix1 <= ix0 or iy1 <= iy0 or x1 <= x0 or y1 <= y0:
            return
        xs = np.arange(ix0, ix1, dtype=np.float32)
        ys = np.arange(iy0, iy1, dtype=np.float32)
        cx = np.clip(np.minimum(xs + 1, x1) - np.maximum(xs, x0), 0, 1)
        cy = np.clip(np.minimum(ys + 1, y1) - np.maximum(ys, y0), 0, 1)
        cov = np.outer(cy, cx).astype(np.float32)
        if color is not None:
            self.composite(cov, ix0, iy0, color, alpha)
        if hatch:
            self.hatch(cov, ix0, iy0, hatch, alpha)

    def stroke(self, runs: list, width: float, color: tuple, alpha: float, closed=False, cap="butt", join="round", dash=None):
        if not runs or width <= 0 or alpha <= 0:
            return
        if dash:
            sc = self.scale
            cut = []
            for r in runs:
                cut.extend(_dash_runs(np.asarray(r, dtype=np.float64), [d * sc for d in dash], closed))
            runs, closed = cut, False
        polys = _stroke_polys(runs, width, closed, cap, join)
        self.fill(polys, color, alpha)

    # -- hatch patterns
    def hatch(self, cov: np.ndarray, x0: int, y0: int, spec: str, alpha: float) -> None:
        color, _, kind = spec.partition("|")
        kind = kind or "/"
        sc = self.scale
        h, w = cov.shape
        ys, xs = np.mgrid[y0:y0 + h, x0:x0 + w].astype(np.float32)
        xs, ys = xs / sc, ys / sc                      # pattern lives in user units
        def ramp(half_width, dist):
            return np.clip((half_width - dist) * sc + _AA, 0, 1)      # a one-pixel anti-aliased edge

        if kind == ".":
            fx, fy = np.mod(xs, 5) - 2.5, np.mod(ys, 5) - 2.5
            pat = ramp(1.1, np.hypot(fx, fy))
        elif kind in ("-", "|"):
            u = np.mod(ys if kind == "-" else xs, 6) - 3
            pat = ramp(0.7, np.abs(u))
        else:
            rot = {"/": 45.0, "\\": -45.0, "x": 45.0}[kind if kind in ("/", "\\", "x") else "/"]
            t = math.radians(rot)
            u = xs * math.cos(t) + ys * math.sin(t)
            v = -xs * math.sin(t) + ys * math.cos(t)
            period = 6.0 if kind == "x" else 5.0
            # the SVG pattern draws its line on the tile edge, so only the half inside the tile shows
            def edge_line(c):
                m = np.mod(c, period)
                return np.clip(m * sc + _AA, 0, 1) * ramp(0.7, m)

            pat = edge_line(u)
            if kind == "x":
                pat = np.maximum(pat, edge_line(v))
        self.composite(cov * pat.astype(np.float32), x0, y0, _rgba(color), alpha)

    # -- images
    def image(self, op: S.Image) -> None:
        sc = self.scale
        px, py = self.to_px([op.x, op.x + op.w], [op.y, op.y + op.h])
        x0, x1 = int(round(px[0])), int(round(px[1]))
        y0, y1 = int(round(py[0])), int(round(py[1]))
        w, h = x1 - x0, y1 - y0
        if w <= 0 or h <= 0:
            return
        src = np.asarray(op.rgba, dtype=np.float32) / 255.0
        sh, sw = src.shape[:2]
        gy = (np.arange(h) + 0.5) * sh / h - 0.5
        gx = (np.arange(w) + 0.5) * sw / w - 0.5
        if op.smooth and (sh != h or sw != w):
            iy0 = np.clip(np.floor(gy).astype(int), 0, sh - 1)
            iy1 = np.clip(iy0 + 1, 0, sh - 1)
            ix0 = np.clip(np.floor(gx).astype(int), 0, sw - 1)
            ix1 = np.clip(ix0 + 1, 0, sw - 1)
            fy = np.clip(gy - iy0, 0, 1)[:, None, None]
            fx = np.clip(gx - ix0, 0, 1)[None, :, None]
            top = src[iy0][:, ix0] * (1 - fx) + src[iy0][:, ix1] * fx
            bot = src[iy1][:, ix0] * (1 - fx) + src[iy1][:, ix1] * fx
            img = top * (1 - fy) + bot * fy
        else:
            img = src[np.clip(np.round(gy).astype(int), 0, sh - 1)][:, np.clip(np.round(gx).astype(int), 0, sw - 1)]
        cx0, cy0, cx1, cy1 = self.clip
        ix0_, iy0_, ix1_, iy1_ = max(x0, cx0), max(y0, cy0), min(x1, cx1), min(y1, cy1)
        if ix1_ <= ix0_ or iy1_ <= iy0_:
            return
        img = img[iy0_ - y0:iy1_ - y0, ix0_ - x0:ix1_ - x0]
        a = img[..., 3:4] if img.shape[2] == 4 else 1.0
        sub = self.rgb[iy0_:iy1_, ix0_:ix1_]
        sub += (img[..., :3] - sub) * a
        _ = sc

    # -- text
    def glyph(self, font, gid: int, size_px: float, fq: int):
        key = (id(font), gid, round(size_px, 2), fq)
        got = self.glyph_cache.get(key)
        if got is not None:
            return got
        polys = []
        for c in font.outline(gid):
            polys.append(np.column_stack((c[:, 0] * size_px + fq / 4.0, -c[:, 1] * size_px)))
        if not polys:
            got = (None, 0, 0)
        else:
            pts = np.vstack(polys)
            x0, y0 = int(math.floor(pts[:, 0].min())) - 1, int(math.floor(pts[:, 1].min())) - 1
            x1, y1 = int(math.ceil(pts[:, 0].max())) + 1, int(math.ceil(pts[:, 1].max())) + 1
            cov = _shape_cov(_accumulate([p - (x0, y0) for p in polys], x1 - x0, y1 - y0), False)
            got = (cov, x0, y0)
        self.glyph_cache[key] = got
        return got

    def text(self, op: S.Text) -> None:
        sc = self.scale
        spans = op.spans or [(op.text, op.weight, op.italic, None)]
        runs = []                                        # (font, gid, advance_em, colour)
        for txt, weight, italic, colour in spans:
            font = _ttf.load(self.font_kind, weight >= 600, bool(italic))
            for ch in txt:
                gid = font.glyph_index(ch) or font.glyph_index("?")
                runs.append((font, gid, font.advance(gid), colour))
        if not runs:
            return
        size = op.size
        total = sum(r[2] * size + op.letter_spacing for r in runs)
        start = {"start": 0.0, "middle": -total / 2, "end": -total}[op.anchor]
        by = baseline_shift(op.baseline, size)
        ox, oy = self.offsets[-1]
        ax, ay = (op.x + ox) * sc, (op.y + oy) * sc
        if op.rotate:
            self._rotated_text(op, runs, start, by, ax, ay)
            return
        size_px = size * sc
        pen = ax + start * sc
        base_y = int(round(ay + by * sc))
        pieces = []                                      # (coverage, x, y, colour) per glyph
        for font, gid, adv, colour in runs:
            fx = pen
            ix = int(math.floor(fx))
            fq = int((fx - ix) * 4)
            cov, gx, gy = self.glyph(font, gid, size_px, fq)
            if cov is not None:
                pieces.append((cov, ix + gx, base_y + gy, colour or op.color))
            pen += adv * size_px + op.letter_spacing * sc
        if not pieces:
            return
        x0 = min(p[1] for p in pieces)
        y0 = min(p[2] for p in pieces)
        x1 = max(p[1] + p[0].shape[1] for p in pieces)
        y1 = max(p[2] + p[0].shape[0] for p in pieces)
        buffers: dict = {}
        for cov, gx, gy, colour in pieces:
            buf = buffers.setdefault(colour, np.zeros((y1 - y0, x1 - x0), dtype=np.float32))
            sub = buf[gy - y0:gy - y0 + cov.shape[0], gx - x0:gx - x0 + cov.shape[1]]
            np.maximum(sub, cov, out=sub)
        if op.halo:
            r = max(1, int(round(1.5 * sc)))
            union = np.maximum.reduce(list(buffers.values()))
            padded = np.pad(union, r)
            halo = np.zeros_like(union)
            yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
            for dy, dx in zip(yy.ravel(), xx.ravel()):
                if dx * dx + dy * dy <= r * r + 0.5:
                    np.maximum(halo, padded[r + dy:r + dy + union.shape[0], r + dx:r + dx + union.shape[1]], out=halo)
            self.composite(halo, x0, y0, _rgba(op.halo))
        for colour, buf in buffers.items():
            self.composite(buf, x0, y0, _rgba(colour))

    def _rotated_text(self, op, runs, start, by, ax, ay) -> None:
        sc = self.scale
        t = math.radians(op.rotate)
        ct, st = math.cos(t), math.sin(t)
        size_px = op.size * sc
        pen = start * sc
        polys_by_colour: dict = {}
        for font, gid, adv, colour in runs:
            for c in font.outline(gid):
                lx = c[:, 0] * size_px + pen
                ly = -c[:, 1] * size_px + by * sc
                x = ax + lx * ct - ly * st
                y = ay + lx * st + ly * ct
                polys_by_colour.setdefault(colour or op.color, []).append(np.column_stack((x, y)))
            pen += adv * size_px + op.letter_spacing * sc
        if op.halo:
            allp = [p for ps in polys_by_colour.values() for p in ps]
            ring = []
            for p in allp:
                ring.extend(_stroke_polys([np.vstack((p, p[:1]))], 3.0 * sc, False, "round", "round"))
            self.fill(ring + [_orient(p, False) for p in allp], _rgba(op.halo), 1.0)
        for colour, ps in polys_by_colour.items():
            self.fill(ps, _rgba(colour), 1.0)

    # -- markers
    def markers(self, op: S.Markers) -> None:
        xs = np.asarray(op.xs, dtype=np.float64)
        ys = np.asarray(op.ys, dtype=np.float64)
        n = len(xs)
        if n == 0:
            return
        sc = self.scale
        px, py = self.to_px(xs, ys)
        sizes = np.broadcast_to(np.asarray(op.size, dtype=np.float64), (n,)) * sc
        fills = op.fill if isinstance(op.fill, (list, tuple, np.ndarray)) else None
        strokes = op.stroke if isinstance(op.stroke, (list, tuple, np.ndarray)) else None
        fcol = None if (fills is not None or not op.fill) else _rgba(op.fill)
        scol = None if (strokes is not None or not op.stroke) else _rgba(op.stroke)
        sw = op.stroke_width * sc
        alpha_f = op.opacity * op.fill_opacity
        shape = op.shape
        cx0, cy0, cx1, cy1 = self.clip
        cache: dict = {}
        for i in range(n):
            x, y, r = px[i], py[i], round(float(sizes[i]) * 5) / 5      # radii on a 0.2 px grid: sprites are reused
            if not (math.isfinite(x) and math.isfinite(y)) or x + r + sw < cx0 or x - r - sw > cx1 or y + r + sw < cy0 or y - r - sw > cy1:
                continue
            fc = _rgba(fills[i]) if fills is not None else fcol
            scl = _rgba(strokes[i]) if strokes is not None else scol
            if shape == "circle":
                ix, iy = int(math.floor(x)), int(math.floor(y))
                fq, gq = int((x - ix) * 4), int((y - iy) * 4)
                key = (round(float(r), 2), fq, gq, round(sw, 2))
                sprite = cache.get(key)
                if sprite is None:
                    sprite = self._disc(r, sw, fq / 4.0, gq / 4.0, bool(scl is not None or strokes is not None))
                    cache[key] = sprite
                fill_cov, ring_cov, ox, oy = sprite
                if fc is not None:
                    self.composite(fill_cov, ix + ox, iy + oy, fc, alpha_f)
                if scl is not None and ring_cov is not None:
                    self.composite(ring_cov, ix + ox, iy + oy, scl, op.opacity)
            else:
                poly, lines = _marker_geometry(shape, x, y, r)
                if poly is not None and fc is not None:
                    self.fill([_orient(poly)], fc, alpha_f)
                if scl is not None:
                    self.stroke(lines if poly is None else [np.vstack((poly, poly[:1]))], sw, scl, op.opacity, False, "butt", "round")

    @staticmethod
    def _disc(r: float, sw: float, fx: float, fy: float, ring: bool):
        pad = int(math.ceil(r + sw)) + 2
        size = 2 * pad + 1
        c = _shape_cov(_accumulate([_orient(_circle(pad + fx, pad + fy, r))], size, size), False)
        ring_cov = None
        if ring and sw > 0:
            outer = _shape_cov(_accumulate([_orient(_circle(pad + fx, pad + fy, r + sw / 2))], size, size), False)
            inner = _shape_cov(_accumulate([_orient(_circle(pad + fx, pad + fy, max(r - sw / 2, 0.01)))], size, size), False)
            ring_cov = np.clip(outer - inner, 0, 1)
        return c, ring_cov, -pad, -pad


def _marker_geometry(shape: str, x: float, y: float, r: float):
    if shape == "square":
        return np.array([[x - r, y - r], [x + r, y - r], [x + r, y + r], [x - r, y + r]]), None
    if shape == "triangle":
        return np.array([[x, y - r * 1.2], [x + r * 1.1, y + r * 0.8], [x - r * 1.1, y + r * 0.8]]), None
    if shape == "diamond":
        return np.array([[x, y - r * 1.25], [x + r, y], [x, y + r * 1.25], [x - r, y]]), None
    if shape == "cross":
        return None, [np.array([[x - r, y], [x + r, y]]), np.array([[x, y - r], [x, y + r]])]
    if shape == "x":
        k = r * 0.8
        return None, [np.array([[x - k, y - k], [x + k, y + k]]), np.array([[x - k, y + k], [x + k, y - k]])]
    raise ValueError(shape)


# --------------------------------------------------------------------------- scene walking

def _flatten_path(cmds, sc_pts) -> list:
    """Path commands (already in canvas pixels) -> list of (points array, closed)."""
    subs, cur, start, closed = [], [], None, False
    last = None
    for c in cmds:
        k = c[0]
        if k == "M":
            if cur:
                subs.append((np.array(cur), closed))
            cur, closed = [(c[1], c[2])], False
            start = last = (c[1], c[2])
        elif k == "L":
            cur.append((c[1], c[2]))
            last = (c[1], c[2])
        elif k == "C":
            p0 = last
            ln = math.hypot(c[5] - p0[0], c[6] - p0[1]) + math.hypot(c[3] - c[1], c[4] - c[2]) * 0.5
            n = int(min(40, max(4, ln / 3)))
            t = np.linspace(0, 1, n + 1)[1:]
            x = ((1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * c[1] + 3 * (1 - t) * t * t * c[3] + t ** 3 * c[5])
            y = ((1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * c[2] + 3 * (1 - t) * t * t * c[4] + t ** 3 * c[6])
            cur.extend(zip(x.tolist(), y.tolist()))
            last = (c[5], c[6])
        elif k == "Q":
            p0 = last
            ln = math.hypot(c[3] - p0[0], c[4] - p0[1])
            n = int(min(40, max(4, ln / 3)))
            t = np.linspace(0, 1, n + 1)[1:]
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[1] + t * t * c[3]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[2] + t * t * c[4]
            cur.extend(zip(x.tolist(), y.tolist()))
            last = (c[3], c[4])
        elif k == "Z":
            closed = True
            if cur:
                subs.append((np.array(cur), True))
                cur = [start] if start else []
                closed = False
                last = start
    if len(cur) > 1:
        subs.append((np.array(cur), closed))
    return subs


def _rounded_rect(x0, y0, x1, y1, r) -> np.ndarray:
    n = max(3, int(r) + 3)
    t = np.linspace(0, math.pi / 2, n)
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -math.pi / 2), (x1 - r, y1 - r, 0.0), (x0 + r, y1 - r, math.pi / 2),
                       (x0 + r, y0 + r, math.pi)):
        pts.append(np.column_stack((cx + r * np.cos(a0 + t), cy + r * np.sin(a0 + t))))
    return np.vstack(pts)


def render_png(scene: S.Scene, scale: float = 2.0) -> bytes:
    cv = Canvas(scene.width, scene.height, scene.background, scale)
    cv.font_kind = scene.font_kind if scene.font_kind in ("sans", "serif", "mono") else "sans"
    sc = scale

    def walk(ops):
        for op in ops:
            t = type(op)
            if t is S.Rect:
                x0, y0 = cv.to_px(op.x, op.y)
                x1, y1 = cv.to_px(op.x + max(op.w, 0), op.y + max(op.h, 0))
                x0, y0, x1, y1 = float(x0), float(y0), float(x1), float(y1)
                fill = _rgba(op.fill) if op.fill else None
                if op.rx > 0.5 and (fill or op.stroke):
                    poly = _rounded_rect(x0, y0, x1, y1, min(op.rx * sc, (x1 - x0) / 2, (y1 - y0) / 2))
                    if fill:
                        cv.fill([poly], fill, op.opacity)
                    if op.hatch:
                        cv.fill([poly], None, op.opacity, hatch=op.hatch)
                else:
                    if fill or op.hatch:
                        cv.fill_rect(x0, y0, x1, y1, fill, op.opacity, op.hatch)
                if op.stroke:
                    poly = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
                    cv.stroke([poly], op.stroke_width * sc, _rgba(op.stroke), op.opacity, True, "butt", "miter", op.dash)
            elif t is S.Line:
                a = cv.pts_px([op.x1, op.x2], [op.y1, op.y2])
                cv.stroke([a], op.stroke_width * sc, _rgba(op.stroke), op.opacity, False, op.cap, "round", op.dash)
            elif t is S.Polyline:
                xs = np.asarray(op.xs, dtype=np.float64)
                ys = np.asarray(op.ys, dtype=np.float64)
                finite = np.isfinite(xs) & np.isfinite(ys)
                if finite.all():
                    runs = [(0, len(xs))]
                else:
                    idx = np.flatnonzero(np.diff(np.concatenate(([0], finite.view(np.int8), [0]))))
                    runs = list(zip(idx[::2], idx[1::2]))
                pts_runs = [cv.pts_px(xs[a:b], ys[a:b]) for a, b in runs if b - a >= 1]
                if op.fill:
                    cv.fill([p for p in pts_runs if len(p) >= 3], _rgba(op.fill), op.opacity * op.fill_opacity,
                            hatch=op.hatch if op.closed else None)
                if op.stroke:
                    cv.stroke(pts_runs, op.stroke_width * sc, _rgba(op.stroke), op.opacity, op.closed, op.cap, op.join, op.dash)
            elif t is S.Path:
                cmds = []
                ox, oy = cv.offsets[-1]
                for c in op.cmds:
                    if c[0] == "Z":
                        cmds.append(c)
                    else:
                        vals = [(v + (ox, oy)[i % 2]) * sc for i, v in enumerate(c[1:])]
                        cmds.append((c[0], *vals))
                subs = _flatten_path(cmds, None)
                if op.fill or op.hatch:
                    polys = [p for p, _ in subs if len(p) >= 3]
                    if op.fill:
                        cv.fill(polys, _rgba(op.fill), op.opacity * op.fill_opacity, op.evenodd, op.hatch)
                    elif op.hatch:
                        cv.fill(polys, None, 1.0, op.evenodd, op.hatch)
                if op.stroke:
                    for p, closed in subs:
                        cv.stroke([p], op.stroke_width * sc, _rgba(op.stroke), op.opacity, closed, op.cap, op.join, op.dash)
                    if op.arrow and subs and len(subs[-1][0]) >= 2:
                        _arrow(cv, subs[-1][0], _rgba(op.stroke), op.opacity, sc)
            elif t is S.Markers:
                cv.markers(op)
            elif t is S.Text:
                if op.text or op.spans:
                    cv.text(op)
            elif t is S.Image:
                cv.image(op)
            elif t is S.Clip:
                x0, y0 = cv.to_px(op.x, op.y)
                x1, y1 = cv.to_px(op.x + op.w, op.y + op.h)
                cx0, cy0, cx1, cy1 = cv.clip
                cv.clips.append((max(cx0, int(math.floor(x0))), max(cy0, int(math.floor(y0))),
                                 min(cx1, int(math.ceil(x1))), min(cy1, int(math.ceil(y1)))))
            elif t is S.EndClip:
                if len(cv.clips) > 1:
                    cv.clips.pop()
            elif t is S.Group:
                ox, oy = cv.offsets[-1]
                cv.offsets.append((ox + op.dx, oy + op.dy))
                walk(op.ops)
                cv.offsets.pop()
            else:  # pragma: no cover - defensive
                raise TypeError(f"Unknown scene op {t.__name__}")

    walk(scene.ops)
    out = np.clip(np.rint(cv.rgb * 255.0), 0, 255).astype(np.uint8)
    return encode_png(out)


def _arrow(cv: Canvas, pts: np.ndarray, color: tuple, opacity: float, sc: float) -> None:
    """Arrowhead at the end of a path, like the SVG marker (10x10 box shown at 7 px, tip at the end point)."""
    p = pts[-1]
    q = pts[-2]
    for k in range(len(pts) - 2, -1, -1):          # the last segment that has a length
        if np.hypot(*(pts[-1] - pts[k])) > 1e-6:
            q = pts[k]
            break
    d = p - q
    ln = float(np.hypot(*d))
    if ln == 0:
        return
    u = d / ln
    n = np.array([-u[1], u[0]])
    k = 0.7 * sc                                    # the marker is 10 units wide, drawn 7 px wide
    tri = np.array([p + u * k, p - u * 9 * k + n * 4 * k, p - u * 9 * k - n * 4 * k])   # tip 1 unit past the end, base 9 behind
    cv.fill([_orient(tri)], color, opacity)
