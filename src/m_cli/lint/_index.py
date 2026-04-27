"""Per-tree node index for the lint single-pass dispatcher.

Walking a tree-sitter tree is O(N) per call. The previous lint
implementation walked the full tree once per rule; with N rules that's
N× redundant work. ``NodeIndex`` walks the tree exactly once and
groups every node by its ``type`` so rules can fetch only the nodes
they care about.

Sub-tree walks (e.g. iterating over a single argument's children) are
not cached — they're already cheap and scoped.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Tree


class NodeIndex:
    """Group every node in a tree-sitter parse tree by ``node.type``."""

    __slots__ = ("_buckets",)

    def __init__(self, tree: "Tree") -> None:
        buckets: dict[str, list] = {}
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            buckets.setdefault(node.type, []).append(node)
            stack.extend(reversed(node.children))
        self._buckets = buckets

    def of(self, *types: str) -> Iterator:
        """Yield every node whose type matches any of ``types``.

        Pre-order is preserved within each type bucket. When ``types``
        contains more than one entry, the first type's nodes come first
        (callers rarely need cross-type ordering).
        """
        for t in types:
            yield from self._buckets.get(t, [])

    def first(self, *types: str):
        """Return the first node matching any of ``types``, or ``None``."""
        for t in types:
            bucket = self._buckets.get(t)
            if bucket:
                return bucket[0]
        return None

    def has(self, node_type: str) -> bool:
        return node_type in self._buckets

    def types(self) -> set[str]:
        return set(self._buckets)
