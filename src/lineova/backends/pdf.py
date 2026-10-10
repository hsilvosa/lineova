"""Scene -> vector PDF. Pure Python (zlib only).

Text stays text (selectable, searchable) and lines stay vectors, so figures are
sharp at any zoom — what journals ask for. 1 px = 0.75 pt (CSS reference).

By default the text uses the bundled Liberation fonts, embedded as TrueType (Type0 / Identity-H with a
ToUnicode map), so the PDF looks the same everywhere and keeps real Unicode (−, →, ≤, é ...). With
``embed_fonts=False`` it uses the 14 standard PDF fonts instead (smaller files, ASCII-ish symbols).
"""

from __future__ import annotations

import math
import zlib

import numpy as np

from .. import scene as S
from .._color import parse
from .._text import KIND_FACTOR, text_width
from . import _ttf
from .svg import baseline_shift

PT = 0.75
_FAMILIES = {
    "sans": ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"),
    "serif": ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"),
    "mono": ("Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique"),
}
_REPLACE = {"−": "-", "→": "->", "←": "<-", "Σ": "S", "≤": "<=", "≥": ">=",
            "≈": "~", " ": " ", " ": " ", "⁻": "-", "¹": "1"}
_K = 0.5522847498


def _enc(text: str) -> bytes:
    for a, b in _REPLACE.items():
        text = text.replace(a, b)
    raw = text.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _n(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


class _Writer:
    def __init__(self, scene: S.Scene, embed: bool = True):
        self.scene = scene
        self.embed = embed
        self.faces: dict[str, tuple] = {}          # resource name (F1..) -> (font, {gid: char}) for embedded fonts
        self._face_by_key: dict[tuple, str] = {}
        self.out: list[str] = []
        self.gstates: dict[tuple, str] = {}
        self.images: list[tuple[str, np.ndarray]] = []

    # -- state helpers
    def alpha(self, fill_a: float = 1.0, stroke_a: float = 1.0) -> None:
        if fill_a >= 0.999 and stroke_a >= 0.999:
            return
        key = (round(fill_a, 3), round(stroke_a, 3))
        name = self.gstates.setdefault(key, f"GS{len(self.gstates)}")
        self.out.append(f"/{name} gs")

    def fill_color(self, c: str) -> float:
        r, g, b, a = parse(c)
        self.out.append(f"{_n(r)} {_n(g)} {_n(b)} rg")
        return a

    def stroke_color(self, c: str) -> float:
        r, g, b, a = parse(c)
        self.out.append(f"{_n(r)} {_n(g)} {_n(b)} RG")
        return a

    def stroke_style(self, width: float, dash=None, cap="butt", join="miter"):
        self.out.append(f"{_n(width)} w")
        self.out.append({"butt": "0 J", "round": "1 J", "square": "2 J"}.get(cap, "0 J"))
        self.out.append({"miter": "0 j", "round": "1 j", "bevel": "2 j"}.get(join, "0 j"))
        if dash:
            self.out.append(f"[{' '.join(_n(d) for d in dash)}] 0 d")

    def paint(self, fill, stroke, width=1.0, opacity=1.0, fill_opacity=1.0, dash=None, cap="butt", join="miter",
              evenodd=False):
        fa = sa = opacity
        if fill:
            fa *= self.fill_color(fill) * fill_opacity
        if stroke:
            sa *= self.stroke_color(stroke)
            self.stroke_style(width, dash, cap, join)
        self.alpha(fa, sa)
        if fill and stroke:
            self.out.append("B*" if evenodd else "B")
        elif fill:
            self.out.append("f*" if evenodd else "f")
        elif stroke:
            self.out.append("S")
        else:
            self.out.append("n")

    # -- geometry
    def rect_path(self, x, y, w, h, r=0.0):
        if r <= 0.01:
            self.out.append(f"{_n(x)} {_n(y)} {_n(w)} {_n(h)} re")
            return
        r = min(r, w / 2, h / 2)
        k = r * (1 - _K)
        o = self.out
        o.append(f"{_n(x + r)} {_n(y)} m")
        o.append(f"{_n(x + w - r)} {_n(y)} l")
        o.append(f"{_n(x + w - k)} {_n(y)} {_n(x + w)} {_n(y + k)} {_n(x + w)} {_n(y + r)} c")
        o.append(f"{_n(x + w)} {_n(y + h - r)} l")
        o.append(f"{_n(x + w)} {_n(y + h - k)} {_n(x + w - k)} {_n(y + h)} {_n(x + w - r)} {_n(y + h)} c")
        o.append(f"{_n(x + r)} {_n(y + h)} l")
        o.append(f"{_n(x + k)} {_n(y + h)} {_n(x)} {_n(y + h - k)} {_n(x)} {_n(y + h - r)} c")
        o.append(f"{_n(x)} {_n(y + r)} l")
        o.append(f"{_n(x)} {_n(y + k)} {_n(x + k)} {_n(y)} {_n(x + r)} {_n(y)} c h")

    def circle_path(self, cx, cy, r):
        k = r * _K
        o = self.out
        o.append(f"{_n(cx + r)} {_n(cy)} m")
        o.append(f"{_n(cx + r)} {_n(cy + k)} {_n(cx + k)} {_n(cy + r)} {_n(cx)} {_n(cy + r)} c")
        o.append(f"{_n(cx - k)} {_n(cy + r)} {_n(cx - r)} {_n(cy + k)} {_n(cx - r)} {_n(cy)} c")
        o.append(f"{_n(cx - r)} {_n(cy - k)} {_n(cx - k)} {_n(cy - r)} {_n(cx)} {_n(cy - r)} c")
        o.append(f"{_n(cx + k)} {_n(cy - r)} {_n(cx + r)} {_n(cy - k)} {_n(cx + r)} {_n(cy)} c h")

    def cmds_path(self, cmds):
        cur = (0.0, 0.0)
        start = cur
        o = self.out
        for c in cmds:
            op = c[0]
            if op == "M":
                cur = start = (c[1], c[2])
                o.append(f"{_n(c[1])} {_n(c[2])} m")
            elif op == "L":
                cur = (c[1], c[2])
                o.append(f"{_n(c[1])} {_n(c[2])} l")
            elif op == "C":
                o.append(" ".join(_n(v) for v in c[1:]) + " c")
                cur = (c[5], c[6])
            elif op == "Q":
                qx, qy, x, y = c[1:]
                c1 = (cur[0] + 2 / 3 * (qx - cur[0]), cur[1] + 2 / 3 * (qy - cur[1]))
                c2 = (x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y))
                o.append(f"{_n(c1[0])} {_n(c1[1])} {_n(c2[0])} {_n(c2[1])} {_n(x)} {_n(y)} c")
                cur = (x, y)
            elif op == "Z":
                o.append("h")
                cur = start

    def hatch(self, spec, bbox, clip_fn):
        """Texture inside a shape: 45° lines (default) or ``colour|kind`` with kind in / \\ x - | ."""
        color, _, kind = spec.partition("|")
        kind = kind or "/"
        x0, y0, x1, y1 = bbox
        self.out.append("q")
        clip_fn()
        self.out.append("W n")
        w, h = x1 - x0, y1 - y0
        if kind == ".":
            self.fill_color(color)
            step = 5.0
            yy = y0 + 2.5
            while yy < y1:
                xx = x0 + 2.5
                while xx < x1:
                    self.out.append(f"{_n(xx - 0.9)} {_n(yy - 0.9)} 1.8 1.8 re")
                    xx += step
                yy += step
            self.out.append("f Q")
            return
        self.stroke_color(color)
        self.stroke_style(1.2)
        lines = []
        if kind in ("/", "x"):
            step, span, t = 5 / math.sqrt(2) * 2, w + h, -(w + h)
            while t < span:
                lines.append(f"{_n(x0 + t)} {_n(y1)} m {_n(x0 + t + h)} {_n(y0)} l")
                t += step
        if kind in ("\\", "x"):
            step, span, t = 5 / math.sqrt(2) * 2, w + h, -(w + h)
            while t < span:
                lines.append(f"{_n(x0 + t)} {_n(y0)} m {_n(x0 + t + h)} {_n(y1)} l")
                t += step
        if kind == "-":
            yy = y0 + 3
            while yy < y1:
                lines.append(f"{_n(x0)} {_n(yy)} m {_n(x1)} {_n(yy)} l")
                yy += 6
        if kind == "|":
            xx = x0 + 3
            while xx < x1:
                lines.append(f"{_n(xx)} {_n(y0)} m {_n(xx)} {_n(y1)} l")
                xx += 6
        self.out.extend(lines)
        self.out.append("S Q")

    def marker(self, shape, x, y, r):
        if shape == "circle":
            self.circle_path(x, y, r)
        elif shape == "square":
            self.out.append(f"{_n(x - r)} {_n(y - r)} {_n(2 * r)} {_n(2 * r)} re")
        elif shape == "triangle":
            self.out.append(f"{_n(x)} {_n(y - r * 1.2)} m {_n(x + r * 1.1)} {_n(y + r * 0.8)} l "
                            f"{_n(x - r * 1.1)} {_n(y + r * 0.8)} l h")
        elif shape == "diamond":
            self.out.append(f"{_n(x)} {_n(y - r * 1.25)} m {_n(x + r)} {_n(y)} l {_n(x)} {_n(y + r * 1.25)} l "
                            f"{_n(x - r)} {_n(y)} l h")
        elif shape == "cross":
            self.out.append(f"{_n(x - r)} {_n(y)} m {_n(x + r)} {_n(y)} l {_n(x)} {_n(y - r)} m {_n(x)} {_n(y + r)} l")
        elif shape == "x":
            k = r * 0.8
            self.out.append(f"{_n(x - k)} {_n(y - k)} m {_n(x + k)} {_n(y + k)} l {_n(x - k)} {_n(y + k)} m "
                            f"{_n(x + k)} {_n(y - k)} l")

    # -- ops
    def op(self, op):
        o = self.out
        t = type(op)
        if t is S.Rect:
            if op.w <= 0 or op.h <= 0:
                return
            o.append("q")
            self.rect_path(op.x, op.y, op.w, op.h, op.rx)
            self.paint(op.fill, op.stroke, op.stroke_width, op.opacity, dash=op.dash)
            o.append("Q")
            if op.hatch:
                self.hatch(op.hatch, (op.x, op.y, op.x + op.w, op.y + op.h),
                           lambda: self.rect_path(op.x, op.y, op.w, op.h, op.rx))
        elif t is S.Line:
            o.append("q")
            o.append(f"{_n(op.x1)} {_n(op.y1)} m {_n(op.x2)} {_n(op.y2)} l")
            self.paint(None, op.stroke, op.stroke_width, op.opacity, dash=op.dash, cap=op.cap)
            o.append("Q")
        elif t is S.Polyline:
            xs, ys = np.asarray(op.xs, float), np.asarray(op.ys, float)
            ok = np.isfinite(xs) & np.isfinite(ys)
            if not ok.any():
                return
            o.append("q")
            pen = False
            for x, y, good in zip(xs.tolist(), ys.tolist(), ok.tolist()):
                if not good:
                    pen = False
                    continue
                o.append(f"{_n(x)} {_n(y)} {'l' if pen else 'm'}")
                pen = True
            if op.closed:
                o.append("h")
            self.paint(op.fill, op.stroke, op.stroke_width, op.opacity, op.fill_opacity, op.dash, op.cap, op.join)
            o.append("Q")
            if op.hatch and op.closed:
                px, py = xs[ok], ys[ok]

                def poly():
                    o.append(f"{_n(px[0])} {_n(py[0])} m " + " ".join(f"{_n(a)} {_n(b)} l" for a, b in
                                                                      zip(px[1:].tolist(), py[1:].tolist())) + " h")
                self.hatch(op.hatch, (float(px.min()), float(py.min()), float(px.max()), float(py.max())), poly)
        elif t is S.Path:
            o.append("q")
            self.cmds_path(op.cmds)
            self.paint(op.fill, op.stroke, op.stroke_width, op.opacity, op.fill_opacity, op.dash, op.cap, op.join,
                       evenodd=op.evenodd)
            o.append("Q")
            if op.hatch:
                xs = [v for c in op.cmds for v in c[1::2]]
                ys = [v for c in op.cmds for v in c[2::2]]
                self.hatch(op.hatch, (min(xs), min(ys), max(xs), max(ys)), lambda: self.cmds_path(op.cmds))
            if op.arrow and op.stroke:
                self.arrow(op)
        elif t is S.Markers:
            self.markers(op)
        elif t is S.Text:
            self.text(op)
        elif t is S.Image:
            name = f"Im{len(self.images)}"
            self.images.append((name, op.rgba))
            o.append(f"q {_n(op.w)} 0 0 {_n(-op.h)} {_n(op.x)} {_n(op.y + op.h)} cm /{name} Do Q")
        elif t is S.Clip:
            o.append(f"q {_n(op.x)} {_n(op.y)} {_n(op.w)} {_n(op.h)} re W n")
        elif t is S.EndClip:
            o.append("Q")
        elif t is S.Group:
            o.append(f"q 1 0 0 1 {_n(op.dx)} {_n(op.dy)} cm")
            for child in op.ops:
                self.op(child)
            o.append("Q")

    def arrow(self, op: S.Path):
        pts = [(c[-2], c[-1]) for c in op.cmds if c[0] != "Z"]
        if len(pts) < 2:
            return
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        last = op.cmds[-1]
        if last[0] in ("Q", "C"):
            x0, y0 = last[-4], last[-3]
        a = math.atan2(y1 - y0, x1 - x0)
        size = 7
        p1 = (x1 - size * math.cos(a - 0.4), y1 - size * math.sin(a - 0.4))
        p2 = (x1 - size * math.cos(a + 0.4), y1 - size * math.sin(a + 0.4))
        self.out.append("q")
        self.out.append(f"{_n(x1)} {_n(y1)} m {_n(p1[0])} {_n(p1[1])} l {_n(p2[0])} {_n(p2[1])} l h")
        self.paint(op.stroke, None, opacity=op.opacity)
        self.out.append("Q")

    def markers(self, op: S.Markers):
        xs, ys = np.asarray(op.xs, float), np.asarray(op.ys, float)
        n = len(xs)
        sizes = np.broadcast_to(np.asarray(op.size, float), (n,))
        fills = op.fill if isinstance(op.fill, (list, tuple, np.ndarray)) else None
        strokes = op.stroke if isinstance(op.stroke, (list, tuple, np.ndarray)) else None
        line_only = op.shape in ("cross", "x")
        for i in range(n):
            if not (math.isfinite(xs[i]) and math.isfinite(ys[i])):
                continue
            f = None if line_only else (fills[i] if fills is not None else op.fill)
            s = strokes[i] if strokes is not None else op.stroke
            if line_only and not s:
                s = f or (fills[i] if fills is not None else op.fill)
            self.out.append("q")
            self.marker(op.shape, xs[i], ys[i], sizes[i])
            self.paint(f, s, op.stroke_width, op.opacity, op.fill_opacity, cap="round" if line_only else "butt")
            self.out.append("Q")

    def face(self, kind: str, bold: bool, italic: bool) -> str:
        """Resource name of the embedded face for a style (faces that are not bundled share another style's font)."""
        font = _ttf.load(kind, bold, italic)
        key = (id(font),)
        name = self._face_by_key.get(key)
        if name is None:
            name = f"F{len(self.faces) + 1}"
            self._face_by_key[key] = name
            self.faces[name] = (font, {})
        return name

    def _glyphs(self, font, used: dict, text: str) -> tuple[str, float]:
        """Hex string of glyph ids for ``text`` and its advance width in em."""
        for a, b in _REPLACE.items():
            if font.glyph_index(a) == 0:
                text = text.replace(a, b)
        codes, adv = [], 0.0
        for ch in text:
            gid = font.glyph_index(ch)
            if gid == 0:
                gid = font.glyph_index("?")
                ch = "?"
            used.setdefault(gid, ch)
            codes.append(f"{gid:04X}")
            adv += font.advance(gid)
        return "".join(codes), adv

    def text(self, op: S.Text):
        if not op.text and not op.spans:
            return
        kind = self.scene.font_kind if self.scene.font_kind in _FAMILIES else "sans"
        factor = KIND_FACTOR[kind]
        runs = op.spans or [(op.text, op.weight, op.italic, None)]
        encoded = None
        if self.embed:
            encoded = []
            for t, wt, it, _col in runs:
                name = self.face(kind, wt >= 600, bool(it))
                font, used = self.faces[name]
                hexs, adv = self._glyphs(font, used, t)
                encoded.append((name, hexs, adv))
            w = sum(a for _, _, a in encoded) * op.size
            w += op.letter_spacing * max(0, sum(len(h) // 4 for _, h, _ in encoded) - 1)
        else:
            w = sum(text_width(t, op.size, kind, wt >= 600) for t, wt, _, _ in runs) / factor
            w += op.letter_spacing * max(0, len(op.text) - 1)
        shift = {"start": 0.0, "middle": -w / 2, "end": -w}[op.anchor]
        th = math.radians(op.rotate)
        c, s = math.cos(th), math.sin(th)
        by = baseline_shift(op.baseline, op.size)
        # offset along the rotated baseline and perpendicular to it
        x = op.x + shift * c - by * s
        y = op.y + shift * s + by * c
        tm = f"{_n(c)} {_n(s)} {_n(s)} {_n(-c)} {_n(x)} {_n(y)} Tm"
        spacing = f"{_n(op.letter_spacing)} Tc " if op.letter_spacing else ""

        def body(with_color: bool) -> str:
            parts = []
            for k, (t, wt, it, col) in enumerate(runs):
                if with_color:
                    r, g, b, _ = parse(col or op.color)
                    parts.append(f"{_n(r)} {_n(g)} {_n(b)} rg")
                # Tj advances the text position, so runs flow one after another
                if encoded is not None:
                    name, hexs, _adv = encoded[k]
                    parts.append(f"/{name} {_n(op.size)} Tf <{hexs}> Tj")
                else:
                    font = {(False, False): "F1", (True, False): "F2", (False, True): "F3", (True, True): "F4"}[(wt >= 600, it)]
                    parts.append(f"/{font} {_n(op.size)} Tf ({_enc(t).decode('latin-1')}) Tj")
            return " ".join(parts)

        if op.halo:
            self.out.append("q")
            self.stroke_color(op.halo)
            self.out.append(f"BT {spacing}1 Tr 3 w 1 j {tm} {body(False)} ET Q")
        self.out.append("q")
        a = parse(op.color)[3]
        self.alpha(a, 1.0)
        self.out.append(f"BT {spacing}{tm} {body(True)} ET Q")


def _embedded_font_objects(add, font, used: dict) -> int:
    """Add the objects of one embedded TrueType font and return the id of its Type0 font."""
    raw = font.data
    comp = zlib.compress(raw, 9)
    ffile = add(f"<< /Length {len(comp)} /Length1 {len(raw)} /Filter /FlateDecode >>\nstream\n".encode() + comp + b"\nendstream")
    u = font.units
    bb = " ".join(str(round(v * 1000 / u)) for v in font.bbox)
    name = font.postscript_name
    fixed = font.advance(font.glyph_index("i")) == font.advance(font.glyph_index("M"))
    flags = 4 | (1 if fixed else 0) | (64 if font.italic_angle else 0)
    desc = add(f"<< /Type /FontDescriptor /FontName /{name} /Flags {flags} /FontBBox [{bb}] "
               f"/ItalicAngle {_n(font.italic_angle)} /Ascent {round(font.ascent * 1000 / u)} "
               f"/Descent {round(font.descent * 1000 / u)} /CapHeight {round(font.cap_height * 1000 / u)} /StemV 80 "
               f"/FontFile2 {ffile} 0 R >>".encode())
    widths = " ".join(f"{g} [{round(font.advance(g) * 1000)}]" for g in sorted(used))
    cid = add(f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /{name} /CIDSystemInfo << /Registry (Adobe) "
              f"/Ordering (Identity) /Supplement 0 >> /FontDescriptor {desc} 0 R /DW 0 /W [{widths}] "
              f"/CIDToGIDMap /Identity >>".encode())
    bf = "\n".join(f"<{g:04X}> <{ord(ch):04X}>" if ord(ch) < 0x10000 else f"<{g:04X}> <FFFD>" for g, ch in sorted(used.items()))
    cmap = (f"/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) "
            f"/Ordering (UCS) /Supplement 0 >> def /CMapName /Adobe-Identity-UCS def /CMapType 2 def "
            f"1 begincodespacerange <0000> <FFFF> endcodespacerange {len(used)} beginbfchar\n{bf}\nendbfchar "
            f"endcmap CMapName currentdict /CMap defineresource pop end end").encode()
    cm = zlib.compress(cmap, 6)
    tou = add(f"<< /Length {len(cm)} /Filter /FlateDecode >>\nstream\n".encode() + cm + b"\nendstream")
    return add(f"<< /Type /Font /Subtype /Type0 /BaseFont /{name} /Encoding /Identity-H "
               f"/DescendantFonts [{cid} 0 R] /ToUnicode {tou} 0 R >>".encode())


def render(scene: S.Scene, embed_fonts: bool = True) -> bytes:
    w = _Writer(scene, embed_fonts)
    W, H = scene.width, scene.height
    w.out.append(f"{_n(PT)} 0 0 {_n(-PT)} 0 {_n(H * PT)} cm")
    w.out.append("q")
    w.rect_path(0, 0, W, H)
    w.paint(scene.background, None)
    w.out.append("Q")
    for op in scene.ops:
        w.op(op)
    content = zlib.compress("\n".join(w.out).encode("latin-1"), 6)

    objs: list[bytes] = []

    def add(obj: bytes) -> int:
        objs.append(obj)
        return len(objs)

    kind = scene.font_kind if scene.font_kind in _FAMILIES else "sans"
    if embed_fonts:
        font_res = {name: _embedded_font_objects(add, font, used) for name, (font, used) in w.faces.items()}
    else:
        font_res = {f"F{i + 1}": add(f"<< /Type /Font /Subtype /Type1 /BaseFont /{name} /Encoding /WinAnsiEncoding >>".encode())
                    for i, name in enumerate(_FAMILIES[kind])}
    gs_ids = {name: add(f"<< /Type /ExtGState /ca {_n(k[0])} /CA {_n(k[1])} >>".encode())
              for k, name in w.gstates.items()}
    img_ids = {}
    for name, rgba in w.images:
        a = np.ascontiguousarray(rgba, dtype=np.uint8)
        h_, w_ = a.shape[:2]
        rgb = zlib.compress(a[..., :3].tobytes(), 6)
        alpha = zlib.compress(a[..., 3].tobytes(), 6) if a.shape[2] == 4 else None
        smask = None
        if alpha is not None:
            smask = add(f"<< /Type /XObject /Subtype /Image /Width {w_} /Height {h_} /ColorSpace /DeviceGray "
                        f"/BitsPerComponent 8 /Filter /FlateDecode /Length {len(alpha)} >>\nstream\n".encode()
                        + alpha + b"\nendstream")
        sm = f" /SMask {smask} 0 R" if smask else ""
        img_ids[name] = add(f"<< /Type /XObject /Subtype /Image /Width {w_} /Height {h_} /ColorSpace /DeviceRGB "
                            f"/BitsPerComponent 8 /Filter /FlateDecode{sm} /Length {len(rgb)} >>\nstream\n".encode()
                            + rgb + b"\nendstream")
    content_id = add(f"<< /Length {len(content)} /Filter /FlateDecode >>\nstream\n".encode() + content + b"\nendstream")
    fonts = " ".join(f"/{n} {fid} 0 R" for n, fid in font_res.items())
    gs = " ".join(f"/{n} {i} 0 R" for n, i in gs_ids.items())
    xo = " ".join(f"/{n} {i} 0 R" for n, i in img_ids.items())
    res = f"<< /Font << {fonts} >>" + (f" /ExtGState << {gs} >>" if gs else "") + \
          (f" /XObject << {xo} >>" if xo else "") + " >>"
    pages_id = len(objs) + 2
    page_id = add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {_n(W * PT)} {_n(H * PT)}] "
                  f"/Resources {res} /Contents {content_id} 0 R >>".encode())
    add(f"<< /Type /Pages /Kids [{page_id} 0 R] /Count 1 >>".encode())
    title = _enc(scene.description or "Chart").decode("latin-1")
    info_id = add(f"<< /Producer (lineova) /Title ({title}) >>".encode("latin-1"))
    catalog_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())

    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(buf))
        buf += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(buf)
    buf += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        buf += f"{off:010d} 00000 n \n".encode()
    buf += (f"trailer\n<< /Size {len(objs) + 1} /Root {catalog_id} 0 R /Info {info_id} 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    return bytes(buf)
