"""One-call chart functions. Each returns a ``Chart`` you can keep customising.

    lv.line(df, x="date", y="sales").save("sales.png")
    lv.bar({"A": 3, "B": 5}, theme="fjord", title="Votes")
"""

from __future__ import annotations

from typing import Any

from .chart import _AXIS_KEYS, _CHART_KEYS, SIZES, Chart


def _split(options: dict) -> tuple[dict, dict]:
    chart, layer = {}, {}
    for k, v in options.items():
        if k == "size" and not _is_size_preset(v):
            layer[k] = v              # e.g. scatter(size=column): bubble size, not figure size
        elif k in _CHART_KEYS or (k[:2] in ("x_", "y_") and k[2:] in _AXIS_KEYS):
            chart[k] = v
        else:
            layer[k] = v
    return chart, layer


def _is_size_preset(v) -> bool:
    if isinstance(v, str):
        return v in SIZES
    return isinstance(v, tuple) and len(v) == 2 and all(isinstance(t, (int, float)) for t in v)


def _make(method: str, data, args: dict, options: dict) -> Chart:
    chart_opts, layer_opts = _split(options)
    chart = Chart(data, **chart_opts)
    _check_options(method, layer_opts)
    getattr(chart, method)(None, **args, **layer_opts)
    return chart


def _layer_class(method: str):
    from .marks import bar, box, heatmap, histogram, line, network, scatter
    return {"line": line.LineLayer, "area": line.AreaLayer, "scatter": scatter.ScatterLayer,
            "bar": bar.BarLayer, "histogram": histogram.HistogramLayer, "heatmap": heatmap.HeatmapLayer,
            "box": box.BoxLayer, "network": network.NetworkLayer}[method]


def _check_options(method: str, layer_opts: dict) -> None:
    """Friendly error for typos, with a suggestion drawn from every valid option."""
    import difflib
    import inspect
    cls = _layer_class(method)
    params = set()
    for klass in cls.__mro__:
        if "__init__" in vars(klass):
            params |= {p for p in inspect.signature(klass.__init__).parameters if p not in ("self", "kw", "data")}
    for key in layer_opts:
        if key not in params:
            valid = sorted(params | _CHART_KEYS | {f"{a}_{k}" for a in "xy" for k in _AXIS_KEYS})
            close = difflib.get_close_matches(key, valid, n=1)
            hint = f" Did you mean {close[0]!r}?" if close else ""
            raise TypeError(f"{method}() got an unknown option {key!r}.{hint}")


def line(data: Any = None, x: Any = None, y: Any = None, color: Any = "auto", **options) -> Chart:
    """Line chart. ``data`` can be a list, array, dict of series, or a DataFrame.

    Useful options: ``title``, ``subtitle``, ``theme`` (folio | ledger | instrument | fjord),
    ``highlight``, ``legend``, ``x_label``/``y_label``, ``x_range``/``y_range``,
    ``x_scale="log"``, ``curve="smooth"``, ``markers=True``.
    """
    return _make("line", data, {"x": x, "y": y, "color": color}, options)


def area(data: Any = None, x: Any = None, y: Any = None, color: Any = "auto", **options) -> Chart:
    """Area chart. Several series stack; ``normalize=True`` shows each as a share of 100%."""
    return _make("area", data, {"x": x, "y": y, "color": color}, options)


def scatter(data: Any = None, x: Any = None, y: Any = None, color: Any = "auto", **options) -> Chart:
    """Scatter/bubble plot. ``size=`` maps a column to bubble area, ``fit=True`` adds a trend line.

    Above 50,000 points it switches to a density image automatically (``render="vector"`` to force).
    """
    return _make("scatter", data, {"x": x, "y": y, "color": color}, options)


def bar(data: Any = None, x: Any = None, y: Any = None, color: Any = None, **options) -> Chart:
    """Bar chart from ``{label: value}``, a Series, raw labels (counted) or a DataFrame.

    ``color=`` groups bars, ``stack=True`` stacks them, ``normalize=True`` shows 100% stacks,
    ``orientation="h"`` forces horizontal, ``reference="mean"`` adds a reference line.
    """
    return _make("bar", data, {"x": x, "y": y, "color": color}, options)


def histogram(data: Any = None, x: Any = None, color: Any = None, **options) -> Chart:
    """Distribution of values with automatic round-numbered bins. ``bins=`` to override."""
    return _make("histogram", data, {"x": x, "color": color}, options)


def heatmap(data: Any = None, x: Any = None, y: Any = None, value: Any = None, **options) -> Chart:
    """Heatmap from a 2-D array, a DataFrame (index x columns), or long data (x, y, value columns)."""
    return _make("heatmap", data, {"x": x, "y": y, "value": value}, options)


def box(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart:
    """Box plot per group: ``{"A": values, "B": values}`` or ``box(df, x="group", y="value")``."""
    return _make("box", data, {"x": x, "y": y}, options)


def network(data: Any = None, **options) -> Chart:
    """Node-link diagram from a ``Graph``, an edge list, an edge DataFrame or a networkx graph.

    ``path=("A", "Z")`` highlights the shortest path; ``groups="community"`` colours clusters;
    ``layout="circular" | "layered" | "force"``.
    """
    chart_opts, layer_opts = _split(options)
    chart = Chart(data, **chart_opts)
    _check_options("network", layer_opts)
    chart.network(None, **layer_opts)
    return chart
