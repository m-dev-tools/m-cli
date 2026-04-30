"""Diagnostic types for `m lint`.

A Diagnostic is one finding — a rule fired at a specific location in a
specific file. The CLI / output formatters turn these into text, JSON,
TAP, or LSP diagnostics.

Two orthogonal axes describe a finding:

**Severity** — actionability. How urgent is the fix?

  ERROR    — must fix. Bug, vulnerability, or invalid syntax.
             CI gate fails by default.
  WARNING  — should fix. Likely bug or unsafe pattern.
             CI gate fails when ``--error-on=warning`` (default).
  STYLE    — auto-fix preferred. Convention or readability concern;
             usually has an associated `m fmt` rule. CI passes by
             default; appears as an editor "Hint" in LSP clients.
  INFO     — informational. No action expected (metric report,
             contextual note). Never fails CI.

**Category** — kind. What concern does this finding belong to?

  BUG             — defect detection (undefined ref, dead code, ...)
  SECURITY        — taint, injection, unsafe operations
  CONCURRENCY     — locks, transactions, races
  PERFORMANCE     — perf-relevant patterns
  STYLE           — readability / convention
  COMPLEXITY      — over a metric threshold (length, cyclomatic, ...)
  DOCUMENTATION   — comment / docstring concerns
  PORTABILITY     — engine-specific construct that limits portability
  MODERNIZATION   — legacy idiom with a modern alternative

Rules pick a severity AND a category at registration. Per-project
severity overrides go through ``[lint.severity]`` in ``.m-cli.toml``.
The two-axis scheme is engine- and dialect-neutral; the LSP wrapper
maps Severity to ``lsprotocol.DiagnosticSeverity`` (ERROR→Error,
WARNING→Warning, STYLE→Hint, INFO→Information).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(Enum):
    """Actionability axis. See module docstring for semantics."""

    ERROR = "error"
    WARNING = "warning"
    STYLE = "style"
    INFO = "info"

    @property
    def short(self) -> str:
        """One-letter severity code (E/W/S/I) for compact summary output."""
        return {
            Severity.ERROR: "E",
            Severity.WARNING: "W",
            Severity.STYLE: "S",
            Severity.INFO: "I",
        }[self]

    @property
    def is_actionable(self) -> bool:
        """True when the finding expects the developer to do something.

        ERROR / WARNING / STYLE all imply an action (fix, suppress, or
        accept-via-config). INFO is purely informational and expects
        no response.
        """
        return self is not Severity.INFO


class Category(Enum):
    """Kind axis. See module docstring for semantics."""

    BUG = "bug"
    SECURITY = "security"
    CONCURRENCY = "concurrency"
    PERFORMANCE = "performance"
    STYLE = "style"
    COMPLEXITY = "complexity"
    DOCUMENTATION = "documentation"
    PORTABILITY = "portability"
    MODERNIZATION = "modernization"


@dataclass(frozen=True)
class Diagnostic:
    """One linter finding.

    Fields use 1-based line/column numbering (matching the convention
    used by editors / LSP clients). `column_end` is exclusive;
    `column_end == column` means a point diagnostic with no range.
    """

    rule_id: str
    """Stable rule identifier, e.g. `M-XINDX-013` or `M-MOD-NN`."""

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
