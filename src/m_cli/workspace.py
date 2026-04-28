"""Workspace-wide M symbol index.

Maps routine names to their label locations across every ``.m`` file
in a workspace, and resolves ``LABEL^ROUTINE`` / ``^ROUTINE`` /
``$$LABEL^ROUTINE`` references at cursor position. Used by the LSP
for go-to-definition (and, in follow-ups, find-references and
workspace symbol search) and — once cross-routine lint rules land —
by the linter for "call to undefined label" diagnostics.

The index is built once at LSP startup and updated incrementally on
``didChangeWatchedFiles``. Files that fail to parse (or fail to read)
are silently skipped — we never want a single broken routine to
poison the whole index.

M is case-insensitive for routine names and labels (per ANSI), so the
index keys on the upper-cased canonical form.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from m_cli.parser import parse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LabelLocation:
    """A single labelled entry point in the workspace."""

    routine: str  # upper-case canonical routine name
    label: str  # original-case label name
    path: Path
    line: int  # 1-indexed for human / LSP consumption


class WorkspaceIndex:
    """In-memory index of routines and their labels.

    Lookups are case-insensitive on the routine and label name. The
    index is intentionally minimal — name + path + line. Callers that
    need source ranges should re-parse the resolved file.
    """

    def __init__(self) -> None:
        self._by_routine: dict[str, list[LabelLocation]] = {}
        self._by_path: dict[Path, list[LabelLocation]] = {}

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_routine.values())

    def routines(self) -> list[str]:
        """Sorted list of every routine name in the index."""
        return sorted(self._by_routine.keys())

    def all_locations(self) -> list[LabelLocation]:
        """Every (routine, label, path, line) entry — sorted for stable output."""
        out = [loc for entries in self._by_routine.values() for loc in entries]
        out.sort(key=lambda loc: (loc.routine, loc.line, loc.label))
        return out

    def lookup(self, routine: str, label: str | None) -> LabelLocation | None:
        """Resolve ``LABEL^ROUTINE`` (or ``^ROUTINE`` when ``label`` is None).

        ``^ROUTINE`` resolves to the routine's first label (its entry
        point), matching M semantics. Returns None when the routine is
        unknown or the label doesn't exist within it.
        """
        entries = self._by_routine.get(routine.upper())
        if not entries:
            return None
        if label is None:
            return entries[0]  # routine entry — first label declared
        target = label.upper()
        for loc in entries:
            if loc.label.upper() == target:
                return loc
        return None

    def add_file(self, path: Path, src: bytes) -> None:
        """Index one ``.m`` file, replacing any prior entries for that path.

        The routine name comes from the file stem (upper-cased) — that
        matches ydb's resolution and avoids depending on the
        first-label-equals-routine-name convention, which not every
        codebase follows.
        """
        self.remove_file(path)
        labels = _extract_labels(src)
        if not labels:
            return
        routine = path.stem.upper()
        locs = [
            LabelLocation(routine=routine, label=name, path=path, line=line)
            for name, line in labels
        ]
        self._by_routine.setdefault(routine, []).extend(locs)
        self._by_path[path] = locs

    def remove_file(self, path: Path) -> None:
        """Drop every label location associated with ``path``."""
        prior = self._by_path.pop(path, None)
        if not prior:
            return
        for loc in prior:
            entries = self._by_routine.get(loc.routine, [])
            entries[:] = [e for e in entries if e.path != path]
            if not entries:
                self._by_routine.pop(loc.routine, None)


def build_index(roots: Iterable[Path]) -> WorkspaceIndex:
    """Walk every ``.m`` file under each root and index its labels.

    Roots may be files or directories. Files that can't be read or
    parsed are skipped silently — the index is best-effort.
    """
    index = WorkspaceIndex()
    seen: set[Path] = set()
    for root in roots:
        for path in _walk_m_files(root):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                src = path.read_bytes()
            except OSError as e:
                logger.debug("workspace index: skipping %s: %s", path, e)
                continue
            index.add_file(path, src)
    return index


def _walk_m_files(root: Path) -> Iterable[Path]:
    if root.is_file() and root.suffix == ".m":
        yield root
        return
    if root.is_dir():
        yield from sorted(root.rglob("*.m"))


def _extract_labels(src: bytes) -> list[tuple[str, int]]:
    """Return ``[(label_name, line_1indexed), ...]`` for each label in ``src``.

    Walks the tree-sitter AST and pulls every ``label`` child of a
    top-level ``line`` node. Identical helper to
    ``m_cli.lsp.structure.find_labels`` but trimmed — workspace
    indexing doesn't need formals or body ranges.
    """
    tree = parse(src)
    out: list[tuple[str, int]] = []
    for line_node in tree.root_node.children:
        if line_node.type != "line":
            continue
        for child in line_node.children:
            if child.type == "label":
                name = src[child.start_byte : child.end_byte].decode(
                    "latin-1", errors="replace"
                )
                out.append((name, child.start_point[0] + 1))
                break
    return out


# ---------------------------------------------------------------------------
# Reference resolution at cursor
# ---------------------------------------------------------------------------


# A reference is one of:
#   LABEL^ROUTINE       — labelled entry
#   ^ROUTINE            — routine entry
#   $$LABEL^ROUTINE     — extrinsic with explicit routine
#   $$LABEL             — extrinsic in current routine (label-only)
#   LABEL               — bare label (in-routine call from D / G / etc.)
# We accept the cursor anywhere over the label OR routine half.
_REF_PATTERN = re.compile(
    r"""
    (?:\$\$)?                       # optional extrinsic prefix
    (?P<label>[%A-Za-z][A-Za-z0-9]*)?  # optional label
    (?:\^(?P<routine>[%A-Za-z][A-Za-z0-9]*))?  # optional ^routine
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class Reference:
    """Parsed (label, routine) reference under the cursor.

    Either side may be None: ``^FOO`` has no label; ``BARE`` (a local
    label call) has no routine. Both being None means there's no
    resolvable reference at the cursor.
    """

    label: str | None
    routine: str | None


def reference_at(line: str, character: int) -> Reference | None:
    """Return the (label, routine) reference under the cursor, or None.

    Recognizes ``LABEL^ROUTINE``, ``^ROUTINE``, ``LABEL``,
    ``$$LABEL^ROUTINE``, ``$$LABEL``. Returns None when the cursor is
    on whitespace, on a non-identifier character with no adjacent
    word, or when the parsed reference has neither side.
    """
    if character < 0 or character > len(line):
        return None
    span = _expand_reference_span(line, character)
    if span is None:
        return None
    start, end = span
    text = line[start:end]
    m = _REF_PATTERN.fullmatch(text)
    if not m:
        return None
    label = m.group("label")
    routine = m.group("routine")
    if label is None and routine is None:
        return None
    return Reference(label=label, routine=routine)


def _expand_reference_span(line: str, character: int) -> tuple[int, int] | None:
    """Walk outward from ``character`` to capture an entire M reference.

    A reference may include letters, digits, ``%``, ``$``, and a
    single ``^``. We stop at any other char. The cursor may sit just
    after the reference end (LSP convention)."""

    def is_ref_char(c: str) -> bool:
        return c.isalnum() or c in ("$", "%", "^")

    # If cursor is sitting on a non-ref char, look one to the left.
    pos = character
    if pos == len(line) or not is_ref_char(line[pos]):
        if pos > 0 and is_ref_char(line[pos - 1]):
            pos -= 1
        else:
            return None
    start = pos
    while start > 0 and is_ref_char(line[start - 1]):
        start -= 1
    end = pos + 1
    while end < len(line) and is_ref_char(line[end]):
        end += 1
    if start == end:
        return None
    return start, end


__all__ = [
    "LabelLocation",
    "Reference",
    "WorkspaceIndex",
    "build_index",
    "reference_at",
]
