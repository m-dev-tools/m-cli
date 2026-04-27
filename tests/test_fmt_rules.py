"""Tests for ``m_cli.fmt.rules`` — canonical-layout transformations.

Each rule is an idempotent ``bytes -> bytes`` transformation that must
preserve the parsed AST's *meaning*. Tests cover both directions:

  - rule fires on input that needs the change
  - rule is a no-op on input that's already canonical
  - rule is idempotent (applying twice yields the same output)
"""

from __future__ import annotations

import pytest

from m_cli.fmt.rules import (
    FmtRule,
    all_rules,
    canonical_rules,
    select_fmt_rules,
    trim_trailing_whitespace,
    uppercase_command_keywords,
)
from m_cli.parser import parse

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_all_rules_includes_at_least_two_rules() -> None:
    rules = all_rules()
    ids = {r.id for r in rules}
    assert "trim-trailing-whitespace" in ids
    assert "uppercase-command-keywords" in ids


def test_canonical_rules_returns_all_registered() -> None:
    assert {r.id for r in canonical_rules()} == {r.id for r in all_rules()}


def test_select_fmt_rules_canonical_returns_everything() -> None:
    rules = select_fmt_rules("canonical")
    assert {r.id for r in rules} == {r.id for r in all_rules()}


def test_select_fmt_rules_none_returns_empty() -> None:
    assert select_fmt_rules("none") == []


def test_select_fmt_rules_specific_ids() -> None:
    rules = select_fmt_rules("trim-trailing-whitespace")
    assert [r.id for r in rules] == ["trim-trailing-whitespace"]


def test_select_fmt_rules_comma_separated() -> None:
    rules = select_fmt_rules("trim-trailing-whitespace,uppercase-command-keywords")
    assert {r.id for r in rules} == {
        "trim-trailing-whitespace",
        "uppercase-command-keywords",
    }


def test_select_fmt_rules_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown fmt rule"):
        select_fmt_rules("not-a-real-rule")


# ---------------------------------------------------------------------------
# trim-trailing-whitespace
# ---------------------------------------------------------------------------


class TestTrimTrailingWhitespace:
    def test_clean_line_unchanged(self) -> None:
        src = b"hello ;c\n quit\n"
        assert trim_trailing_whitespace(src) == src

    def test_trailing_spaces_removed(self) -> None:
        src = b"hello ;c   \n quit  \n"
        out = trim_trailing_whitespace(src)
        assert out == b"hello ;c\n quit\n"

    def test_trailing_tabs_removed(self) -> None:
        src = b"hello ;c\t\n quit\t\t\n"
        out = trim_trailing_whitespace(src)
        assert out == b"hello ;c\n quit\n"

    def test_mixed_trailing(self) -> None:
        src = b"hello ;c \t \n quit\n"
        out = trim_trailing_whitespace(src)
        assert out == b"hello ;c\n quit\n"

    def test_crlf_preserved(self) -> None:
        src = b"hello ;c   \r\n quit\r\n"
        out = trim_trailing_whitespace(src)
        assert out == b"hello ;c\r\n quit\r\n"

    def test_no_terminator_on_last_line(self) -> None:
        src = b"hello ;c   "
        out = trim_trailing_whitespace(src)
        assert out == b"hello ;c"

    def test_empty_input(self) -> None:
        assert trim_trailing_whitespace(b"") == b""

    def test_idempotent(self) -> None:
        src = b"hello   \n quit\t\n"
        once = trim_trailing_whitespace(src)
        twice = trim_trailing_whitespace(once)
        assert once == twice

    def test_does_not_touch_leading_or_internal_whitespace(self) -> None:
        # Indentation and intra-line whitespace must survive.
        src = b"hello\n    new x  ,  y\n quit\n"
        out = trim_trailing_whitespace(src)
        assert out == src


# ---------------------------------------------------------------------------
# uppercase-command-keywords
# ---------------------------------------------------------------------------


class TestUppercaseCommandKeywords:
    def test_lowercase_keyword_uppercased(self) -> None:
        src = b"hello ;c\n new x\n quit\n"
        out = uppercase_command_keywords(src)
        assert b" NEW x" in out
        assert b" QUIT" in out

    def test_already_uppercase_unchanged(self) -> None:
        src = b"hello ;c\n NEW x\n QUIT\n"
        assert uppercase_command_keywords(src) == src

    def test_abbreviation_uppercased(self) -> None:
        src = b"hello ;c\n s x=1\n q\n"
        out = uppercase_command_keywords(src)
        assert b" S x=1" in out
        assert b" Q\n" in out

    def test_mixed_case_uppercased(self) -> None:
        src = b"hello ;c\n Set x=1\n Quit\n"
        out = uppercase_command_keywords(src)
        assert b" SET x=1" in out
        assert b" QUIT" in out

    def test_does_not_touch_arguments(self) -> None:
        # Local variable named "set" is unusual but legal as an identifier.
        # The rule must only touch `command_keyword` nodes.
        src = b"hello ;c\n new lcVar\n quit\n"
        out = uppercase_command_keywords(src)
        assert b"lcVar" in out  # argument left alone
        assert b" NEW lcVar" in out  # but the keyword changed

    def test_does_not_touch_comments(self) -> None:
        src = b"hello ;set this here is a comment, not a command\n quit\n"
        out = uppercase_command_keywords(src)
        assert b";set this here is a comment, not a command" in out

    def test_idempotent(self) -> None:
        src = b"hello ;c\n new x\n set x=1\n quit\n"
        once = uppercase_command_keywords(src)
        twice = uppercase_command_keywords(once)
        assert once == twice

    def test_preserves_ast_shape(self) -> None:
        """Uppercasing keywords must not change the parse tree's shape."""
        src = b"hello ;c\n new x\n set x=1\n quit\n"
        before = _collapsed_tree(src)
        after = _collapsed_tree(uppercase_command_keywords(src))
        assert before == after

    def test_handles_dot_block_keywords(self) -> None:
        src = b"loop ;trivial dot block\n new i\n for i=1:1:5 do\n . write i,!\n quit\n"
        out = uppercase_command_keywords(src)
        assert b" FOR i=1:1:5 DO" in out
        assert b" WRITE i,!" in out
        assert b" NEW i" in out
        assert b" QUIT" in out

    def test_empty_input(self) -> None:
        assert uppercase_command_keywords(b"") == b""


# ---------------------------------------------------------------------------
# FmtRule dataclass + integration via format_source
# ---------------------------------------------------------------------------


def test_FmtRule_dataclass_fields() -> None:
    rule = FmtRule(id="x", title="X", description="x", apply=lambda src: src)
    assert rule.id == "x"
    assert rule.apply(b"hi") == b"hi"


def test_format_source_with_rules_applies_all() -> None:
    from m_cli.fmt.formatter import format_source

    src = b"hello   \n new x  \n quit\n"
    out = format_source(src, rules=canonical_rules())
    # trailing whitespace stripped AND keywords uppercased
    assert out == b"hello\n NEW x\n QUIT\n"


def test_format_source_default_is_identity() -> None:
    """No --rules → identity behavior preserved (back-compat with VistA gate)."""
    from m_cli.fmt.formatter import format_source

    src = b"hello   \n new x\n quit\n"
    assert format_source(src) == src


def test_format_source_with_empty_rule_list_is_identity() -> None:
    from m_cli.fmt.formatter import format_source

    src = b"hello   \n new x\n quit\n"
    assert format_source(src, rules=[]) == src


def test_format_source_canonical_is_idempotent_on_vista_style() -> None:
    """Apply canonical twice; second pass must be a no-op."""
    from m_cli.fmt.formatter import format_source

    src = b"hello ;c\n new pat\n set ^DPT(pat,0)=name\n quit\n"
    once = format_source(src, rules=canonical_rules())
    twice = format_source(once, rules=canonical_rules())
    assert once == twice


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collapsed_tree(src: bytes) -> str:
    """Return a structural representation of the parse tree."""
    tree = parse(src)

    def walk(node, depth=0):
        out = ["  " * depth + node.type]
        for c in node.children:
            out.extend(walk(c, depth + 1))
        return out

    return "\n".join(walk(tree.root_node))
