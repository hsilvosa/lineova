"""Network (node-link) drawings. Scales from 5 nodes to millions of edges."""

from __future__ import annotations

import math

import numpy as np

from .. import layout as L
from .. import scene as S
from .._color import mix, readable_on, rgb_array
from .._data import columns_of, DataError, get_column, is_auto, is_frame, to_array
from .._text import format_value, text_width
from ..graph import Graph
from ..raster import bin_points, bin_segments, shade
from ._base import DrawContext, Layer, LegendItem, Plot

_AUTO = "auto"
VECTOR_EDGES = 6000
VECTOR_NODES = 6000

_SRC = ("source", "src", "from", "u", "start", "origin")
_DST = ("target", "dst", "to", "v", "end", "destination")
_W = ("weight", "value", "w", "cost", "distance", "count")


def _edges_from_frame(df):
    cols = {str(c).lower(): c for c in columns_of(df)}
    s = next((cols[c] for c in _SRC if c in cols), None)
    d = next((cols[c] for c in _DST if c in cols), None)
    if s is None or d is None:
        names = list(columns_of(df))
        if len(names) < 2:
            raise DataError("An edge table needs source and target columns.")
        s, d = names[0], names[1]
    w = next((cols[c] for c in _W if c in cols), None)
    return to_array(get_column(df, s)), to_array(get_column(df, d)), (to_array(get_column(df, w)).astype(float)
                                                                      if w is not None else None)


class NetworkLayer(Layer):
    cartesian = False
    legend_shape = "circle"

    def __init__(self, data=None, *, directed=None, layout=_AUTO, labels=_AUTO, node_size=_AUTO, groups=_AUTO,
                 edge_labels=_AUTO, path=None, highlight=None, positions=None, seed=0):
        self.data, self.directed, self.layout = data, directed, layout
        self.labels, self.node_size, self.groups_opt = labels, node_size, groups
        self.edge_labels, self.path, self.hl = edge_labels, path, highlight
        self.positions, self.seed = positions, seed

    # ---------------------------------------------------------------- data
    def prepare(self, chart) -> None:
        data = self.data
        graph = None
        if isinstance(data, Graph):
            graph = data
        elif hasattr(data, "is_directed") and hasattr(data, "edges") and hasattr(data, "nodes"):
            graph = Graph.from_networkx(data)
        elif isinstance(data, dict):
            graph = Graph.from_adjacency(data, directed=bool(self.directed))
        if graph is not None:
            directed = graph.directed if self.directed is None else self.directed
            nodes, src, dst, w = graph.to_arrays()
            self.graph = graph
        else:
            if is_frame(data):
                a, b, w = _edges_from_frame(data)
            else:
                arr = data if isinstance(data, np.ndarray) else None
                if arr is None:
                    rows = list(data)
                    a = np.array([r[0] for r in rows], dtype=object)
                    b = np.array([r[1] for r in rows], dtype=object)
                    w = np.array([float(r[2]) for r in rows]) if rows and len(rows[0]) > 2 else None
                else:
                    if arr.ndim != 2 or arr.shape[1] < 2:
                        raise DataError("An edge array must have shape (m, 2) or (m, 3).")
                    a, b = arr[:, 0], arr[:, 1]
                    w = arr[:, 2].astype(float) if arr.shape[1] > 2 else None
            both = np.concatenate([np.asarray(a), np.asarray(b)])
            try:
                nodes_arr, inv = np.unique(both, return_inverse=True)
            except TypeError:  # mixed types
                nodes_arr, inv = np.unique(both.astype(str), return_inverse=True)
            m = len(a)
            src, dst = inv[:m].astype(np.int64), inv[m:].astype(np.int64)
            nodes = nodes_arr.tolist()
            w = np.ones(m) if w is None else np.asarray(w, float)
            directed = bool(self.directed)
            self.graph = None
            if len(nodes) <= 200_000 and (self.path is not None or self.groups_opt == "community"
                                          or self.node_size in ("pagerank", "betweenness", "closeness")):
                g = Graph(directed=directed)
                for n in nodes:
                    g.add_node(n)
                for i, j, ww in zip(src.tolist(), dst.tolist(), w.tolist()):
                    g.add_edge(nodes[i], nodes[j], ww)
                self.graph = g
        self.nodes, self.src, self.dst, self.w = nodes, src, dst, w
        self.directed_ = directed
        self.index = {n: i for i, n in enumerate(nodes)}
        n = len(nodes)
        self.deg = np.bincount(src, minlength=n) + np.bincount(dst, minlength=n)
        # highlighted path
        hl_nodes = list(self.hl) if self.hl is not None else list(chart._opts.get("highlight") or [])
        if self.path is not None:
            if self.graph is None:
                raise DataError("path=... needs the graph structure; pass a lv.Graph or an edge list.")
            s, t = self.path
            hl_nodes = self.graph.shortest_path(s, t)
            self.path_cost = self.graph.path_weight(hl_nodes)
        self.hl_nodes = [h for h in hl_nodes if h in self.index]
        self.hl_edges = set()
        for a, b in zip(self.hl_nodes, self.hl_nodes[1:]):
            ia, ib = self.index[a], self.index[b]
            self.hl_edges.add((ia, ib))
            if not directed:
                self.hl_edges.add((ib, ia))
        # groups (colour)
        self.group_of = None
        self.group_names: list[str] = []
        g = self.groups_opt
        if isinstance(g, dict):
            vals = [str(g.get(nn, "other")) for nn in nodes]
            self.group_names = list(dict.fromkeys(vals))
            self.group_of = np.array([self.group_names.index(v) for v in vals])
        elif g in ("component", "community") or (is_auto(g) and self._auto_components()):
            if g == "community" and self.graph is not None:
                comps = self.graph.communities(seed=self.seed)
            else:
                comps = self._components()
            self.group_of = np.zeros(n, dtype=np.int64)
            for ci, comp in enumerate(comps):
                for nn in comp:
                    self.group_of[self.index[nn]] = min(ci, 7)
            self.group_names = [f"Group {i + 1}" for i in range(min(len(comps), 8))]
            if len(comps) > 8:
                self.group_names[-1] = "Other"
        self.theme = chart.resolved_theme
        # layout
        self.pos = self._layout(n)

    def _components(self):
        n = len(self.nodes)
        parent = np.arange(n)

        def find(x):
            root = x
            while parent[root] != root:
                root = parent[root]
            while parent[x] != root:
                parent[x], x = root, parent[x]
            return root

        for a, b in zip(self.src.tolist(), self.dst.tolist()):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        roots = np.array([find(i) for i in range(n)])
        comps: dict = {}
        for i, r in enumerate(roots.tolist()):
            comps.setdefault(r, []).append(self.nodes[i])
        return sorted(comps.values(), key=len, reverse=True)

    def _auto_components(self) -> bool:
        n = len(self.nodes)
        if n > 5000:
            return False
        comps = len(self._components())
        return 1 < comps <= 8

    def _layout(self, n):
        if self.positions is not None:
            p = np.array([self.positions[nn] for nn in self.nodes], dtype=float)
            p[:, 1] = -p[:, 1]           # user coordinates: y up
            return L.normalize(p)
        how = self.layout
        if is_auto(how):
            # DAGs read best left-to-right; layered() falls back to force if there is a cycle
            how = "layered" if (self.directed_ and n <= 400) else "force"
        if how == "force":
            return L.force(n, self.src, self.dst, self.w, seed=self.seed)
        if how == "circular":
            return L.circular(n)
        if how == "grid":
            return L.grid(n)
        if how == "layered":
            self.layered_ = True
            return L.layered(n, self.src, self.dst)
        raise ValueError(f"Unknown layout {how!r}: use auto, force, circular, grid, layered, or positions=.")

    def keys(self):
        return list(self.group_names)

    def default_size(self, theme):
        n = len(self.nodes)
        if getattr(self, "layered_", False) and n:
            _, counts = np.unique(np.round(self.pos[:, 0], 6), return_counts=True)
            return 720.0, float(min(900, 150 + counts.max() * 64))
        return (720.0, 520.0) if n > 12 else (640.0, 420.0)

    def legend_items(self, ctx):
        return [LegendItem(g, g, ctx.color(g, i), "circle") for i, g in enumerate(self.group_names)]

    # ---------------------------------------------------------------- drawing
    def draw(self, ctx: DrawContext) -> None:
        theme = ctx.theme
        n, m = len(self.nodes), len(self.src)
        style = theme.node_style
        label_mode = self.labels
        short = all(len(str(x)) <= 3 for x in self.nodes[:200])
        show_labels = label_mode is True or (is_auto(label_mode) and n <= 40)
        top_labels = is_auto(label_mode) and 40 < n <= 400
        # node radius
        if not is_auto(self.node_size) and not isinstance(self.node_size, str):
            base_r = float(self.node_size)
        else:
            base_r = 12.0 if n <= 20 else (9.0 if n <= 60 else max(1.2, 60 / math.sqrt(n)))
        measure = self.deg.astype(float)
        if self.node_size in ("pagerank", "betweenness", "closeness"):
            if self.graph is None:
                raise DataError(f"node_size={self.node_size!r} needs the graph structure; pass a lv.Graph.")
            scores = getattr(self.graph, self.node_size)()
            measure = np.array([scores[nn] for nn in self.nodes], float)
        sized = style == "sized" or self.node_size in ("degree", "pagerank", "betweenness", "closeness")
        if sized and n:
            dmax = float(measure.max()) or 1.0
            radii = base_r * (0.55 + 0.75 * np.sqrt(np.clip(measure, 0, None) / dmax))
        else:
            radii = np.full(n, base_r)
        if style == "box" and show_labels:
            radii = np.maximum(radii, 12.0)
        # node half-extents (boxes are wider than tall) — used for margins and arrow ends
        size = theme.font_size
        labels = [str(v) for v in self.nodes]
        if style == "box" and show_labels:
            hw = np.array([max(radii[i] + 3, text_width(labels[i], size + 1, theme.font_kind, True) / 2 + 7)
                           for i in range(n)])
        else:
            hw = radii.copy()
        self._hw, self._hh = hw, radii
        # place into plot with a margin for node size + labels drawn beside nodes
        beside = (show_labels or top_labels) and not (style == "box" or (short and style in ("circle", "sized")))
        label_w = max((text_width(l, size, theme.font_kind) for l in labels[:2000]), default=0) if beside else 0
        mx = float(hw.max(initial=4)) + 6 + label_w
        my = float(radii.max(initial=4)) + (size + 8 if beside else 6)
        plot = ctx.plot
        inner = Plot(plot.x + (float(hw.max(initial=4)) + 6), plot.y + my,
                     max(10, plot.w - (float(hw.max(initial=4)) + 6) - mx), max(10, plot.h - 2 * my))
        span = self.pos.max(axis=0) - self.pos.min(axis=0) if n else np.array([1, 1])
        px = inner.x + self.pos[:, 0] * inner.w if span[0] > 0 else np.full(n, inner.x + inner.w / 2)
        py = inner.y + self.pos[:, 1] * inner.h if span[1] > 0 else np.full(n, inner.y + inner.h / 2)
        # keep aspect from distorting too much
        self._px, self._py = px, py
        hl_set = {self.index[h] for h in self.hl_nodes}
        weighted = m > 0 and float(self.w.max()) != float(self.w.min())
        self._draw_edges(ctx, px, py, radii, weighted)
        self._draw_nodes(ctx, px, py, radii, hl_set, show_labels, top_labels, short)

    def _node_colors(self, ctx, hl_set):
        theme = ctx.theme
        n = len(self.nodes)
        if self.group_of is not None:
            return [ctx.color(self.group_names[g], g) for g in self.group_of.tolist()]
        base = theme.palette[0]
        if hl_set:
            return [theme.accent if i in hl_set else base for i in range(n)]
        return [base] * n

    def _draw_edges(self, ctx, px, py, radii, weighted):
        theme = ctx.theme
        m = len(self.src)
        if m == 0:
            return
        s, d = self.src, self.dst
        ecol = theme.edge_color
        hl_col = theme.accent if theme.family != "folio" else theme.ink
        if m > VECTOR_EDGES:
            rs = ctx.raster_scale
            plot = ctx.plot
            rows, cols = int(plot.h * rs), int(plot.w * rs)
            X = (px - plot.x) / plot.w
            Y = 1 - (py - plot.y) / plot.h
            grid = bin_segments(X[s], Y[s], X[d], Y[d], (0, 1), (0, 1), (rows, cols))
            img = shade(grid, rgb_array([ecol])[0], "log", min_alpha=0.12, spread_px=0)
            ctx.scene.add(S.Image(plot.x, plot.y, plot.w, plot.h, img))
            for a, b in self.hl_edges:
                ctx.scene.add(S.Line(px[a], py[a], px[b], py[b], hl_col, 2.4, cap="round"))
            return
        if weighted:
            wmin, wmax = float(self.w.min()), float(self.w.max())
            widths = 0.8 + 2.2 * (self.w - wmin) / ((wmax - wmin) or 1)
        else:
            widths = np.full(m, 1.0 if m < 400 else 0.6)
        curved = theme.edge_style == "curved"
        xs_unique = np.unique(np.round(self.pos[:, 0], 6))
        self._layer_step = float(np.diff(xs_unique).min()) if len(xs_unique) > 1 else 1.0
        show_w = self.edge_labels is True or (is_auto(self.edge_labels) and weighted and m <= 30)
        same_group = None
        if self.group_of is not None and theme.node_style == "sized":
            same_group = self.group_of[s] == self.group_of[d]
        opacity = 1.0 if m < 300 else max(0.25, 300 / m)
        hl_draw, labels = [], []
        for e in range(m):
            a, b = int(s[e]), int(d[e])
            on = (a, b) in self.hl_edges
            x0, y0, x1, y1 = px[a], py[a], px[b], py[b]
            if a == b:
                continue
            col = ecol
            if same_group is not None and same_group[e]:
                col = mix(ctx.color(self.group_names[self.group_of[a]], int(self.group_of[a])), theme.background, 0.35)
            dx, dy = x1 - x0, y1 - y0
            L_ = math.hypot(dx, dy) or 1.0
            # stop arrows at the node border
            if self.directed_:
                ux, uy = abs(dx / L_), abs(dy / L_)
                if theme.node_style == "box":   # stop at the box border, not a circle
                    cut = min(self._hw[b] / ux if ux > 1e-9 else 1e9, self._hh[b] / uy if uy > 1e-9 else 1e9)
                else:
                    cut = radii[b]
                x1e, y1e = x1 - dx / L_ * (cut + 2), y1 - dy / L_ * (cut + 2)
            else:
                x1e, y1e = x1, y1
            # layered drawings: arcs for edges that skip a layer, so they don't hide behind others
            skip = getattr(self, "layered_", False) and abs(self.pos[b, 0] - self.pos[a, 0]) > self._layer_step * 1.5
            if curved or skip:
                bend = min(24, L_ * 0.12) if not skip else min(80, L_ * 0.25)
                cx, cy = (x0 + x1) / 2 - dy / L_ * bend, (y0 + y1) / 2 + dx / L_ * bend
                cmds = [("M", x0, y0), ("Q", cx, cy, x1e, y1e)]
                mx, my = 0.25 * x0 + 0.5 * cx + 0.25 * x1, 0.25 * y0 + 0.5 * cy + 0.25 * y1
            else:
                cmds = [("M", x0, y0), ("L", x1e, y1e)]
                mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            title = f"{self.nodes[a]} – {self.nodes[b]}" + (f": {format_value(self.w[e])}" if weighted else "")
            op = S.Path(cmds, stroke=hl_col if on else col, stroke_width=(max(2.6, widths[e] + 1) if on else widths[e]),
                        opacity=1.0 if on else opacity, arrow=self.directed_, title=title if m <= 500 else None)
            (hl_draw if on else ctx.scene.ops).append(op)
            if show_w:
                labels.append((mx, my, self.w[e], on))
        ctx.scene.extend(hl_draw)
        for mx, my, w, on in labels:
            self._edge_label(ctx, mx, my, w, on, hl_col)

    def _edge_label(self, ctx, x, y, w, on, hl_col):
        theme = ctx.theme
        txt = format_value(w)
        size = theme.font_size - 1
        if theme.node_style == "box":
            r = 8
            half = max(r, text_width(txt, size, theme.font_kind, True) / 2 + 4)   # pill grows with the text
            ctx.scene.add(S.Rect(x - half, y - r, 2 * half, 2 * r,
                                 fill=hl_col if on else mix(theme.background, theme.ink, 0.05),
                                 stroke=theme.background, stroke_width=2, rx=r))
            ctx.scene.add(S.Text(x, y, txt, size, readable_on(hl_col) if on else theme.ink_secondary,
                                 anchor="middle", baseline="middle", weight=600))
        elif theme.node_style == "ring":
            ctx.scene.add(S.Text(x + 5, y - 5, "w" + txt, size, hl_col if on else theme.ink_muted))
        else:
            ctx.scene.add(S.Text(x, y, txt, size, theme.ink_secondary, anchor="middle", baseline="middle",
                                 halo=theme.background))

    def _draw_nodes(self, ctx, px, py, radii, hl_set, show_labels, top_labels, short):
        theme = ctx.theme
        n = len(self.nodes)
        if n == 0:
            return
        colors = self._node_colors(ctx, hl_set)
        style = theme.node_style
        if n > VECTOR_NODES:
            plot = ctx.plot
            rs = ctx.raster_scale
            grid = bin_points((px - plot.x) / plot.w, 1 - (py - plot.y) / plot.h, (0, 1), (0, 1),
                              (int(plot.h * rs), int(plot.w * rs)))
            img = shade(grid, rgb_array([theme.palette[0]])[0], "eq_hist", min_alpha=0.5)
            ctx.scene.add(S.Image(plot.x, plot.y, plot.w, plot.h, img))
            return
        size = theme.font_size
        labels = [str(v) for v in self.nodes]
        titles = [f"{labels[i]} · degree {int(self.deg[i])}" for i in range(n)] if n <= 2000 else None
        if style == "box" and show_labels:
            for i in range(n):
                on = i in hl_set
                w = max(2 * radii[i] + 6, text_width(labels[i], size + 1, theme.font_kind, True) + 14)
                h = 2 * radii[i]
                fill = colors[i] if (on or self.group_of is not None) else theme.background
                stroke = colors[i] if (on or self.group_of is not None) else mix(theme.ink, theme.background, 0.7)
                ctx.scene.add(S.Rect(px[i] - w / 2, py[i] - h / 2, w, h, fill=fill, stroke=stroke, stroke_width=1.3,
                                     rx=6, title=titles[i] if titles else None))
                ctx.scene.add(S.Text(px[i], py[i], labels[i], size + 1, readable_on(fill) if fill != theme.background
                                     else theme.ink, anchor="middle", baseline="middle", weight=600))
            return
        if style == "circle":
            fills = [theme.ink if i in hl_set else (colors[i] if self.group_of is not None else theme.background)
                     for i in range(n)]
            ctx.scene.add(S.Markers(px, py, "circle", radii, fill=fills, stroke=theme.ink, stroke_width=1.1,
                                    titles=titles))
        elif style == "ring":
            ctx.scene.add(S.Markers(px, py, "circle", np.minimum(radii, 8), fill=theme.background,
                                    stroke=[theme.accent if i in hl_set else colors[i] for i in range(n)],
                                    stroke_width=1.8, titles=titles))
            if hl_set:
                idx = np.array(sorted(hl_set))
                ctx.scene.add(S.Markers(px[idx], py[idx], "circle", 2.5, fill=theme.accent))
        else:  # sized / default filled
            ring = float(min(2.2, max(0.4, radii.min() * 0.35)))
            ctx.scene.add(S.Markers(px, py, "circle", radii, fill=colors, stroke=theme.background, stroke_width=ring,
                                    titles=titles))
            if hl_set:
                idx = np.array(sorted(hl_set))
                ctx.scene.add(S.Markers(px[idx], py[idx], "circle", radii[idx] + 3, fill=None, stroke=theme.ink,
                                        stroke_width=1.6))
        if not (show_labels or top_labels):
            return
        which = range(n) if show_labels else np.argsort(-self.deg)[:12].tolist()
        for i in which:
            lab = labels[i]
            inside = short and style in ("circle", "sized") and radii[i] >= 8
            if inside:
                fill = fills[i] if style == "circle" else colors[i]
                col = readable_on(fill) if fill != theme.background else theme.ink
                ctx.scene.add(S.Text(px[i], py[i], lab,
                                     size + (1.5 if style == "circle" else 0.5), col, anchor="middle", baseline="middle",
                                     italic=theme.italic_labels, weight=700 if style == "sized" else 400))
            else:
                r = min(radii[i], 8) if style == "ring" else radii[i]
                ctx.scene.add(S.Text(px[i] + r + 3, py[i] + r + size * 0.5, lab, size, theme.ink,
                                     halo=theme.background, italic=theme.italic_labels))
        if style == "ring" and self.hl_nodes and len(self.hl_nodes) > 1:
            cost = getattr(self, "path_cost", None)
            txt = "PATH " + "→".join(map(str, self.hl_nodes)) + (f"  Σw={format_value(cost)}" if cost is not None else "")
            ctx.scene.add(S.Text(ctx.plot.right, ctx.plot.bottom, txt, size, theme.accent, anchor="end"))
