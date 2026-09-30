# Roadmap

## 0.1
- Four themes: folio, ledger, instrument, fjord
- Charts: line, area, bar, scatter, histogram, heatmap, box, network
- Graph data structure with BFS/DFS, Dijkstra, components, topological sort, MST, communities
- SVG and PDF writers (no dependencies), PNG through optional backends
- Big-data paths: M4 line reduction, density scatter, chunked aggregation, FFT force layout

## 0.2
See CHANGELOG.md.

## 0.3 (this release)
See CHANGELOG.md. Items ticked below shipped in 0.2 or 0.3.

## Chart types
- [x] Pie / donut, with an honest default (above 6 slices the rest fold into "Other" and a bar chart is suggested)
- [x] Violin and ridgeline (density per group)
- [x] Error bars and confidence bands for line and scatter
- [x] Small multiples / facets (`facet="region"`), with shared axes
- [x] Slope chart and dumbbell chart (before/after)
- [x] Waterfall (bridges for finance)
- [x] Treemap (hierarchies, two levels)
- [x] Sunburst, and treemaps of any depth
- [x] Sankey / flow diagrams
- [x] Candlestick / OHLC
- [x] Radar (with a warning in the docs about when not to use it)
- [x] Contour / 2-D density (KDE) from scattered points
- [x] Choropleth and point maps (GeoJSON input), and tile maps
- [x] Gantt / timeline
- [x] Calendar heatmap
- [x] Sparklines and stat tiles for dashboards

## Library features
- [x] Out-of-core input: iterables of chunks (e.g. Parquet row groups) for data larger than RAM
- [x] Interactive HTML output (tooltips, zoom, pan) from the same scene
- [x] Crosshair readout in HTML
- [ ] Date-range brushing and zoom that re-ticks the axes
- [ ] Font embedding in PDF (theme fonts instead of the standard PDF fonts)
- [ ] Native PNG rasteriser so PNG needs no extra install
- [x] Multi-chart layouts: `lv.grid([c1, c2], cols=2)` with aligned axes
- [x] Secondary encodings for accessibility: textures for bars and areas, and an auto-generated data table / alt text
- [x] Theme builder from a brand colour (validated palette generation)
- [x] Dark variants of folio, ledger and fjord (and a light instrument)
- [ ] Animated transitions (SVG/SMIL or GIF) between two charts
- [ ] Barnes–Hut layout and edge bundling for very large networks
- [x] More graph algorithms: betweenness/closeness centrality, PageRank, max flow, A*, strongly connected components
- [x] Graph algorithms at scale: approximate betweenness (sampling) for 100k+ nodes
- [ ] Optional numba acceleration when it is installed
- [x] Hexbin plots
- [x] Box/violin for chunked (out-of-core) data via streaming quantile sketches
- [x] Bar and heatmap aggregation directly from `Chunks`

## Next
- [ ] More tile layouts (European countries, US states) and bundled simplified boundaries
- [ ] Font embedding in PDF, native PNG rasteriser
- [ ] Date-range brushing in HTML
- [ ] A script to rebuild the real-data gallery inputs from the raw IGN/OMIE files
