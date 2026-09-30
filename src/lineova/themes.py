"""Themes: every visual decision the library makes lives here.

A theme is an immutable dataclass. To customise one, derive a copy::

    import lineova as lv
    brand = lv.themes.get("ledger").replace(accent="#0f766e", palette=("#0f766e", "#b45309"))
    lv.themes.register("brand", brand)
    lv.line(data, theme="brand")
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace as _replace
from typing import Literal, Optional

AxisStyle = Literal["range", "baseline", "box", "none"]
GridStyle = Literal["none", "x", "y", "xy"]
LegendStyle = Literal["direct", "top", "right", "readout"]


@dataclass(frozen=True)
class Theme:
    name: str
    family: str = ""                     # the built-in style this theme derives from (folio, ledger, ...)
    # --- type -------------------------------------------------------------
    font: str = "'IBM Plex Sans', 'Helvetica Neue', Arial, sans-serif"
    font_kind: Literal["sans", "serif", "mono"] = "sans"
    font_size: float = 11.0
    title_size: float = 15.0
    subtitle_size: float = 12.0
    title_weight: int = 600
    italic_labels: bool = False          # axis titles / direct labels in italics
    uppercase_header: bool = False
    # --- surfaces & ink ---------------------------------------------------
    background: str = "#ffffff"
    plot_background: Optional[str] = None
    ink: str = "#1a2233"
    ink_secondary: str = "#475467"
    ink_muted: str = "#8a94a6"
    axis_color: str = "#98a2b3"
    grid_color: str = "#e7eaf0"
    dark: bool = False
    # --- colour -----------------------------------------------------------
    palette: tuple[str, ...] = ("#2f5bd3", "#17a38b", "#e0913a", "#8a6bd1",
                                "#d0527a", "#5b8c2a", "#2b9bc9", "#a8641c")
    accent: str = "#2f5bd3"
    muted: str = "#c9d0dc"               # non-highlighted marks
    sequential: tuple[str, ...] = ("#eef2fc", "#9fb4ec", "#2f5bd3", "#172d6e")
    diverging: tuple[str, str, str] = ("#c2410c", "#f1f1ef", "#2f5bd3")
    positive: str = "#17a38b"            # increases (waterfall, candles, deltas)
    negative: str = "#d0527a"            # decreases
    # --- axes & grid ------------------------------------------------------
    axis_style: AxisStyle = "baseline"
    grid: GridStyle = "y"
    grid_dash: Optional[tuple[float, ...]] = (3, 3)
    grid_width: float = 1.0
    tick_direction: Literal["out", "in", "none"] = "none"
    tick_length: float = 4.0
    axis_width: float = 1.0
    # --- marks ------------------------------------------------------------
    line_width: float = 2.0
    curve: Literal["linear", "smooth"] = "linear"
    dashes: Optional[tuple[Optional[tuple[float, ...]], ...]] = None
    series_markers: Optional[tuple[str, ...]] = None   # per-series marker shapes on lines
    marker_size: float = 4.5
    scatter_style: Literal["solid", "hollow", "cross", "bubble"] = "solid"
    end_markers: bool = True             # dot on the last point of each line
    area_opacity: float = 0.22
    lead_area: bool = False              # fill under the first line series
    bar_radius: float = 3.0
    bar_gap: float = 0.28                # fraction of band left empty
    bar_highlight: Literal["color", "hatch"] = "color"
    bar_value_labels: Literal["auto", "inside", "outside", "none"] = "auto"
    # --- legend & text ----------------------------------------------------
    legend: LegendStyle = "top"
    legend_marker: Literal["square", "circle", "line"] = "square"
    caption_style: Literal["below", "figure"] = "below"
    # --- network ----------------------------------------------------------
    node_style: Literal["circle", "box", "ring", "sized"] = "box"
    edge_style: Literal["straight", "curved"] = "straight"
    edge_color: str = "#cdd3de"
    # --- spacing ----------------------------------------------------------
    padding: float = 16.0
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self):
        if not self.family:
            object.__setattr__(self, "family", self.name)

    def replace(self, **changes) -> Theme:
        """Return a copy with some fields changed."""
        valid = {f.name for f in fields(self)}
        unknown = set(changes) - valid
        if unknown:
            raise TypeError(f"Unknown theme field(s): {', '.join(sorted(unknown))}")
        return _replace(self, **changes)

    def color(self, i: int) -> str:
        return self.palette[i % len(self.palette)]


FOLIO = Theme(
    name="folio",
    font="'Source Serif 4', 'Source Serif Pro', Georgia, 'Times New Roman', serif",
    font_kind="serif", font_size=11.0, title_size=13.0, subtitle_size=11.5, title_weight=600,
    italic_labels=True,
    background="#ffffff", ink="#1e2229", ink_secondary="#4b5260", ink_muted="#7b828e",
    axis_color="#1e2229", grid_color="#e4e6ea",
    palette=("#1e2229", "#56647a", "#a3263b", "#2f5e8c", "#6e7b3a", "#5e4a8a", "#8a5a2b", "#3f7f7a"),
    accent="#1e2229", muted="#c7cbd1",
    sequential=("#f4f5f7", "#b9bec7", "#6b7382", "#1e2229"),
    diverging=("#a3263b", "#f2f2f2", "#2f5e8c"),
    positive="#8b929c", negative="#1e2229",
    axis_style="range", grid="none", grid_dash=None, tick_direction="out", tick_length=4, axis_width=0.9,
    line_width=1.4, dashes=(None, (6, 3), (1.5, 3), (8, 3, 2, 3), (3, 3), (10, 4), (1.5, 2, 5, 2), (4, 2)),
    series_markers=("circle", "square", "triangle", "diamond", "circle", "square", "triangle", "diamond"),
    marker_size=3.0, scatter_style="hollow", end_markers=False,
    area_opacity=0.12, bar_radius=0, bar_gap=0.45, bar_highlight="hatch", bar_value_labels="outside",
    legend="direct", legend_marker="line", caption_style="figure",
    node_style="circle", edge_style="straight", edge_color="#8b919b",
)

LEDGER = Theme(name="ledger")

INSTRUMENT = Theme(
    name="instrument",
    font="'JetBrains Mono', 'IBM Plex Mono', Consolas, 'DejaVu Sans Mono', monospace",
    font_kind="mono", font_size=10.0, title_size=11.0, subtitle_size=10.0, title_weight=500,
    uppercase_header=True,
    background="#0f1a24", ink="#d5e1ea", ink_secondary="#9db0bf", ink_muted="#62788a",
    axis_color="#3a5063", grid_color="#2a3c4c", dark=True,
    palette=("#2a9cc4", "#c08418", "#d2567f", "#62a846", "#8e7cd6", "#3aa88f", "#d0663a", "#c06cc0"),
    accent="#c08418", muted="#3f5467",
    sequential=("#13222f", "#1d5c78", "#2a9cc4", "#b9ecfb"),
    diverging=("#d2567f", "#1b2a37", "#2a9cc4"),
    positive="#62a846", negative="#d2567f",
    axis_style="box", grid="xy", grid_dash=(1, 3), tick_direction="in", tick_length=5,
    line_width=1.6, marker_size=4.0, scatter_style="cross", end_markers=False,
    area_opacity=0.18, bar_radius=0, bar_gap=0.3, bar_value_labels="outside",
    legend="readout", legend_marker="line",
    node_style="ring", edge_style="straight", edge_color="#3a5063",
)

FJORD = Theme(
    name="fjord",
    font="Figtree, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif",
    font_kind="sans", font_size=11.5, title_size=17.0, subtitle_size=12.5, title_weight=700,
    background="#eef2f4", ink="#17262e", ink_secondary="#43565f", ink_muted="#6e8088",
    axis_color="#b7c4ca", grid_color="#d5dde1",
    palette=("#008c9e", "#e0673f", "#4062b8", "#a8850e", "#9b4f96", "#3e8e4e", "#3a95d0", "#c4475a"),
    accent="#e0673f", muted="#b8c6cc",
    sequential=("#e3ecef", "#8fc7cf", "#008c9e", "#0b4750"),
    diverging=("#e0673f", "#f4f1ee", "#008c9e"),
    positive="#008c9e", negative="#e0673f",
    axis_style="none", grid="y", grid_dash=None, tick_direction="none",
    line_width=2.6, curve="smooth", marker_size=5.0, scatter_style="bubble",
    area_opacity=0.3, lead_area=True, bar_radius=999, bar_gap=0.26, bar_value_labels="inside",
    legend="top", legend_marker="circle",
    node_style="sized", edge_style="curved", edge_color="#a9b7be",
)

# --- dark variants: same hue order as the light themes (a series keeps its colour), lightness
# re-stepped for a dark surface and validated with check_palette (CVD ΔE >= 8, contrast >= 3:1)
LEDGER_DARK = LEDGER.replace(
    name="ledger-dark", family="ledger",
    background="#141a23", ink="#e6ebf2", ink_secondary="#aab4c3", ink_muted="#7a8698",
    axis_color="#4a5566", grid_color="#262f3c", dark=True,
    palette=("#4676f1", "#12ab92", "#b46d16", "#896ad0", "#cb4e76", "#73a545", "#1e8bb7", "#b66b19"),
    accent="#4676f1", muted="#3b4556",
    sequential=("#141e36", "#254cba", "#6593fe", "#cfdefd"),
    diverging=("#d0714a", "#2a3240", "#6593fe"),
    positive="#12ab92", negative="#cb4e76", edge_color="#3a4454",
)

FOLIO_DARK = FOLIO.replace(
    name="folio-dark", family="folio",
    background="#17191d", ink="#e4e6ea", ink_secondary="#b3b8c1", ink_muted="#868c97",
    axis_color="#c9cdd3", grid_color="#2c2f35", dark=True,
    palette=("#e4e6ea", "#9aa6b8", "#ce4f5d", "#3a84ca", "#8c9e36", "#886ec4", "#b66c16", "#1e938c"),
    accent="#e4e6ea", muted="#3d4047",
    sequential=("#1e1f22", "#515866", "#9199a7", "#d8deea"),
    diverging=("#ce4f5d", "#2a2c31", "#3a84ca"),
    positive="#868c97", negative="#e4e6ea", edge_color="#7d838e",
)

FJORD_DARK = FJORD.replace(
    name="fjord-dark", family="fjord",
    background="#0f2129", ink="#e3eef1", ink_secondary="#a9bdc4", ink_muted="#7892a0",
    axis_color="#3e5660", grid_color="#1f3842", dark=True,
    palette=("#1e8fa1", "#cd562d", "#577cd4", "#b38f18", "#ac5fa7", "#409551", "#3a9cdc", "#cd4f61"),
    accent="#cd562d", muted="#3a525c",
    sequential=("#102326", "#0b6370", "#43a8b9", "#a6ecf9"),
    diverging=("#cd562d", "#2a3f47", "#43a8b9"),
    positive="#1e8fa1", negative="#cd562d", edge_color="#3e5660",
)

# a light counterpart for the (dark) technical theme
INSTRUMENT_LIGHT = INSTRUMENT.replace(
    name="instrument-light", family="instrument",
    background="#f7f9fa", ink="#16222c", ink_secondary="#40535f", ink_muted="#6c7e8a",
    axis_color="#9aabb7", grid_color="#dde4e9", dark=False,
    palette=("#017faa", "#b57709", "#a92c59", "#5a993f", "#6350af", "#1a9c81", "#a24111", "#b660b5"),
    accent="#b57709", muted="#c3cdd4",
    sequential=("#eaf3f7", "#9fcbe0", "#017faa", "#0d3a4d"),
    diverging=("#a92c59", "#eef0f1", "#017faa"),
    positive="#5a993f", negative="#a92c59", edge_color="#b5c3cc",
)

_REGISTRY: dict[str, Theme] = {t.name: t for t in (FOLIO, LEDGER, INSTRUMENT, FJORD, LEDGER_DARK, FOLIO_DARK,
                                                   FJORD_DARK, INSTRUMENT_LIGHT)}
DEFAULT = "ledger"


def get(theme: str | Theme | None) -> Theme:
    """Resolve a theme name (or pass a Theme through)."""
    if theme is None:
        return _REGISTRY[DEFAULT]
    if isinstance(theme, Theme):
        return theme
    try:
        return _REGISTRY[str(theme).lower()]
    except KeyError:
        raise ValueError(f"Unknown theme {theme!r}. Available: {', '.join(names())}") from None


def register(name: str, theme: Theme) -> None:
    """Make ``theme`` available by ``name`` everywhere a theme is accepted.

    The theme keeps its ``family`` (the built-in style it derives from), so charts keep that style.
    """
    _REGISTRY[name.lower()] = theme.replace(name=name.lower(), family=theme.family)


def names() -> list[str]:
    return sorted(_REGISTRY)


def set_default(name: str) -> None:
    """Change the theme used when none is given."""
    global DEFAULT
    get(name)
    DEFAULT = name.lower()


# ------------------------------------------------------------------ theme builder

_DARK_OF = {"ledger": "ledger-dark", "folio": "folio-dark", "fjord": "fjord-dark", "instrument": "instrument"}
_LIGHT_OF = {"ledger": "ledger", "folio": "folio", "fjord": "fjord", "instrument": "instrument-light"}


def dark(theme: str | Theme) -> Theme:
    """The dark variant of a theme's family (``dark("ledger")`` -> ledger-dark)."""
    return get(_DARK_OF.get(get(theme).family, "ledger-dark"))


def light(theme: str | Theme) -> Theme:
    """The light variant of a theme's family."""
    return get(_LIGHT_OF.get(get(theme).family, "ledger"))


def check_palette(colors, background: str = "#ffffff"):
    """Check a categorical palette against a background: lightness band, chroma, colour-blind
    separation of neighbours, normal-vision separation and contrast. Returns a printable report
    with ``.ok``. ``check_palette(theme)`` checks a theme's own palette."""
    from ._palette import check_palette as _check
    if isinstance(colors, (Theme, str)) and not (isinstance(colors, str) and colors.startswith("#")):
        t = get(colors)
        return _check(t.palette, t.background)
    return _check(colors, background)


def from_brand(color: str, base: str | Theme = "ledger", *, dark: bool = False, name: str | None = None,
               background: str | None = None, n: int = 8) -> Theme:
    """Build a theme around a brand colour.

    The brand colour leads the categorical palette; the other colours are generated to stay
    distinguishable for colour-blind readers and to contrast with the background (see
    ``check_palette``). Sequential and diverging ramps, accent and highlight colours follow.
    Everything else (type, axes, marks) comes from ``base``. Pass ``name=`` to register it::

        lv.themes.from_brand("#0f766e", base="fjord", name="acme")
        lv.bar(data, theme="acme")
    """
    from ._palette import _hex_rgb, generate, oklch, ramp
    from ._color import mix
    b = get(base)
    b = globals()["dark"](b) if dark else (light(b) if b.dark and not dark else b)
    bg = background or b.background
    pal = generate(color, bg, n=n)
    lead = pal[0]
    # the negative pole of the diverging ramp: the palette colour whose hue is farthest from the brand
    h0 = oklch(lead)[2]
    far = max(pal[1:], key=lambda c: abs(((oklch(c)[2] - h0 + 180) % 360) - 180)) if len(pal) > 1 else b.diverging[0]
    mid = mix(bg, b.ink, 0.08)
    _hex_rgb(lead)  # validates the colour string early
    t = b.replace(
        name=(name or f"{b.family}-brand").lower(), family=b.family, background=bg,
        palette=pal, accent=lead if b.family != "folio" else b.accent,
        sequential=ramp(lead, bg, 4), diverging=(far, mid, lead),
    )
    if name:
        register(name, t)
    return t
