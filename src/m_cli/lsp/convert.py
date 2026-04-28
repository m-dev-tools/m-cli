"""Convert ``m_cli.lint.Diagnostic`` instances into LSP wire-format.

LSP positions are zero-indexed, m-cli's are one-indexed. LSP severity
is a four-level enum (Error/Warning/Information/Hint); m-cli's
severity is also four levels but with different semantics — the
mapping below is the agreed compromise.

The auto-fixer linkage (``Rule.fixer_id``, ``m_cli.lint.fixer_for``)
is forwarded into LSP's ``data`` field so the Stage 3 code-action
handler can offer Quick Fixes without re-querying the registry.
"""

from __future__ import annotations

from collections.abc import Iterable

from lsprotocol.types import Diagnostic as LspDiagnostic
from lsprotocol.types import DiagnosticSeverity, Position, Range

from m_cli.lint import Diagnostic, Severity, fixer_for

_SEVERITY_MAP: dict[Severity, DiagnosticSeverity] = {
    Severity.FATAL: DiagnosticSeverity.Error,
    Severity.STANDARD: DiagnosticSeverity.Warning,
    Severity.WARNING: DiagnosticSeverity.Warning,
    Severity.INFO: DiagnosticSeverity.Information,
}


def to_lsp_diagnostic(diag: Diagnostic) -> LspDiagnostic:
    """Map one m-cli ``Diagnostic`` to an LSP ``Diagnostic``."""
    line0 = max(0, diag.line - 1)
    col0 = max(0, diag.column - 1)
    end_col0 = max(col0, diag.column_end - 1) if diag.column_end is not None else col0
    fixer = fixer_for(diag.rule_id)
    return LspDiagnostic(
        range=Range(
            start=Position(line=line0, character=col0),
            end=Position(line=line0, character=end_col0),
        ),
        severity=_SEVERITY_MAP[diag.severity],
        code=diag.rule_id,
        source="m-cli",
        message=diag.message,
        data={"fixer_id": fixer} if fixer else None,
    )


def to_lsp_diagnostics(diags: Iterable[Diagnostic]) -> list[LspDiagnostic]:
    """Bulk convert."""
    return [to_lsp_diagnostic(d) for d in diags]
