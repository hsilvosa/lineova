# Use cases

Six complete examples, one per kind of work. The code is taken from [`examples/use_cases.py`](https://github.com/hsilvosa/lineova/blob/main/examples/use_cases.py). Run that file to reproduce every image on this page.

## Academic papers and theses

**Need:** figures that survive black-and-white printing and journal column widths, uncertainty shown honestly, numbered captions, vector output for LaTeX.

**Use:** the `folio` theme (serif type, range-frame axes, series told apart by line pattern and marker as well as colour, direct labels instead of a legend box), `band=` for confidence intervals, `number=` and `caption=` for the figure caption, and PDF output.

{{academic}}

![Symptom score by treatment arm](gallery/use-cases/academic.svg)

Tips:

- `size="column"` (3.5 in) and `size="page"` match common journal widths.
- `facet="column"` produces panels labelled (a), (b), (c), with shared axes.
- `bar(df, x="group", y="value", agg="mean", error="ci")` gives mean ± 95% CI bars from raw rows.

## Business reports and dashboards

**Need:** numbers someone can read in a few seconds, the one thing that matters highlighted, charts that can be shared as a link or dropped into slides.

**Use:** the `ledger` theme, `stat` tiles with a change arrow and sparkline, `waterfall` for bridges, `highlight=` to mute everything but the point, and `.html` output for an interactive page.

{{business}}

![KPI tiles](gallery/use-cases/business_kpis.svg)
![Revenue bridge](gallery/use-cases/business_bridge.svg)

## Engineering and monitoring

**Need:** long, dense time series drawn exactly (every spike visible), thresholds, and screens that are comfortable to leave on.

**Use:** the dark `instrument` theme. Lines of any length are reduced per pixel column (first, last, min and max), so a month of 1 Hz data draws in well under a second and no spike is lost.

{{engineering}}

![Bearing temperature](gallery/use-cases/engineering.svg)

Related charts: `candlestick` for OHLC data (auto-aggregated when zoomed out), `calendar` for daily activity, `density` for where operating points cluster.

## Public reports and teaching

**Need:** charts for readers who aren't analysts: fewer axes, more shape, plain labels.

**Use:** the `fjord` theme with `treemap`, `area`, `slope`, `sankey`, `donut` or `radar`.

{{public}}

![Budget treemap](gallery/use-cases/public.svg)

## Exploring very large data

**Need:** see the shape of tens or hundreds of millions of rows, possibly more than fits in memory.

**Use:** `lv.Chunks(source)` streams data through `line`, `scatter` and `histogram`. Scatter plots switch to density rendering above 50,000 points. `np.memmap` arrays can also be passed directly.

{{bigdata}}

![50 million trips](gallery/use-cases/bigdata.svg)

With a real Parquet file (requires `pyarrow`):

```python
import pyarrow.parquet as pq
batches = lambda: pq.ParquetFile("trips.parquet").iter_batches(columns=["distance", "fare"])
lv.scatter(lv.Chunks(batches), x="distance", y="fare")
```

## Analysing networks

**Need:** compute things about a network (routes, hubs, clusters) and show the answer.

**Use:** `lv.Graph` for the algorithms and `lv.network` to draw them. See [Graphs](graphs.md).

{{network}}

![Fastest route](gallery/use-cases/network.svg)
