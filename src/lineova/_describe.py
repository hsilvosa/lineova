"""Accessibility: text descriptions (alt text) and data tables for charts.

Every chart gets a plain-language description, written into the SVG's ``<desc>``
and available as ``chart.describe()``, and a data table (``chart.table()``) of
what is plotted, so a reader never depends on colour or vision alone.
"""

from __future__ import annotations

import csv
import io
from html import escape

import numpy as np

from ._text import format_value

MAX_ROWS = 5000


def _fmt_x(v, kind: str) -> str:
    if kind == "time":
        try:
            d = np.datetime64(int(round(float(v))), "ns")
            day = d.astype("datetime64[D]")
            return str(day) if d == day.astype("datetime64[ns]") else str(d.astype("datetime64[s]")).replace("T", " ")
        except (ValueError, OverflowError):
            return str(v)
    if isinstance(v, (float, np.floating)):
        return format_value(v)
    return str(v)


def _names(names, limit=5) -> str:
    names = [str(n) for n in names]
    if len(names) <= limit:
        return ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1] if names else ""
    return ", ".join(names[:limit]) + f" and {len(names) - limit} more"


def _range(a) -> tuple[float, float]:
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    return (float(a.min()), float(a.max())) if len(a) else (float("nan"), float("nan"))


# ---------------------------------------------------------------- per layer

def describe_layer(layer) -> str:
    kind = type(layer).__name__.replace("Layer", "").lower()
    fn = _DESCRIBE.get(kind)
    try:
        return fn(layer) if fn else _generic(layer, kind)
    except Exception:   # a description must never break rendering
        return _generic(layer, kind)


def _generic(layer, kind) -> str:
    keys = layer.keys() if hasattr(layer, "keys") else []
    label = {"stat": "Stat tile", "sparkline": "Sparkline"}.get(kind, f"{kind.capitalize()} chart")
    return f"{label}" + (f" of {_names(keys)}." if keys else ".")


def _line(layer) -> str:
    xy = layer.xy
    kind = "Area chart" if type(layer).__name__ == "AreaLayer" else "Line chart"
    ser = xy.series
    xs = np.concatenate([np.asarray(s.x) for s in ser]) if xy.x_kind != "cat" else None
    head = f"{kind} of {len(ser)} series ({_names([s.name for s in ser])})" if len(ser) > 1 else \
        f"{kind} of {ser[0].name}"
    if xs is not None and len(xs):
        a, b = _range(xs)
        head += f", {xy.x_label or 'x'} from {_fmt_x(a, xy.x_kind)} to {_fmt_x(b, xy.x_kind)}"
    parts = [head + "."]
    for s in ser[:6]:
        y = np.asarray(s.y, float)
        fin = np.flatnonzero(np.isfinite(y))
        if not len(fin):
            continue
        first, last = y[fin[0]], y[fin[-1]]
        lo, hi = _range(y)
        trend = ""
        if first > 0 and last > 0:
            ch = (last - first) / first
            trend = f", {'up' if ch > 0 else 'down'} {abs(ch):.0%} from the start" if abs(ch) >= 0.005 else ", flat overall"
        elif np.isfinite(first) and last != first:
            trend = f", {'up' if last > first else 'down'} {format_value(abs(last - first))} from the start"
        parts.append(f"{s.name}: from {format_value(lo)} to {format_value(hi)}, last {format_value(last)}{trend}.")
    return " ".join(parts)


def _bar(layer) -> str:
    cats, names, vals = layer.cats, layer.names, np.asarray(layer.values, float)
    head = f"Bar chart of {_names(names)} across {len(cats)} categories" if len(names) > 1 else \
        f"Bar chart of {names[0]} for {len(cats)} categories"
    if len(names) == 1 and len(cats):
        v = vals[0]
        ok = np.isfinite(v)
        if ok.any():
            i_hi, i_lo = int(np.nanargmax(v)), int(np.nanargmin(v))
            return (f"{head}. Highest: {cats[i_hi]} ({format_value(v[i_hi])}); "
                    f"lowest: {cats[i_lo]} ({format_value(v[i_lo])}).")
    tot = np.nansum(vals, axis=0)
    if len(cats) and np.isfinite(tot).any():
        i = int(np.nanargmax(tot))
        return f"{head}. Largest total: {cats[i]} ({format_value(tot[i])})."
    return head + "."


def _scatter(layer) -> str:
    groups = layer.groups
    xs = np.concatenate([np.asarray(g.x, float) for g in groups])
    ys = np.concatenate([np.asarray(g.y, float) for g in groups])
    n = getattr(layer, "n", len(xs))
    head = f"Scatter plot of {n:,} points" + (f" in {len(groups)} groups ({_names([g.name for g in groups])})"
                                                if len(groups) > 1 else "")
    ax, bx = _range(xs)
    ay, by = _range(ys)
    xk = getattr(layer, "x_kind", "num")
    txt = (f"{head}; {layer.x_label or 'x'} from {_fmt_x(ax, xk)} to {_fmt_x(bx, xk)}, "
           f"{layer.y_label or 'y'} from {format_value(ay)} to {format_value(by)}.")
    ok = np.isfinite(xs) & np.isfinite(ys)
    if ok.sum() > 2 and "_w" not in groups[0].extra:
        r = np.corrcoef(xs[ok], ys[ok])[0, 1]
        if np.isfinite(r):
            strength = "strong" if abs(r) > 0.7 else "moderate" if abs(r) > 0.4 else "weak"
            txt += f" Correlation {r:.2f} ({strength}, {'positive' if r > 0 else 'negative'})."
    return txt


def _histogram(layer) -> str:
    e = layer.edges
    parts = [f"Histogram of {_names([g for g, _ in layer.groups])}, {len(e) - 1} bins from "
             f"{format_value(e[0])} to {format_value(e[-1])}."]
    for (name, _), c in zip(layer.groups, layer.counts):
        i = int(np.argmax(c))
        parts.append(f"{name}: most common {format_value(e[i])}–{format_value(e[i + 1])} ({format_value(c[i])}).")
    return " ".join(parts)


def _pie(layer) -> str:
    tot = float(np.sum(layer.values)) or 1.0
    items = [f"{c} {v / tot:.0%}" for c, v in zip(layer.cats, layer.values)]
    return f"{'Donut' if getattr(layer, 'is_donut', False) else 'Pie'} chart: " + ", ".join(items) + "."


def _heatmap(layer) -> str:
    m = np.asarray(layer.matrix, float)
    lo, hi = _range(m)
    return f"Heatmap of {m.shape[0]} rows by {m.shape[1]} columns, values from {format_value(lo)} to {format_value(hi)}."


def _tree(layer, kind) -> str:
    root = layer.root
    tot = root.value or 1.0
    tops = ", ".join(f"{c.name} {c.value / tot:.0%}" for c in root.children[:6])
    more = f" and {len(root.children) - 6} more" if len(root.children) > 6 else ""
    return f"{kind} of {format_value(tot)} in total, {root.height()} level(s): {tops}{more}."


def _hexbin(layer) -> str:
    return (f"Hexbin of {layer.n:,} points in {len(layer.val)} hexagons, {layer.cbar_label} from "
            f"{format_value(layer.vmin)} to {format_value(layer.vmax)}.")


_DESCRIBE = {
    "line": _line, "area": _line, "bar": _bar, "scatter": _scatter, "density": _scatter,
    "histogram": _histogram, "pie": _pie, "heatmap": _heatmap, "hexbin": _hexbin,
    "treemap": lambda l: _tree(l, "Treemap"), "sunburst": lambda l: _tree(l, "Sunburst"),
}


# ---------------------------------------------------------------- tables

class Table:
    """The data behind a chart, as rows. ``to_csv()``, ``to_html()``, ``to_pandas()``, or iterate."""

    def __init__(self, columns: list[str], rows: list[list], truncated: bool = False, name: str = "",
                 title: str = ""):
        self.columns, self.rows, self.truncated, self.name, self.title = columns, rows, truncated, name, title

    def __len__(self):
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def __repr__(self):
        return f"<Table {self.name or ''} {len(self.rows)} rows x {len(self.columns)} columns>"

    def _cell(self, v) -> str:
        if isinstance(v, (float, np.floating)):
            return "" if not np.isfinite(v) else format_value(v) if abs(v) < 1e15 else str(v)
        return str(v)

    def to_csv(self, path=None) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(self.columns)
        for r in self.rows:
            w.writerow([("" if isinstance(v, float) and not np.isfinite(v) else v) for v in r])
        text = buf.getvalue()
        if path is not None:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        return text

    def to_html(self, max_rows: int = 500) -> str:
        head = "".join(f"<th scope=\"col\">{escape(str(c))}</th>" for c in self.columns)
        body = "".join("<tr>" + "".join(f"<td>{escape(self._cell(v))}</td>" for v in r) + "</tr>"
                       for r in self.rows[:max_rows])
        note = ""
        if len(self.rows) > max_rows or self.truncated:
            note = f"<caption>First {min(max_rows, len(self.rows))} rows</caption>"
        return f"<table>{note}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    _repr_html_ = to_html

    def to_pandas(self):
        import pandas as pd
        return pd.DataFrame(self.rows, columns=self.columns)


def table_layer(layer) -> Table | None:
    kind = type(layer).__name__.replace("Layer", "").lower()
    try:
        if kind in ("line", "area"):
            xy = layer.xy
            rows = []
            for s in xy.series:
                for x, y in zip(np.asarray(s.x)[:MAX_ROWS], np.asarray(s.y)[:MAX_ROWS]):
                    rows.append([s.name, _fmt_x(x, xy.x_kind), float(y)])
            return Table(["series", xy.x_label or "x", xy.y_label or "y"], rows,
                         any(len(s.x) > MAX_ROWS for s in xy.series), kind)
        if kind == "bar":
            vals = np.asarray(layer.values, float)
            rows = [[c] + [float(vals[i, j]) for i in range(len(layer.names))] for j, c in enumerate(layer.cats)]
            return Table(["category"] + [str(n) for n in layer.names], rows, name=kind)
        if kind in ("scatter", "density"):
            rows, trunc = [], False
            for g in layer.groups:
                k = min(len(g.x), MAX_ROWS)
                trunc |= len(g.x) > MAX_ROWS
                for x, y in zip(np.asarray(g.x)[:k], np.asarray(g.y)[:k]):
                    rows.append([g.name, _fmt_x(x, getattr(layer, "x_kind", "num")), float(y)])
            return Table(["group", layer.x_label or "x", layer.y_label or "y"], rows, trunc, kind)
        if kind == "histogram":
            e = layer.edges
            rows = [[float(e[i]), float(e[i + 1])] + [float(c[i]) for c in layer.counts] for i in range(len(e) - 1)]
            return Table(["from", "to"] + [str(g) for g, _ in layer.groups], rows, name=kind)
        if kind == "pie":
            tot = float(np.sum(layer.values)) or 1.0
            return Table(["label", "value", "share"],
                         [[c, float(v), float(v) / tot] for c, v in zip(layer.cats, layer.values)], name=kind)
        if kind == "heatmap":
            m = np.asarray(layer.matrix, float)
            xn = layer.xn or [str(i) for i in range(m.shape[1])]
            yn = layer.yn or [str(i) for i in range(m.shape[0])]
            return Table(["row"] + list(map(str, xn)), [[yn[i]] + [float(v) for v in m[i]] for i in range(m.shape[0])],
                         name=kind)
        if kind in ("treemap", "sunburst"):
            depth = layer.root.height()
            rows = [n.path() + [""] * (depth - len(n.path())) + [n.value] for n in layer.root.walk() if n.is_leaf]
            return Table([f"level {i + 1}" for i in range(depth)] + ["value"], rows, name=kind)
    except Exception:
        return None
    return None
