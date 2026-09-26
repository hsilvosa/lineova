"""Sankey diagrams: flows between stages, band width proportional to quantity."""

from __future__ import annotations

import numpy as np

from .. import scene as S
from .._color import mix
from .._data import DataError, is_frame
from .._text import format_value, text_width
from ._base import DrawContext, Layer
from .network import _edges_from_frame

_AUTO = "auto"


class SankeyLayer(Layer):
    cartesian = False
    own_legend = True

    def __init__(self, data=None, *, node_width=_AUTO, padding=_AUTO, color=_AUTO, format=None, iterations=24):
        self.data, self.node_width, self.padding, self.color_by = data, node_width, padding, color
        self.fmt, self.iterations = format, iterations

    def prepare(self, chart) -> None:
        data = self.data
        if is_frame(data):
            a, b, w = _edges_from_frame(data)
            if w is None:
                raise DataError("A sankey needs a value column (value / weight / count).")
            rows = list(zip(a.tolist(), b.tolist(), w.tolist()))
        else:
            rows = [tuple(r) for r in data]
            if rows and len(rows[0]) < 3:
                raise DataError("Sankey rows are (source, target, value).")
        agg: dict = {}
        for s, t, v in rows:
            if v is None or not np.isfinite(v) or v <= 0:
                continue
            if s == t:
                raise DataError(f"Flow from {s!r} to itself.")
            agg[(str(s), str(t))] = agg.get((str(s), str(t)), 0.0) + float(v)
        if not agg:
            raise DataError("No positive flows to draw.")
        nodes = list(dict.fromkeys([k for pair in agg for k in pair]))
        idx = {n: i for i, n in enumerate(nodes)}
        links = [(idx[s], idx[t], v) for (s, t), v in agg.items()]
        n = len(nodes)
        out_v, in_v = np.zeros(n), np.zeros(n)
        for s, t, v in links:
            out_v[s] += v
            in_v[t] += v
        value = np.maximum(out_v, in_v)
        # columns: longest path from any source; sinks pushed to the last column
        depth = np.zeros(n, dtype=int)
        succ: list[list[int]] = [[] for _ in range(n)]
        for s, t, _ in links:
            succ[s].append(t)
        indeg = np.zeros(n, dtype=int)
        for _, t, _ in links:
            indeg[t] += 1
        queue = [i for i in range(n) if indeg[i] == 0]
        seen = 0
        while queue:
            u = queue.pop()
            seen += 1
            for v in succ[u]:
                depth[v] = max(depth[v], depth[u] + 1)
                indeg[v] -= 1
                if indeg[v] == 0:
                    queue.append(v)
        if seen != n:
            raise DataError("The flows contain a cycle; a sankey needs flows that move forward.")
        last = depth.max()
        for i in range(n):
            if not succ[i]:
                depth[i] = last
        self.nodes, self.links, self.value, self.depth = nodes, links, value, depth
        self.out_v, self.in_v = out_v, in_v

    def keys(self):
        return list(self.nodes)

    def default_size(self, theme):
        cols = int(self.depth.max()) + 1
        per_col = max(np.bincount(self.depth))
        return float(max(640, cols * 170)), float(min(900, max(360, per_col * 44 + 80)))

    def _fmt(self, v):
        if self.fmt is not None:
            return self.fmt(v) if callable(self.fmt) else (self.fmt.format(v) if "{" in self.fmt else format(v, self.fmt))
        return format_value(v)

    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        plot = ctx.plot
        size = theme.font_size
        n = len(self.nodes)
        ncol = int(self.depth.max()) + 1
        nw = 12.0 if isinstance(self.node_width, str) else float(self.node_width)
        # labels need room at the sides: right of every column but the last, left of the last
        lab_last = max((text_width(self.nodes[i], size, theme.font_kind, True) for i in range(n)
                        if self.depth[i] == ncol - 1), default=0) + 10
        lab_first = 0.0
        x0, x1 = plot.x + lab_first, plot.right - lab_last
        colx = [x0 + (x1 - x0 - nw) * (c / max(ncol - 1, 1)) for c in range(ncol)]
        cols = [[i for i in range(n) if self.depth[i] == c] for c in range(ncol)]
        pad = (size * 2.4) if isinstance(self.padding, str) else float(self.padding)
        H = plot.h
        ky = min((H - pad * (len(c) - 1)) / max(self.value[c].sum(), 1e-12) for c in cols)
        ky = max(ky, 0.0)
        heights = self.value * ky
        y = np.zeros(n)
        for c in cols:                      # initial: stacked from the top in input order
            cur = plot.y
            for i in c:
                y[i] = cur
                cur += heights[i] + pad
        # relax towards the weighted centre of connected nodes, then resolve overlaps
        nbrs: list[list[tuple[int, float]]] = [[] for _ in range(n)]
        for a, b, v in self.links:
            nbrs[a].append((b, v))
            nbrs[b].append((a, v))
        for it in range(self.iterations):
            alpha = 0.99 ** it
            order = range(1, ncol) if it % 2 == 0 else range(ncol - 2, -1, -1)
            for ci in order:
                for i in cols[ci]:
                    num = den = 0.0
                    for other, v in nbrs[i]:
                        num += (y[other] + heights[other] / 2) * v
                        den += v
                    if den:
                        y[i] += ((num / den) - (y[i] + heights[i] / 2)) * alpha
                self._collide(cols[ci], y, heights, pad, plot)
        # link offsets
        out_off = y.copy()
        in_off = y.copy()
        order = range(len(self.links))
        src_y, dst_y = {}, {}
        for k in sorted(order, key=lambda k: y[self.links[k][1]]):
            s = self.links[k][0]
            src_y[k] = out_off[s]
            out_off[s] += self.links[k][2] * ky
        for k in sorted(order, key=lambda k: y[self.links[k][0]]):
            t = self.links[k][1]
            dst_y[k] = in_off[t]
            in_off[t] += self.links[k][2] * ky
        node_col = [ctx.color(self.nodes[i], i) for i in range(n)]
        if theme.name == "folio":
            node_col = [theme.ink] * n
        hl = ctx.highlight
        for k, (s, t, v) in enumerate(self.links):
            w = v * ky
            xa = colx[self.depth[s]] + nw
            xb = colx[self.depth[t]]
            ya, yb = src_y[k], dst_y[k]
            mx = (xa + xb) / 2
            cmds = [("M", xa, ya), ("C", mx, ya, mx, yb, xb, yb), ("L", xb, yb + w),
                    ("C", mx, yb + w, mx, ya + w, xa, ya + w), ("Z",)]
            on = not hl or self.nodes[s] in hl or self.nodes[t] in hl
            col = node_col[s] if theme.name != "folio" else theme.ink
            ctx.scene.add(S.Path(cmds, fill=col if on else theme.muted,
                                 fill_opacity=(0.14 if theme.name == "folio" else 0.32) if on else 0.2,
                                 title=f"{self.nodes[s]} → {self.nodes[t]}: {self._fmt(v)}"))
        for i in range(n):
            x = colx[self.depth[i]]
            ctx.scene.add(S.Rect(x, y[i], nw, max(heights[i], 1.0), fill=node_col[i], rx=min(2.0, nw / 3),
                                 title=f"{self.nodes[i]}: {self._fmt(self.value[i])}"))
            tx = x + nw + 6                  # right of the node (space for the last column is reserved)
            anchor = "start"
            cy = y[i] + heights[i] / 2
            ctx.scene.add(S.Text(tx, cy - (size * 0.45 if heights[i] > size * 2 else 0), self.nodes[i], size, theme.ink,
                                 anchor=anchor, baseline="middle", weight=600, halo=theme.background))
            if heights[i] > size * 2:
                ctx.scene.add(S.Text(tx, cy + size * 0.75, self._fmt(self.value[i]), size - 0.5, theme.ink_secondary,
                                     anchor=anchor, baseline="middle", halo=theme.background))

    @staticmethod
    def _collide(col, y, heights, pad, plot):
        if not col:
            return
        order = sorted(col, key=lambda i: y[i])
        cur = plot.y
        for i in order:
            if y[i] < cur:
                y[i] = cur
            cur = y[i] + heights[i] + pad
        over = cur - pad - plot.bottom
        if over > 0:
            cur = plot.bottom
            for i in reversed(order):
                if y[i] + heights[i] > cur:
                    y[i] = cur - heights[i]
                cur = y[i] - pad
