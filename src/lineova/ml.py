"""Model-evaluation and distribution charts built from the basic layers.

    lv.roc(y_true, {"logreg": p1, "forest": p2})
    lv.pr(y_true, scores)
    lv.calibration(y_true, probabilities)
    lv.confusion_matrix(y_true, y_pred, normalize="true")
    lv.ecdf({"A": a, "B": b})
    lv.qq(residuals)
    lv.correlation(df)          # clustered correlation matrix

Every function returns a ``Chart``, so ``.title()``, ``.save()`` and the usual options work on it.
"""

from __future__ import annotations

from statistics import NormalDist
from typing import Any

import numpy as np

from . import themes
from ._data import DataError, as_float, columns_of, get_column, is_frame, to_array, value_kind
from .chart import Chart

MAX_POINTS = 2000
_LINE = {"values": False}      # no end-of-line value labels on curves


# ---------------------------------------------------------------- helpers

def _chart(options: dict, **defaults) -> tuple[Chart, dict, str]:
    from .api import _split
    chart_opts, layer_opts = _split(options)
    for k, v in defaults.items():
        chart_opts.setdefault(k, v)
    chart = Chart(None, **chart_opts)
    return chart, layer_opts, str(chart._opts.get("theme") or themes.DEFAULT)


def _muted(theme_name: str) -> str:
    return themes.get(theme_name).muted


def _mute(chart: Chart, theme_name: str, names: list) -> None:
    """Draw reference lines in the theme's muted colour (unless the caller chose a palette)."""
    if chart._opts["palette"] == "auto":
        chart.palette({n: _muted(theme_name) for n in names})


def _named(data, what: str) -> dict:
    """One array, a dict of arrays or a DataFrame (every column) as {name: float array}."""
    if isinstance(data, dict):
        return {str(k): _num(v, what) for k, v in data.items()}
    if is_frame(data) and not isinstance(data, (list, tuple, np.ndarray)):
        return {str(c): _num(get_column(data, c), what) for c in columns_of(data)}
    return {"": _num(data, what)}


def _num(v, what: str) -> np.ndarray:
    a = to_array(v)
    if value_kind(a) == "cat":
        raise DataError(f"{what} needs numbers.")
    a = as_float(a, value_kind(a))
    return a[np.isfinite(a)]


def _binary(y_true) -> np.ndarray:
    y = np.asarray(to_array(y_true))
    vals = np.unique(y)
    if len(vals) != 2:
        raise DataError(f"y_true must hold exactly two classes; found {len(vals)}.")
    return (y == vals[1]).astype(np.int8)


def _scores(y: np.ndarray, scores) -> dict:
    out = _named(scores, "scores")
    for k, s in out.items():
        if len(s) != len(y):
            raise DataError(f"scores{' ' + repr(k) if k else ''} has {len(s)} values; y_true has {len(y)}.")
    return out


def _thin(*arrays, n: int = MAX_POINTS):
    m = len(arrays[0])
    if m <= n:
        return arrays
    idx = np.unique(np.linspace(0, m - 1, n).astype(np.int64))
    return tuple(a[idx] for a in arrays)


def _curve_counts(y: np.ndarray, s: np.ndarray):
    """True and false positives at every distinct threshold, scores high to low."""
    order = np.argsort(-s, kind="stable")
    ys, ss = y[order], s[order]
    tps = np.cumsum(ys)
    fps = np.cumsum(1 - ys)
    last = np.r_[np.flatnonzero(np.diff(ss)), len(ss) - 1]      # end of each run of equal scores
    return tps[last].astype(float), fps[last].astype(float)


# ---------------------------------------------------------------- ROC and precision-recall

def roc(y_true: Any, scores: Any, **options) -> Chart:
    """ROC curve with the AUC in the legend. ``scores`` is one array or ``{model: scores}``."""
    y = _binary(y_true)
    pos, neg = float(y.sum()), float((1 - y).sum())
    chart, layer_opts, theme = _chart(options, width=520, height=520, legend="bottom")
    chart.x_axis(label="False positive rate", range=(0, 1))
    chart.y_axis(label="True positive rate", range=(0, 1))
    for name, s in _scores(y, scores).items():
        tp, fp = _curve_counts(y, s)
        fpr, tpr = np.r_[0.0, fp / neg], np.r_[0.0, tp / pos]
        auc = float(np.sum(np.diff(fpr) * (tpr[1:] + tpr[:-1]) / 2))
        fpr, tpr = _thin(fpr, tpr)
        label = f"{name} (AUC {auc:.3f})" if name else f"AUC {auc:.3f}"
        chart.line(None, fpr, tpr, label=label, curve="linear", **{**_LINE, **layer_opts})
    chart.line(None, np.array([0.0, 1.0]), np.array([0.0, 1.0]), label="Chance", dash=(4, 3), curve="linear", **_LINE)
    _mute(chart, theme, ["Chance"])
    return chart


def pr(y_true: Any, scores: Any, **options) -> Chart:
    """Precision-recall curve with the average precision (AP) in the legend; the baseline is the positive rate."""
    y = _binary(y_true)
    pos = float(y.sum())
    chart, layer_opts, theme = _chart(options, width=520, height=520, legend="bottom")
    chart.x_axis(label="Recall", range=(0, 1))
    chart.y_axis(label="Precision", range=(0, 1.02))
    for name, s in _scores(y, scores).items():
        tp, fp = _curve_counts(y, s)
        recall, precision = tp / pos, tp / (tp + fp)
        ap = float(np.sum(np.diff(np.r_[0.0, recall]) * precision))
        rr, pp = _thin(np.r_[0.0, recall], np.r_[precision[0], precision])
        label = f"{name} (AP {ap:.3f})" if name else f"AP {ap:.3f}"
        chart.line(None, rr, pp, label=label, curve="linear", **{**_LINE, **layer_opts})
    rate = pos / len(y)
    chart.line(None, np.array([0.0, 1.0]), np.array([rate, rate]), label=f"No skill ({rate:.2f})", dash=(4, 3),
               curve="linear", **_LINE)
    _mute(chart, theme, [f"No skill ({rate:.2f})"])
    return chart


def calibration(y_true: Any, probabilities: Any, bins: int = 10, strategy: str = "uniform", **options) -> Chart:
    """Reliability diagram: mean predicted probability against the observed rate, per bin; Brier score in the legend.

    ``strategy="uniform"`` cuts [0, 1] in equal bins, ``"quantile"`` gives every bin the same number of rows.
    """
    y = _binary(y_true)
    if strategy not in ("uniform", "quantile"):
        raise DataError("strategy must be 'uniform' or 'quantile'.")
    chart, layer_opts, theme = _chart(options, width=520, height=520, legend="bottom")
    chart.x_axis(label="Mean predicted probability", range=(0, 1))
    chart.y_axis(label="Observed rate", range=(0, 1))
    for name, p in _scores(y, probabilities).items():
        if p.min() < 0 or p.max() > 1:
            raise DataError("Probabilities must lie in [0, 1].")
        edges = (np.linspace(0, 1, bins + 1) if strategy == "uniform"
                 else np.unique(np.quantile(p, np.linspace(0, 1, bins + 1))))
        idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, len(edges) - 2)
        count = np.bincount(idx, minlength=len(edges) - 1)
        ok = count > 0
        mean_p = np.bincount(idx, p, len(edges) - 1)[ok] / count[ok]
        rate = np.bincount(idx, y, len(edges) - 1)[ok] / count[ok]
        brier = float(np.mean((p - y) ** 2))
        label = f"{name} (Brier {brier:.3f})" if name else f"Brier {brier:.3f}"
        chart.line(None, mean_p, rate, label=label, markers=True, curve="linear", **{**_LINE, **layer_opts})
    chart.line(None, np.array([0.0, 1.0]), np.array([0.0, 1.0]), label="Perfectly calibrated", dash=(4, 3),
               curve="linear", **_LINE)
    _mute(chart, theme, ["Perfectly calibrated"])
    return chart


def confusion_matrix(y_true: Any, y_pred: Any, labels=None, normalize=None, **options) -> Chart:
    """Confusion matrix as an annotated heatmap: rows are the true class, columns the prediction.

    ``normalize="true"`` shows each row as shares of the true class (recall), ``"pred"`` each column
    (precision), ``"all"`` shares of the total; ``None`` shows counts.
    """
    t = np.asarray(to_array(y_true))
    p = np.asarray(to_array(y_pred))
    if len(t) != len(p):
        raise DataError(f"y_true has {len(t)} values and y_pred has {len(p)}.")
    names = list(labels) if labels is not None else sorted(set(t.tolist()) | set(p.tolist()), key=str)
    pos = {v: i for i, v in enumerate(names)}
    mat = np.zeros((len(names), len(names)))
    for a, b in zip(t.tolist(), p.tolist()):
        if a in pos and b in pos:
            mat[pos[a], pos[b]] += 1
    if normalize not in (None, "true", "pred", "all"):
        raise DataError("normalize must be None, 'true', 'pred' or 'all'.")
    shown = mat
    if normalize == "true":
        shown = mat / np.where(mat.sum(1, keepdims=True) == 0, 1, mat.sum(1, keepdims=True))
    elif normalize == "pred":
        shown = mat / np.where(mat.sum(0, keepdims=True) == 0, 1, mat.sum(0, keepdims=True))
    elif normalize == "all":
        shown = mat / (mat.sum() or 1)
    from .api import _split
    chart_opts, layer_opts = _split(options)
    chart_opts.setdefault("x_label", "Predicted")
    chart_opts.setdefault("y_label", "True")
    layer_opts.setdefault("format", "{:.0%}" if normalize else "{:,.0f}")
    layer_opts.setdefault("label", "Share" if normalize else "Count")
    layer_opts.setdefault("cmap", "sequential")
    chart = Chart(None, **chart_opts)
    labels_s = [str(v) for v in names]
    chart.heatmap(shown, labels_s, labels_s, **layer_opts)
    return chart


# ---------------------------------------------------------------- distributions

def ecdf(data: Any, complementary: bool = False, **options) -> Chart:
    """Empirical cumulative distribution: the share of values at or below x. One array, ``{name: values}`` or
    a DataFrame (one line per column). ``complementary=True`` shows the share above x (survival)."""
    chart, layer_opts, _ = _chart(options)
    chart.x_axis(label=None)
    chart.y_axis(label="Share of values at or below x" if not complementary else "Share of values above x",
                 range=(0, 1), format="{:.0%}")
    groups = _named(data, "ecdf")
    for name, v in groups.items():
        if not len(v):
            raise DataError(f"{name or 'data'} has no finite values.")
        v = np.sort(v)
        n = len(v)
        if n <= MAX_POINTS:
            xs = np.repeat(v, 2)
            ys = np.empty(2 * n)
            ys[0::2] = np.arange(n) / n
            ys[1::2] = np.arange(1, n + 1) / n
        else:
            ys = np.linspace(0, 1, MAX_POINTS)
            xs = np.quantile(v, ys)
        if complementary:
            ys = 1 - ys
        chart.line(None, xs, ys, label=name or "data", curve="linear", **{**_LINE, **layer_opts})
    return chart


def _ppf(dist):
    if callable(dist):
        return dist
    if dist == "normal":
        nd = NormalDist()
        return lambda p: np.array([nd.inv_cdf(float(q)) for q in p])
    if dist == "uniform":
        return lambda p: np.asarray(p, float)
    if dist == "exponential":
        return lambda p: -np.log1p(-np.asarray(p, float))
    raise DataError("dist must be 'normal', 'uniform', 'exponential' or a function p -> quantile.")


def qq(data: Any, dist: Any = "normal", **options) -> Chart:
    """Quantile-quantile plot against a theoretical distribution (``"normal"``, ``"uniform"``,
    ``"exponential"`` or a quantile function). Points on the reference line (through the quartiles) mean a good fit."""
    ppf = _ppf(dist)
    chart, layer_opts, theme = _chart(options, width=520, height=520)
    chart.x_axis(label=f"Theoretical quantiles ({dist if isinstance(dist, str) else 'custom'})")
    chart.y_axis(label="Sample quantiles")
    lo = hi = None
    refs = []
    for name, v in _named(data, "qq").items():
        v = np.sort(v)
        n = len(v)
        if n < 3:
            raise DataError("A Q-Q plot needs at least 3 values.")
        p = (np.arange(1, n + 1) - 0.5) / n
        p, v = _thin(p, v)
        th = ppf(p)
        chart.scatter(None, th, v, label=name or "sample", **{"marker": "bubble", **layer_opts})
        q1, q3 = np.quantile(v, [0.25, 0.75])
        t1, t3 = ppf(np.array([0.25, 0.75]))
        slope = (q3 - q1) / (t3 - t1) if t3 != t1 else 1.0
        icpt = q1 - slope * t1
        lo = th[0] if lo is None else min(lo, th[0])
        hi = th[-1] if hi is None else max(hi, th[-1])
        ref = f"Reference{' ' + name if name else ''}"
        refs.append(ref)
        chart.line(None, np.array([lo, hi]), icpt + slope * np.array([lo, hi]), label=ref, dash=(4, 3), curve="linear", **_LINE)
    _mute(chart, theme, refs)
    return chart


# ---------------------------------------------------------------- correlation

def _cluster_order(dist: np.ndarray) -> list[int]:
    """Leaf order of an average-linkage tree: similar variables end up next to each other."""
    n = len(dist)
    if n <= 2:
        return list(range(n))
    clusters = {i: [i] for i in range(n)}
    d = {(i, j): float(dist[i, j]) for i in range(n) for j in range(i + 1, n)}
    nxt = n
    while len(clusters) > 1:
        (a, b), _ = min(d.items(), key=lambda kv: kv[1])
        ca, cb = clusters.pop(a), clusters.pop(b)
        for k in list(clusters):
            dak = d.pop((min(a, k), max(a, k)))
            dbk = d.pop((min(b, k), max(b, k)))
            d[(k, nxt)] = (dak * len(ca) + dbk * len(cb)) / (len(ca) + len(cb))
        d.pop((a, b), None)
        clusters[nxt] = ca + cb
        nxt += 1
    return next(iter(clusters.values()))


def correlation(data: Any, method: str = "pearson", cluster: bool = True, **options) -> Chart:
    """Correlation matrix of the numeric columns as a diverging heatmap, from -1 to 1.

    With ``cluster=True`` (default) the variables are reordered by average-linkage clustering of
    ``1 - |r|``, so groups of related variables form blocks. ``method`` is ``"pearson"`` or ``"spearman"``.
    """
    if method not in ("pearson", "spearman"):
        raise DataError("method must be 'pearson' or 'spearman'.")
    if isinstance(data, np.ndarray) and data.ndim == 2:
        cols = {f"x{i + 1}": data[:, i].astype(float) for i in range(data.shape[1])}
    elif isinstance(data, dict):
        cols = {str(k): to_array(v) for k, v in data.items()}
    elif is_frame(data):
        cols = {str(c): to_array(get_column(data, c)) for c in columns_of(data)}
    else:
        raise DataError("Pass a DataFrame, a dict of columns or a 2-D array.")
    cols = {k: as_float(v, value_kind(v)) for k, v in cols.items() if value_kind(v) in ("num", "time")}
    if len(cols) < 2:
        raise DataError("A correlation matrix needs at least 2 numeric columns.")
    names = list(cols)
    X = np.column_stack([cols[k] for k in names])
    ok = np.isfinite(X).all(axis=1)          # complete rows only, so every pair uses the same data
    X = X[ok]
    if len(X) < 3:
        raise DataError("Fewer than 3 complete rows.")
    if method == "spearman":
        X = np.argsort(np.argsort(X, axis=0, kind="stable"), axis=0).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.corrcoef(X, rowvar=False)
    r = np.nan_to_num(r)
    if cluster:
        order = _cluster_order(1 - np.abs(r))
        r = r[np.ix_(order, order)]
        names = [names[i] for i in order]
    from .api import _split
    chart_opts, layer_opts = _split(options)
    layer_opts.setdefault("cmap", "diverging")
    layer_opts.setdefault("vmin", -1.0)
    layer_opts.setdefault("vmax", 1.0)
    layer_opts.setdefault("format", "{:.2f}")
    layer_opts.setdefault("label", f"{method.capitalize()} r")
    chart = Chart(None, **chart_opts)
    chart.heatmap(r, names, names, **layer_opts)
    return chart
