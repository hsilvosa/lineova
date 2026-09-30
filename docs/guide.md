# lineova guide

Every option below defaults to `"auto"` or `None`, and the automatic choice is described next to it. You only set what you want to change.

- [Data you can pass](#data-you-can-pass)
- [Chart options (all chart types)](#chart-options)
- [Axis options](#axis-options)
- [Annotations](#annotations)
- [Per-chart options](#per-chart-options)
- [Themes](#themes)
- [Output](#output)
- [Performance notes](#performance-notes)
- [Layouts: grids and facets](#layouts-grids-and-facets)
- [Data larger than memory](#data-larger-than-memory)
- [Interactive HTML](#interactive-html)
- [What "auto" does](#what-auto-does)

## Data you can pass

| You have | Example |
|---|---|
| A list or array | `lv.line([3, 1, 4, 1, 5])` |
| x and y arrays | `lv.line(x=dates, y=values)` |
| Several named series | `lv.line({"a": ya, "b": yb}, x=dates)` |
| A 2-D array (columns = series) | `lv.line(matrix)` |
| A DataFrame + column names | `lv.line(df, x="date", y="sales")` |
| Long format, one row per point | `lv.line(df, x="date", y="sales", color="region")` |
| Several value columns | `lv.line(df, x="date", y=["north", "south"])` |
| A pandas Series | `lv.line(series)` (the index becomes x) |
| `{label: value}` | `lv.bar({"A": 3, "B": 5})` |
| Raw labels (counted for you) | `lv.bar(["cat", "dog", "cat"])` |
| An edge list | `lv.network([("a", "b"), ("b", "c", 2.5)])` |

pandas, polars, NumPy (including `np.memmap`), plain lists, dicts of columns and structured arrays all work. Dates can be `datetime64`, Python `datetime`/`date`, or pandas timestamps (time-zone aware ones are converted to UTC). Missing values (`None`, `NaN`, `NaT`, pandas `NA`) leave gaps in lines and are skipped elsewhere.

When `y` is not given for a DataFrame, every numeric column is plotted. When `x` is not given, the first date column is used, then a meaningful pandas index, then row numbers.

## Chart options

These work in every chart function as keywords, and on `Chart` as methods.

| Keyword | Method | Meaning |
|---|---|---|
| `theme` | `.theme()` | `"folio"`, `"ledger"` (default), `"instrument"`, `"fjord"`, a registered name, or a `Theme` |
| `title`, `subtitle` | `.title(t, subtitle=)` | Heading text. In Folio they become the figure caption instead. |
| `caption` | `.caption(text, number=)` | Paragraph under the chart |
| `number` | | Figure number in Folio captions (`Figure 3.`) |
| `source` | `.source(text)` | "Source: …" line |
| `width`, `height` | `.size(w, h)` | In px (1 px = 0.75 pt in PDF). Auto sizes fit the content. |
| `size` | `.size("column")` | Preset: `column`, `page`, `wide`, `slide`, `square`, `dashboard`, `a4` |
| `legend` | `.legend(pos)` | `auto`, `top`, `bottom`, `right`, `direct` (labels at line ends), `readout`, `none` |
| `palette` | `.palette(p)` | A list of colours, `{series: colour}`, one colour for everything, or another theme's name |
| `highlight` | `.highlight(*names)` | Colour these series, bars, boxes or nodes and mute the rest |
| `background` | | Override the theme background |

## Axis options

Prefix with `x_` or `y_` as keywords (`y_range=(0, 1)`), or use `.x_axis(...)` / `.y_axis(...)`.

| Option | Values |
|---|---|
| `label` | text, `None` to hide, `"auto"` (from the column name) |
| `scale` | `auto`, `linear`, `log`, `time`, `category` |
| `range` | `(lo, hi)`. Either end may be `None`. Dates accepted on time axes. |
| `ticks` | `auto`, an approximate count (`6`), a list of values, or `{value: "label"}` |
| `format` | `",.1f"`, `"{:.0%}"`, `"%b %Y"` (time), or a function |
| `zero` | include zero? `auto` (yes for bars, areas and histograms) |
| `grid` | `auto` (from the theme), `True`, `False` |
| `reverse` | flip the axis |
| `visible` | `False` hides it |

## Annotations

```python
chart.hline(100, "Target")                 # horizontal reference line with a label
chart.hline("mean")                        # at the data mean
chart.vline("2025-03-01", "Launch")
chart.band(x=("2025-06-01", "2025-08-31"), label="Summer")
chart.band(y=(0, 20), color="#e0673f")
chart.annotate("2025-07-01", 138, "Peak")  # text pointing at a data position
```

## Per-chart options

### line
`curve` (`auto` / `"smooth"` / `"linear"`), `markers` (`auto` / `True` / `False`), `width` (line width), `dash` (e.g. `(4, 2)`), `values` (end-of-line values: `auto` / `True` / `False`), `label` (name of a single series), `render` (`auto`, or `"exact"` to turn off pixel reduction).

### area
Everything from `line`, plus `stack` (auto: stacks when there are several series) and `normalize` (`True` for 100% shares).

### bar
| Option | Meaning |
|---|---|
| `color` | Column to group by (grouped bars, one colour each) |
| `stack` | `True` to stack the groups |
| `normalize` | 100% stacked |
| `orientation` | `auto` (horizontal when labels are long or there are more than 12 bars), `"h"`, `"v"` |
| `sort` | `auto` (sorts horizontal bars with unordered labels), `True`, `"ascending"`, `False` |
| `agg` | How to combine repeated labels: `sum` (default), `mean`, `median`, `min`, `max`, `count` |
| `top` | Keep the N largest and fold the rest into "Other" (auto: 25 when there are more than 30) |
| `labels` | Value labels on bars: `auto` (up to 24 bars), `True`, `False` |
| `format` | Value label format, e.g. `"{:.1f}%"` |
| `reference` | `"mean"`, `"median"` or a number: dashed reference line with a label |

Labels that look ordered (months, weekdays, numbers, ranges like `0-9`, quarters, years) keep their order.

### scatter
| Option | Meaning |
|---|---|
| `color` | Column or array. Text → one colour per group (auto-detected in DataFrames). Numbers → colour scale with a colour bar. |
| `size` | Column or array mapped to bubble area |
| `sizes` | `(min_radius, max_radius)` in px |
| `fit` | `True`: least-squares line, 95% confidence band and equation |
| `render` | `auto` (density above 50,000 points), `"vector"`, `"density"` |
| `shade` | Density shading: `eq_hist` (default), `log`, `linear` |
| `marker` | `solid`, `hollow`, `cross`, `bubble` (default from the theme) |
| `opacity`, `tooltips` | Automatic based on point count |

### histogram
`bins` (`auto`, a count, or explicit edges), `range`, `stat` (`count`, `percent`, `density`), `cumulative`, `color` (group column, overlaid). Integer data over a short range gets one bin per integer.

### heatmap
Pass a 2-D array (with optional `x=`/`y=` labels), a DataFrame (index × columns), or long data with `x=`, `y=`, `value=` column names (`agg` combines duplicates). Options: `cmap` (`auto`: diverging when values cross zero; `"sequential"`, `"diverging"`, or a list of colours), `vmin`, `vmax`, `annotate` (values in cells: auto up to 400 cells), `format`, `label` (colour bar title). Matrices larger than the plot are block-averaged into one image.

### box
`{group: values}`, a list of arrays, or `box(df, x="group", y="value")`. Options: `orientation`, `points` (raw points: auto for groups of 60 or fewer), `whisker` (IQR multiple, default 1.5), `mean` (diamond marker), `color="group"` (one colour per box). At most 150 outliers per group are drawn (the most extreme ones).

### network
Pass a `lv.Graph`, an edge list `[(u, v)]` / `[(u, v, w)]`, an `(m, 2|3)` array, a DataFrame with source/target(/weight) columns (names detected), an adjacency dict, or a networkx graph.

| Option | Meaning |
|---|---|
| `path` | `(source, target)`: finds and highlights the cheapest path |
| `highlight` | A list of nodes to highlight as a path |
| `layout` | `auto` (layered for small directed acyclic graphs, force otherwise), `force`, `circular`, `grid`, `layered` |
| `positions` | `{node: (x, y)}` to place nodes yourself |
| `groups` | `{node: group}`, `"component"`, or `"community"` (label propagation). Auto: colours components when there are 2–8. |
| `labels` | auto: all nodes up to 40, the 12 best-connected up to 400 |
| `node_size` | px radius, `"degree"`, `"pagerank"`, `"betweenness"` or `"closeness"` |
| `edge_labels` | weights on edges: auto for weighted graphs with 30 or fewer edges |
| `directed` | Draw arrows. Auto for directed `Graph`s. |
| `seed` | Layout random seed (layouts are deterministic) |

### Error bars and bands
`line(..., band=spec)`, `scatter(..., error=spec, x_error=spec)`, `bar(..., error=spec)`. A spec is a column name or array of ± half-widths, a number, or a **tuple** `(lower, upper)` of absolute bounds. For bars built from raw rows, `error="std"`, `"sem"` or `"ci"` (95%) computes the statistic per bar.

### pie / donut
`pie({label: value})` or `pie(df, x="label", y="value")`. Options: `donut` (auto: a donut except in Folio), `top` (auto 6: the smallest slices fold into "Other", with a warning suggesting a bar chart), `sort`, `labels` (outside, with leader lines that never overlap), `center` (donut centre text, auto: the total), `start` (angle, default 90 = 12 o'clock), `format`.

### violin / ridgeline
Same inputs as `box`. The density is a binned Gaussian KDE (Silverman bandwidth, `bw=` to override), so it's O(n). Violin options: `inner` (quartile bar + median dot), `scale` (`"width"`: every violin as wide as the band, or `"area"`: shared scale), `orientation`. Ridgeline: `overlap` (default 1.6 rows).

### dumbbell / slope
Two values per item: `{item: (before, after)}`, `df` with `y="item", x=("col_a", "col_b")`, or long data with `x="value", color="year"` (exactly two years). `labels=("2015", "2024")` names the two ends. Slope lines are coloured up/down (theme `positive`/`negative`), or by `highlight=`.

### waterfall
`waterfall({step: change})`. `start=("2024", 900)` adds an opening bar; `subtotals=["H1"]` turns steps into running-total bars; `total=False` hides the closing bar. Increases and decreases use the theme's `positive` and `negative` colours.

### candlestick
A DataFrame with open/high/low/close columns (detected by name, or `open=`, `high=`, … to set them) and a date column or index. `style="candle" | "ohlc"` (Folio defaults to OHLC). When there are more rows than fit (about 1 per 4 px), consecutive rows are merged into longer periods.

### treemap
`treemap({label: value})`, nested dicts of any depth (`{region: {country: {city: value}}}`), or `treemap(df, path=["region", "country", "city"], value="pop")`. Squarified layout; each level gets a tinted frame with a header (name and total) where there's room. `depth=2` stops after two levels. Labels appear where they fit.

### sunburst
The same hierarchies as `treemap`, drawn as rings: the centre shows the total, the first ring the top level, and so on outward. Angles are proportional to value. Labels run along the ring when they fit, across it when the segment is narrow but deep, and move to the tooltip otherwise. `depth=` limits the rings, `center=` changes the text in the middle.

### hexbin
`hexbin(df, x=, y=)` counts points per hexagon; `value="col", agg="mean" | "sum" | "max" | "min"` aggregates a column instead. `gridsize=` sets hexagons across (default: about one per 15 px). Skewed counts get a log colour scale automatically (`log=False` to turn off), and signed values a diverging one. Hexagons stay regular whatever the panel shape (binning happens at the final pixel size), and `lv.Chunks` works for counts.

### map
Choropleths and point maps from GeoJSON, with no extra dependency:

```python
lv.map(unemployment, geo="provinces.geojson", key="name")     # {name: value}, joined ignoring accents/case
lv.map(df, geo=geojson, id="code", value="rate", key="cod_prov")
lv.map(geojson, value="population")                            # colour by a feature property
lv.map(quakes, lon="lon", lat="lat", size="magnitude", color="depth")
```

Polygons with holes and multi-polygons are supported. Points above 50,000 become a density image. Without a basemap, a graticule with degree labels is drawn. `projection="auto"` uses a latitude-corrected equirectangular projection (right for countries and regions) and Web Mercator for continent-wide spans. Skewed positive values get a log colour scale; otherwise the 99th percentile caps it so a few extremes don't wash out the rest.

### tilemap
`tilemap({region: value}, layout="es-provinces")`: one equal square per region, placed roughly as on the map, so small regions count as much as large ones. Built in: `"es-provinces"` (52 Spanish provinces by plate code, INE number or name) and `"es-regions"` (19 autonomous communities by ISO code or name). Keys that don't match are reported in a warning. A custom layout is `{code: (column, row, name)}`. `names=True` writes full names on large tiles.

### sankey
Rows of `(source, target, value)` or an edge DataFrame. Nodes are placed in stages by their longest path from a source; flows must not form a cycle.

### radar
`radar({item: {measure: value}})` or a DataFrame with one row per item. `normalize=True` scales each measure to its own maximum (use it when measures have different units). Warns above 6 items.

### density
`density(df, x=, y=, color=)`: smoothed 2-D density with contour lines enclosing 25/50/75/90% of the points (`levels=` to change). One group gets a shaded image. Several groups get coloured contours. Works for any number of points.

### timeline
Rows of `(task, start, end[, group])` or a DataFrame (columns named task/start/end are detected). `color=` groups tasks, `progress=` shades the completed part, and tasks with no end become milestone diamonds. On a date axis, `today` (auto) draws a line at the current date when it's in range.

### calendar
Dates (counted per day) or dates with values (`calendar(df)` detects a date and a value column; `agg="sum" | "mean"`). One block per year, weeks as columns.

### sparkline / stat
`sparkline(values)`: a word-sized line with the last value. `stat(value, label=, previous= | delta=, spark=, good="up" | "down" | None, note=)`: a KPI tile. The change is shown as ▲/▼ with a sign and colour, so it doesn't rely on colour alone.

## Layouts: grids and facets

```python
lv.line(df, x="month", y="gwh", color="source", facet="region")        # small multiples
chart.facet("region", cols=2, share="y")                                # same, chained
lv.grid([c1, c2, c3], cols=3, title="Overview", share="none")
```

Panels share one colour per series and one legend (when they show the same series), and axis ranges when `share` is `"both"` (default for facets), `"x"` or `"y"`. Axis titles appear once: x on the bottom row, y on the first column. In Folio, panels are labelled (a), (b), (c). Grids save to every format, like charts.

## Data larger than memory

`lv.Chunks(source)` wraps data that arrives in pieces. `source` is a function returning a fresh iterable of chunks (called once per pass), or a list of chunks. A chunk can be an array, a dict of arrays, a pandas/polars DataFrame or a pyarrow RecordBatch.

| Chart | How it streams |
|---|---|
| `line` | extent pass, then per-chunk M4 on a shared 16k-column grid. Chunks must arrive sorted by x. |
| `scatter` | extent pass, then a 2048 × 2048 count grid, always drawn as density. |
| `histogram` | range + 1M-value sample pass for the bins, then a counting pass. Counts are exact. |
| `bar` | one group-by pass: count, sum, mean, min, max or std per category (and per `color=` group). `error="ci"` works from the streamed moments. Exact. |
| `heatmap` | one group-by pass over `x` × `y` (counts, or `agg` of `value=`). Exact. |
| `box`, `violin`, `ridgeline` | group ranges, then a 4,096-bin histogram per group, turned into a quantile-preserving sample. Percentiles are exact to 1/4,096 of each group's range; group sizes are the true ones. |
| `hexbin` | extent pass, then a fine count grid binned into hexagons. |

Memory use is bounded by the chunk size (plus one small array per group). `np.memmap` arrays don't need `Chunks`: pass them directly. Weekdays and months keep calendar order in streamed categories.

## Interactive HTML

`chart.save("chart.html")` writes one self-contained file with no external scripts. Hover shows each mark's value in a styled tooltip; on line charts a crosshair reads out every series at the pointer. The scroll wheel zooms around the pointer, dragging pans, and double-click resets. Below the chart, a "Description and data" section holds the text description and the data table with a CSV download (`to_html(data=False)` leaves it out). `chart.show()` outside a notebook opens this page in the browser.

## Accessibility

Every chart carries a plain-language description of what it shows: chart type, series, ranges, extremes, the change from start to end, correlation for scatter plots.

```python
chart.describe()        # "Energy output. Line chart of 3 series (Solar, Wind and Hydro), month from ..."
chart.table()           # the plotted data: .to_csv("data.csv"), .to_html(), .to_pandas()
lv.bar(data, alt="Sales rose in every region")   # your own alt text
lv.bar(data, texture=True)                       # a pattern per series as well as a colour
```

- SVGs get `<title>` and `<desc>` linked with `aria-labelledby`, so screen readers announce the chart.
- `texture=True` adds a second encoding (diagonal, back-diagonal, dots, cross, rows, columns) to bars, pies, areas and overlaid histograms, legends included, in SVG and PDF.
- Folio already encodes series with dashes and markers, and Instrument with a readout; direct labels are used where they fit.
- Palettes are checked for colour-blind readers (see Themes).

## Themes

| Theme | For | Signature |
|---|---|---|
| `folio` | papers, theses, print | Serif type, range-frame axes, direct labels, dash + marker encoding, hatching, numbered captions |
| `ledger` | dashboards, decks | Quiet grey structure, one accent, dashed grid, reference pills, end values |
| `instrument` | engineering, monitoring | Dark, monospace, boxed frame, inward ticks, readout panel, rug marks |
| `fjord` | reports, teaching | Soft background, smooth curves, lead-area fill, pill bars, degree-sized nodes |

```python
t = lv.themes.get("folio")
my = t.replace(font_size=9, palette=("#000000", "#666666"), line_width=1.0)
lv.themes.register("thesis", my)
lv.themes.set_default("thesis")
```

Each field is documented in `lineova/themes.py`. You can change fonts, colours, the axis style (`range`, `baseline`, `box`, `none`), grid, ticks, marker styles, bar rounding, legend style, network node and edge style, and padding. A derived theme keeps its `family`, so it keeps that style's behaviour (a renamed Folio still draws range frames and OHLC bars).

Dark and light variants: `ledger-dark`, `folio-dark`, `fjord-dark` and `instrument-light`. Series keep the same hue order as in the light themes; lightness is re-stepped for the surface. `lv.themes.dark("ledger")` and `lv.themes.light("instrument")` look them up.

A theme from a brand colour:

```python
lv.themes.from_brand("#0f766e", base="fjord", name="acme")        # dark=True for a dark version
print(lv.themes.check_palette("acme"))                           # the checks, PASS/WARN/FAIL
```

`from_brand` keeps your colour first and generates the rest of the palette so that neighbouring colours stay distinguishable for protan, deutan and tritan vision (ΔE ≥ 8), for normal vision (ΔE ≥ 15), and contrast with the background (≥ 3:1), plus sequential and diverging ramps. If eight colours can't all pass, it returns fewer rather than confusable ones.

## Output

```python
chart.save("fig.svg")
chart.save("fig.pdf")               # vector, standard PDF fonts, selectable text
chart.save("fig.png", dpi=300)      # needs lineova[png], cairosvg or playwright
svg_text = chart.to_svg()
pdf_bytes = chart.to_pdf()
png_bytes = chart.to_png(scale=3)
chart.show()                        # notebook inline, or opens a browser
```

The PNG backend can be forced with `LINEOVA_PNG_BACKEND=resvg|cairosvg|playwright`.

## Performance notes

- Lines: sorted x is required for per-pixel reduction. Unsorted x is sorted once (O(n log n)). Pass sorted data for the fastest path.
- Scatter: density mode costs one pass over the data in 4M-row chunks. `render="vector"` above ~50k points gives large files.
- Networks: the force layout is O(n²) per step up to 1,500 nodes, then O(n + grid) with FFT repulsion. Pass `positions=` if you already have coordinates.
- Everything is deterministic: the same input gives the same picture.

## What "auto" does

| Decision | Rule |
|---|---|
| Colour scales | Sequential for magnitudes, diverging (symmetric around 0) for signed values, log for skewed positive counts. |
| Legend | None for one series. Direct labels in Folio (≤ 8 lines). Readout in Instrument (≤ 5 lines). A top row otherwise, or a right-hand column above 8. |
| Colours | Theme palette in fixed order, so a series keeps its colour. Above 8 series, the rest are muted and grouped as "Other" (with a warning). |
| Series detection | In a DataFrame, a text column with 2–12 distinct values becomes the series identity. |
| Axis range | Round tick values that contain the data. Zero is included for bars, areas and histograms. Lines touch the x edges. |
| Tick count | About one tick per 90 px horizontally and per 46 px vertically, thinned until labels don't collide |
| Number format | Decimals from the tick step. 12k / 3.4M for large values. A real minus sign. |
| Dates | Tick unit from milliseconds to centuries. Labels show a larger unit when it changes ("Jan 2025", "Apr", …). |
| Category labels | Rotated when they don't fit. Bars turn horizontal instead when that reads better. |
| Size | 720 × 440 (Folio 640 × 400). Horizontal bars and heatmaps grow with the number of rows. |
