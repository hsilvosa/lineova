"""Maps: GeoJSON choropleths, point maps (any number of points), and tile maps.

* ``lv.map(geojson, data, key=..., value=...)`` colours each feature by a joined value;
* ``lv.map(points_df, lon=..., lat=...)`` draws points (a density image above 50k points),
  optionally over a GeoJSON basemap (``geo=``);
* ``lv.tilemap(data, layout="es-provinces")`` gives every region one equal tile, so small
  regions count as much as large ones.

Projection is equirectangular with the x scale corrected at the map's central latitude
(right for countries and regions), or Web Mercator (``projection="mercator"``).
"""

from __future__ import annotations

import json
import math
import os

import numpy as np

from .. import scene as S
from .._color import ramp_lut, readable_on, to_hex, mix
from .._data import DataError, as_float, columns_of, get_column, is_auto, is_frame, to_array
from .._text import format_value, text_width, truncate
from ..raster import bin_points, shade
from ._base import DrawContext, Layer, LegendItem
from ._layouts import LAYOUTS, fold, resolver

_AUTO = "auto"
DENSITY_POINTS = 50_000


# ---------------------------------------------------------------- GeoJSON

def load_geojson(geo):
    """A GeoJSON dict from a dict, a JSON string or a file path (``__geo_interface__`` also works)."""
    if hasattr(geo, "__geo_interface__"):
        geo = geo.__geo_interface__
    if isinstance(geo, (str, os.PathLike)):
        text = str(geo)
        if text.lstrip().startswith("{"):
            geo = json.loads(text)
        else:
            with open(geo, encoding="utf-8") as fh:
                geo = json.load(fh)
    if not isinstance(geo, dict):
        raise DataError("geo= must be a GeoJSON dict, a JSON string or a path to a .geojson file.")
    if geo.get("type") == "FeatureCollection":
        return geo.get("features", [])
    if geo.get("type") == "Feature":
        return [geo]
    return [{"type": "Feature", "properties": {}, "geometry": geo}]


def polygons(geometry) -> list[list[np.ndarray]]:
    """[[ring (n, 2) lon/lat, ...] per polygon] for Polygon / MultiPolygon / GeometryCollection."""
    if not geometry:
        return []
    t = geometry.get("type")
    if t == "Polygon":
        return [[np.asarray(r, float)[:, :2] for r in geometry["coordinates"] if len(r)]]
    if t == "MultiPolygon":
        return [[np.asarray(r, float)[:, :2] for r in poly if len(r)] for poly in geometry["coordinates"]]
    if t == "GeometryCollection":
        return [p for g in geometry.get("geometries", []) for p in polygons(g)]
    return []


def lines(geometry) -> list[np.ndarray]:
    if not geometry:
        return []
    t = geometry.get("type")
    if t == "LineString":
        return [np.asarray(geometry["coordinates"], float)[:, :2]]
    if t == "MultiLineString":
        return [np.asarray(c, float)[:, :2] for c in geometry["coordinates"]]
    return []


# ---------------------------------------------------------------- projection

class Projection:
    """lon/lat -> plot pixels, fitted to a bounding box inside a region with the aspect kept."""

    def __init__(self, kind: str, bbox, region):
        lon0, lat0, lon1, lat1 = bbox
        self.kind = kind
        self.k = math.cos(math.radians((lat0 + lat1) / 2)) if kind == "equirectangular" else 1.0
        x0, y0 = self._raw(np.array([lon0]), np.array([lat0]))
        x1, y1 = self._raw(np.array([lon1]), np.array([lat1]))
        w, h = max(float(x1[0] - x0[0]), 1e-9), max(float(y1[0] - y0[0]), 1e-9)
        s = min(region.w / w, region.h / h)
        self.s = s
        self.ox = region.x + (region.w - w * s) / 2 - float(x0[0]) * s
        self.oy = region.y + (region.h - h * s) / 2 + float(y1[0]) * s
        self.extent = (region.x + (region.w - w * s) / 2, region.y + (region.h - h * s) / 2, w * s, h * s)

    def _raw(self, lon, lat):
        lon = np.asarray(lon, float)
        lat = np.asarray(lat, float)
        if self.kind == "mercator":
            lat = np.clip(lat, -85.0, 85.0)
            return np.radians(lon), np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))
        return lon * self.k, lat

    def __call__(self, lon, lat):
        x, y = self._raw(lon, lat)
        if self.kind == "mercator":
            return self.ox + x * self.s, self.oy - y * self.s
        return self.ox + x * self.s, self.oy - y * self.s


def _join(data, id_col, value_col, resolve=None):
    """{key: value} from a dict, a Series, or a DataFrame (``id_col``, ``value_col``)."""
    if data is None:
        return {}
    if isinstance(data, dict):
        items = data.items()
    elif is_frame(data):
        if id_col is None or value_col is None:
            raise DataError("With a DataFrame, pass id='column with the region keys' and value='column'.")
        items = zip(to_array(get_column(data, id_col)), to_array(get_column(data, value_col)))
    elif hasattr(data, "index") and hasattr(data, "values"):
        items = zip(to_array(data.index), to_array(data))
    else:
        raise DataError("Pass the values as {region: value}, a pandas Series, or a DataFrame with id= and value=.")
    out, missing = {}, []
    for k, v in items:
        key = resolve(k) if resolve else fold(k)
        if key is None:
            missing.append(str(k))
            continue
        out[key] = v
    return out, missing


def _colour_scale(values, theme, cmap, vmin=None, vmax=None):
    """(stops, lo, hi, kind) for numeric values; kind is 'seq', 'log' (skewed positives) or 'div'.

    A handful of extreme values shouldn't wash out everything else: skewed positive values get a
    log scale, and otherwise the top of the scale is the 99th percentile (larger values saturate).
    """
    v = np.array([float(x) for x in values if x is not None and np.isfinite(float(x))])
    lo = float(v.min()) if len(v) else 0.0
    hi = float(v.max()) if len(v) else 1.0
    if is_auto(cmap) and len(v) > 5 and lo > 0 and hi / max(float(np.median(v)), 1e-12) > 20:
        return tuple(theme.sequential), (vmin if vmin is not None else lo), (vmax if vmax is not None else hi), "log"
    if len(v) > 50 and lo >= 0:
        p99 = float(np.percentile(v, 99))
        if hi > 3 * p99 > 0:
            hi = p99
    if isinstance(cmap, (list, tuple)):
        return tuple(cmap), (vmin if vmin is not None else lo), (vmax if vmax is not None else hi), "seq"
    div = cmap == "diverging" or (is_auto(cmap) and lo < 0 < hi and min(-lo, hi) / max(-lo, hi) > 0.2)
    if div:
        m = max(abs(lo), abs(hi))
        return tuple(theme.diverging), -m if vmin is None else vmin, m if vmax is None else vmax, "div"
    return tuple(theme.sequential), (vmin if vmin is not None else lo), (vmax if vmax is not None else hi), "seq"


def _numeric(values) -> bool:
    try:
        [float(v) for v in values if v is not None]
        return True
    except (TypeError, ValueError):
        return False


class _ValueColours:
    """Shared colouring for maps: numeric values -> ramp (+ colour bar), categories -> palette (+ legend)."""

    def _setup_colours(self, theme, values: dict):
        self.numeric = _numeric(values.values()) if values else True
        self.cats = []
        self.has_scale = bool(values) and self.numeric
        if values and self.numeric:
            self.stops, self.vmin, self.vmax, self.scale_kind = _colour_scale(values.values(), theme, self.cmap,
                                                                              self.vmin_opt, self.vmax_opt)
            self.lut = ramp_lut(self.stops)
        elif values:
            self.cats = list(dict.fromkeys(str(v) for v in values.values()))

    def _fill(self, ctx, v):
        theme = ctx.theme
        if v is None:
            return None
        if self.numeric:
            f = float(v)
            if not np.isfinite(f):
                return None
            if self.scale_kind == "log":
                a, b = math.log10(self.vmin), math.log10(self.vmax)
                t = (math.log10(max(f, self.vmin)) - a) / ((b - a) or 1.0)
            else:
                t = (f - self.vmin) / ((self.vmax - self.vmin) or 1.0)
            t = min(max(t, 0.0), 1.0)
            if self.scale_kind in ("seq", "log"):
                t = 0.1 + 0.9 * t            # the lightest step stays visible against the background
            return to_hex(self.lut[int(t * (len(self.lut) - 1))] / 255.0)
        i = self.cats.index(str(v))
        return ctx.color(str(v), i) if not (ctx.highlight and str(v) not in ctx.highlight) else theme.muted

    def _fmt(self, v):
        if self.fmt is not None and v is not None:
            return self.fmt(v) if callable(self.fmt) else (self.fmt.format(v) if "{" in self.fmt else format(v, self.fmt))
        return format_value(float(v)) if (v is not None and self.numeric) else str(v)

    def keys(self):
        return list(self.cats)

    def legend_items(self, ctx):
        return [LegendItem(c, c, ctx.color(c, i), "square") for i, c in enumerate(self.cats)]

    def colorbar(self):
        if getattr(self, "numeric", False) and getattr(self, "has_scale", False):
            label = self.bar_label + (" (log)" if getattr(self, "scale_kind", "") == "log" else "")
            return (self.stops, self.vmin, self.vmax, label.strip())
        return None


# ---------------------------------------------------------------- GeoJSON map

class MapLayer(_ValueColours, Layer):
    """Choropleth from GeoJSON features, and/or points at lon/lat."""

    cartesian = False

    def __init__(self, data=None, geo=None, *, key=None, id=None, value=None, lon=None, lat=None, size=None,
                 color=None, projection=_AUTO, cmap=_AUTO, vmin=None, vmax=None, labels=_AUTO, format=None,
                 graticule=_AUTO, label=None, missing=_AUTO):
        self.data, self.geo, self.key, self.id, self.value = data, geo, key, id, value
        self.lon, self.lat, self.size, self.color = lon, lat, size, color
        self.projection, self.cmap, self.vmin_opt, self.vmax_opt = projection, cmap, vmin, vmax
        self.labels, self.fmt, self.graticule, self.label, self.missing = labels, format, graticule, label, missing

    def prepare(self, chart) -> None:
        theme = chart.resolved_theme
        data, geo = self.data, self.geo
        # lv.map(geojson) with no separate data: the first argument is the geometry
        if geo is None and (isinstance(data, dict) and data.get("type") in ("FeatureCollection", "Feature",
                                                                            "Polygon", "MultiPolygon")
                            or hasattr(data, "__geo_interface__")
                            or (isinstance(data, str) and data.lower().endswith((".geojson", ".json")))):
            geo, data = data, None
        self.features = load_geojson(geo) if geo is not None else []
        self.points = None
        if self.lon is not None or self.lat is not None:
            if self.lon is None or self.lat is None:
                raise DataError("Points need both lon= and lat=.")
            lon = as_float(to_array(get_column(data, self.lon) if isinstance(self.lon, str) else self.lon), "num")
            lat = as_float(to_array(get_column(data, self.lat) if isinstance(self.lat, str) else self.lat), "num")
            ok = np.isfinite(lon) & np.isfinite(lat)
            cvals = None
            if self.color is not None:
                cvals = to_array(get_column(data, self.color) if isinstance(self.color, str) else self.color)[ok]
            svals = None
            if self.size is not None and not isinstance(self.size, (int, float)):
                svals = as_float(to_array(get_column(data, self.size) if isinstance(self.size, str) else self.size), "num")[ok]
            self.points = (lon[ok], lat[ok], cvals, svals)
        # choropleth values joined to features (by id/name), or read from a feature property
        self.values = {}
        self.missing_keys = []
        if self.features and data is not None and self.points is None:
            self.values, self.missing_keys = _join(data, self.id, self.value)
        elif self.features and isinstance(self.value, str):
            for f in self.features:
                pv = (f.get("properties") or {}).get(self.value)
                if pv is not None:
                    self.values[self._fkey(f)] = pv
        self.bar_label = str(self.label or self.value or "")
        self._setup_colours(theme, self.values)
        # point colours (a column): a colour ramp for numbers, the palette for categories
        if self.points is not None and self.points[2] is not None:
            cv = self.points[2]
            if _numeric(cv[:1000]):
                v = as_float(cv, "num")
                self.stops, self.vmin, self.vmax, self.scale_kind = _colour_scale(
                    v[np.isfinite(v)][:200_000], theme, self.cmap, self.vmin_opt, self.vmax_opt)
                self.lut = ramp_lut(self.stops)
                self.numeric, self.has_scale = True, True
                self.bar_label = str(self.label or self.color)
            else:
                self.numeric, self.has_scale = False, False
                self.cats = list(dict.fromkeys(str(c) for c in cv))
        # bounding box
        xs, ys = [], []
        for f in self.features:
            for poly in polygons(f.get("geometry")):
                for ring in poly:
                    xs.append(ring[:, 0])
                    ys.append(ring[:, 1])
            for ln in lines(f.get("geometry")):
                xs.append(ln[:, 0])
                ys.append(ln[:, 1])
        if self.points is not None and len(self.points[0]):
            lo_x, hi_x = np.percentile(self.points[0], [0.1, 99.9]) if len(self.points[0]) > 1000 else \
                (self.points[0].min(), self.points[0].max())
            lo_y, hi_y = np.percentile(self.points[1], [0.1, 99.9]) if len(self.points[1]) > 1000 else \
                (self.points[1].min(), self.points[1].max())
            xs.append(np.array([lo_x, hi_x]))
            ys.append(np.array([lo_y, hi_y]))
        if not xs:
            raise DataError("Nothing to map: pass GeoJSON features (geo=) and/or points (lon=, lat=).")
        ax, ay = np.concatenate(xs), np.concatenate(ys)
        x0, x1, y0, y1 = float(np.nanmin(ax)), float(np.nanmax(ax)), float(np.nanmin(ay)), float(np.nanmax(ay))
        px, py = (x1 - x0) * 0.03 or 0.5, (y1 - y0) * 0.03 or 0.5
        self.bbox = (x0 - px, y0 - py, x1 + px, y1 + py)
        span = max(x1 - x0, y1 - y0)
        self.proj_kind = ("mercator" if span > 60 else "equirectangular") if is_auto(self.projection) else str(self.projection)

    def _fkey(self, f):
        props = f.get("properties") or {}
        if self.key is not None:
            return fold(props.get(self.key, ""))
        if f.get("id") is not None:
            return fold(f["id"])
        for k in ("id", "code", "iso", "name", "NAME", "name_en"):
            if k in props:
                return fold(props[k])
        return ""

    def _fname(self, f):
        props = f.get("properties") or {}
        for k in (self.key, "name", "NAME", "name_en", "nombre", "id"):
            if k and props.get(k) is not None:
                return str(props[k])
        return str(f.get("id", ""))

    def default_size(self, theme):
        return 640.0, 560.0

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        plot = ctx.plot
        show_graticule = (self.graticule is True) or (is_auto(self.graticule) and not self.features)
        region = plot
        if show_graticule:        # room for the degree labels
            from ._base import Plot
            m = text_width("45°N", theme.font_size - 1, theme.font_kind) + 8
            region = Plot(plot.x + m, plot.y, plot.w - m, plot.h - theme.font_size - 6)
        proj = Projection(self.proj_kind, self.bbox, region)
        base_fill = mix(theme.background, theme.ink, 0.06)
        edge = theme.background if self.values else mix(theme.background, theme.ink, 0.35)
        label_items = []
        if show_graticule:
            self._graticule(ctx, proj)
        for f in self.features:
            polys = polygons(f.get("geometry"))
            k = self._fkey(f)
            v = self.values.get(k)
            fill = self._fill(ctx, v) if (self.values and self.has_scale or self.values and not self.numeric) else base_fill
            if fill is None:
                fill = base_fill
            cmds = []
            area_best, centre = 0.0, None
            for poly in polys:
                for ring in poly:
                    x, y = proj(ring[:, 0], ring[:, 1])
                    if len(x) < 3:
                        continue
                    cmds.append(("M", float(x[0]), float(y[0])))
                    cmds.extend(("L", float(a), float(b)) for a, b in zip(x[1:].tolist(), y[1:].tolist()))
                    cmds.append(("Z",))
                if poly:
                    x, y = proj(poly[0][:, 0], poly[0][:, 1])
                    a = 0.5 * abs(float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))
                    if a > area_best:
                        area_best, centre = a, (float(x.mean()), float(y.mean()), float(x.max() - x.min()))
            if cmds:
                name = self._fname(f)
                title = f"{name}: {self._fmt(v)}" if v is not None else (name or None)
                ctx.scene.add(S.Path(cmds, fill=fill, stroke=edge, stroke_width=0.6, evenodd=True, join="round",
                                     title=title))
                if centre is not None:
                    label_items.append((area_best, centre, name, v, fill))
            for ln in lines(f.get("geometry")):
                x, y = proj(ln[:, 0], ln[:, 1])
                ctx.scene.add(S.Polyline(x, y, stroke=theme.ink_muted, stroke_width=0.8))
        if self.points is not None:
            self._draw_points(ctx, proj)
        show_labels = self.labels is True or (is_auto(self.labels) and self.values and len(self.features) <= 60)
        if show_labels:
            size = theme.font_size - 1.5
            for _a, (cx, cy, width), name, _v, fill in sorted(label_items, key=lambda t: -t[0]):
                txt = name
                if text_width(txt, size, theme.font_kind) > width * 0.9:
                    continue
                ctx.scene.add(S.Text(cx, cy, txt, size, readable_on(fill), anchor="middle", baseline="middle"))

    def _graticule(self, ctx, proj):
        theme = ctx.theme
        lon0, lat0, lon1, lat1 = self.bbox
        span = max(lon1 - lon0, lat1 - lat0)
        step = next(s for s in (0.5, 1, 2, 5, 10, 15, 30, 45, 60, 90) if span / s <= 8)
        size = theme.font_size - 1
        ex, ey, ew, eh = proj.extent
        for lo in np.arange(math.ceil(lon0 / step) * step, lon1 + 1e-9, step):
            lats = np.linspace(lat0, lat1, 40)
            x, y = proj(np.full_like(lats, lo), lats)
            ctx.scene.add(S.Polyline(x, y, stroke=theme.grid_color, stroke_width=0.8))
            ctx.scene.add(S.Text(float(x[0]), ey + eh + 12, f"{abs(lo):g}°{'W' if lo < 0 else 'E' if lo > 0 else ''}",
                                 size, theme.ink_muted, anchor="middle"))
        for la in np.arange(math.ceil(lat0 / step) * step, lat1 + 1e-9, step):
            lons = np.linspace(lon0, lon1, 40)
            x, y = proj(lons, np.full_like(lons, la))
            ctx.scene.add(S.Polyline(x, y, stroke=theme.grid_color, stroke_width=0.8))
            ctx.scene.add(S.Text(ex - 5, float(y[0]), f"{abs(la):g}°{'S' if la < 0 else 'N' if la > 0 else ''}",
                                 size, theme.ink_muted, anchor="end", baseline="middle"))

    def _draw_points(self, ctx, proj):
        theme = ctx.theme
        lon, lat, cvals, svals = self.points
        x, y = proj(lon, lat)
        n = len(x)
        if n > DENSITY_POINTS:
            plot = ctx.plot
            rs = ctx.raster_scale
            rows, cols = int(plot.h * rs), int(plot.w * rs)
            if cvals is not None and not self.numeric:
                codes = np.array([self.cats.index(str(c)) for c in cvals])
                counts = bin_points(x, y, (plot.x, plot.right), (plot.bottom, plot.y), (rows, cols),
                                    categories=codes, n_categories=len(self.cats), y_transform=lambda v: v)
                from .._color import rgb_array
                colors = rgb_array([ctx.color(c, i) for i, c in enumerate(self.cats)])
            else:
                counts = bin_points(x, y, (plot.x, plot.right), (plot.bottom, plot.y), (rows, cols))
                from .._color import rgb_array
                colors = rgb_array([theme.accent if theme.family != "ledger" else theme.palette[0]])[0]
            img = shade(counts, colors)
            ctx.scene.add(S.Image(plot.x, plot.y, plot.w, plot.h, img))
            ctx.notes.append(f"{n:,} points · density")
            return
        if svals is not None:
            v = np.nan_to_num(svals, nan=0.0)
            m = float(v.max()) or 1.0
            top = 14.0 if n <= 300 else 9.0 if n <= 3000 else 5.0      # many points: smaller bubbles
            lo_v = float(np.percentile(v, 1))
            r = 1.2 + top * np.sqrt(np.clip(v - lo_v, 0, None) / ((m - lo_v) or 1.0))
        else:
            r = np.full(n, float(self.size) if isinstance(self.size, (int, float)) else (3.0 if n < 2000 else 1.8))
        if cvals is None:
            fill = [theme.accent if theme.family != "ledger" else theme.palette[0]] * n
        else:
            fill = [self._point_fill(ctx, c) for c in cvals]
        order = np.argsort(-r, kind="stable")          # big bubbles underneath
        ctx.scene.add(S.Markers(x[order], y[order], "circle", r[order], fill=[fill[i] for i in order],
                                stroke=theme.background, stroke_width=0.8 if n < 5000 else 0.0,
                                opacity=0.85 if n > 500 else 1.0))

    def _point_fill(self, ctx, c):
        if self.numeric:
            return self._fill(ctx, c) or ctx.theme.muted
        return ctx.color(str(c), self.cats.index(str(c)))


# ---------------------------------------------------------------- tile map

class TileMapLayer(_ValueColours, Layer):
    """One equal tile per region, placed like the map: ``tilemap({"M": 6.8, "B": 5.7}, layout="es-provinces")``."""

    cartesian = False

    def __init__(self, data=None, *, layout="es-provinces", id=None, value=None, cmap=_AUTO, vmin=None, vmax=None,
                 labels=_AUTO, format=None, label=None, names=_AUTO):
        self.data, self.layout, self.id, self.value = data, layout, id, value
        self.cmap, self.vmin_opt, self.vmax_opt = cmap, vmin, vmax
        self.labels, self.fmt, self.label, self.names = labels, format, label, names

    def prepare(self, chart) -> None:
        theme = chart.resolved_theme
        if isinstance(self.layout, dict):
            lay = {str(k): (v[0], v[1], v[2] if len(v) > 2 else str(k), tuple(v[3]) if len(v) > 3 else ())
                   for k, v in self.layout.items()}
        else:
            try:
                lay = LAYOUTS[str(self.layout).lower()]
            except KeyError:
                raise DataError(f"Unknown tile layout {self.layout!r}. Built in: {', '.join(LAYOUTS)}; "
                                "or pass {code: (column, row, name)}.") from None
        self.lay = lay
        res = resolver(lay)
        if self.data is None:
            self.values, self.missing_keys = {}, []
        else:
            if is_frame(self.data) and not isinstance(self.data, dict) and (self.id is None or self.value is None):
                cols = columns_of(self.data)
                self.id = self.id or cols[0]
                self.value = self.value or next(c for c in cols if c != self.id)
            self.values, self.missing_keys = _join(self.data, self.id, self.value, res)
        if self.missing_keys:
            import warnings
            warnings.warn(f"{len(self.missing_keys)} key(s) didn't match the {self.layout!r} layout and are not "
                          f"shown: {', '.join(self.missing_keys[:6])}{' …' if len(self.missing_keys) > 6 else ''}",
                          stacklevel=4)
        self.bar_label = str(self.label or (self.value if isinstance(self.value, str) else "") or "")
        self._setup_colours(theme, self.values)

    def default_size(self, theme):
        cols = max(c for c, _, _, _ in self.lay.values()) + 1
        rows = max(r for _, r, _, _ in self.lay.values()) + 1
        w = 640.0
        return w, float(min(900, max(300, (w - 40) / cols * rows + 120)))

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        plot = ctx.plot
        cols = max(c for c, _, _, _ in self.lay.values()) + 1
        rows = max(r for _, r, _, _ in self.lay.values()) + 1
        cell = min(plot.w / cols, plot.h / rows)
        gap = max(2.0, cell * 0.06)
        ox = plot.x + (plot.w - cell * cols) / 2
        oy = plot.y + (plot.h - cell * rows) / 2
        size = max(7.0, min(theme.font_size, cell * 0.24))
        empty = mix(theme.background, theme.ink, 0.07)
        show_values = (self.labels is True or is_auto(self.labels)) and cell >= 44 and self.values
        for code, (c, r, name, _al) in self.lay.items():
            x, y = ox + c * cell + gap / 2, oy + r * cell + gap / 2
            w = cell - gap
            v = self.values.get(code)
            fill = self._fill(ctx, v) if v is not None else None
            title = f"{name}: {self._fmt(v)}" if v is not None else f"{name}: no data"
            ctx.scene.add(S.Rect(x, y, w, w, fill=fill or empty, rx=min(4.0, w * 0.08), title=title,
                                 stroke=None if fill else mix(theme.background, theme.ink, 0.18),
                                 stroke_width=0.8))
            ink = readable_on(fill) if fill else theme.ink_muted
            if self.labels is False:
                continue
            label = code if (is_auto(self.names) and cell < 70) or self.names is False else truncate(name, w - 6, size,
                                                                                                   theme.font_kind)
            ty = y + w / 2 - (size * 0.55 if show_values and v is not None else 0)
            ctx.scene.add(S.Text(x + w / 2, ty, label, size, ink, anchor="middle", baseline="middle", weight=600))
            if show_values and v is not None:
                ctx.scene.add(S.Text(x + w / 2, ty + size * 1.2, self._fmt(v), size - 1, ink, anchor="middle",
                                     baseline="middle"))
