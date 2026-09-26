# Quick start

This page covers the essentials in about five minutes. Every example runs as is.

```python
import numpy as np
import lineova as lv
```

## 1. One call per chart

Pass your data, and optionally a title. lineova chooses everything else.

```python
lv.line([3, 1, 4, 1, 5, 9, 2, 6], title="A first line").save("line.svg")
lv.bar({"Rome": 34, "Paris": 51, "Oslo": 12}, title="Visitors (M)").save("bar.svg")
lv.histogram(np.random.default_rng(0).normal(size=10_000)).save("hist.svg")
```

Data can be lists, NumPy arrays, dicts, pandas or polars DataFrames and Series:

```python
import pandas as pd
df = pd.DataFrame({
    "month": pd.date_range("2025-01-01", periods=12, freq="MS").repeat(3),
    "source": ["Solar", "Wind", "Hydro"] * 12,
    "gwh": np.random.default_rng(1).random(36) * 100,
})
lv.line(df, x="month", y="gwh").save("energy.svg")    # "source" is detected as the series
```

## 2. Change what you want

Every option is a keyword argument, and each one defaults to `"auto"`:

```python
lv.line(df, x="month", y="gwh",
        title="Energy output", subtitle="GWh per month",
        theme="fjord", y_range=(0, 120), highlight="Solar",
        source="Grid operator").save("energy.svg")
```

Or build the chart step by step:

```python
chart = (lv.Chart(df, theme="ledger")
           .line(x="month", y="gwh", color="source")
           .title("Energy output", subtitle="GWh per month")
           .y_axis(range=(0, 120), label="GWh")
           .band(x=("2025-06-01", "2025-08-31"), label="Summer")
           .hline(100, "Target"))
chart.save("energy.pdf")
```

## 3. Choose a style

| Theme | For |
|---|---|
| `folio` | Papers, theses, anything printed. Serif type, black and white friendly, numbered captions |
| `ledger` (default) | Reports, dashboards, slides |
| `instrument` | Engineering, monitoring. Dark with a measurement grid |
| `fjord` | Public reports, articles, teaching |

```python
lv.themes.set_default("folio")     # for the whole session
```

## 4. Save it

```python
chart.save("figure.svg")           # vector, for the web
chart.save("figure.pdf")           # vector, for LaTeX and print
chart.save("figure.png", dpi=300)  # needs: pip install "lineova[png]"
chart.save("figure.html")          # interactive: hover, zoom, pan
chart                              # in Jupyter, the chart just displays
```

## 5. Several charts together

```python
lv.line(df, x="month", y="gwh", facet="source")                        # small multiples, one per source
lv.grid([chart_a, chart_b, chart_c], cols=3, title="Overview")               # any charts side by side
```

## Next steps

- The [user guide](guide.md) documents every chart type and option.
- [Use cases](use-cases.md) shows complete examples for papers, dashboards and monitoring.
- The [gallery](gallery.md) shows charts made from real data.
