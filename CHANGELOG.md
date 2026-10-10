# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]
### Added
- Charts: `chord`, `arc` (arc diagram), `parallel` (parallel coordinates), `streamgraph`, `horizon`, `marimekko`
  and `bullet`.
- Evaluation and distribution helpers that return ordinary charts: `roc`, `pr`, `calibration`,
  `confusion_matrix`, `ecdf`, `qq` and `correlation` (clustered correlation matrix; Pearson or Spearman).
- Gallery: a "New in 0.4" section with all of them.

- Interactive HTML: line charts on a number or date axis get a data-level zoom. The wheel, a shift-drag brush and a
  range strip change the visible x range; lines are redrawn at the new resolution and the axes are re-ticked
  (date and number ticks prepared in Python at many densities). Also "Fit y to view", series buttons to hide lines, a
  reset button, and linked zoom between grid panels with the same x range. SVG, PDF and PNG output is unchanged.

- Graphs: `core_numbers`, `k_core`, `triangles`, `clustering`, `average_clustering`, `transitivity`,
  `articulation_points`, `bridges`, `eccentricity`, `diameter`, `bellman_ford`, `floyd_warshall`, `louvain`,
  `modularity` and `to_networkx`. All are tested against networkx.
- Network layouts `radial` (`root=`) and `bipartite` (`sets=`); `groups="louvain"`; the arc diagram colours nodes by community.

### Changed
- Facets share the density threshold across the whole chart: panels that add up to more than 50,000 points
  switch to density rendering (12 x 200k scatter: 8.3 MB of SVG down to 0.3 MB).
- `benchmarks/bench.py` has 14 cases, `--save`, `--compare` and `--only`; `benchmarks/baseline.json` holds the 0.3.0 timings.

## [0.3.0] — 2026-09-30
### Added
- Charts: `hexbin` (counts or aggregated values per hexagon, log/diverging colour scales, streams `lv.Chunks`),
  `sunburst`, `map` (GeoJSON choropleths with holes and multi-polygons, point maps with a density image above
  50k points, graticule, latitude-corrected equirectangular or Mercator projection) and `tilemap` (Spanish
  provinces and autonomous communities built in, custom layouts).
- Treemaps of any depth, from nested dicts or `path=[...]` with any number of columns (`depth=` to limit).
- Out-of-core `bar` and `heatmap` (streaming group-by: sum, mean, count, min, max, std, error bars) and
  `box` / `violin` / `ridgeline` (per-group quantile sketches) from `lv.Chunks`.
- Themes: `ledger-dark`, `folio-dark`, `fjord-dark`, `instrument-light`; `lv.themes.dark()` / `light()`;
  `lv.themes.from_brand(colour)` generates a checked palette and ramps; `lv.themes.check_palette()` runs the
  colour checks (lightness, chroma, colour-blind and normal-vision separation, contrast).
- Accessibility: `chart.describe()` (generated alt text, written into every SVG as `<title>`/`<desc>`),
  `chart.table()` / `grid.tables()` (the plotted data, CSV/HTML/pandas), `alt=` and `texture=True`
  (a pattern per series on bars, pies, areas and histograms, in SVG and PDF).
- Interactive HTML: crosshair readout on line charts and a "Description and data" section with CSV download.
- `Graph.betweenness(k=)`: sampled betweenness for large graphs (used automatically for network sizing above 2,000 nodes).
- Gallery: hexbin, tile map, point map and a streamed heatmap of 12 million market offers from the real datasets.

### Changed
- Folio range frames use the data extent (no round-number padding), round their end labels to the tick
  precision and drop round ticks that would touch them; log range frames start at the first positive value.
- The zero baseline is no longer drawn through scatter, density and hexbin plots.
- Figure captions capitalise each sentence; compact numbers drop trailing zeros and roll over (999,960 → 1M).
- Themes carry a `family`, so derived and registered themes keep their style.
- Colour bars are drawn after the plot, so layers can settle their range at the final size.

### Fixed
- CI: install SciPy with the `dev` extra (networkx needs it for PageRank in the tests); GitHub Actions updated to Node 24 versions.
- The first x label no longer collides with a y label on the bottom edge; band labels stay above the data.
- Thin sankey nodes show their value; pie labels no longer crowd; bar value labels hide when wider than the bar.
- Network node labels keep their case in Folio; edge-weight pills fit their text.
- Density plots take their domain from the 0.5–99.5% quantiles instead of the outliers.

## [0.2.0] — 2026-09-26
- New charts: pie/donut, violin, ridgeline, dumbbell, slope, waterfall, candlestick/OHLC, treemap, sankey, radar,
  2-D density with contours, timeline/Gantt, calendar heatmap, sparkline, stat tile.
- Confidence bands on lines (`band=`), error bars on scatter (`error=`, `x_error=`) and bars (`error="std" | "sem" | "ci"`).
- Small multiples (`facet="column"`) and `lv.grid([...])` layouts with shared axes, colours and legend.
- Interactive HTML export (`.save("chart.html")`): tooltips, zoom, pan.
- Out-of-core input with `lv.Chunks(...)` for line, scatter and histogram.
- Graph: PageRank, betweenness, closeness, strongly connected components, max flow, A*; `node_size="pagerank"`.
- Log value axes for histograms and bars (`y_scale="log"`). Chunked scatter plots use the axis range to focus their grid.
- Documentation site (MkDocs): installation, quick start, use cases, gallery from real data (IGN earthquakes, OMIE
  electricity market), themes, graphs, performance, generated API reference, FAQ.
- Repository: contribution guide with branch model, CI on Linux/macOS/Windows × Python 3.10–3.13, release workflow
  (PyPI trusted publishing), docs deployment, issue/PR templates, citation file.
- Fixed: Folio figure captions ran into the "Figure N." label with some fonts; value labels could be clipped at the
  top of the plot; end-of-line values could overlap; SVG ids are now stable across runs.

## [0.1.0] — 2026-09-26
First release: four themes, eight chart types, the `Graph` data structure, SVG/PDF/PNG output, and big-data rendering paths.

[Unreleased]: https://github.com/hsilvosa/lineova/compare/v0.2.0...develop
[0.2.0]: https://github.com/hsilvosa/lineova/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/hsilvosa/lineova/releases/tag/v0.1.0
