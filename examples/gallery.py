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
print("wrote", len(list(OUT.glob("*.svg"))), "files to", OUT)
