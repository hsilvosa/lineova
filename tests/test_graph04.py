import numpy as np
import pytest

import lineova as lv
from lineova import GraphError, layout

nx = pytest.importorskip("networkx")


def from_nx(G):
    g = lv.Graph.from_edges([(a, b) for a, b in G.edges()], directed=G.is_directed())
    for n in G.nodes():
        g.add_node(n)
    return g


@pytest.mark.parametrize("seed", range(5))
def test_structure_matches_networkx(seed):
    G = nx.gnp_random_graph(70, 0.06, seed=seed)
    g = from_nx(G)
    assert g.core_numbers() == nx.core_number(G)
    assert g.triangles() == nx.triangles(G)
    assert g.clustering() == pytest.approx(nx.clustering(G))
    assert g.average_clustering() == pytest.approx(nx.average_clustering(G))
    assert g.transitivity() == pytest.approx(nx.transitivity(G))
    assert g.articulation_points() == set(nx.articulation_points(G))
    assert {frozenset(b) for b in g.bridges()} == {frozenset(b) for b in nx.bridges(G)}


def test_k_core_and_diameter():
    G = nx.karate_club_graph()
    g = from_nx(G)
    top = max(nx.core_number(G).values())
    assert set(g.k_core().nodes) == set(nx.k_core(G).nodes()) and top == max(g.core_numbers().values())
    assert set(g.k_core(2).nodes) == set(nx.k_core(G, 2).nodes())
    assert g.diameter() == nx.diameter(G)
    assert g.eccentricity() == nx.eccentricity(G)
    assert lv.Graph(directed=False).k_core().nodes == []
    with pytest.raises(GraphError, match="not connected"):
        lv.Graph.from_edges([(1, 2), (3, 4)]).diameter()


def test_self_loops_and_directions_are_ignored_by_structure():
    g = lv.Graph.from_edges([(1, 2), (2, 3), (3, 1), (3, 3)], directed=True)
    assert g.core_numbers() == {1: 2, 2: 2, 3: 2}
    assert g.triangles() == {1: 1, 2: 1, 3: 1}


@pytest.mark.parametrize("seed", range(4))
def test_bellman_ford_matches_networkx_with_negative_edges(seed):
    rng = np.random.default_rng(seed)
    G = nx.DiGraph()
    # a DAG layer order guarantees no negative cycle
    for _ in range(120):
        a, b = sorted(rng.integers(0, 40, 2).tolist())
        if a != b:
            G.add_edge(a, b, weight=float(rng.integers(-4, 9)))
    g = lv.Graph.from_edges([(a, b, d["weight"]) for a, b, d in G.edges(data=True)], directed=True)
    src = next(iter(G.nodes))
    dist, pred = g.bellman_ford(src)
    ref = nx.single_source_bellman_ford_path_length(G, src)
    assert dist == pytest.approx(ref)
    for v, p in pred.items():
        if p is not None:
            assert dist[v] == pytest.approx(dist[p] + G[p][v]["weight"])


def test_bellman_ford_negative_cycle_and_undirected_negative_edge():
    g = lv.Graph.from_edges([("a", "b", 1), ("b", "c", -3), ("c", "a", 1)], directed=True)
    with pytest.raises(GraphError, match="negative cycle"):
        g.bellman_ford("a")
    with pytest.raises(GraphError, match="negative"):
        lv.Graph.from_edges([("a", "b", -1)]).bellman_ford("a")
    unreachable = lv.Graph.from_edges([("a", "b", 2)], directed=True)
    unreachable.add_node("z")
    assert "z" not in unreachable.bellman_ford("a")[0]


def test_floyd_warshall_matches_dijkstra_and_networkx():
    rng = np.random.default_rng(0)
    edges = [(int(a), int(b), float(w)) for a, b, w in zip(rng.integers(0, 25, 70), rng.integers(0, 25, 70),
                                                             rng.integers(1, 9, 70)) if a != b]
    g = lv.Graph.from_edges(edges)
    nodes, d = g.floyd_warshall()
    G = nx.Graph()
    for a, b, w in edges:
        G.add_edge(a, b, weight=w)
    for i, u in enumerate(nodes):
        ref = nx.single_source_dijkstra_path_length(G, u)
        for j, v in enumerate(nodes):
            assert d[i, j] == pytest.approx(ref.get(v, np.inf))
    assert np.allclose(d, d.T)
    assert g.floyd_warshall(weighted=False)[1].max() < np.inf
    neg = lv.Graph.from_edges([(0, 1, 1), (1, 2, -3), (2, 0, 1)], directed=True)
    with pytest.raises(GraphError):
        neg.floyd_warshall()


def test_modularity_matches_networkx_and_louvain_finds_planted_clusters():
    from networkx.algorithms import community as nc
    G = nx.planted_partition_graph(4, 15, 0.8, 0.02, seed=3)
    g = from_nx(G)
    parts = g.louvain(seed=0)
    assert g.modularity(parts) == pytest.approx(nc.modularity(G, [set(p) for p in parts]))
    assert sorted(len(p) for p in parts) == [15, 15, 15, 15]
    truth = [set(range(i * 15, (i + 1) * 15)) for i in range(4)]
    assert sorted(map(sorted, parts)) == sorted(map(sorted, truth))
    assert g.modularity(parts) > g.modularity(g.communities()) - 1e-9
    assert g.modularity([set(G.nodes)]) == pytest.approx(0.0)
    with pytest.raises(GraphError, match="cover"):
        g.modularity([{0, 1}])


def test_louvain_is_deterministic_and_handles_weights_and_edge_cases():
    g = lv.Graph.from_edges([("a", "b", 5), ("b", "c", 5), ("a", "c", 5), ("x", "y", 5), ("y", "z", 5), ("x", "z", 5),
                             ("c", "x", 0.1)])
    assert g.louvain(seed=1) == g.louvain(seed=1)
    assert sorted(map(sorted, g.louvain())) == [["a", "b", "c"], ["x", "y", "z"]]
    assert lv.Graph().louvain() == []
    iso = lv.Graph()
    for n in "abc":
        iso.add_node(n)
    assert sorted(map(len, iso.louvain())) == [1, 1, 1]
    assert lv.Graph.from_edges([(1, 2), (2, 3)], directed=True).louvain()


def test_to_networkx_round_trip():
    g = lv.Graph.from_edges([("a", "b", 2.5), ("b", "c", 1)], directed=True)
    g.add_node("lonely", note="x")
    G = g.to_networkx()
    assert G.is_directed() and G["a"]["b"]["weight"] == 2.5 and G.nodes["lonely"]["note"] == "x"
    back = lv.Graph.from_networkx(G)
    assert back.edges == g.edges and set(back.nodes) == set(g.nodes)


# ---------------------------------------------------------------- layouts

def test_radial_rings_follow_distance_from_the_root():
    src = np.array([0, 0, 0, 1, 1, 2])
    dst = np.array([1, 2, 3, 4, 5, 6])
    pos = layout.radial(7, src, dst, root=0)
    r = np.hypot(pos[:, 0] - pos[0, 0], pos[:, 1] - pos[0, 1])
    assert r[0] == pytest.approx(0)
    assert r[1] == pytest.approx(r[2]) and r[2] == pytest.approx(r[3])
    assert r[4] == pytest.approx(r[6]) and r[1] < r[4]
    assert layout.radial(0, src[:0], dst[:0]).shape == (0, 2)


def test_radial_handles_other_components():
    pos = layout.radial(6, np.array([0, 1, 3]), np.array([1, 2, 4]), root=0)    # node 5 is isolated
    assert pos.shape == (6, 2) and np.isfinite(pos).all()
    assert len({tuple(np.round(p, 6)) for p in pos}) == 6


def test_bipartite_columns_and_validation():
    src, dst = np.array([0, 0, 1, 2]), np.array([3, 4, 4, 5])
    pos = layout.bipartite(6, src, dst)
    assert set(np.round(pos[:, 0], 6)) == {0.0, 1.0}
    assert len(set(pos[[0, 1, 2], 0])) == 1 and len(set(pos[[3, 4, 5], 0])) == 1
    with pytest.raises(ValueError, match="not bipartite"):
        layout.bipartite(3, np.array([0, 1, 2]), np.array([1, 2, 0]))
    forced = layout.bipartite(3, np.array([0, 1, 2]), np.array([1, 2, 0]), left=[0])
    assert forced[0, 0] == 0 and forced[1, 0] == 1


@pytest.mark.parametrize("opts", [{"layout": "radial"}, {"layout": "radial", "root": "A"},
                                  {"layout": "bipartite", "sets": ["A", "B"]}, {"groups": "louvain"},
                                  {"layout": "bipartite"}])
def test_network_accepts_the_new_layouts(opts):
    import xml.etree.ElementTree as ET
    edges = [("A", "x"), ("A", "y"), ("B", "y"), ("B", "z")]
    ET.fromstring(lv.network(edges, **opts).to_svg())


def test_network_layout_errors():
    with pytest.raises(ValueError, match="root="):
        lv.network([("a", "b")], layout="radial", root="zzz").to_svg()
    with pytest.raises(ValueError, match="sets="):
        lv.network([("a", "b")], layout="bipartite", sets=["zzz"]).to_svg()
    with pytest.raises(ValueError, match="Unknown layout"):
        lv.network([("a", "b")], layout="spiral").to_svg()
