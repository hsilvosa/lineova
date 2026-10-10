"""Animated transitions between charts.

    anim = lv.animate(chart_a, chart_b, duration=1.2)      # or a list of three or more charts
    anim.save("transition.gif")                            # animated GIF (any PNG backend, or the built-in one)
    anim.save("transition.svg")                            # animated SVG (SMIL), plays in browsers and by itself
    anim.frame(0.5)                                        # the in-between chart as a Scene (or .frame_svg / .frame_png)

How it works: both charts are drawn into scenes, the drawing operations of the two scenes are aligned
(``difflib`` over a key per operation: bars with bars, lines with lines, a tick label with the same label),
and every matched pair is interpolated: positions, sizes, colours, point by point for lines (the shorter
line is resampled to the longer one). Operations that exist on one side only fade out or in; labels that
change fade across. Both charts must have the same pixel size.
"""

from __future__ import annotations

import difflib
from dataclasses import replace
from typing import Any

import numpy as np

from . import scene as S
from ._color import parse, to_hex
from ._data import DataError

EASES = {
    "linear": lambda t: t,
    "in-out": lambda t: t * t * (3 - 2 * t),
    "out": lambda t: 1 - (1 - t) ** 3,
    "in": lambda t: t ** 3,
    "cubic": lambda t: 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2,
}


# --------------------------------------------------------------------------- small helpers

def _lerp(a, b, t):
    return a + (b - a) * t


def _mix(a, b, t):
    """Linear mix of two colour strings (None means: no paint; the colour switches at the half-way point)."""
    if a == b:
        return a
    if a is None or b is None:
        return b if t >= 0.5 else a
    ra, rb = parse(a), parse(b)
    return to_hex(tuple(_lerp(x, y, t) for x, y in zip(ra[:3], rb[:3])))


def _color_seq(c, n):
    return list(c) if isinstance(c, (list, tuple, np.ndarray)) else [c] * n


def _mix_color_field(a, b, t, n):
    if not isinstance(a, (list, tuple, np.ndarray)) and not isinstance(b, (list, tuple, np.ndarray)):
        return _mix(a, b, t)
    la, lb = _color_seq(a, n), _color_seq(b, n)
    return [_mix(x, y, t) for x, y in zip(la, lb)]


def _resample(xs: np.ndarray, ys: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    """The same polyline with ``n`` points: the new points lie on the old segments, at equal index steps."""
    m = len(xs)
    if m == n:
        return xs, ys
    pos = np.linspace(0, m - 1, n)
    i = np.minimum(pos.astype(int), m - 2) if m > 1 else np.zeros(n, dtype=int)
    f = pos - i
    if m == 1:
        return np.full(n, xs[0]), np.full(n, ys[0])
    return xs[i] * (1 - f) + xs[i + 1] * f, ys[i] * (1 - f) + ys[i + 1] * f


def _structure(cmds) -> tuple:
    return tuple((c[0], len(c)) for c in cmds)


def _key(op) -> tuple:
    t = type(op)
    if t is S.Polyline:
        finite = bool(np.isfinite(np.asarray(op.xs, float)).all() and np.isfinite(np.asarray(op.ys, float)).all())
        return ("poly", op.closed, op.fill is not None, op.stroke is not None, finite, op.hatch is None)
    if t is S.Path:
        return ("path", _structure(op.cmds), op.fill is not None, op.stroke is not None, op.hatch is None)
    if t is S.Markers:
        return ("mk", op.shape)
    if t is S.Text:
        return ("text", op.text if not op.spans else "".join(s[0] for s in op.spans), op.anchor, op.rotate != 0)
    if t is S.Image:
        return ("img", id(op))                       # images cannot be morphed: they always cross-fade
    if t is S.Rect:
        return ("rect", op.hatch is None)
    if t is S.Group:
        return ("group",)
    return (t.__name__.lower(),)


# --------------------------------------------------------------------------- fading and interpolation

def _faded(op, k: float, background: str):
    """The op at visibility ``k`` (0 = gone, 1 = as drawn)."""
    t = type(op)
    if k >= 0.999:
        return op
    if t in (S.Rect, S.Line, S.Path, S.Polyline, S.Markers):
        return replace(op, opacity=op.opacity * k)
    if t is S.Text:
        spans = None
        if op.spans:
            spans = [(a, b, c, _mix(background, d or op.color, k)) for a, b, c, d in op.spans]
        return replace(op, color=_mix(background, op.color, k), spans=spans,
                       halo=op.halo if op.halo is None else _mix(background, op.halo, k))
    if t is S.Image:
        rgba = np.array(op.rgba, copy=True)
        if rgba.shape[2] == 4:
            rgba[..., 3] = np.round(rgba[..., 3] * k).astype(np.uint8)
        else:
            rgba = np.dstack((rgba, np.full(rgba.shape[:2], round(255 * k), dtype=np.uint8)))
        return replace(op, rgba=rgba)
    return op if k >= 0.5 else None             # clips, groups: structural, never fade


def _interp(a, b, t: float, bg: str):
    """Interpolated copy of two matched ops. Returns a list (a marker pair can leave extras)."""
    ty = type(a)
    if ty is S.Rect:
        return [replace(a, x=_lerp(a.x, b.x, t), y=_lerp(a.y, b.y, t), w=_lerp(a.w, b.w, t), h=_lerp(a.h, b.h, t),
                        rx=_lerp(a.rx, b.rx, t), opacity=_lerp(a.opacity, b.opacity, t), fill=_mix(a.fill, b.fill, t),
                        stroke=_mix(a.stroke, b.stroke, t), stroke_width=_lerp(a.stroke_width, b.stroke_width, t),
                        hatch=a.hatch if t < 0.5 else b.hatch, title=b.title if t >= 0.5 else a.title)]
    if ty is S.Line:
        return [replace(a, x1=_lerp(a.x1, b.x1, t), y1=_lerp(a.y1, b.y1, t), x2=_lerp(a.x2, b.x2, t),
                        y2=_lerp(a.y2, b.y2, t), stroke=_mix(a.stroke, b.stroke, t),
                        stroke_width=_lerp(a.stroke_width, b.stroke_width, t), opacity=_lerp(a.opacity, b.opacity, t),
                        dash=a.dash if t < 0.5 else b.dash)]
    if ty is S.Polyline:
        xa, ya = np.asarray(a.xs, float), np.asarray(a.ys, float)
        xb, yb = np.asarray(b.xs, float), np.asarray(b.ys, float)
        n = max(len(xa), len(xb))
        xa, ya = _resample(xa, ya, n)
        xb, yb = _resample(xb, yb, n)
        return [replace(a, xs=_lerp(xa, xb, t), ys=_lerp(ya, yb, t), stroke=_mix(a.stroke, b.stroke, t),
                        fill=_mix(a.fill, b.fill, t), stroke_width=_lerp(a.stroke_width, b.stroke_width, t),
                        opacity=_lerp(a.opacity, b.opacity, t), fill_opacity=_lerp(a.fill_opacity, b.fill_opacity, t),
                        dash=a.dash if t < 0.5 else b.dash, hatch=a.hatch if t < 0.5 else b.hatch)]
    if ty is S.Path:
        cmds = [(ca[0], *[_lerp(u, v, t) for u, v in zip(ca[1:], cb[1:])]) for ca, cb in zip(a.cmds, b.cmds)]
        return [replace(a, cmds=cmds, stroke=_mix(a.stroke, b.stroke, t), fill=_mix(a.fill, b.fill, t),
                        stroke_width=_lerp(a.stroke_width, b.stroke_width, t), opacity=_lerp(a.opacity, b.opacity, t),
                        fill_opacity=_lerp(a.fill_opacity, b.fill_opacity, t), title=b.title if t >= 0.5 else a.title,
                        hatch=a.hatch if t < 0.5 else b.hatch)]
    if ty is S.Markers:
        xa, ya = np.asarray(a.xs, float), np.asarray(a.ys, float)
        xb, yb = np.asarray(b.xs, float), np.asarray(b.ys, float)
        m = min(len(xa), len(xb))
        sa = np.broadcast_to(np.asarray(a.size, float), (len(xa),))
        sb = np.broadcast_to(np.asarray(b.size, float), (len(xb),))
        out = []
        if m:
            fill = _mix_color_field(_cut(a.fill, m), _cut(b.fill, m), t, m)
            stroke = _mix_color_field(_cut(a.stroke, m), _cut(b.stroke, m), t, m)
            out.append(replace(a, xs=_lerp(xa[:m], xb[:m], t), ys=_lerp(ya[:m], yb[:m], t), size=_lerp(sa[:m], sb[:m], t),
                               fill=fill, stroke=stroke, opacity=_lerp(a.opacity, b.opacity, t),
                               fill_opacity=_lerp(a.fill_opacity, b.fill_opacity, t),
                               stroke_width=_lerp(a.stroke_width, b.stroke_width, t),
                               titles=(b.titles[:m] if t >= 0.5 and b.titles is not None else
                                       (a.titles[:m] if a.titles is not None else None))))
        if len(xa) > m:                                     # points that only exist in A shrink away
            out.append(_faded(_slice_markers(a, m, len(xa)), 1 - t, bg))
        if len(xb) > m:                                     # points that only exist in B grow in
            out.append(_faded(_slice_markers(b, m, len(xb)), t, bg))
        return out
    if ty is S.Text:
        spans = a.spans if t < 0.5 else b.spans
        return [replace(a, x=_lerp(a.x, b.x, t), y=_lerp(a.y, b.y, t), size=_lerp(a.size, b.size, t),
                        color=_mix(a.color, b.color, t), rotate=_lerp(a.rotate, b.rotate, t), spans=spans,
                        halo=_mix(a.halo, b.halo, t) if a.halo and b.halo else (a.halo if t < 0.5 else b.halo))]
    if ty is S.Clip:
        return [replace(a, x=_lerp(a.x, b.x, t), y=_lerp(a.y, b.y, t), w=_lerp(a.w, b.w, t), h=_lerp(a.h, b.h, t))]
    return [a if t < 0.5 else b]


def _cut(c, m):
    return list(c)[:m] if isinstance(c, (list, tuple, np.ndarray)) else c


def _slice_markers(op: S.Markers, a: int, b: int) -> S.Markers:
    n = len(op.xs)

    def cut(v):
        return list(v)[a:b] if isinstance(v, (list, tuple, np.ndarray)) and len(v) == n else v
    size = np.asarray(op.size, float)
    return replace(op, xs=np.asarray(op.xs)[a:b], ys=np.asarray(op.ys)[a:b], size=size[a:b] if size.ndim else op.size,
                   fill=cut(op.fill), stroke=cut(op.stroke), titles=cut(op.titles))


# --------------------------------------------------------------------------- alignment

def _align(ops_a: list, ops_b: list) -> list:
    """List of (op_a | None, op_b | None) in drawing order; a pair of ops is morphed, a lone op fades."""
    ka, kb = [_key(o) for o in ops_a], [_key(o) for o in ops_b]
    out: list = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ka, kb, autojunk=False).get_opcodes():
        if tag == "equal":
            out.extend(zip(ops_a[i1:i2], ops_b[j1:j2]))
        else:
            out.extend((o, None) for o in ops_a[i1:i2])
            out.extend((None, o) for o in ops_b[j1:j2])
    return out


def _structural(op) -> bool:
    return type(op) in (S.Clip, S.EndClip, S.Group)


def _frame_ops(pairs: list, t: float, bg: str) -> list:
    out: list = []
    for a, b in pairs:
        if a is not None and b is not None:
            if type(a) is S.Group:
                out.append(S.Group(_lerp(a.dx, b.dx, t), _lerp(a.dy, b.dy, t), _frame_ops(_align(a.ops, b.ops), t, bg)))
            elif type(a) is S.EndClip:
                out.append(a)
            else:
                out.extend(_interp(a, b, t, bg))
        elif a is not None:
            if type(a) is S.Group:
                out.append(S.Group(a.dx, a.dy, _frame_ops([(o, None) for o in a.ops], t, bg)))
            elif _structural(a):
                out.append(a)
            else:
                f = _faded(a, 1 - _soft(t, 0.0, 0.6), bg)
                if f is not None:
                    out.append(f)
        else:
            assert b is not None
            if type(b) is S.Group:
                out.append(S.Group(b.dx, b.dy, _frame_ops([(None, o) for o in b.ops], t, bg)))
            elif _structural(b):
                out.append(b)
            else:
                f = _faded(b, _soft(t, 0.4, 1.0), bg)
                if f is not None:
                    out.append(f)
    return out


def _soft(t: float, a: float, b: float) -> float:
    """0 before ``a``, 1 after ``b``, smooth in between (lone elements fade within part of the transition)."""
    if t <= a:
        return 0.0
    if t >= b:
        return 1.0
    x = (t - a) / (b - a)
    return x * x * (3 - 2 * x)


def _balance(ops: list) -> list:
    """Make Clip / EndClip pairs balanced after fading removed or duplicated some of them."""
    depth, out = 0, []
    for op in ops:
        if type(op) is S.Clip:
            depth += 1
        elif type(op) is S.EndClip:
            if depth == 0:
                continue
            depth -= 1
        out.append(op)
    out.extend(S.EndClip() for _ in range(depth))
    return out


# --------------------------------------------------------------------------- the animation object

class Animation:
    """Transitions through two or more charts. ``frame(t)`` for ``t`` in [0, steps]; see ``lv.animate``."""

    def __init__(self, scenes: list, duration: float, ease: str, hold: float, loop: bool, bounce: bool, frames: int):
        w, h = scenes[0].width, scenes[0].height
        for sc in scenes[1:]:
            if abs(sc.width - w) > 0.5 or abs(sc.height - h) > 0.5:
                raise DataError(f"The charts have different sizes ({w:g}x{h:g} and {sc.width:g}x{sc.height:g}); "
                                "give them the same width and height, e.g. size=(640, 400).")
        self.scenes = scenes
        self.duration, self.hold, self.loop, self.bounce = float(duration), float(hold), bool(loop), bool(bounce)
        self.ease = EASES[ease]
        self.frames = int(frames)
        self._pairs = [_align(a.ops, b.ops) for a, b in zip(scenes, scenes[1:])]
        self.steps = len(self._pairs)

    # ---------------------------------------------------------------- frames
    def frame(self, t: float) -> S.Scene:
        """The scene at position ``t`` (0 = first chart, 1 = second, 2 = third ...), eased inside each step."""
        t = min(max(float(t), 0.0), float(self.steps))
        i = min(int(t), self.steps - 1)
        k = self.ease(t - i)
        a, b = self.scenes[i], self.scenes[i + 1]
        if k <= 0.0:
            return a
        if k >= 1.0:
            return b
        bg = _mix(a.background, b.background, k) or a.background
        sc = S.Scene(a.width, a.height, bg, a.font, a.font_kind, description=a.description if k < 0.5 else b.description,
                     title=a.title if k < 0.5 else b.title)
        sc.ops = _balance(_frame_ops(self._pairs[i], k, bg))
        return sc

    def positions(self) -> list[float]:
        """The ``t`` of every frame in play order (including holds and the return trip when ``bounce``)."""
        per = max(2, self.frames)
        fwd = []
        for s in range(self.steps):
            fwd.extend(s + j / per for j in range(per))
        fwd.append(float(self.steps))
        if self.bounce:
            fwd = fwd + fwd[-2:0:-1]
        return fwd

    def delays(self) -> list[float]:
        """Seconds each frame stays on screen."""
        pos = self.positions()
        step = self.duration / max(2, self.frames)
        out = [step] * len(pos)
        out[0] += self.hold
        out[pos.index(float(self.steps))] += self.hold
        return out

    def frame_svg(self, t: float) -> str:
        from .backends import svg
        return svg.render(self.frame(t))

    def frame_png(self, t: float, scale: float = 1.0) -> bytes:
        from .backends import png
        return png.render(self.frame(t), scale)

    # ---------------------------------------------------------------- outputs
    def to_gif(self, scale: float = 1.0, colors: int = 256) -> bytes:
        """Animated GIF (``scale`` 1 = the chart's pixel size; GIF has 256 colours, so smooth shading bands slightly)."""
        from .backends import _gif, png
        rgbs = []
        for t in self.positions():
            rgbs.append(_decode_rgb(png.render(self.frame(t), scale)))
        return _gif.encode(rgbs, [max(2, round(d * 100)) for d in self.delays()], loop=0 if self.loop else -1, colors=colors)

    def to_svg(self) -> str:
        """Animated SVG (SMIL): every frame is a group switched on in turn. Plays in browsers; no scripts."""
        from .backends import svg
        pos = self.positions()
        delays = self.delays()
        total = sum(delays)
        docs = [svg.render(self.frame(t)) for t in pos]
        head = docs[0][:docs[0].index(">") + 1]
        out = [head]
        times = np.concatenate(([0.0], np.cumsum(delays)))
        for i, doc in enumerate(docs):
            inner = doc[doc.index(">") + 1:doc.rindex("</svg>")]
            inner = _strip_meta(inner)
            uid = f"f{i}"
            inner = _prefix_ids(inner, uid)
            t0, t1 = times[i] / total, times[i + 1] / total
            last = i == len(docs) - 1
            # discrete steps: hidden until t0, shown until t1, hidden again (the last frame stays when not looping)
            on = (f'<animate attributeName="display" dur="{total:.3f}s" '
                  f'repeatCount="{"indefinite" if self.loop else 1}" calcMode="discrete" '
                  f'keyTimes="0;{t0:.5f};{t1:.5f}" values="{"inline" if i == 0 else "none"};inline;'
                  f'{"inline" if last and not self.loop else "none"}" fill="freeze"/>')
            out.append(f'<g display="{"inline" if i == 0 else "none"}">{on}{inner}</g>')
        out.append("</svg>")
        return "\n".join(out)

    def save(self, path, **kw) -> str:
        """Write ``.gif`` or ``.svg`` (chosen by the extension). Returns the path."""
        import os
        p = os.fspath(path)
        ext = os.path.splitext(p)[1].lower()
        if ext == ".gif":
            data = self.to_gif(**kw)
        elif ext == ".svg":
            data = self.to_svg().encode("utf-8")
        else:
            raise ValueError(f"Can't save an animation as {ext or 'this extension'!r}; use .gif or .svg.")
        with open(p, "wb") as fh:
            fh.write(data)
        return p

    def __repr__(self) -> str:
        return f"<lineova.Animation {self.steps + 1} charts, {self.duration:g}s per step>"


def _strip_meta(inner: str) -> str:
    """Drop the <title>/<desc> of a frame (only the first would matter, and they repeat in every frame)."""
    import re
    return re.sub(r"<(title|desc)[^>]*>.*?</\1>", "", inner, flags=re.S)


def _prefix_ids(inner: str, uid: str) -> str:
    import re
    ids = set(re.findall(r'\bid="([^"]+)"', inner))
    for i in ids:
        inner = inner.replace(f'id="{i}"', f'id="{uid}{i}"').replace(f"url(#{i})", f"url(#{uid}{i})")
    return inner


def _decode_rgb(data: bytes) -> np.ndarray:
    """RGB array of a PNG made by lineova's own encoder or by resvg / cairosvg / playwright."""
    import struct
    import zlib
    pos, idat, ihdr = 8, b"", None
    while pos < len(data):
        n, tag = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    assert ihdr is not None
    w, h, depth, ctype = ihdr[:4]
    c = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    stride = w * c
    raw = np.frombuffer(zlib.decompress(idat), dtype=np.uint8).reshape(h, stride + 1)
    out = np.zeros((h, stride), dtype=np.int32)
    for y in range(h):
        f, line = int(raw[y, 0]), raw[y, 1:].astype(np.int32)
        prev = out[y - 1] if y else np.zeros(stride, dtype=np.int32)
        if f == 0:
            row = line
        elif f == 2:
            row = line + prev
        elif f == 1:
            row = line.copy()
            for ch in range(c):
                row[ch::c] = np.cumsum(line[ch::c])
        else:
            row = np.zeros(stride, dtype=np.int32)
            for i in range(stride):
                a = row[i - c] if i >= c else 0
                b = prev[i]
                cc = prev[i - c] if i >= c else 0
                if f == 3:
                    pred = (a + b) // 2
                else:
                    pa, pb, pc = abs(b - cc), abs(a - cc), abs(a + b - 2 * cc)
                    pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else cc)
                row[i] = (line[i] + pred) & 255
        out[y] = row & 255
    img = out.reshape(h, w, c).astype(np.uint8)
    if c == 1:
        img = np.repeat(img, 3, axis=2)
    elif c == 2:
        img = np.repeat(img[..., :1], 3, axis=2)
    elif c == 4:                                   # composite on white
        a = img[..., 3:4].astype(np.float32) / 255.0
        img = np.round(img[..., :3] * a + 255 * (1 - a)).astype(np.uint8)
    return img


def animate(charts: Any, *more, frames: int = 24, duration: float = 1.2, ease: str = "in-out", hold: float = 0.5,
            loop: bool = False, bounce: bool = False) -> Animation:
    """Animate a transition from one chart to the next.

    ``lv.animate(a, b)`` or ``lv.animate([a, b, c])``. Charts of the same kind morph (bars grow, lines bend,
    points move, ticks slide); anything that has no counterpart fades. Both need the same pixel size.

    ``frames`` frames per step, ``duration`` seconds per step, ``ease`` ``"in-out"`` (default), ``"linear"``,
    ``"in"``, ``"out"`` or ``"cubic"``, ``hold`` seconds to rest on the first and last chart, ``loop=True`` to
    repeat, ``bounce=True`` to play back to the start. Save with ``.save("x.gif")`` or ``.save("x.svg")``.
    """
    items = list(charts) if isinstance(charts, (list, tuple)) else [charts]
    items += list(more)
    if len(items) < 2:
        raise DataError("animate() needs at least two charts.")
    if ease not in EASES:
        raise DataError(f"ease must be one of {', '.join(EASES)}.")
    if frames < 2:
        raise DataError("frames must be at least 2.")
    scenes = [it.build() for it in items]
    return Animation(scenes, duration, ease, hold, loop, bounce, frames)

