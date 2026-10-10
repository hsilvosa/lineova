import warnings
import xml.etree.ElementTree as ET

import numpy as np
import pytest

import lineova as lv
from lineova import DataError

THEMES = ["folio", "ledger", "instrument", "fjord", "ledger-dark"]


@pytest.fixture
def series(rng):
    t = np.arange(60.0)
    names = ["a", "b", "c", "d"]
    return {"x": np.tile(t, 4), "y": np.concatenate([np.abs(np.sin(t / (6 + i)) * 10 + rng.normal(size=60)) + 1
                                                     for i in range(4)]),
            "g": np.repeat(names, 60)}


def charts(theme, rng, series):
    y = rng.integers(0, 2, 400)
    s = y * 0.8 + rng.normal(size=400)
    cols = {f"v{i}": rng.normal(size=100) for i in range(4)}
    cols["g"] = rng.choice(["p", "q"], 100)
    edges = [(i, i + 1) for i in range(15)] + [(0, 7), (3, 12), (5, 14)]
    return [
        lv.chord([[0, 5, 2], [3, 0, 4], [1, 2, 0]], names=["A", "B", "C"], theme=theme),
        lv.chord([("a", "b", 3), ("b", "c", 2), ("c", "a", 1)], theme=theme),
        lv.arc(edges, theme=theme),
        lv.parallel(cols, color="g", theme=theme),
        lv.parallel(cols, color="v0", invert=["v1"], theme=theme),
        lv.streamgraph(series, x="x", y="y", color="g", theme=theme),
        lv.horizon(series, x="x", y="y", color="g", theme=theme),
        lv.marimekko({"EU": {"A": 3, "B": 2}, "US": {"A": 1, "B": 4}}, theme=theme),
        lv.bullet([{"label": "Rev", "value": 270, "target": 250, "ranges": [150, 225, 300]},
                   {"label": "NPS", "value": 41, "target": 50}], theme=theme),
        lv.roc(y, {"m1": s, "m2": -s}, theme=theme),
        lv.pr(y, s, theme=theme),
        lv.calibration(y, 1 / (1 + np.exp(-s)), theme=theme),
        lv.confusion_matrix(y, (s > 0.3).astype(int), normalize="true", theme=theme),
        lv.ecdf({"a": rng.normal(size=300), "b": rng.normal(size=50)}, theme=theme),
        lv.qq(rng.normal(size=200), theme=theme),
        lv.correlation(cols, theme=theme),
    ]


@pytest.mark.parametrize("theme", THEMES)
def test_new_charts_render_everywhere(theme, rng, series):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for c in charts(theme, rng, series):
            ET.fromstring(c.to_svg())
            assert c.to_pdf().startswith(b"%PDF")
            assert c.describe()
            assert "<svg" in c.to_html()


# ---------------------------------------------------------------- numbers

def test_roc_auc_and_chance():
    y = np.array([0, 0, 1, 1])
    svg = lv.roc(y, np.array([0.1, 0.4, 0.35, 0.8])).to_svg()
    assert "AUC 0.750" in svg
    perfect = lv.roc(y, np.array([0.1, 0.2, 0.8, 0.9])).to_svg()
    assert "AUC 1.000" in perfect
    assert "AUC 0.000" in lv.roc(y, -np.array([0.1, 0.2, 0.8, 0.9])).to_svg()


def test_roc_handles_tied_scores():
    y = np.array([0, 1, 0, 1, 0, 1])
    assert "AUC 0.500" in lv.roc(y, np.zeros(6)).to_svg()


def test_pr_average_precision():
    y = np.array([0, 0, 1, 1])
    assert "AP 0.833" in lv.pr(y, np.array([0.1, 0.4, 0.35, 0.8])).to_svg()


def test_roc_pr_validate():
    with pytest.raises(DataError, match="two classes"):
        lv.roc([0, 1, 2], [0.1, 0.2, 0.3])
    with pytest.raises(DataError, match="two classes"):
        lv.roc(np.array([True, True, True]), [0.1, 0.2, 0.3])
    with pytest.raises(DataError, match="scores"):
        lv.pr([0, 1, 0, 1], [0.1, 0.2, 0.3])


def test_calibration_brier():
    y = np.array([0, 1, 0, 1])
    p = np.array([0.0, 1.0, 0.0, 1.0])
    assert "Brier 0.000" in lv.calibration(y, p, bins=2).to_svg()
    with pytest.raises(DataError, match="lie in"):
        lv.calibration(y, np.array([0.2, 1.5, 0.1, 0.9]))


def test_confusion_matrix_counts_and_normalisation():
    t = ["a", "a", "b", "b", "b"]
    p = ["a", "b", "b", "b", "a"]
    c = lv.confusion_matrix(t, p, labels=["a", "b"])
    lay = c._layers[0]
    lay.prepare(c)
    assert lay.matrix.tolist() == [[1, 1], [1, 2]]
    r = lv.confusion_matrix(t, p, labels=["a", "b"], normalize="true")
    r._layers[0].prepare(r)
    assert np.allclose(r._layers[0].matrix.sum(axis=1), 1)
    with pytest.raises(DataError):
        lv.confusion_matrix(t, p[:-1])


def test_ecdf_is_monotone_and_ends_at_one():
    c = lv.ecdf(np.array([3.0, 1.0, 2.0, 2.0]))
    lay = c._layers[0]
    lay.prepare(c)
    s = lay.xy.series[0]
    assert np.all(np.diff(s.y) >= 0) and s.y[-1] == 1.0 and s.y[0] == 0.0
    assert lv.ecdf(np.arange(10.0), complementary=True).to_svg()


def test_qq_distributions():
    x = np.random.default_rng(0).normal(size=300)
    for dist in ("normal", "uniform", "exponential", lambda p: p * 2):
        ET.fromstring(lv.qq(np.abs(x) if dist == "exponential" else x, dist=dist).to_svg())
    with pytest.raises(DataError):
        lv.qq(x, dist="cauchy")
    with pytest.raises(DataError):
        lv.qq([1.0, 2.0])


def test_correlation_clusters_related_variables():
    rng = np.random.default_rng(1)
    a, b = rng.normal(size=400), rng.normal(size=400)
    data = {"a1": a, "b1": b, "a2": a + 0.1 * rng.normal(size=400), "b2": -b + 0.1 * rng.normal(size=400)}
    c = lv.correlation(data)
    lay = c._layers[0]
    lay.prepare(c)
    order = lay.xn
    assert abs(order.index("a1") - order.index("a2")) == 1
    assert abs(order.index("b1") - order.index("b2")) == 1
    assert np.allclose(np.diag(lay.matrix), 1)
    unclustered = lv.correlation(data, cluster=False)
    unclustered._layers[0].prepare(unclustered)
    assert unclustered._layers[0].xn == list(data)
    with pytest.raises(DataError):
        lv.correlation({"only": a})


def test_correlation_spearman_ignores_monotone_transform():
    x = np.random.default_rng(2).random(200)
    c = lv.correlation({"x": x, "e": np.exp(8 * x)}, method="spearman", cluster=False)
    c._layers[0].prepare(c)
    assert c._layers[0].matrix[0, 1] == pytest.approx(1.0)


# ---------------------------------------------------------------- layers

def test_chord_geometry_and_validation():
    c = lv.chord([[0, 4], [2, 0]], names=["x", "y"])
    lay = c._layers[0]
    lay.prepare(c)
    assert lay.mat.sum() == 6
    with pytest.raises(DataError, match="negative"):
        lv.chord([[0, -1], [1, 0]]).to_svg()
    with pytest.raises(DataError, match="names="):
        lv.chord([[0, 1], [1, 0]], names=["only"]).to_svg()
    svg = lv.chord([("a", "b", 3), ("b", "a", 1)], sort=True).to_svg()
    assert "a → b: 3" in svg


def test_arc_orders_nodes():
    edges = [("a", "b"), ("b", "c"), ("c", "d")]
    c = lv.arc(edges, order=["d", "c", "b", "a"])
    lay = c._layers[0]
    lay.prepare(c)
    assert lay.nodes == ["d", "c", "b", "a"]
    with pytest.raises(DataError, match="missing"):
        lv.arc(edges, order=["a"]).to_svg()
    ET.fromstring(lv.arc(lv.Graph.from_edges([(1, 2, 2.0), (2, 3, 1.0)])).to_svg())


def test_parallel_validation_and_sampling():
    rng = np.random.default_rng(0)
    data = {"a": rng.normal(size=40_000), "b": rng.normal(size=40_000)}
    c = lv.parallel(data)
    svg = c.to_svg()
    assert svg.count("<polyline") + svg.count("<path") < 31_000
    with pytest.raises(DataError, match="at least 2"):
        lv.parallel({"a": [1, 2, 3]}).to_svg()
    with pytest.raises(DataError, match="not numeric"):
        lv.parallel({"a": [1, 2], "b": ["x", "y"]}, dims=["a", "b"]).to_svg()
    with pytest.raises(DataError, match="invert"):
        lv.parallel({"a": [1, 2], "b": [3, 4]}, invert=["zzz"]).to_svg()
    ET.fromstring(lv.parallel({"a": [1, 2, 3], "b": [3, 1, 2]}, normalize="zscore").to_svg())


def test_streamgraph_zero_offset_matches_stacked_area(series):
    c = lv.streamgraph(series, x="x", y="y", color="g", offset="zero", order="input")
    lay = c._layers[0]
    lay.prepare(c)
    assert np.allclose(lay.lower[0], 0)
    assert np.allclose(lay.upper[-1], lay.tops[-1])
    wig = lv.streamgraph(series, x="x", y="y", color="g")
    wig._layers[0].prepare(wig)
    w = wig._layers[0]
    thickness = w.upper[-1] - w.lower[0]
    assert np.allclose(thickness, lay.tops[-1])       # same total height at every x, only the baseline moves
    with pytest.raises(DataError, match="at least 2"):
        lv.streamgraph({"x": [1, 2, 3], "y": [1, 2, 3], "g": ["a"] * 3}, x="x", y="y", color="g").to_svg()
    with pytest.raises(DataError, match="offset"):
        lv.streamgraph(series, x="x", y="y", color="g", offset="x")


def test_horizon_bands(series):
    svg = lv.horizon(series, x="x", y="y", color="g", bands=4).to_svg()
    assert "4 bands" in svg
    with pytest.raises(DataError, match="bands"):
        lv.horizon(series, x="x", y="y", color="g", bands=9).to_svg()
    with pytest.raises(DataError, match="scale"):
        lv.horizon(series, x="x", y="y", color="g", scale="x").to_svg()


def test_marimekko_widths_follow_totals():
    c = lv.marimekko({"big": {"a": 9, "b": 1}, "small": {"a": 1, "b": 1}})
    svg = c.to_svg()
    assert "big · a: 9 (90% of big)" in svg
    with pytest.raises(DataError, match="negative"):
        lv.marimekko({"x": {"a": -1}}).to_svg()
    with pytest.raises(DataError, match="zero"):
        lv.marimekko({"x": {"a": 0}}).to_svg()


def test_bullet_inputs():
    a = lv.bullet({"Rev": (270, 250, [150, 225, 300])}).to_svg()
    b = lv.bullet([{"label": "Rev", "value": 270, "target": 250}], ranges=[150, 225, 300]).to_svg()
    assert "Rev: 270 (target 250)" in a and "Rev: 270 (target 250)" in b
    with pytest.raises(DataError):
        lv.bullet([]).to_svg()
    with pytest.raises(DataError, match="numeric"):
        lv.bullet([{"label": "x", "value": None}]).to_svg()


def test_new_charts_in_a_grid(rng, series):
    g = lv.grid([lv.roc(rng.integers(0, 2, 50), rng.random(50)), lv.marimekko({"a": {"x": 1, "y": 2}})], cols=2)
    ET.fromstring(g.to_svg())


def test_horizon_rows_run_top_to_bottom_and_grow_upwards():
    from lineova import scene as S
    t = np.arange(10.0)
    c = lv.horizon({"x": np.tile(t, 2), "y": np.r_[t, t * 2], "g": np.repeat(["first", "second"], 10)},
                   x="x", y="y", color="g", bands=1)
    polys = [op for op in c.build().ops if isinstance(op, S.Polyline) and op.closed]
    assert len(polys) == 2
    first, second = polys
    assert first.ys.max() <= second.ys.min() + 1e-6          # first series above the second
    top_of_row = first.ys.min()
    assert np.isclose(first.ys[0], first.ys.max())             # the fill starts at the row's bottom line
    assert top_of_row < first.ys.max()
