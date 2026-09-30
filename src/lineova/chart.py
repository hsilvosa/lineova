"""The Chart object: layout, axes, legends, titles and output.

Everything has an automatic default. Every default can be overridden, either
as a keyword (``lv.line(df, y_range=(0, 100))``) or with a chainable method
(``chart.y_axis(range=(0, 100))``).
"""

from __future__ import annotations

import difflib
import math
import warnings
from dataclasses import dataclass, fields, replace
from typing import Any, Optional

import numpy as np

from . import scene as S
from . import themes
from ._output import Renderable
from ._color import ramp_lut
from ._text import format_value, text_width, truncate, wrap
from .marks import layer_class
from .marks._base import Domain, DrawContext, LegendItem, Plot
from .scales import BandScale, LinearScale, LogScale, TimeScale, nice_domain

SIZES = {
    "column": (340, 250),     # one journal column (3.5 in)
    "page": (640, 400),       # full text width
    "wide": (960, 440),
    "slide": (1280, 720),
    "square": (560, 560),
    "dashboard": (480, 300),
    "a4": (760, 520),
}


@dataclass
class Axis:
    """Options for one axis. ``"auto"`` means: let the library decide."""
    label: Any = "auto"          # str | None | "auto"
    scale: str = "auto"          # auto | linear | log | time | category
    range: Any = None            # (lo, hi); either end may be None
    ticks: Any = "auto"          # auto | int (approx count) | list of values | {value: label}
    format: Any = None           # None | ',.1f' | '{:.0%}' | '%b %Y' (time) | callable
    zero: Any = "auto"           # include zero? auto | True | False
    grid: Any = "auto"           # auto | True | False
    reverse: bool = False
    visible: bool = True


_CHART_KEYS = {
    "title", "subtitle", "caption", "source", "theme", "width", "height", "size", "legend",
    "palette", "highlight", "number", "background", "notes", "facet", "facet_cols", "share",
}
_AXIS_KEYS = {f.name for f in fields(Axis)}


class Chart(Renderable):
    """A figure made of one or more layers (line, bar, scatter, ...)."""

    def __init__(self, data: Any = None, **options):
        self.data = data
        self._layers: list = []
        self._annotations: list[dict] = []
        self._opts: dict = {"theme": None, "title": None, "subtitle": None, "caption": None,
                            "source": None, "width": "auto", "height": "auto", "size": None,
                            "legend": "auto", "palette": "auto", "highlight": None, "number": None,
                            "background": None, "notes": True, "facet": None, "facet_cols": "auto",
                            "share": "both", "panel": None}
        self._x = Axis()
        self._y = Axis()
        self.set(**options)

    # ------------------------------------------------------------------ configuration

    def set(self, **options) -> Chart:
        """Set any chart option by keyword. Axis options use ``x_``/``y_`` prefixes."""
        for key, value in options.items():
            if key == "highlight" and isinstance(value, (str, int, float)):
                value = [value]
            if key == "size" and isinstance(value, tuple):
                self._opts["width"], self._opts["height"] = value
            elif key in _CHART_KEYS:
                self._opts[key] = value
            elif key[:2] in ("x_", "y_") and key[2:] in _AXIS_KEYS:
                ax = self._x if key[0] == "x" else self._y
                setattr(ax, key[2:], value)
            else:
                valid = sorted(_CHART_KEYS | {f"{a}_{k}" for a in "xy" for k in _AXIS_KEYS})
                close = difflib.get_close_matches(key, valid, n=1)
                hint = f" Did you mean {close[0]!r}?" if close else ""
                raise TypeError(f"Unknown option {key!r}.{hint}")
        return self

    def title(self, text: str, subtitle: Optional[str] = None) -> Chart:
        """Main heading, optionally with a subtitle."""
        self._opts["title"] = text
        if subtitle is not None:
            self._opts["subtitle"] = subtitle
        return self

    def subtitle(self, text: str) -> Chart:
        """Second heading line."""
        self._opts["subtitle"] = text
        return self

    def caption(self, text: str, number: Optional[int] = None) -> Chart:
        """Paragraph under the chart. ``number`` adds 'Figure N.' (Folio)."""
        self._opts["caption"] = text
        if number is not None:
            self._opts["number"] = number
        return self

    def source(self, text: str) -> Chart:
        """'Source: …' line under the chart."""
        self._opts["source"] = text
        return self

    def theme(self, theme) -> Chart:
        """Use a theme by name or a ``Theme`` object."""
        self._opts["theme"] = theme
        return self

    def size(self, width: Any = "auto", height: Any = "auto") -> Chart:
        """``size(800, 450)``, ``size(width=600)`` or a preset: ``size("column")``."""
        if isinstance(width, str) and width in SIZES:
            self._opts["size"] = width
        else:
            self._opts["width"], self._opts["height"] = width, height
        return self

    def legend(self, position: Any = "auto") -> Chart:
        """auto | top | bottom | right | direct | readout | none."""
        self._opts["legend"] = position
        return self

    def palette(self, colors: Any) -> Chart:
        """A list of colours, a {series: colour} dict, or one colour for everything."""
        self._opts["palette"] = colors
        return self

    def highlight(self, *keys) -> Chart:
        """Emphasise some series/categories/nodes; everything else is muted."""
        flat = []
        for k in keys:
            flat.extend(k if isinstance(k, (list, tuple, set)) else [k])
        self._opts["highlight"] = flat
        return self

    def x_axis(self, **options) -> Chart:
        """Set x-axis options (``label``, ``scale``, ``range``, ``ticks``, ``format``, ``zero``, ``grid``, ``reverse``, ``visible``)."""
        self._x = replace(self._x, **options)
        return self

    def y_axis(self, **options) -> Chart:
        """Set y-axis options (same names as ``x_axis``)."""
        self._y = replace(self._y, **options)
        return self

    def hline(self, y: Any, label: Optional[str] = None, *, color: Optional[str] = None, dash=(4, 3)) -> Chart:
        """Horizontal reference line, e.g. a target. ``y="mean"`` uses the data mean."""
        self._annotations.append({"kind": "hline", "at": y, "label": label, "color": color, "dash": dash})
        return self

    def vline(self, x: Any, label: Optional[str] = None, *, color: Optional[str] = None, dash=(4, 3)) -> Chart:
        """Vertical reference line; ``x="mean"`` uses the data mean."""
        self._annotations.append({"kind": "vline", "at": x, "label": label, "color": color, "dash": dash})
        return self

    def band(self, x: Any = None, y: Any = None, label: Optional[str] = None, *, color: Optional[str] = None) -> Chart:
        """Shade a range, e.g. ``band(x=("2024-06-01", "2024-08-31"), label="Summer")``."""
        self._annotations.append({"kind": "band", "x": x, "y": y, "label": label, "color": color})
        return self

    def annotate(self, x: Any, y: Any, text: str, *, dx: float = 8, dy: float = -8) -> Chart:
        """Text note pointing at a data position."""
        self._annotations.append({"kind": "text", "x": x, "y": y, "text": text, "dx": dx, "dy": dy})
        return self

    # ------------------------------------------------------------------ layers

    def _add(self, layer) -> Chart:
        self._layers.append(layer)
        return self

    def line(self, data=None, x=None, y=None, color="auto", **kw) -> Chart:
        """Add a line layer. Takes the same options as ``lv.line()``."""
        return self._add(layer_class("line")(self._d(data), x, y, color, **kw))

    def area(self, data=None, x=None, y=None, color="auto", **kw) -> Chart:
        """Add a area layer. Takes the same options as ``lv.area()``."""
        return self._add(layer_class("area")(self._d(data), x, y, color, **kw))

    def scatter(self, data=None, x=None, y=None, color="auto", **kw) -> Chart:
        """Add a scatter layer. Takes the same options as ``lv.scatter()``."""
        return self._add(layer_class("scatter")(self._d(data), x, y, color, **kw))

    def bar(self, data=None, x=None, y=None, color=None, **kw) -> Chart:
        """Add a bar layer. Takes the same options as ``lv.bar()``."""
        return self._add(layer_class("bar")(self._d(data), x, y, color, **kw))

    def histogram(self, data=None, x=None, color=None, **kw) -> Chart:
        """Add a histogram layer. Takes the same options as ``lv.histogram()``."""
        return self._add(layer_class("histogram")(self._d(data), x, color, **kw))

    def heatmap(self, data=None, x=None, y=None, value=None, **kw) -> Chart:
        """Add a heatmap layer. Takes the same options as ``lv.heatmap()``."""
        return self._add(layer_class("heatmap")(self._d(data), x, y, value, **kw))

    def box(self, data=None, x=None, y=None, **kw) -> Chart:
        """Add a box layer. Takes the same options as ``lv.box()``."""
        return self._add(layer_class("box")(self._d(data), x, y, **kw))

    def violin(self, data=None, x=None, y=None, **kw) -> Chart:
        """Add a violin layer. Takes the same options as ``lv.violin()``."""
        return self._add(layer_class("violin")(self._d(data), x, y, **kw))

    def ridgeline(self, data=None, x=None, y=None, **kw) -> Chart:
        """Add a ridgeline layer. Takes the same options as ``lv.ridgeline()``."""
        return self._add(layer_class("ridgeline")(self._d(data), x, y, **kw))

    def network(self, data=None, **kw) -> Chart:
        """Add a network layer. Takes the same options as ``lv.network()``."""
        return self._add(layer_class("network")(self._d(data), **kw))

    def pie(self, data=None, x=None, y=None, **kw) -> Chart:
        """Add a pie layer. Takes the same options as ``lv.pie()``."""
        return self._add(layer_class("pie")(self._d(data), x, y, **kw))

    def dumbbell(self, data=None, x=None, y=None, color=None, **kw) -> Chart:
        """Add a dumbbell layer. Takes the same options as ``lv.dumbbell()``."""
        return self._add(layer_class("dumbbell")(self._d(data), x, y, color, **kw))

    def slope(self, data=None, x=None, y=None, color=None, **kw) -> Chart:
        """Add a slope layer. Takes the same options as ``lv.slope()``."""
        return self._add(layer_class("slope")(self._d(data), x, y, color, **kw))

    def waterfall(self, data=None, x=None, y=None, **kw) -> Chart:
        """Add a waterfall layer. Takes the same options as ``lv.waterfall()``."""
        return self._add(layer_class("waterfall")(self._d(data), x, y, **kw))

    def candlestick(self, data=None, x=None, **kw) -> Chart:
        """Add a candlestick layer. Takes the same options as ``lv.candlestick()``."""
        return self._add(layer_class("candlestick")(self._d(data), x, **kw))

    def treemap(self, data=None, **kw) -> Chart:
        """Add a treemap layer. Takes the same options as ``lv.treemap()``."""
        return self._add(layer_class("treemap")(self._d(data), **kw))

    def sankey(self, data=None, **kw) -> Chart:
        """Add a sankey layer. Takes the same options as ``lv.sankey()``."""
        return self._add(layer_class("sankey")(self._d(data), **kw))

    def radar(self, data=None, **kw) -> Chart:
        """Add a radar layer. Takes the same options as ``lv.radar()``."""
        return self._add(layer_class("radar")(self._d(data), **kw))

    def density(self, data=None, x=None, y=None, color=None, **kw) -> Chart:
        """Add a density layer. Takes the same options as ``lv.density()``."""
        return self._add(layer_class("density")(self._d(data), x, y, color, **kw))

    def timeline(self, data=None, **kw) -> Chart:
        """Add a timeline layer. Takes the same options as ``lv.timeline()``."""
        return self._add(layer_class("timeline")(self._d(data), **kw))

    def calendar(self, data=None, x=None, y=None, **kw) -> Chart:
        """Add a calendar layer. Takes the same options as ``lv.calendar()``."""
        return self._add(layer_class("calendar")(self._d(data), x, y, **kw))

    def sparkline(self, data=None, x=None, **kw) -> Chart:
        """Add a sparkline layer. Takes the same options as ``lv.sparkline()``."""
        return self._add(layer_class("sparkline")(self._d(data), x, **kw))

    def stat(self, value=None, **kw) -> Chart:
        """Add a stat layer. Takes the same options as ``lv.stat()``."""
        return self._add(layer_class("stat")(self._d(value), **kw))

    def _d(self, data):
        return self.data if data is None else data

    def __repr__(self) -> str:
        kinds = ", ".join(type(l).__name__.replace("Layer", "").lower() for l in self._layers) or "empty"
        return f"<lineova.Chart [{kinds}] theme={themes.get(self._opts['theme']).name!r}>"

    # ------------------------------------------------------------------ build

    @property
    def resolved_theme(self):
        return themes.get(self._opts["theme"])

    def facet(self, column: Any, cols: Any = "auto", share: str = "both") -> Chart:
        """Small multiples: one panel per value of ``column``, with shared axes and one legend."""
        self._opts.update(facet=column, facet_cols=cols, share=share)
        return self

    def build(self, raster_scale: float = 2.0) -> S.Scene:
        """Lay out and draw the chart into a backend-neutral ``Scene``."""
        if self._opts.get("facet") is not None:
            from .figure import facet_grid
            return facet_grid(self).build(raster_scale)
        if not self._layers:
            if self.data is None:
                raise ValueError("The chart has no layers. Add one, e.g. Chart(df).line(x='t', y='v').")
            self.line()
        for layer in self._layers:
            layer.prepare(self)
        return self._build_prepared(raster_scale)

    def _build_prepared(self, raster_scale: float = 2.0) -> S.Scene:
        """Draw, assuming every layer's ``prepare`` has already run."""
        theme = self.resolved_theme
        if self._opts["background"]:
            theme = theme.replace(background=self._opts["background"])
        self._theme = theme
        W, H = self._resolve_size(theme)
        scene = S.Scene(W, H, theme.background, theme.font, theme.font_kind,
                        description=self._opts["title"] or "")
        keys = list(dict.fromkeys(k for layer in self._layers for k in layer.keys()))
        colors, others = self._assign_colors(theme, keys)
        highlight = set(map(str, self._opts["highlight"] or []))
        pad = theme.padding

        top = self._draw_header(scene, theme, W, pad)
        mode = self._legend_mode(theme, keys)
        dummy = DrawContext(scene, theme, Plot(0, 0, 1, 1), None, None, colors, highlight, raster_scale)
        items: list[LegendItem] = []
        if mode in ("top", "bottom", "right"):
            seen = set()
            for layer in self._layers:
                for it in layer.legend_items(dummy):
                    if it.key not in seen and it.key not in others:
                        seen.add(it.key)
                        items.append(it)
            if others:
                items.append(LegendItem("__other__", f"Other ({len(others)})", theme.muted, "square"))
        if mode == "top" and items:
            top = self._draw_legend_row(scene, theme, items, pad, top, W - 2 * pad)
        cbar = next((l.colorbar() for l in self._layers if l.colorbar()), None)
        if cbar:
            top = self._draw_colorbar(scene, theme, cbar, pad, top)
        bottom = self._draw_footer(scene, theme, W, H - pad)
        if mode == "bottom" and items:
            h = self._legend_height(theme, items, W - 2 * pad)
            self._draw_legend_row(scene, theme, items, pad, bottom - h, W - 2 * pad)
            bottom -= h + 4
        right = W - pad
        if mode == "right" and items:
            lw = min(W * 0.3, max(text_width(i.label, theme.font_size, theme.font_kind) for i in items) + 26)
            self._draw_legend_column(scene, theme, items, right - lw, top + 4, lw)
            right -= lw + 8

        region = Plot(pad, top, right - pad, bottom - top)
        if all(l.cartesian for l in self._layers):
            self._draw_cartesian(scene, theme, region, colors, highlight, raster_scale, mode)
        else:
            ctx = DrawContext(scene, theme, region, None, None, colors, highlight, raster_scale,
                              dict(self._opts, _legend_mode=mode))
            for layer in self._layers:
                layer.draw(ctx)
            scene.extend(ctx.overlay)
        return scene

    # ------------------------------------------------------------------ sizing & colour

    def _resolve_size(self, theme) -> tuple[float, float]:
        w, h = self._opts["width"], self._opts["height"]
        if self._opts["size"]:
            if self._opts["size"] not in SIZES:
                raise ValueError(f"Unknown size preset {self._opts['size']!r}. Use one of {', '.join(SIZES)}.")
            pw_, ph_ = SIZES[self._opts["size"]]
            w = pw_ if w == "auto" else w
            h = ph_ if h == "auto" else h
        base = (640, 400) if theme.caption_style == "figure" else (720, 440)
        layer_w, layer_h = next((s for s in (l.default_size(theme) for l in self._layers) if s), (None, None))
        if w == "auto":
            w = layer_w or base[0]
        if h == "auto":
            h = layer_h or round(w * base[1] / base[0])
            if self._opts["title"] and theme.caption_style != "figure":
                h += 20
        return float(w), float(h)

    def _assign_colors(self, theme, keys: list[str]) -> tuple[dict, list]:
        pal = self._opts["palette"]
        colors: dict[str, str] = {}
        others: list[str] = []
        if isinstance(pal, dict):
            colors.update({str(k): v for k, v in pal.items()})
            base = [c for c in theme.palette if c not in colors.values()]
        elif isinstance(pal, str) and pal != "auto":
            if pal in themes.names():
                base = list(themes.get(pal).palette)
            else:
                return {k: pal for k in keys}, []
        elif isinstance(pal, (list, tuple)):
            base = list(pal)
        else:
            base = list(theme.palette)
        hl = [k for k in keys if k in set(map(str, self._opts["highlight"] or []))]
        if hl:
            hl_colors = [theme.accent] if len(hl) == 1 and theme.accent else base
            for i, k in enumerate(hl):
                colors.setdefault(k, hl_colors[i % len(hl_colors)])
            for k in keys:
                colors.setdefault(k, theme.muted)
            return colors, []
        free = [k for k in keys if k not in colors]
        limit = len(base)
        if len(free) > limit:
            keep, others = free[: limit - 1], free[limit - 1:]
            if not all(getattr(l, "own_legend", False) for l in self._layers):
                warnings.warn(f"{len(free)} series but only {limit} distinct colours; the last {len(others)} are "
                              "drawn muted as 'Other'. Use highlight=... or split into several charts.", stacklevel=3)
        else:
            keep = free
        for i, k in enumerate(keep):
            colors[k] = base[i % len(base)]
        for k in others:
            colors[k] = theme.muted
        return colors, others

    def _legend_mode(self, theme, keys) -> str:
        mode = self._opts["legend"]
        if mode in (None, False, "none"):
            return "none"
        if mode != "auto":
            return mode
        if all(getattr(l, "own_legend", False) for l in self._layers):
            return "none"            # the layer labels itself (pie, treemap, sankey, ...)
        visible_keys = [k for k in keys if not k.startswith("__")]
        if len(visible_keys) <= 1 and not any(getattr(l, "force_legend", False) for l in self._layers):
            return "none"
        direct_ok = all(l.supports_direct_labels for l in self._layers)
        if theme.legend == "direct" and direct_ok and len(visible_keys) <= 8:
            return "direct"
        if theme.legend == "readout" and all(l.wants_readout for l in self._layers) and len(visible_keys) <= 5:
            return "readout"
        return "right" if len(visible_keys) > 8 else "top"

    # ------------------------------------------------------------------ header / footer / legend

    def _draw_header(self, scene, theme, W, top) -> float:
        title, subtitle = self._opts["title"], self._opts["subtitle"]
        pad = theme.padding
        panel = self._opts.get("panel")
        if panel is not None and title:
            # a panel inside a grid: small heading; Folio uses the (a), (b) convention
            size = theme.subtitle_size + 0.5
            spans = None
            if theme.caption_style == "figure":
                spans = [(f"({panel}) ", 700, False, theme.ink), (str(title), 400, True, theme.ink)]
            scene.add(S.Text(pad, top + size, str(title), size, theme.ink, weight=theme.title_weight, spans=spans))
            return top + size + 10
        if theme.caption_style == "figure" or not (title or subtitle):
            return top
        if theme.uppercase_header:
            y = pad + theme.title_size * 0.4
            if title:
                scene.add(S.Text(pad, y, str(title).upper(), theme.title_size, theme.ink_secondary,
                                 weight=theme.title_weight, baseline="middle", letter_spacing=0.6))
            if subtitle:
                tw = text_width(str(title or "").upper(), theme.title_size, theme.font_kind) + 24
                sub = truncate(str(subtitle).upper(), W - 2 * pad - tw, theme.subtitle_size, theme.font_kind)
                scene.add(S.Text(W - pad, y, sub, theme.subtitle_size, theme.ink_muted, anchor="end",
                                 baseline="middle", letter_spacing=0.4))
            rule = y + theme.title_size * 0.5 + 8
            scene.add(S.Line(0, rule, W, rule, theme.axis_color, 1))
            return rule + pad * 0.9
        y = top
        width = W - 2 * pad
        if title:
            for line in wrap(str(title), width, theme.title_size, theme.font_kind, True):
                y += theme.title_size * 1.05
                scene.add(S.Text(pad, y, line, theme.title_size, theme.ink, weight=theme.title_weight))
                y += theme.title_size * 0.22
        if subtitle:
            y += 2
            for line in wrap(str(subtitle), width, theme.subtitle_size, theme.font_kind):
                y += theme.subtitle_size * 1.05
                scene.add(S.Text(pad, y, line, theme.subtitle_size, theme.ink_secondary))
                y += theme.subtitle_size * 0.25
        return y + 12

    def _draw_footer(self, scene, theme, W, bottom) -> float:
        pad = theme.padding
        if self._opts.get("panel") is not None:
            return bottom
        width = W - 2 * pad
        size = theme.font_size + (1.5 if theme.caption_style == "figure" else 0)
        lines: list[tuple[str, str, bool]] = []   # (text, colour, first-line-has-prefix)
        prefix = ""
        if theme.caption_style == "figure":
            parts = [str(p).strip() for p in (self._opts["title"], self._opts["subtitle"], self._opts["caption"]) if p]
            # each part becomes a sentence: "Forecast." + "with 90% interval" -> "Forecast. With 90% interval."
            parts = [p[:1].upper() + p[1:] if i and p[:1].islower() else p for i, p in enumerate(parts)]
            text = " ".join(p if p.endswith((".", "?", "!", ":")) else p + "." for p in parts)
            if self._opts["number"] is not None:
                prefix = f"Figure {self._opts['number']}."
            if text or prefix:
                full = (prefix + " " + text).strip()
                for i, ln in enumerate(wrap(full, width, size, theme.font_kind)):
                    lines.append((ln, theme.ink_secondary, i == 0 and bool(prefix)))
        elif self._opts["caption"]:
            for ln in wrap(str(self._opts["caption"]), width, size, theme.font_kind):
                lines.append((ln, theme.ink_secondary, False))
        if self._opts["source"]:
            for ln in wrap(f"Source: {self._opts['source']}", width, size - 1, theme.font_kind):
                lines.append((ln, theme.ink_muted, False))
        if not lines:
            return bottom
        lh = size * 1.4
        y = bottom - lh * (len(lines) - 1)
        for ln, col, has_prefix in lines:
            if has_prefix and ln.startswith(prefix):
                # one text element with two runs: the renderer places the second run
                # right after the first, so spacing is correct whatever font is used
                rest = ln[len(prefix):].lstrip()
                spans = [(prefix, 700, False, theme.ink)] + ([(" " + rest, 400, False, col)] if rest else [])
                scene.add(S.Text(pad, y, ln, size, col, spans=spans))
            else:
                scene.add(S.Text(pad, y, ln, size, col))
            y += lh
        return bottom - lh * len(lines) - 8

    def _legend_rows(self, theme, items, width):
        size = theme.font_size + 0.5
        rows, cur, cur_w = [], [], 0.0
        for it in items:
            w = 16 + text_width(it.label, size, theme.font_kind) + 18
            if cur and cur_w + w > width:
                rows.append(cur)
                cur, cur_w = [], 0.0
            cur.append((it, w))
            cur_w += w
        if cur:
            rows.append(cur)
        return rows, size

    def _legend_height(self, theme, items, width) -> float:
        rows, size = self._legend_rows(theme, items, width)
        return len(rows) * size * 1.7 + 6

    def _swatch(self, scene, theme, it: LegendItem, x, cy):
        if it.shape == "line":
            scene.add(S.Line(x, cy, x + 14, cy, it.color, max(1.6, theme.line_width), dash=it.dash, cap="butt"))
        elif it.shape == "circle":
            scene.add(S.Rect(x + 2, cy - 5, 10, 10, fill=it.color, rx=5))
        elif it.shape == "hatch":
            scene.add(S.Rect(x + 2, cy - 5, 10, 10, fill=theme.background, stroke=theme.ink, stroke_width=0.8,
                             hatch=theme.ink))
        else:
            scene.add(S.Rect(x + 2, cy - 5, 10, 10, fill=it.color, rx=2))

    def _draw_legend_row(self, scene, theme, items, x0, top, width) -> float:
        rows, size = self._legend_rows(theme, items, width)
        y = top + size * 0.7
        for row in rows:
            x = x0
            for it, w in row:
                self._swatch(scene, theme, it, x, y)
                scene.add(S.Text(x + 16, y, it.label, size, theme.ink_secondary, baseline="middle"))
                x += w
            y += size * 1.7
        return y - size * 0.7 + 6

    def _draw_legend_column(self, scene, theme, items, x, top, width):
        size = theme.font_size
        y = top + size * 0.6
        for it in items:
            self._swatch(scene, theme, it, x, y)
            scene.add(S.Text(x + 16, y, truncate(it.label, width - 18, size, theme.font_kind), size,
                             theme.ink_secondary, baseline="middle"))
            y += size * 1.65

    def _draw_colorbar(self, scene, theme, cbar, x, top) -> float:
        stops, vmin, vmax, label = cbar
        lut = ramp_lut(tuple(stops))
        w, h = 160, 8
        img = np.repeat(np.concatenate([lut, np.full((len(lut), 1), 255, np.uint8)], axis=1)[None, :, :], 2, axis=0)
        size = theme.font_size - 0.5
        lx = x
        if label:
            scene.add(S.Text(x, top + 7, str(label), size, theme.ink_secondary, baseline="middle"))
            lx = x + text_width(str(label), size, theme.font_kind) + 10
        scene.add(S.Text(lx, top + 7, format_value(vmin), size, theme.ink_muted, baseline="middle"))
        bx = lx + text_width(format_value(vmin), size, theme.font_kind) + 6
        scene.add(S.Image(bx, top + 3, w, h, img))
        scene.add(S.Text(bx + w + 6, top + 7, format_value(vmax), size, theme.ink_muted, baseline="middle"))
        return top + 24

    # ------------------------------------------------------------------ cartesian

    def _domain(self, which: str) -> Domain:
        forced = getattr(self, "_forced", None)
        if forced and which in forced:
            return forced[which]
        dom = None
        for layer in self._layers:
            d = layer.x_domain() if which == "x" else layer.y_domain()
            if d is not None:
                dom = d if dom is None else dom.merge(d)
        return dom or Domain()

    def _scale(self, dom: Domain, axis: Axis, r0: float, r1: float, length: float, horizontal: bool, theme):
        if axis.reverse:
            r0, r1 = r1, r0
        kind = axis.scale
        if kind == "category" or (kind == "auto" and dom.kind == "cat"):
            cats = dom.categories or []
            gap = dom.gap if dom.gap is not None else theme.bar_gap
            return BandScale(cats, (r0, r1), gap=gap)
        lo, hi = dom.lo, dom.hi
        if not (math.isfinite(lo) and math.isfinite(hi)):
            lo, hi = 0.0, 1.0
        zero = dom.zero if axis.zero == "auto" else bool(axis.zero)
        if zero and kind != "log":
            lo, hi = min(lo, 0.0), max(hi, 0.0)
        user_lo, user_hi = (axis.range if axis.range is not None else (None, None))
        if dom.kind == "time":
            user_lo, user_hi = (_time_value(user_lo), _time_value(user_hi))
        if user_lo is not None:
            lo = float(user_lo)
        if user_hi is not None:
            hi = float(user_hi)
        spacing = 90 if horizontal else 48
        count = max(2.0, length / spacing)
        if kind == "log":
            if lo <= 0:   # zero can't be shown on a log axis: start at the smallest positive value
                pos = getattr(dom, "min_positive", None)
                lo = pos if pos else (dom.lo if dom.lo > 0 else hi / 1e3 if hi > 0 else 1e-3)
                lo = lo * 0.5            # so the smallest bar/point is still visible above the axis
            if dom.pad and hi > lo:
                f = (hi / lo) ** dom.pad
                lo = lo / f if user_lo is None else lo
                hi = hi * f if user_hi is None else hi
            return LogScale((lo, hi), (r0, r1))
        if dom.kind == "time" or kind == "time":
            if dom.pad and user_lo is None:
                p = (hi - lo) * dom.pad or 1.0
                lo, hi = lo - p, hi + p
            if lo == hi:
                lo, hi = lo - 43200e9, hi + 43200e9
            return TimeScale((lo, hi), (r0, r1))
        if (theme.axis_style == "range" and dom.nice and dom.kind == "num" and user_lo is None
                and user_hi is None and hi > lo):
            # range frames show the data extent, so round-number padding would only leave empty space
            p = (hi - lo) * max(dom.pad, 0.04)
            lo = lo if (zero and lo == 0) else lo - p
            hi = hi if (zero and hi == 0) else hi + p
        elif dom.nice and user_lo is None and user_hi is None:
            lo, hi, _ = nice_domain(lo, hi, count)
        else:
            if lo == hi:
                lo, hi = lo - (abs(lo) * 0.1 or 1), hi + (abs(hi) * 0.1 or 1)
            if dom.pad:
                p = (hi - lo) * dom.pad
                lo = lo - p if user_lo is None and not (zero and lo == 0) else lo
                hi = hi + p if user_hi is None and not (zero and hi == 0) else hi
            if dom.nice and user_lo is None:
                lo, _, _ = nice_domain(lo, hi, count)
            if dom.nice and user_hi is None:
                _, hi, _ = nice_domain(lo, hi, count)
        return LinearScale((lo, hi), (r0, r1))

    def _ticks(self, scale, axis: Axis, length: float, horizontal: bool, theme):
        """Tick positions and labels, thinned until the labels fit."""
        size = theme.font_size
        if isinstance(scale, BandScale):
            cats = scale.categories
            labels = [str(c) for c in cats]
            if axis.format is not None:
                from .scales import _apply_fmt
                labels = [_apply_fmt(axis.format, c) for c in cats]
            return list(range(len(cats))), labels
        if isinstance(axis.ticks, dict):
            vals = np.array([_axis_value(v, scale) for v in axis.ticks], dtype=float)
            return vals, [str(v) for v in axis.ticks.values()]
        if isinstance(axis.ticks, (list, tuple, np.ndarray)):
            vals = np.array([_axis_value(v, scale) for v in axis.ticks], dtype=float)
            if isinstance(scale, TimeScale):
                scale.ticks(max(2, length / 90))
            else:
                scale.step = float(np.min(np.diff(np.sort(vals)))) if len(vals) > 1 else None
            return vals, scale.labels(vals, axis.format)
        count = axis.ticks if isinstance(axis.ticks, (int, float)) and not isinstance(axis.ticks, bool) \
            else max(2.0, length / (90 if horizontal else 46))
        for _ in range(6):
            vals = scale.ticks(count)
            labels = scale.labels(vals, axis.format)
            if not horizontal or len(vals) < 3:
                break
            widest = max(text_width(l, size, theme.font_kind) for l in labels)
            if widest + 14 <= length / max(1, len(vals)):
                break
            count *= 0.7
        return vals, labels

    def _draw_cartesian(self, scene, theme, region: Plot, colors, highlight, raster_scale, legend_mode):
        xd, yd = self._domain("x"), self._domain("y")
        lx, ly = self._axis_titles(xd, yd)
        size = theme.font_size
        kind = theme.font_kind
        range_style = theme.axis_style == "range"
        offset = 8 if range_style else 0
        tick_out = theme.tick_length if theme.tick_direction == "out" else 0
        rotated_y = theme.caption_style == "figure"

        top = region.y + (size * 1.8 if (ly and not rotated_y and self._y.visible) else 4)
        if legend_mode == "readout":
            top += size * 2.0
        left = region.x
        bottom = region.bottom
        right = region.right
        if lx and self._x.visible:
            bottom -= size * 1.8
        if ly and rotated_y and self._y.visible:
            left += size * 1.6

        # direct labels / end values need room on the right
        if legend_mode == "direct":
            names = [k for l in self._layers for k in l.keys()]
            right -= max((text_width(n, size + 0.5, kind) for n in names), default=0) + 14
        else:
            ends = [t for l in self._layers for t in getattr(l, "end_value_texts", lambda th, m: [])(theme, legend_mode)]
            if ends:
                right -= max(text_width(t, size, kind, True) for t in ends) + 12
        # margins depend on tick labels and tick labels depend on margins: y first, then x
        x_band = (size * 1.5 + 6 + offset + tick_out) if self._x.visible else 0.0
        ph = bottom - top - x_band
        ys = self._scale(yd, self._y, top + ph, top, ph, False, theme)
        yv, yl = self._ticks(ys, self._y, ph, False, theme)
        yw = max((text_width(l, size, kind) for l in yl), default=0) if self._y.visible else 0
        if isinstance(ys, BandScale):
            yw = min(yw, (right - left) * 0.38)
        pl = left + yw + (8 + offset + tick_out if self._y.visible else 0)
        pw_ = right - pl
        xs = self._scale(xd, self._x, pl, pl + pw_, pw_, True, theme)
        xv, xl = self._ticks(xs, self._x, pw_, True, theme)
        x_rot = bool(self._x.visible and isinstance(xs, BandScale) and xl
                     and max(text_width(l, size, kind) for l in xl) > xs.step - 6)
        if x_rot:
            ph -= min(120.0, max(text_width(l, size, kind) for l in xl)) * 0.64 - size * 0.5
            ys = self._scale(yd, self._y, top + ph, top, ph, False, theme)
            yv, yl = self._ticks(ys, self._y, ph, False, theme)
        # last x label may overhang the right edge
        if not isinstance(xs, BandScale) and len(xl) and legend_mode != "direct":
            over = xs.scalar(xv[-1]) + text_width(xl[-1], size, kind) / 2 - region.right
            if over > 0:
                pw_ -= over
                xs = self._scale(xd, self._x, pl, pl + pw_, pw_, True, theme)
                xv, xl = self._ticks(xs, self._x, pw_, True, theme)
        plot = Plot(pl, top, pw_, ph)

        if theme.plot_background:
            scene.add(S.Rect(plot.x, plot.y, plot.w, plot.h, fill=theme.plot_background))
        self._draw_grid(scene, theme, plot, xs, ys, xv, yv)
        ctx = DrawContext(scene, theme, plot, xs, ys, colors, highlight, raster_scale,
                          dict(self._opts, _legend_mode=legend_mode))
        self._draw_annotations(ctx, under=True)
        scene.add(S.Clip(plot.x - 1, plot.y - 1, plot.w + 2, plot.h + 2))
        for layer in self._layers:
            layer.draw(ctx)
        scene.add(S.EndClip())
        scene.extend(ctx.overlay)
        self._draw_axes(scene, theme, plot, xs, ys, xv, xl, yv, yl, xd, yd, x_rot, offset)
        self._draw_annotations(ctx, under=False)
        if lx and self._x.visible:
            if theme.caption_style == "figure":
                scene.add(S.Text(plot.x + plot.w / 2, region.bottom - 2, lx, size, theme.ink_secondary,
                                 anchor="middle", italic=theme.italic_labels))
            else:
                scene.add(S.Text(plot.right, region.bottom - 2, lx, size, theme.ink_muted, anchor="end"))
        if ly and self._y.visible:
            if rotated_y:
                cx, cy = region.x + size * 0.6, plot.y + plot.h / 2
                scene.add(S.Text(cx, cy, ly, size, theme.ink_secondary, anchor="middle", rotate=-90,
                                 italic=theme.italic_labels, baseline="middle"))
            else:
                scene.add(S.Text(region.x, region.y + size * 0.9, truncate(ly, plot.right - region.x, size, kind),
                                 size, theme.ink_muted))
        if legend_mode == "direct":
            self._draw_direct_labels(ctx)
        elif legend_mode == "readout":
            self._draw_readout(ctx, region)
        for i, note in enumerate(ctx.notes if self._opts.get("notes", True) else []):
            scene.add(S.Text(plot.x + 8, plot.y + 14 + i * (size + 4), note, size, theme.ink_secondary,
                             italic=theme.italic_labels, halo=theme.background))

    def _axis_titles(self, xd, yd):
        auto_x = auto_y = None
        for layer in self._layers:
            ax, ay = layer.axis_labels()
            auto_x = auto_x or ax
            auto_y = auto_y or ay
        lx = auto_x if self._x.label == "auto" else self._x.label
        ly = auto_y if self._y.label == "auto" else self._y.label
        return (str(lx) if lx else None), (str(ly) if ly else None)

    def _draw_grid(self, scene, theme, plot, xs, ys, xv, yv):
        gx = self._x.grid if self._x.grid != "auto" else ("x" in theme.grid)
        gy = self._y.grid if self._y.grid != "auto" else ("y" in theme.grid)
        box = theme.axis_style == "box"
        if gy and not isinstance(ys, BandScale):
            for v in yv:
                py = ys.scalar(v)
                if box and (abs(py - plot.y) < 1 or abs(py - plot.bottom) < 1):
                    continue
                zero = v == 0 and theme.axis_style == "none" and all(getattr(l, "emphasize_zero", True) for l in self._layers)
                scene.add(S.Line(plot.x, py, plot.right, py, theme.axis_color if zero else theme.grid_color,
                                 1.5 if zero else theme.grid_width, dash=None if zero else theme.grid_dash))
        if gx and not isinstance(xs, BandScale):
            for v in xv:
                px = xs.scalar(v)
                if box and (abs(px - plot.x) < 1 or abs(px - plot.right) < 1):
                    continue
                scene.add(S.Line(px, plot.y, px, plot.bottom, theme.grid_color, theme.grid_width, dash=theme.grid_dash))

    def _draw_axes(self, scene, theme, plot, xs, ys, xv, xl, yv, yl, xd, yd, x_rot, offset):
        size, kind = theme.font_size, theme.font_kind
        style = theme.axis_style
        ink = theme.axis_color
        tl = theme.tick_length
        tdir = theme.tick_direction
        lab_col = theme.ink_secondary if style == "range" else theme.ink_muted

        # --- axis lines
        if style == "box":
            scene.add(S.Rect(plot.x, plot.y, plot.w, plot.h, stroke=ink, stroke_width=theme.axis_width))
        elif style == "baseline":
            if not isinstance(ys, BandScale):
                at_zero = ys.kind == "linear" and min(ys.d0, ys.d1) <= 0 <= max(ys.d0, ys.d1) \
                    and all(getattr(l, "emphasize_zero", True) for l in self._layers)
                y0 = ys.scalar(0) if at_zero else plot.bottom
                scene.add(S.Line(plot.x, y0, plot.right, y0, ink, theme.axis_width))
            elif not isinstance(xs, BandScale):
                x0 = xs.scalar(0) if xs.kind == "linear" and min(xs.d0, xs.d1) <= 0 <= max(xs.d0, xs.d1) else plot.x
                scene.add(S.Line(x0, plot.y, x0, plot.bottom, ink, theme.axis_width))
        elif style == "range":
            if self._x.visible and not isinstance(xs, BandScale):
                a, b = _extent(xd, xs)
                by = plot.bottom + offset
                scene.add(S.Line(xs.scalar(a), by, xs.scalar(b), by, ink, theme.axis_width))
                xv, xl = _range_ticks(xs, xv, xl, a, b, True, size, kind)
            if self._y.visible and not isinstance(ys, BandScale):
                a, b = _extent(yd, ys)
                ax = plot.x - offset
                scene.add(S.Line(ax, ys.scalar(a), ax, ys.scalar(b), ink, theme.axis_width))
                yv, yl = _range_ticks(ys, yv, yl, a, b, False, size, kind)
            if isinstance(ys, BandScale) and not isinstance(xs, BandScale):
                x0 = xs.scalar(0) if min(xs.d0, xs.d1) <= 0 <= max(xs.d0, xs.d1) else plot.x
                scene.add(S.Line(x0, plot.y, x0, plot.bottom, ink, theme.axis_width))

        # --- x ticks & labels
        # a y label sitting on the bottom edge collides with a centred first x label
        y_at_bottom = self._y.visible and not isinstance(ys, BandScale) and any(
            abs(ys.scalar(v) - plot.bottom) < size for v in yv)
        if self._x.visible:
            base = plot.bottom + offset
            for i, (v, lab) in enumerate(zip(xv, xl)):
                px = xs.center(v) if isinstance(xs, BandScale) else xs.scalar(v)
                if not (plot.x - 1 <= px <= plot.right + 1):
                    continue
                if tdir == "out" and not isinstance(xs, BandScale):
                    scene.add(S.Line(px, base, px, base + tl, ink, theme.axis_width))
                elif tdir == "in" and not isinstance(xs, BandScale):
                    scene.add(S.Line(px, plot.bottom, px, plot.bottom - tl, ink, theme.axis_width))
                    scene.add(S.Line(px, plot.y, px, plot.y + tl, ink, theme.axis_width))
                ty = base + (tl if tdir == "out" else 0) + 6
                if x_rot:
                    scene.add(S.Text(px + 3, ty, truncate(lab, 120, size, kind), size, lab_col, anchor="end",
                                     rotate=-40, baseline="hanging"))
                elif (i == 0 and y_at_bottom and not isinstance(xs, BandScale)
                      and px - text_width(lab, size, kind) / 2 < plot.x - offset - 3):
                    scene.add(S.Text(px - 2, ty, lab, size, lab_col, anchor="start", baseline="hanging"))
                else:
                    scene.add(S.Text(px, ty, lab, size, lab_col, anchor="middle", baseline="hanging"))
        # --- y ticks & labels
        if self._y.visible:
            base = plot.x - offset
            for v, lab in zip(yv, yl):
                py = ys.center(v) if isinstance(ys, BandScale) else ys.scalar(v)
                if not (plot.y - 1 <= py <= plot.bottom + 1):
                    continue
                if tdir == "out" and not isinstance(ys, BandScale):
                    scene.add(S.Line(base - tl, py, base, py, ink, theme.axis_width))
                elif tdir == "in" and not isinstance(ys, BandScale):
                    scene.add(S.Line(plot.x, py, plot.x + tl, py, ink, theme.axis_width))
                    scene.add(S.Line(plot.right, py, plot.right - tl, py, ink, theme.axis_width))
                tx = base - (tl if tdir == "out" else 0) - 7
                is_hl = isinstance(ys, BandScale) and lab in {str(h) for h in (self._opts["highlight"] or [])}
                lab_txt = truncate(lab, tx - theme.padding + 2, size, kind) if isinstance(ys, BandScale) else lab
                scene.add(S.Text(tx, py, lab_txt, size, theme.ink if is_hl else lab_col, anchor="end",
                                 baseline="middle", weight=600 if is_hl else 400))

    def _draw_direct_labels(self, ctx: DrawContext):
        theme = ctx.theme
        size = theme.font_size + 0.5
        labels = sorted(ctx.end_labels, key=lambda t: t[3])
        if not labels:
            return
        ys = [t[3] for t in labels]
        gap = size * 1.2
        for i in range(1, len(ys)):             # push apart downward
            ys[i] = max(ys[i], ys[i - 1] + gap)
        overflow = ys[-1] - ctx.plot.bottom
        if overflow > 0:
            ys = [y - overflow for y in ys]
            for i in range(len(ys) - 2, -1, -1):
                ys[i] = min(ys[i], ys[i + 1] - gap)
        for (_key, label, x, y0), y in zip(labels, ys):
            if abs(y - y0) > 3:
                ctx.scene.add(S.Line(x + 3, y0, x + 7, y, theme.ink_muted, 0.7))
            ctx.scene.add(S.Text(x + 9, y, label, size, theme.ink, baseline="middle", italic=theme.italic_labels))

    def _draw_readout(self, ctx: DrawContext, region: Plot):
        theme = ctx.theme
        items = [it for l in self._layers for it in l.readout(ctx)]
        x = ctx.plot.x
        y = ctx.plot.y - theme.font_size * 1.3
        for key, color, value in items:
            ctx.scene.add(S.Line(x, y, x + 10, y, color, 2))
            txt = f"{key[:10].upper()} {value}"
            ctx.scene.add(S.Text(x + 15, y, txt, theme.font_size, theme.ink, baseline="middle"))
            x += 15 + text_width(txt, theme.font_size, theme.font_kind) + 18

    def _draw_annotations(self, ctx: DrawContext, under: bool):
        theme, plot, scene = ctx.theme, ctx.plot, ctx.scene
        size = theme.font_size - 0.5
        for a in self._annotations:
            kind = a["kind"]
            if under and kind == "band":
                col = a["color"] or theme.accent
                x0, x1 = plot.x, plot.right
                y0, y1 = plot.y, plot.bottom
                if a["x"] is not None:
                    x0, x1 = sorted((_px(ctx.xs, a["x"][0], plot), _px(ctx.xs, a["x"][1], plot)))
                if a["y"] is not None:
                    y0, y1 = sorted((_px(ctx.ys, a["y"][0], plot), _px(ctx.ys, a["y"][1], plot)))
                x0, x1 = max(x0, plot.x), min(x1, plot.right)
                y0, y1 = max(y0, plot.y), min(y1, plot.bottom)
                opacity = 0.14 if theme.dark else 0.07
                scene.add(S.Rect(x0, y0, x1 - x0, y1 - y0, fill=col, opacity=opacity))
                if a["label"]:
                    # drawn over the data (overlay) so a line crossing the band can't hide it
                    tw = text_width(str(a["label"]), size, theme.font_kind)
                    tx, anchor = (x0 + x1) / 2, "middle"
                    if tx + tw / 2 > plot.right:
                        tx, anchor = min(x1, plot.right) - 2, "end"
                    elif tx - tw / 2 < plot.x:
                        tx, anchor = max(x0, plot.x) + 2, "start"
                    ctx.overlay.append(S.Text(tx, plot.y + size + 2, a["label"], size, theme.ink_secondary,
                                              anchor=anchor, weight=500, halo=theme.background))
            elif not under and kind in ("hline", "vline"):
                col = a["color"] or theme.ink
                if kind == "hline":
                    at = self._resolve_at(a["at"], "y")
                    py = _px(ctx.ys, at, plot)
                    if not plot.y <= py <= plot.bottom:
                        continue
                    scene.add(S.Line(plot.x, py, plot.right, py, col, 1.2, dash=a["dash"]))
                    lab = a["label"] if a["label"] is not None else (f"Mean {format_value(at)}" if a["at"] == "mean" else None)
                    if lab:
                        self._pill(ctx, plot.right - 4, py - 4, lab, anchor="end", above=True)
                else:
                    at = self._resolve_at(a["at"], "x")
                    px = _px(ctx.xs, at, plot)
                    if not plot.x <= px <= plot.right:
                        continue
                    scene.add(S.Line(px, plot.y, px, plot.bottom, col, 1.2, dash=a["dash"]))
                    lab = a["label"] if a["label"] is not None else (f"Mean {format_value(at)}" if a["at"] == "mean" else None)
                    if lab:
                        self._pill(ctx, px + 5, plot.bottom - 14, lab, anchor="start")
            elif not under and kind == "text":
                px, py = _px(ctx.xs, a["x"], plot), _px(ctx.ys, a["y"], plot)
                scene.add(S.Markers(np.array([px]), np.array([py]), "circle", 2.5, theme.ink))
                tx, ty = px + a["dx"], py + a["dy"]
                scene.add(S.Line(px, py, tx - 2, ty + 3, theme.ink_muted, 0.8))
                scene.add(S.Text(tx, ty, a["text"], size + 0.5, theme.ink, halo=theme.background,
                                 italic=theme.italic_labels))

    def _pill(self, ctx, x, y, text, anchor="start", above=False):
        theme = ctx.theme
        size = theme.font_size - 1
        w = text_width(text, size, theme.font_kind) + 12
        h = size + 7
        x0 = x - w if anchor == "end" else x
        y0 = y - h if above else y - h / 2
        if theme.name == "folio":
            ctx.scene.add(S.Text(x0 + 6, y0 + h / 2, text, size + 0.5, theme.ink, baseline="middle", italic=True,
                                 halo=theme.background))
            return
        ctx.scene.add(S.Rect(x0, y0, w, h, fill=theme.ink, rx=h / 2))
        ctx.scene.add(S.Text(x0 + 6, y0 + h / 2, text, size, theme.background, baseline="middle", weight=500))

    def _resolve_at(self, at, axis):
        if isinstance(at, str) and at in ("mean", "median"):
            vals = [v for l in self._layers for v in getattr(l, "values_for_reference", lambda a: [])(axis)]
            if not vals:
                raise ValueError(f"Can't compute the {at} for this chart; pass a number.")
            arr = np.concatenate([np.ravel(v) for v in vals])
            return float(np.nanmean(arr) if at == "mean" else np.nanmedian(arr))
        return at


# ---------------------------------------------------------------------- helpers

def _time_value(v):
    if v is None:
        return None
    if isinstance(v, (int, float, np.floating, np.integer)):
        return float(v)
    return float(np.datetime64(v, "ns").astype(np.int64))


def _axis_value(v, scale):
    if isinstance(scale, TimeScale) and not isinstance(v, (int, float, np.number)):
        return _time_value(v)
    return float(v)


def _px(scale, v, plot) -> float:
    if isinstance(scale, BandScale):
        return float(scale(str(v))[0])
    if isinstance(scale, TimeScale) and not isinstance(v, (int, float, np.number)):
        v = _time_value(v)
    return float(scale.scalar(v))


def _extent(dom: Domain, scale):
    if dom.extent:
        a, b = dom.extent
    else:
        a, b = dom.lo, dom.hi
    lo, hi = min(scale.d0, scale.d1), max(scale.d0, scale.d1)
    if scale.kind == "log":
        if a <= 0 and dom.min_positive:        # bars/histograms start at 0; the frame starts at the first value
            a = dom.min_positive
        a, b = math.log10(max(a, 1e-300)), math.log10(max(b, 1e-300))
        return 10 ** max(lo, a), 10 ** min(hi, b)
    return max(lo, a), min(hi, b)


def _range_ticks(scale, vals, labels, a, b, horizontal=True, size=11.0, kind="sans"):
    """Range-frame ticks: the data extremes plus the round ticks between them.

    Extremes are rounded to one decimal more than the tick step, and round ticks
    whose labels would touch an extreme's label are dropped.
    """
    if isinstance(scale, TimeScale):
        keep = [(v, l) for v, l in zip(vals, labels) if a - 1 <= v <= b + 1]
        return [v for v, _ in keep], [l for _, l in keep]
    if a == b:
        return [a], [format_value(a)]
    if scale.kind == "log":
        inner = [(v, l) for v, l in zip(vals, labels) if a * 1.4 < v < b / 1.4]
        la, lb = format_value(a), format_value(b)
    else:
        step = getattr(scale, "step", None) or ((b - a) / 4 or 1)
        digits = max(0, 1 - math.floor(math.log10(abs(step)))) if step else 2
        la, lb = _round_label(a, digits), _round_label(b, digits)
        inner = [(v, l) for v, l in zip(vals, labels) if a + step * 0.2 < v < b - step * 0.2]

    def clear(v, l, ev, el):
        d = abs(scale.scalar(v) - scale.scalar(ev))
        need = (text_width(l, size, kind) + text_width(el, size, kind)) / 2 + 6 if horizontal else size * 1.6
        return d >= need

    inner = [(v, l) for v, l in inner if clear(v, l, a, la) and clear(v, l, b, lb)]
    return [a] + [v for v, _ in inner] + [b], [la] + [l for _, l in inner] + [lb]


def _round_label(v, digits):
    r = round(float(v), digits)
    txt = format_value(r)
    return txt
