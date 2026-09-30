"""Build the gallery images used in the README (docs/gallery/*.svg).

    python examples/gallery.py
"""
from pathlib import Path

import numpy as np

import lineova as lv

OUT = Path(__file__).resolve().parent.parent / "docs" / "gallery"
OUT.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(7)

months = np.arange("2025-01", "2026-01", dtype="datetime64[M]")
output = {
    "Solar": [42, 55, 78, 96, 118, 131, 138, 127, 99, 72, 48, 38],
    "Wind": [112, 104, 98, 86, 74, 66, 62, 68, 80, 96, 108, 118],
    "Hydro": [70, 74, 88, 95, 92, 84, 72, 64, 60, 64, 70, 72],
}
sites = {"Alta Ridge": 41.2, "Brennmoor": 37.8, "Cala Serena": 34.5, "Dunhollow": 31.0,
         "Eskvale": 28.6, "Ferrow Point": 24.9, "Gallan Flats": 21.3}
irr = 160 + rng.random(48) * 780
temp = 8 + (irr - 160) / 780 * 22 + rng.normal(0, 3, 48)
out = 12 + 0.082 * irr - (temp - 18) * 0.35 + rng.normal(0, 5.5, 48)
grid = lv.Graph.from_edges([
    ("A", "B", 4), ("A", "C", 3), ("B", "D", 5), ("C", "D", 2), ("B", "E", 6), ("D", "E", 4), ("D", "G", 3),
    ("C", "F", 6), ("F", "G", 4), ("E", "H", 5), ("G", "H", 3), ("G", "I", 5), ("F", "I", 7), ("E", "G", 2),
])

for theme in lv.themes.names():
    if theme not in ("folio", "ledger", "instrument", "fjord"):
        continue
    common = {"theme": theme, "width": 640, "height": 400}
    lv.line(output, x=months, title="Energy output by source", subtitle="Monthly, GWh", y_label="GWh",
            number=1, **common).save(OUT / f"{theme}-line.svg")
    lv.bar(sites, title="Capacity factor by site", highlight="Cala Serena", format="{:.1f}%",
           reference="mean", number=2, **common).save(OUT / f"{theme}-bar.svg")
    lv.scatter(x=irr, y=out, size=temp, fit=True, title="Output vs irradiance", x_label="Irradiance (W/m²)",
               y_label="Output (kW)", number=3, **common).save(OUT / f"{theme}-scatter.svg")
    lv.network(grid, path=("A", "I"), title="Cheapest route A → I", number=4, **common).save(OUT / f"{theme}-network.svg")

# the four new chart types
lv.area(output, x=months, title="Stacked output", subtitle="GWh", theme="fjord", width=640, height=400) \
    .save(OUT / "area.svg")
lv.histogram({"Control": rng.normal(50, 10, 4000), "Treatment": rng.normal(56, 12, 4000)},
             title="Reaction time", subtitle="ms, two groups", theme="ledger", width=640, height=400) \
    .save(OUT / "histogram.svg")
corr = np.corrcoef(rng.normal(size=(8, 60)) + rng.normal(size=60) * 0.8)
labels = ["Temp", "Sun", "Wind", "Rain", "Load", "Price", "Demand", "Output"]
lv.heatmap(corr, x=labels, y=labels, title="Correlation matrix", theme="folio", number=5,
           width=560, height=480).save(OUT / "heatmap.svg")
lv.box({s: rng.normal(v, 5, 300) for s, v in sites.items()}, title="Daily capacity factor", subtitle="%",
       theme="instrument", width=640, height=400).save(OUT / "box.svg")

# big data
n = 2_000_000
cls = rng.integers(0, 3, n)
x = rng.standard_normal(n) + cls * 1.6
y = rng.standard_normal(n) * 0.8 + np.sin(cls * 2.0)
lv.scatter(x=x, y=y, color=np.array(["North", "Central", "South"])[cls], title="Two million points",
           subtitle="Rendered as a density image automatically", theme="ledger", width=640, height=400) \
    .save(OUT / "big-scatter.svg")
# 0.2 chart types
import pandas as pd  # noqa: E402  (only the gallery needs pandas)

groups = pd.DataFrame({"group": np.repeat(["Alpha", "Beta", "Gamma", "Delta"], 300),
                       "value": np.concatenate([rng.normal(10, 2, 300), rng.gamma(4, 2, 300), rng.normal(14, 4, 300),
                                                np.r_[rng.normal(7, 1, 150), rng.normal(13, 1.5, 150)]])})
mix = {"Solar": 31, "Wind": 27, "Hydro": 18, "Gas": 14, "Coal": 6, "Nuclear": 4}
share = {"Spain": (37, 57), "France": (19, 28), "Italy": (33, 41), "Germany": (31, 52), "Portugal": (52, 64)}
days = pd.date_range("2025-01-01", periods=120)
close = 100 + np.cumsum(rng.normal(0, 1.4, 120))
opn = np.r_[100, close[:-1]] + rng.normal(0, 0.4, 120)
ohlc = pd.DataFrame({"date": days, "open": opn, "close": close,
                     "high": np.maximum(opn, close) + rng.random(120) * 2,
                     "low": np.minimum(opn, close) - rng.random(120) * 2})
flows = [("Solar", "Grid", 120), ("Wind", "Grid", 160), ("Hydro", "Grid", 90), ("Gas", "Grid", 140),
         ("Grid", "Homes", 210), ("Grid", "Industry", 200), ("Grid", "Transport", 60), ("Grid", "Losses", 40),
         ("Gas", "Industry", 50)]
plan = pd.DataFrame({
    "task": ["Research", "Design", "Prototype", "Review", "Build", "Test", "Launch"],
    "start": pd.to_datetime(["2026-07-01", "2026-07-20", "2026-08-10", "2026-09-01", "2026-09-05", "2026-10-10",
                             "2026-11-02"]),
    "end": pd.to_datetime(["2026-07-25", "2026-08-15", "2026-09-05", "2026-09-01", "2026-10-20", "2026-11-01",
                           "2026-11-02"]),
    "team": ["Research", "Design", "Engineering", "Research", "Engineering", "Engineering", "Design"],
    "done": [1, 1, 1, np.nan, .6, .1, 0]})
year = pd.date_range("2025-01-01", "2025-12-31")
commits = pd.DataFrame({"day": year, "commits": rng.poisson(np.where(year.dayofweek < 5, 4, 0.7))})
x24 = np.arange(24.0)
fc = 20 + 5 * np.sin(x24 / 4) + rng.normal(0, 0.8, 24)
size = {"width": 640, "height": 400}

lv.donut(mix, title="Electricity mix", subtitle="Share of generation, %", theme="ledger", **size).save(OUT / "donut.svg")
lv.violin(groups, x="group", y="value", title="Response by group", theme="fjord", **size).save(OUT / "violin.svg")
lv.ridgeline(groups, x="group", y="value", title="Distributions", theme="folio", number=6, **size) \
    .save(OUT / "ridgeline.svg")
lv.slope(share, labels=("2015", "2024"), title="Renewables share of electricity", subtitle="%", theme="ledger",
         width=640, height=400).save(OUT / "slope.svg")
lv.dumbbell(share, labels=("2015", "2024"), title="Renewables share of electricity", subtitle="%",
            theme="instrument", **size).save(OUT / "dumbbell.svg")
lv.waterfall({"Sales": 420, "Services": 130, "Costs": -310, "Tax": -60, "Other": 25}, start=("2024", 900),
             title="Profit bridge", subtitle="k€", theme="ledger", **size).save(OUT / "waterfall.svg")
lv.candlestick(ohlc, title="Share price", theme="instrument", **size).save(OUT / "candlestick.svg")
lv.treemap({"Europe": {"Spain": 48, "France": 68, "Italy": 59}, "Asia": {"Japan": 125, "Korea": 52},
            "America": {"USA": 335, "Mexico": 128, "Brazil": 216}}, title="Population", subtitle="millions",
           theme="fjord", **size).save(OUT / "treemap.svg")
lv.sankey(flows, title="Energy flows", subtitle="TWh", theme="ledger", width=720, height=400).save(OUT / "sankey.svg")
lv.radar({"Model A": {"Speed": 8, "Accuracy": 6, "Cost": 4, "Memory": 7, "Ease": 9},
          "Model B": {"Speed": 5, "Accuracy": 9, "Cost": 7, "Memory": 5, "Ease": 6}}, title="Model comparison",
         theme="fjord", **size).save(OUT / "radar.svg")
dens = pd.DataFrame({"x": np.r_[rng.normal(0, 1, 20000), rng.normal(2.5, 1.2, 20000)],
                     "y": np.r_[rng.normal(0, 0.8, 20000), rng.normal(1.5, 1, 20000)]})
lv.density(dens, x="x", y="y", title="Where the points are", theme="ledger", **size).save(OUT / "density.svg")
lv.timeline(plan, color="team", progress="done", today=False, title="Project plan", theme="ledger", **size) \
    .save(OUT / "timeline.svg")
lv.calendar(commits, title="Commits in 2025", theme="ledger", width=860).save(OUT / "calendar.svg")
lv.line(x=x24, y=fc, band=(fc - 2, fc + 2.5), title="Forecast", subtitle="with 90% interval", theme="folio",
        number=7, **size).save(OUT / "band.svg")
lv.bar(groups, x="group", y="value", agg="mean", error="ci", title="Mean ± 95% CI", theme="ledger", **size) \
    .save(OUT / "errorbars.svg")
lv.grid([lv.stat(1284, label="Active users", previous=1190, spark=rng.normal(0, 1, 30).cumsum()),
         lv.stat(56.2, label="Revenue (k€)", previous=61.0, spark=rng.normal(0, 1, 30).cumsum()),
         lv.stat("99.9%", label="Uptime", note="last 30 days")], title="This week", theme="ledger") \
    .save(OUT / "stats.svg")
panel = pd.DataFrame({"month": np.tile(pd.date_range("2025-01-01", periods=12, freq="MS"), 12),
                      "region": np.repeat(["North", "South", "East", "West"], 36),
                      "source": np.tile(np.repeat(["Solar", "Wind", "Hydro"], 12), 4),
                      "gwh": rng.random(144) * 60 + np.tile(np.r_[np.linspace(20, 90, 6), np.linspace(90, 20, 6)], 12)})
lv.line(panel, x="month", y="gwh", color="source", facet="region", title="Output by region", subtitle="GWh",
        theme="fjord", width=860).save(OUT / "facets.svg")

# 0.3 chart types and features
n = 1_000_000
hx = np.r_[rng.normal(0, 1, n // 2), rng.normal(2.5, 1.2, n // 2)]
hy = np.r_[rng.normal(0, 0.8, n // 2), rng.normal(1.5, 1, n // 2)]
lv.hexbin(x=hx, y=hy, title="One million points in hexagons", subtitle="Log colour scale for skewed counts",
          theme="ledger", **size).save(OUT / "hexbin.svg")
world = {"Europe": {"Spain": {"Madrid": 6.8, "Barcelona": 5.6, "Valencia": 2.5, "Seville": 1.9},
                    "France": {"Paris": 11.2, "Lyon": 2.3, "Marseille": 1.9},
                    "Italy": {"Rome": 4.3, "Milan": 3.1, "Naples": 3.0}},
         "Asia": {"Japan": {"Tokyo": 37.2, "Osaka": 19.0}, "Korea": {"Seoul": 25.5, "Busan": 3.4}},
         "America": {"USA": {"New York": 19.5, "Los Angeles": 12.5, "Chicago": 8.9},
                     "Mexico": {"Mexico City": 21.8, "Guadalajara": 5.3},
                     "Brazil": {"São Paulo": 22.4, "Rio": 13.6}}}
lv.sunburst(world, title="Metropolitan population", subtitle="millions, three levels", theme="fjord",
            width=560, height=520).save(OUT / "sunburst.svg")
lv.treemap(world, title="Metropolitan population", subtitle="millions, three levels", theme="ledger", **size) \
    .save(OUT / "treemap-deep.svg")
quarters = {"North": {"Q1": 3.1, "Q2": 4.0, "Q3": 5.2, "Q4": 6.0}, "South": {"Q1": 4.2, "Q2": 3.3, "Q3": 5.0, "Q4": 4.1},
            "East": {"Q1": 2.0, "Q2": 3.1, "Q3": 3.9, "Q4": 5.2}}
lv.bar(quarters, title="Textures as a second encoding", subtitle="texture=True: readable in greyscale and for "
       "colour-blind readers", texture=True, theme="ledger", **size).save(OUT / "textures.svg")
months = pd.date_range("2025-01-01", periods=36, freq="MS")
dark_df = pd.DataFrame({"month": np.tile(months, 3), "source": np.repeat(["Solar", "Wind", "Hydro"], 36),
                        "twh": np.r_[4 + 3 * np.sin(np.arange(36) / 1.9), 5 + 1.5 * np.cos(np.arange(36) / 1.9),
                                     3 + rng.normal(0, 0.3, 36).cumsum() * 0.2]})
for name in ("ledger-dark", "fjord-dark", "folio-dark"):
    lv.line(dark_df, x="month", y="twh", color="source", title="Monthly generation", subtitle="TWh",
            theme=name, **size).save(OUT / f"{name}-line.svg")
acme = lv.themes.from_brand("#0f766e", base="ledger", name="acme")
lv.grid([lv.bar(quarters, title="Sales by quarter"),
         lv.line(dark_df, x="month", y="twh", color="source", title="Generation")],
        cols=2, title="A theme built from one brand colour", subtitle="lv.themes.from_brand('#0f766e')",
        theme="acme").save(OUT / "brand-theme.svg")
regions = {"AN": 8.6, "CT": 8.0, "MD": 7.0, "VC": 5.3, "GA": 2.7, "CL": 2.4, "PV": 2.2, "CN": 2.2, "CM": 2.1,
           "MC": 1.5, "AR": 1.3, "IB": 1.2, "EX": 1.1, "AS": 1.0, "NC": 0.7, "CB": 0.6, "RI": 0.3, "CE": 0.08,
           "ML": 0.09}
lv.tilemap(regions, layout="es-regions", names=True, title="Population by autonomous community",
           subtitle="millions (approximate)", label="millions", theme="fjord", width=640).save(OUT / "tilemap.svg")

print("wrote", len(list(OUT.glob("*.svg"))), "files to", OUT)
