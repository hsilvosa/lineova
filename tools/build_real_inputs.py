"""Rebuild the input files of ``examples/real_data.py`` from the raw public sources.

    python tools/build_real_inputs.py prices   DATA_DIR [--start 2023-01-01] [--end 2026-03-31]
    python tools/build_real_inputs.py curves   DATA_DIR  2024-01 2024-02 ...          (months)
    python tools/build_real_inputs.py quakes   DATA_DIR  catalogue1.csv [catalogue2.csv ...]

Then:  python examples/real_data.py DATA_DIR

``prices``  downloads the daily OMIE files ``marginalpdbc_YYYYMMDD.1`` (rows ``year;month;day;period;price_es;price_pt;``)
            and writes ``omie_prices.csv`` with the columns ``date,period,price_es,price_pt``. Downloads are cached in
            ``DATA_DIR/raw`` so a rerun only fetches what is missing.
``curves``  downloads the monthly OMIE archives ``curva_pbc_uof_YYYYMM.zip`` (one file per day with every bid:
            ``Hora;Fecha;Pais;Unidad;Tipo Oferta;Energía Compra/Venta;Precio Compra/Venta;Ofertada (O)/Casada (C)``,
            decimal comma) and writes ``curves_YYYYMM.npz`` with the arrays day (YYYYMMDD), hour, side (1 = sell),
            status (1 = matched), energy and price.
``quakes``  turns catalogue exports from the Instituto Geografico Nacional (the search form at
            https://www.ign.es/web/ign/portal/sis-catalogo-terremotos, CSV with ';') into ``ign_earthquakes.csv``
            with the columns ``event_id;date;time;lat;lon;depth_km;intensity;magnitude;mag_type;location``. Columns are
            found by their Spanish header names, so the order and accents do not matter.

The sources keep their own terms: OMIE market data needs attribution to OMIE; the IGN catalogue is published at
https://doi.org/10.7419/162.03.2022. Needs pandas for ``curves`` and ``quakes``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

OMIE = "https://www.omie.es/es/file-download?parents%5B0%5D={folder}&filename={name}"
QUAKE_COLUMNS = ["event_id", "date", "time", "lat", "lon", "depth_km", "intensity", "magnitude", "mag_type", "location"]


# --------------------------------------------------------------------------- download

def fetch(folder: str, name: str, cache: Path | None = None, retries: int = 3) -> bytes | None:
    """Bytes of one OMIE file (None when the site has no such file). Cached under ``cache``."""
    if cache is not None and (cache / name).exists():
        return (cache / name).read_bytes()
    url = OMIE.format(folder=folder, name=name)
    last: Exception | None = None
    for k in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "lineova-tools"}), timeout=120) as r:
                data = r.read()
            if data[:1] == b"<":                         # an HTML error page: the file does not exist
                return None
            if cache is not None:
                cache.mkdir(parents=True, exist_ok=True)
                (cache / name).write_bytes(data)
            return data
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return None
            last = e
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
        time.sleep(1.5 * (k + 1))
    raise RuntimeError(f"could not download {name}: {last}")


# --------------------------------------------------------------------------- prices

def parse_prices(text: str) -> list[tuple[str, int, float, float]]:
    """Rows (date, period, price_es, price_pt) of one ``marginalpdbc`` file."""
    rows = []
    for line in text.splitlines():
        parts = line.strip().split(";")
        if len(parts) < 6 or not parts[0].isdigit():
            continue
        y, m, d, period = (int(p) for p in parts[:4])
        rows.append((f"{y:04d}-{m:02d}-{d:02d}", period, float(parts[4]), float(parts[5])))
    return rows


def build_prices(out: Path, start: dt.date, end: dt.date, workers: int = 6) -> int:
    cache = out / "raw"
    days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]

    def one(day: dt.date):
        data = fetch("marginalpdbc", f"marginalpdbc_{day:%Y%m%d}.1", cache)
        return day, None if data is None else parse_prices(data.decode("latin-1"))

    rows, missing = [], []
    with ThreadPoolExecutor(workers) as pool:
        for day, got in pool.map(one, days):
            (missing if got is None else rows).append(day if got is None else got)
    flat = [r for chunk in rows for r in chunk]
    flat.sort(key=lambda r: (r[0], r[1]))
    with open(out / "omie_prices.csv", "w", encoding="utf-8", newline="") as fh:
        fh.write("date,period,price_es,price_pt\n")
        for date, period, es, pt in flat:
            fh.write(f"{date},{period},{es:g},{pt:g}\n")
    if missing:
        print(f"no file for {len(missing)} days (first: {missing[0]}, last: {missing[-1]})", file=sys.stderr)
    return len(flat)


# --------------------------------------------------------------------------- bid curves

def _number(series):
    """Spanish numbers (``1.500,00``) as floats."""
    return series.astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float)


def parse_curves(text: str) -> dict[str, np.ndarray]:
    """Arrays day, hour, side, status, energy, price from one ``curva_pbc_uof`` file."""
    import pandas as pd
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.lower().startswith("hora;")), None)
    if start is None:
        raise ValueError("no header line (Hora;Fecha;...) found")
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])), sep=";", dtype=str, usecols=range(8))
    df.columns = ["hour", "date", "country", "unit", "kind", "energy", "price", "status"]
    df = df[df["hour"].str.fullmatch(r"\d+", na=False)]
    day = pd.to_datetime(df["date"], format="%d/%m/%Y")
    return {
        "day": (day.dt.year * 10000 + day.dt.month * 100 + day.dt.day).to_numpy(np.int32),
        "hour": df["hour"].astype(int).to_numpy(np.int16),
        "side": (df["kind"].str.upper() == "V").to_numpy(np.int8),
        "status": (df["status"].str.upper() == "C").to_numpy(np.int8),
        "energy": _number(df["energy"]).to_numpy(np.float32),
        "price": _number(df["price"]).to_numpy(np.float32),
    }


def build_curves(out: Path, month: str) -> int:
    data = fetch("curva_pbc_uof", f"curva_pbc_uof_{month.replace('-', '')}.zip", out / "raw")
    if data is None:
        raise SystemExit(f"OMIE has no curve archive for {month}")
    parts = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in sorted(z.namelist()):
            parts.append(parse_curves(z.read(name).decode("latin-1")))
    arrays = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    np.savez_compressed(out / f"curves_{month.replace('-', '')}.npz", **arrays)
    return len(arrays["price"])


# --------------------------------------------------------------------------- earthquakes

def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]+", "", s)


_QUAKE_KEYS = [("event_id", ("evento", "eventid", "id")), ("date", ("fecha", "date")), ("time", ("hora", "time")),
               ("lat", ("latitud", "latitude", "lat")), ("lon", ("longitud", "longitude", "lon")),
               ("depth_km", ("prof", "profundidad", "depth")), ("intensity", ("inten", "intensidad", "intensity")),
               ("magnitude", ("mag", "magnitud", "magnitude")), ("mag_type", ("tipomag", "magtype", "tipomagnitud")),
               ("location", ("localizacion", "location", "lugar"))]


def parse_quakes(text: str):
    """Normalised catalogue (a DataFrame with ``QUAKE_COLUMNS``) from an IGN export."""
    import pandas as pd
    df = pd.read_csv(io.StringIO(text), sep=";", dtype=str, skipinitialspace=True)
    heads = {_norm(c): c for c in df.columns}
    out = {}
    for target, options in _QUAKE_KEYS:
        found = next((heads[o] for o in options if o in heads), None)
        if found is None:
            found = next((c for k, c in heads.items() if any(k.startswith(o) for o in options)), None)
        if found is None and target not in ("event_id", "intensity", "mag_type", "location"):
            raise ValueError(f"no column for {target!r} in {list(df.columns)}")
        out[target] = df[found].str.strip() if found is not None else ""
        if found is not None and target in ("lat", "lon", "depth_km", "magnitude"):
            out[target] = df[found].str.replace(",", ".", regex=False).str.strip()
    res = pd.DataFrame(out)
    for c in ("lat", "lon", "magnitude"):
        res[c] = pd.to_numeric(res[c], errors="coerce")
    res = res.dropna(subset=["lat", "lon"])
    return res[QUAKE_COLUMNS]


def build_quakes(out: Path, files: list[Path]) -> int:
    import pandas as pd
    frames = [parse_quakes(Path(f).read_text(encoding="utf-8-sig", errors="replace")) for f in files]
    allq = pd.concat(frames, ignore_index=True)
    allq = allq.drop_duplicates(subset=["event_id"] if allq["event_id"].astype(str).str.len().gt(0).all() else None)
    allq.to_csv(out / "ign_earthquakes.csv", sep=";", index=False)
    return len(allq)


# --------------------------------------------------------------------------- command line

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prices")
    p.add_argument("out", type=Path)
    p.add_argument("--start", type=dt.date.fromisoformat, default=dt.date(2023, 1, 1))
    p.add_argument("--end", type=dt.date.fromisoformat, default=dt.date.today() - dt.timedelta(days=1))
    p.add_argument("--workers", type=int, default=6)
    c = sub.add_parser("curves")
    c.add_argument("out", type=Path)
    c.add_argument("months", nargs="+", help="YYYY-MM")
    q = sub.add_parser("quakes")
    q.add_argument("out", type=Path)
    q.add_argument("files", nargs="+", type=Path)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    if a.cmd == "prices":
        print(f"wrote {build_prices(a.out, a.start, a.end, a.workers):,} price rows to {a.out / 'omie_prices.csv'}")
    elif a.cmd == "curves":
        for m in a.months:
            print(f"{m}: {build_curves(a.out, m):,} bids")
    else:
        print(f"wrote {build_quakes(a.out, a.files):,} events to {a.out / 'ign_earthquakes.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
