"""Tests for ``m_cli.lint._directives`` and lint_source integration.

Inline ``; m-lint: disable=...`` directives let users suppress
diagnostics on a per-line / per-file basis without editing the
project config.
"""

from __future__ import annotations

from pathlib import Path

from m_cli.lint._directives import Suppressions, parse_directives
from m_cli.lint.rules import _REGISTRY
from m_cli.lint.runner import lint_source, select_rules

# ---------------------------------------------------------------------------
# parse_directives
# ---------------------------------------------------------------------------


def test_parse_disable_same_line() -> None:
    src = b" SET X=1 ; m-lint: disable=M-XINDX-047\n"
    s = parse_directives(src)
    assert s.is_suppressed(1, "M-XINDX-047")
    assert not s.is_suppressed(2, "M-XINDX-047")
    assert not s.is_suppressed(1, "M-XINDX-013")  # different rule unaffected


def test_parse_disable_next_line() -> None:
    src = b"; m-lint: disable-next-line=M-XINDX-019\n SET X=1\n"
    s = parse_directives(src)
    # The directive line itself is line 1; next line is 2.
    assert not s.is_suppressed(1, "M-XINDX-019")
    assert s.is_suppressed(2, "M-XINDX-019")


def test_parse_disable_file() -> None:
    src = b"; m-lint: disable-file=M-XINDX-013\n SET X=1\n SET Y=2\n"
    s = parse_directives(src)
    # File-level disables apply to every line.
    assert s.is_suppressed(1, "M-XINDX-013")
    assert s.is_suppressed(99, "M-XINDX-013")
    assert not s.is_suppressed(1, "M-XINDX-019")


def test_parse_wildcard_disables_all_rules() -> None:
    src = b" SET X=1 ; m-lint: disable=*\n"
    s = parse_directives(src)
    assert s.is_suppressed(1, "M-XINDX-013")
    assert s.is_suppressed(1, "M-XINDX-019")
    assert s.is_suppressed(1, "ANY-RULE-ID")


def test_parse_comma_separated_rule_ids() -> None:
    src = b" SET X=1 ; m-lint: disable=M-XINDX-013,M-XINDX-019\n"
    s = parse_directives(src)
    assert s.is_suppressed(1, "M-XINDX-013")
    assert s.is_suppressed(1, "M-XINDX-019")
    assert not s.is_suppressed(1, "M-XINDX-047")


def test_parse_tolerates_whitespace_around_punctuation() -> None:
    src = b" SET X=1 ;  m-lint :  disable = M-XINDX-013  \n"
    s = parse_directives(src)
    assert s.is_suppressed(1, "M-XINDX-013")


def test_parse_ignores_unrelated_comments() -> None:
    src = b" SET X=1 ; just a normal comment\n; another comment\n"
    s = parse_directives(src)
    assert not s.is_suppressed(1, "M-XINDX-013")
    assert s == Suppressions.empty()


def test_parse_multiple_directives_in_one_file() -> None:
    src = (
        b"; m-lint: disable-file=M-XINDX-019\n"
        b" SET X=1 ; m-lint: disable=M-XINDX-013\n"
        b"; m-lint: disable-next-line=M-XINDX-047\n"
        b" set y=2\n"
    )
    s = parse_directives(src)
    assert s.is_suppressed(1, "M-XINDX-019")  # file-wide
    assert s.is_suppressed(2, "M-XINDX-013")  # same-line
    assert s.is_suppressed(2, "M-XINDX-019")  # also file-wide
    assert s.is_suppressed(4, "M-XINDX-047")  # next-line directive
    assert not s.is_suppressed(2, "M-XINDX-047")


def test_parse_empty_source_produces_empty_suppressions() -> None:
    assert parse_directives(b"") == Suppressions.empty()


# ---------------------------------------------------------------------------
# lint_source integration
# ---------------------------------------------------------------------------


def _xindx_013() -> list:
    return [_REGISTRY["M-XINDX-013"]]


def test_lint_source_respects_same_line_disable(tmp_path: Path) -> None:
    """A trailing-whitespace finding (M-XINDX-013) on a line
    suppressed by an inline directive must not appear in the output."""
    p = tmp_path / "FOO.m"
    src = b"FOO ;c\n SET X=1   ; m-lint: disable=M-XINDX-013\n QUIT\n"
    diags = lint_source(p, src, _xindx_013())
    assert all(d.rule_id != "M-XINDX-013" for d in diags)


def test_lint_source_respects_disable_file(tmp_path: Path) -> None:
    p = tmp_path / "FOO.m"
    src = b"; m-lint: disable-file=M-XINDX-013\nFOO   \n SET X=1   \n QUIT\n"
    diags = lint_source(p, src, _xindx_013())
    assert all(d.rule_id != "M-XINDX-013" for d in diags)


def test_lint_source_disable_next_line(tmp_path: Path) -> None:
    p = tmp_path / "FOO.m"
    src = (
        b"FOO ;c\n"
        b"; m-lint: disable-next-line=M-XINDX-013\n"
        b" SET X=1   \n"  # trailing space, would be M-XINDX-013 — suppressed
        b" SET Y=2   \n"  # trailing space, NOT suppressed
        b" QUIT\n"
    )
    diags = lint_source(p, src, _xindx_013())
    flagged_lines = [d.line for d in diags if d.rule_id == "M-XINDX-013"]
    # Line 3 is suppressed; line 4 still fires.
    assert 3 not in flagged_lines
    assert 4 in flagged_lines


def test_lint_source_disable_other_rule_still_fires(tmp_path: Path) -> None:
    """Disabling M-XINDX-013 doesn't silence M-XINDX-047."""
    rules = [_REGISTRY["M-XINDX-013"], _REGISTRY["M-XINDX-047"]]
    p = tmp_path / "FOO.m"
    # Trailing space (013) AND lowercase command (047) on same line.
    src = b"FOO ;c\n set X=1   ; m-lint: disable=M-XINDX-013\n QUIT\n"
    diags = lint_source(p, src, rules)
    flagged = {d.rule_id for d in diags if d.line == 2}
    assert "M-XINDX-013" not in flagged
    assert "M-XINDX-047" in flagged


def test_lint_source_wildcard_disables_everything(tmp_path: Path) -> None:
    rules = select_rules("xindex")
    p = tmp_path / "FOO.m"
    # Lots of issues on this line, but all suppressed.
    src = b"; m-lint: disable-file=*\n foo bar baz\n"
    diags = lint_source(p, src, rules)
    assert diags == []


def test_lint_source_internal_rule_crash_is_never_suppressed(
    tmp_path: Path,
) -> None:
    """Disable directives must not silence the rule-crash diagnostic —
    the user always wants to know about a buggy rule."""
    from m_cli.lint.diagnostic import Category, Severity
    from m_cli.lint.rules import _REGISTRY as registry
    from m_cli.lint.rules import Rule

    def crashing_check(src, tree, path, index):
        raise RuntimeError("oops")

    crash_rule = Rule(
        id="TEST-CRASH-1",
        severity=Severity.WARNING,
        category=Category.BUG,
        title="Crash test rule",
        tags=("test",),
        check=crashing_check,
    )
    registry["TEST-CRASH-1"] = crash_rule
    try:
        p = tmp_path / "FOO.m"
        src = b"; m-lint: disable-file=*\n FOO\n"
        diags = lint_source(p, src, [crash_rule])
        # Crash diagnostic survives the wildcard disable.
        assert any(d.rule_id == "M-INTERNAL-RULE-CRASH" for d in diags)
    finally:
        del registry["TEST-CRASH-1"]
