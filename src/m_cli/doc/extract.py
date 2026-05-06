"""Extract docstrings from an M routine source.

Pulls:

- The routine name (first label in the file; matches the file stem
  by VistA / m-cli convention).
- The routine summary (text after ``;`` on the first label's line,
  stripped of a leading ``@summary`` annotation).
- The version stub if present on line 2 (``;;<v>;<pkg>;;<date>;<build>``).
- Per-label entries: name, formals string, summary (same convention).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from m_cli.lsp.structure import find_labels

_VERSION_RE = re.compile(r"^\s*;;([^;]*);([^;]*);")
_SUMMARY_PREFIX = re.compile(r"^\s*@summary\s+", re.IGNORECASE)


@dataclass(frozen=True)
class LabelDoc:
    name: str
    formals: str  # "(a,b)" or ""
    summary: str  # one-line description from `; @summary ...`


@dataclass(frozen=True)
class RoutineDoc:
    path: Path
    name: str
    summary: str
    version: str
    package: str
    labels: tuple[LabelDoc, ...] | list[LabelDoc]


def extract_routine_doc(path: Path, src: bytes) -> RoutineDoc:
    text = src.decode("latin-1", errors="replace")
    lines = text.splitlines()

    # Routine name: the file stem, uppercased (matches the M convention).
    routine_name = path.stem.upper() if path.stem else ""

    # Routine summary: first comment on line 1 of the routine.
    routine_summary = _extract_inline_comment(lines[0]) if lines else ""

    # Version stub: line 2 if matches ``;;<v>;<pkg>;;...;...``.
    version, package = "", ""
    if len(lines) >= 2:
        m = _VERSION_RE.match(lines[1])
        if m:
            version = m.group(1).strip()
            package = m.group(2).strip()

    # Per-label entries from tree-sitter.
    label_ranges = find_labels(src)
    labels: list[LabelDoc] = []
    for lbl in label_ranges:
        # Skip the routine entry label itself — we already report it
        # at the routine level.
        if lbl.name == routine_name and lbl.start_line == 0:
            continue
        line_text = lines[lbl.start_line] if 0 <= lbl.start_line < len(lines) else ""
        summary = _extract_inline_comment(line_text)
        labels.append(LabelDoc(name=lbl.name, formals=lbl.formals, summary=summary))

    return RoutineDoc(
        path=path,
        name=routine_name,
        summary=routine_summary,
        version=version,
        package=package,
        labels=labels,
    )


def _extract_inline_comment(line: str) -> str:
    """Return the trimmed comment text after the first ``;`` on a line.

    Strips a leading ``@summary`` annotation if present, and rejects
    lines whose comment starts with ``;;`` (those are version stubs or
    structured directives, not human prose).
    """
    idx = line.find(";")
    if idx < 0:
        return ""
    comment = line[idx + 1 :]
    if comment.startswith(";"):
        return ""  # double-semicolon: version stub or directive
    comment = comment.strip()
    return _SUMMARY_PREFIX.sub("", comment)
