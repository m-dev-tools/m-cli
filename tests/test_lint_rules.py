"""Per-rule unit tests for `m lint`.

Each rule has at least one positive test (must fire) and one negative
test (must not fire). Tests are named after the rule ID.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from m_cli.lint.runner import lint_source, select_rules


def _lint(src: bytes, rule_id: str, path: Path | None = None):
    """Run a single rule by id and return its diagnostics."""
    rules = select_rules(rule_id)
    return lint_source(path or Path(rule_id.replace("-", "") + ".m"), src, rules)


# ---------------------------------------------------------------------------
# Text-based rules
# ---------------------------------------------------------------------------

class TestTrailingBlanks:
    """M-XINDX-013 — Blank(s) at end of line."""

    def test_fires_on_trailing_space(self):
        src = b"hello ;ok\n quit \n"
        diags = _lint(src, "M-XINDX-013")
        assert len(diags) == 1
        assert diags[0].rule_id == "M-XINDX-013"
        assert diags[0].line == 2

    def test_clean_source_no_finding(self):
        src = b"hello ;ok\n quit\n"
        assert _lint(src, "M-XINDX-013") == []


class TestControlChars:
    """M-XINDX-018 — CONTROL char on line."""

    def test_fires_on_form_feed(self):
        src = b"hello ;ok\n quit\x0c\n"
        diags = _lint(src, "M-XINDX-018")
        assert len(diags) == 1

    def test_tab_is_allowed(self):
        src = b"hello ;ok\n\tquit\n"
        assert _lint(src, "M-XINDX-018") == []

    def test_clean_source_no_finding(self):
        assert _lint(b"hello\n quit\n", "M-XINDX-018") == []


class TestLineLength:
    """M-XINDX-019 — Line longer than 245 bytes."""

    def test_fires_on_long_line(self):
        long_line = b" w " + b"x" * 250 + b"\n"
        src = b"hello\n" + long_line + b" quit\n"
        diags = _lint(src, "M-XINDX-019")
        assert len(diags) == 1
        assert diags[0].line == 2

    def test_short_lines_no_finding(self):
        assert _lint(b"hello\n quit\n", "M-XINDX-019") == []


class TestNullLine:
    """M-XINDX-042 — Null line (no commands or comment)."""

    def test_fires_on_blank_line_in_middle(self):
        src = b"hello\n\n quit\n"
        diags = _lint(src, "M-XINDX-042")
        assert len(diags) == 1
        assert diags[0].line == 2

    def test_no_finding_for_only_trailing_blank(self):
        src = b"hello\n quit\n"
        assert _lint(src, "M-XINDX-042") == []


class TestRoutineSize:
    """M-XINDX-035 — Routine exceeds 20000 bytes."""

    def test_fires_above_20kb(self):
        src = b"hello\n" + (b" w \"x\"\n" * 4000)  # ~24kb
        diags = _lint(src, "M-XINDX-035")
        assert len(diags) == 1

    def test_no_finding_below_20kb(self):
        src = b"hello\n quit\n"
        assert _lint(src, "M-XINDX-035") == []


class TestSecondLineSAC:
    """M-XINDX-044 — Second line violates SAC."""

    def test_fires_on_missing_double_semicolon(self):
        src = b"hello ;routine\n new x\n quit\n"
        diags = _lint(src, "M-XINDX-044")
        assert len(diags) == 1
        assert diags[0].line == 2

    def test_no_finding_on_proper_sac(self):
        src = b"hello ;routine\n ;;1.0;PKG;;Jan 1, 2025;Build 1\n quit\n"
        assert _lint(src, "M-XINDX-044") == []


# ---------------------------------------------------------------------------
# AST-based rules
# ---------------------------------------------------------------------------

class TestFirstLabel:
    """M-XINDX-017 — First label != routine name."""

    def test_fires_when_label_mismatches_filename(self):
        src = b"WRONG ;label not matching filename\n quit\n"
        diags = _lint(src, "M-XINDX-017", path=Path("CORRECT.m"))
        assert len(diags) == 1
        assert "WRONG" in diags[0].message
        assert "CORRECT" in diags[0].message

    def test_no_finding_when_label_matches(self):
        src = b"HELLO ;ok\n quit\n"
        assert _lint(src, "M-XINDX-017", path=Path("HELLO.m")) == []

    def test_percent_routines_excluded(self):
        # XINDEX exclusion: %-prefixed routines may have different label
        src = b"foo ;ok\n quit\n"
        assert _lint(src, "M-XINDX-017", path=Path("%foo.m")) == []


class TestDuplicateLabels:
    """M-XINDX-015 — Duplicate label."""

    def test_fires_on_duplicate(self):
        src = b"hello ;ok\n quit\nhello ;dup\n quit\n"
        diags = _lint(src, "M-XINDX-015")
        assert len(diags) == 1
        assert diags[0].line == 3

    def test_no_finding_on_unique_labels(self):
        src = b"hello ;ok\n quit\nworld ;ok\n quit\n"
        assert _lint(src, "M-XINDX-015") == []


class TestMissingLabelCall:
    """M-XINDX-014 — Call to missing label in this routine."""

    def test_fires_on_undefined_label(self):
        src = b"hello ;ok\n do undefined\n quit\n"
        diags = _lint(src, "M-XINDX-014", path=Path("hello.m"))
        # Look for our specific finding (other rules may also fire)
        our = [d for d in diags if d.rule_id == "M-XINDX-014"]
        assert len(our) == 1
        assert "undefined" in our[0].message

    def test_no_finding_when_label_exists(self):
        src = b"hello ;ok\n do helper\n quit\nhelper ;ok\n quit\n"
        diags = _lint(src, "M-XINDX-014", path=Path("hello.m"))
        our = [d for d in diags if d.rule_id == "M-XINDX-014"]
        assert our == []


class TestBreakCommand:
    """M-XINDX-025 — BREAK command used."""

    def test_fires_on_break(self):
        src = b"hello ;ok\n break\n quit\n"
        diags = _lint(src, "M-XINDX-025")
        assert len(diags) == 1

    def test_fires_on_b_short_form(self):
        src = b"hello ;ok\n b\n quit\n"
        diags = _lint(src, "M-XINDX-025")
        assert len(diags) == 1

    def test_no_finding_without_break(self):
        src = b"hello ;ok\n quit\n"
        assert _lint(src, "M-XINDX-025") == []


# ---------------------------------------------------------------------------
# Framework tests
# ---------------------------------------------------------------------------

class TestRuleSelection:
    def test_xindex_tag_returns_xindex_rules(self):
        rules = select_rules("xindex")
        assert len(rules) > 0
        assert all("xindex" in r.tags for r in rules)

    def test_all_returns_every_rule(self):
        rules = select_rules("all")
        assert len(rules) > 0

    def test_explicit_id_list(self):
        rules = select_rules("M-XINDX-013,M-XINDX-019")
        assert {r.id for r in rules} == {"M-XINDX-013", "M-XINDX-019"}

    def test_unknown_id_raises(self):
        with pytest.raises(ValueError, match="unknown rule id"):
            select_rules("M-XINDX-999")
