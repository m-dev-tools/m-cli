"""Tests for ``m_cli.lsp.convert`` — m-cli Diagnostic to LSP-shape mapper.

The conversion is a pure function. LSP positions are 0-indexed; the
m-cli Diagnostic uses 1-indexed line and column. The severity scheme
collapses from four levels (XINDEX FATAL/STANDARD/WARNING/INFO) to
LSP's four-level set (Error/Warning/Information/Hint). Rule id goes
in ``code``; the auto-fixer id (if any) goes in ``data`` so the
code-action handler in Stage 3 can pick it up without a second
registry lookup.
"""

from __future__ import annotations

from pathlib import Path

from lsprotocol.types import DiagnosticSeverity

from m_cli.lint import Diagnostic, Severity
from m_cli.lsp.convert import to_lsp_diagnostic, to_lsp_diagnostics


def _diag(
    *,
    rule_id: str = "M-XINDX-013",
    severity: Severity = Severity.WARNING,
    message: str = "trailing blanks",
    line: int = 5,
    column: int = 3,
    column_end: int | None = 7,
) -> Diagnostic:
    return Diagnostic(
        rule_id=rule_id,
        severity=severity,
        message=message,
        path=Path("hello.m"),
        line=line,
        column=column,
        column_end=column_end,
    )


# ---------------------------------------------------------------------------
# Position translation: 1-based -> 0-based
# ---------------------------------------------------------------------------


def test_line_is_zero_indexed() -> None:
    out = to_lsp_diagnostic(_diag(line=10))
    assert out.range.start.line == 9
    assert out.range.end.line == 9


def test_column_is_zero_indexed() -> None:
    out = to_lsp_diagnostic(_diag(column=4, column_end=10))
    assert out.range.start.character == 3
    assert out.range.end.character == 9


def test_line_one_clamped_to_zero() -> None:
    out = to_lsp_diagnostic(_diag(line=1, column=1, column_end=2))
    assert out.range.start.line == 0
    assert out.range.start.character == 0


def test_missing_column_end_collapses_to_point_range() -> None:
    """A diagnostic with no column_end becomes a zero-width LSP range."""
    out = to_lsp_diagnostic(_diag(column=5, column_end=None))
    assert out.range.start.character == 4
    assert out.range.end.character == 4


# ---------------------------------------------------------------------------
# Severity mapping
# ---------------------------------------------------------------------------


def test_error_maps_to_lsp_error() -> None:
    out = to_lsp_diagnostic(_diag(severity=Severity.ERROR))
    assert out.severity == DiagnosticSeverity.Error


def test_warning_maps_to_lsp_warning() -> None:
    out = to_lsp_diagnostic(_diag(severity=Severity.WARNING))
    assert out.severity == DiagnosticSeverity.Warning


def test_style_maps_to_lsp_hint() -> None:
    # STYLE diagnostics surface as LSP Hints (subtle suggestion / refactor
    # opportunity), since they are typically auto-fixable conventions.
    out = to_lsp_diagnostic(_diag(severity=Severity.STYLE))
    assert out.severity == DiagnosticSeverity.Hint


def test_info_maps_to_lsp_information() -> None:
    out = to_lsp_diagnostic(_diag(severity=Severity.INFO))
    assert out.severity == DiagnosticSeverity.Information


# ---------------------------------------------------------------------------
# Code, source, message
# ---------------------------------------------------------------------------


def test_code_carries_rule_id() -> None:
    out = to_lsp_diagnostic(_diag(rule_id="M-XINDX-014"))
    assert out.code == "M-XINDX-014"


def test_source_is_m_cli() -> None:
    out = to_lsp_diagnostic(_diag())
    assert out.source == "m-cli"


def test_message_is_carried_through() -> None:
    out = to_lsp_diagnostic(_diag(message="something specific"))
    assert out.message == "something specific"


# ---------------------------------------------------------------------------
# Fixer linkage in `data`
# ---------------------------------------------------------------------------


def test_data_carries_fixer_id_when_rule_has_one() -> None:
    out = to_lsp_diagnostic(_diag(rule_id="M-XINDX-013"))
    assert out.data is not None
    assert out.data["fixer_id"] == "trim-trailing-whitespace"


def test_data_is_none_when_rule_has_no_fixer() -> None:
    out = to_lsp_diagnostic(_diag(rule_id="M-XINDX-014"))
    assert out.data is None


def test_data_is_none_when_rule_id_unknown() -> None:
    out = to_lsp_diagnostic(_diag(rule_id="not-a-real-rule"))
    assert out.data is None


# ---------------------------------------------------------------------------
# Bulk converter
# ---------------------------------------------------------------------------


def test_to_lsp_diagnostics_empty() -> None:
    assert to_lsp_diagnostics([]) == []


def test_to_lsp_diagnostics_passes_through_count() -> None:
    diags = [_diag(line=i) for i in (1, 5, 10)]
    out = to_lsp_diagnostics(diags)
    assert len(out) == 3
    assert [d.range.start.line for d in out] == [0, 4, 9]
