"""lineova — clean, fast charts with good defaults.

    import lineova as lv
    lv.line([3, 1, 4, 1, 5, 9, 2, 6]).save("line.svg")
"""

from . import themes
from ._data import DataError
from .api import area, bar, box, heatmap, histogram, line, network, scatter
from .chart import SIZES, Axis, Chart
from .graph import Graph, GraphError
from .themes import Theme

__version__ = "0.1.0"

__all__ = [
    "Chart", "Axis", "Graph", "GraphError", "DataError", "Theme", "themes", "SIZES",
    "line", "area", "bar", "scatter", "histogram", "heatmap", "box", "network", "__version__",
]
