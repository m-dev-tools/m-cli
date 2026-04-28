"""Document-structure helpers — labels and dot blocks for the LSP.

These walk the tree-sitter parse tree to extract the regions that
power document-symbol outlines, code lenses, and folding ranges.
Pure functions over bytes; no LSP types — server.py wraps the
results into the LSP wire shapes.
"""

from __future__ import annotations

from dataclasses import dataclass

from m_cli.parser import parse


@dataclass(frozen=True)
class LabelRange:
    """A label and the line range it covers (its body, until the next
    label or end-of-file).

    ``start_line`` and ``end_line`` are 0-indexed for direct LSP use.
    ``end_line`` is inclusive of the last body line — for a one-line
    label-only file, ``end_line == start_line``.
    """

    name: str
    start_line: int
    end_line: int
    formals: str  # the parenthesised formals string, e.g. "(a,b)"; empty if none


@dataclass(frozen=True)
class DotBlockRange:
    """A contiguous run of ``dot_block_prefix`` lines."""

    start_line: int
    end_line: int


def find_labels(src: bytes) -> list[LabelRange]:
    """Return every label in ``src`` with the line range its body covers.

    The body of label N runs from N's line through the line before
    label N+1 (or end-of-file for the last label). Label-only files
    or labels with empty bodies report ``end_line == start_line``.
    """
    tree = parse(src)
    line_nodes = [c for c in tree.root_node.children if c.type == "line"]
    last_row = max(0, tree.root_node.end_point[0] - 1)

    label_lines: list[tuple[int, str, str]] = []  # (row, name, formals)
    for line_node in line_nodes:
        label_node = next((c for c in line_node.children if c.type == "label"), None)
        if label_node is None:
            continue
        name = src[label_node.start_byte : label_node.end_byte].decode(
            "latin-1", errors="replace"
        )
        formals_node = next((c for c in line_node.children if c.type == "formals"), None)
        formals_str = ""
        if formals_node is not None:
            formals_str = src[formals_node.start_byte : formals_node.end_byte].decode(
                "latin-1", errors="replace"
            )
        label_lines.append((label_node.start_point[0], name, formals_str))

    out: list[LabelRange] = []
    for i, (row, name, formals_str) in enumerate(label_lines):
        if i + 1 < len(label_lines):
            end_row = label_lines[i + 1][0] - 1
        else:
            end_row = last_row
        if end_row < row:
            end_row = row
        out.append(
            LabelRange(name=name, start_line=row, end_line=end_row, formals=formals_str)
        )
    return out


def find_dot_blocks(src: bytes) -> list[DotBlockRange]:
    """Return contiguous runs of dot-block lines.

    A dot block is any run of consecutive ``line`` nodes whose first
    non-whitespace child is a ``dot_block_prefix``. We don't track
    nesting depth — the editor can fold the whole indented region as
    one unit.
    """
    tree = parse(src)
    line_nodes = [c for c in tree.root_node.children if c.type == "line"]
    runs: list[DotBlockRange] = []
    current_start: int | None = None
    current_end: int | None = None
    for line_node in line_nodes:
        is_dot = any(c.type == "dot_block_prefix" for c in line_node.children)
        row = line_node.start_point[0]
        if is_dot:
            if current_start is None:
                current_start = row
            current_end = row
        else:
            if current_start is not None:
                end = current_end if current_end is not None else current_start
                runs.append(DotBlockRange(start_line=current_start, end_line=end))
                current_start = None
                current_end = None
    if current_start is not None:
        end = current_end if current_end is not None else current_start
        runs.append(DotBlockRange(start_line=current_start, end_line=end))
    return runs


__all__ = ["LabelRange", "DotBlockRange", "find_labels", "find_dot_blocks"]
