"""Node placement for network drawings. Vectorised NumPy; deterministic (seeded)."""

from __future__ import annotations

import math

import numpy as np


def force(n: int, src: np.ndarray, dst: np.ndarray, weights=None, *, iterations=None, seed: int = 0) -> np.ndarray:
    """Fruchterman–Reingold spring layout. Returns ``(n, 2)`` positions in [0, 1].

    Exact repulsion up to 1,500 nodes. Above that, repulsion is computed on a
    grid with an FFT convolution (particle-mesh method), so each step costs
    O(n + m + G² log G) instead of O(n²).
    """
    if n == 0:
        return np.zeros((0, 2))
    if n == 1:
        return np.array([[0.5, 0.5]])
    rng = np.random.default_rng(seed)
    pos = _spectral_init(n, src, dst, rng)
    k = 1.0 / math.sqrt(n)
    iters = iterations or int(min(300, max(60, 3000 / math.sqrt(n + 1))))
    t = 0.12
    cool = t / (iters + 1)
    exact = n <= 1500
    G = int(min(512, max(64, 2 * math.sqrt(n))))
    same = src == dst
    s, d = src[~same], dst[~same]
    w = np.ones(len(s)) if weights is None else np.asarray(weights, float)[~same]
    # stronger edges pull harder; normalise so weights don't explode the layout
    if len(w) and (w.max() > w.min()):
        w = 0.5 + (w - w.min()) / (w.max() - w.min())
    else:
        w = np.ones(len(s))
    for _ in range(iters):
        disp = np.zeros((n, 2))
        if exact:
            for a in range(0, n, 512):
                delta = pos[a:a + 512, None, :] - pos[None, :, :]
                dist2 = np.einsum("ijk,ijk->ij", delta, delta) + 1e-9
                disp[a:a + 512] += np.einsum("ijk,ij->ik", delta, (k * k) / dist2)
        else:
            disp += _mesh_repulsion(pos, k, G)
        if len(s):
            delta = pos[s] - pos[d]
            dist = np.sqrt(np.einsum("ij,ij->i", delta, delta)) + 1e-9
            f = (dist / k) * w
            fx, fy = delta[:, 0] * f, delta[:, 1] * f
            disp[:, 0] -= np.bincount(s, fx, n) - np.bincount(d, fx, n)
            disp[:, 1] -= np.bincount(s, fy, n) - np.bincount(d, fy, n)
        disp += (0.5 - pos) * (k * 0.5)          # gentle gravity keeps components together
        length = np.sqrt(np.einsum("ij,ij->i", disp, disp)) + 1e-9
        pos += disp / length[:, None] * np.minimum(length, t)[:, None]
        t -= cool
    return normalize(pos)


def _unit_kernels(G: int):
    """FFTs of the repulsion kernel in grid units (cached per grid size)."""
    cached = _KERNELS.get(G)
    if cached is None:
        off = np.fft.fftfreq(2 * G, 1.0 / (2 * G))
        dx, dy = np.meshgrid(off, off)
        r2 = dx * dx + dy * dy
        r2[0, 0] = np.inf
        r2 = np.maximum(r2, 0.25)
        cached = (np.fft.rfft2(dx / r2), np.fft.rfft2(dy / r2))
        _KERNELS[G] = cached
    return cached


_KERNELS: dict = {}


def _mesh_repulsion(pos: np.ndarray, k: float, G: int) -> np.ndarray:
    """Repulsive force k²/r from all other nodes, via density grid ⊛ kernel (FFT)."""
    lo = pos.min(axis=0)
    span = float((pos.max(axis=0) - lo).max()) or 1.0
    cell = span / (G - 1)
    ij = np.clip(((pos - lo) / cell).astype(np.int64), 0, G - 1)
    flat = ij[:, 1] * G + ij[:, 0]
    rho = np.bincount(flat, minlength=G * G).reshape(G, G).astype(np.float64)
    KX, KY = _unit_kernels(G)
    R = np.fft.rfft2(rho, s=(2 * G, 2 * G))
    scale = k * k / cell          # kernel in world units = (k²/cell) · kernel in grid units
    fx = np.fft.irfft2(R * KX, s=(2 * G, 2 * G))[:G, :G] * scale
    fy = np.fft.irfft2(R * KY, s=(2 * G, 2 * G))[:G, :G] * scale
    return np.column_stack((fx.ravel()[flat], fy.ravel()[flat]))


def _spectral_init(n, src, dst, rng):
    """Start near a sensible shape: random, lightly smoothed along edges."""
    pos = rng.random((n, 2))
    if len(src) and n <= 200_000:
        for _ in range(8):
            acc = np.zeros((n, 2))
            deg = np.bincount(src, minlength=n) + np.bincount(dst, minlength=n) + 1.0
            acc[:, 0] = np.bincount(src, pos[dst, 0], n) + np.bincount(dst, pos[src, 0], n) + pos[:, 0]
            acc[:, 1] = np.bincount(src, pos[dst, 1], n) + np.bincount(dst, pos[src, 1], n) + pos[:, 1]
            pos = 0.5 * pos + 0.5 * acc / deg[:, None]
            pos = normalize(pos) * 0.9 + 0.05 + rng.random((n, 2)) * 0.02
    return pos


def circular(n: int) -> np.ndarray:
    a = np.linspace(0, 2 * np.pi, n, endpoint=False) - np.pi / 2
    return normalize(np.column_stack((np.cos(a), np.sin(a))))


def grid(n: int) -> np.ndarray:
    c = math.ceil(math.sqrt(n))
    i = np.arange(n)
    return normalize(np.column_stack((i % c, i // c)).astype(float))


def layered(n: int, src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Left-to-right layers for DAGs (longest-path layering + barycentre ordering)."""
    indeg = np.bincount(dst, minlength=n)
    layer = np.zeros(n, dtype=np.int64)
    order = []
    q = list(np.flatnonzero(indeg == 0))
    indeg = indeg.copy()
    out: list[list[int]] = [[] for _ in range(n)]
    for a, b in zip(src.tolist(), dst.tolist()):
        out[a].append(b)
    while q:
        u = q.pop()
        order.append(u)
        for v in out[u]:
            layer[v] = max(layer[v], layer[u] + 1)
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if len(order) != n:  # has a cycle: fall back
        return force(n, src, dst)
    n_layers = int(layer.max()) + 1
    rank = np.zeros(n)
    members = [list(np.flatnonzero(layer == L)) for L in range(n_layers)]
    for mem in members:
        for i, v in enumerate(mem):
            rank[v] = i
    preds: list[list[int]] = [[] for _ in range(n)]
    for a, b in zip(src.tolist(), dst.tolist()):
        preds[b].append(a)
    for _ in range(4):  # barycentre sweeps reduce crossings
        for L in range(1, n_layers):
            mem = members[L]
            bary = [np.mean([rank[p] for p in preds[v]]) if preds[v] else rank[v] for v in mem]
            mem = [v for _, v in sorted(zip(bary, mem))]
            members[L] = mem
            for i, v in enumerate(mem):
                rank[v] = i
    pos = np.zeros((n, 2))
    for L, mem in enumerate(members):
        k = len(mem)
        for i, v in enumerate(mem):
            pos[v] = (L, (i + 0.5) / k)
    if n_layers > 1:
        pos[:, 0] /= n_layers - 1
    else:
        pos[:, 0] = 0.5
    return pos


def radial(n: int, src: np.ndarray, dst: np.ndarray, root: int | None = None) -> np.ndarray:
    """Rings by distance from ``root`` (the best-connected node by default): a node's angle comes from the
    size of its branch of the breadth-first tree. Other components hang off the centre as extra branches."""
    if n == 0:
        return np.zeros((0, 2))
    nbrs: list[list[int]] = [[] for _ in range(n)]
    for a, b in zip(src.tolist(), dst.tolist()):
        if a != b:
            nbrs[a].append(b)
            nbrs[b].append(a)
    deg = np.array([len(x) for x in nbrs])
    root = int(np.argmax(deg)) if root is None else int(root)
    depth = np.full(n, -1)
    parent = np.full(n, -1)
    children: list[list[int]] = [[] for _ in range(n)]
    order: list[int] = []
    tops: list[int] = []                       # roots of the trees: the main one, then other components

    def grow(r: int, d0: int) -> None:
        depth[r] = d0
        queue = [r]
        tops.append(r)
        head = 0
        while head < len(queue):
            u = queue[head]
            head += 1
            order.append(u)
            for v in sorted(nbrs[u], key=lambda x: (-deg[x], x)):
                if depth[v] < 0:
                    depth[v] = depth[u] + 1
                    parent[v] = u
                    children[u].append(v)
                    queue.append(v)

    grow(root, 0)
    for u in np.argsort(-deg, kind="stable").tolist():
        if depth[u] < 0:
            grow(u, 1)
            children[root].append(u)           # a branch of the centre, one ring out
            parent[u] = root
    leaves = np.ones(n)
    for u in reversed(order):
        if children[u]:
            leaves[u] = sum(leaves[c] for c in children[u])
    lo = np.zeros(n)
    hi = np.zeros(n)
    lo[root], hi[root] = 0.0, 2 * np.pi
    for u in order:
        if not children[u]:
            continue
        total = sum(leaves[c] for c in children[u])
        cur = lo[u]
        for c in children[u]:
            span = (hi[u] - lo[u]) * leaves[c] / total
            lo[c], hi[c] = cur, cur + span
            cur += span
    ang = (lo + hi) / 2
    r = depth.astype(float)
    pos = np.column_stack((r * np.cos(ang), r * np.sin(ang)))
    biggest = float(np.abs(pos).max()) or 1.0          # one scale for both axes keeps the rings circular
    return pos / (2 * biggest) + 0.5


def bipartite(n: int, src: np.ndarray, dst: np.ndarray, left=None) -> np.ndarray:
    """Two columns. ``left`` is the set of node indices for the left column; by default the graph is
    two-coloured (it must be bipartite). Rows are ordered by barycentre sweeps to cut crossings."""
    nbrs: list[list[int]] = [[] for _ in range(n)]
    for a, b in zip(src.tolist(), dst.tolist()):
        if a != b:
            nbrs[a].append(b)
            nbrs[b].append(a)
    if left is None:
        color = np.full(n, -1)
        for s in range(n):
            if color[s] >= 0:
                continue
            color[s] = 0
            queue = [s]
            for u in queue:
                for v in nbrs[u]:
                    if color[v] < 0:
                        color[v] = 1 - color[u]
                        queue.append(v)
                    elif color[v] == color[u]:
                        raise ValueError("The graph is not bipartite; pass sets=[nodes of the left column].")
        side = color
    else:
        side = np.ones(n, dtype=int)
        side[list(left)] = 0
    rank = np.zeros(n)
    for col in (0, 1):
        members = np.flatnonzero(side == col)
        rank[members] = np.arange(len(members))
    for sweep in range(6):
        for col in ((1, 0) if sweep % 2 == 0 else (0, 1)):
            members = np.flatnonzero(side == col)
            bary = np.array([np.mean([rank[v] for v in nbrs[u]]) if nbrs[u] else rank[u] for u in members])
            rank[members[np.argsort(bary, kind="stable")]] = np.arange(len(members))
    pos = np.zeros((n, 2))
    for col in (0, 1):
        members = np.flatnonzero(side == col)
        k = max(len(members), 1)
        pos[members, 0] = col
        pos[members, 1] = (rank[members] + 0.5) / k
    return pos


def normalize(pos: np.ndarray) -> np.ndarray:
    lo = pos.min(axis=0)
    span = pos.max(axis=0) - lo
    span[span == 0] = 1.0
    return (pos - lo) / span
