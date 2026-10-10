"""Chord diagrams: flows (or links) between a few groups, drawn as ribbons inside a circle."""

from __future__ import annotations

import math

import numpy as np

from .. import scene as S
from .._data import DataError, columns_of, get_column, is_frame, to_array
from .._text import format_value, text_width
from ._base import DrawContext, Layer
from ._geom import arc

_AUTO = "auto"


class ChordLayer(Layer):
    """Square matrix (``names=`` for the labels), a square DataFrame, or (source, target, value) rows
    (a square table made only of numbers is read as a matrix, rows with names as edges).

    The arc of a group is as long as its row sum; the ribbon between groups *i* and *j* is as wide as
    ``M[i][j]`` at *i* and ``M[j][i]`` at *j*, so a directed flow shows its asymmetry.
    """

    cartesian = False
    own_legend = True

    def __init__(self, data=None, *, names=None, gap=0.03, thickness=_AUTO, labels=True, format=None, sort=False):
        self.data, self.names_opt, self.gap, self.thickness = data, names, gap, thickness
        self.labels, self.fmt, self.sort = labels, format, sort

    def prepare(self, chart) -> None:
        data = self.data
        if is_frame(data) and not isinstance(data, (list, tuple, np.ndarray)):
            cols = [str(c) for c in columns_of(data)]
            body = np.column_stack([np.asarray(to_array(get_column(data, c)), dtype=object) for c in columns_of(data)])
            numeric = all(isinstance(v, (int, float, np.integer, np.floating)) for v in body.ravel())
            if numeric and body.shape[0] == body.shape[1]:
                mat = body.astype(float)
                names = list(self.names_opt or cols)
            else:                                           # edge table
                from .network import _edges_from_frame
                a, b, w = _edges_from_frame(data)
                if w is None:
                    raise DataError("A chord diagram needs a value column (value / weight / count).")
                names, mat = _matrix_from_rows(zip(a.tolist(), b.tolist(), w.tolist()))
        else:
            arr = None
            if isinstance(data, np.ndarray) and data.ndim == 2 and data.shape[0] == data.shape[1]:
                arr = data
            elif isinstance(data, (list, tuple)) and data and all(isinstance(r, (list, tuple, np.ndarray)) for r in data) \
                    and all(len(r) == len(data) for r in data) \
                    and all(isinstance(v, (int, float, np.integer, np.floating)) for r in data for v in r):
                arr = np.asarray(data, float)     # a square table of numbers is a matrix; rows with names are edges
            if arr is not None:
                mat = np.asarray(arr, float)
                names = [str(n) for n in (self.names_opt or range(len(mat)))]
            else:
                names, mat = _matrix_from_rows(data)
        if len(names) != mat.shape[0]:
            raise DataError(f"names= has {len(names)} entries but the matrix is {mat.shape[0]} x {mat.shape[1]}.")
        mat = np.nan_to_num(mat)
        if np.any(mat < 0):
            raise DataError("Chord values can't be negative.")
        if mat.sum() <= 0:
            raise DataError("All chord values are zero.")
        if self.sort:
            order = np.argsort(-mat.sum(axis=1), kind="stable")
            names = [names[i] for i in order]
            mat = mat[np.ix_(order, order)]
        self.names, self.mat = [str(n) for n in names], mat

    def keys(self):
        return list(self.names)

    def default_size(self, theme):
        return 620.0, 620.0

    def _fmt(self, v):
        if self.fmt is not None:
            return self.fmt(v) if callable(self.fmt) else (self.fmt.format(v) if "{" in self.fmt else format(v, self.fmt))
        return format_value(v)

    def draw(self, ctx: DrawContext) -> None:
        theme, plot = ctx.theme, ctx.plot
        size = theme.font_size
        n = len(self.names)
        lab_w = max(text_width(nm, size, theme.font_kind) for nm in self.names) + 14 if self.labels else 6
        r_out = max(40.0, min(plot.w / 2 - lab_w, plot.h / 2 - size * 1.5))
        thick = max(6.0, r_out * 0.06) if isinstance(self.thickness, str) else float(self.thickness)
        r_in = r_out - thick
        cx, cy = plot.x + plot.w / 2, plot.y + plot.h / 2
        row = self.mat.sum(axis=1)
        total = float(row.sum())
        gap = float(self.gap) if n > 1 else 0.0
        scale = (2 * math.pi - gap * n) / total
        start = -math.pi / 2
        a0 = np.zeros(n)
        pos = start
        for i in range(n):
            a0[i] = pos
            pos += row[i] * scale + gap
        cursor = a0.copy()
        sub = {}                      # (i, j) -> (start angle, end angle) of the i end of the ribbon i-j
        for i in range(n):
            for j in range(n):
                v = self.mat[i, j]
                if v > 0:
                    sub[(i, j)] = (cursor[i], cursor[i] + v * scale)
                    cursor[i] += v * scale
        hl = ctx.highlight
        cols = [ctx.color(self.names[i], i) for i in range(n)]
        if theme.family == "folio":
            cols = [theme.ink_secondary] * n
        for i in range(n):
            for j in range(i, n):
                ends = []
                if (i, j) in sub:
                    ends.append((i, j))
                if j != i and (j, i) in sub:
                    ends.append((j, i))
                if not ends:
                    continue
                if i == j:
                    s = sub[(i, i)]
                    t = s
                else:
                    s = sub.get((i, j), (cursor[i], cursor[i]))
                    t = sub.get((j, i), (cursor[j], cursor[j]))
                big = i if self.mat[i, j] >= self.mat[j, i] else j
                on = not hl or self.names[i] in hl or self.names[j] in hl
                color = cols[big] if on else theme.muted
                ri = r_in - 2
                pts_t0 = (cx + ri * math.cos(t[0]), cy + ri * math.sin(t[0]))
                pts_s0 = (cx + ri * math.cos(s[0]), cy + ri * math.sin(s[0]))
                cmds = arc(cx, cy, ri, s[0], s[1])
                cmds.append(("Q", cx, cy, pts_t0[0], pts_t0[1]))
                cmds += arc(cx, cy, ri, t[0], t[1], move=False)
                cmds.append(("Q", cx, cy, pts_s0[0], pts_s0[1]))
                cmds.append(("Z",))
                a_ij, a_ji = self.mat[i, j], self.mat[j, i]
                title = (f"{self.names[i]} → {self.names[j]}: {self._fmt(a_ij)}" if i == j else
                         f"{self.names[i]} → {self.names[j]}: {self._fmt(a_ij)}; "
                         f"{self.names[j]} → {self.names[i]}: {self._fmt(a_ji)}")
                ctx.scene.add(S.Path(cmds, fill=color,
                                     fill_opacity=(0.16 if theme.family == "folio" else 0.45) if on else 0.2,
                                     stroke=theme.background, stroke_width=0.6, title=title))
        for i in range(n):
            a1 = a0[i] + row[i] * scale
            if row[i] <= 0:
                continue
            ctx.scene.add(S.Path(_ring_segment(cx, cy, r_out, r_in, a0[i], a1), fill=cols[i],
                                 title=f"{self.names[i]}: {self._fmt(row[i])}"))
            if self.labels:
                mid = (a0[i] + a1) / 2
                lx, ly = cx + (r_out + 8) * math.cos(mid), cy + (r_out + 8) * math.sin(mid)
                c = math.cos(mid)
                anchor = "middle" if abs(c) < 0.2 else ("start" if c > 0 else "end")
                base = "hanging" if math.sin(mid) > 0.6 else ("alphabetic" if math.sin(mid) < -0.6 else "middle")
                ctx.scene.add(S.Text(lx, ly, self.names[i], size, theme.ink, anchor=anchor, baseline=base,
                                     weight=600, halo=theme.background))


def _ring_segment(cx, cy, r_out, r_in, a0, a1) -> list:
    cmds = arc(cx, cy, r_out, a0, a1)
    cmds.append(("L", cx + r_in * math.cos(a1), cy + r_in * math.sin(a1)))
    cmds += arc(cx, cy, r_in, a1, a0, move=False)
    cmds.append(("Z",))
    return cmds


def _matrix_from_rows(rows):
    agg: dict = {}
    for r in rows:
        if len(r) < 3:
            raise DataError("Chord rows are (source, target, value).")
        s, t, v = r[0], r[1], r[2]
        if v is None or not np.isfinite(v) or v <= 0:
            continue
        agg[(str(s), str(t))] = agg.get((str(s), str(t)), 0.0) + float(v)
    if not agg:
        raise DataError("No positive flows to draw.")
    names = list(dict.fromkeys([k for pair in agg for k in pair]))
    idx = {nm: i for i, nm in enumerate(names)}
    mat = np.zeros((len(names), len(names)))
    for (s, t), v in agg.items():
        mat[idx[s], idx[t]] += v
    return names, mat
