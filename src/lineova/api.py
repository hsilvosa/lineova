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
    from .marks import layer_class
    return layer_class(method)


def _check_options(method: str, layer_opts: dict) -> None:
    """Friendly error for typos, with a suggestion drawn from every valid option."""
    import difflib
    import inspect
    cls = _layer_class(method)
    params = set()
    for klass in cls.__mro__:
        if "__init__" in vars(klass):
            params |= {p for p in inspect.signature(klass.__init__).parameters if p not in ("self", "kw", "data")}
    if method == "stat":
        params.add("value")
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
    return _make("network", data, {}, options)


def violin(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart:
    """Violin plot: the full distribution per group, with quartiles and median inside."""
    return _make("violin", data, {"x": x, "y": y}, options)


def ridgeline(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart:
    """Ridgeline (joyplot): one density curve per group, stacked and slightly overlapping."""
    return _make("ridgeline", data, {"x": x, "y": y}, options)


def pie(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart:
    """Pie or donut. ``donut=True/False``; more than 6 slices fold into "Other" automatically."""
    return _make("pie", data, {"x": x, "y": y}, options)


def donut(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart:
    """Donut chart (a pie with a hole showing the total)."""
    options.setdefault("donut", True)
    return _make("pie", data, {"x": x, "y": y}, options)


def dumbbell(data: Any = None, x: Any = None, y: Any = None, color: Any = None, **options) -> Chart:
    """Two values per row joined by a line: ``dumbbell({"A": (3, 5)})`` or
    ``dumbbell(df, y="country", x=("2019", "2024"))``."""
    return _make("dumbbell", data, {"x": x, "y": y, "color": color}, options)


def slope(data: Any = None, x: Any = None, y: Any = None, color: Any = None, **options) -> Chart:
    """Slope chart: each item's value before and after, as a line between two axes."""
    return _make("slope", data, {"x": x, "y": y, "color": color}, options)


def waterfall(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart:
    """Waterfall (bridge): ``waterfall({"Sales": 120, "Costs": -80}, start=("2023", 400))``."""
    return _make("waterfall", data, {"x": x, "y": y}, options)


def candlestick(data: Any = None, x: Any = None, **options) -> Chart:
    """Candlestick/OHLC from a DataFrame with open/high/low/close columns (names detected)."""
    return _make("candlestick", data, {"x": x}, options)


def treemap(data: Any = None, **options) -> Chart:
    """Treemap: ``treemap({"A": 10, "B": 4})``, nested dicts of any depth, or
    ``treemap(df, path=["region", "country", "city"], value="pop")``. ``depth=`` limits the levels drawn."""
    return _make("treemap", data, {}, options)


def sunburst(data: Any = None, **options) -> Chart:
    """Sunburst: a hierarchy as rings, the angle proportional to value.

    ``data`` is nested dicts of any depth ({"Europe": {"Spain": {"Madrid": 7}}}) or a DataFrame with
    ``path=["region", "country", "city"]`` and ``value=``. Options: ``depth=`` (rings to show),
    ``labels=``, ``format=``, ``center=`` (text in the middle; the total by default).
    """
    return _make("sunburst", data, {}, options)


def sankey(data: Any = None, **options) -> Chart:
    """Sankey flow diagram from (source, target, value) rows or an edge DataFrame."""
    return _make("sankey", data, {}, options)


def radar(data: Any = None, **options) -> Chart:
    """Radar chart: ``radar({"Model A": {"Speed": 7, "Cost": 4, ...}, "Model B": {...}})``."""
    return _make("radar", data, {}, options)


def density(data: Any = None, x: Any = None, y: Any = None, color: Any = None, **options) -> Chart:
    """2-D density with contour lines (for very many points, or to compare groups' shapes)."""
    return _make("density", data, {"x": x, "y": y, "color": color}, options)


def hexbin(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart:
    """Hexagonal binning of a point cloud: how many points (or the mean of ``value``) fall in each hexagon.

    Works for millions of rows and for ``lv.Chunks``. Options: ``value=`` (column to aggregate),
    ``agg="count" | "sum" | "mean" | "max" | "min"``, ``gridsize=`` (hexagons across), ``mincount=1``,
    ``log="auto"`` (log colour scale for skewed counts), ``cmap=`` (colour stops), ``label=``.
    """
    return _make("hexbin", data, {"x": x, "y": y}, options)


def map(data: Any = None, geo: Any = None, **options) -> Chart:  # noqa: A001 - lv.map reads naturally
    """Maps from GeoJSON and/or points.

    * Choropleth: ``lv.map(values, geo="regions.geojson", key="name")`` where ``values`` is
      {region: number}, a Series, or a DataFrame with ``id=`` and ``value=`` columns;
      or ``lv.map(geojson, value="population")`` to colour by a feature property.
    * Points: ``lv.map(df, lon="lon", lat="lat", size="mag", color="depth")``, optionally over
      ``geo=`` as a basemap. Above 50,000 points they are drawn as a density image.

    Options: ``projection="auto" | "equirectangular" | "mercator"``, ``cmap=``, ``vmin=``, ``vmax=``,
    ``labels=``, ``format=``, ``graticule=``, ``label=`` (colour-bar title).
    """
    return _make("map", data, {"geo": geo}, options)


def tilemap(data: Any = None, **options) -> Chart:
    """Tile map: one equal square per region, placed roughly as on the map, so every region is
    equally visible. ``lv.tilemap({"M": 6.8, "B": 5.7}, layout="es-provinces")``.

    Built-in layouts: ``"es-provinces"`` (52 Spanish provinces; plate codes, INE numbers or names)
    and ``"es-regions"`` (19 autonomous communities; ISO codes or names). A custom layout is
    ``{code: (column, row, name)}``. Options: ``id=``/``value=`` for DataFrames, ``cmap=``,
    ``format=``, ``labels=``, ``names=`` (full names instead of codes on large tiles).
    """
    return _make("tilemap", data, {}, options)


def timeline(data: Any = None, **options) -> Chart:
    """Timeline / Gantt: rows of (task, start, end); ``color=`` groups, ``progress=`` shades done work."""
    return _make("timeline", data, {}, options)


def calendar(data: Any = None, x: Any = None, y: Any = None, **options) -> Chart:
    """Calendar heatmap: one cell per day, weeks as columns (GitHub-style)."""
    return _make("calendar", data, {"x": x, "y": y}, options)


def sparkline(data: Any = None, x: Any = None, **options) -> Chart:
    """Word-sized line chart with no axes, for tables and dashboards."""
    return _make("sparkline", data, {"x": x}, options)


def stat(value: Any = None, **options) -> Chart:
    """Stat tile: one big number with a label, an optional change (``delta=``) and a sparkline (``spark=``)."""
    return _make("stat", value, {}, options)
