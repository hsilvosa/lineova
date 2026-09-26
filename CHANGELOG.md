# Changelog

## 0.2.0 — 2026-09-26
- New charts: pie/donut, violin, ridgeline, dumbbell, slope, waterfall, candlestick/OHLC, treemap, sankey, radar,
  2-D density with contours, timeline/Gantt, calendar heatmap, sparkline, stat tile.
- Confidence bands on lines (`band=`), error bars on scatter (`error=`, `x_error=`) and bars (`error="std" | "sem" | "ci"`).
- Small multiples (`facet="column"`) and `lv.grid([...])` layouts with shared axes, colours and legend.
- Interactive HTML export (`.save("chart.html")`): tooltips, zoom, pan.
- Out-of-core input with `lv.Chunks(...)` for line, scatter and histogram.
- Graph: PageRank, betweenness, closeness, strongly connected components, max flow, A*; `node_size="pagerank"`.
- Fixed: Folio figure captions ran into the "Figure N." label with some fonts; value labels could be clipped at the
  top of the plot; end-of-line values could overlap; SVG ids are now stable across runs.

## 0.1.0 — 2026-09-26
First release: four themes, eight chart types, the `Graph` data structure, SVG/PDF/PNG output, and big-data rendering paths.
