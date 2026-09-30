"""Gallery built from two real, public datasets.

1. **IGN earthquake catalogue** (Instituto Geográfico Nacional, Spain): about 207,000
   events from 1373 to 2026 around Iberia and the Canary Islands.
   https://doi.org/10.7419/162.03.2022
2. **OMIE day-ahead electricity market** (Operador del Mercado Ibérico de Energía):
   hourly (quarter-hourly from October 2025) marginal prices 2023–2026, and every
   bid of 2024's bidding curves for 182 days (about 17 million bids).
   Public market data. Attribution to OMIE is required.

The data isn't included in the repository. To rebuild the images, put these files in
one folder and pass it as the first argument (or set ``LINEOVA_DATA``):

    ign_earthquakes.csv   event_id;date;time;lat;lon;depth_km;intensity;magnitude;mag_type;location
    omie_prices.csv       date,period,price_es,price_pt
    curves_*.npz          arrays: day, hour, side (1 = sell), status (1 = matched), energy, price

    python examples/real_data.py path/to/data
"""

from __future__ import annotations

import glob
import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

import lineova as lv

DATA = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LINEOVA_DATA", "data"))
OUT = Path(__file__).resolve().parent.parent / "docs" / "gallery" / "real"
OUT.mkdir(parents=True, exist_ok=True)
IGN = "IGN, Catálogo de terremotos (doi:10.7419/162.03.2022)"
OMIE = "OMIE, Mercado diario"
W = {"width": 760, "height": 440}
timings: list[tuple[str, float, int]] = []


def save(chart, name: str, rows: int) -> None:
    t0 = time.perf_counter()
    chart.save(OUT / f"{name}.svg")
    timings.append((name, time.perf_counter() - t0, rows))


# ---------------------------------------------------------------- earthquakes
eq = pd.read_csv(DATA / "ign_earthquakes.csv", sep=";")
eq["t"] = pd.to_datetime(eq["date"] + " " + eq["time"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
eq = eq.dropna(subset=["t"])
n_eq = len(eq)


def region(lat, lon):
    r = np.full(len(lat), "Iberian interior", dtype=object)
    r[lat > 42.0] = "Pyrenees"
    r[(lat < 37.6) & (lon < -6.3)] = "Gulf of Cádiz"
    r[(lat < 37.3) & (lon >= -6.3) & (lon < 0)] = "Betics & Alborán"
    r[(lat < 35.9) & (lon > -6)] = "North Africa"
    r[lat < 30.0] = "Canary Islands"
    return r


eq["region"] = region(eq["lat"].to_numpy(), eq["lon"].to_numpy())

# 1. Where: every event on a lon/lat plane (drawn as a density image automatically)
save(lv.scatter(eq, x="lon", y="lat", color=None, theme="instrument",
                title="Seismicity around Iberia", subtitle=f"{n_eq:,} events, 1373–2026",
                x_label="Longitude", y_label="Latitude", source=IGN, width=760, height=560),
     "eq_map", n_eq)

# 2. How big: magnitude distribution on a log axis (Gutenberg–Richter law)
mag = eq["magnitude"].dropna()
save(lv.histogram(mag[mag > 0], bins=np.arange(-0.05, 8.8, 0.1), y_scale="log", theme="folio", number=1,
                  title="Earthquakes by magnitude",
                  caption="The count falls roughly tenfold per unit of magnitude (Gutenberg–Richter). "
                          "Log scale.", x_label="Magnitude", source=IGN, **W),
     "eq_magnitudes", len(mag))

# 3. When: events per year since 1900, the network gets denser
yearly = eq[eq["t"].dt.year >= 1900].groupby(eq["t"].dt.year).size()
save(lv.line(x=pd.to_datetime(yearly.index.astype(str)), y=yearly.to_numpy(), label="events per year",
             theme="ledger", title="Recorded earthquakes per year",
             subtitle="Growth reflects more seismometers, not more earthquakes", x_label=None, source=IGN, **W)
     .band(x=("2021-01-01", "2022-12-31"), label="La Palma"),
     "eq_per_year", int(yearly.sum()))

# 4. Depth by region: ridgeline of the full distributions
shallow = eq[(eq["depth_km"] > 0) & (eq["depth_km"] <= 60)]
save(lv.ridgeline(shallow, x="region", y="depth_km", theme="fjord", title="How deep are they?",
                  subtitle="Hypocentre depth, km (0–60)", source=IGN, **W),
     "eq_depth_regions", len(shallow))

# 5. La Palma 2021: the eruption's swarm, daily counts and depth over time
lp = eq[eq["lat"].between(28.4, 28.8) & eq["lon"].between(-18.1, -17.7) &
        eq["t"].between("2021-09-01", "2022-01-15")]
daily = lp.groupby(lp["t"].dt.floor("D")).size()
save(lv.grid([
    lv.area(x=daily.index, y=daily.to_numpy(), label="events", title="Earthquakes per day", x_label=None),
    lv.scatter(lp, x="t", y="depth_km", color=None, title="Depth of each event (km)", y_reverse=True,
               x_label=None, y_label=None),
], cols=1, title="La Palma eruption, autumn 2021",
    subtitle=f"{len(lp):,} events under Cumbre Vieja; the eruption ran 19 Sep – 13 Dec", theme="ledger",
    width=760), "eq_la_palma", len(lp))

# 6. The ten largest instrumental events since 1950
big = eq[eq["t"].dt.year >= 1950].nlargest(10, "magnitude")
labels = {f"{r.location.title()} ({r.t.year})": r.magnitude for r in big.itertuples()}
save(lv.bar(labels, theme="ledger", title="Largest earthquakes since 1950", subtitle="Magnitude",
            format="{:.1f}", source=IGN, width=760), "eq_largest", 10)

# 7. A year of activity, day by day
y24 = eq[eq["t"].dt.year == 2025]
save(lv.calendar(y24["t"], theme="ledger", title="Earthquakes per day, 2025", label="events",
                 source=IGN, width=860), "eq_calendar", len(y24))

# 8. Share by region
save(lv.treemap(eq.groupby("region").size().to_dict(), theme="fjord", title="Where the catalogue's events are",
                subtitle="Events by region, 1373–2026", source=IGN, **W), "eq_regions", n_eq)

# 9. Headline numbers
recent = eq[eq["t"].dt.year.isin([2024, 2025])]
by_year = recent.groupby(recent["t"].dt.year).size()
monthly = eq[eq["t"] >= "2023-01-01"].groupby(eq["t"].dt.to_period("M")).size().to_numpy()
save(lv.grid([
    lv.stat(n_eq, label="Events in the catalogue"),
    lv.stat(int(by_year.get(2025, 0)), label="Events in 2025", previous=int(by_year.get(2024, 0)), good=None,
            spark=monthly),
    lv.stat(f"{eq['magnitude'].max():.1f}", label="Largest magnitude", note="1761, SW of Cabo San Vicente"),
], cols=3, theme="ledger", title="IGN earthquake catalogue"), "eq_stats", n_eq)

# ---------------------------------------------------------------- electricity prices
pr = pd.read_csv(DATA / "omie_prices.csv", parse_dates=["date"])
quarter = pr.groupby("date")["period"].transform("max") > 25          # 15-minute products from Oct 2025
pr["hour"] = np.where(quarter, (pr["period"] - 1) // 4 + 1, pr["period"]).clip(1, 24)
n_pr = len(pr)
day = pr.groupby("date")["price_es"].agg(["mean", "min", "max", "first", "last"])

# 10. Daily mean price with the daily min–max range
save(lv.line(x=day.index, y=day["mean"].to_numpy(), band=(day["min"].to_numpy(), day["max"].to_numpy()),
             label="Spain", theme="ledger", title="Spanish day-ahead electricity price", x_label=None,
             subtitle="Daily mean and daily range, €/MWh", source=OMIE, **W)
     .hline(0, "0 €/MWh"), "power_daily", n_pr)

# 11. Price by hour and month: the solar "duck"
hm = pr.assign(month=pr["date"].dt.strftime("%Y-%m")).pivot_table(index="month", columns="hour",
                                                                    values="price_es", aggfunc="mean")
save(lv.heatmap(hm, theme="fjord", title="When is power cheap?", subtitle="Mean price by hour of day, €/MWh",
                label="€/MWh", annotate=False, source=OMIE, width=860, height=760), "power_heatmap", n_pr)

# 12. The duck deepens: mean price by hour, 2023 vs 2025
by_h = pr[pr["date"].dt.year.isin([2023, 2025])].pivot_table(index="hour", columns=pr["date"].dt.year,
                                                             values="price_es", aggfunc="mean")
save(lv.dumbbell({f"{h:02d}:00": (by_h.loc[h, 2023], by_h.loc[h, 2025]) for h in by_h.index},
                 labels=("2023", "2025"), sort=False, theme="instrument", title="Mean price by hour",
                 subtitle="€/MWh, 2023 vs 2025", source=OMIE, width=760, height=720), "power_by_hour", n_pr)

# 13. Daily candles for 2025 (open = first hour, close = last hour)
d25 = day[day.index.year == 2025].rename(columns={"first": "open", "last": "close", "max": "high", "min": "low"})
save(lv.candlestick(d25, theme="instrument", title="Daily price candles, 2025", subtitle="€/MWh",
                    source=OMIE, **W), "power_candles", len(d25))

# 14. Distribution per weekday
pr["weekday"] = pd.Categorical(pr["date"].dt.day_name().str[:3],
                               ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], ordered=True)
save(lv.violin(pr, x="weekday", y="price_es", theme="fjord", title="Weekends are cheaper",
               subtitle="Hourly price distribution, 2023–2026", x_label=None, y_label="€/MWh",
               source=OMIE, **W), "power_weekday", n_pr)

# 15. Days at zero or below: calendar of daily mean price, 2024
save(lv.calendar(day[day.index.year == 2024].reset_index(), x="date", y="mean", agg="mean", theme="ledger",
                 title="Daily mean price, 2024", label="€/MWh", source=OMIE, width=860), "power_calendar", 366 * 24)

# 16b. magnitude against depth: 200k events as hexagons (log colour scale)
known = eq.dropna(subset=["magnitude", "depth_km"])
save(lv.hexbin(known, x="magnitude", y="depth_km", theme="ledger", gridsize=36, y_range=(0, 60),
               title="Most earthquakes are small and shallow", subtitle="Magnitude against depth (km), top 60 km",
               source=IGN, **W), "eq_hexbin", len(known))

# 16c. events per province as a tile map (the catalogue tags each event with a province code)
code = eq["location"].astype(str).str.extract(r"\.(\w+)\s*$")[0]
islands = {"IHI": "TF", "ILP": "TF", "IGM": "TF", "IGC": "GC", "IFV": "GC", "ILZ": "GC",
           "IMA": "PM", "IME": "PM", "IBZ": "PM", "IB": "PM", "MENORCA": "PM"}
per_prov = code.replace(islands).value_counts()
with warnings.catch_warnings():
    warnings.simplefilter("ignore")          # codes outside Spain (FRA, POR, ...) are left out on purpose
    save(lv.tilemap(per_prov, layout="es-provinces", theme="ledger", label="events",
                    title="Recorded earthquakes by province", subtitle="Each province is one tile; El Hierro and "
                    "La Palma (S. C. de Tenerife) dominate", source=IGN, width=640), "eq_tilemap", int(per_prov.sum()))

# 16d. the larger events on a map: size = magnitude, colour = depth
big = eq[eq["magnitude"] >= 4].dropna(subset=["depth_km"])
save(lv.map(big, lon="lon", lat="lat", size="magnitude", color="depth_km", theme="fjord", label="depth (km)",
            title="Earthquakes of magnitude 4 or more", subtitle=f"{len(big):,} events, 1373–2026",
            source=IGN, width=760, height=560), "eq_map_m4", len(big))

# ---------------------------------------------------------------- 17 million bids (streamed)
files = sorted(glob.glob(str(DATA / "curves_*.npz")))
if files:
    def price_chunks():
        for f in files:
            with np.load(f) as z:
                yield z["price"].astype(np.float64)

    n_bids = sum(np.load(f)["price"].shape[0] for f in files)
    # 16. every bid price, streamed file by file (never all in memory)
    save(lv.histogram(lv.Chunks(price_chunks), bins=np.arange(-100, 401, 5), theme="folio", number=2,
                      title="Bid prices in the Iberian day-ahead market, 2024",
                      caption=f"All {n_bids:,} buy and sell bids on 182 days, €/MWh, read in chunks.",
                      x_label="€/MWh", source=OMIE, **W), "bids_histogram", n_bids)

    # 16e. sell offers by month and hour: a streamed group-by over all files
    months = np.array(["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])

    def offer_chunks():
        for f in files:
            with np.load(f) as z:
                ok = (z["side"] == 1) & (z["price"] > -100) & (z["price"] < 500)
                yield {"month": months[(z["day"][ok] // 100) % 100], "hour": z["hour"][ok].astype(np.int64),
                       "price": z["price"][ok].astype(np.float64)}

    n_offers = sum(len(c["price"]) for c in offer_chunks())
    save(lv.heatmap(lv.Chunks(offer_chunks), x="hour", y="month", value="price", theme="ledger", format="{:.0f}",
                    title="Sell offers are cheapest around midday", label="mean offer, €/MWh",
                    subtitle=f"Mean price of {n_offers:,} sell offers by month and hour, Jan–Jun 2024 · streamed",
                    source=OMIE, width=860, height=380), "bids_offer_heatmap", n_offers)

    # 17. supply and demand curves for one hour
    with np.load(files[0]) as z:
        first_day = int(z["day"][0])
        sel = (z["day"] == first_day) & (z["hour"] == 20)
        side, e, p = z["side"][sel], z["energy"][sel].astype(float), z["price"][sel].astype(float)
    sell_order, buy_order = np.argsort(p[side == 1]), np.argsort(-p[side == 0])
    sup_q = np.cumsum(e[side == 1][sell_order]) / 1000
    sup_p = p[side == 1][sell_order]
    dem_q = np.cumsum(e[side == 0][buy_order]) / 1000
    dem_p = p[side == 0][buy_order]
    save(lv.Chart(theme="ledger", title="Supply meets demand", subtitle="1 Jan 2024, 19:00–20:00",
                  source=OMIE, **W)
         .line({"Supply (sell bids)": (sup_q, np.clip(sup_p, -100, 400)),
                "Demand (buy bids)": (dem_q, np.clip(dem_p, -100, 400))}, curve="linear", values=False)
         .x_axis(label="Cumulative GWh").y_axis(label="€/MWh (shown between −100 and 400)"),
         "bids_curves", int(sel.sum()))

print(f"{'chart':<20}{'rows':>14}{'seconds':>10}")
for name, dt, rows in timings:
    print(f"{name:<20}{rows:>14,}{dt:>10.2f}")
