import numpy as np
import pytest

import lineova as lv
from lineova import scene as S

pd = pytest.importorskip("pandas")


@pytest.fixture
def df(rng):
    return pd.DataFrame({"t": np.tile(np.arange(10), 6), "v": rng.random(60),
                         "k": np.repeat(["a", "b"], 30), "panel": np.tile(np.repeat(["p", "q", "r"], 10), 2)})


def test_facet_makes_one_panel_per_value(df):
    c = lv.line(df, x="t", y="v", color="k", facet="panel", title="T")
    scene = c.build()
    groups = [op for op in scene.ops if isinstance(op, S.Group)]
    assert len(groups) == 3
    svg = c.to_svg()
    assert svg.count(">p<") >= 1 and "T" in svg


def test_facet_shares_axes(df):
    df.loc[df.panel == "r", "v"] *= 10
    g = lv.figure.facet_grid(lv.line(df, x="t", y="v", facet="panel"))
    g.build()


def test_grid_shared_legend_only_for_same_series(df):
    a = lv.line(df[df.panel == "p"], x="t", y="v", color="k")
    b = lv.line(df[df.panel == "q"], x="t", y="v", color="k")
    svg = lv.grid([a, b], title="Two").to_svg()
    assert svg.count(">a<") == 1          # one legend entry, not one per panel
    mixed = lv.grid([lv.bar({"x": 1, "y": 2}), lv.pie({"u": 1, "w": 2})])
    mixed.to_svg()


def test_grid_outputs(tmp_path, df):
    g = lv.grid([lv.stat(1, label="a"), lv.stat(2, label="b")], cols=2)
    g.save(tmp_path / "g.svg")
    g.save(tmp_path / "g.pdf")
    g.save(tmp_path / "g.html")
    html = (tmp_path / "g.html").read_text()
    assert "<svg" in html and "viewBox" in html and "<script>" in html


def test_html_moves_titles_to_tooltips():
    html = lv.bar({"a": 1}).to_html()
    assert "data-tip" in html and "<title>a: 1</title>" in html


def test_chunked_line_matches_in_memory(rng):
    n = 300_000
    t = np.arange(n, dtype=float)
    v = np.cumsum(rng.normal(size=n))
    chunks = lv.Chunks(lambda: ({"t": t[i:i + 50_000], "v": v[i:i + 50_000]} for i in range(0, n, 50_000)))
    c = lv.line(chunks, x="t", y="v")
    c.build()
    s = c._layers[0].xy.series[0]
    assert s.y.max() == v.max() and s.y.min() == v.min() and len(s.x) < 100_000


def test_chunked_histogram_matches_numpy(rng):
    parts = [rng.normal(size=100_000) for _ in range(5)]
    c = lv.histogram(lv.Chunks(parts))
    c.build()
    L = c._layers[0]
    ref, _ = np.histogram(np.concatenate(parts), bins=L.edges)
    assert np.array_equal(L.counts[0], ref)


def test_chunked_scatter_is_density(rng):
    parts = [pd.DataFrame({"x": rng.normal(size=50_000), "y": rng.normal(size=50_000)}) for _ in range(4)]
    c = lv.scatter(lv.Chunks(parts), x="x", y="y")
    assert any(isinstance(op, S.Image) for op in c.build().ops)
    assert c._layers[0].n == 200_000


def test_unsorted_chunks_rejected():
    chunks = lv.Chunks([{"t": np.array([2.0, 1.0]), "v": np.array([1.0, 2.0])}])
    with pytest.raises(lv.DataError, match="sorted"):
        lv.line(chunks, x="t", y="v").to_svg()
