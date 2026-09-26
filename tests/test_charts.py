import warnings

import numpy as np
import pytest

import lineova as lv
from lineova import scene as S

import xml.etree.ElementTree as ET

pd = pytest.importorskip("pandas")
THEMES = ["folio", "ledger", "instrument", "fjord"]


def texts(chart):
    return [op.text for op in chart.build().ops if isinstance(op, S.Text)]


@pytest.fixture
def df(rng):
    return pd.DataFrame({
        "month": pd.date_range("2024-01-01", periods=24, freq="MS").repeat(3),
        "source": ["Solar", "Wind", "Hydro"] * 24,
        "gwh": rng.random(72) * 100,
    })


@pytest.mark.parametrize("theme", THEMES)
def test_every_chart_type_renders_valid_svg_and_pdf(theme, rng, df):
    charts = [
        lv.line(df, x="month", y="gwh", theme=theme, title="T"),
        lv.area(df, x="month", y="gwh", theme=theme),
        lv.bar({"a": 1, "b": 3, "c": 2}, theme=theme, highlight="b"),
        lv.scatter(x=rng.random(50), y=rng.random(50), size=rng.random(50), fit=True, theme=theme),
        lv.histogram(rng.normal(size=500), theme=theme),
        lv.heatmap(rng.normal(size=(5, 6)), theme=theme),
        lv.box({"a": rng.normal(size=100), "b": rng.normal(size=100)}, theme=theme),
        lv.network([("a", "b", 1), ("b", "c", 2), ("a", "c", 5)], path=("a", "c"), theme=theme),
    ]
    for c in charts:
        root = ET.fromstring(c.to_svg())
        assert root.tag.endswith("svg")
        pdf = c.to_pdf()
        assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")


def test_auto_grouping_makes_legend(df):
    t = texts(lv.line(df, x="month", y="gwh", theme="ledger"))
    assert {"Solar", "Wind", "Hydro"} <= set(t)


def test_direct_labels_in_folio(df):
    c = lv.line(df, x="month", y="gwh", theme="folio")
    assert c._legend_mode(c.resolved_theme, ["Solar", "Wind", "Hydro"]) == "direct"
    assert {"Solar", "Wind", "Hydro"} <= set(texts(c))


def test_single_series_has_no_legend():
    c = lv.line([1, 2, 3])
    assert c._legend_mode(c.resolved_theme, ["Series 1"]) == "none"


def test_highlight_mutes_others():
    c = lv.line({"a": [1, 2], "b": [2, 1], "c": [0, 1]}, highlight="b")
    c.build()
    colors, _ = c._assign_colors(c.resolved_theme, ["a", "b", "c"])
    assert colors["a"] == colors["c"] == c.resolved_theme.muted != colors["b"]


def test_palette_dict_and_single_colour():
    c = lv.line({"a": [1, 2], "b": [2, 1]}, palette={"a": "#ff0000"})
    colors, _ = c._assign_colors(c.resolved_theme, ["a", "b"])
    assert colors["a"] == "#ff0000" and colors["b"] != "#ff0000"
    c2 = lv.line({"a": [1, 2], "b": [2, 1]}, palette="#123456")
    assert set(c2._assign_colors(c2.resolved_theme, ["a", "b"])[0].values()) == {"#123456"}


def test_too_many_series_fold_to_other():
    data = {f"s{i}": [i, i + 1] for i in range(12)}
    c = lv.line(data)
    with pytest.warns(UserWarning, match="Other"):
        c.to_svg()


def test_unknown_option_suggests():
    with pytest.raises(TypeError, match="Did you mean 'title'"):
        lv.line([1, 2], titel="x")


def test_unknown_layer_option():
    with pytest.raises(TypeError, match="line"):
        lv.line([1, 2], not_a_thing=1)


def test_chainable_api(df):
    c = (lv.Chart(df, theme="fjord")
         .line(x="month", y="gwh")
         .title("Output", subtitle="GWh per month")
         .y_axis(range=(0, 120), label="GWh")
         .band(x=("2024-06-01", "2024-08-31"), label="Summer")
         .hline(100, "Target")
         .source("Grid operator")
         .size("wide"))
    t = texts(c)
    assert "Output" in t and "Summer" in t and "Target" in t and "Source: Grid operator" in t
    assert c.build().width == 960


def test_axis_options_log_and_format():
    c = lv.scatter(x=[1, 10, 100, 1000], y=[1, 2, 3, 4], x_scale="log", y_format="{:.1f}")
    t = texts(c)
    assert "1,000" in t and "1.0" in t


def test_explicit_ticks_and_labels():
    c = lv.line([1, 2, 3], x_ticks={0: "start", 2: "end"})
    assert {"start", "end"} <= set(texts(c))


def test_bar_inputs(df):
    assert lv.bar(["x", "y", "x", "x"]).build()
    c = lv.bar(df, x="source", y="gwh", agg="mean")
    c.build()
    assert set(c._layers[0].cats) == {"Solar", "Wind", "Hydro"}
    c = lv.bar(df, x="source", y="gwh", color="month")
    with pytest.warns(UserWarning, match="distinct colours"):
        c.build()
    assert len(c._layers[0].names) == 24


def test_bar_top_n_folds_tail():
    data = {f"c{i}": float(i) for i in range(40)}
    c = lv.bar(data)
    c.build()
    assert c._layers[0].cats[-1] == "Other (15)" and len(c._layers[0].cats) == 26


def test_bar_orientation_and_sorting():
    long = {"A very long category name": 3, "Another long category": 5, "Short-ish label here": 1}
    c = lv.bar(long, width=500)
    c.build()
    L = c._layers[0]
    assert L.horizontal and L.cats[0] == "Another long category"
    c = lv.bar({"Jan": 3, "Feb": 1, "Mar": 2})
    c.build()
    assert c._layers[0].cats == ["Jan", "Feb", "Mar"] and not c._layers[0].horizontal


def test_bar_stack_and_normalize():
    data = {"x": {"a": 1, "b": 3}, "y": {"a": 3, "b": 1}}
    c = lv.bar(data, normalize=True)
    c.build()
    assert np.allclose(c._layers[0].values.sum(axis=0), 1)


def test_histogram_matches_numpy(rng):
    v = rng.normal(size=10_000)
    c = lv.histogram(v)
    c.build()
    L = c._layers[0]
    ref, _ = np.histogram(v, bins=L.edges)
    assert np.array_equal(L.counts[0], ref)


def test_histogram_integer_data_one_bin_per_value():
    c = lv.histogram([1, 2, 2, 3, 3, 3, 6])
    c.build()
    L = c._layers[0]
    assert np.allclose(np.diff(L.edges), 1) and L.counts[0].sum() == 7


def test_heatmap_long_format_and_big_matrix(rng):
    long = pd.DataFrame({"r": ["a", "a", "b"], "c": ["x", "y", "x"], "v": [1.0, 2.0, 3.0]})
    c = lv.heatmap(long, x="c", y="r", value="v")
    c.build()
    assert c._layers[0].matrix.shape == (2, 2) and np.isnan(c._layers[0].matrix[1, 1])
    big = lv.heatmap(rng.normal(size=(3000, 2000)))
    assert any(isinstance(op, S.Image) for op in big.build().ops)


def test_box_stats(rng):
    from lineova.marks.box import box_stats
    v = rng.normal(size=1001)
    s = box_stats(v)
    assert s["med"] == pytest.approx(np.median(v))
    assert s["lo"] >= s["q1"] - 1.5 * (s["q3"] - s["q1"])


def test_big_scatter_uses_density(rng):
    n = 200_000
    c = lv.scatter(x=rng.normal(size=n), y=rng.normal(size=n))
    ops = c.build().ops
    assert any(isinstance(op, S.Image) for op in ops)
    assert len(c.to_svg()) < 2_000_000


def test_big_line_is_reduced():
    n = 1_000_000
    c = lv.line(np.sin(np.arange(n) / 1000))
    polys = [op for op in c.build().ops if isinstance(op, S.Polyline)]
    assert max(len(p.xs) for p in polys) < 10_000


def test_nan_breaks_line():
    svg = lv.line([1, 2, np.nan, 4, 5]).to_svg()
    assert svg.count("M") >= 2


def test_empty_chart_errors():
    with pytest.raises(ValueError):
        lv.Chart().to_svg()


def test_theme_customisation():
    brand = lv.themes.get("ledger").replace(accent="#0f766e")
    lv.themes.register("brand", brand)
    assert lv.line([1, 2], theme="brand").resolved_theme.accent == "#0f766e"
    with pytest.raises(TypeError):
        brand.replace(not_a_field=1)
    with pytest.raises(ValueError, match="Available"):
        lv.themes.get("nope")


def test_save_formats(tmp_path):
    c = lv.bar({"a": 1, "b": 2})
    assert c.save(tmp_path / "x.svg").endswith(".svg")
    assert (tmp_path / "x.svg").read_text().startswith("<svg")
    c.save(tmp_path / "x.pdf")
    assert (tmp_path / "x.pdf").read_bytes()[:4] == b"%PDF"
    with pytest.raises(ValueError, match="Unsupported"):
        c.save(tmp_path / "x.gif")


def test_png_when_a_backend_exists(tmp_path):
    from lineova.backends import png
    if not png.available():
        pytest.skip("no PNG backend installed")
    import os
    if "playwright" in png.available() and not os.environ.get("LINEOVA_TEST_PNG"):
        pytest.skip("set LINEOVA_TEST_PNG=1 to run the (slow) browser backend")
    data = lv.bar({"a": 1, "b": 2}).to_png()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_repr_svg_for_notebooks():
    assert lv.line([1, 2])._repr_svg_().startswith("<svg")
