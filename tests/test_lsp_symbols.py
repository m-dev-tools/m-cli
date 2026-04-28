"""Tests for ``m_cli.lsp.symbols`` — token resolution + keyword lookup.

These pieces back the Stage 4 hover and completion handlers. We test
the helpers directly (no FakeServer needed) since they're pure
functions over strings + cached metadata.
"""

from __future__ import annotations

from m_cli.lsp.symbols import all_keywords, lookup_keyword, token_at

# ---------------------------------------------------------------------------
# token_at
# ---------------------------------------------------------------------------


def test_token_at_word_in_middle() -> None:
    assert token_at(" SET X=1", 1) == "SET"
    assert token_at(" SET X=1", 2) == "SET"
    assert token_at(" SET X=1", 3) == "SET"


def test_token_at_just_past_token_end() -> None:
    """LSP convention: cursor at end of identifier still hovers it."""
    assert token_at(" SET X=1", 4) == "SET"


def test_token_at_intrinsic_keeps_dollar() -> None:
    assert token_at(' W $LENGTH("foo")', 5) == "$LENGTH"


def test_token_at_z_function() -> None:
    assert token_at(" S X=$ZTRNLNM(\"PATH\")", 8) == "$ZTRNLNM"


def test_token_at_empty_line_returns_none() -> None:
    assert token_at("", 0) is None


def test_token_at_position_on_whitespace_returns_none() -> None:
    """Cursor on a separator with no adjacent word chars returns None."""
    assert token_at("  X = 1", 0) is None


def test_token_at_out_of_range_returns_none() -> None:
    assert token_at("SET", -1) is None
    assert token_at("SET", 10) is None


def test_token_at_caret_global_yields_word_only() -> None:
    """``^`` is not a word char — hover on ``^GBL`` resolves to GBL,
    which won't match any standard keyword (correctly returning None
    from lookup_keyword)."""
    assert token_at(" S ^GBL=1", 4) == "GBL"


# ---------------------------------------------------------------------------
# lookup_keyword
# ---------------------------------------------------------------------------


def test_lookup_canonical_command() -> None:
    rec = lookup_keyword("SET")
    assert rec is not None
    assert rec.kind == "command"
    assert rec.canonical == "SET"


def test_lookup_command_abbreviation() -> None:
    """`S` is the abbreviation for SET; both must resolve to the same record."""
    rec = lookup_keyword("S")
    assert rec is not None
    assert rec.kind == "command"
    assert rec.canonical == "SET"


def test_lookup_is_case_insensitive() -> None:
    """M is case-insensitive for keywords; hover should match either case."""
    assert lookup_keyword("set") is not None
    assert lookup_keyword("Set") is not None


def test_lookup_intrinsic_function() -> None:
    rec = lookup_keyword("$LENGTH")
    assert rec is not None
    assert rec.kind == "function"


def test_lookup_intrinsic_special_variable() -> None:
    # `$JOB` is unambiguously an ISV (some names like `$HOROLOG` appear
    # in ANSI as both ISV and intrinsic function; we test the unambiguous
    # case here).
    rec = lookup_keyword("$JOB")
    assert rec is not None
    assert rec.kind == "isv"


def test_lookup_unknown_token_returns_none() -> None:
    assert lookup_keyword("XYZNOTAKEYWORD") is None
    assert lookup_keyword("MYLABEL") is None


# ---------------------------------------------------------------------------
# all_keywords (drives completion)
# ---------------------------------------------------------------------------


def test_all_keywords_contains_each_kind() -> None:
    kinds = {r.kind for r in all_keywords()}
    assert "command" in kinds
    assert "isv" in kinds
    assert "function" in kinds


def test_all_keywords_contains_set_and_length() -> None:
    canonicals = {r.canonical for r in all_keywords()}
    assert "SET" in canonicals
    assert "$LENGTH" in canonicals
