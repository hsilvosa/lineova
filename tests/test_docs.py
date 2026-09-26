"""The examples in README.md and docs/guide.md must keep working."""
import numpy as np
import pytest

import lineova as lv

pd = pytest.importorskip("pandas")


@pytest.fixture
def df():
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "month": pd.date_range("2025-01-01", periods=12, freq="MS").repeat(3),
        "source": ["Solar", "Wind", "Hydro"] * 12,
        "gwh": rng.random(36) * 140,
    })


def test_readme_chained_example(df, tmp_path):
    chart = (
        lv.Chart(df, theme="fjord")
          .line(x="month", y="gwh", color="source")
          .title("Energy output", subtitle="GWh per month")
          .y_axis(range=(0, 150), label="GWh", format="{:,.0f}")
          .x_axis(ticks=6)
          .band(x=("2025-06-01", "2025-08-31"), label="Summer")
          .hline(120, "Target")
          .highlight("Solar")
          .legend("top")
          .source("Grid operator")
          .size("wide")
    )
    chart.save(tmp_path / "energy.pdf")
    chart.save(tmp_path / "energy.svg")


def test_guide_annotations(df):
    c = lv.line(df, x="month", y="gwh")
    c.hline("mean").vline("2025-03-01", "Launch").band(y=(0, 20), color="#e0673f").annotate("2025-07-01", 138, "Peak")
    assert "Launch" in c.to_svg() and "Peak" in c.to_svg()


def test_readme_one_liners(df):
    lv.line(df, x="month", y="gwh").to_svg()
    lv.line(df, x="month", y="gwh", y_range=(0, 150), highlight="Solar").to_svg()
    lv.bar({"Rome": 34, "Paris": 51, "Oslo": 12}).to_svg()
    wide = df.pivot(index="month", columns="source", values="gwh").reset_index()
    lv.line(wide, x="month", y=["Solar", "Wind"]).to_svg()
    lv.scatter(pd.DataFrame({"sun": [1, 2, 3], "kw": [2, 4, 5], "temp": [9, 12, 20]}),
               x="sun", y="kw", size="temp", fit=True).to_svg()
    lv.area(df, x="month", y="gwh", normalize=True).to_svg()
    lv.box(df, x="source", y="gwh").to_svg()
    lv.heatmap(df.assign(m=df.month.dt.month), x="m", y="source", value="gwh").to_svg()


def test_graph_examples():
    g = lv.Graph.from_edges([("A", "B", 4), ("A", "C", 3), ("C", "D", 2)])
    assert g.shortest_path("A", "D") == ["A", "C", "D"]
    assert lv.Graph.from_edges([("a", "b"), ("b", "c")], directed=True).topological_sort() == ["a", "b", "c"]
    g.draw(path=("A", "D")).to_svg()


def test_theme_example():
    brand = lv.themes.get("ledger").replace(accent="#0f766e", palette=("#0f766e", "#b45309", "#6d28d9"))
    lv.themes.register("brand2", brand)
    lv.themes.set_default("brand2")
    try:
        assert lv.line([1, 2]).resolved_theme.accent == "#0f766e"
    finally:
        lv.themes.set_default("ledger")


def test_network_input_forms():
    edges_df = pd.DataFrame({"from": ["a", "b"], "to": ["b", "c"], "cost": [1.0, 2.0]})
    lv.network(edges_df, layout="circular").to_svg()
    lv.network(np.array([[0, 1], [1, 2], [2, 0]]), groups="community").to_svg()
    lv.network({"a": ["b", "c"], "b": ["c"]}, positions={"a": (0, 0), "b": (1, 0), "c": (0.5, 1)}).to_svg()


def _blocks(path):
    import re
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / path).read_text(encoding="utf-8")
    return re.findall(r"```python\n(.*?)```", text, re.S)


def test_quickstart_runs(tmp_path, monkeypatch):
    """Every code block in docs/quickstart.md runs, in order, in one namespace."""
    monkeypatch.chdir(tmp_path)
    ns = {"chart_a": lv.bar({"a": 1}), "chart_b": lv.line([1, 2]), "chart_c": lv.pie({"x": 1, "y": 2})}
    for code in _blocks("docs/quickstart.md"):
        if "figure.png" in code:              # PNG needs an optional backend
            code = code.replace('chart.save("figure.png", dpi=300)', "")
        exec(compile(code, "quickstart.md", "exec"), ns)
    lv.themes.set_default("ledger")


def test_use_case_blocks_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for code in _blocks("docs/use-cases.md"):
        if "pyarrow" in code or "Chunks(trips)" in code:     # needs pyarrow / slow; covered elsewhere
            continue
        exec(compile(code, "use-cases.md", "exec"), {})
