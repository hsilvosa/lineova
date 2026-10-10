"""A small TrueType reader: glyph outlines and advance widths, in pure Python.

It reads the bundled font subsets (``backends/fonts``) for the native PNG writer. Only what the writer
needs is supported: cmap formats 4 and 12, simple and composite glyphs, hmtx. No hinting, no kerning.
"""

from __future__ import annotations

import gzip
import struct
from functools import lru_cache
from pathlib import Path

import numpy as np

FONT_DIR = Path(__file__).resolve().parent / "fonts"


class TrueTypeFont:
    def __init__(self, data: bytes):
        self.data = data
        n = struct.unpack_from(">H", data, 4)[0]
        self.tables = {}
        for i in range(n):
            tag, _cs, off, length = struct.unpack_from(">4sIII", data, 12 + 16 * i)
            self.tables[tag.decode("latin-1")] = (off, length)
        head = self.tables["head"][0]
        self.units = struct.unpack_from(">H", data, head + 18)[0]
        self.bbox = struct.unpack_from(">hhhh", data, head + 36)
        self.loca_long = struct.unpack_from(">h", data, head + 50)[0] == 1
        self.num_glyphs = struct.unpack_from(">H", data, self.tables["maxp"][0] + 4)[0]
        hhea = self.tables["hhea"][0]
        self.ascent, self.descent = struct.unpack_from(">hh", data, hhea + 4)
        self.n_hmetrics = struct.unpack_from(">H", data, hhea + 34)[0]
        os2 = self.tables.get("OS/2")
        self.cap_height = struct.unpack_from(">h", data, os2[0] + 88)[0] if os2 and os2[1] >= 90 else self.ascent
        post = self.tables.get("post")
        self.italic_angle = struct.unpack_from(">i", data, post[0] + 4)[0] / 65536 if post else 0.0
        self.postscript_name = self._name(6)
        self._cmap = self._read_cmap()
        self._loca = self._read_loca()
        self._outlines: dict = {}

    # ------------------------------------------------------------------ tables
    def _name(self, name_id: int) -> str:
        off = self.tables["name"][0]
        count, str_off = struct.unpack_from(">HH", self.data, off + 2)
        for i in range(count):
            pid, eid, lid, nid, length, o = struct.unpack_from(">HHHHHH", self.data, off + 6 + 12 * i)
            if nid == name_id:
                raw = self.data[off + str_off + o:off + str_off + o + length]
                return raw.decode("utf-16-be" if pid in (0, 3) else "latin-1")
        return "Font"

    def _read_loca(self):
        off, length = self.tables["loca"]
        if self.loca_long:
            return np.frombuffer(self.data, dtype=">u4", count=self.num_glyphs + 1, offset=off).astype(np.int64)
        return np.frombuffer(self.data, dtype=">u2", count=self.num_glyphs + 1, offset=off).astype(np.int64) * 2

    def _read_cmap(self) -> dict:
        d = self.data
        base = self.tables["cmap"][0]
        n = struct.unpack_from(">H", d, base + 2)[0]
        best = None
        for i in range(n):
            pid, eid, off = struct.unpack_from(">HHI", d, base + 4 + 8 * i)
            fmt = struct.unpack_from(">H", d, base + off)[0]
            rank = {(3, 10): 3, (3, 1): 2, (0, 4): 3, (0, 3): 2, (0, 6): 1}.get((pid, eid), 0)
            if fmt in (4, 12) and (best is None or rank > best[0]):
                best = (rank, base + off, fmt)
        if best is None:
            raise ValueError("The font has no usable cmap.")
        _, off, fmt = best
        out: dict = {}
        if fmt == 4:
            segx2 = struct.unpack_from(">H", d, off + 6)[0]
            seg = segx2 // 2
            ends = struct.unpack_from(f">{seg}H", d, off + 14)
            starts = struct.unpack_from(f">{seg}H", d, off + 16 + segx2)
            deltas = struct.unpack_from(f">{seg}h", d, off + 16 + 2 * segx2)
            ro_pos = off + 16 + 3 * segx2
            offsets = struct.unpack_from(f">{seg}H", d, ro_pos)
            for i in range(seg):
                for c in range(starts[i], ends[i] + 1):
                    if c == 0xFFFF:
                        continue
                    if offsets[i] == 0:
                        g = (c + deltas[i]) & 0xFFFF
                    else:
                        p = ro_pos + 2 * i + offsets[i] + 2 * (c - starts[i])
                        g = struct.unpack_from(">H", d, p)[0]
                        g = (g + deltas[i]) & 0xFFFF if g else 0
                    if g:
                        out[c] = g
        else:
            groups = struct.unpack_from(">I", d, off + 12)[0]
            for i in range(groups):
                s, e, g = struct.unpack_from(">III", d, off + 16 + 12 * i)
                for c in range(s, e + 1):
                    out[c] = g + c - s
        return out

    # ------------------------------------------------------------------ metrics and outlines
    def glyph_index(self, ch: str) -> int:
        return self._cmap.get(ord(ch), 0)

    def advance(self, gid: int) -> float:
        off = self.tables["hmtx"][0]
        i = min(gid, self.n_hmetrics - 1)
        return struct.unpack_from(">H", self.data, off + 4 * i)[0] / self.units

    def outline(self, gid: int) -> list:
        """Polygons (arrays of x, y in em units, y up) that make up the glyph."""
        got = self._outlines.get(gid)
        if got is None:
            got = [np.asarray(c, dtype=np.float64) / self.units for c in self._contours(gid, 0)]
            self._outlines[gid] = got
        return got

    def _contours(self, gid: int, depth: int) -> list:
        if depth > 4 or gid >= self.num_glyphs:
            return []
        a, b = int(self._loca[gid]), int(self._loca[gid + 1])
        if b <= a:
            return []
        d = self.data
        g = self.tables["glyf"][0] + a
        ncont = struct.unpack_from(">h", d, g)[0]
        p = g + 10
        if ncont >= 0:
            return self._simple(d, p, ncont)
        out: list = []
        while True:
            flags, sub = struct.unpack_from(">HH", d, p)
            p += 4
            if flags & 1:
                dx, dy = struct.unpack_from(">hh", d, p)
                p += 4
            else:
                dx, dy = struct.unpack_from(">bb", d, p)
                p += 2
            if not flags & 2:
                dx = dy = 0
            a_, b_, c_, d_ = 1.0, 0.0, 0.0, 1.0
            if flags & 0x8:
                a_ = d_ = struct.unpack_from(">h", d, p)[0] / 16384
                p += 2
            elif flags & 0x40:
                a_, d_ = (v / 16384 for v in struct.unpack_from(">hh", d, p))
                p += 4
            elif flags & 0x80:
                a_, b_, c_, d_ = (v / 16384 for v in struct.unpack_from(">hhhh", d, p))
                p += 8
            for cont in self._contours(sub, depth + 1):
                arr = np.asarray(cont, dtype=np.float64)
                x = arr[:, 0] * a_ + arr[:, 1] * c_ + dx
                y = arr[:, 0] * b_ + arr[:, 1] * d_ + dy
                out.append(np.column_stack((x, y)))
            if not flags & 0x20:
                break
        return out

    @staticmethod
    def _simple(d: bytes, p: int, ncont: int) -> list:
        if ncont == 0:
            return []
        ends = struct.unpack_from(f">{ncont}H", d, p)
        p += 2 * ncont
        ilen = struct.unpack_from(">H", d, p)[0]
        p += 2 + ilen
        npts = ends[-1] + 1
        flags = []
        while len(flags) < npts:
            f = d[p]
            p += 1
            flags.append(f)
            if f & 8:
                r = d[p]
                p += 1
                flags.extend([f] * r)
        xs, ys = [], []
        v = 0
        for f in flags[:npts]:
            if f & 2:
                dv = d[p]
                p += 1
                v += dv if f & 16 else -dv
            elif not f & 16:
                v += struct.unpack_from(">h", d, p)[0]
                p += 2
            xs.append(v)
        v = 0
        for f in flags[:npts]:
            if f & 4:
                dv = d[p]
                p += 1
                v += dv if f & 32 else -dv
            elif not f & 32:
                v += struct.unpack_from(">h", d, p)[0]
                p += 2
            ys.append(v)
        out, start = [], 0
        for e in ends:
            pts = [(xs[i], ys[i], bool(flags[i] & 1)) for i in range(start, e + 1)]
            start = e + 1
            out.append(_flatten(pts))
        return out


def _flatten(pts: list) -> list:
    """Quadratic TrueType contour -> list of (x, y) points."""
    n = len(pts)
    if n < 2:
        return [(p[0], p[1]) for p in pts]
    # rotate so that the contour starts on an on-curve point
    first = next((i for i, p in enumerate(pts) if p[2]), None)
    if first is None:
        mid = ((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2, True)
        pts = [mid] + pts
    else:
        pts = pts[first:] + pts[:first]
    out = [(pts[0][0], pts[0][1])]
    cur = pts[0]
    i = 1
    pts = pts + [pts[0]]
    while i < len(pts):
        p = pts[i]
        if p[2]:
            out.append((p[0], p[1]))
            cur = p
            i += 1
            continue
        nxt = pts[i + 1] if i + 1 < len(pts) else pts[0]
        if nxt[2]:
            end = nxt
            i += 2
        else:
            end = ((p[0] + nxt[0]) / 2, (p[1] + nxt[1]) / 2, True)
            i += 1
        t = np.linspace(0, 1, 7)[1:]
        qx = (1 - t) ** 2 * cur[0] + 2 * (1 - t) * t * p[0] + t * t * end[0]
        qy = (1 - t) ** 2 * cur[1] + 2 * (1 - t) * t * p[1] + t * t * end[1]
        out.extend(zip(qx.tolist(), qy.tolist()))
        cur = end
    return out


@lru_cache(maxsize=16)
def load(kind: str, bold: bool, italic: bool) -> TrueTypeFont:
    """The bundled face for a theme font kind (``sans``, ``serif``, ``mono``)."""
    family = {"sans": "Sans", "serif": "Serif", "mono": "Mono"}.get(kind, "Sans")
    style = "Bold" if bold else ("Italic" if italic and family != "Mono" else "Regular")
    path = FONT_DIR / f"Lineova{family}-{style}.ttf.gz"
    if not path.exists():
        path = FONT_DIR / f"Lineova{family}-Regular.ttf.gz"
    return TrueTypeFont(gzip.decompress(path.read_bytes()))
