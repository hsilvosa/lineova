# Performance

lineova aims to keep the cost of a chart tied to the size of the picture, not the size of the data.

## How

| Technique | Used by | Effect |
|---|---|---|
| **M4 reduction**: per pixel column, keep the first, last, min and max point | `line`, `area`, `sparkline` | ≤ 4 points per pixel column; the drawn line is identical |
| **Density rendering**: count points per pixel, shade by histogram equalisation | `scatter` above 50k points, huge networks | Output size independent of point count; structure visible at every density |
| **Chunked passes**: data processed in 4-million-row blocks | binning, histograms, fits, KDE | Memory stays bounded |
| **Binned KDE**: fine histogram then a Gaussian convolution | `violin`, `ridgeline`, `density` | O(n) instead of O(n × grid) |
| **Bucketing**: consecutive rows merged into longer periods | `candlestick` | About one candle per 4 px |
| **Block reduction**: average blocks of cells | `heatmap` larger than the plot | Draws as one image |
| **FFT repulsion**: particle-mesh force layout | `network` above 1,500 nodes | O(n + grid) per step instead of O(n²) |
| **Streaming**: `lv.Chunks(source)` | `line`, `scatter`, `histogram`, `hexbin`, `bar`, `heatmap`, `box`, `violin` | Data larger than memory |
| **Streaming group-by**: count/sum/sum of squares/min/max per group, merged chunk by chunk | `bar`, `heatmap` from `Chunks` | Exact means, totals and error bars; memory per group |
| **Quantile sketch**: per-group 4,096-bin histogram → quantile-preserving sample | `box`, `violin` from `Chunks` | Percentiles exact to 1/4,096 of the range |
| **Dense hex binning**: nearest of two offset lattices, `bincount` into a grid | `hexbin` | One linear pass, no sort |
| **Shared point budget**: the density threshold counts the points of the whole chart, not of each panel | `facet=` and `lv.grid` of scatter plots | 12 panels of 200,000 points: 0.3 MB of SVG instead of 8.3 MB |
| **Sampled betweenness** (Brandes & Pich) | `Graph.betweenness(k=)`, network sizing above 2,000 nodes | ~10× faster at 3,000 nodes, rank correlation > 0.98 |

## Measurements

Full pipeline (data → finished SVG) on a 2-core cloud VM:

| Input | Time | SVG size |
|---|---|---|
| Line, 10 million points | 0.15 s | 70 KB |
| Line, 100 million points | 1.5 s | 70 KB |
| Scatter (density), 10 million points | 0.34 s | 320 KB |
| Scatter (density), 100 million points | 1.9 s | 630 KB |
| Histogram, 100 million values | 1.3 s | 20 KB |
| Heatmap, 4,000 × 4,000 | 0.44 s | 390 KB |
| Violin, 10 million values in 5 groups | 1.9 s | 40 KB |
| 2-D density + contours, 10 million points | 0.5 s | 30 KB |
| Candlestick, 1 million rows | 0.03 s | 30 KB |
| Line from `lv.Chunks`, 20 million rows | 1.1 s | 70 KB |
| Histogram of 17 million real market bids from 6 files | 0.3 s | 25 KB |
| Network, 40,000 nodes / 200,000 edges | 3 s | 670 KB |
| Hexbin, 10 million points | 1.0 s | 140 KB |
| Bar (mean per category) from `lv.Chunks`, 10 million rows | 0.8 s | 11 KB |
| Box plots from `lv.Chunks`, 10 million rows in 50 groups | 1.4 s | 330 KB |
| Point map (density), 10 million points | 1.2 s | 0.9 MB |
| Heatmap of 12 million real market offers from 6 files (streamed group-by) | 2.3 s | 40 KB |
| 12 facets of 200,000 scatter points each | 0.7 s | 0.3 MB |

Reproduce with:

```bash
python benchmarks/bench.py          # up to 10 M
python benchmarks/bench.py --big    # adds 100 M (needs ~8 GB RAM)
```

## Version 0.4.0

Profiling for 0.4.0 showed that layout and rendering were already fast, so it kept the algorithms and fixed the one real problem: facets. A float32 FFT in the network layout gave only about 17% and was not adopted. Timings of 0.3.0 and 0.4.0 are the same within noise (10 million line points: 0.31 s best of five on both).

Two new outputs have their own costs:

- The built-in PNG renderer takes about 0.2 to 0.3 s for a 640 x 400 chart. It is slower than resvg but needs no install.
- A GIF animation renders every frame as a PNG, so the time is about the number of frames times the PNG time. The default is 24 frames per step.

`benchmarks/baseline.json` holds the 0.3.0 timings. Compare a new run with `python benchmarks/bench.py --compare benchmarks/baseline.json`.

## Tips

- Pass sorted x to `line` (unsorted x is sorted once, O(n log n)).
- For inputs that don't fit in memory, use `np.memmap` or `lv.Chunks`.
- `render="vector"` forces individual marks on big scatter plots, which gives large files.
- Most of the time for text-heavy inputs (millions of category labels) is spent grouping them; pass categorical/integer codes when you can.
