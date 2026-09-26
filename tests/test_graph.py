import numpy as np
import pytest

import lineova as lv
from lineova import GraphError, layout

nx = pytest.importorskip("networkx")

EDGES = [("A", "B", 4), ("A", "C", 3), ("B", "D", 5), ("C", "D", 2), ("B", "E", 6), ("D", "E", 4),
         ("D", "G", 3), ("C", "F", 6), ("F", "G", 4), ("E", "H", 5), ("G", "H", 3), ("G", "I", 5),
         ("F", "I", 7), ("E", "G", 2)]


def test_basic_counts():
    g = lv.Graph.from_edges(EDGES)
    assert len(g) == 9 and g.number_of_edges() == 14
    assert g.degree("D") == 4 and set(g.neighbors("A")) == {"B", "C"}


def test_shortest_path_matches_networkx():
    g = lv.Graph.from_edges(EDGES)
    path = g.shortest_path("A", "I")
    assert path == ["A", "C", "D", "G", "I"] and g.path_weight(path) == 13
    G = nx.Graph()
    G.add_weighted_edges_from(EDGES)
    assert g.distance("A", "I") == nx.shortest_path_length(G, "A", "I", weight="weight")


@pytest.mark.parametrize("seed", range(5))
def test_random_graphs_against_networkx(seed):
    rng = np.random.default_rng(seed)
    edges = [(int(a), int(b), float(w)) for a, b, w in zip(rng.integers(0, 60, 200), rng.integers(0, 60, 200),
                                                             rng.integers(1, 20, 200)) if a != b]
    g = lv.Graph.from_edges(edges)
    G = nx.Graph()
    for a, b, w in edges:
        G.add_edge(a, b, weight=w)       # last write wins, same as Graph
    src = edges[0][0]
    dist, _ = g.shortest_paths(src)
    ref = nx.single_source_dijkstra_path_length(G, src)
    assert dist == pytest.approx(ref)
    assert sorted(map(len, g.connected_components())) == sorted(map(len, nx.connected_components(G)))
    mst = g.minimum_spanning_tree()
    ref_w = sum(d["weight"] for *_, d in nx.minimum_spanning_edges(G, data=True))
    assert sum(w for *_, w in mst.edges) == pytest.approx(ref_w)


def test_directed_topological_and_cycles():
    g = lv.Graph.from_edges([("a", "b"), ("b", "c"), ("a", "c")], directed=True)
    order = g.topological_sort()
    assert order.index("a") < order.index("b") < order.index("c")
    assert not g.has_cycle()
    g.add_edge("c", "a")
    assert g.has_cycle()
    with pytest.raises(GraphError, match="cycle"):
        g.topological_sort()


def test_undirected_cycle_detection():
    assert not lv.Graph.from_edges([(1, 2), (2, 3)]).has_cycle()
    assert lv.Graph.from_edges([(1, 2), (2, 3), (3, 1)]).has_cycle()


def test_bfs_dfs_orders():
    g = lv.Graph.from_edges([(1, 2), (1, 3), (2, 4), (3, 5)])
    assert g.bfs(1) == [1, 2, 3, 4, 5]
    assert g.dfs(1) == [1, 2, 4, 3, 5]


def test_unreachable_and_missing_node():
    g = lv.Graph.from_edges([(1, 2), (3, 4)])
    with pytest.raises(GraphError, match="No path"):
        g.shortest_path(1, 4)
    with pytest.raises(GraphError, match="No node"):
        g.neighbors(99)


def test_remove_and_subgraph():
    g = lv.Graph.from_edges(EDGES)
    g.remove_node("D")
    assert "D" not in g and g.number_of_edges() == 10
    assert len(g.subgraph(["A", "B", "C"]).edges) == 2


def test_communities_split_two_cliques():
    edges = [(a, b) for a in range(5) for b in range(a + 1, 5)] + \
            [(a, b) for a in range(5, 10) for b in range(a + 1, 10)] + [(4, 5)]
    comms = lv.Graph.from_edges(edges).communities()
    assert len(comms) == 2


def test_from_networkx_and_adjacency():
    G = nx.path_graph(4)
    assert lv.Graph.from_networkx(G).number_of_edges() == 3
    g = lv.Graph.from_adjacency({"a": ["b", "c"], "b": {"c": 2.0}})
    assert g.weight("b", "c") == 2.0


@pytest.mark.parametrize("n", [1, 2, 50, 2000])
def test_force_layout_is_finite_and_normalised(n, rng):
    src, dst = rng.integers(0, n, (2, n * 2))
    p = layout.force(n, src, dst, iterations=20)
    assert p.shape == (n, 2) and np.isfinite(p).all() and p.min() >= 0 and p.max() <= 1


def test_layered_layout_orders_dag():
    p = layout.layered(3, np.array([0, 1]), np.array([1, 2]))
    assert p[0, 0] < p[1, 0] < p[2, 0]


@pytest.fixture
def weighted_digraph():
    G = nx.gnp_random_graph(50, 0.1, seed=4, directed=True)
    for u, v in G.edges:
        G[u][v]["weight"] = float((u * 7 + v) % 5 + 1)
    return G


def test_pagerank_matches_networkx(weighted_digraph):
    pytest.importorskip("scipy")          # networkx.pagerank needs scipy
    ref = nx.pagerank(weighted_digraph, weight="weight")
    got = lv.Graph.from_networkx(weighted_digraph).pagerank()
    assert max(abs(got[k] - ref[k]) for k in ref) < 1e-5


@pytest.mark.parametrize("weighted", [True, False])
def test_betweenness_matches_networkx(weighted_digraph, weighted):
    ref = nx.betweenness_centrality(weighted_digraph, weight="weight" if weighted else None)
    got = lv.Graph.from_networkx(weighted_digraph).betweenness(weighted=weighted)
    assert max(abs(got[k] - ref[k]) for k in ref) < 1e-9
    U = weighted_digraph.to_undirected()
    ref = nx.betweenness_centrality(U, weight="weight" if weighted else None)
    got = lv.Graph.from_networkx(U).betweenness(weighted=weighted)
    assert max(abs(got[k] - ref[k]) for k in ref) < 1e-9


def test_closeness_scc_flow_astar(weighted_digraph):
    g = lv.Graph.from_networkx(weighted_digraph)
    ref = nx.closeness_centrality(weighted_digraph.reverse(), distance="weight")
    got = g.closeness()
    assert max(abs(got[k] - ref[k]) for k in ref) < 1e-9
    assert sorted(map(len, g.strongly_connected_components())) == \
        sorted(map(len, nx.strongly_connected_components(weighted_digraph)))
    value, flow = g.max_flow(0, 7)
    assert value == pytest.approx(nx.maximum_flow_value(weighted_digraph, 0, 7, capacity="weight"))
    U = weighted_digraph.to_undirected()
    gu = lv.Graph.from_networkx(U)
    assert gu.path_weight(gu.astar(0, 7)) == pytest.approx(nx.shortest_path_length(U, 0, 7, weight="weight"))


def test_astar_uses_positions():
    g = lv.Graph()
    for n, p in {"a": (0, 0), "b": (1, 0), "c": (2, 0), "d": (1, 5)}.items():
        g.add_node(n, pos=p)
    g.add_edges([("a", "b", 1), ("b", "c", 1), ("a", "d", 5), ("d", "c", 5)])
    assert g.astar("a", "c") == ["a", "b", "c"]


def test_network_sized_by_centrality():
    g = lv.Graph.from_edges([("a", "b"), ("b", "c"), ("c", "d"), ("b", "e")])
    lv.network(g, node_size="betweenness").to_svg()
    lv.network(g, node_size="pagerank").to_svg()
