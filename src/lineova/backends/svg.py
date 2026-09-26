"""Scene -> SVG string. Pure Python, no dependencies."""

from __future__ import annotations

import base64
import math
import hashlib
from html import escape

import numpy as np

from .. import scene as S
from ..raster import encode_png


def _f(v: float) -> str:
    s = f"{v:.2f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _dash(d) -> str:
    return f' stroke-dasharray="{" ".join(_f(x) for x in d)}"' if d else ""


def _paint(fill, stroke, sw, opacity=1.0, fill_opacity=1.0, dash=None, cap=None, join=None) -> str:
    a = [f' fill="{fill or "none"}"']
    if fill and fill_opacity < 1:
        a.append(f' fill-opacity="{_f(fill_opacity)}"')
    if stroke:
        a.append(f' stroke="{stroke}" stroke-width="{_f(sw)}"')
        if cap and cap != "butt":
            a.append(f' stroke-linecap="{cap}"')
        if join and join != "miter":
            a.append(f' stroke-linejoin="{join}"')
        a.append(_dash(dash))
    if opacity < 1:
        a.append(f' opacity="{_f(opacity)}"')
    return "".join(a)


def baseline_shift(baseline: str, size: float) -> float:
    """Vertical offset from the requested anchor to the alphabetic baseline."""
    if baseline == "middle":
        return size * 0.35
    if baseline == "hanging":
        return size * 0.78
    return 0.0


def _points(xs: np.ndarray, ys: np.ndarray) -> list[str]:
    """Split a polyline at NaNs, return one 'M..L..' string per finite run."""
    finite = np.isfinite(xs) & np.isfinite(ys)
    if finite.all():
        runs = [(0, len(xs))]
    else:
        idx = np.flatnonzero(np.diff(np.concatenate(([0], finite.view(np.int8), [0]))))
        runs = list(zip(idx[::2], idx[1::2]))
    out = []
    for a, b in runs:
        if b - a < 1:
            continue
        xr = np.round(xs[a:b], 2)
        yr = np.round(ys[a:b], 2)
        pts = [f"{x:g},{y:g}" for x, y in zip(xr.tolist(), yr.tolist())]
        out.append("M" + "L".join(pts) if len(pts) > 1 else f"M{pts[0]}h0")
    return out


def _path_d(cmds) -> str:
    parts = []
    for c in cmds:
        parts.append(c[0] + ",".join(_f(v) for v in c[1:]))
    return "".join(parts)


def _marker_d(shape: str, x: float, y: float, r: float) -> str:
    if shape == "square":
        return f"M{_f(x - r)},{_f(y - r)}h{_f(2 * r)}v{_f(2 * r)}h{_f(-2 * r)}Z"
    if shape == "triangle":
        return (f"M{_f(x)},{_f(y - r * 1.2)}L{_f(x + r * 1.1)},{_f(y + r * 0.8)}"
                f"L{_f(x - r * 1.1)},{_f(y + r * 0.8)}Z")
    if shape == "diamond":
        return f"M{_f(x)},{_f(y - r * 1.25)}L{_f(x + r)},{_f(y)}L{_f(x)},{_f(y + r * 1.25)}L{_f(x - r)},{_f(y)}Z"
    if shape == "cross":
        return f"M{_f(x - r)},{_f(y)}h{_f(2 * r)}M{_f(x)},{_f(y - r)}v{_f(2 * r)}"
    if shape == "x":
        k = r * 0.8
        return f"M{_f(x - k)},{_f(y - k)}L{_f(x + k)},{_f(y + k)}M{_f(x - k)},{_f(y + k)}L{_f(x + k)},{_f(y - k)}"
    raise ValueError(shape)


def render(scene: S.Scene) -> str:
    w, h = scene.width, scene.height
    out: list[str] = []
    defs: dict[str, str] = {}
    clip_n = 0
    uid = "\x00U\x00"   # replaced by a content hash at the end: stable across runs, unique across charts

    def hatch_id(color: str) -> str:
        key = f"{uid}h" + color.lstrip("#")
        if key not in defs:
            defs[key] = (f'<pattern id="{key}" width="5" height="5" patternUnits="userSpaceOnUse" '
                         f'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5" '
                         f'stroke="{color}" stroke-width="1.4"/></pattern>')
        return key

    def arrow_id(color: str) -> str:
        key = f"{uid}a" + color.lstrip("#")
        if key not in defs:
            defs[key] = (f'<marker id="{key}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
                         f'markerHeight="7" markerUnits="userSpaceOnUse" orient="auto">'
                         f'<path d="M0,1L10,5L0,9Z" fill="{color}"/></marker>')
        return key

    for op in scene.ops:
        t = type(op)
        if t is S.Rect:
            title = f"<title>{escape(op.title)}</title>" if op.title else ""
            rx = f' rx="{_f(op.rx)}"' if op.rx else ""
            geo = f'x="{_f(op.x)}" y="{_f(op.y)}" width="{_f(max(op.w, 0))}" height="{_f(max(op.h, 0))}"{rx}'
            body = f"<rect {geo}{_paint(op.fill, op.stroke, op.stroke_width, op.opacity, dash=op.dash)}"
            out.append(body + (f">{title}</rect>" if title else "/>"))
            if op.hatch:
                out.append(f'<rect {geo} fill="url(#{hatch_id(op.hatch)})" pointer-events="none"/>')
        elif t is S.Line:
            out.append(f'<line x1="{_f(op.x1)}" y1="{_f(op.y1)}" x2="{_f(op.x2)}" y2="{_f(op.y2)}"'
                       f'{_paint(None, op.stroke, op.stroke_width, op.opacity, dash=op.dash, cap=op.cap)}/>')
        elif t is S.Polyline:
            runs = _points(np.asarray(op.xs, float), np.asarray(op.ys, float))
            if not runs:
                continue
            d = "".join(r + ("Z" if op.closed else "") for r in runs)
            paint = _paint(op.fill, op.stroke, op.stroke_width, op.opacity, op.fill_opacity, op.dash, op.cap, op.join)
            out.append(f'<path d="{d}"{paint}/>')
        elif t is S.Path:
            title = f"<title>{escape(op.title)}</title>" if op.title else ""
            arrow = f' marker-end="url(#{arrow_id(op.stroke)})"' if op.arrow and op.stroke else ""
            paint = _paint(op.fill, op.stroke, op.stroke_width, op.opacity, op.fill_opacity, op.dash, op.cap, op.join)
            body = f'<path d="{_path_d(op.cmds)}"{paint}{arrow}'
            out.append(body + (f">{title}</path>" if title else "/>"))
            if op.hatch:
                out.append(f'<path d="{_path_d(op.cmds)}" fill="url(#{hatch_id(op.hatch)})" pointer-events="none"/>')
        elif t is S.Markers:
            _markers(op, out)
        elif t is S.Text:
            if not op.text:
                continue
            y = op.y + baseline_shift(op.baseline, op.size)
            attrs = [f'x="{_f(op.x)}" y="{_f(y)}" font-size="{_f(op.size)}" fill="{op.color}"']
            if op.anchor != "start":
                attrs.append(f'text-anchor="{op.anchor}"')
            if op.weight != 400:
                attrs.append(f'font-weight="{op.weight}"')
            if op.italic:
                attrs.append('font-style="italic"')
            if op.letter_spacing:
                attrs.append(f'letter-spacing="{_f(op.letter_spacing)}"')
            if op.rotate:
                attrs.append(f'transform="rotate({_f(op.rotate)} {_f(op.x)} {_f(op.y)})"')
            if op.halo:
                attrs.append(f'stroke="{op.halo}" stroke-width="3" stroke-linejoin="round" paint-order="stroke"')
            if op.spans:
                attrs.append('xml:space="preserve"')
                body = "".join(_tspan(t, w, it, c, op) for t, w, it, c in op.spans)
            else:
                body = escape(op.text)
            out.append(f"<text {' '.join(attrs)}>{body}</text>")
        elif t is S.Image:
            data = base64.b64encode(encode_png(op.rgba)).decode("ascii")
            rendering = "" if op.smooth else ' image-rendering="pixelated" style="image-rendering:pixelated"'
            out.append(f'<image x="{_f(op.x)}" y="{_f(op.y)}" width="{_f(op.w)}" height="{_f(op.h)}" '
                       f'preserveAspectRatio="none"{rendering} href="data:image/png;base64,{data}"/>')
        elif t is S.Clip:
            clip_n += 1
            cid = f"{uid}c{clip_n}"
            defs[cid] = f'<clipPath id="{cid}"><rect x="{_f(op.x)}" y="{_f(op.y)}" width="{_f(op.w)}" height="{_f(op.h)}"/></clipPath>'
            out.append(f'<g clip-path="url(#{cid})">')
        elif t is S.EndClip:
            out.append("</g>")
        else:  # pragma: no cover - defensive
            raise TypeError(f"Unknown scene op {t.__name__}")

    font = escape(scene.font, quote=True)
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{_f(w)}" height="{_f(h)}" '
            f'viewBox="0 0 {_f(w)} {_f(h)}" font-family="{font}" role="img">')
    parts = [head]
    if scene.description:
        parts.append(f"<desc>{escape(scene.description)}</desc>")
    if defs:
        parts.append("<defs>" + "".join(defs.values()) + "</defs>")
    parts.append(f'<rect width="100%" height="100%" fill="{scene.background}"/>')
    parts.extend(out)
    parts.append("</svg>")
    doc = "\n".join(parts)
    if uid in doc:
        doc = doc.replace(uid, "lv" + hashlib.sha1(doc.encode("utf-8")).hexdigest()[:8])
    return doc


def _tspan(text: str, weight: int, italic: bool, color, parent) -> str:
    a = []
    if weight != parent.weight:
        a.append(f' font-weight="{weight}"')
    if italic != parent.italic:
        a.append(f' font-style="{"italic" if italic else "normal"}"')
    if color and color != parent.color:
        a.append(f' fill="{color}"')
    return f"<tspan{''.join(a)}>{escape(text)}</tspan>"


def _markers(op: S.Markers, out: list[str]) -> None:
    xs = np.asarray(op.xs, float)
    ys = np.asarray(op.ys, float)
    n = len(xs)
    if n == 0:
        return
    sizes = np.broadcast_to(np.asarray(op.size, float), (n,))
    fills = op.fill if isinstance(op.fill, (list, tuple, np.ndarray)) else None
    strokes = op.stroke if isinstance(op.stroke, (list, tuple, np.ndarray)) else None
    common = []
    if fills is None:
        common.append(f'fill="{op.fill or "none"}"')
        if op.fill and op.fill_opacity < 1:
            common.append(f'fill-opacity="{_f(op.fill_opacity)}"')
    elif op.fill_opacity < 1:
        common.append(f'fill-opacity="{_f(op.fill_opacity)}"')
    if strokes is None and op.stroke:
        common.append(f'stroke="{op.stroke}"')
    if op.stroke or strokes is not None:
        common.append(f'stroke-width="{_f(op.stroke_width)}"')
    if op.opacity < 1:
        common.append(f'opacity="{_f(op.opacity)}"')
    out.append(f"<g {' '.join(common)}>")
    titles = op.titles
    circle = op.shape == "circle"
    for i in range(n):
        x, y, r = xs[i], ys[i], sizes[i]
        if not (math.isfinite(x) and math.isfinite(y)):
            continue
        extra = ""
        if fills is not None:
            extra += f' fill="{fills[i]}"'
        if strokes is not None:
            extra += f' stroke="{strokes[i]}"'
        tt = f"<title>{escape(titles[i])}</title>" if titles is not None else ""
        if circle:
            el = f'<circle cx="{_f(x)}" cy="{_f(y)}" r="{_f(r)}"{extra}'
            out.append(el + (f">{tt}</circle>" if tt else "/>"))
        else:
            el = f'<path d="{_marker_d(op.shape, x, y, r)}"{extra}'
            out.append(el + (f">{tt}</path>" if tt else "/>"))
    out.append("</g>")
