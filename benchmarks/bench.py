"""Timing for large inputs. Run: python benchmarks/bench.py [--big]

Each case builds the chart and serialises it to SVG (the full pipeline).
"""
import sys
import time

import numpy as np

import lineova as lv


def timed(label, fn):
    t0 = time.perf_counter()
    out = fn()
    dt = time.perf_counter() - t0
    size = len(out) / 1e6
    print(f"{label:<44} {dt:7.2f} s   SVG {size:6.2f} MB")


def main(big: bool):
    rng = np.random.default_rng(0)
    sizes = [1_000_000, 10_000_000] + ([100_000_000] if big else [])
    for n in sizes:
        t = np.arange(n, dtype=np.float64)
        y = np.cumsum(rng.standard_normal(n))
        timed(f"line, {n:,} points", lambda: lv.line(x=t, y=y).to_svg())
        del t
        x = rng.standard_normal(n)
        y2 = x * 0.6 + rng.standard_normal(n) * 0.8
        timed(f"scatter (density), {n:,} points", lambda: lv.scatter(x=x, y=y2).to_svg())
        timed(f"histogram, {n:,} values", lambda: lv.histogram(y2).to_svg())
        del x, y2, y
    m = rng.standard_normal((4000, 4000)).cumsum(axis=1)
    timed("heatmap, 4000 x 4000 matrix", lambda: lv.heatmap(m).to_svg())
    for ne in (2_000, 200_000):
        nn = max(100, ne // 5)
        edges = rng.integers(0, nn, size=(ne, 2))
        timed(f"network, {nn:,} nodes / {ne:,} edges", lambda: lv.network(edges).to_svg())


if __name__ == "__main__":
    main("--big" in sys.argv)
