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
    compact_command_keywords,
    compact_intrinsic_functions,
    compact_rules,
    compact_special_variables,
    expand_command_keywords,
    expand_intrinsic_functions,
    expand_special_variables,
    lowercase_command_keywords,
    lowercase_intrinsic_functions,
    lowercase_special_variables,
    pythonic_lower_rules,
    pythonic_rules,
    rule_by_id,
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


def test_canonical_rules_is_hygiene_only() -> None:
    """Canonical layout = trim + uppercase. Translation rules are opt-in."""
    assert {r.id for r in canonical_rules()} == {
        "trim-trailing-whitespace",
        "uppercase-command-keywords",
    }


def test_canonical_rules_excludes_translation_rules() -> None:
    """expand-* and compact-* must not collide with the default formatter."""
    canonical_ids = {r.id for r in canonical_rules()}
    for rid in canonical_ids:
        assert not rid.startswith("expand-")
        assert not rid.startswith("compact-")


def test_select_fmt_rules_canonical_matches_canonical_rules() -> None:
    assert {r.id for r in select_fmt_rules("canonical")} == {
        r.id for r in canonical_rules()
    }


def test_select_fmt_rules_pythonic_returns_expand_set() -> None:
    rules = select_fmt_rules("pythonic")
    ids = [r.id for r in rules]
    assert ids == [
        "expand-command-keywords",
        "expand-intrinsic-functions",
        "expand-special-variables",
        "trim-trailing-whitespace",
    ]


def test_select_fmt_rules_compact_returns_compact_set() -> None:
    rules = select_fmt_rules("compact")
    ids = [r.id for r in rules]
    assert ids == [
        "compact-command-keywords",
        "compact-intrinsic-functions",
        "compact-special-variables",
        "trim-trailing-whitespace",
    ]


def test_select_fmt_rules_all_returns_every_registered() -> None:
    assert {r.id for r in select_fmt_rules("all")} == {r.id for r in all_rules()}


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
# Translation rules — expand / compact (Phase A)
# ---------------------------------------------------------------------------


class TestExpandCommandKeywords:
    def test_short_keyword_expanded(self) -> None:
        src = b"hello ;c\n S X=1\n Q\n"
        out = expand_command_keywords(src)
        assert b" SET X=1" in out
        assert b" QUIT" in out

    def test_already_canonical_unchanged(self) -> None:
        src = b"hello ;c\n SET X=1\n QUIT\n"
        assert expand_command_keywords(src) == src

    def test_lowercase_preserved(self) -> None:
        src = b"hello ;c\n s X=1\n q\n"
        out = expand_command_keywords(src)
        assert b" set X=1" in out
        assert b" quit\n" in out

    def test_idempotent(self) -> None:
        src = b"hello ;c\n S X=1\n W X\n Q\n"
        once = expand_command_keywords(src)
        twice = expand_command_keywords(once)
        assert once == twice

    def test_does_not_touch_arguments(self) -> None:
        # A local variable named `s` (one of the more pernicious cases).
        src = b"hello ;c\n N s\n S s=1\n Q\n"
        out = expand_command_keywords(src)
        assert b" SET s=1" in out
        assert b" NEW s" in out

    def test_does_not_touch_comments(self) -> None:
        src = b"hello ;s here is just a comment\n Q\n"
        out = expand_command_keywords(src)
        assert b";s here is just a comment" in out

    def test_preserves_ast_shape(self) -> None:
        src = b"hello ;c\n S X=1\n W X\n Q\n"
        before = _collapsed_tree(src)
        after = _collapsed_tree(expand_command_keywords(src))
        assert before == after

    def test_safe_on_parse_error(self) -> None:
        src = b"!!! not valid M\n"
        # No assertion that text changes — just that we don't raise.
        out = expand_command_keywords(src)
        assert isinstance(out, bytes)

    def test_empty_input(self) -> None:
        assert expand_command_keywords(b"") == b""


class TestCompactCommandKeywords:
    def test_canonical_compacted(self) -> None:
        src = b"hello ;c\n SET X=1\n QUIT\n"
        out = compact_command_keywords(src)
        assert b" S X=1" in out
        assert b" Q\n" in out

    def test_already_compact_unchanged(self) -> None:
        src = b"hello ;c\n S X=1\n Q\n"
        assert compact_command_keywords(src) == src

    def test_lowercase_preserved(self) -> None:
        src = b"hello ;c\n set X=1\n quit\n"
        out = compact_command_keywords(src)
        assert b" s X=1" in out
        assert b" q\n" in out

    def test_idempotent(self) -> None:
        src = b"hello ;c\n SET X=1\n WRITE X\n QUIT\n"
        once = compact_command_keywords(src)
        twice = compact_command_keywords(once)
        assert once == twice

    def test_round_trip_with_expand(self) -> None:
        # SET X=1 → S X=1 → SET X=1 (same since canonical is the round-trip
        # anchor).
        canonical = b"hello ;c\n SET X=1\n WRITE X\n QUIT\n"
        compacted = compact_command_keywords(canonical)
        assert expand_command_keywords(compacted) == canonical


class TestExpandIntrinsicFunctions:
    def test_short_function_expanded(self) -> None:
        src = b"hello ;c\n W $L(X)\n Q\n"
        out = expand_intrinsic_functions(src)
        assert b"$LENGTH(X)" in out

    def test_canonical_unchanged(self) -> None:
        src = b"hello ;c\n W $LENGTH(X)\n Q\n"
        assert expand_intrinsic_functions(src) == src

    def test_lowercase_preserved(self) -> None:
        src = b"hello ;c\n W $l(X)\n Q\n"
        out = expand_intrinsic_functions(src)
        assert b"$length(X)" in out

    def test_idempotent(self) -> None:
        src = b"hello ;c\n W $L(X),$E(X,1,3)\n Q\n"
        once = expand_intrinsic_functions(src)
        twice = expand_intrinsic_functions(once)
        assert once == twice

    def test_does_not_touch_command_keywords(self) -> None:
        src = b"hello ;c\n S X=1\n Q\n"
        # No intrinsic functions present — should be a no-op.
        assert expand_intrinsic_functions(src) == src

    def test_preserves_ast_shape(self) -> None:
        src = b"hello ;c\n W $L(X),$E(X,1,3)\n Q\n"
        before = _collapsed_tree(src)
        after = _collapsed_tree(expand_intrinsic_functions(src))
        assert before == after


class TestCompactIntrinsicFunctions:
    def test_canonical_compacted(self) -> None:
        src = b"hello ;c\n W $LENGTH(X)\n Q\n"
        out = compact_intrinsic_functions(src)
        assert b"$L(X)" in out

    def test_already_compact_unchanged(self) -> None:
        src = b"hello ;c\n W $L(X)\n Q\n"
        assert compact_intrinsic_functions(src) == src

    def test_round_trip_with_expand(self) -> None:
        canonical = b"hello ;c\n W $LENGTH(X),$EXTRACT(X,1,3)\n Q\n"
        compacted = compact_intrinsic_functions(canonical)
        assert expand_intrinsic_functions(compacted) == canonical


class TestExpandSpecialVariables:
    def test_short_isv_expanded(self) -> None:
        src = b"hello ;c\n W $T\n Q\n"
        out = expand_special_variables(src)
        assert b" $TEST\n" in out

    def test_canonical_unchanged(self) -> None:
        src = b"hello ;c\n W $TEST\n Q\n"
        assert expand_special_variables(src) == src

    def test_idempotent(self) -> None:
        src = b"hello ;c\n W $T,$H,$J\n Q\n"
        once = expand_special_variables(src)
        twice = expand_special_variables(once)
        assert once == twice

    def test_does_not_touch_intrinsic_functions(self) -> None:
        # $L is a function (intrinsic_function_keyword), not an ISV — must be
        # left alone by the ISV rule.
        src = b"hello ;c\n W $L(X)\n Q\n"
        assert expand_special_variables(src) == src


class TestCompactSpecialVariables:
    def test_canonical_compacted(self) -> None:
        src = b"hello ;c\n W $TEST\n Q\n"
        out = compact_special_variables(src)
        assert b" $T\n" in out

    def test_round_trip_with_expand(self) -> None:
        canonical = b"hello ;c\n W $TEST,$HOROLOG,$JOB\n Q\n"
        compacted = compact_special_variables(canonical)
        assert expand_special_variables(compacted) == canonical


# ---------------------------------------------------------------------------
# Lowercase rules — companions to uppercase-command-keywords
# ---------------------------------------------------------------------------


class TestLowercaseCommandKeywords:
    def test_uppercase_keyword_lowered(self) -> None:
        src = b"hello ;c\n SET X=1\n QUIT\n"
        out = lowercase_command_keywords(src)
        assert b" set X=1" in out
        assert b" quit\n" in out

    def test_already_lowercase_unchanged(self) -> None:
        src = b"hello ;c\n set X=1\n quit\n"
        assert lowercase_command_keywords(src) == src

    def test_abbreviation_lowered(self) -> None:
        src = b"hello ;c\n S X=1\n Q\n"
        out = lowercase_command_keywords(src)
        assert b" s X=1" in out
        assert b" q\n" in out

    def test_does_not_touch_arguments(self) -> None:
        # An uppercase variable in the args must survive — only the keyword
        # changes.
        src = b"hello ;c\n SET FOOBAR=1\n"
        out = lowercase_command_keywords(src)
        assert b"FOOBAR" in out
        assert b" set FOOBAR=1" in out

    def test_does_not_touch_comments(self) -> None:
        src = b"hello ;SET BAR is documented\n QUIT\n"
        out = lowercase_command_keywords(src)
        assert b";SET BAR is documented" in out

    def test_idempotent(self) -> None:
        src = b"hello ;c\n SET X=1\n WRITE X\n QUIT\n"
        once = lowercase_command_keywords(src)
        twice = lowercase_command_keywords(once)
        assert once == twice

    def test_inverse_of_uppercase(self) -> None:
        """upper(lower(src)) == upper(src) for any keyword input."""
        src = b"hello ;c\n SET X=1\n write X\n Q\n"
        round_trip = uppercase_command_keywords(lowercase_command_keywords(src))
        all_upper = uppercase_command_keywords(src)
        assert round_trip == all_upper

    def test_preserves_ast_shape(self) -> None:
        src = b"hello ;c\n SET X=1\n WRITE X\n QUIT\n"
        before = _collapsed_tree(src)
        after = _collapsed_tree(lowercase_command_keywords(src))
        assert before == after

    def test_safe_on_parse_error(self) -> None:
        out = lowercase_command_keywords(b"!!! not valid M\n")
        assert isinstance(out, bytes)

    def test_empty_input(self) -> None:
        assert lowercase_command_keywords(b"") == b""


class TestLowercaseIntrinsicFunctions:
    def test_uppercase_function_lowered(self) -> None:
        src = b"hello ;c\n W $LENGTH(X)\n"
        out = lowercase_intrinsic_functions(src)
        assert b"$length(X)" in out

    def test_abbreviation_lowered(self) -> None:
        src = b"hello ;c\n W $L(X)\n"
        out = lowercase_intrinsic_functions(src)
        assert b"$l(X)" in out

    def test_already_lowercase_unchanged(self) -> None:
        src = b"hello ;c\n W $length(X)\n"
        assert lowercase_intrinsic_functions(src) == src

    def test_does_not_touch_command_keywords(self) -> None:
        # No intrinsic functions present — no edits.
        src = b"hello ;c\n SET X=1\n"
        assert lowercase_intrinsic_functions(src) == src

    def test_idempotent(self) -> None:
        src = b"hello ;c\n W $LENGTH(X),$EXTRACT(X,1,3)\n"
        once = lowercase_intrinsic_functions(src)
        twice = lowercase_intrinsic_functions(once)
        assert once == twice


class TestLowercaseSpecialVariables:
    def test_uppercase_isv_lowered(self) -> None:
        src = b"hello ;c\n W $TEST\n"
        out = lowercase_special_variables(src)
        assert b" $test\n" in out

    def test_abbreviation_lowered(self) -> None:
        src = b"hello ;c\n W $T\n"
        out = lowercase_special_variables(src)
        assert b" $t\n" in out

    def test_already_lowercase_unchanged(self) -> None:
        src = b"hello ;c\n W $test\n"
        assert lowercase_special_variables(src) == src

    def test_does_not_touch_intrinsic_functions(self) -> None:
        src = b"hello ;c\n W $LENGTH(X)\n"
        assert lowercase_special_variables(src) == src

    def test_idempotent(self) -> None:
        src = b"hello ;c\n W $TEST,$HOROLOG,$JOB\n"
        once = lowercase_special_variables(src)
        twice = lowercase_special_variables(once)
        assert once == twice


# ---------------------------------------------------------------------------
# Translation presets
# ---------------------------------------------------------------------------


class TestTranslationPresets:
    def test_pythonic_returns_expected_rules(self) -> None:
        ids = [r.id for r in pythonic_rules()]
        assert ids == [
            "expand-command-keywords",
            "expand-intrinsic-functions",
            "expand-special-variables",
            "trim-trailing-whitespace",
        ]

    def test_compact_returns_expected_rules(self) -> None:
        ids = [r.id for r in compact_rules()]
        assert ids == [
            "compact-command-keywords",
            "compact-intrinsic-functions",
            "compact-special-variables",
            "trim-trailing-whitespace",
        ]

    def test_pythonic_lower_returns_expected_rules(self) -> None:
        """Order matters: lowercase rules must run *before* expand rules."""
        ids = [r.id for r in pythonic_lower_rules()]
        assert ids == [
            "lowercase-command-keywords",
            "lowercase-intrinsic-functions",
            "lowercase-special-variables",
            "expand-command-keywords",
            "expand-intrinsic-functions",
            "expand-special-variables",
            "trim-trailing-whitespace",
        ]

    def test_pythonic_lower_full_expansion(self) -> None:
        from m_cli.fmt.formatter import format_source

        src = b"hello ;c\n S X=1 W $L(X),$T\n Q\n"
        out = format_source(src, rules=pythonic_lower_rules())
        # Commands lowered + expanded; functions and ISVs the same.
        assert b" set X=1 write $length(X),$test" in out
        assert b" quit" in out

    def test_pythonic_lower_idempotent(self) -> None:
        from m_cli.fmt.formatter import format_source

        src = b"hello ;c\n SET X=1\n W $L(X),$T\n Q\n"
        once = format_source(src, rules=pythonic_lower_rules())
        twice = format_source(once, rules=pythonic_lower_rules())
        assert once == twice

    def test_pythonic_lower_preserves_variables_and_strings(self) -> None:
        """Only keywords are case-folded — names, labels, strings preserved."""
        from m_cli.fmt.formatter import format_source

        src = b'hello ;c\n S MSG="HELLO WORLD",CNT=$L(MSG)\n W !,MSG,!\n Q\n'
        out = format_source(src, rules=pythonic_lower_rules())
        # Variable names preserved.
        assert b"MSG" in out
        assert b"CNT" in out
        # String literal preserved (uppercase).
        assert b'"HELLO WORLD"' in out
        # Keywords lowered + expanded.
        assert b" set MSG=" in out
        assert b" write " in out
        assert b"$length(MSG)" in out

    def test_select_fmt_rules_pythonic_lower(self) -> None:
        from m_cli.fmt.rules import select_fmt_rules as sel

        rules = sel("pythonic-lower")
        assert [r.id for r in rules] == [r.id for r in pythonic_lower_rules()]

    def test_pythonic_lower_compact_round_trip_modulo_case(self) -> None:
        """Round-trip recovers structure but not case.

        ``compact(pythonic-lower(SRC))`` produces a *lowercase* compact form,
        so byte-equality with an uppercase original isn't expected. The
        recoverable invariant is up to keyword case: re-uppercasing
        commands / functions / ISVs gives back the original.
        """
        from m_cli.fmt.formatter import format_source

        compact_src = b"hello ;c\n S X=1\n W $L(X),$T\n Q\n"
        lower = format_source(compact_src, rules=pythonic_lower_rules())
        recovered_lower = format_source(lower, rules=compact_rules())
        # Lowercase form of original compact source.
        re_uppered = uppercase_command_keywords(recovered_lower)
        re_uppered = _rewrite_node_case_helper(
            re_uppered, "intrinsic_function_keyword"
        )
        re_uppered = _rewrite_node_case_helper(re_uppered, "special_variable_keyword")
        assert re_uppered == compact_src


def _rewrite_node_case_helper(src: bytes, node_type: str) -> bytes:
    """Helper for the round-trip test: uppercase a single keyword type."""
    from m_cli.fmt.rules import _rewrite_node_case

    return _rewrite_node_case(src, node_type, bytes.upper)

    def test_pythonic_is_inverse_of_compact_on_normalized_input(self) -> None:
        """Round-trip property: compact and pythonic are normalizing.

        On already-normalized input (all-compact or all-canonical), the
        round-trip ``compact(pythonic(src))`` recovers the original.
        On mixed-form input, the round-trip collapses to a single form
        — which is the intended behavior of a normalizer.
        """
        from m_cli.fmt.formatter import format_source

        compact_src = b"hello ;c\n S X=1\n W $L(X),$T\n Q\n"
        expanded = format_source(compact_src, rules=pythonic_rules())
        recovered = format_source(expanded, rules=compact_rules())
        assert recovered == compact_src

        # Same property in the other direction.
        canonical_src = b"hello ;c\n SET X=1\n WRITE $LENGTH(X),$TEST\n QUIT\n"
        compacted = format_source(canonical_src, rules=compact_rules())
        re_expanded = format_source(compacted, rules=pythonic_rules())
        assert re_expanded == canonical_src

    def test_pythonic_normalizes_mixed_input(self) -> None:
        """Mixed-form input is intentionally collapsed to canonical."""
        from m_cli.fmt.formatter import format_source

        mixed = b"hello ;c\n S X=1\n WRITE $L(X)\n Q\n"
        out = format_source(mixed, rules=pythonic_rules())
        # All commands canonical, all functions canonical.
        assert b" SET X=1" in out
        assert b" WRITE $LENGTH(X)" in out
        assert b" QUIT" in out

    def test_pythonic_preset_full_expansion(self) -> None:
        from m_cli.fmt.formatter import format_source

        src = b"hello ;c\n S X=1 W $L(X),$T\n Q\n"
        out = format_source(src, rules=pythonic_rules())
        assert b" SET X=1 WRITE $LENGTH(X),$TEST" in out
        assert b" QUIT" in out

    def test_compact_preset_full_compaction(self) -> None:
        from m_cli.fmt.formatter import format_source

        src = b"hello ;c\n SET X=1 WRITE $LENGTH(X),$TEST\n QUIT\n"
        out = format_source(src, rules=compact_rules())
        assert b" S X=1 W $L(X),$T" in out
        assert b" Q\n" in out

    def test_pythonic_idempotent(self) -> None:
        from m_cli.fmt.formatter import format_source

        src = b"hello ;c\n S X=1\n W $L(X),$T\n Q\n"
        once = format_source(src, rules=pythonic_rules())
        twice = format_source(once, rules=pythonic_rules())
        assert once == twice

    def test_pythonic_includes_registered_rules_only(self) -> None:
        for rule in pythonic_rules():
            assert rule_by_id(rule.id) is rule

    def test_pythonic_safe_on_parse_error(self) -> None:
        from m_cli.fmt.formatter import format_source

        src = b"!!! garbage that does not parse\n"
        # ParseError must propagate from format_source — not silently mangle.
        with pytest.raises(Exception):  # ParseError, but exact class is in fmt
            format_source(src, rules=pythonic_rules())


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
