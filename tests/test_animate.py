import struct
import xml.etree.ElementTree as ET

import numpy as np
import pytest

import lineova as lv
from lineova import DataError
from lineova import scene as S


def bars(values, title="t", **kw):
    return lv.bar(values, title=title, width=320, height=220, y_range=(0, 10), theme="ledger", **kw)


class Bar:
    def __init__(self, op):
        ys = [v for c in op.cmds for v in c[2::2]] if op.cmds else [0]
        self.h = max(ys) - min(ys)


def rects(scene):
    """The drawn bars (rounded-bar paths) of a bar chart scene."""
    return [Bar(op) for op in scene.ops if isinstance(op, S.Path) and op.fill and op.opacity == 1 and op.cmds]


# ---------------------------------------------------------------- interpolation

def test_ends_reproduce_the_charts_exactly():
    a, b = bars({"A": 3, "B": 5}), bars({"A": 6, "B": 2})
    an = lv.animate(a, b)
    assert an.frame_svg(0) == a.to_svg() and an.frame_svg(1) == b.to_svg()
    assert an.frame(-5) is an.scenes[0] and an.frame(9) is an.scenes[1]


def test_bars_grow_between_the_two_charts():
    a, b = bars({"A": 3, "B": 5}), bars({"A": 6, "B": 2})
    an = lv.animate(a, b, ease="linear")
    ha = [r.h for r in rects(an.scenes[0])]
    hb = [r.h for r in rects(an.scenes[1])]
    mid = [r.h for r in rects(an.frame(0.5))]
    assert len(mid) == 2
    assert mid == pytest.approx([(x + y) / 2 for x, y in zip(ha, hb)], abs=1.0)
    quarter = [r.h for r in rects(an.frame(0.25))]
    assert quarter[0] > ha[0] and quarter[1] < ha[1]


def test_easing_functions():
    a, b = bars({"A": 2}), bars({"A": 8})
    h0, h1 = rects(a.build())[0].h, rects(b.build())[0].h
    for ease in ("linear", "in-out", "in", "out", "cubic"):
        an = lv.animate(a, b, ease=ease)
        assert an.frame(0.0) is an.scenes[0] and an.frame(1.0) is an.scenes[1]
        h = rects(an.frame(0.3))[0].h
        assert h0 < h < h1
    lin = rects(lv.animate(a, b, ease="linear").frame(0.3))[0].h
    assert rects(lv.animate(a, b, ease="in").frame(0.3))[0].h < lin < rects(lv.animate(a, b, ease="out").frame(0.3))[0].h


def test_lines_with_different_lengths_are_resampled():
    t1, t2 = np.arange(30.0), np.arange(80.0)
    a = lv.line(x=t1, y=np.sin(t1 / 4), width=320, height=220)
    b = lv.line(x=t2, y=np.cos(t2 / 9), width=320, height=220)
    an = lv.animate(a, b)
    polys = [op for op in an.frame(0.5).ops if isinstance(op, S.Polyline) and op.stroke and len(op.xs) > 5]
    assert polys and all(np.isfinite(p.xs).all() and np.isfinite(p.ys).all() for p in polys)
    assert len(polys[0].xs) == 80


def test_scatter_points_move_and_extra_points_fade():
    rng = np.random.default_rng(0)
    a = lv.scatter(x=rng.random(30), y=rng.random(30), width=320, height=220)
    b = lv.scatter(x=rng.random(45), y=rng.random(45), width=320, height=220)
    an = lv.animate(a, b)
    mk = [op for op in an.frame(0.5).ops if isinstance(op, S.Markers)]
    assert sorted(len(m.xs) for m in mk) == [15, 30]               # 30 morph, 15 new points grow in
    grow = min(mk, key=lambda m: len(m.xs))
    assert 0 < grow.opacity < 1
    assert 0 < an.frame(0.5).ops.__len__()


def test_only_in_one_chart_fades_and_labels_cross_fade():
    a = lv.bar({"A": 3, "B": 5}, title="Before", width=320, height=220)
    b = lv.bar({"A": 3, "B": 5, "C": 4}, title="After", width=320, height=220)
    an = lv.animate(a, b, ease="linear")
    def texts(sc):
        return {op.text: op.color for op in sc.ops if isinstance(op, S.Text)}

    start, mid, end = texts(an.scenes[0]), texts(an.frame(0.5)), texts(an.scenes[1])
    assert "C" in end and "C" not in start
    assert mid["C"] not in (end["C"],) and mid["Before"] != start["Before"] and mid["After"] != end["After"]


def test_different_chart_types_cross_fade_without_error():
    a = lv.bar({"A": 3, "B": 5}, width=320, height=220)
    b = lv.line(x=[1, 2, 3], y=[3, 1, 2], width=320, height=220)
    an = lv.animate([a, b, a])
    assert an.steps == 2
    for t in (0, 0.3, 0.5, 1, 1.5, 2):
        sc = an.frame(t)
        depth = 0
        for op in sc.ops:
            depth += isinstance(op, S.Clip) - isinstance(op, S.EndClip)
            assert depth >= 0
        assert depth == 0
        assert lv.animate(a, b).frame_svg(t)


def test_grids_and_images_animate():
    rng = np.random.default_rng(1)
    g1 = lv.grid([lv.line([1, 2, 3]), lv.bar({"a": 1})], cols=2, width=700)
    g2 = lv.grid([lv.line([3, 1, 2]), lv.bar({"a": 4})], cols=2, width=700)
    ET.fromstring(lv.animate(g1, g2).frame_svg(0.5))
    big1 = lv.scatter(x=rng.normal(size=80_000), y=rng.normal(size=80_000), width=320, height=220)
    big2 = lv.scatter(x=rng.normal(size=80_000) + 1, y=rng.normal(size=80_000), width=320, height=220)
    an = lv.animate(big1, big2)
    imgs = [op for op in an.frame(0.5).ops if isinstance(op, S.Image)]
    assert len(imgs) == 2 and {int(i.rgba[..., 3].max()) for i in imgs} != {255}
    ET.fromstring(an.frame_svg(0.5))


def test_validation():
    a, b = bars({"A": 1}), bars({"A": 2})
    with pytest.raises(DataError, match="at least two"):
        lv.animate(a)
    with pytest.raises(DataError, match="ease"):
        lv.animate(a, b, ease="bounce")
    with pytest.raises(DataError, match="frames"):
        lv.animate(a, b, frames=1)
    with pytest.raises(DataError, match="different sizes"):
        lv.animate(a, lv.bar({"A": 2}, width=400, height=220))
    with pytest.raises(ValueError, match="gif or .svg"):
        lv.animate(a, b).save("x.mp4")


def test_timeline_positions_and_delays():
    a, b, c = bars({"A": 1}), bars({"A": 2}), bars({"A": 3})
    an = lv.animate([a, b, c], frames=10, duration=1.0, hold=0.5)
    pos = an.positions()
    assert pos[0] == 0 and pos[-1] == 2 and len(pos) == 21 and pos == sorted(pos)
    d = an.delays()
    assert len(d) == len(pos) and d[0] == pytest.approx(0.6) and d[-1] == pytest.approx(0.6) and d[5] == pytest.approx(0.1)
    bounce = lv.animate(a, b, frames=10, bounce=True).positions()
    assert max(bounce) == 1 and bounce[-1] == pytest.approx(0.1) and len(bounce) == 20     # ends one frame before the start: seamless loop


# ---------------------------------------------------------------- GIF

def read_gif(data: bytes):
    """Minimal GIF reader: (width, height, loop, [(delay_cs, rgb frame composed on the previous ones)])."""
    assert data[:6] == b"GIF89a" and data[-1:] == b"\x3b"
    w, h, flags = struct.unpack("<HHB", data[6:11])
    pos = 13
    gct = np.frombuffer(data[pos:pos + 3 * (2 << (flags & 7))], dtype=np.uint8).reshape(-1, 3)
    pos += 3 * (2 << (flags & 7))
    loop, delay, trans, frames = None, 0, None, []
    canvas = np.zeros((h, w, 3), dtype=np.uint8)
    while data[pos] != 0x3B:
        if data[pos] == 0x21:
            label = data[pos + 1]
            pos += 2
            if label == 0xF9:
                gflags, delay, tidx = struct.unpack("<BHB", data[pos + 1:pos + 5])
                trans = tidx if gflags & 1 else None
                pos += 6
                continue
            if label == 0xFF:
                if data[pos + 1:pos + 12] == b"NETSCAPE2.0":
                    loop = struct.unpack("<H", data[pos + 14:pos + 16])[0]
            while data[pos] != 0:
                pos += data[pos] + 1
            pos += 1
        elif data[pos] == 0x2C:
            x, y, iw, ih, _f = struct.unpack("<HHHHB", data[pos + 1:pos + 10])
            pos += 10
            min_bits = data[pos]
            pos += 1
            blob = bytearray()
            while data[pos] != 0:
                blob += data[pos + 1:pos + 1 + data[pos]]
                pos += data[pos] + 1
            pos += 1
            idx = np.array(_lzw_decode(bytes(blob), min_bits, iw * ih), dtype=np.uint8).reshape(ih, iw)
            patch = gct[idx]
            mask = np.ones((ih, iw), bool) if trans is None else idx != trans
            region = canvas[y:y + ih, x:x + iw]
            region[mask] = patch[mask]
            frames.append((delay, canvas.copy()))
    return w, h, loop, frames


def _lzw_decode(blob: bytes, min_bits: int, count: int) -> list:
    clear, eoi = 1 << min_bits, (1 << min_bits) + 1
    size, nxt = min_bits + 1, eoi + 1
    table = {i: [i] for i in range(clear)}
    out, prev, acc, nb, pos = [], None, 0, 0, 0
    while len(out) < count:
        while nb < size:
            acc |= blob[pos] << nb
            nb += 8
            pos += 1
        code = acc & ((1 << size) - 1)
        acc >>= size
        nb -= size
        if code == clear:
            table = {i: [i] for i in range(clear)}
            size, nxt, prev = min_bits + 1, eoi + 1, None
            continue
        if code == eoi:
            break
        if prev is None:
            entry = table[code]
        else:
            entry = table[code] if code in table else table[prev] + [table[prev][0]]
            table[nxt] = table[prev] + [entry[0]]
            nxt += 1
            if nxt == (1 << size) and size < 12:
                size += 1
        out.extend(entry)
        prev = code
    return out[:count]


def test_gif_structure_and_pixels():
    a, b = bars({"A": 3, "B": 5}), bars({"A": 6, "B": 2})
    an = lv.animate(a, b, frames=6, duration=0.6, hold=0.4)
    w, h, loop, frames = read_gif(an.to_gif())
    assert (w, h) == (320, 220) and loop is None and len(frames) == len(an.positions()) == 7
    assert [d for d, _ in frames][0] == 50 and frames[3][0] == 10
    ref0 = native_frame(an, 0.0)
    assert np.abs(frames[0][1].astype(int) - ref0.astype(int)).mean() < 3
    last = native_frame(an, 1.0)
    assert np.abs(frames[-1][1].astype(int) - last.astype(int)).mean() < 3
    assert np.abs(frames[0][1].astype(int) - frames[-1][1].astype(int)).mean() > 1      # the chart did change


def native_frame(an, t):
    from lineova.animate import _decode_rgb
    return _decode_rgb(an.frame_png(t, 1.0))


def test_gif_loop_and_scale():
    a, b = bars({"A": 3}), bars({"A": 6})
    an = lv.animate(a, b, frames=3, loop=True)
    w, h, loop, frames = read_gif(an.to_gif(scale=0.5))
    assert loop == 0 and (w, h) == (160, 110) and len(frames) == 4


def test_gif_with_unchanged_frames_and_save(tmp_path):
    a = bars({"A": 3})
    an = lv.animate(a, a, frames=3)
    w, h, _, frames = read_gif(an.to_gif())
    assert len(frames) == 4 and all(np.array_equal(frames[0][1], f) for _, f in frames)
    out = tmp_path / "x.gif"
    an.save(out)
    assert out.read_bytes()[:6] == b"GIF89a"


def test_gif_palette_handles_many_colours():
    rng = np.random.default_rng(0)
    a = lv.scatter(x=rng.normal(size=60_000), y=rng.normal(size=60_000), width=240, height=180)
    b = lv.scatter(x=rng.normal(size=60_000) * 2, y=rng.normal(size=60_000), width=240, height=180)
    w, h, _, frames = read_gif(lv.animate(a, b, frames=3).to_gif())
    assert len(frames) == 4 and (w, h) == (240, 180)


def test_every_theme_transitions():
    for theme in ("folio", "ledger", "instrument", "fjord", "ledger-dark"):
        a = lv.line([1, 3, 2], theme=theme, width=300, height=200)
        b = lv.line([2, 1, 4, 3], theme=theme, width=300, height=200)
        read_gif(lv.animate(a, b, frames=2).to_gif())


# ---------------------------------------------------------------- SVG

def test_animated_svg_is_valid_and_switches_frames():
    a, b = bars({"A": 3, "B": 5}), bars({"A": 6, "B": 2})
    an = lv.animate(a, b, frames=4, duration=1.0, hold=0.5, loop=True)
    svg = an.to_svg()
    root = ET.fromstring(svg)
    ns = "{http://www.w3.org/2000/svg}"
    frames = [g for g in root if g.tag == ns + "g"]
    assert len(frames) == len(an.positions()) == 5
    assert [g.get("display") for g in frames] == ["inline"] + ["none"] * 4
    anims = [g.find(ns + "animate") for g in frames]
    assert all(x is not None and x.get("calcMode") == "discrete" and x.get("repeatCount") == "indefinite" for x in anims)
    ids = [e.get("id") for e in root.iter() if e.get("id")]
    assert len(ids) == len(set(ids))                               # per-frame prefixes keep clip ids unique
    once = ET.fromstring(lv.animate(a, b, frames=2).to_svg())
    last = [g for g in once if g.tag == ns + "g"][-1].find(ns + "animate")
    assert last is not None and last.get("values").endswith("inline") and last.get("repeatCount") == "1"


def test_save_svg(tmp_path):
    a, b = bars({"A": 3}), bars({"A": 6})
    p = lv.animate(a, b, frames=2).save(tmp_path / "x.svg")
    ET.parse(p)
