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

Reproduce with:

```bash
python benchmarks/bench.py          # up to 10 M
python benchmarks/bench.py --big    # adds 100 M (needs ~8 GB RAM)
```

## Tips

- Pass sorted x to `line` (unsorted x is sorted once, O(n log n)).
- For inputs that don't fit in memory, use `np.memmap` or `lv.Chunks`.
- `render="vector"` forces individual marks on big scatter plots, which gives large files.
- Most of the time for text-heavy inputs (millions of category labels) is spent grouping them; pass categorical/integer codes when you can.
