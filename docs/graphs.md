# Graphs

`lv.Graph` is a small, dependency-free graph data structure with the classic algorithms. `lv.network` draws graphs.

```python
import lineova as lv

g = lv.Graph.from_edges([
    ("A", "B", 4), ("A", "C", 3), ("B", "D", 5), ("C", "D", 2), ("D", "E", 4),
])
g.shortest_path("A", "E")            # ['A', 'C', 'D', 'E']
g.distance("A", "E")                 # 9.0
g.draw(path=("A", "E")).save("route.svg")
```

## Building graphs

| From | Call |
|---|---|
| Edge list | `Graph.from_edges([(u, v), (u, v, weight), ...], directed=False)` |
| Adjacency | `Graph.from_adjacency({"a": ["b", "c"]})` or `{"a": {"b": 2.5}}` |
| networkx | `Graph.from_networkx(G)`, and back with `g.to_networkx()` |
| Step by step | `g.add_node(n, pos=(x, y))`, `g.add_edge(u, v, w)`, `g.remove_node(n)` |

## Algorithms

| Question | Method | Algorithm |
|---|---|---|
| Visit order | `bfs(start)`, `dfs(start)` | Breadth- / depth-first (iterative, no recursion limit) |
| Cheapest route | `shortest_path(a, b)`, `distance(a, b)`, `shortest_paths(a)` | Dijkstra (BFS when unweighted) |
| Cheapest route with a heuristic | `astar(a, b, heuristic=None)` | A*; uses node `pos` attributes if present |
| Pieces | `connected_components()`, `strongly_connected_components()`, `is_connected()` | BFS, Tarjan |
| Order of dependencies | `topological_sort()`, `has_cycle()` | Kahn |
| Cheapest way to connect everything | `minimum_spanning_tree()` | Kruskal with union–find |
| Clusters | `communities()`, `louvain(resolution=1.0)`, `modularity(parts)` | Label propagation; Louvain modularity optimisation |
| Dense cores | `core_numbers()`, `k_core(k=None)` | Peeling by degree |
| Triangles | `triangles()`, `clustering()`, `average_clustering()`, `transitivity()` | Neighbour-set intersection |
| Weak points | `articulation_points()`, `bridges()` | Tarjan low-link (iterative) |
| Size | `eccentricity()`, `diameter()` | BFS from every node (connected graphs) |
| Negative weights | `bellman_ford(source)` | Bellman-Ford; raises on a negative cycle |
| All pairs | `floyd_warshall()` | Vectorised Floyd-Warshall; returns `(nodes, matrix)` |
| Importance | `pagerank()`, `betweenness()`, `closeness()`, `degree()` | Power iteration, Brandes, Wasserman–Faust |
| Capacity | `max_flow(source, sink)` | Edmonds–Karp |

Results are tested against networkx.

## Drawing

```python
lv.network(g)                                     # automatic layout, labels and sizes
lv.network(g, path=("A", "E"))                    # highlight the cheapest route
lv.network(g, groups="community")                 # colour clusters
lv.network(g, node_size="pagerank")               # size by importance
lv.network(deps, directed=True)                   # small DAGs are drawn left to right in layers
lv.network(edges_df, layout="circular")           # force | circular | grid | layered | radial | bipartite | positions={...}
lv.network(tree, layout="radial", root="CEO")    # rings by distance from the root, branches share the angle
lv.network(pairs, layout="bipartite")             # two columns, ordered to reduce crossings; sets=[...] fixes the left one
lv.network(g, groups="louvain")                   # colour by modularity clusters
```

Large graphs are handled automatically. The force layout switches to an FFT-based approximation above 1,500 nodes, and edges are rasterised above 6,000, so 40,000 nodes and 200,000 edges draw in about 3 seconds.
