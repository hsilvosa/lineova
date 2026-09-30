<p align="center">
  <img src="https://raw.githubusercontent.com/hsilvosa/lineova/main/docs/gallery/real/eq_map.svg" alt="Map of 207,221 earthquakes around Iberia drawn with lineova" width="640">
</p>

<h1 align="center">lineova</h1>

<p align="center">
  <b>Clean, fast charts from Python, with good defaults and one dependency.</b><br>
  27 chart types · four house styles and their dark variants · SVG, PDF, PNG and interactive HTML · from 10 rows to 100 million
</p>

<p align="center">
  <a href="https://github.com/hsilvosa/lineova/actions/workflows/tests.yml"><img alt="Tests" src="https://github.com/hsilvosa/lineova/actions/workflows/tests.yml/badge.svg"></a>
  <a href="https://pypi.org/project/lineova/"><img alt="PyPI" src="https://img.shields.io/pypi/v/lineova"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%E2%80%933.13-blue">
  <a href="https://github.com/hsilvosa/lineova/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green"></a>
  <a href="https://hsilvosa.github.io/lineova/"><img alt="Docs" src="https://img.shields.io/badge/docs-online-informational"></a>
</p>

---

**lineova** is a Python library for charts and graphs. It draws everything from quick exploratory plots to publication-ready figures, with sensible defaults, and handles datasets of any size with NumPy as its only dependency.

There are already great plotting libraries. I built this one because I wanted my own: a library I understand end to end and can keep shaping as my needs grow.

```python
import lineova as lv

lv.line(df, x="date", y="price", color="market").save("prices.svg")
```

That one call chooses the size, the ticks, number and date formats, the colours, the legend, and how to draw the data: vector marks for small data, pixel-exact reduction for millions of points. Every choice can be overridden, one option at a time.

## What it offers

- **Good output with no tuning.** Readable ticks, labels that don't collide, colour palettes checked for colour-blind readers, captions and sources where they belong.
- **Four house styles** for four kinds of document: *Folio* for papers and theses, *Ledger* for business reports and dashboards, *Instrument* for engineering and monitoring, *Fjord* for public-facing reports and teaching. Each has a dark (or light) variant, and `lv.themes.from_brand("#0f766e")` builds a checked palette around your own colour.
- **Accessible by default.** Every chart carries a generated text description (`chart.describe()`, written into the SVG) and a data table (`chart.table()`); `texture=True` adds patterns as a second encoding.
- **Any data size.** 100 million points render in about 2 seconds, and data larger than memory can be streamed in chunks, including group-bys for bars and heatmaps and quantile sketches for box plots. What a chart costs depends on its pixels, not its rows.
- **One dependency.** Only NumPy is required. pandas, polars and pyarrow data are accepted as they are.
- **Publication formats built in.** Vector SVG and PDF (text stays selectable), high-DPI PNG, and a self-contained interactive HTML page with tooltips, a crosshair readout and the data behind the chart.
- **Maps without GIS dependencies.** GeoJSON choropleths, point maps of any size, and tile maps of Spanish provinces and regions.
- **Graphs as data, too.** A `Graph` class with shortest paths, centrality, communities, flows and more, tested against networkx.

## Installation

```bash
pip install lineova              # SVG, PDF and HTML output
pip install "lineova[png]"       # adds PNG export (resvg, no system libraries)
```

Until the first PyPI release, install from GitHub:

```bash
pip install "git+https://github.com/hsilvosa/lineova.git"
```

Requires Python 3.10+. See [Installation](https://github.com/hsilvosa/lineova/blob/main/docs/installation.md) for optional extras and development setup.

## Quick start

```python
import lineova as lv

# 1. One call: lineova decides the rest
lv.bar({"Solar": 31, "Wind": 27, "Hydro": 18}, title="Electricity mix (%)").save("mix.svg")

# 2. Chained: set only what you care about
(lv.Chart(df, theme="folio")
   .line(x="year", y="value", color="country")
   .title("Renewable share")
   .y_axis(range=(0, 100), label="%")
   .caption("Source: national statistics.", number=3)
   .save("figure3.pdf"))
```

A typo gets a suggestion (`titel=` → *Did you mean 'title'?*), and every option defaults to `"auto"`. The [Quick start](https://github.com/hsilvosa/lineova/blob/main/docs/quickstart.md) walks through both styles.

## Real data examples

These charts were made from two public datasets: the IGN Spanish earthquake catalogue (207,221 events, 1373–2026) and the OMIE Iberian electricity market (hourly prices 2023–2026 and 17 million bids from 2024). The code is in [`examples/real_data.py`](https://github.com/hsilvosa/lineova/blob/main/examples/real_data.py).

| | |
|---|---|
| ![La Palma eruption](https://raw.githubusercontent.com/hsilvosa/lineova/main/docs/gallery/real/eq_la_palma.svg) | ![Price by hour and month](https://raw.githubusercontent.com/hsilvosa/lineova/main/docs/gallery/real/power_heatmap.svg) |
| ![Magnitudes, log scale](https://raw.githubusercontent.com/hsilvosa/lineova/main/docs/gallery/real/eq_magnitudes.svg) | ![Supply and demand curves](https://raw.githubusercontent.com/hsilvosa/lineova/main/docs/gallery/real/bids_curves.svg) |
| ![Depth by region](https://raw.githubusercontent.com/hsilvosa/lineova/main/docs/gallery/real/eq_depth_regions.svg) | ![Daily price with range](https://raw.githubusercontent.com/hsilvosa/lineova/main/docs/gallery/real/power_daily.svg) |
| ![Price by hour 2023 vs 2025](https://raw.githubusercontent.com/hsilvosa/lineova/main/docs/gallery/real/power_by_hour.svg) | ![Weekday distribution](https://raw.githubusercontent.com/hsilvosa/lineova/main/docs/gallery/real/power_weekday.svg) |
| ![Earthquakes by province](https://raw.githubusercontent.com/hsilvosa/lineova/main/docs/gallery/real/eq_tilemap.svg) | ![Sell offers by month and hour](https://raw.githubusercontent.com/hsilvosa/lineova/main/docs/gallery/real/bids_offer_heatmap.svg) |

More in the [gallery](https://github.com/hsilvosa/lineova/blob/main/docs/gallery.md).

## Use cases

| You are… | Typical charts | Style | See |
|---|---|---|---|
| Writing a paper or thesis | line with bands, bar with CI, box/violin, histogram, small multiples | `folio` → PDF | [Academic figures](https://github.com/hsilvosa/lineova/blob/main/docs/use-cases.md#academic-papers-and-theses) |
| Building a business report or dashboard | bar, waterfall, stat tiles, sparklines, donut | `ledger` → SVG/HTML | [Business reporting](https://github.com/hsilvosa/lineova/blob/main/docs/use-cases.md#business-reports-and-dashboards) |
| Monitoring sensors, markets or systems | long time series, candlestick, calendar, density | `instrument` | [Engineering](https://github.com/hsilvosa/lineova/blob/main/docs/use-cases.md#engineering-and-monitoring) |
| Explaining data to the public | area, treemap, sunburst, maps, sankey, slope | `fjord` | [Public reports](https://github.com/hsilvosa/lineova/blob/main/docs/use-cases.md#public-reports-and-teaching) |
| Exploring very large data | scatter density, hexbin, histogram, line, bar and box from `lv.Chunks` | any | [Big data](https://github.com/hsilvosa/lineova/blob/main/docs/use-cases.md#exploring-very-large-data) |
| Analysing networks | network drawings, shortest paths, centrality | any | [Graphs](https://github.com/hsilvosa/lineova/blob/main/docs/graphs.md) |

## Chart types

| Compare | Distribution | Composition | Change & time | Relationships | Flows & structure | Maps | Dashboards |
|---|---|---|---|---|---|---|---|
| `bar` | `histogram` | `pie` / `donut` | `line` | `scatter` | `network` | `map` (GeoJSON) | `stat` |
| `dumbbell` | `box` | `treemap` | `area` | `density` | `sankey` | `map` (points) | `sparkline` |
| `slope` | `violin` | `sunburst` | `candlestick` | `hexbin` | `timeline` | `tilemap` | `grid` |
| `radar` | `ridgeline` | `waterfall` | `calendar` | `heatmap` | | | `facet=` |

Error bars and confidence bands, reference lines, shaded ranges, annotations, log and date axes, and small multiples work across chart types. See the [user guide](https://github.com/hsilvosa/lineova/blob/main/docs/guide.md).

## The four styles

| Folio: academic | Ledger: business |
|---|---|
| ![](https://raw.githubusercontent.com/hsilvosa/lineova/main/docs/gallery/folio-line.svg) | ![](https://raw.githubusercontent.com/hsilvosa/lineova/main/docs/gallery/ledger-bar.svg) |
| **Instrument: technical** | **Fjord: public reports** |
| ![](https://raw.githubusercontent.com/hsilvosa/lineova/main/docs/gallery/instrument-scatter.svg) | ![](https://raw.githubusercontent.com/hsilvosa/lineova/main/docs/gallery/fjord-network.svg) |

Dark variants (`ledger-dark`, `fjord-dark`, `folio-dark`) and `instrument-light` keep each series' colour. Themes are plain dataclasses; `lv.themes.from_brand(colour)` builds one around your brand colour with a palette checked for colour-blind readers. See [Themes](https://github.com/hsilvosa/lineova/blob/main/docs/themes.md).

## Performance

Full pipeline (data → finished SVG) on a 2-core cloud machine:

| Input | Time |
|---|---|
| Line chart, 100 million points | 1.5 s |
| Scatter (density), 100 million points | 1.9 s |
| Histogram, 17 million real market bids streamed from 6 files | 0.3 s |
| Violin, 10 million values | 1.9 s |
| Network, 40,000 nodes / 200,000 edges | 3 s |
| Hexbin, 10 million points | 1.0 s |
| Heatmap of 12 million real market offers, streamed group-by | 2.3 s |

How it works and how to benchmark it yourself: [Performance](https://github.com/hsilvosa/lineova/blob/main/docs/performance.md).

## Documentation

- [Installation](https://github.com/hsilvosa/lineova/blob/main/docs/installation.md)
- [Quick start](https://github.com/hsilvosa/lineova/blob/main/docs/quickstart.md)
- [User guide](https://github.com/hsilvosa/lineova/blob/main/docs/guide.md): every chart and option
- [Use cases](https://github.com/hsilvosa/lineova/blob/main/docs/use-cases.md)
- [Gallery](https://github.com/hsilvosa/lineova/blob/main/docs/gallery.md)
- [Themes](https://github.com/hsilvosa/lineova/blob/main/docs/themes.md)
- [Graphs](https://github.com/hsilvosa/lineova/blob/main/docs/graphs.md)
- [Performance](https://github.com/hsilvosa/lineova/blob/main/docs/performance.md)
- [API reference](https://github.com/hsilvosa/lineova/blob/main/docs/api.md)
- [FAQ](https://github.com/hsilvosa/lineova/blob/main/docs/faq.md)

## Contributing

Bug reports, ideas and pull requests are welcome. [CONTRIBUTING.md](https://github.com/hsilvosa/lineova/blob/main/CONTRIBUTING.md) explains the branch model (`main`, `develop`, `release/*`, `feature/*`), how to run the tests and how releases are made. See the [roadmap](https://github.com/hsilvosa/lineova/blob/main/ROADMAP.md) for what's planned.

## Citing lineova

If lineova helps your research, you can cite it using [CITATION.cff](https://github.com/hsilvosa/lineova/blob/main/CITATION.cff) (GitHub shows a "Cite this repository" button).

## License

[MIT](https://github.com/hsilvosa/lineova/blob/main/LICENSE) © 2026 Hugo Silvosa Cuervo.

The example datasets are not part of this repository and keep their own terms: the earthquake catalogue is published by the [Instituto Geográfico Nacional](https://doi.org/10.7419/162.03.2022), and the electricity market data by [OMIE](https://www.omie.es) (attribution required).
