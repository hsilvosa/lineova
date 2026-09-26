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
| `node_size` | px radius, or `"degree"` |
| `edge_labels` | weights on edges: auto for weighted graphs with 30 or fewer edges |
| `directed` | Draw arrows. Auto for directed `Graph`s. |
| `seed` | Layout random seed (layouts are deterministic) |

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

Each field is documented in `lineova/themes.py`. You can change fonts, colours, the axis style (`range`, `baseline`, `box`, `none`), grid, ticks, marker styles, bar rounding, legend style, network node and edge style, and padding.

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
| Legend | None for one series. Direct labels in Folio (≤ 8 lines). Readout in Instrument (≤ 5 lines). A top row otherwise, or a right-hand column above 8. |
| Colours | Theme palette in fixed order, so a series keeps its colour. Above 8 series, the rest are muted and grouped as "Other" (with a warning). |
| Series detection | In a DataFrame, a text column with 2–12 distinct values becomes the series identity. |
| Axis range | Round tick values that contain the data. Zero is included for bars, areas and histograms. Lines touch the x edges. |
| Tick count | About one tick per 90 px horizontally and per 46 px vertically, thinned until labels don't collide |
| Number format | Decimals from the tick step. 12k / 3.4M for large values. A real minus sign. |
| Dates | Tick unit from milliseconds to centuries. Labels show a larger unit when it changes ("Jan 2025", "Apr", …). |
| Category labels | Rotated when they don't fit. Bars turn horizontal instead when that reads better. |
| Size | 720 × 440 (Folio 640 × 400). Horizontal bars and heatmaps grow with the number of rows. |
