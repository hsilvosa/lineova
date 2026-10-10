import struct
import zlib

import numpy as np
import pytest

import lineova as lv
from lineova import _text
from lineova.backends import _ttf, native_png, png


def decode(data: bytes) -> np.ndarray:
    """Decode an 8-bit RGB/RGBA PNG (any filter type) without an imaging library."""
    assert data[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
    pos, idat, ihdr = 8, b"", None
    while pos < len(data):
        n, tag = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        assert struct.unpack(">I", data[pos + 8 + n:pos + 12 + n])[0] == zlib.crc32(tag + body) & 0xFFFFFFFF
        if tag == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    assert ihdr is not None
    w, h, depth, ctype = ihdr[:4]
    assert depth == 8
    c = {2: 3, 6: 4}[ctype]
    stride = w * c
    raw = np.frombuffer(zlib.decompress(idat), dtype=np.uint8).reshape(h, stride + 1)
    out = np.zeros((h, stride), dtype=np.uint8)
    for y in range(h):
        f, line = raw[y, 0], raw[y, 1:].astype(np.int32)
        prev = out[y - 1].astype(np.int32) if y else np.zeros(stride, dtype=np.int32)
        if f == 0:
            row = line
        elif f == 2:
            row = line + prev
        else:                                              # sub, average, paeth depend on the pixel to the left
            row = np.zeros(stride, dtype=np.int32)
            for i in range(stride):
                a = row[i - c] if i >= c else 0
                b = prev[i]
                cc = prev[i - c] if i >= c else 0
                if f == 1:
                    pred = a
                elif f == 3:
                    pred = (a + b) // 2
                else:
                    pa, pb, pc = abs(b - cc), abs(a - cc), abs(a + b - 2 * cc)
                    pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else cc)
                row[i] = (line[i] + pred) & 255
        out[y] = row & 255
    return out.reshape(h, w, c)


@pytest.fixture(autouse=True)
def native_only(monkeypatch):
    monkeypatch.setenv("LINEOVA_PNG_BACKEND", "native")


def test_png_needs_no_extra_install(monkeypatch):
    monkeypatch.delenv("LINEOVA_PNG_BACKEND")
    monkeypatch.setattr(png, "BACKENDS", {})
    monkeypatch.setattr(png, "ORDER", ("native",))
    img = decode(lv.bar({"a": 1, "b": 2}).to_png())
    assert img.shape[2] == 3 and img.shape[0] > 100
    assert "native" in png.available()


def test_size_follows_scale_and_dpi(tmp_path):
    c = lv.line([1, 3, 2], width=300, height=200)
    assert decode(c.to_png(scale=1)).shape[:2] == (200, 300)
    assert decode(c.to_png(scale=2)).shape[:2] == (400, 600)
    assert decode(c.to_png(dpi=192)).shape[:2] == (400, 600)
    out = tmp_path / "c.png"
    c.save(out)
    assert decode(out.read_bytes()).shape[:2] == (400, 600)


def test_background_and_dark_theme():
    light = decode(lv.line([1, 2], theme="ledger", width=200, height=120).to_png(scale=1))
    dark = decode(lv.line([1, 2], theme="ledger-dark", width=200, height=120).to_png(scale=1))
    assert light[2, 2].tolist() != dark[2, 2].tolist() and dark[2, 2].sum() < light[2, 2].sum()


def test_is_deterministic():
    c = lv.scatter(x=np.arange(50.0), y=np.arange(50.0) ** 0.5, fit=True)
    assert c.to_png() == c.to_png()


# ---------------------------------------------------------------- the rasteriser

def test_filled_rectangle_coverage_is_exact():
    cv = native_png.Canvas(10, 10, "#ffffff", 1.0)
    cv.fill_rect(2.5, 3.0, 6.25, 5.5, (0, 0, 0, 1.0))
    ink = 1 - cv.rgb[..., 0]
    assert ink.sum() == pytest.approx(3.75 * 2.5, abs=1e-4)
    assert ink[3, 2] == pytest.approx(0.5) and ink[3, 4] == pytest.approx(1.0) and ink[5, 4] == pytest.approx(0.5)


@pytest.mark.parametrize("r", [1.5, 4.0, 11.3])
def test_circle_area_matches_pi_r2(r):
    cv = native_png.Canvas(40, 40, "#ffffff", 1.0)
    cv.fill([native_png._orient(native_png._circle(20.3, 19.6, r))], (0, 0, 0, 1.0))
    assert (1 - cv.rgb[..., 0]).sum() == pytest.approx(np.pi * r * r, rel=0.03)


def test_even_odd_leaves_holes():
    outer = np.array([[2, 2], [18, 2], [18, 18], [2, 18]], float)
    inner = np.array([[6, 6], [14, 6], [14, 14], [6, 14]], float)
    cv = native_png.Canvas(20, 20, "#ffffff", 1.0)
    cv.fill([outer, inner], (0, 0, 0, 1.0), evenodd=True)
    ink = 1 - cv.rgb[..., 0]
    assert ink[10, 10] == pytest.approx(0) and ink[4, 4] == pytest.approx(1) and ink.sum() == pytest.approx(256 - 64)


def test_clip_limits_drawing():
    cv = native_png.Canvas(20, 20, "#ffffff", 1.0)
    cv.clips.append((5, 5, 10, 10))
    cv.fill_rect(0, 0, 20, 20, (0, 0, 0, 1.0))
    ink = 1 - cv.rgb[..., 0]
    assert ink.sum() == pytest.approx(25) and ink[7, 7] == 1 and ink[2, 2] == 0


def test_dashes_leave_gaps():
    cv = native_png.Canvas(60, 10, "#ffffff", 1.0)
    cv.stroke([np.array([[0.0, 5.0], [60.0, 5.0]])], 2.0, (0, 0, 0, 1.0), 1.0, dash=(4, 4))
    row = 1 - cv.rgb[5, :, 0]
    assert 0.4 < row.mean() < 0.6 and (row < 0.05).any() and (row > 0.95).any()


def test_stroke_width_and_round_cap():
    cv = native_png.Canvas(40, 20, "#ffffff", 1.0)
    cv.stroke([np.array([[10.0, 10.0], [30.0, 10.0]])], 4.0, (0, 0, 0, 1.0), 1.0, cap="round")
    assert (1 - cv.rgb[..., 0]).sum() == pytest.approx(20 * 4 + np.pi * 4, rel=0.04)


# ---------------------------------------------------------------- fonts and text

def test_bundled_fonts_match_the_layout_metrics():
    for kind, bold in (("sans", False), ("sans", True), ("serif", False), ("serif", True), ("mono", False)):
        font = _ttf.load(kind, bold, False)
        table = _text._TABLES.get((kind, bold))
        for ch in "AMWaegiqy0123456789.,%+-":
            adv = font.advance(font.glyph_index(ch)) * 1000
            ref = table[ord(ch) - 32] if table else 600
            assert adv == pytest.approx(ref, abs=2), (kind, bold, ch)


def test_fonts_cover_the_characters_charts_use():
    font = _ttf.load("sans", False, False)
    for ch in "ABC xyz 0123456789 −·→±€°%éñüÅ—–…×≤≥≈":
        assert font.glyph_index(ch) != 0, repr(ch)
    assert len(font.outline(font.glyph_index("g"))) == 2          # a glyph with a counter keeps its hole


def test_text_draws_ink_where_expected():
    from lineova import scene as S
    sc = S.Scene(120, 40, "#ffffff", "sans-serif", "sans")
    sc.add(S.Text(10, 28, "Hello", 20, "#000000"))
    img = decode(native_png.render_png(sc, 1.0))
    ink = 255 - img[..., 0].astype(int)
    ys, xs = np.nonzero(ink > 60)
    assert 10 <= xs.min() <= 14 and xs.max() < 10 + _text.text_width("Hello", 20) + 4
    assert ys.max() <= 30 and ys.min() >= 10                      # baseline at 28, cap height about 14


def test_text_anchor_rotation_and_halo():
    from lineova import scene as S
    sc = S.Scene(100, 100, "#ffffff", "sans-serif", "sans")
    sc.add(S.Text(50, 50, "abc", 14, "#000000", anchor="middle", baseline="middle", rotate=-90, halo="#ff0000"))
    img = decode(native_png.render_png(sc, 1.0))
    dark = np.argwhere(img.sum(axis=2) < 200)
    reds = np.argwhere((img[..., 0] > 200) & (img[..., 1] < 120))
    assert len(dark) and len(reds)
    assert np.ptp(dark[:, 0]) > np.ptp(dark[:, 1])                    # rotated: taller than wide
    assert abs(dark[:, 0].mean() - 50) < 8


def test_rich_text_spans_and_unknown_characters():
    from lineova import scene as S
    sc = S.Scene(200, 40, "#ffffff", "sans-serif", "sans")
    sc.add(S.Text(5, 25, "ab", 16, "#000000", spans=[("ab", 600, False, "#ff0000"), ("日本", 400, False, "#0000ff")]))
    img = decode(native_png.render_png(sc, 1.0))
    assert ((img[..., 0] > 150) & (img[..., 2] < 100)).any()        # the red span; unsupported glyphs fall back, no crash


# ---------------------------------------------------------------- against resvg

def _diff(chart):
    resvg = pytest.importorskip("resvg_py")
    from lineova.backends import svg
    sc = chart.build(raster_scale=2.0)
    ours = decode(native_png.render_png(sc, 2.0)).astype(float)
    theirs = decode(bytes(resvg.svg_to_bytes(svg_string=svg.render(sc), zoom=2.0))).astype(float)
    theirs = theirs[..., :ours.shape[2]] if theirs.shape[2] >= ours.shape[2] else theirs
    assert ours.shape[:2] == theirs.shape[:2]
    return np.abs(ours - theirs[..., :3]).mean()


@pytest.mark.parametrize("make", [
    lambda: lv.line(x=np.arange(80.0), y=np.sin(np.arange(80.0) / 7), title="Line", subtitle="sub"),
    lambda: lv.bar({"alpha": 3, "beta": 5, "gamma": 2}, title="Bars", theme="ledger"),
    lambda: lv.donut({"a": 3, "b": 2, "c": 1}, theme="fjord"),
    lambda: lv.heatmap(np.random.default_rng(0).normal(size=(6, 6)), theme="folio"),
    lambda: lv.network([("A", "B", 2), ("B", "C", 3), ("A", "C", 1)], directed=True, theme="fjord"),
    lambda: lv.chord([[0, 5, 2], [3, 0, 4], [1, 2, 0]], names=["A", "B", "C"], theme="fjord"),
    lambda: lv.line(x=np.arange(40.0), y=np.cos(np.arange(40.0) / 5), theme="ledger-dark"),
])
def test_close_to_resvg(make):
    assert _diff(make()) < 2.0            # mean absolute difference per channel, out of 255 (folio text uses another serif in resvg)


def test_every_chart_type_and_theme_renders():
    rng = np.random.default_rng(0)
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({"g": np.repeat(["A", "B"], 50), "v": rng.normal(size=100)})
    for theme in ("folio", "ledger", "instrument", "fjord", "ledger-dark"):
        for c in (lv.violin(df, x="g", y="v", theme=theme), lv.ridgeline(df, x="g", y="v", theme=theme),
                  lv.waterfall({"a": 5, "b": -2}, start=10, theme=theme),
                  lv.treemap({"x": {"a": 3, "b": 1}, "y": {"c": 2}}, theme=theme),
                  lv.sankey([("a", "b", 3), ("a", "c", 1)], theme=theme),
                  lv.radar({"s": {"p": 1, "q": 2, "r": 3}}, theme=theme),
                  lv.marimekko({"x": {"a": 1, "b": 2}, "y": {"a": 2, "b": 1}}, theme=theme),
                  lv.bar({"A": {"x": 3, "y": 4}}, texture=True, theme=theme),
                  lv.scatter(x=rng.normal(size=3000), y=rng.normal(size=3000), fit=True, theme=theme),
                  lv.hexbin(x=rng.normal(size=5000), y=rng.normal(size=5000), theme=theme),
                  lv.grid([lv.line([1, 2, 3]), lv.bar({"a": 1})], theme=theme)):
            img = decode(c.to_png(scale=1))
            assert img.std() > 5          # something was drawn


def test_large_chart_is_fast_enough():
    import time
    rng = np.random.default_rng(0)
    c = lv.scatter(x=rng.normal(size=2_000_000), y=rng.normal(size=2_000_000))
    t = time.perf_counter()
    c.to_png(scale=1)
    assert time.perf_counter() - t < 20
