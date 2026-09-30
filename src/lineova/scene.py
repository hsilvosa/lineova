"""A backend-neutral list of drawing operations.

Charts never write SVG or PDF directly. They append primitives to a ``Scene``;
each backend (SVG, PDF, PNG) serialises the same scene. Coordinates are CSS
pixels with the origin at the top-left.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from collections.abc import Sequence

import numpy as np

Dash = Optional[Sequence[float]]


@dataclass(slots=True)
class Rect:
    x: float
    y: float
    w: float
    h: float
    fill: Optional[str] = None
    stroke: Optional[str] = None
    stroke_width: float = 1.0
    rx: float = 0.0
    opacity: float = 1.0
    dash: Dash = None
    hatch: Optional[str] = None      # texture over the fill: "colour" (45° lines) or "colour|kind",
                                     # kind in / \\ x - | . (diagonal, back-diagonal, cross, rows, columns, dots)
    title: Optional[str] = None      # hover text (SVG only)


@dataclass(slots=True)
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    stroke: str
    stroke_width: float = 1.0
    dash: Dash = None
    opacity: float = 1.0
    cap: str = "butt"


@dataclass(slots=True)
class Polyline:
    """Many-point line or polygon. ``xs``/``ys`` are float arrays; NaN breaks the line."""
    xs: np.ndarray
    ys: np.ndarray
    stroke: Optional[str] = None
    stroke_width: float = 1.0
    fill: Optional[str] = None
    opacity: float = 1.0
    fill_opacity: float = 1.0
    dash: Dash = None
    closed: bool = False
    join: str = "round"
    cap: str = "round"
    hatch: Optional[str] = None      # texture over the fill: "colour" or "colour|kind" (see Rect)


@dataclass(slots=True)
class Path:
    """General path: list of ('M',x,y) ('L',x,y) ('C',x1,y1,x2,y2,x,y) ('Q',x1,y1,x,y) ('Z',)."""
    cmds: list
    stroke: Optional[str] = None
    stroke_width: float = 1.0
    fill: Optional[str] = None
    opacity: float = 1.0
    fill_opacity: float = 1.0
    dash: Dash = None
    cap: str = "round"
    join: str = "round"
    hatch: Optional[str] = None
    title: Optional[str] = None
    arrow: bool = False              # arrowhead at the end (networks)


@dataclass(slots=True)
class Markers:
    """A batch of identical markers (scatter plots, line markers)."""
    xs: np.ndarray
    ys: np.ndarray
    shape: str = "circle"            # circle | square | triangle | diamond | cross | plus
    size: Any = 4.0                  # radius in px, scalar or array
    fill: Any = None                 # colour or list of colours
    stroke: Any = None
    stroke_width: float = 1.0
    opacity: float = 1.0
    fill_opacity: float = 1.0
    titles: Optional[Sequence[str]] = None


@dataclass(slots=True)
class Text:
    x: float
    y: float
    text: str
    size: float
    color: str
    anchor: str = "start"            # start | middle | end
    weight: int = 400
    italic: bool = False
    rotate: float = 0.0              # degrees, around (x, y)
    baseline: str = "alphabetic"     # alphabetic | middle | hanging
    letter_spacing: float = 0.0
    halo: Optional[str] = None       # background-coloured outline for legibility
    spans: Optional[list] = None     # rich text: [(text, weight, italic, colour|None), ...]; overrides ``text``


@dataclass(slots=True)
class Image:
    x: float
    y: float
    w: float
    h: float
    rgba: np.ndarray                 # (rows, cols, 4) uint8
    smooth: bool = True


@dataclass(slots=True)
class Clip:
    x: float
    y: float
    w: float
    h: float


@dataclass(slots=True)
class EndClip:
    pass


@dataclass(slots=True)
class Group:
    """Ops drawn translated by (dx, dy): used to compose several charts into one figure."""
    dx: float
    dy: float
    ops: list


@dataclass
class Scene:
    width: float
    height: float
    background: str
    font: str
    font_kind: str
    ops: list = field(default_factory=list)
    description: str = ""
    title: str = ""
    meta: list = field(default_factory=list)     # interactive metadata (HTML export), not drawn
    table_html: str = ""

    def add(self, op) -> None:
        self.ops.append(op)

    def extend(self, ops) -> None:
        self.ops.extend(ops)
