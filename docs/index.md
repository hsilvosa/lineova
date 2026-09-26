# lineova

**Clean, fast charts from Python, with good defaults and one dependency.**

![Seismicity around Iberia](gallery/real/eq_map.svg)

```python
import lineova as lv
lv.line(df, x="date", y="price", color="market").save("prices.svg")
```

lineova turns data into publication-quality charts with one call, and lets you adjust any detail when you need to. It has 23 chart types, four house styles, vector and raster output, and handles anything from ten rows to a hundred million.

<div class="grid cards" markdown>

- **[Installation](installation.md)**: pip, optional extras, development setup
- **[Quick start](quickstart.md)**: your first charts in five minutes
- **[User guide](guide.md)**: every chart type and option
- **[Use cases](use-cases.md)**: papers, dashboards, monitoring, public reports, big data
- **[Gallery](gallery.md)**: charts made from real data, with code
- **[API reference](api.md)**: functions, classes and signatures

</div>

## Principles

1. **Good by default.** Every decision (size, ticks, colours, legend placement, drawing method) has an automatic choice that works, so a chart needs no tuning.
2. **Override anything, one option at a time.** Options default to `"auto"`, so you set only what you care about.
3. **Cost follows pixels, not rows.** Large inputs are reduced to what the image can show, in a way that doesn't change the picture.
4. **Honest charts.** Zero-based bars, colour-blind-checked palettes, no dual axes, and no more pie slices than can be read.
5. **Small footprint.** Only NumPy is required. Everything else is optional.
