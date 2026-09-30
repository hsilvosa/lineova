"""0.3 features: hexbin, sunburst, deep treemaps, maps, themes, accessibility, chunked aggregation."""

import re
import warnings
import xml.etree.ElementTree as ET

import numpy as np
import pytest

import lineova as lv
from lineova import DataError
from lineova._text import format_value

THEMES = lv.themes.names()


def svg_ok(chart) -> str:
    s = chart.to_svg()
    ET.fromstring(s)            # well-formed
    return s


# ------------------------------------------------------------------ hexbin

def test_hexbin_counts_add_up(rng):
    x, y = rng.normal(size=20_000), rng.normal(size=20_000)
    c = lv.hexbin(x=x, y=y, gridsize=20)
    svg_ok(c)
    layer = c._layers[0]
    assert layer.agg_name == "count"
    assert layer.val.sum() == pytest.approx(20_000)
    assert svg_ok(c).count("<path") >= len(layer.val)


def test_hexbin_mean_is_diverging_for_signed_values(rng):
    x, y = rng.normal(size=5000), rng.normal(size=5000)
    c = lv.hexbin(x=x, y=y, value=x * y)
    svg_ok(c)
    layer = c._layers[0]
    assert layer.diverging and layer.vmin == -layer.vmax


def test_hexbin_chunks_match_arrays(rng):
    x, y = rng.normal(size=40_000), rng.normal(size=40_000)
    parts = [{"a": x[i:i + 10_000], "b": y[i:i + 10_000]} for i in range(0, 40_000, 10_000)]
    c = lv.hexbin(lv.Chunks(parts), x="a", y="b")
    svg_ok(c)
    assert c._layers[0].val.sum() == pytest.approx(40_000)


def test_hexbin_errors():
    with pytest.raises(DataError):
        lv.hexbin(x=[1, 2], y=[1, 2], agg="mean").to_svg()


# ------------------------------------------------------------------ hierarchies

WORLD = {"Europe": {"Spain": {"Madrid": 7, "Barcelona": 5.6}, "France": {"Paris": 11, "Lyon": 2.3}},
         "Asia": {"Japan": {"Tokyo": 37, "Osaka": 19}}}


@pytest.mark.parametrize("theme", THEMES)
def test_sunburst_and_treemap_any_depth(theme):
    for fn in (lv.sunburst, lv.treemap):
        s = svg_ok(fn(WORLD, theme=theme, title="t"))
        assert "Tokyo" in s and "Madrid" in s


def test_hierarchy_from_dataframe_paths():
    pd = pytest.importorskip("pandas")
    rows = [(r, c, m, v) for r, cs in WORLD.items() for c, ms in cs.items() for m, v in ms.items()]
    df = pd.DataFrame(rows, columns=["region", "country", "city", "pop"])
    c = lv.sunburst(df, path=["region", "country", "city"], value="pop", depth=2)
    svg_ok(c)
    layer = c._layers[0]
    assert layer.root.value == pytest.approx(sum(r[3] for r in rows))
    assert layer.levels == 2
    t = lv.treemap(df, path=["region", "country", "city"], value="pop").table()
    assert t.columns == ["level 1", "level 2", "level 3", "value"] and len(t) == len(rows)


# ------------------------------------------------------------------ themes

def test_theme_variants_and_family():
    for name in ("ledger-dark", "folio-dark", "fjord-dark", "instrument-light"):
        t = lv.themes.get(name)
        assert t.family in ("ledger", "folio", "fjord", "instrument")
    assert lv.themes.dark("ledger").name == "ledger-dark"
    assert lv.themes.light("instrument").name == "instrument-light"
    # registering a derived theme keeps its family (so folio styling survives a rename)
    lv.themes.register("paper", lv.themes.get("folio").replace(font_size=12))
    assert lv.themes.get("paper").family == "folio"


@pytest.mark.parametrize("brand,bg", [("#e11d48", "#ffffff"), ("#2563eb", "#131821"), ("#16a34a", "#ffffff")])
def test_brand_theme_palette_passes_checks(brand, bg):
    t = lv.themes.from_brand(brand, dark=bg != "#ffffff")
    report = lv.themes.check_palette(t.palette, t.background)
    assert report.ok, str(report)
    assert len(t.palette) >= 6 and len(t.sequential) == 4


def test_check_palette_flags_confusable_neighbours():
    report = lv.themes.check_palette(["#2f5bd3", "#3060d0", "#d0527a"])
    assert not report.ok


def test_dark_palettes_validated():
    for name in ("ledger-dark", "instrument-light", "ledger", "instrument"):
        assert lv.themes.check_palette(name).ok, name


# ------------------------------------------------------------------ accessibility

def test_description_and_svg_metadata(rng):
    c = lv.line(x=np.arange(10), y=np.arange(10) * 2.0 + 1, title="Growth")
    text = c.describe()
    assert text.startswith("Growth.") and "up" in text
    s = svg_ok(c)
    assert "<title id=" in s and "<desc id=" in s and "aria-labelledby" in s
    assert lv.bar({"A": 3, "B": 5}, alt="Custom alt").describe() == "Custom alt"
    assert "Highest: B" in lv.bar({"A": 3, "B": 5}).describe()


def test_tables_round_trip():
    t = lv.bar({"A": 3, "B": 5}).table()
    assert t.columns == ["category", "value"]
    assert t.to_csv().splitlines()[1:] == ["A,3.0", "B,5.0"]
    assert "<table>" in t.to_html()


def test_texture_patterns_in_svg_and_pdf():
    c = lv.bar({"x": {"a": 1, "b": 2}, "y": {"a": 2, "b": 1}}, texture=True)
    s = svg_ok(c)
    assert s.count("<pattern") >= 2
    assert c.to_pdf().startswith(b"%PDF")


def test_html_has_readout_and_data(rng):
    c = lv.line(x=np.arange(50), y=rng.normal(size=50).cumsum(), title="Walk")
    html = c.to_html()
    assert 'id="lv-meta"' in html and '"series"' in html
    assert "Description and data" in html and "Download CSV" in html
    assert "Description and data" not in c.to_html(data=False)


# ------------------------------------------------------------------ chunked aggregation

@pytest.fixture
def chunked(rng):
    pd = pytest.importorskip("pandas")
    frames = []
    for _ in range(4):
        n = 20_000
        frames.append(pd.DataFrame({"day": rng.choice(["Mon", "Tue", "Wed"], n), "kind": rng.choice(["a", "b"], n),
                                    "v": rng.normal(10, 2, n)}))
    return frames, pd.concat(frames)


def test_chunked_bar_matches_pandas(chunked):
    frames, full = chunked
    c = lv.bar(lv.Chunks(frames), x="day", y="v", agg="mean", error="ci")
    svg_ok(c)
    got = dict(c.table().rows)
    want = full.groupby("day").v.mean().to_dict()
    assert list(got) == ["Mon", "Tue", "Wed"]            # calendar order
    for k in want:
        assert got[k] == pytest.approx(want[k])
    counts = lv.bar(lv.Chunks(frames), x="day", color="kind")
    svg_ok(counts)
    assert counts._layers[0].values.sum() == len(full)


def test_chunked_heatmap_and_box(chunked):
    frames, full = chunked
    h = lv.heatmap(lv.Chunks(frames), x="kind", y="day", value="v")
    svg_ok(h)
    m = h._layers[0].matrix
    assert m[0, 0] == pytest.approx(full[(full.day == "Mon") & (full.kind == "a")].v.mean())
    b = lv.box(lv.Chunks(frames), x="day", y="v")
    b._prepare_layers()
    st = b._layers[0].stats[0]
    ref = full[full.day == "Mon"].v
    assert st["n"] == len(ref)
    assert st["med"] == pytest.approx(ref.median(), abs=0.01)
    assert st["q3"] == pytest.approx(ref.quantile(0.75), abs=0.01)
    svg_ok(lv.violin(lv.Chunks(frames), x="kind", y="v"))


# ------------------------------------------------------------------ maps

def square(x0, y0, s=1.0):
    return [[x0, y0], [x0 + s, y0], [x0 + s, y0 + s], [x0, y0 + s], [x0, y0]]


GEO = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"name": "Álava"}, "geometry": {"type": "Polygon", "coordinates": [square(0, 40, 2), square(0.5, 40.5, 1)]}},
    {"type": "Feature", "properties": {"name": "Beta"}, "geometry": {"type": "MultiPolygon", "coordinates": [[square(3, 40)], [square(5, 40)]]}},
]}


def test_choropleth_joins_names_and_draws_holes():
    c = lv.map({"alava": 1.0, "BETA": 3.0}, geo=GEO, key="name")
    s = svg_ok(c)
    assert 'fill-rule="evenodd"' in s
    assert "Álava: 1" in s and "Beta: 3" in s
    pdf = c.to_pdf()
    streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S)
    import zlib
    body = b"".join(zlib.decompress(x) if x[:1] == b"x" else x for x in streams)
    assert b"f*" in body or b"B*" in body


def test_point_map_density_and_vector(rng):
    lon, lat = rng.uniform(-9, 3, 60_000), rng.uniform(36, 43, 60_000)
    s = svg_ok(lv.map(lon=lon, lat=lat))
    assert "<image" in s and "°N" in s
    s = svg_ok(lv.map(lon=lon[:300], lat=lat[:300], size=rng.random(300), color=rng.random(300)))
    assert "<circle" in s or "<use" in s


def test_tilemap_join_by_code_name_and_ine():
    c = lv.tilemap({"M": 1, "Barcelona": 2, "41": 3}, layout="es-provinces")
    svg_ok(c)
    assert c._layers[0].values == {"M": 1, "B": 2, "SE": 3}
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        lv.tilemap({"Atlantis": 1, "M": 2}).to_svg()
    assert any("Atlantis" in str(x.message) for x in w)
    svg_ok(lv.tilemap({"AN": 5, "Catalonia": 3}, layout="es-regions", names=True))


# ------------------------------------------------------------------ graphs & details

def test_sampled_betweenness_close_to_exact():
    nx = pytest.importorskip("networkx")
    g = lv.Graph.from_networkx(nx.barabasi_albert_graph(600, 2, seed=3))
    exact, approx = g.betweenness(), g.betweenness(k=200, seed=1)
    a = np.array([exact[n] for n in exact])
    b = np.array([approx[n] for n in exact])
    assert np.corrcoef(a, b)[0, 1] > 0.95


def test_compact_numbers_roll_over():
    assert format_value(999_960) == "1M"
    assert format_value(12_000) == "12k"
    assert format_value(2_500_000) == "2.5M"


def test_no_zero_baseline_through_point_clouds(rng):
    s = lv.scatter(x=rng.normal(size=50), y=rng.normal(size=50), theme="ledger").to_svg()
    # the emphasised baseline is 1.5 wide; scatter plots keep only the dashed grid
    assert 'stroke-width="1.5"' not in s


def test_range_frame_labels_do_not_collide():
    c = lv.line(x=np.arange(24), y=np.linspace(12.3, 28.2, 24), theme="folio")
    s = c.to_svg()
    labels = re.findall(r">(\d+(?:\.\d+)?)</text>", s)
    assert "12.3" in labels and "28.2" in labels
