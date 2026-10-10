"""Timing for large inputs.

    python benchmarks/bench.py                  # standard cases
    python benchmarks/bench.py --big            # adds 100M-point cases
    python benchmarks/bench.py --save FILE      # write the results as JSON (e.g. benchmarks/baseline.json)
    python benchmarks/bench.py --compare FILE   # print the speed-up against a saved run
    python benchmarks/bench.py --only line,pdf  # run only the cases whose name contains one of these words

Each case builds the chart and serialises it (SVG unless the name says otherwise): the full pipeline.
Data generation is not timed.
"""
import argparse
import json
import platform
import time

import numpy as np

import lineova as lv


def _line(n):
    rng = np.random.default_rng(0)
    t = np.arange(n, dtype=np.float64)
    y = np.cumsum(rng.standard_normal(n))
    return lambda: lv.line(x=t, y=y).to_svg()


def _scatter(n):
    rng = np.random.default_rng(1)
    x = rng.standard_normal(n)
    y = x * 0.6 + rng.standard_normal(n) * 0.8
    return lambda: lv.scatter(x=x, y=y).to_svg()


def _hist(n):
    values = np.random.default_rng(2).standard_normal(n)
    return lambda: lv.histogram(values).to_svg()


def _hexbin(n):
    rng = np.random.default_rng(3)
    x = rng.standard_normal(n)
    y = x * 0.6 + rng.standard_normal(n) * 0.8
    return lambda: lv.hexbin(x=x, y=y).to_svg()


def _heatmap_matrix(side):
    m = np.random.default_rng(4).standard_normal((side, side)).cumsum(axis=1)
    return lambda: lv.heatmap(m).to_svg()


def _heatmap_chunks(rows, chunk=1_000_000):
    def source():
        rng = np.random.default_rng(5)
        for _ in range(rows // chunk):
            yield {"a": rng.integers(0, 50, chunk).astype(float),
                   "b": rng.integers(0, 40, chunk).astype(float),
                   "v": rng.standard_normal(chunk)}
    return lambda: lv.heatmap(lv.Chunks(source), x="a", y="b", value="v").to_svg()


def _network(ne):
    nn = max(100, ne // 5)
    edges = np.random.default_rng(6).integers(0, nn, size=(ne, 2))
    return lambda: lv.network(edges).to_svg()


def _pdf_line(n):
    rng = np.random.default_rng(7)
    t = np.arange(n, dtype=np.float64)
    y = np.cumsum(rng.standard_normal(n))
    return lambda: lv.line(x=t, y=y).to_pdf()


def _facets():
    rng = np.random.default_rng(8)
    n = 200_000
    data = {"x": rng.standard_normal(n), "y": rng.standard_normal(n),
            "g": rng.integers(0, 12, n).astype(str)}
    return lambda: lv.scatter(data, x="x", y="y", facet="g").to_svg()


def cases(big: bool):
    out = [
        ("line 1M", lambda: _line(1_000_000)),
        ("line 10M", lambda: _line(10_000_000)),
        ("scatter 1M", lambda: _scatter(1_000_000)),
        ("scatter 5M", lambda: _scatter(5_000_000)),
        ("scatter 10M", lambda: _scatter(10_000_000)),
        ("histogram 10M", lambda: _hist(10_000_000)),
        ("hexbin 5M", lambda: _hexbin(5_000_000)),
        ("heatmap matrix 4000x4000", lambda: _heatmap_matrix(4000)),
        ("heatmap chunks 10M rows", lambda: _heatmap_chunks(10_000_000)),
        ("network 2k edges", lambda: _network(2_000)),
        ("network 200k edges", lambda: _network(200_000)),
        ("network 100k nodes", lambda: _network(500_000)),
        ("facets 12 x 200k scatter", _facets),
        ("pdf line 1M", lambda: _pdf_line(1_000_000)),
    ]
    if big:
        out += [("line 100M", lambda: _line(100_000_000)),
                ("scatter 100M", lambda: _scatter(100_000_000))]
    return out


def run(big, only):
    results = {}
    for name, make in cases(big):
        if only and not any(w in name for w in only):
            continue
        fn = make()
        t0 = time.perf_counter()
        out = fn()
        dt = time.perf_counter() - t0
        results[name] = {"seconds": round(dt, 3), "output_mb": round(len(out) / 1e6, 3)}
        print(f"{name:<32} {dt:8.2f} s   out {len(out) / 1e6:7.2f} MB", flush=True)
        del fn, out
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--big", action="store_true")
    ap.add_argument("--save")
    ap.add_argument("--compare")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    only = [w for w in a.only.split(",") if w]
    results = run(a.big, only)
    if a.save:
        meta = {"python": platform.python_version(), "numpy": np.__version__, "lineova": lv.__version__}
        with open(a.save, "w") as f:
            json.dump({"meta": meta, "results": results}, f, indent=2)
        print(f"saved {a.save}")
    if a.compare:
        with open(a.compare) as f:
            base = json.load(f)["results"]
        print("\nvs", a.compare)
        for name, r in results.items():
            if name in base and r["seconds"] > 0:
                print(f"{name:<32} {base[name]['seconds'] / r['seconds']:6.2f}x   ({base[name]['seconds']:.2f} -> {r['seconds']:.2f} s)")


if __name__ == "__main__":
    main()
