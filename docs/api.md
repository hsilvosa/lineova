# API reference

Generated from the source by `tools/build_docs.py`. Every chart function returns a [`Chart`](#chart), so the methods below work on its result.

## Chart functions

### `lv.line`

```python
lv.line(data: Any = None, x: Any = None, y: Any = None, color: Any = "auto", **options) -> Chart
```

Line chart. ``data`` can be a list, array, dict of series, or a DataFrame.

Useful options: ``title``, ``subtitle``, ``theme`` (folio | ledger | instrument | fjord),
``highlight``, ``legend``, ``x_label``/``y_label``, ``x_range``/``y_range``,
``x_scale="log"``, ``curve="smooth"``, ``markers=True``.

Chart-specific options: `width="auto"`, `curve="auto"`, `markers="auto"`, `dash=None`, `label=None`, `render="auto"`, `values="auto"`, `band=None`.

### `lv.area`

```python
lv.area(data: Any = None, x: Any = None, y: Any = None, color: Any = "auto", **options) -> Chart
```

Area chart. Several series stack; ``normalize=True`` shows each as a share of 100%.

Chart-specific options: `stack="auto"`, `normalize=False`.

### `lv.bar`

```python
lv.bar(data: Any = None, x: Any = None, y: Any = None, color: Any = None, **options) -> Chart
```

Bar chart from ``{label: value}``, a Series, raw labels (counted) or a DataFrame.

``color=`` groups bars, ``stack=True`` stacks them, ``normalize=True`` shows 100% stacks,
``orientation="h"`` forces horizontal, ``reference="mean"`` adds a reference line.

Chart-specific options: `orientation="auto"`, `stack="auto"`, `normalize=False`, `sort="auto"`, `agg='sum'`, `top="auto"`, `labels="auto"`, `format=None`, `reference=None`, `label=None`, `error=None`.

### `lv.scatter`

```python
lv.scatter(data: Any = None, x: Any = None, y: Any = None, color: Any = "auto", **options) -> Chart
```

Scatter/bubble plot. ``size=`` maps a column to bubble area, ``fit=True`` adds a trend line.

Above 50,000 points it switches to a density image automatically (``render="vector"`` to force).

Chart-specific options: `size=None`, `label=None`, `fit=False`, `render="auto"`, `opacity="auto"`, `marker="auto"`, `tooltips="auto"`, `shade="auto"`, `sizes=(2.5, 16.0)`, `error=None`, `x_error=None`.

### `lv.histogram`

```python
lv.histogram(data: Any = None, x: Any = None, color: Any = None, **options) -> Chart
```

Distribution of values with automatic round-numbered bins. ``bins=`` to override.

Chart-specific options: `bins="auto"`, `range=None`, `stat='count'`, `cumulative=False`, `label=None`.

### `lv.heatmap`

```python
lv.heatmap(data: Any = None, x: Any = None, y: Any = None, value: Any = None, **options) -> Chart
```

Heatmap from a 2-D array, a DataFrame (index x columns), or long data (x, y, value columns).

Chart-specific options: `cmap="auto"`, `vmin=None`, `vmax=None`, `annotate="auto"`, `format=None`, `agg='mean'`, `label=None`.

### `lv.box`

```python
lv.box(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart
```

Box plot per group: ``{"A": values, "B": values}`` or ``box(df, x="group", y="value")``.

Chart-specific options: `orientation="auto"`, `points="auto"`, `whisker=1.5`, `mean=False`, `label=None`.

### `lv.violin`

```python
lv.violin(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart
```

Violin plot: the full distribution per group, with quartiles and median inside.

Chart-specific options: `orientation="auto"`, `inner="auto"`, `bw=None`, `scale='width'`, `label=None`.

### `lv.ridgeline`

```python
lv.ridgeline(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart
```

Ridgeline (joyplot): one density curve per group, stacked and slightly overlapping.

Chart-specific options: `overlap=1.6`, `bw=None`, `label=None`.

### `lv.pie`

```python
lv.pie(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart
```

Pie or donut. ``donut=True/False``; more than 6 slices fold into "Other" automatically.

Chart-specific options: `donut="auto"`, `top="auto"`, `sort="auto"`, `labels="auto"`, `center="auto"`, `format=None`, `agg='sum'`, `start=90.0`.

### `lv.donut`

```python
lv.donut(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart
```

Donut chart (a pie with a hole showing the total).

Chart-specific options: `donut="auto"`, `top="auto"`, `sort="auto"`, `labels="auto"`, `center="auto"`, `format=None`, `agg='sum'`, `start=90.0`.

### `lv.dumbbell`

```python
lv.dumbbell(data: Any = None, x: Any = None, y: Any = None, color: Any = None, **options) -> Chart
```

Two values per row joined by a line: ``dumbbell({"A": (3, 5)})`` or
``dumbbell(df, y="country", x=("2019", "2024"))``.

Chart-specific options: `labels=None`, `sort="auto"`, `values="auto"`, `agg='mean'`.

### `lv.slope`

```python
lv.slope(data: Any = None, x: Any = None, y: Any = None, color: Any = None, **options) -> Chart
```

Slope chart: each item's value before and after, as a line between two axes.

Chart-specific options: `labels=None`, `agg='mean'`, `format=None`.

### `lv.waterfall`

```python
lv.waterfall(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart
```

Waterfall (bridge): ``waterfall({"Sales": 120, "Costs": -80}, start=("2023", 400))``.

Chart-specific options: `start=None`, `total="auto"`, `subtotals=None`, `labels="auto"`, `format=None`, `agg='sum'`.

### `lv.candlestick`

```python
lv.candlestick(data: Any = None, x: Any = None, **options) -> Chart
```

Candlestick/OHLC from a DataFrame with open/high/low/close columns (names detected).

Chart-specific options: `open=None`, `high=None`, `low=None`, `close=None`, `style="auto"`, `max_candles="auto"`.

### `lv.treemap`

```python
lv.treemap(data: Any = None, **options) -> Chart
```

Treemap: ``treemap({"A": 10, "B": 4})``, nested dicts of any depth, or
``treemap(df, path=["region", "country", "city"], value="pop")``. ``depth=`` limits the levels drawn.

Chart-specific options: `path=None`, `labels="auto"`, `format=None`, `agg='sum'`, `depth=None`.

### `lv.sunburst`

```python
lv.sunburst(data: Any = None, **options) -> Chart
```

Sunburst: a hierarchy as rings, the angle proportional to value.

``data`` is nested dicts of any depth ({"Europe": {"Spain": {"Madrid": 7}}}) or a DataFrame with
``path=["region", "country", "city"]`` and ``value=``. Options: ``depth=`` (rings to show),
``labels=``, ``format=``, ``center=`` (text in the middle; the total by default).

Chart-specific options: `path=None`, `depth=None`, `labels="auto"`, `format=None`, `agg='sum'`, `center="auto"`, `start=90.0`.

### `lv.sankey`

```python
lv.sankey(data: Any = None, **options) -> Chart
```

Sankey flow diagram from (source, target, value) rows or an edge DataFrame.

Chart-specific options: `node_width="auto"`, `padding="auto"`, `format=None`, `iterations=24`.

### `lv.radar`

```python
lv.radar(data: Any = None, **options) -> Chart
```

Radar chart: ``radar({"Model A": {"Speed": 7, "Cost": 4, ...}, "Model B": {...}})``.

Chart-specific options: `axes=None`, `normalize=False`, `fill="auto"`, `range=None`.

### `lv.density`

```python
lv.density(data: Any = None, x: Any = None, y: Any = None, color: Any = None, **options) -> Chart
```

2-D density with contour lines (for very many points, or to compare groups' shapes).

Chart-specific options: `levels="auto"`, `fill="auto"`, `points="auto"`, `bandwidth=None`, `grid=160`.

### `lv.hexbin`

```python
lv.hexbin(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart
```

Hexagonal binning of a point cloud: how many points (or the mean of ``value``) fall in each hexagon.

Works for millions of rows and for ``lv.Chunks``. Options: ``value=`` (column to aggregate),
``agg="count" | "sum" | "mean" | "max" | "min"``, ``gridsize=`` (hexagons across), ``mincount=1``,
``log="auto"`` (log colour scale for skewed counts), ``cmap=`` (colour stops), ``label=``.

Chart-specific options: `agg="auto"`, `gridsize="auto"`, `mincount=1`, `log="auto"`, `cmap="auto"`, `label=None`, `border="auto"`.

### `lv.map`

```python
lv.map(data: Any = None, geo: Any = None, **options) -> Chart
```

Maps from GeoJSON and/or points.

* Choropleth: ``lv.map(values, geo="regions.geojson", key="name")`` where ``values`` is
  {region: number}, a Series, or a DataFrame with ``id=`` and ``value=`` columns;
  or ``lv.map(geojson, value="population")`` to colour by a feature property.
* Points: ``lv.map(df, lon="lon", lat="lat", size="mag", color="depth")``, optionally over
  ``geo=`` as a basemap. Above 50,000 points they are drawn as a density image.

Options: ``projection="auto" | "equirectangular" | "mercator"``, ``cmap=``, ``vmin=``, ``vmax=``,
``labels=``, ``format=``, ``graticule=``, ``label=`` (colour-bar title).

Chart-specific options: `geo=None`, `key=None`, `id=None`, `lon=None`, `lat=None`, `size=None`, `projection="auto"`, `cmap="auto"`, `vmin=None`, `vmax=None`, `labels="auto"`, `format=None`, `graticule="auto"`, `label=None`, `missing="auto"`.

### `lv.tilemap`

```python
lv.tilemap(data: Any = None, **options) -> Chart
```

Tile map: one equal square per region, placed roughly as on the map, so every region is
equally visible. ``lv.tilemap({"M": 6.8, "B": 5.7}, layout="es-provinces")``.

Built-in layouts: ``"es-provinces"`` (52 Spanish provinces; plate codes, INE numbers or names)
and ``"es-regions"`` (19 autonomous communities; ISO codes or names). A custom layout is
``{code: (column, row, name)}``. Options: ``id=``/``value=`` for DataFrames, ``cmap=``,
``format=``, ``labels=``, ``names=`` (full names instead of codes on large tiles).

Chart-specific options: `layout='es-provinces'`, `id=None`, `cmap="auto"`, `vmin=None`, `vmax=None`, `labels="auto"`, `format=None`, `label=None`, `names="auto"`.

### `lv.timeline`

```python
lv.timeline(data: Any = None, **options) -> Chart
```

Timeline / Gantt: rows of (task, start, end); ``color=`` groups, ``progress=`` shades done work.

Chart-specific options: `task=None`, `start=None`, `end=None`, `progress=None`, `today="auto"`, `labels="auto"`.

### `lv.calendar`

```python
lv.calendar(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart
```

Calendar heatmap: one cell per day, weeks as columns (GitHub-style).

Chart-specific options: `agg='sum'`, `label=None`, `format=None`.

### `lv.sparkline`

```python
lv.sparkline(data: Any = None, x: Any = None, **options) -> Chart
```

Word-sized line chart with no axes, for tables and dashboards.

Chart-specific options: `area="auto"`, `dots=True`, `band=None`.

### `lv.stat`

```python
lv.stat(value: Any = None, **options) -> Chart
```

Stat tile: one big number with a label, an optional change (``delta=``) and a sparkline (``spark=``).

Chart-specific options: `label=None`, `delta=None`, `previous=None`, `spark=None`, `format=None`, `delta_format="auto"`, `good='up'`, `note=None`.

### `lv.network`

```python
lv.network(data: Any = None, **options) -> Chart
```

Node-link diagram from a ``Graph``, an edge list, an edge DataFrame or a networkx graph.

``path=("A", "Z")`` highlights the shortest path; ``groups="community"`` colours clusters;
``layout="circular" | "layered" | "force"``.

Chart-specific options: `directed=None`, `layout="auto"`, `labels="auto"`, `node_size="auto"`, `groups="auto"`, `edge_labels="auto"`, `path=None`, `highlight=None`, `positions=None`, `seed=0`.

## Common options

Accepted by every chart function as keywords, and by `Chart(...)`:

| Option | Meaning |
|---|---|
| `title / subtitle` | Heading text (in `folio`, the figure caption) |
| `caption / number / source` | Text under the chart; `number` gives 'Figure N.' |
| `theme` | `folio`, `ledger`, `instrument`, `fjord`, their variants (`ledger-dark`, `folio-dark`, `fjord-dark`, `instrument-light`), a registered name or a `Theme` |
| `width / height / size` | Pixels, or a preset: `column`, `page`, `wide`, `slide`, `square`, `dashboard`, `a4` |
| `legend` | `auto`, `top`, `bottom`, `right`, `direct`, `readout`, `none` |
| `palette / highlight` | Colours for series, and series to emphasise |
| `facet / facet_cols / share` | Small multiples by a column |
| `texture` | `True` adds a pattern per series (a second encoding besides colour) |
| `alt` | Your own text description (otherwise generated; see `describe()`) |
| `x_* / y_*` | Axis options: `label`, `scale`, `range`, `ticks`, `format`, `zero`, `grid`, `reverse`, `visible` |

## Chart

```python
lv.Chart(data: Any = None, **options)
```

A figure made of one or more layers (line, bar, scatter, ...).

- **`.annotate(x: Any, y: Any, text: str, *, dx: float = 8, dy: float = -8) -> Chart`**: Text note pointing at a data position.
- **`.area(data=None, x=None, y=None, color="auto", **kw) -> Chart`**: Add a area layer. Takes the same options as ``lv.area()``.
- **`.band(x: Any = None, y: Any = None, label: Optional[str] = None, *, color: Optional[str] = None) -> Chart`**: Shade a range, e.g. ``band(x=("2024-06-01", "2024-08-31"), label="Summer")``.
- **`.bar(data=None, x=None, y=None, color=None, **kw) -> Chart`**: Add a bar layer. Takes the same options as ``lv.bar()``.
- **`.box(data=None, x=None, y=None, **kw) -> Chart`**: Add a box layer. Takes the same options as ``lv.box()``.
- **`.calendar(data=None, x=None, y=None, **kw) -> Chart`**: Add a calendar layer. Takes the same options as ``lv.calendar()``.
- **`.candlestick(data=None, x=None, **kw) -> Chart`**: Add a candlestick layer. Takes the same options as ``lv.candlestick()``.
- **`.caption(text: str, number: Optional[int] = None) -> Chart`**: Paragraph under the chart. ``number`` adds 'Figure N.' (Folio).
- **`.density(data=None, x=None, y=None, color=None, **kw) -> Chart`**: Add a density layer. Takes the same options as ``lv.density()``.
- **`.describe() -> str`**: A plain-language description of the chart (alt text): what is plotted, ranges, extremes, trends.
- **`.dumbbell(data=None, x=None, y=None, color=None, **kw) -> Chart`**: Add a dumbbell layer. Takes the same options as ``lv.dumbbell()``.
- **`.facet(column: Any, cols: Any = "auto", share: str = 'both') -> Chart`**: Small multiples: one panel per value of ``column``, with shared axes and one legend.
- **`.heatmap(data=None, x=None, y=None, value=None, **kw) -> Chart`**: Add a heatmap layer. Takes the same options as ``lv.heatmap()``.
- **`.hexbin(data=None, x=None, y=None, **kw) -> Chart`**: Add a hexbin layer. Takes the same options as ``lv.hexbin()``.
- **`.highlight(*keys) -> Chart`**: Emphasise some series/categories/nodes; everything else is muted.
- **`.histogram(data=None, x=None, color=None, **kw) -> Chart`**: Add a histogram layer. Takes the same options as ``lv.histogram()``.
- **`.hline(y: Any, label: Optional[str] = None, *, color: Optional[str] = None, dash=(4, 3)) -> Chart`**: Horizontal reference line, e.g. a target. ``y="mean"`` uses the data mean.
- **`.legend(position: Any = "auto") -> Chart`**: auto | top | bottom | right | direct | readout | none.
- **`.line(data=None, x=None, y=None, color="auto", **kw) -> Chart`**: Add a line layer. Takes the same options as ``lv.line()``.
- **`.map(data=None, geo=None, **kw) -> Chart`**: Add a map layer. Takes the same options as ``lv.map()``.
- **`.network(data=None, **kw) -> Chart`**: Add a network layer. Takes the same options as ``lv.network()``.
- **`.palette(colors: Any) -> Chart`**: A list of colours, a {series: colour} dict, or one colour for everything.
- **`.pie(data=None, x=None, y=None, **kw) -> Chart`**: Add a pie layer. Takes the same options as ``lv.pie()``.
- **`.radar(data=None, **kw) -> Chart`**: Add a radar layer. Takes the same options as ``lv.radar()``.
- **`.ridgeline(data=None, x=None, y=None, **kw) -> Chart`**: Add a ridgeline layer. Takes the same options as ``lv.ridgeline()``.
- **`.sankey(data=None, **kw) -> Chart`**: Add a sankey layer. Takes the same options as ``lv.sankey()``.
- **`.save(path: str | os.PathLike, *, dpi: Optional[float] = None, scale: Optional[float] = None, format: Optional[str] = None) -> str`**: Save to .svg, .pdf, .png or .html (format from the extension). Returns the path.
- **`.scatter(data=None, x=None, y=None, color="auto", **kw) -> Chart`**: Add a scatter layer. Takes the same options as ``lv.scatter()``.
- **`.set(**options) -> Chart`**: Set any chart option by keyword. Axis options use ``x_``/``y_`` prefixes.
- **`.show() -> None`**: Display in a notebook, or open an interactive page in the default browser.
- **`.size(width: Any = "auto", height: Any = "auto") -> Chart`**: ``size(800, 450)``, ``size(width=600)`` or a preset: ``size("column")``.
- **`.slope(data=None, x=None, y=None, color=None, **kw) -> Chart`**: Add a slope layer. Takes the same options as ``lv.slope()``.
- **`.source(text: str) -> Chart`**: 'Source: …' line under the chart.
- **`.sparkline(data=None, x=None, **kw) -> Chart`**: Add a sparkline layer. Takes the same options as ``lv.sparkline()``.
- **`.stat(value=None, **kw) -> Chart`**: Add a stat layer. Takes the same options as ``lv.stat()``.
- **`.subtitle(text: str) -> Chart`**: Second heading line.
- **`.sunburst(data=None, **kw) -> Chart`**: Add a sunburst layer. Takes the same options as ``lv.sunburst()``.
- **`.table()`**: The data behind the chart as a ``Table`` (``.to_csv()``, ``.to_html()``, ``.to_pandas()``).
- **`.theme(theme) -> Chart`**: Use a theme by name or a ``Theme`` object.
- **`.tilemap(data=None, **kw) -> Chart`**: Add a tile-map layer. Takes the same options as ``lv.tilemap()``.
- **`.timeline(data=None, **kw) -> Chart`**: Add a timeline layer. Takes the same options as ``lv.timeline()``.
- **`.title(text: str, subtitle: Optional[str] = None) -> Chart`**: Main heading, optionally with a subtitle.
- **`.to_html(*, title: Optional[str] = None, data: bool = True) -> str`**: Standalone HTML page: hover tooltips, a crosshair readout on line charts, wheel/drag zoom,
- **`.to_pdf() -> bytes`**: The chart as a vector PDF (bytes). Text stays selectable.
- **`.to_png(scale: Optional[float] = None, dpi: Optional[float] = None) -> bytes`**: The chart as PNG bytes. Default 2x; ``dpi=300`` for print. Needs a PNG backend (``lineova[png]``).
- **`.to_svg() -> str`**: The chart as an SVG document (string).
- **`.treemap(data=None, **kw) -> Chart`**: Add a treemap layer. Takes the same options as ``lv.treemap()``.
- **`.violin(data=None, x=None, y=None, **kw) -> Chart`**: Add a violin layer. Takes the same options as ``lv.violin()``.
- **`.vline(x: Any, label: Optional[str] = None, *, color: Optional[str] = None, dash=(4, 3)) -> Chart`**: Vertical reference line; ``x="mean"`` uses the data mean.
- **`.waterfall(data=None, x=None, y=None, **kw) -> Chart`**: Add a waterfall layer. Takes the same options as ``lv.waterfall()``.
- **`.x_axis(**options) -> Chart`**: Set x-axis options (``label``, ``scale``, ``range``, ``ticks``, ``format``, ``zero``, ``grid``, ``reverse``, ``visible``).
- **`.y_axis(**options) -> Chart`**: Set y-axis options (same names as ``x_axis``).

## Grid

```python
lv.grid(charts: Sequence, cols: Any = "auto", **options) -> Grid
```

Several charts laid out in rows and columns, with one title, one legend and aligned sizes.

``share="both" | "x" | "y" | "none"`` makes panels use the same axis ranges, so they can be compared.

- **`.describe()`**: Plain-language description of every panel (alt text); written into the SVG ``<desc>``.
- **`.tables()`**: The data table of each panel (``Table`` objects, ``None`` where a panel has none).

## Chunks

```python
lv.Chunks(source)
```

Data read piece by piece, for inputs larger than memory.

    lv.histogram(lv.Chunks(lambda: pq.ParquetFile("big.parquet").iter_batches(columns=["v"])), x="v")
    lv.line(lv.Chunks(my_reader), x="t", y="value")

``source`` is a function returning a fresh iterable of chunks (it's called
once per pass; most charts need two passes), or a list of chunks. A chunk
can be a NumPy array (one column), a dict of arrays, a pandas/polars
DataFrame or a pyarrow RecordBatch/Table.

## Graph

Directed or undirected weighted graph (adjacency dict of dicts).

- **`.add_edge(u: Node, v: Node, weight: float = 1.0) -> Graph`**: Add an edge (and its nodes). Adding it again replaces the weight.
- **`.add_edges(edges: Iterable) -> Graph`**: Add many ``(u, v)`` or ``(u, v, weight)`` edges.
- **`.add_node(n: Node, **attrs) -> Graph`**: Add a node (if new) and set attributes, e.g. ``pos=(x, y)`` or ``label=``.
- **`.astar(source: Node, target: Node, heuristic=None) -> list`**: A* shortest path. ``heuristic(node, target)`` must never overestimate the remaining cost.
- **`.attrs(n: Node) -> dict`**: A copy of the node's attributes.
- **`.betweenness(weighted: bool = True, normalized: bool = True, k: Optional[int] = None, seed: int = 0) -> dict`**: Betweenness centrality (Brandes): how often a node lies on shortest paths.
- **`.bfs(start: Node) -> list`**: Nodes in breadth-first order from ``start``.
- **`.closeness(weighted: bool = True) -> dict`**: Closeness centrality (Wasserman–Faust, handles disconnected graphs).
- **`.communities(seed: int = 0, max_iter: int = 30) -> list[set]`**: Groups of densely connected nodes (label propagation). Fast, approximate.
- **`.connected_components() -> list[set]`**: Components, largest first (weakly connected for directed graphs).
- **`.degree(n: Optional[Node] = None)`**: Degree of one node, or a dict for all nodes (in + out for directed graphs).
- **`.dfs(start: Node) -> list`**: Nodes in depth-first (pre-)order from ``start``. Iterative: no recursion limit.
- **`.distance(source: Node, target: Node, weighted: bool = True) -> float`**: Cost of the cheapest path, or ``inf`` if unreachable.
- **`.draw(**options)`**: Shortcut for ``lv.network(graph, **options)``.
- **`.has_cycle() -> bool`**: True if the graph contains a cycle (directed or undirected).
- **`.has_edge(u, v) -> bool`**: True if there is an edge from ``u`` to ``v``.
- **`.is_connected() -> bool`**: True if every node can reach every other (ignoring direction).
- **`.is_weighted() -> bool`**: True unless every edge has weight 1.
- **`.max_flow(source: Node, sink: Node) -> tuple[float, dict]`**: Maximum flow (Edmonds–Karp); edge weights are capacities. Returns (value, {(u, v): flow}).
- **`.minimum_spanning_tree() -> Graph`**: Kruskal. For a disconnected graph, returns a spanning forest.
- **`.neighbors(n: Node) -> list`**: Nodes reachable from ``n`` in one step.
- **`.number_of_edges() -> int`**: Number of edges (self-loops count once).
- **`.pagerank(damping: float = 0.85, tol: float = 1e-10, max_iter: int = 200) -> dict`**: PageRank (power iteration, vectorised). Edge weights are used as link strength.
- **`.path_weight(path: list) -> float`**: Sum of the edge weights along ``path``.
- **`.predecessors(n: Node) -> list`**: Nodes with an edge into ``n`` (same as neighbors for undirected graphs).
- **`.remove_edge(u: Node, v: Node) -> Graph`**: Remove one edge. Raises ``GraphError`` if it doesn't exist.
- **`.remove_node(n: Node) -> Graph`**: Remove a node and every edge touching it.
- **`.shortest_path(source: Node, target: Node, weighted: bool = True) -> list`**: Cheapest path as a list of nodes. Raises ``GraphError`` if unreachable.
- **`.shortest_paths(source: Node, weighted: bool = True) -> tuple[dict, dict]`**: Distances and predecessors from ``source`` (Dijkstra, or BFS if unweighted).
- **`.strongly_connected_components() -> list[set]`**: Tarjan's algorithm (iterative). For undirected graphs this equals connected_components().
- **`.subgraph(nodes: Iterable) -> Graph`**
- **`.to_arrays() -> tuple[list, np.ndarray, np.ndarray, np.ndarray]`**: (nodes, src_index, dst_index, weights) for fast numeric work.
- **`.topological_sort() -> list`**: Kahn's algorithm. Raises ``GraphError`` on cycles or undirected graphs.
- **`.weight(u, v) -> float`**: Weight of the edge ``u``–``v``.

## Themes

Themes: every visual decision the library makes lives here.

A theme is an immutable dataclass. To customise one, derive a copy::

    import lineova as lv
    brand = lv.themes.get("ledger").replace(accent="#0f766e", palette=("#0f766e", "#b45309"))
    lv.themes.register("brand", brand)
    lv.line(data, theme="brand")

- `lv.themes.get(name)`, `lv.themes.register(name, theme)`, `lv.themes.names()`, `lv.themes.set_default(name)`, `lv.themes.dark(name)`, `lv.themes.light(name)`

- `lv.themes.from_brand(color: str, base: str | Theme = 'ledger', *, dark: bool = False, name: str | None = None, background: str | None = None, n: int = 8) -> Theme`: Build a theme around a brand colour.
- `lv.themes.check_palette(colors, background: str = '#ffffff')`: Check a categorical palette against a background: lightness band, chroma, colour-blind

`Theme` fields: `name`, `family`, `font`, `font_kind`, `font_size`, `title_size`, `subtitle_size`, `title_weight`, `italic_labels`, `uppercase_header`, `background`, `plot_background`, `ink`, `ink_secondary`, `ink_muted`, `axis_color`, `grid_color`, `dark`, `palette`, `accent`, `muted`, `sequential`, `diverging`, `positive`, `negative`, `axis_style`, `grid`, `grid_dash`, `grid_width`, `tick_direction`, `tick_length`, `axis_width`, `line_width`, `curve`, `dashes`, `series_markers`, `marker_size`, `scatter_style`, `end_markers`, `area_opacity`, `lead_area`, `bar_radius`, `bar_gap`, `bar_highlight`, `bar_value_labels`, `legend`, `legend_marker`, `caption_style`, `node_style`, `edge_style`, `edge_color`, `padding`.
