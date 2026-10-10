"""Visual regression: each case is drawn to SVG and compared with the file in tests/snapshots.

The comparison reads numbers with a tolerance (0.02 px), so tiny float formatting differences between NumPy
versions or platforms do not fail the suite; any change in structure, text, colour or a drawing that moves
by more than that does. After a deliberate visual change, rewrite the files and review the diff:

    LINEOVA_UPDATE_SNAPSHOTS=1 pytest tests/test_snapshots.py
"""
import os
import re
from pathlib import Path

import numpy as np
import pytest

import lineova as lv

pd = pytest.importorskip("pandas")
DIR = Path(__file__).parent / "snapshots"
NUM = re.compile(r"-?\d+(?:\.\d+)?")      # no exponents: hex colours like #1e2229 must not read as 1e2229
TOL = 0.02
SIZE = {"width": 360, "height": 240}


def cases():
    rng = np.random.default_rng(42)
    t = np.arange(24.0)
    months = pd.date_range("2025-01-01", periods=12, freq="MS")
    df = pd.DataFrame({"g": np.repeat(["A", "B", "C"], 40), "v": rng.normal(size=120)})
    ohlc = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=30)})
    c = 100 + np.cumsum(rng.normal(size=30))
    ohlc["open"], ohlc["close"] = np.r_[100, c[:-1]], c
    ohlc["high"], ohlc["low"] = np.maximum(ohlc.open, ohlc.close) + 1, np.minimum(ohlc.open, ohlc.close) - 1
    cols = {f"v{i}": rng.normal(size=60) for i in range(4)}
    cols["g"] = rng.choice(["p", "q"], 60)
    y = rng.integers(0, 2, 200)
    s = y * 0.8 + rng.normal(size=200)
    series = {"x": np.tile(np.arange(30.0), 3), "y": np.abs(rng.normal(size=90)) + 2, "g": np.repeat(["a", "b", "c"], 30)}
    edges = [("A", "B", 2), ("B", "C", 3), ("A", "C", 1), ("C", "D", 4), ("D", "E", 2), ("B", "E", 1)]
    return {
        "line_folio": lv.line(x=t, y=np.sin(t / 4), title="Line", theme="folio", **SIZE),
        "line_ledger_dates": lv.line(x=months, y=np.arange(12.0) ** 1.5, title="Dates", theme="ledger", **SIZE),
        "line_fjord_multi": lv.line({"a": np.sin(t / 3), "b": np.cos(t / 3)}, x=t, theme="fjord", **SIZE),
        "line_instrument_dark": lv.line(x=t, y=np.cos(t / 5), theme="ledger-dark", **SIZE),
        "area": lv.area({"a": np.abs(np.sin(t / 5)) + 1, "b": np.abs(np.cos(t / 5)) + 1}, x=t, **SIZE),
        "bar_highlight": lv.bar({"alpha": 3, "beta": 5, "gamma": 2}, highlight="beta", reference="mean", **SIZE),
        "bar_stack_texture": lv.bar({"N": {"a": 3, "b": 2}, "S": {"a": 1, "b": 4}}, stack=True, texture=True, **SIZE),
        "scatter_fit": lv.scatter(x=rng.normal(size=60), y=rng.normal(size=60), fit=True, theme="instrument", **SIZE),
        "scatter_density": lv.scatter(x=rng.normal(size=60_000), y=rng.normal(size=60_000), **SIZE),
        "histogram": lv.histogram({"a": rng.normal(size=300), "b": rng.normal(1, 1, 300)}, **SIZE),
        "heatmap": lv.heatmap(rng.normal(size=(5, 5)), theme="folio", **SIZE),
        "box": lv.box(df, x="g", y="v", **SIZE),
        "violin": lv.violin(df, x="g", y="v", theme="fjord", **SIZE),
        "pie": lv.donut({"a": 3, "b": 2, "c": 1}, **SIZE),
        "waterfall": lv.waterfall({"a": 5, "b": -2, "c": 3}, start=10, **SIZE),
        "candlestick": lv.candlestick(ohlc, theme="instrument", **SIZE),
        "treemap": lv.treemap({"x": {"a": 3, "b": 1}, "y": {"c": 2}}, **SIZE),
        "sankey": lv.sankey([("a", "b", 3), ("a", "c", 1), ("b", "d", 3)], **SIZE),
        "radar": lv.radar({"s": {"p": 1, "q": 2, "r": 3, "t": 2}}, **SIZE),
        "network": lv.network(edges, **SIZE),
        "network_radial": lv.network(edges, layout="radial", root="A", **SIZE),
        "grid": lv.grid([lv.line(x=t, y=t), lv.bar({"a": 1, "b": 2})], cols=2, width=700),
        "facets": lv.line(pd.DataFrame({"t": np.tile(t, 2), "v": rng.normal(size=48), "g": np.repeat(["a", "b"], 24)}),
                          x="t", y="v", facet="g", width=600),
        "chord": lv.chord([[0, 5, 2], [3, 0, 4], [1, 2, 0]], names=["A", "B", "C"], **SIZE),
        "arc": lv.arc(edges, **SIZE),
        "parallel": lv.parallel(cols, color="g", **SIZE),
        "streamgraph": lv.streamgraph(series, x="x", y="y", color="g", **SIZE),
        "horizon": lv.horizon(series, x="x", y="y", color="g", **SIZE),
        "marimekko": lv.marimekko({"EU": {"a": 3, "b": 2}, "US": {"a": 1, "b": 4}}, **SIZE),
        "bullet": lv.bullet([{"label": "Rev", "value": 270, "target": 250, "ranges": [150, 225, 300]}], width=360, height=120),
        "roc": lv.roc(y, {"m": s}, **SIZE),
        "confusion": lv.confusion_matrix(y, (s > 0.3).astype(int), normalize="true", **SIZE),
        "correlation": lv.correlation({k: v for k, v in cols.items() if k != "g"}, **SIZE),
        "qq": lv.qq(rng.normal(size=100), **SIZE),
    }


ID = re.compile(r"lv[0-9a-f]{8}")          # ids are a hash of the whole document: they change with every tiny difference


def _tokens(svg: str):
    svg = ID.sub("lvID", svg)
    return NUM.split(svg), [float(x) for x in NUM.findall(svg)]


def same(a: str, b: str, tol: float = TOL) -> tuple[bool, str]:
    ta, na = _tokens(a)
    tb, nb = _tokens(b)
    if ta != tb:
        for i, (x, y) in enumerate(zip(ta, tb)):
            if x != y:
                return False, f"text differs near: {x[-60:]!r} vs {y[-60:]!r}"
        return False, "different number of numbers"
    xa, xb = np.array(na), np.array(nb)
    d = np.where(xa == xb, 0.0, np.abs(xa - xb))
    if d.size and d.max() > tol:
        return False, f"{int((d > tol).sum())} numbers differ, largest by {d.max():.3f}"
    return True, ""


CASES = cases()


@pytest.mark.parametrize("name", sorted(CASES))
def test_snapshot(name):
    svg = CASES[name].to_svg()
    path = DIR / f"{name}.svg"
    if os.environ.get("LINEOVA_UPDATE_SNAPSHOTS"):
        DIR.mkdir(exist_ok=True)
        path.write_text(svg, encoding="utf-8", newline="\n")
        return
    if not path.exists():
        pytest.fail(f"no snapshot for {name}; create it with LINEOVA_UPDATE_SNAPSHOTS=1")
    ok, why = same(svg, path.read_text(encoding="utf-8"))
    assert ok, f"{name} changed: {why}. If intended, rerun with LINEOVA_UPDATE_SNAPSHOTS=1 and review the diff."


def test_snapshots_are_deterministic():
    for name in ("scatter_density", "network", "streamgraph", "violin"):
        assert CASES[name].to_svg() == CASES[name].to_svg()


def test_comparison_helper_detects_changes():
    base = '<rect x="10.00" y="20.5" width="30" fill="#2f5bd3"/>'
    assert same(base, base.replace("10.00", "10.01"))[0]
    assert not same(base, base.replace("10.00", "10.5"))[0]
    assert not same(base, base.replace("#2f5bd3", "#2f5bd4"))[0]
    assert not same(base, base + base)[0]
