"""Input normalisation: turn whatever the user passes into NumPy arrays.

Accepted everywhere: lists, tuples, ranges, NumPy arrays (incl. memmaps),
dicts of columns, pandas/polars Series and DataFrames, anything exposing
``__array__`` or ``to_numpy``. pandas and polars are never imported unless the
user already passed one of their objects.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


class DataError(ValueError):
    """Raised when input data can't be understood. Messages say how to fix it."""


# --------------------------------------------------------------------------- basics

def is_frame(obj: Any) -> bool:
    """DataFrame-like: pandas/polars frames, dicts of columns, structured arrays."""
    if obj is None:
        return False
    if isinstance(obj, dict):
        return True
    if isinstance(obj, np.ndarray):
        return obj.dtype.names is not None
    return hasattr(obj, "columns") and hasattr(obj, "__getitem__") and not hasattr(obj, "dtype")


def columns_of(frame: Any) -> list:
    if isinstance(frame, dict):
        return list(frame.keys())
    if isinstance(frame, np.ndarray):
        return list(frame.dtype.names)
    return list(frame.columns)


def get_column(frame: Any, key: Any):
    try:
        return frame[key]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        cols = columns_of(frame)
        hint = ", ".join(map(repr, cols[:12])) + (" …" if len(cols) > 12 else "")
        raise DataError(f"Column {key!r} not found. Available columns: {hint}") from exc


def series_name(obj: Any) -> Optional[str]:
    name = getattr(obj, "name", None)
    return str(name) if name is not None and not callable(name) else None


def to_array(obj: Any) -> np.ndarray:
    """1-D NumPy view/copy of any array-like. Avoids copies where possible."""
    if isinstance(obj, np.ndarray):
        return obj
    mod = type(obj).__module__.split(".")[0]
    if mod == "pandas":
        dtype = getattr(obj, "dtype", None)
        if dtype is not None and getattr(dtype, "tz", None) is not None:  # tz-aware -> UTC naive
            obj = obj.dt.tz_convert("UTC").dt.tz_localize(None) if hasattr(obj, "dt") else obj.tz_convert("UTC").tz_localize(None)
        if dtype is not None and str(dtype) == "category":
            return np.asarray(obj.astype(object))
        if dtype is not None and hasattr(dtype, "numpy_dtype"):  # nullable Int64/Float64/boolean
            return obj.to_numpy(dtype="float64", na_value=np.nan)
        return obj.to_numpy()
    if mod == "polars":
        return obj.to_numpy()
    if hasattr(obj, "to_numpy"):
        return np.asarray(obj.to_numpy())
    if isinstance(obj, (range, list, tuple)):
        return np.asarray(obj)
    if hasattr(obj, "__array__"):
        return np.asarray(obj)
    if hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes)):
        return np.asarray(list(obj))
    raise DataError(f"Can't turn {type(obj).__name__} into an array of values.")


def value_kind(a: np.ndarray) -> str:
    """'num', 'time' or 'cat'."""
    k = a.dtype.kind
    if k == "M":
        return "time"
    if k in "iuf":
        return "num"
    if k == "b":
        return "cat"
    if k == "m":
        return "num"
    if k == "O" and len(a):
        first = next((v for v in a[:50] if v is not None), None)
        if isinstance(first, (_dt.datetime, _dt.date, np.datetime64)):
            return "time"
        if isinstance(first, (int, float, np.integer, np.floating)) and not isinstance(first, bool):
            try:
                a[:1000].astype(np.float64)
                return "num"
            except (TypeError, ValueError):
                return "cat"
        if type(first).__name__ == "Timestamp":
            return "time"
    return "cat"


def as_float(a: np.ndarray, kind: str) -> np.ndarray:
    """Numeric representation used by scales. Time -> ns since epoch (float64)."""
    if kind == "time":
        if a.dtype.kind != "M":
            a = np.array([np.datetime64(v) if v is not None else np.datetime64("NaT") for v in a],
                         dtype="datetime64[ns]")
        a = a.astype("datetime64[ns]", copy=False)
        out = a.view(np.int64).astype(np.float64)
        out[np.isnat(a)] = np.nan
        return out
    if a.dtype.kind == "m":
        return a.astype("timedelta64[ns]").view(np.int64).astype(np.float64) / 1e9
    if a.dtype == np.float64:
        return a
    try:
        return a.astype(np.float64)
    except (TypeError, ValueError):
        out = np.empty(len(a), dtype=np.float64)
        for i, v in enumerate(a):
            try:
                out[i] = float(v) if v is not None else np.nan
            except (TypeError, ValueError):
                raise DataError(f"Value {v!r} at position {i} is not a number.") from None
        return out


def factorize(a: np.ndarray) -> tuple[np.ndarray, list]:
    """Integer codes + unique labels in order of first appearance. NaN/None -> -1."""
    try:
        import pandas as pd  # noqa: F401 - only used if installed
        codes, uniques = pd.factorize(a, use_na_sentinel=True)
        return np.asarray(codes, dtype=np.int64), [str(u) for u in uniques]
    except ImportError:
        pass
    labels = np.array([str(v) if v is not None else "\0nan" for v in a], dtype=object)
    uniq, first, inv = np.unique(labels, return_index=True, return_inverse=True)
    order = np.argsort(first)
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    codes = rank[inv].astype(np.int64)
    names = [str(u) for u in uniq[order]]
    if "\0nan" in names:
        bad = names.index("\0nan")
        codes = np.where(codes == bad, -1, np.where(codes > bad, codes - 1, codes))
        names.pop(bad)
    return codes, names


def ordered_categories(obj: Any) -> Optional[list]:
    """Category order if the input carries one (pandas Categorical)."""
    cat = getattr(obj, "cat", None)
    if cat is not None and hasattr(cat, "categories"):
        return [str(c) for c in cat.categories]
    return None


# --------------------------------------------------------------------------- series


@dataclass
class Series:
    name: str
    x: np.ndarray               # float64 (numeric / ns) or object labels for categorical
    y: np.ndarray               # float64
    extra: dict = field(default_factory=dict)


@dataclass
class XY:
    series: list[Series]
    x_kind: str                 # num | time | cat
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    categories: Optional[list] = None   # for cat x: order of categories
    grouped_by: Optional[str] = None


_AUTO = "auto"


def is_auto(v) -> bool:
    """True only for the string "auto" (safe with arrays)."""
    return isinstance(v, str) and v == _AUTO


def _looks_like_many(y: Any) -> bool:
    if isinstance(y, np.ndarray):
        return y.ndim == 2
    if isinstance(y, (list, tuple)) and y and not isinstance(y[0], (str, bytes)):
        first = y[0]
        return hasattr(first, "__len__") and not isinstance(first, (str, bytes)) and len(y) > 0 and \
            all(hasattr(v, "__len__") for v in y[:5])
    return False


def resolve_xy(data=None, x=None, y=None, color=None, *, allow_cat_x=True, extra: Optional[dict] = None) -> XY:
    """Normalise the many ways people pass x/y data into a list of ``Series``.

    ``extra`` maps names to per-point columns/arrays that travel with y (error
    bars, bands, sizes). They are split by group and sorted along with the data;
    each series gets them in ``Series.extra``.
    """
    xy = _resolve_xy(data, x, y, color, extra)
    for s in xy.series:
        for k, v in s.extra.items():
            s.extra[k] = as_float(np.asarray(v), "num")
            if len(s.extra[k]) != len(s.y):
                raise DataError(f"{k!r} has {len(s.extra[k])} values but {s.name!r} has {len(s.y)} points.")
    return xy


def _extra_arrays(data, extra, n_hint=None) -> dict:
    out = {}
    for k, spec in (extra or {}).items():
        if spec is None:
            continue
        if isinstance(spec, str) and is_frame(data):
            out[k] = to_array(get_column(data, spec))
        elif isinstance(spec, dict):
            out[k] = spec            # per-series mapping, resolved later
        elif np.ndim(spec) == 0:
            out[k] = np.full(n_hint or 0, float(spec)) if n_hint else spec
        else:
            out[k] = to_array(spec)
    return out


def _attach(series: list, extras: dict) -> list:
    for s in series:
        for k, v in extras.items():
            if isinstance(v, dict):
                if s.name in v:
                    s.extra[k] = to_array(v[s.name]) if np.ndim(v[s.name]) else np.full(len(s.y), float(v[s.name]))
            elif np.ndim(v) == 0:
                s.extra[k] = np.full(len(s.y), float(v))
            else:
                s.extra[k] = v
    return series


def _resolve_xy(data, x, y, color, extra) -> XY:
    x_label = y_label = None
    grouped_by = None

    # -- a DataFrame (or dict of columns) with column names --------------------------------
    if is_frame(data) and not (isinstance(data, dict) and y is None and x is None
                               and all(np.ndim(v) == 0 for v in data.values())):
        cols = columns_of(data)
        if isinstance(data, dict) and y is None and (color is None or is_auto(color)) and (x is None or not _is_key(x)):
            # {name: values}: one series per key (x optional, shared)
            return _attach_xy(_from_mapping(data, x), _extra_arrays(None, extra))
        xcol = x
        if xcol is None:
            xcol = _guess_x(data, cols)
        x_arr, x_label = _x_from(data, xcol)
        if y is None:
            ycols = [c for c in cols if c != xcol and value_kind(to_array(get_column(data, c))) == "num"]
            if not (color is None or is_auto(color)):
                ycols = [c for c in ycols if c != color]
            if not ycols:
                raise DataError("No numeric column to plot. Pass y='column_name'.")
        else:
            ycols = list(y) if isinstance(y, (list, tuple)) else [y]
        if is_auto(color) and len(ycols) == 1:
            color = guess_group(data, cols, exclude={xcol, ycols[0]})
        elif is_auto(color):
            color = None
        if color is not None and len(ycols) == 1:
            grouped_by = str(color)
            y_label = str(ycols[0])
            yv = to_array(get_column(data, ycols[0]))
            gv = to_array(get_column(data, color))
            order = ordered_categories(get_column(data, color))
            ex = _extra_arrays(data, extra)
            return _finish(_split_groups(x_arr, yv, gv, order, ex), x_label, y_label, grouped_by)
        series = [Series(str(c), x_arr, to_array(get_column(data, c))) for c in ycols]
        y_label = str(ycols[0]) if len(ycols) == 1 else None
        return _finish(_attach(series, _extra_arrays(data, extra)), x_label, y_label, None)

    # -- data passed positionally as the y values ---------------------------------------
    if data is not None and y is None:
        y, data = data, None
    if y is None:
        raise DataError("Nothing to plot: pass data, e.g. lv.line([3, 1, 4, 1, 5]).")
    if isinstance(y, dict):
        return _attach_xy(_from_mapping(y, x), _extra_arrays(None, extra))
    if _looks_like_many(y):
        arr = y if isinstance(y, np.ndarray) else None
        cols = [arr[:, i] for i in range(arr.shape[1])] if arr is not None else [to_array(v) for v in y]
        xs = None if x is None else to_array(x)
        series = [Series(f"Series {i + 1}", xs if xs is not None else np.arange(len(c)), to_array(c))
                  for i, c in enumerate(cols)]
        return _finish(_attach(series, _extra_arrays(None, extra)), series_name(x), None, None)
    if is_frame(y):
        return _resolve_xy(y, x, None, color, extra)
    yv = to_array(y)
    name = series_name(y) or "Series 1"
    if x is None:
        idx = getattr(y, "index", None)
        if idx is not None and type(y).__module__.split(".")[0] == "pandas" and not _is_range_index(idx):
            xv, x_label = to_array(idx), series_name(idx)
        else:
            xv = np.arange(len(yv))
    else:
        xv, x_label = to_array(x), series_name(x)
    if color is not None and not is_auto(color):
        gv = to_array(color)
        ex = _extra_arrays(None, extra)
        return _finish(_split_groups(xv, yv, gv, ordered_categories(color), ex), x_label, series_name(y),
                       series_name(color))
    return _finish(_attach([Series(name, xv, yv)], _extra_arrays(None, extra)), x_label, series_name(y), None)


def _attach_xy(xy: XY, extras: dict) -> XY:
    _attach(xy.series, extras)
    return xy


def _is_range_index(idx) -> bool:
    return type(idx).__name__ == "RangeIndex"


def _from_mapping(mapping: dict, x) -> XY:
    xs = None if x is None else to_array(x)
    series = []
    for k, v in mapping.items():
        if isinstance(v, tuple) and len(v) == 2 and np.ndim(v[0]) == 1:
            series.append(Series(str(k), to_array(v[0]), to_array(v[1])))
        else:
            yv = to_array(v)
            series.append(Series(str(k), xs if xs is not None else np.arange(len(yv)), yv))
    return _finish(series, series_name(x), None, None)


def _guess_x(frame, cols):
    for c in cols:
        if value_kind(to_array(get_column(frame, c))) == "time":
            return c
    idx = getattr(frame, "index", None)
    if idx is not None and type(frame).__module__.split(".")[0] == "pandas" and not _is_range_index(idx):
        return _INDEX
    return None


_INDEX = object()


def _is_key(v) -> bool:
    return isinstance(v, (str, int, np.integer, tuple)) or v is None


def _x_from(frame, xcol):
    if xcol is not None and not _is_key(xcol) and xcol is not _INDEX:
        return to_array(xcol), series_name(xcol)
    if xcol is None:
        n = len(to_array(get_column(frame, columns_of(frame)[0])))
        return np.arange(n), None
    if xcol is _INDEX:
        return to_array(frame.index), series_name(frame.index)
    return to_array(get_column(frame, xcol)), str(xcol)


def guess_group(frame, cols, exclude) -> Optional[str]:
    """A low-cardinality text column is almost always the series identity."""
    best = None
    for c in cols:
        if c in exclude:
            continue
        a = to_array(get_column(frame, c))
        if value_kind(a) != "cat":
            continue
        sample = a[: min(len(a), 200_000)]
        k = len(set(map(str, sample[:50_000])))
        if 1 < k <= 12 and (best is None or k < best[1]):
            best = (c, k)
    return best[0] if best else None


def _split_groups(x, y, g, order=None, extras: Optional[dict] = None) -> list[Series]:
    codes, names = factorize(g)
    if order:
        pos = {n: i for i, n in enumerate(order)}
        new_names = sorted(names, key=lambda n: pos.get(n, len(pos)))
        where = {n: i for i, n in enumerate(new_names)}
        remap = np.array([where[n] for n in names], dtype=np.int64)
        if len(remap):
            codes = np.where(codes >= 0, remap[np.maximum(codes, 0)], -1)
        names = new_names
    idx = np.argsort(codes, kind="stable")
    counts = np.bincount(codes[codes >= 0], minlength=len(names))
    skip = int((codes < 0).sum())
    out, start = [], skip
    for i, n in enumerate(names):
        sel = idx[start:start + counts[i]]
        start += counts[i]
        ex = {k: (v[sel] if np.ndim(v) else v) for k, v in (extras or {}).items() if not isinstance(v, dict)}
        s = Series(n, x[sel], y[sel], ex)
        _attach([s], {k: v for k, v in (extras or {}).items() if isinstance(v, dict)})
        out.append(s)
    return out


def _finish(series: list[Series], x_label, y_label, grouped_by) -> XY:
    if not series:
        raise DataError("No data to plot.")
    kinds = {value_kind(s.x) for s in series}
    x_kind = "time" if "time" in kinds else ("cat" if "cat" in kinds else "num")
    categories = None
    for s in series:
        if len(s.x) != len(s.y):
            raise DataError(f"x and y have different lengths in {s.name!r}: {len(s.x)} vs {len(s.y)}.")
        if value_kind(s.y) == "cat":
            raise DataError(f"y values of {s.name!r} are not numeric (found e.g. {s.y[:1].tolist()!r}).")
        s.y = as_float(s.y, "num")
    if x_kind == "cat":
        seen: dict = {}
        for s in series:
            s.x = np.asarray([str(v) for v in s.x], dtype=object)
            for v in s.x:
                seen.setdefault(v, None)
        categories = list(seen)
    else:
        for s in series:
            s.x = as_float(s.x, x_kind)
    return XY(series, x_kind, x_label, y_label, categories, grouped_by)


# --------------------------------------------------------------------------- aggregation

_AGG = {
    "sum": np.nansum, "mean": np.nanmean, "median": np.nanmedian,
    "min": np.nanmin, "max": np.nanmax, "count": lambda v: float(np.count_nonzero(~np.isnan(v))),
    "std": lambda v: float(np.nanstd(v, ddof=1)) if np.count_nonzero(~np.isnan(v)) > 1 else np.nan,
}


def aggregate(labels: np.ndarray, values: Optional[np.ndarray], how: str = "sum") -> tuple[list, np.ndarray]:
    """Group ``values`` by ``labels``. ``values=None`` counts rows. Fast path via bincount."""
    codes, names = factorize(labels)
    ok = codes >= 0
    k = len(names)
    if values is None or how == "count":
        return names, np.bincount(codes[ok], minlength=k).astype(np.float64)
    v = as_float(values, "num")
    good = ok & ~np.isnan(v)
    if how == "sum":
        return names, np.bincount(codes[good], weights=v[good], minlength=k)
    if how == "mean":
        s = np.bincount(codes[good], weights=v[good], minlength=k)
        c = np.bincount(codes[good], minlength=k)
        with np.errstate(invalid="ignore", divide="ignore"):
            return names, s / c
    if how == "std":           # two bincount passes (centred), no sorting
        c = np.bincount(codes[good], minlength=k).astype(np.float64)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.bincount(codes[good], weights=v[good], minlength=k) / c
            dev = v[good] - mean[codes[good]]
            ss = np.bincount(codes[good], weights=dev * dev, minlength=k)
            return names, np.where(c > 1, np.sqrt(ss / (c - 1)), np.nan)
    if how not in _AGG:
        raise DataError(f"Unknown aggregation {how!r}. Use one of: {', '.join(_AGG)}.")
    order = np.argsort(codes[good], kind="stable")
    cs = codes[good][order]
    vs = v[good][order]
    bounds = np.searchsorted(cs, np.arange(k + 1))
    return names, np.array([_AGG[how](vs[bounds[i]:bounds[i + 1]]) if bounds[i + 1] > bounds[i] else np.nan
                            for i in range(k)])


# --------------------------------------------------------------------------- intervals

def interval_spec(spec, prefix: str = "") -> dict:
    """Error/band input -> extra columns. A tuple means (lower, upper); anything else is a ± half-width."""
    if spec is None:
        return {}
    if isinstance(spec, tuple) and len(spec) == 2:
        return {prefix + "lo": spec[0], prefix + "hi": spec[1]}
    return {prefix + "err": spec}


def interval_bounds(y: np.ndarray, extra: dict, prefix: str = ""):
    """(lower, upper) arrays from a series' extras, or None."""
    if prefix + "lo" in extra:
        return extra[prefix + "lo"], extra[prefix + "hi"]
    if prefix + "err" in extra:
        e = np.abs(extra[prefix + "err"])
        return y - e, y + e
    return None


def subset(data, mask: np.ndarray):
    """Rows of a DataFrame / dict of columns / structured array where ``mask`` is True."""
    mod = type(data).__module__.split(".")[0]
    if mod == "pandas":
        return data[mask]
    if mod == "polars":
        import polars as pl
        return data.filter(pl.Series(mask))
    if isinstance(data, dict):
        return {k: (to_array(v)[mask] if np.ndim(v) else v) for k, v in data.items()}
    if isinstance(data, np.ndarray):
        return data[mask]
    raise DataError(f"Can't split {type(data).__name__} into facets; use a DataFrame or a dict of columns.")


# --------------------------------------------------------------------------- out-of-core input

class Chunks:
    """Data read piece by piece, for inputs larger than memory.

        lv.histogram(lv.Chunks(lambda: pq.ParquetFile("big.parquet").iter_batches(columns=["v"])), x="v")
        lv.line(lv.Chunks(my_reader), x="t", y="value")

    ``source`` is a function returning a fresh iterable of chunks (it's called
    once per pass; most charts need two passes), or a list of chunks. A chunk
    can be a NumPy array (one column), a dict of arrays, a pandas/polars
    DataFrame or a pyarrow RecordBatch/Table.
    """

    def __init__(self, source):
        if not callable(source) and not isinstance(source, (list, tuple)):
            raise TypeError("Chunks(source): pass a function returning an iterable of chunks, or a list of chunks.")
        self.source = source

    def __iter__(self):
        it = self.source() if callable(self.source) else self.source
        for chunk in it:
            yield chunk

    def columns(self, *names):
        """Yield one tuple of float arrays per chunk for the requested columns (None = the chunk itself)."""
        for chunk in self:
            out = []
            for name in names:
                out.append(_chunk_column(chunk, name))
            yield tuple(out)

    def __repr__(self) -> str:
        return "<lineova.Chunks>"


def _chunk_column(chunk, name) -> np.ndarray:
    if name is None:
        if hasattr(chunk, "num_columns") and getattr(chunk, "num_columns", 0) == 1:   # pyarrow, one column
            chunk = chunk.column(0)
        a = np.asarray(to_array(chunk))
        if a.ndim != 1:
            raise DataError("A chunk with several columns needs a column name (x= / y=).")
        return as_float(a, value_kind(a) if len(a) else "num")
    if hasattr(chunk, "column") and hasattr(chunk, "schema"):            # pyarrow RecordBatch / Table
        a = np.asarray(chunk.column(name).to_numpy(zero_copy_only=False))
    else:
        a = to_array(get_column(chunk, name))
    return as_float(a, value_kind(a) if len(a) else "num")
