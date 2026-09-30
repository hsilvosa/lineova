# Gallery

## Real data

Made from two public datasets with [`examples/real_data.py`](https://github.com/hsilvosa/lineova/blob/main/examples/real_data.py). The data is not in the repository: the script's docstring explains the expected files.

- **IGN earthquake catalogue**: 207,221 events around Iberia and the Canary Islands, 1373–2026. Instituto Geográfico Nacional, [doi:10.7419/162.03.2022](https://doi.org/10.7419/162.03.2022).
- **OMIE Iberian day-ahead market**: 54,983 hourly and quarter-hourly prices (2023–2026) and 17,093,765 individual bids (182 days of 2024). Source: OMIE. Attribution is required.

### Earthquakes

![Seismicity map](gallery/real/eq_map.svg)
*207,221 epicentres drawn as a density image: `lv.scatter(eq, x="lon", y="lat", theme="instrument")`.*

![Magnitudes](gallery/real/eq_magnitudes.svg)
*Histogram on a log axis, `folio` style with a numbered caption: `lv.histogram(mag, y_scale="log", number=1, …)`.*

![Per year](gallery/real/eq_per_year.svg)
*`lv.line(...)` with a shaded period: `.band(x=("2021-01-01", "2022-12-31"), label="La Palma")`.*

![La Palma](gallery/real/eq_la_palma.svg)
*`lv.grid([lv.area(...), lv.scatter(..., y_reverse=True)], cols=1)`: the 2021 eruption swarm.*

![Depth](gallery/real/eq_depth_regions.svg)
*`lv.ridgeline(df, x="region", y="depth_km", theme="fjord")`*

![Hexbin](gallery/real/eq_hexbin.svg)
*200,848 events with a known depth, binned into hexagons: `lv.hexbin(eq, x="magnitude", y="depth_km", y_range=(0, 60))`.*

![Tile map](gallery/real/eq_tilemap.svg)
*Events per province, one equal tile each: `lv.tilemap(counts, layout="es-provinces")`. The colour scale switches to log for skewed counts.*

![Map M4+](gallery/real/eq_map_m4.svg)
*`lv.map(big, lon="lon", lat="lat", size="magnitude", color="depth_km")`: 4,001 events of magnitude 4 or more.*

![Largest](gallery/real/eq_largest.svg)
![Calendar](gallery/real/eq_calendar.svg)
![Regions](gallery/real/eq_regions.svg)
![Stats](gallery/real/eq_stats.svg)

### Electricity market

![Daily price](gallery/real/power_daily.svg)
*Daily mean with the daily min–max as a band: `lv.line(x=..., y=mean, band=(low, high))`.*

![Heatmap](gallery/real/power_heatmap.svg)
*Mean price by month (rows) and hour (columns). Solar pushes midday prices to zero in spring.*

![By hour](gallery/real/power_by_hour.svg)
*`lv.dumbbell({hour: (price_2023, price_2025)}, labels=("2023", "2025"))`*

![Candles](gallery/real/power_candles.svg)
![Weekday](gallery/real/power_weekday.svg)
![Calendar](gallery/real/power_calendar.svg)

![Bids](gallery/real/bids_histogram.svg)
*17 million bids streamed from six files with `lv.Chunks`, in 0.3 s.*

![Offers](gallery/real/bids_offer_heatmap.svg)
*12 million sell offers aggregated by month and hour in one streamed pass: `lv.heatmap(lv.Chunks(files), x="hour", y="month", value="price")`.*

![Curves](gallery/real/bids_curves.svg)
*Supply and demand for one hour, from the raw bids.*

## Chart types

Synthetic examples of every chart type, made by [`examples/gallery.py`](https://github.com/hsilvosa/lineova/blob/main/examples/gallery.py).

| | |
|---|---|
| ![](gallery/donut.svg) | ![](gallery/violin.svg) |
| ![](gallery/ridgeline.svg) | ![](gallery/slope.svg) |
| ![](gallery/dumbbell.svg) | ![](gallery/waterfall.svg) |
| ![](gallery/candlestick.svg) | ![](gallery/treemap.svg) |
| ![](gallery/sankey.svg) | ![](gallery/radar.svg) |
| ![](gallery/density.svg) | ![](gallery/timeline.svg) |
| ![](gallery/band.svg) | ![](gallery/errorbars.svg) |
| ![](gallery/area.svg) | ![](gallery/histogram.svg) |
| ![](gallery/heatmap.svg) | ![](gallery/box.svg) |
| ![](gallery/facets.svg) | ![](gallery/stats.svg) |
| ![](gallery/big-scatter.svg) | ![](gallery/calendar.svg) |
| ![](gallery/hexbin.svg) | ![](gallery/sunburst.svg) |
| ![](gallery/treemap-deep.svg) | ![](gallery/tilemap.svg) |
| ![](gallery/textures.svg) | ![](gallery/brand-theme.svg) |

## The four styles on the same data

| | Folio | Ledger | Instrument | Fjord |
|---|---|---|---|---|
| Line | ![](gallery/folio-line.svg) | ![](gallery/ledger-line.svg) | ![](gallery/instrument-line.svg) | ![](gallery/fjord-line.svg) |
| Bar | ![](gallery/folio-bar.svg) | ![](gallery/ledger-bar.svg) | ![](gallery/instrument-bar.svg) | ![](gallery/fjord-bar.svg) |
| Scatter | ![](gallery/folio-scatter.svg) | ![](gallery/ledger-scatter.svg) | ![](gallery/instrument-scatter.svg) | ![](gallery/fjord-scatter.svg) |
| Network | ![](gallery/folio-network.svg) | ![](gallery/ledger-network.svg) | ![](gallery/instrument-network.svg) | ![](gallery/fjord-network.svg) |

## Dark variants

| Ledger dark | Fjord dark | Folio dark |
|---|---|---|
| ![](gallery/ledger-dark-line.svg) | ![](gallery/fjord-dark-line.svg) | ![](gallery/folio-dark-line.svg) |
