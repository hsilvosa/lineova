"""A small, dependency-free graph data structure with the classic algorithms.

    g = lv.Graph.from_edges([("A", "B", 4), ("A", "C", 3), ("C", "D", 2)])
    g.shortest_path("A", "D")        # ['A', 'C', 'D']
    g.draw(highlight=g.shortest_path("A", "D")).save("route.svg")
"""

from __future__ import annotations

import heapq
from collections import deque
from typing import Hashable, Iterable, Iterator, Optional

import numpy as np

Node = Hashable


class GraphError(ValueError):
    pass


class Graph:
    """Directed or undirected weighted graph (adjacency dict of dicts)."""

    def __init__(self, edges: Optional[Iterable] = None, *, directed: bool = False):
        self.directed = directed
        self._adj: dict[Node, dict[Node, float]] = {}
        self._pred: dict[Node, dict[Node, float]] = {} if directed else self._adj
        self._attrs: dict[Node, dict] = {}
        if edges is not None:
            self.add_edges(edges)

    # ------------------------------------------------------------------ building
    @classmethod
    def from_edges(cls, edges: Iterable, *, directed: bool = False) -> "Graph":
        """Edges as (u, v) or (u, v, weight) tuples, or an (m, 2|3) array."""
        return cls(edges, directed=directed)

    @classmethod
    def from_adjacency(cls, adjacency: dict, *, directed: bool = False) -> "Graph":
        """``{'A': ['B', 'C']}`` or ``{'A': {'B': 2.5}}``."""
        g = cls(directed=directed)
        for u, nbrs in adjacency.items():
            g.add_node(u)
            if isinstance(nbrs, dict):
                for v, w in nbrs.items():
                    g.add_edge(u, v, w)
            else:
                for v in nbrs:
                    g.add_edge(u, v)
        return g

    @classmethod
    def from_networkx(cls, G) -> "Graph":
        g = cls(directed=G.is_directed())
        for n, attrs in G.nodes(data=True):
            g.add_node(n, **attrs)
        for u, v, d in G.edges(data=True):
            g.add_edge(u, v, d.get("weight", 1.0))
        return g

    def add_node(self, n: Node, **attrs) -> "Graph":
        if n not in self._adj:
            self._adj[n] = {}
            if self.directed:
                self._pred[n] = {}
        if attrs:
            self._attrs.setdefault(n, {}).update(attrs)
        return self

    def add_edge(self, u: Node, v: Node, weight: float = 1.0) -> "Graph":
        w = float(weight)
        if w != w:
            raise GraphError(f"Edge {u!r}–{v!r} has a NaN weight.")
        self.add_node(u)
        self.add_node(v)
        self._adj[u][v] = w
        if self.directed:
            self._pred[v][u] = w
        else:
            self._adj[v][u] = w
        return self

    def add_edges(self, edges: Iterable) -> "Graph":
        if isinstance(edges, np.ndarray):
            edges = edges.tolist()
        for e in edges:
            if len(e) == 2:
                self.add_edge(e[0], e[1])
            elif len(e) >= 3:
                self.add_edge(e[0], e[1], e[2])
            else:
                raise GraphError(f"Edge {e!r} must be (u, v) or (u, v, weight).")
        return self

    def remove_edge(self, u: Node, v: Node) -> "Graph":
        try:
            del self._adj[u][v]
            if self.directed:
                del self._pred[v][u]
            else:
                del self._adj[v][u]
        except KeyError:
            raise GraphError(f"No edge {u!r}–{v!r}.") from None
        return self

    def remove_node(self, n: Node) -> "Graph":
        if n not in self._adj:
            raise GraphError(f"No node {n!r}.")
        for v in list(self._adj[n]):
            self.remove_edge(n, v)
        if self.directed:
            for u in list(self._pred[n]):
                self.remove_edge(u, n)
            del self._pred[n]
        del self._adj[n]
        self._attrs.pop(n, None)
        return self

    # ------------------------------------------------------------------ inspection
    @property
    def nodes(self) -> list:
        return list(self._adj)

    @property
    def edges(self) -> list[tuple]:
        if self.directed:
            return [(u, v, w) for u, nb in self._adj.items() for v, w in nb.items()]
        seen, out = set(), []
        for u, nb in self._adj.items():
            for v, w in nb.items():
                key = (v, u)
                if key in seen:
                    continue
                seen.add((u, v))
                out.append((u, v, w))
        return out

    def __len__(self) -> int:
        return len(self._adj)

    def __contains__(self, n) -> bool:
        return n in self._adj

    def __iter__(self) -> Iterator:
        return iter(self._adj)

    def __repr__(self) -> str:
        kind = "directed" if self.directed else "undirected"
        return f"<Graph {kind}, {len(self)} nodes, {self.number_of_edges()} edges>"

    def number_of_edges(self) -> int:
        m = sum(len(nb) for nb in self._adj.values())
        if not self.directed:
            loops = sum(1 for u, nb in self._adj.items() if u in nb)
            m = (m + loops) // 2
        return m

    def neighbors(self, n: Node) -> list:
        self._check(n)
        return list(self._adj[n])

    def predecessors(self, n: Node) -> list:
        self._check(n)
        return list(self._pred[n])

    def has_edge(self, u, v) -> bool:
        return u in self._adj and v in self._adj[u]

    def weight(self, u, v) -> float:
        try:
            return self._adj[u][v]
        except KeyError:
            raise GraphError(f"No edge {u!r}–{v!r}.") from None

    def degree(self, n: Optional[Node] = None):
        """Degree of one node, or a dict for all nodes (in + out for directed graphs)."""
        if n is not None:
            self._check(n)
            return len(self._adj[n]) + (len(self._pred[n]) if self.directed else 0)
        return {k: self.degree(k) for k in self._adj}

    def attrs(self, n: Node) -> dict:
        return dict(self._attrs.get(n, {}))

    def is_weighted(self) -> bool:
        ws = {w for nb in self._adj.values() for w in nb.values()}
        return len(ws) > 1 or (len(ws) == 1 and ws != {1.0})

    def _check(self, n):
        if n not in self._adj:
            raise GraphError(f"No node {n!r} in the graph.")

    # ------------------------------------------------------------------ traversal
    def bfs(self, start: Node) -> list:
        """Nodes in breadth-first order from ``start``."""
        self._check(start)
        seen, order, q = {start}, [], deque([start])
        while q:
            u = q.popleft()
            order.append(u)
            for v in self._adj[u]:
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        return order

    def dfs(self, start: Node) -> list:
        """Nodes in depth-first (pre-)order from ``start``. Iterative: no recursion limit."""
        self._check(start)
        seen, order, stack = set(), [], [start]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            order.append(u)
            stack.extend(v for v in reversed(list(self._adj[u])) if v not in seen)
        return order

    def shortest_paths(self, source: Node, weighted: bool = True) -> tuple[dict, dict]:
        """Distances and predecessors from ``source`` (Dijkstra, or BFS if unweighted)."""
        self._check(source)
        dist, prev = {source: 0.0}, {}
        if not weighted:
            q = deque([source])
            while q:
                u = q.popleft()
                for v in self._adj[u]:
                    if v not in dist:
                        dist[v], prev[v] = dist[u] + 1, u
                        q.append(v)
            return dist, prev
        heap, done, counter = [(0.0, 0, source)], set(), 1
        while heap:
            d, _, u = heapq.heappop(heap)
            if u in done:
                continue
            done.add(u)
            for v, w in self._adj[u].items():
                if w < 0:
                    raise GraphError("Dijkstra needs non-negative weights.")
                nd = d + w
                if nd < dist.get(v, float("inf")):
                    dist[v], prev[v] = nd, u
                    heapq.heappush(heap, (nd, counter, v))
                    counter += 1
        return dist, prev

    def shortest_path(self, source: Node, target: Node, weighted: bool = True) -> list:
        """Cheapest path as a list of nodes. Raises ``GraphError`` if unreachable."""
        self._check(target)
        dist, prev = self.shortest_paths(source, weighted)
        if target not in dist:
            raise GraphError(f"No path from {source!r} to {target!r}.")
        path = [target]
        while path[-1] != source:
            path.append(prev[path[-1]])
        return path[::-1]

    def distance(self, source: Node, target: Node, weighted: bool = True) -> float:
        dist, _ = self.shortest_paths(source, weighted)
        if target not in dist:
            return float("inf")
        return dist[target]

    def path_weight(self, path: list) -> float:
        return sum(self.weight(a, b) for a, b in zip(path, path[1:]))

    # ------------------------------------------------------------------ structure
    def connected_components(self) -> list[set]:
        """Components, largest first (weakly connected for directed graphs)."""
        seen, comps = set(), []
        for s in self._adj:
            if s in seen:
                continue
            comp, q = {s}, deque([s])
            seen.add(s)
            while q:
                u = q.popleft()
                nbrs = list(self._adj[u]) + (list(self._pred[u]) if self.directed else [])
                for v in nbrs:
                    if v not in seen:
                        seen.add(v)
                        comp.add(v)
                        q.append(v)
            comps.append(comp)
        return sorted(comps, key=len, reverse=True)

    def is_connected(self) -> bool:
        return len(self) > 0 and len(self.connected_components()) == 1

    def topological_sort(self) -> list:
        """Kahn's algorithm. Raises ``GraphError`` on cycles or undirected graphs."""
        if not self.directed:
            raise GraphError("Topological order needs a directed graph.")
        indeg = {n: len(self._pred[n]) for n in self._adj}
        q = deque(n for n, d in indeg.items() if d == 0)
        order = []
        while q:
            u = q.popleft()
            order.append(u)
            for v in self._adj[u]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
        if len(order) != len(self):
            raise GraphError("The graph has a cycle, so it has no topological order.")
        return order

    def has_cycle(self) -> bool:
        if self.directed:
            try:
                self.topological_sort()
                return False
            except GraphError:
                return True
        parent: dict = {}

        def find(x):
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        for u, v, _ in self.edges:
            if u == v:
                return True
            ru, rv = find(u), find(v)
            if ru == rv:
                return True
            parent[ru] = rv
        return False

    def minimum_spanning_tree(self) -> "Graph":
        """Kruskal. For a disconnected graph, returns a spanning forest."""
        if self.directed:
            raise GraphError("Minimum spanning trees are defined for undirected graphs.")
        parent = {n: n for n in self._adj}
        rank = dict.fromkeys(self._adj, 0)

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        tree = Graph()
        for n in self._adj:
            tree.add_node(n, **self._attrs.get(n, {}))
        for u, v, w in sorted(self.edges, key=lambda e: e[2]):
            ru, rv = find(u), find(v)
            if ru == rv:
                continue
            if rank[ru] < rank[rv]:
                ru, rv = rv, ru
            parent[rv] = ru
            rank[ru] += rank[ru] == rank[rv]
            tree.add_edge(u, v, w)
        return tree

    def communities(self, seed: int = 0, max_iter: int = 30) -> list[set]:
        """Groups of densely connected nodes (label propagation). Fast, approximate."""
        rng = np.random.default_rng(seed)
        nodes = list(self._adj)
        label = {n: i for i, n in enumerate(nodes)}
        for _ in range(max_iter):
            changed = False
            for idx in rng.permutation(len(nodes)):
                n = nodes[idx]
                nbrs = self._adj[n] if not self.directed else {**self._adj[n], **self._pred[n]}
                if not nbrs:
                    continue
                score: dict = {}
                for v, w in nbrs.items():
                    score[label[v]] = score.get(label[v], 0.0) + abs(w)
                best = max(score.values())
                cands = sorted(l for l, s in score.items() if s == best)
                new = label[n] if label[n] in cands else cands[0]
                if new != label[n]:
                    label[n] = new
                    changed = True
            if not changed:
                break
        groups: dict = {}
        for n, l in label.items():
            groups.setdefault(l, set()).add(n)
        return sorted(groups.values(), key=len, reverse=True)

    # ------------------------------------------------------------------ centrality & flows
    def pagerank(self, damping: float = 0.85, tol: float = 1e-10, max_iter: int = 200) -> dict:
        """PageRank (power iteration, vectorised). Edge weights are used as link strength."""
        nodes, src, dst, w = self.to_arrays()
        n = len(nodes)
        if n == 0:
            return {}
        if not self.directed:
            src, dst, w = np.concatenate([src, dst]), np.concatenate([dst, src]), np.concatenate([w, w])
        out_w = np.bincount(src, w, minlength=n)
        dangling = out_w == 0
        r = np.full(n, 1.0 / n)
        for _ in range(max_iter):
            share = np.where(dangling, 0.0, r / np.where(out_w == 0, 1, out_w))
            new = np.bincount(dst, share[src] * w, minlength=n)
            new = damping * (new + r[dangling].sum() / n) + (1 - damping) / n
            if np.abs(new - r).sum() < tol * n:
                r = new
                break
            r = new
        return dict(zip(nodes, (r / r.sum()).tolist()))

    def betweenness(self, weighted: bool = True, normalized: bool = True) -> dict:
        """Betweenness centrality (Brandes): how often a node lies on shortest paths."""
        nodes = self.nodes
        bc = dict.fromkeys(nodes, 0.0)
        use_w = weighted and self.is_weighted()
        for s in nodes:
            stack, pred = [], {v: [] for v in nodes}
            sigma = dict.fromkeys(nodes, 0.0)
            sigma[s] = 1.0
            dist = {s: 0.0}
            if use_w:
                heap, seen, c = [(0.0, 0, s, s)], set(), 1
                while heap:
                    d, _, pr, v = heapq.heappop(heap)
                    if v in seen:
                        continue
                    if pr != v:
                        sigma[v] += sigma[pr]
                    seen.add(v)
                    stack.append(v)
                    for u, wt in self._adj[v].items():
                        nd = d + wt
                        if u not in seen and (u not in dist or nd < dist[u] - 1e-12):
                            dist[u] = nd
                            heapq.heappush(heap, (nd, c, v, u))
                            c += 1
                            sigma[u] = 0.0
                            pred[u] = [v]
                        elif u not in seen and abs(nd - dist[u]) <= 1e-12:
                            sigma[u] += sigma[v]
                            pred[u].append(v)
            else:
                q = deque([s])
                while q:
                    v = q.popleft()
                    stack.append(v)
                    for u in self._adj[v]:
                        if u not in dist:
                            dist[u] = dist[v] + 1
                            q.append(u)
                        if dist[u] == dist[v] + 1:
                            sigma[u] += sigma[v]
                            pred[u].append(v)
            delta = dict.fromkeys(nodes, 0.0)
            while stack:
                w_ = stack.pop()
                for v in pred[w_]:
                    delta[v] += sigma[v] / sigma[w_] * (1 + delta[w_]) if sigma[w_] else 0.0
                if w_ != s:
                    bc[w_] += delta[w_]
        n = len(nodes)
        if not self.directed:
            bc = {k: v / 2 for k, v in bc.items()}
        if normalized and n > 2:
            scale = 1 / ((n - 1) * (n - 2)) * (1 if self.directed else 2)
            bc = {k: v * scale for k, v in bc.items()}
        return bc

    def closeness(self, weighted: bool = True) -> dict:
        """Closeness centrality (Wasserman–Faust, handles disconnected graphs)."""
        n = len(self)
        out = {}
        for v in self._adj:
            dist, _ = self.shortest_paths(v, weighted and self.is_weighted())
            reach = len(dist) - 1
            total = sum(dist.values())
            out[v] = (reach / total) * (reach / (n - 1)) if total > 0 and n > 1 else 0.0
        return out

    def strongly_connected_components(self) -> list[set]:
        """Tarjan's algorithm (iterative). For undirected graphs this equals connected_components()."""
        if not self.directed:
            return self.connected_components()
        index, low, on, stack, comps = {}, {}, set(), [], []
        counter = 0
        for root in self._adj:
            if root in index:
                continue
            work = [(root, iter(self._adj[root]))]
            index[root] = low[root] = counter
            counter += 1
            stack.append(root)
            on.add(root)
            while work:
                v, it = work[-1]
                advanced = False
                for u in it:
                    if u not in index:
                        index[u] = low[u] = counter
                        counter += 1
                        stack.append(u)
                        on.add(u)
                        work.append((u, iter(self._adj[u])))
                        advanced = True
                        break
                    if u in on:
                        low[v] = min(low[v], index[u])
                if advanced:
                    continue
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[v])
                if low[v] == index[v]:
                    comp = set()
                    while True:
                        u = stack.pop()
                        on.discard(u)
                        comp.add(u)
                        if u == v:
                            break
                    comps.append(comp)
        return sorted(comps, key=len, reverse=True)

    def max_flow(self, source: Node, sink: Node) -> tuple[float, dict]:
        """Maximum flow (Edmonds–Karp); edge weights are capacities. Returns (value, {(u, v): flow})."""
        self._check(source)
        self._check(sink)
        cap: dict = {}
        for u, nb in self._adj.items():
            for v, w in nb.items():
                cap[(u, v)] = cap.get((u, v), 0.0) + w
        res = dict(cap)
        adj: dict = {u: set() for u in self._adj}
        for u, v in cap:
            adj[u].add(v)
            adj[v].add(u)
            res.setdefault((v, u), 0.0)
        value = 0.0
        while True:
            parent = {source: None}
            q = deque([source])
            while q and sink not in parent:
                u = q.popleft()
                for v in adj[u]:
                    if v not in parent and res[(u, v)] > 1e-12:
                        parent[v] = u
                        q.append(v)
            if sink not in parent:
                break
            f, v = float("inf"), sink
            while parent[v] is not None:
                f = min(f, res[(parent[v], v)])
                v = parent[v]
            v = sink
            while parent[v] is not None:
                res[(parent[v], v)] -= f
                res[(v, parent[v])] += f
                v = parent[v]
            value += f
        flow = {e: c - res[e] for e, c in cap.items() if c - res[e] > 1e-12}
        return value, flow

    def astar(self, source: Node, target: Node, heuristic=None) -> list:
        """A* shortest path. ``heuristic(node, target)`` must never overestimate the remaining cost.
        Without one, nodes' ``pos=(x, y)`` attributes give a Euclidean heuristic; otherwise it's Dijkstra."""
        self._check(source)
        self._check(target)
        if heuristic is None:
            if all("pos" in self._attrs.get(n, {}) for n in (source, target)):
                tp = self._attrs[target]["pos"]

                def heuristic(n, _t):
                    p = self._attrs.get(n, {}).get("pos")
                    return float(np.hypot(p[0] - tp[0], p[1] - tp[1])) if p is not None else 0.0
            else:
                def heuristic(n, _t):
                    return 0.0
        g = {source: 0.0}
        prev: dict = {}
        heap, c = [(heuristic(source, target), 0, source)], 1
        done = set()
        while heap:
            _, _, u = heapq.heappop(heap)
            if u == target:
                path = [u]
                while path[-1] != source:
                    path.append(prev[path[-1]])
                return path[::-1]
            if u in done:
                continue
            done.add(u)
            for v, w in self._adj[u].items():
                nd = g[u] + w
                if nd < g.get(v, float("inf")):
                    g[v], prev[v] = nd, u
                    heapq.heappush(heap, (nd + heuristic(v, target), c, v))
                    c += 1
        raise GraphError(f"No path from {source!r} to {target!r}.")

    def subgraph(self, nodes: Iterable) -> "Graph":
        keep = set(nodes)
        g = Graph(directed=self.directed)
        for n in keep:
            g.add_node(n, **self._attrs.get(n, {}))
        for u, v, w in self.edges:
            if u in keep and v in keep:
                g.add_edge(u, v, w)
        return g

    def to_arrays(self) -> tuple[list, np.ndarray, np.ndarray, np.ndarray]:
        """(nodes, src_index, dst_index, weights) for fast numeric work."""
        nodes = self.nodes
        pos = {n: i for i, n in enumerate(nodes)}
        e = self.edges
        src = np.fromiter((pos[u] for u, _, _ in e), dtype=np.int64, count=len(e))
        dst = np.fromiter((pos[v] for _, v, _ in e), dtype=np.int64, count=len(e))
        w = np.fromiter((w for _, _, w in e), dtype=np.float64, count=len(e))
        return nodes, src, dst, w

    def draw(self, **options):
        """Shortcut for ``lv.network(graph, **options)``."""
        from .api import network
        return network(self, **options)
