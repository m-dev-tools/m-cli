"""Identity formatter — Step 1.0.

Parses the source via tree-sitter-m, walks the tree, and emits the
original bytes exactly. The point is to:

1. Validate the parser+emit pipeline end-to-end.
2. Ensure round-trip equality on every routine in the VistA corpus
   *before* we start applying canonical layout rules.
3. Establish the file/CLI plumbing (read → format → write/diff) so the
   subsequent rule-based passes plug in without re-architecture.

A real canonical formatter will replace `format_source()` with a
node-walking emitter that re-derives whitespace from the AST shape and
preserves comment text byte-for-byte. For now, returning the parsed
tree's `text` proves the round-trip cleanly.
"""

from __future__ import annotations

from pathlib import Path

from m_cli.parser import parse


def format_source(src: bytes) -> bytes:
    """Format M source bytes; return the formatted bytes.

    Identity pass: parses and re-emits via the tree's root_node.text.
    For a clean parse, this returns `src` byte-for-byte.

    If the source contains parse errors, the tree may not round-trip
    perfectly — those routines should be reported by `--check` rather
    than rewritten.
    """
    tree = parse(src)
    if tree.root_node.has_error:
        # Identity-pass policy: refuse to rewrite a routine that did not
        # parse cleanly. Caller decides whether to skip or fail.
        raise ParseError(
            f"source did not parse cleanly ({_count_errors(tree.root_node)} error nodes)"
        )
    out = tree.root_node.text
    assert out is not None
    return bytes(out)


def format_file(path: Path) -> tuple[bytes, bytes]:
    """Read and format a `.m` file. Returns (original_bytes, formatted_bytes)."""
    src = path.read_bytes()
    return src, format_source(src)


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
