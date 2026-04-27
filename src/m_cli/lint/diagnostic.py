"""Diagnostic types for `m lint`.

A Diagnostic is one finding — a rule fired at a specific location in a
specific file. The CLI / output formatters turn these into text, JSON,
TAP, or LSP diagnostics.

Severity follows XINDEX's four-level scheme:
  Fatal     — definite bug or invalid syntax (XINDEX 'F')
  Standard  — code-quality issue per VA standards (XINDEX 'S')
  Warning   — potential bug or smell (XINDEX 'W')
  Info      — stylistic or informational (XINDEX 'I')
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(Enum):
    FATAL = "fatal"
    STANDARD = "standard"
    WARNING = "warning"
    INFO = "info"

    @property
    def short(self) -> str:
        """One-letter severity code matching XINDEX (F/S/W/I)."""
        return {
            Severity.FATAL: "F",
            Severity.STANDARD: "S",
            Severity.WARNING: "W",
            Severity.INFO: "I",
        }[self]


@dataclass(frozen=True)
class Diagnostic:
    """One linter finding.

    Fields use 1-based line/column numbering (matching editor + xindex
    conventions). `column_end` is exclusive; `column_end == column` means
    a point diagnostic with no range.
    """

    rule_id: str
    """Stable rule identifier, e.g. `M-XINDX-013`."""

    severity: Severity

    message: str
    """Human-readable description of the finding."""

    path: Path
    """Source file the finding applies to."""

    line: int
    """1-based line number where the finding starts."""

    column: int = 1
    """1-based column number where the finding starts."""

    column_end: int | None = None
    """Exclusive end column. None ⇒ to end of line."""

    line_text: str | None = None
    """The offending line, for inline display in human-readable output."""

    extra: dict[str, Any] = field(default_factory=dict)
    """Rule-specific metadata (target label name, etc.)."""

    def to_json(self) -> dict[str, Any]:
        """JSON-serialisable form for `--format=json`."""
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "path": str(self.path),
            "line": self.line,
            "column": self.column,
            "column_end": self.column_end,
            "line_text": self.line_text,
            "extra": self.extra,
        }
