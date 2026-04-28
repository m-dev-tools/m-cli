"""Tests for ``m_cli.lsp.structure`` — label and dot-block discovery.

Pure functions over bytes. Drives DocumentSymbol, CodeLens, and
folding-range handlers in ``server.py``.
"""

from __future__ import annotations

from m_cli.lsp.structure import find_dot_blocks, find_labels


def test_find_labels_returns_each_label_with_body_range() -> None:
    src = b"HELLO ;c\n SET X=1\n QUIT\nINNER ;c\n QUIT\n"
    labels = find_labels(src)

    names = [lbl.name for lbl in labels]
    assert names == ["HELLO", "INNER"]

    hello, inner = labels
    assert hello.start_line == 0
    assert hello.end_line == 2  # last body line of HELLO is " QUIT" on row 2
    assert inner.start_line == 3
    assert inner.end_line == 4


def test_find_labels_extracts_formals() -> None:
    src = b"INNER(a,b) ;c\n QUIT a+b\n"
    labels = find_labels(src)
    assert labels[0].formals == "(a,b)"


def test_find_labels_handles_empty_source() -> None:
    assert find_labels(b"") == []


def test_find_labels_single_label_extends_to_eof() -> None:
    src = b"ONLY ;c\n SET X=1\n QUIT\n"
    labels = find_labels(src)
    assert len(labels) == 1
    assert labels[0].start_line == 0
    assert labels[0].end_line == 2


def test_find_labels_skips_unlabeled_lines() -> None:
    """Code without a leading label still parses; we only emit labelled lines."""
    src = b" SET X=1\nFOO ;c\n QUIT\n"
    labels = find_labels(src)
    assert [lbl.name for lbl in labels] == ["FOO"]


def test_find_dot_blocks_groups_consecutive_dots() -> None:
    src = b"TOP ;c\n . W \"a\"\n . S X=1\n Q\n"
    blocks = find_dot_blocks(src)
    assert len(blocks) == 1
    assert blocks[0].start_line == 1
    assert blocks[0].end_line == 2


def test_find_dot_blocks_separates_runs() -> None:
    src = b"A\n . S X=1\n W \"between\"\n . S Y=2\n"
    blocks = find_dot_blocks(src)
    assert len(blocks) == 2
    assert blocks[0].start_line == 1 and blocks[0].end_line == 1
    assert blocks[1].start_line == 3 and blocks[1].end_line == 3


def test_find_dot_blocks_empty_when_no_dots() -> None:
    src = b"HELLO ;c\n SET X=1\n QUIT\n"
    assert find_dot_blocks(src) == []
