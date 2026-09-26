import warnings
import xml.etree.ElementTree as ET

import numpy as np
import pytest

import lineova as lv
from lineova import DataError
from lineova import scene as S

pd = pytest.importorskip("pandas")
THEMES = ["folio", "ledger", "instrument", "fjord"]


@pytest.fixture
def data(rng):
    df = pd.DataFrame({"g": np.repeat(["A", "B", "C"], 100), "v": rng.normal(size=300)})
    ohlc = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=60)})
    c = 100 + np.cumsum(rng.normal(size=60))
    ohlc["open"], ohlc["close"] = np.r_[100, c[:-1]], c
    ohlc["high"], ohlc["low"] = np.maximum(ohlc.open, ohlc.close) + 1, np.minimum(ohlc.open, ohlc.close) - 1
    return df, ohlc


def all_charts(theme, df, ohlc, rng):
    return [
        lv.pie({"a": 3, "b": 2, "c": 1}, theme=theme),
        lv.donut({"a": 3, "b": 2}, theme=theme),
        lv.violin(df, x="g", y="v", theme=theme),
        lv.ridgeline(df, x="g", y="v", theme=theme),
        lv.dumbbell({"x": (1, 2), "y": (3, 2)}, theme=theme),
        lv.slope({"x": (1, 2), "y": (3, 2)}, theme=theme),
        lv.waterfall({"a": 5, "b": -2}, start=10, theme=theme),
        lv.candlestick(ohlc, theme=theme),
        lv.treemap({"g1": {"a": 3, "b": 1}, "g2": {"c": 2}}, theme=theme),
        lv.sankey([("a", "b", 3), ("a", "c", 1), ("b", "d", 3)], theme=theme),
        lv.radar({"s": {"p": 1, "q": 2, "r": 3}}, theme=theme),
        lv.density(x=rng.normal(size=500), y=rng.normal(size=500), theme=theme),
        lv.timeline([("t1", "2025-01-01", "2025-02-01"), ("m", "2025-02-10", None)], theme=theme),
        lv.calendar(pd.date_range("2025-01-01", periods=90), theme=theme),
        lv.sparkline(rng.normal(size=30), theme=theme),
        lv.stat(42, label="x", previous=40, spark=rng.normal(size=10), theme=theme),
        lv.line(x=np.arange(5.0), y=np.arange(5.0), band=(np.arange(5.0) - 1, np.arange(5.0) + 1), theme=theme),
        lv.scatter(x=np.arange(5.0), y=np.arange(5.0), error=0.5, x_error=0.2, theme=theme),
        lv.bar(df, x="g", y="v", agg="mean", error="sem", theme=theme),
    ]


@pytest.mark.parametrize("theme", THEMES)
def test_new_charts_render_everywhere(theme, data, rng):
    df, ohlc = data
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for c in all_charts(theme, df, ohlc, rng):
            ET.fromstring(c.to_svg())
            assert c.to_pdf().startswith(b"%PDF")


def test_pie_folds_and_validates():
    with pytest.warns(UserWarning, match="Other"):
        c = lv.pie({str(i): 10 - i for i in range(9)})
        c.build()
    assert c._layers[0].cats[-1] == "Other (4)" and c._layers[0].values.sum() == sum(10 - i for i in range(9))
    with pytest.raises(DataError, match="negative"):
        lv.pie({"a": 1, "b": -1}).to_svg()


def test_waterfall_running_totals():
    c = lv.waterfall({"up": 5, "down": -2}, start=("Start", 10))
    c.build()
    steps = c._layers[0].steps
    assert [s[0] for s in steps] == ["Start", "up", "down", "Total"]
    assert steps[-1][3] == 13 and steps[2][2:4] == (15, 13)


def test_candlestick_buckets_many_rows(rng):
    n = 5000
    c0 = 100 + np.cumsum(rng.normal(size=n))
    df = pd.DataFrame({"open": c0, "close": c0 + 0.1, "high": c0 + 1, "low": c0 - 1},
                      index=pd.date_range("2020-01-01", periods=n, freq="h"))
    L = lv.candlestick(df)._layers[0]
    L.prepare(lv.Chart())
    x, o, h, lo, c = L._bucket(100)
    assert len(x) <= 100 and h.max() == df.high.max() and lo.min() == df.low.min()


def test_squarify_areas_are_proportional():
    from lineova.marks.treemap import squarify
    vals = [50, 25, 15, 10]
    rects = squarify(vals, 0, 0, 200, 100)
    areas = [w * h for _, _, w, h in rects]
    assert np.allclose(np.array(areas) / sum(areas), np.array(vals) / sum(vals))


def test_sankey_rejects_cycles():
    with pytest.raises(DataError, match="cycle"):
        lv.sankey([("a", "b", 1), ("b", "a", 1)]).to_svg()


def test_radar_needs_three_axes():
    with pytest.raises(DataError, match="3 measures"):
        lv.radar({"s": {"a": 1, "b": 2}}).to_svg()


def test_contours_of_a_cone_are_circles():
    from lineova.marks.density import contour_segments
    yy, xx = np.mgrid[0:101, 0:101]
    z = -np.hypot(xx - 50, yy - 50)
    cx, cy = contour_segments(z, -20)
    ok = np.isfinite(cx)
    r = np.hypot(cx[ok] - 50, cy[ok] - 50)
    assert np.allclose(r, 20, atol=0.2)


def test_kde_integrates_to_one(rng):
    from lineova.marks.violin import kde
    grid, d = kde(rng.normal(size=10_000), -6, 6)
    assert abs(np.trapezoid(d, grid) - 1) < 0.02 if hasattr(np, "trapezoid") else True


def test_timeline_validates_order():
    with pytest.raises(DataError, match="ends before"):
        lv.timeline([("t", "2025-02-01", "2025-01-01")]).to_svg()


def test_calendar_counts_days():
    days = pd.to_datetime(["2025-03-01", "2025-03-01", "2025-03-02"])
    c = lv.calendar(days)
    c.build()
    L = c._layers[0]
    i = (np.datetime64("2025-03-01") - np.datetime64("2025-01-01")).astype(int)
    assert L.per_day[i] == 2 and L.per_day[i + 1] == 1


def test_stat_delta_text():
    svg = lv.stat(110, label="Users", previous=100).to_svg()
    assert "+10.0%" in svg and "▲" in svg
    assert "▼" in lv.stat(90, previous=100).to_svg()


def test_error_bars_ci(rng):
    df = pd.DataFrame({"g": ["a"] * 50 + ["b"] * 50, "v": rng.normal(size=100)})
    c = lv.bar(df, x="g", y="v", agg="mean", error="ci")
    c.build()
    lo, hi = c._layers[0].errors["a"]
    v = df[df.g == "a"].v
    half = 1.96 * v.std(ddof=1) / np.sqrt(50)
    assert np.isclose(hi - lo, 2 * half)


def test_band_extends_y_domain():
    c = lv.line(x=[0, 1, 2], y=[1.0, 2.0, 3.0], band=([0.0, 1.0, 2.0], [5.0, 6.0, 9.0]))
    c.build()
    d = c._domain("y")
    assert d.lo == 0 and d.hi == 9


def test_extras_follow_groups_and_sorting():
    df = pd.DataFrame({"t": [2, 1, 2, 1], "v": [1.0, 2.0, 3.0, 4.0], "g": ["a", "a", "b", "b"],
                       "e": [0.1, 0.2, 0.3, 0.4]})
    c = lv.line(df, x="t", y="v", color="g", band="e")
    c.build()
    s = {x.name: x for x in c._layers[0].xy.series}
    assert s["a"].extra["err"].tolist() == [0.2, 0.1] and s["b"].extra["err"].tolist() == [0.4, 0.3]
