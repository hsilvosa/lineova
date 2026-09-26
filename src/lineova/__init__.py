"""lineova — clean, fast charts with good defaults.

    import lineova as lv
    lv.line([3, 1, 4, 1, 5, 9, 2, 6]).save("line.svg")
"""

from . import themes
from ._data import Chunks, DataError
from .api import (area, bar, box, calendar, candlestick, density, donut, dumbbell, heatmap, histogram, line,
                  network, pie, radar, ridgeline, sankey, scatter, slope, sparkline, stat, timeline, treemap,
                  violin, waterfall)
from .chart import SIZES, Axis, Chart
from .figure import Grid, grid
from .graph import Graph, GraphError
from .themes import Theme

__version__ = "0.2.0"

__all__ = [
    "Chart", "Axis", "Grid", "grid", "Chunks", "Graph", "GraphError", "DataError", "Theme", "themes", "SIZES",
    "line", "area", "bar", "scatter", "histogram", "heatmap", "box", "network", "__version__",
    "pie", "donut", "violin", "ridgeline", "dumbbell", "slope", "waterfall", "candlestick", "treemap",
    "sankey", "radar", "density", "timeline", "calendar", "sparkline", "stat",
]
