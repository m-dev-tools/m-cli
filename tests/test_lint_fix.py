"""Tests for ``m lint --fix`` orchestration.

Covers the :func:`m_cli.lint.fix.apply_fixes` helper plus the CLI-
level wiring smoke-tested via subprocess. Unit-style tests here
work directly with the helper; the end-to-end behavior is exercised
by integration tests in ``test_lint_cli_integration.py`` if any.
"""

from __future__ import annotations

from pathlib import Path

from m_cli.lint.diagnostic import Diagnostic, Severity
from m_cli.lint.fix import apply_fixes


def _write(tmp_path: Path, name: str, text: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(text)
    return p


def _diag(rule_id: str, path: Path, line: int = 1, col: int = 1) -> Diagnostic:
    return Diagnostic(
        rule_id=rule_id,
        severity=Severity.STYLE,
        message="trailing whitespace",
        path=path,
        line=line,
        column=col,
        column_end=col + 1,
    )


class TestApplyFixes:
    def test_trims_trailing_whitespace_via_fixer_id(self, tmp_path: Path) -> None:
        f = _write(tmp_path, "demo.m", b"hello   \n quit  \n")
        result = apply_fixes([_diag("M-XINDX-013", f)])
        assert result.fixable_count == 1
        assert result.unfixable_count == 0
        assert f in result.files_changed
        assert f.read_bytes() == b"hello\n quit\n"
        assert result.by_fixer == {"trim-trailing-whitespace": 1}

    def test_uppercase_command_keywords_via_fixer_id(self, tmp_path: Path) -> None:
        f = _write(tmp_path, "demo.m", b"hello ;c\n set x=1\n quit\n")
        result = apply_fixes([_diag("M-XINDX-047", f)])
        assert result.fixable_count == 1
        assert f in result.files_changed
        assert b"SET x=1" in f.read_bytes()
        assert b"QUIT" in f.read_bytes()

    def test_collapses_multiple_diagnostics_to_single_rewrite(
        self, tmp_path: Path
    ) -> None:
        """Two M-XINDX-013 findings on the same file → one fmt invocation."""
        f = _write(tmp_path, "demo.m", b"line1   \nline2  \n")
        result = apply_fixes(
            [_diag("M-XINDX-013", f, line=1), _diag("M-XINDX-013", f, line=2)]
        )
        # Both diagnostics were addressed by a single fixer run.
        assert result.by_fixer == {"trim-trailing-whitespace": 2}
        assert f in result.files_changed
        assert f.read_bytes() == b"line1\nline2\n"

    def test_no_op_when_diag_has_no_fixer(self, tmp_path: Path) -> None:
        # M-XINDX-007 (call to undefined routine) has no fixer_id.
        f = _write(tmp_path, "demo.m", b"hello ;c\n D ^MISSING\n")
        result = apply_fixes([_diag("M-XINDX-007", f)])
        assert result.fixable_count == 0
        assert result.unfixable_count == 1
        assert result.files_changed == []
        # File untouched.
        assert f.read_bytes() == b"hello ;c\n D ^MISSING\n"

    def test_unknown_rule_id_treated_as_unfixable(self, tmp_path: Path) -> None:
        f = _write(tmp_path, "demo.m", b"x\n")
        result = apply_fixes([_diag("M-NONEXISTENT-999", f)])
        assert result.unfixable_count == 1
        assert result.fixable_count == 0

    def test_write_false_does_not_touch_file(self, tmp_path: Path) -> None:
        original = b"hello   \n quit  \n"
        f = _write(tmp_path, "demo.m", original)
        result = apply_fixes([_diag("M-XINDX-013", f)], write=False)
        # Counted as fixable, but the file on disk is unchanged.
        assert result.fixable_count == 1
        assert f.read_bytes() == original
        # files_changed lists files whose bytes WOULD move.
        assert f in result.files_changed

    def test_idempotent_apply(self, tmp_path: Path) -> None:
        """Re-running apply_fixes on already-fixed source is a no-op."""
        f = _write(tmp_path, "demo.m", b"hello\n quit\n")  # already clean
        result = apply_fixes([_diag("M-XINDX-013", f)])
        # The diagnostic is still counted as fixable (it had a fixer_id
        # registered), but the file didn't move.
        assert result.fixable_count == 1
        assert result.files_changed == []

    def test_handles_parse_errors_gracefully(self, tmp_path: Path) -> None:
        # uppercase-command-keywords aborts on parse errors (returns src
        # unchanged). The file shouldn't be skipped — it just doesn't
        # change.
        f = _write(tmp_path, "demo.m", b"!!! garbage that does not parse\n")
        result = apply_fixes([_diag("M-XINDX-047", f)])
        assert result.fixable_count == 1
        # No change to the file.
        assert b"!!! garbage" in f.read_bytes()

    def test_groups_fixers_per_file(self, tmp_path: Path) -> None:
        """Two distinct fixers on one file run separately."""
        f = _write(
            tmp_path, "demo.m", b"hello ;c   \n set x=1   \n quit  \n"
        )
        result = apply_fixes(
            [
                _diag("M-XINDX-013", f),  # trim
                _diag("M-XINDX-047", f),  # uppercase
            ]
        )
        assert result.fixable_count == 2
        assert set(result.by_fixer) == {
            "trim-trailing-whitespace",
            "uppercase-command-keywords",
        }
        new = f.read_bytes()
        assert b"   " not in new  # trim ran
        assert b"SET x=1" in new  # uppercase ran


class TestMmod035FixerWiring:
    """Pin the M-MOD-035 → expand-intrinsic-functions linkage."""

    def test_M_MOD_035_has_fixer_id(self) -> None:
        from m_cli.lint.runner import all_rules

        rule = next(r for r in all_rules() if r.id == "M-MOD-035")
        assert rule.fixer_id == "expand-intrinsic-functions"

    def test_fixer_resolvable(self) -> None:
        from m_cli.fmt.rules import rule_by_id
        from m_cli.lint.runner import fixer_for

        fmt_id = fixer_for("M-MOD-035")
        assert fmt_id == "expand-intrinsic-functions"
        assert rule_by_id(fmt_id) is not None
