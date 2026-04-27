"""m fmt formatter.

Two layers:

1. **Identity pass** — parses the source and re-emits the parse tree's
   bytes verbatim. The point is that anything `m fmt` outputs must
   round-trip through the parser cleanly. With no canonical-layout
   rules applied, the output equals the input byte-for-byte.

2. **Canonical-layout rules** (optional) — pure ``bytes -> bytes``
   transformations layered on top of identity. Each rule preserves
   the parse tree's *shape* (no nodes appear or disappear); they only
   adjust whitespace and the text of certain nodes (e.g. command
   keywords). See ``m_cli.fmt.rules``.

Default behavior is identity. Callers opt into canonical layout by
passing ``rules=canonical_rules()`` (or a subset).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from m_cli.parser import parse


def format_source(src: bytes, *, rules: "Iterable | None" = None) -> bytes:
    """Format M source bytes; return the formatted bytes.

    With ``rules=None`` (the default) this is the identity pass:
    parse → emit. With an explicit rules list, each rule's ``apply``
    callable is invoked in order on the running buffer.

    A clean parse is required before any rule runs — sources with
    parse errors raise :class:`ParseError`.
    """
    if not isinstance(src, (bytes, bytearray)):
        raise TypeError(f"format_source expects bytes, got {type(src).__name__}")
    tree = parse(src)
    if tree.root_node.has_error:
        raise ParseError(
            f"source did not parse cleanly ({_count_errors(tree.root_node)} error nodes)"
        )
    out = tree.root_node.text
    assert out is not None
    out_bytes = bytes(out)
    if rules:
        for rule in rules:
            out_bytes = rule.apply(out_bytes)
    return out_bytes


def format_file(path: Path, *, rules: "Iterable | None" = None) -> tuple[bytes, bytes]:
    """Read and format a `.m` file. Returns (original_bytes, formatted_bytes)."""
    src = path.read_bytes()
    return src, format_source(src, rules=rules)


class ParseError(Exception):
    """Raised when source has parse errors and cannot be safely formatted."""


def _count_errors(node) -> int:
    """Count ERROR / MISSING nodes in the tree."""
    count = 0
    if node.type == "ERROR" or node.is_missing:
        count = 1
    for child in node.children:
        count += _count_errors(child)
    return count
