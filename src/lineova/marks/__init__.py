"""Chart layers. ``layer_class(name)`` imports the one you need on demand."""

from __future__ import annotations

import importlib

REGISTRY = {
    "line": ("line", "LineLayer"),
    "area": ("line", "AreaLayer"),
    "scatter": ("scatter", "ScatterLayer"),
    "bar": ("bar", "BarLayer"),
    "histogram": ("histogram", "HistogramLayer"),
    "heatmap": ("heatmap", "HeatmapLayer"),
    "box": ("box", "BoxLayer"),
    "violin": ("violin", "ViolinLayer"),
    "ridgeline": ("violin", "RidgeLayer"),
    "network": ("network", "NetworkLayer"),
    "pie": ("pie", "PieLayer"),
    "dumbbell": ("compare", "DumbbellLayer"),
    "slope": ("compare", "SlopeLayer"),
    "waterfall": ("waterfall", "WaterfallLayer"),
    "candlestick": ("candlestick", "CandlestickLayer"),
    "treemap": ("treemap", "TreemapLayer"),
    "sankey": ("sankey", "SankeyLayer"),
    "radar": ("radar", "RadarLayer"),
    "density": ("density", "DensityLayer"),
    "timeline": ("timeline", "TimelineLayer"),
    "calendar": ("calendar", "CalendarLayer"),
    "sparkline": ("tiles", "SparklineLayer"),
    "stat": ("tiles", "StatLayer"),
}


def layer_class(name: str):
    module, cls = REGISTRY[name]
    return getattr(importlib.import_module(f"{__name__}.{module}"), cls)
