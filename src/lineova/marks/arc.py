"""Arc diagrams: nodes on a line, one arc per link. Good for ordered nodes (time, genome position, chapters)."""

from __future__ import annotations

import math

import numpy as np

from .. import scene as S
from .._data import DataError
from .._text import format_value, text_width
from ..graph import Graph
from ._base import DrawContext, Layer

_AUTO = "auto"


class ArcLayer(Layer):
    """Edge list, edge table, dict of neighbours, ``lv.Graph`` or networkx graph.

    ``order="auto"`` groups communities together (then by degree); pass a list of nodes to fix the order,
    or ``order="input"`` to keep the order of first appearance. Arcs go above the line; ``below=`` sends
    links whose weight is under that quantile to the lower side (off by default).
    """

    cartesian = False
    own_legend = True

    def __init__(self, data=None, *, order=_AUTO, labels=_AUTO, groups=_AUTO, directed=None, node_size=_AUTO):
        self.data, self.order, self.labels, self.groups_opt = data, order, labels, groups
        self.directed, self.node_size = directed, node_size

    def prepare(self, chart) -> None:
        from .network import NetworkLayer
        helper = NetworkLayer(self.data, directed=self.directed, groups=self.groups_opt if self.groups_opt == "community" else _AUTO)
        helper.prepare(chart)
        nodes = [str(n) for n in helper.nodes]
        src, dst, w = helper.src, helper.dst, helper.w
        n = len(nodes)
        if n < 2:
            raise DataError("An arc diagram needs at least 2 nodes.")
        deg = helper.deg
        comm = np.zeros(n, dtype=int)
        if self.groups_opt not in (False, "none") and n <= 2000:
            g = Graph(directed=False)
            for nd in range(n):
                g.add_node(nodes[nd])
            for a, b, ww in zip(src.tolist(), dst.tolist(), w.tolist()):
                if a != b:
                    g.add_edge(nodes[a], nodes[b], float(ww))
            idx = {nm: i for i, nm in enumerate(nodes)}
            for c, members in enumerate(sorted(g.communities(), key=lambda s: -len(s))):
                for m in members:
                    comm[idx[m]] = c
        if isinstance(self.order, (list, tuple)):
            pos = {str(nm): i for i, nm in enumerate(self.order)}
            missing = [nm for nm in nodes if nm not in pos]
            if missing:
                raise DataError(f"order= is missing {missing[:3]}.")
            perm = np.argsort([pos[nm] for nm in nodes])
        elif self.order == "input":
            perm = np.arange(n)
        else:
            perm = np.lexsort((-deg, comm))
        rank = np.empty(n, dtype=int)
        rank[perm] = np.arange(n)
        self.nodes = [nodes[i] for i in perm]
        self.deg = deg[perm]
        self.comm = comm[perm]
        keep = src != dst
        self.a, self.b, self.w = rank[src[keep]], rank[dst[keep]], w[keep]
        self.n_comm = int(self.comm.max()) + 1
        self.group_names = [f"Group {c + 1}" for c in range(self.n_comm)]

    def keys(self):
        return list(self.group_names) if self.n_comm > 1 else []

    def default_size(self, theme):
        return float(min(1400, max(640, len(self.nodes) * 16 + 120))), 380.0

    def draw(self, ctx: DrawContext) -> None:
        theme, plot = ctx.theme, ctx.plot
        size = theme.font_size - 0.5
        n = len(self.nodes)
        show_labels = (n <= 60) if self.labels == _AUTO else bool(self.labels)
        lab_h = max(text_width(nm, size, theme.font_kind) for nm in self.nodes) + 10 if show_labels else 6
        lab_h = min(lab_h, plot.h * 0.35)
        base_y = plot.bottom - lab_h
        x0, x1 = plot.x + 8, plot.right - 8
        xs = np.linspace(x0, x1, n) if n > 1 else np.array([(x0 + x1) / 2])
        step = xs[1] - xs[0]
        wmax = float(self.w.max()) if len(self.w) else 1.0
        wmin = float(self.w.min()) if len(self.w) else 1.0
        weighted = wmax > wmin
        lo_w, hi_w = (0.8, 4.0) if weighted else (1.0, 1.0)
        hl = ctx.highlight
        cols = [ctx.color(self.group_names[c], c) if self.n_comm > 1 else
                (theme.palette[0] if theme.family != "folio" else theme.ink_secondary) for c in self.comm]
        order = np.argsort(-np.abs(self.b - self.a))       # long arcs first, short ones on top
        max_h = base_y - plot.y - 4
        longest = float(np.abs(self.b - self.a).max()) * step / 2 or 1.0
        k = min(1.0, max_h / longest)
        op = float(np.clip(6.0 / math.sqrt(max(1, len(self.a))), 0.15, 0.7))
        for e in order.tolist():
            i, j = sorted((int(self.a[e]), int(self.b[e])))
            r = (xs[j] - xs[i]) / 2
            cmds = [("M", xs[i], base_y), ("C", xs[i], base_y - r * 4 / 3 * k, xs[j], base_y - r * 4 / 3 * k, xs[j], base_y)]
            t = (self.w[e] - wmin) / (wmax - wmin) if weighted else 0.0
            color = cols[int(self.a[e])] if self.comm[i] == self.comm[j] else theme.ink_muted
            on = not hl or self.nodes[i] in hl or self.nodes[j] in hl
            ctx.scene.add(S.Path(cmds, stroke=color if on else theme.muted, stroke_width=lo_w + (hi_w - lo_w) * t,
                                 opacity=op if on else 0.12,
                                 title=f"{self.nodes[int(self.a[e])]} – {self.nodes[int(self.b[e])]}"
                                       + (f": {format_value(self.w[e])}" if weighted else "")))
        dmax = float(self.deg.max()) or 1.0
        for i in range(n):
            if self.node_size == "equal":
                r = 3.0
            else:
                r = 2.5 + 3.5 * math.sqrt(self.deg[i] / dmax)
            r = min(r, max(1.5, step * 0.45)) if n > 1 else r
            ctx.scene.add(S.Markers(np.array([xs[i]]), np.array([base_y]), "circle", r, fill=cols[i],
                                    stroke=theme.background, stroke_width=1.0,
                                    titles=[f"{self.nodes[i]} · {int(self.deg[i])} links"]))
            if show_labels:
                ctx.scene.add(S.Text(xs[i], base_y + 10, self.nodes[i], size, theme.ink_secondary,
                                     anchor="end", baseline="middle", rotate=-90 if step < size * 1.4 else -45))
