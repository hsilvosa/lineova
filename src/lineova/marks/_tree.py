"""Hierarchies for treemaps and sunbursts: nested dicts or path columns of any depth."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .._data import DataError, aggregate, as_float, get_column, is_frame, to_array

SEP = "\x1f"


@dataclass(eq=False, repr=False)
class Node:
    name: str
    value: float = 0.0
    children: list = field(default_factory=list)
    parent: Optional[Node] = None
    depth: int = 0

    @property
    def is_leaf(self) -> bool:
        return not self.children

    def path(self) -> list[str]:
        out, n = [], self
        while n is not None and n.depth > 0:
            out.append(n.name)
            n = n.parent
        return out[::-1]

    def top(self) -> Node:
        """The depth-1 ancestor (whose colour the subtree shares)."""
        n = self
        while n.parent is not None and n.parent.depth > 0:
            n = n.parent
        return n

    def height(self) -> int:
        return 0 if self.is_leaf else 1 + max(c.height() for c in self.children)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


def _from_dict(d: dict, parent: Node) -> None:
    for k, v in d.items():
        node = Node(str(k), parent=parent, depth=parent.depth + 1)
        if isinstance(v, dict):
            _from_dict(v, node)
            if not node.children:
                continue
            node.value = sum(c.value for c in node.children)
        else:
            try:
                val = float(v)
            except (TypeError, ValueError):
                raise DataError(f"{node.name!r}: values must be numbers or nested dicts.") from None
            if not np.isfinite(val) or val <= 0:
                continue
            node.value = val
        parent.children.append(node)


def build(data, path=None, value=None, agg="sum", sort=True) -> Node:
    """Build the hierarchy. Children are sorted largest first (``sort=True``)."""
    root = Node("", depth=0)
    if is_frame(data) and not isinstance(data, dict):
        cols = [path] if isinstance(path, str) else list(path or [])
        if not cols:
            raise DataError("Pass path=['level1', 'level2', ...] (one or more columns) and value='column'.")
        vals = as_float(to_array(get_column(data, value)), "num") if value is not None else None
        levels = [to_array(get_column(data, c)) for c in cols]
        key = np.array([SEP.join(map(str, t)) for t in zip(*levels)], dtype=object)
        names, v = aggregate(key, vals, agg)
        nested: dict = {}
        for k, val in zip(names, v):
            parts = str(k).split(SEP)
            d = nested
            for p in parts[:-1]:
                d = d.setdefault(p, {})
                if not isinstance(d, dict):
                    raise DataError(f"{p!r} is both a leaf and a group in path={cols}.")
            if isinstance(d.get(parts[-1]), dict):
                raise DataError(f"{parts[-1]!r} is both a leaf and a group in path={cols}.")
            d[parts[-1]] = d.get(parts[-1], 0) + val
        _from_dict(nested, root)
    elif isinstance(data, dict):
        _from_dict(data, root)
    else:
        try:
            idx = data.index
            _from_dict(dict(zip(map(str, idx), to_array(data))), root)
        except AttributeError:
            raise DataError("Pass {label: value}, nested dicts {group: {label: value}}, "
                            "or a DataFrame with path=[...] and value=.") from None
    if not root.children:
        raise DataError("The hierarchy has no positive values.")
    root.value = sum(c.value for c in root.children)
    if sort:
        for n in root.walk():
            n.children.sort(key=lambda c: -c.value)
    return root
