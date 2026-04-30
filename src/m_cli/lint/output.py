"""Output formatters for `m lint` diagnostics.

Three formats:
  - text  — human-readable, one diagnostic per line, file:line:col-style
  - json  — machine-readable, one JSON object per file (or array)
  - tap   — TAP-13, for CI integration
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable

from m_cli.lint.diagnostic import Diagnostic, Severity
from m_cli.lint.runner import fixer_for

_SEV_COLOR = {
    Severity.ERROR: "\033[1;31m",  # bold red
    Severity.WARNING: "\033[33m",  # yellow
    Severity.STYLE: "\033[2;36m",  # dim cyan — auto-fix territory, low-noise
    Severity.INFO: "\033[36m",  # cyan
}
_RESET = "\033[0m"


def format_text(diagnostics: Iterable[Diagnostic], use_color: bool = True) -> str:
    """Human-readable: ` path:line:col: severity rule_id message`."""
    lines = []
    for d in diagnostics:
        sev = d.severity.short
        if use_color:
            color = _SEV_COLOR.get(d.severity, "")
            sev_text = f"{color}{sev}{_RESET}"
        else:
            sev_text = sev
        lines.append(f"{d.path}:{d.line}:{d.column}: [{sev_text}] {d.rule_id}: {d.message}")
    return "\n".join(lines)


def format_json(diagnostics: Iterable[Diagnostic]) -> str:
    """Single JSON array of all diagnostics, enriched with ``fixer_id``."""
    out = []
    for d in diagnostics:
        obj = d.to_json()
        obj["fixer_id"] = fixer_for(d.rule_id)
        out.append(obj)
    return json.dumps(out, indent=2)


def format_tap(diagnostics: Iterable[Diagnostic]) -> str:
    """TAP-13. Each diagnostic is a 'not ok' test."""
    diags = list(diagnostics)
    out = ["TAP version 13", f"1..{len(diags)}"]
    for i, d in enumerate(diags, start=1):
        out.append(f"not ok {i} - {d.path}:{d.line}:{d.column} {d.rule_id} - {d.message}")
        out.append("  ---")
        out.append(f"  rule_id: {d.rule_id}")
        out.append(f"  severity: {d.severity.value}")
        out.append(f"  path: {d.path}")
        out.append(f"  line: {d.line}")
        out.append(f"  column: {d.column}")
        if d.line_text:
            text = d.line_text.replace("'", "''")
            out.append(f"  line_text: '{text}'")
        out.append("  ...")
    return "\n".join(out)


def write_output(diagnostics: Iterable[Diagnostic], fmt: str = "text") -> None:
    """Print diagnostics to stdout in the requested format."""
    diags = list(diagnostics)
    if fmt == "text":
        if diags:
            print(format_text(diags, use_color=sys.stdout.isatty()))
    elif fmt == "json":
        print(format_json(diags))
    elif fmt == "tap":
        print(format_tap(diags))
    else:
        raise ValueError(f"unknown output format: {fmt!r}")
