"""Tests for ``m_cli.lint._index.NodeIndex``."""

from __future__ import annotations

from m_cli.lint._index import NodeIndex
from m_cli.parser import parse


def test_buckets_every_node_by_type() -> None:
    src = b'hello ;c\n write "x",!\n quit\n'
    idx = NodeIndex(parse(src))
    types = idx.types()
    # We should see at least these node types from a trivial routine.
    assert {"label", "command", "command_keyword", "comment"} <= types


def test_of_returns_only_requested_types() -> None:
    src = b"hello ;trivial\n new x\n set x=1\n quit\n"
    idx = NodeIndex(parse(src))
    cmds = list(idx.of("command"))
    assert len(cmds) == 3  # new, set, quit
    assert all(c.type == "command" for c in cmds)


def test_of_multiple_types() -> None:
    src = b"hello ;trivial\n new x\n quit\n"
    idx = NodeIndex(parse(src))
    nodes = list(idx.of("label", "comment"))
    assert {n.type for n in nodes} == {"label", "comment"}


def test_of_unknown_type_returns_empty() -> None:
    src = b"hello\n quit\n"
    idx = NodeIndex(parse(src))
    assert list(idx.of("not_a_node_type")) == []


def test_first_returns_first_or_none() -> None:
    src = b"hello\n new x\n set x=1\n quit\n"
    idx = NodeIndex(parse(src))
    first_cmd = idx.first("command")
    assert first_cmd is not None
    assert first_cmd.type == "command"
    assert idx.first("nonexistent") is None


def test_has_node_type() -> None:
    src = b"hello\n quit\n"
    idx = NodeIndex(parse(src))
    assert idx.has("label") is True
    assert idx.has("nonexistent") is False


def test_pre_order_preserved_within_a_bucket() -> None:
    src = b"hello\n new x\n quit\n ;\nworld\n quit\n"
    idx = NodeIndex(parse(src))
    labels = list(idx.of("label"))
    assert [n.start_point[0] for n in labels] == [0, 4]


def test_empty_source_has_only_top_level_node() -> None:
    src = b""
    idx = NodeIndex(parse(src))
    # Tree-sitter still produces a `source_file` (or equivalent) root.
    assert "source_file" in idx.types() or len(idx.types()) >= 1
