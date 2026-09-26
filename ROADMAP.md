# Roadmap

## 0.1 (this release)
- Four themes: folio, ledger, instrument, fjord
- Charts: line, area, bar, scatter, histogram, heatmap, box, network
- Graph data structure with BFS/DFS, Dijkstra, components, topological sort, MST, communities
- SVG and PDF writers (no dependencies), PNG through optional backends
- Big-data paths: M4 line reduction, density scatter, chunked aggregation, FFT force layout

## Next chart types
- [ ] Pie / donut, with an honest default (a bar chart is suggested above 5 slices)
- [ ] Violin and ridgeline (density per group)
- [ ] Error bars and confidence bands for line and scatter
- [ ] Small multiples / facets (`facet="region"`), with shared axes
- [ ] Slope chart and dumbbell chart (before/after)
- [ ] Waterfall (bridges for finance)
- [ ] Treemap and sunburst (hierarchies)
- [ ] Sankey / flow diagrams (reusing the layered network layout)
- [ ] Candlestick / OHLC
- [ ] Radar (with a warning in the docs about when not to use it)
- [ ] Contour / 2-D density (KDE) from scattered points
- [ ] Choropleth and point maps (GeoJSON input)
- [ ] Gantt / timeline
- [ ] Calendar heatmap
- [ ] Sparklines and stat tiles for dashboards

## Library features
- [ ] Out-of-core input: iterables of chunks (e.g. Parquet row groups) for data larger than RAM
- [ ] Interactive HTML output (zoom, pan, crosshair, tooltips) from the same scene
- [ ] Font embedding in PDF (theme fonts instead of the standard PDF fonts)
- [ ] Native PNG rasteriser so PNG needs no extra install
- [ ] Multi-chart layouts: `lv.grid([c1, c2], cols=2)` with aligned axes
- [ ] Secondary encodings for accessibility: textures for bars and areas, and an auto-generated data table / alt text
- [ ] Theme builder from a brand colour (validated palette generation)
- [ ] Dark variants of folio, ledger and fjord
- [ ] Animated transitions (SVG/SMIL or GIF) between two charts
- [ ] Barnes–Hut layout and edge bundling for very large networks
- [ ] More graph algorithms: betweenness/closeness centrality, max flow, A*, strongly connected components
- [ ] Optional numba acceleration when it is installed
