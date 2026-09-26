# FAQ

**How is lineova different from matplotlib, seaborn or plotly?**
lineova is smaller and more opinionated. Every option has a considered automatic value, output is designed for reading rather than exploring, and big data is handled by default without extra libraries. It doesn't try to cover everything: for 3-D plots, fine low-level control or GUI backends, matplotlib is the better tool.

**Why is PNG an optional extra?**
Turning SVG into pixels well needs a rasteriser. lineova uses `resvg-py` (a small wheel with no system libraries) when installed, otherwise `cairosvg` or `playwright`. SVG, PDF and HTML need nothing extra.

**My fonts look different from the gallery.**
Themes name web fonts (Source Serif 4, IBM Plex Sans, JetBrains Mono, Figtree) with fallbacks. If a font isn't installed, the viewer uses the fallback. Layout leaves room for wider fallback fonts. PDFs use the standard PDF fonts (Times, Helvetica, Courier) until font embedding lands (see the roadmap).

**Can I use it in Jupyter?**
Yes. A chart displays inline as SVG when it's the last expression in a cell.

**How do I put the chart in LaTeX?**
Save as PDF (`chart.save("fig.pdf")`) and `\includegraphics{fig.pdf}`. With `theme="folio"` and `size="column"` or `size="page"`, the figure matches common journal widths.

**Why did my pie chart get an "Other" slice?**
Past six slices, pies become hard to read, so the smallest are grouped and a warning suggests a bar chart. Pass `top=None` to keep every slice.

**Why are some of my series grey?**
More than eight series can't be given distinguishable colours, so the extras are drawn muted as "Other" (with a warning). Use `highlight=` to pick what stands out, or `facet=` to split the chart.

**Does it work with polars / pyarrow?**
Yes. DataFrames and Series from pandas and polars, pyarrow tables and record batches (through `lv.Chunks`), NumPy arrays (including memmaps), lists and dicts are all accepted. None of these libraries are imported unless you pass their objects.

**Is the output deterministic?**
Yes. The same input produces byte-identical SVG, including network layouts (seeded) and element ids (content-hashed).
