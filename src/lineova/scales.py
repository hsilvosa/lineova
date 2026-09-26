"""Scales map data values to pixels and choose readable tick marks."""

from __future__ import annotations

import datetime as _dt
import math
from collections.abc import Sequence

import numpy as np

from ._text import format_number

# --------------------------------------------------------------------------- nice numbers


def nice_step(span: float, count: float) -> float:
    """A 1-2-2.5-5 step giving roughly ``count`` intervals over ``span``."""
    if span <= 0 or not math.isfinite(span):
        return 1.0
    raw = span / max(count, 1)
    mag = 10 ** math.floor(math.log10(raw))
    r = raw / mag
    if r < 1.5:
        f = 1
    elif r < 2.25:
        f = 2
    elif r < 3.5:
        f = 2.5
    elif r < 7.5:
        f = 5
    else:
        f = 10
    return f * mag


def nice_domain(lo: float, hi: float, count: float) -> tuple[float, float, float]:
    """Extend ``[lo, hi]`` outward to tick multiples. Returns ``(lo, hi, step)``."""
    if lo == hi:
        pad = abs(lo) * 0.1 or 1.0
        lo, hi = lo - pad, hi + pad
    step = nice_step(hi - lo, count)
    for _ in range(2):  # re-step once after extending
        nlo = math.floor(lo / step + 1e-9) * step
        nhi = math.ceil(hi / step - 1e-9) * step
        step2 = nice_step(nhi - nlo, count)
        if step2 == step:
            break
        step = step2
    return nlo, nhi, step


def linear_ticks(lo: float, hi: float, count: float) -> tuple[np.ndarray, float]:
    step = nice_step(hi - lo, count)
    start = math.ceil(lo / step - 1e-9) * step
    n = int(math.floor((hi - start) / step + 1e-9)) + 1
    ticks = start + step * np.arange(max(n, 0))
    ticks[np.abs(ticks) < step * 1e-9] = 0.0
    return ticks, step


# --------------------------------------------------------------------------- scales


class LinearScale:
    kind = "linear"

    def __init__(self, domain: Sequence[float], rng: Sequence[float]):
        self.d0, self.d1 = float(domain[0]), float(domain[1])
        self.r0, self.r1 = float(rng[0]), float(rng[1])
        span = self.d1 - self.d0
        self._k = (self.r1 - self.r0) / span if span else 0.0
        self.step = None

    def __call__(self, v):
        return self.r0 + (np.asarray(v, dtype=np.float64) - self.d0) * self._k

    def scalar(self, v: float) -> float:
        return self.r0 + (float(v) - self.d0) * self._k

    def invert(self, px: float) -> float:
        return self.d0 + (px - self.r0) / self._k if self._k else self.d0

    def transform(self, v):
        return np.asarray(v, dtype=np.float64)

    def ticks(self, count: float) -> np.ndarray:
        t, self.step = linear_ticks(min(self.d0, self.d1), max(self.d0, self.d1), count)
        return t

    def labels(self, ticks: np.ndarray, fmt=None) -> list[str]:
        if fmt is not None:
            return [_apply_fmt(fmt, v) for v in ticks]
        step = self.step or (abs(self.d1 - self.d0) / 5)
        return [format_number(v, step) for v in ticks]


class LogScale(LinearScale):
    kind = "log"

    def __init__(self, domain, rng):
        lo, hi = float(domain[0]), float(domain[1])
        if lo <= 0 or hi <= 0:
            raise ValueError("A log scale needs strictly positive values.")
        self.v0, self.v1 = lo, hi
        super().__init__((math.log10(lo), math.log10(hi)), rng)

    def __call__(self, v):
        with np.errstate(divide="ignore", invalid="ignore"):
            lv = np.log10(np.asarray(v, dtype=np.float64))
        return self.r0 + (lv - self.d0) * self._k

    def scalar(self, v):
        return self.r0 + (math.log10(v) - self.d0) * self._k if v > 0 else float("nan")

    def invert(self, px):
        return 10 ** super().invert(px)

    def transform(self, v):
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.log10(np.asarray(v, dtype=np.float64))

    def ticks(self, count):
        a, b = math.floor(self.d0 + 1e-9), math.ceil(self.d1 - 1e-9)
        decades = np.arange(a, b + 1)
        mults = (1,) if (b - a) > count * 0.6 else ((1, 2, 5) if (b - a) > 1 else (1, 2, 3, 5))
        vals = np.array([m * 10.0 ** d for d in decades for m in mults])
        keep = (vals >= self.v0 * (1 - 1e-9)) & (vals <= self.v1 * (1 + 1e-9))
        if (b - a) > count:  # too many decades: thin them
            k = math.ceil((b - a) / count)
            vals = np.array([10.0 ** d for d in decades if d % k == 0])
            keep = (vals >= self.v0 * (1 - 1e-9)) & (vals <= self.v1 * (1 + 1e-9))
        return vals[keep]

    def labels(self, ticks, fmt=None):
        if fmt is not None:
            return [_apply_fmt(fmt, v) for v in ticks]
        return [format_number(v, v) for v in ticks]


# --------------------------------------------------------------------------- time

_NS = {"ms": 1e6, "s": 1e9, "m": 60e9, "h": 3600e9, "D": 86400e9, "W": 7 * 86400e9,
       "M": 30.44 * 86400e9, "Y": 365.25 * 86400e9}
_TIME_STEPS = [
    (1, "ms"), (10, "ms"), (100, "ms"), (250, "ms"), (500, "ms"),
    (1, "s"), (2, "s"), (5, "s"), (10, "s"), (15, "s"), (30, "s"),
    (1, "m"), (2, "m"), (5, "m"), (10, "m"), (15, "m"), (30, "m"),
    (1, "h"), (2, "h"), (3, "h"), (6, "h"), (12, "h"),
    (1, "D"), (2, "D"), (1, "W"), (2, "W"),
    (1, "M"), (2, "M"), (3, "M"), (6, "M"),
    (1, "Y"), (2, "Y"), (5, "Y"), (10, "Y"), (20, "Y"), (50, "Y"), (100, "Y"), (250, "Y"), (500, "Y"),
]
_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _to_dt(v: float) -> _dt.datetime:
    return np.datetime64(int(round(v)), "ns").astype("datetime64[us]").astype(_dt.datetime)


class TimeScale(LinearScale):
    """Values are nanoseconds since the epoch (as float64)."""

    kind = "time"
    unit = "D"

    def ticks(self, count):
        lo, hi = min(self.d0, self.d1), max(self.d0, self.d1)
        span = hi - lo
        k, unit = _TIME_STEPS[-1]
        for kk, uu in _TIME_STEPS:
            if span / (kk * _NS[uu]) <= count:
                k, unit = kk, uu
                break
        self.unit, self.k = unit, k
        lo64 = np.datetime64(int(lo), "ns")
        hi64 = np.datetime64(int(hi), "ns")
        if unit in ("M", "Y"):
            a = lo64.astype(f"datetime64[{unit}]").astype(np.int64)
            b = hi64.astype(f"datetime64[{unit}]").astype(np.int64) + 1
            base = 1970 if unit == "Y" else 0
            vals = [v for v in range(a, b + 1) if (v + base) % k == 0]
            t = np.array(vals, dtype=f"datetime64[{unit}]").astype("datetime64[ns]").astype(np.int64)
        elif unit == "W":
            days = lo64.astype("datetime64[D]").astype(np.int64)
            first_monday = days + ((4 - days) % 7)  # 1970-01-05 was a Monday
            t = np.arange(first_monday, hi64.astype("datetime64[D]").astype(np.int64) + 1, 7 * k)
            t = t.astype("datetime64[D]").astype("datetime64[ns]").astype(np.int64)
        else:
            step = int(k * _NS[unit])
            start = (int(lo) // step) * step
            t = np.arange(start, int(hi) + step, step, dtype=np.int64)
        t = t.astype(np.float64)
        return t[(t >= lo - 1) & (t <= hi + 1)]

    def labels(self, ticks, fmt=None):
        dts = [_to_dt(v) for v in ticks]
        if fmt is not None:
            return [d.strftime(fmt) if isinstance(fmt, str) and "%" in fmt else _apply_fmt(fmt, d) for d in dts]
        unit = getattr(self, "unit", "D")
        out, prev = [], None
        for d in dts:
            if unit == "Y":
                s = str(d.year)
            elif unit == "M":
                s = _MON[d.month - 1] + (f" {d.year}" if prev is None or d.year != prev.year else "")
            elif unit in ("D", "W"):
                s = f"{_MON[d.month - 1]} {d.day}"
                if prev is None or d.year != prev.year:
                    s += f", {d.year}"
            elif unit in ("h", "m"):
                midnight = d.hour == 0 and d.minute == 0
                s = f"{_MON[d.month - 1]} {d.day}" if midnight else d.strftime("%H:%M")
            elif unit == "s":
                s = d.strftime("%H:%M:%S")
            else:
                s = d.strftime("%S.%f")[:-3]
            out.append(s)
            prev = d
        return out


# --------------------------------------------------------------------------- categories


class BandScale:
    kind = "band"

    def __init__(self, categories: Sequence, rng: Sequence[float], gap: float = 0.25, outer: float | None = None):
        self.categories = list(categories)
        self.index = {c: i for i, c in enumerate(self.categories)}
        n = max(1, len(self.categories))
        self.r0, self.r1 = float(rng[0]), float(rng[1])
        outer = gap / 2 if outer is None else outer
        span = self.r1 - self.r0
        self.step = span / (n + 2 * outer - gap) if (n + 2 * outer - gap) else span
        self.bandwidth = self.step * (1 - gap)
        self.start = self.r0 + self.step * outer

    def band(self, i: int) -> float:
        """Start (px) of band ``i``."""
        return self.start + i * self.step

    def center(self, i):
        return self.start + np.asarray(i) * self.step + self.bandwidth / 2

    def __call__(self, v):
        return self.center(np.array([self.index[c] for c in np.atleast_1d(v)]))


def _apply_fmt(fmt, v) -> str:
    if callable(fmt):
        return str(fmt(v))
    if isinstance(fmt, str):
        if "{" in fmt:
            return fmt.format(v)
        return format(v, fmt)
    raise TypeError("format must be a callable, a format spec like ',.1f', or a template like '{:.0%}'")
