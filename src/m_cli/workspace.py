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


@dataclass(frozen=True)
class ReferenceCallSite:
    """A call site that references some target (routine, label).

    ``target_label`` is None for references like ``^ROUTINE`` /
    ``$$^ROUTINE`` that target the routine entry without naming a
    label. ``column`` and ``end_column`` are 0-indexed character
    positions on the caller's line — convenient for LSP ``Range``.
    """

    target_routine: str  # uppercased
    target_label: str | None  # uppercased, None when only ^ROUTINE was written
    path: Path
    line: int  # 1-indexed
    column: int  # 0-indexed start of the reference text
    end_column: int  # 0-indexed end (exclusive)


class WorkspaceIndex:
    """In-memory index of routines, their labels, and inbound call sites.

    Three lookups, all case-insensitive on routine and label:

      - ``lookup(routine, label)`` — resolve a ``LABEL^ROUTINE`` reference
        to its declaration (powers go-to-definition).
      - ``references_to(routine, label)`` — every call site that targets
        ``LABEL^ROUTINE`` (powers find-references).
      - ``all_locations()`` — sorted list of every label (powers
        workspace symbol search).

    The index is intentionally minimal — name + path + line + column.
    Callers that need source ranges or richer node info should re-parse
    the resolved file.
    """

    def __init__(self) -> None:
        self._by_routine: dict[str, list[LabelLocation]] = {}
        self._by_path: dict[Path, list[LabelLocation]] = {}
        # Reference indices, one keyed by target, one keyed by source path
        # (so remove_file can wipe a file's contributions in O(refs-of-file)).
        self._refs_by_target: dict[tuple[str, str | None], list[ReferenceCallSite]] = {}
        self._refs_by_path: dict[Path, list[ReferenceCallSite]] = {}

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

    def references_to(self, routine: str, label: str | None) -> list[ReferenceCallSite]:
        """Every indexed call site whose target matches (routine, label).

        Matching is case-insensitive; ``label=None`` matches only the
        ``^ROUTINE``-style references (where the caller didn't name a
        specific label). To find every reference into a routine
        regardless of label, call ``references_to(routine, label=name)``
        for each label and union the results.
        """
        key = (routine.upper(), label.upper() if label else None)
        return list(self._refs_by_target.get(key, []))

    def refs_from(self, path: Path) -> list[ReferenceCallSite]:
        """Every outbound call site recorded for ``path``.

        Used by cross-routine lint rules (M-XINDX-007 et al.) to walk
        a file's references and verify each target exists. Returns
        an empty list if ``path`` isn't indexed."""
        return list(self._refs_by_path.get(path, []))

    def has_routine(self, routine: str) -> bool:
        """True iff at least one label is indexed for ``routine``
        (case-insensitive)."""
        return routine.upper() in self._by_routine

    def add_file(self, path: Path, src: bytes) -> None:
        """Index one ``.m`` file, replacing any prior entries for that path.

        Indexes both labels (declarations) and inbound references
        (call sites). Routine name comes from the file stem
        (upper-cased) — that matches ydb's resolution and avoids
        depending on the first-label-equals-routine-name convention,
        which not every codebase follows.
        """
        self.remove_file(path)
        labels = _extract_labels(src)
        if labels:
            routine = path.stem.upper()
            locs = [
                LabelLocation(routine=routine, label=name, path=path, line=line)
                for name, line in labels
            ]
            self._by_routine.setdefault(routine, []).extend(locs)
            self._by_path[path] = locs
        refs = _extract_references(src, path)
        if refs:
            self._refs_by_path[path] = refs
            for ref in refs:
                self._refs_by_target.setdefault(
                    (ref.target_routine, ref.target_label), []
                ).append(ref)

    def remove_file(self, path: Path) -> None:
        """Drop every label location and reference associated with ``path``."""
        prior_labels = self._by_path.pop(path, None)
        if prior_labels:
            for loc in prior_labels:
                label_entries = self._by_routine.get(loc.routine, [])
                label_entries[:] = [e for e in label_entries if e.path != path]
                if not label_entries:
                    self._by_routine.pop(loc.routine, None)
        prior_refs = self._refs_by_path.pop(path, None)
        if prior_refs:
            for ref in prior_refs:
                key = (ref.target_routine, ref.target_label)
                ref_entries = self._refs_by_target.get(key, [])
                ref_entries[:] = [r for r in ref_entries if r.path != path]
                if not ref_entries:
                    self._refs_by_target.pop(key, None)


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


# Match the call header at the start of a reference text:
#   LABEL^ROUTINE  → groups (LABEL, ROUTINE)
#   LABEL          → (LABEL, None)
#   ^ROUTINE       → (None, ROUTINE)
# Used after stripping ``$$`` from extrinsic_function nodes.
_CALL_HEADER_RE = re.compile(
    r"^(?P<label>[%A-Za-z][A-Za-z0-9]*)?(?:\^(?P<routine>[%A-Za-z][A-Za-z0-9]*))?"
)


def _extract_references(src: bytes, path: Path) -> list[ReferenceCallSite]:
    """Walk the AST and extract every cross-routine call site.

    Three forms:

      1. ``entry_reference`` — ``LABEL^ROUTINE`` / ``^ROUTINE`` / ``LABEL``
         appearing in DO/GOTO arguments. The parser emits this when
         it sees the ``^`` syntactic clue.
      2. ``extrinsic_function`` — ``$$LABEL^ROUTINE(args)`` /
         ``$$LABEL(args)``. Distinguished by the leading ``$$``.
      3. Bare-label DO/GOTO/JOB — ``D LABEL`` (no ``^``) inside
         these commands is a label call by M semantics. Tree-sitter-m
         parses the argument as ``local_variable``; we disambiguate
         by checking the command keyword. Skipped for X/XECUTE
         (those evaluate string expressions, not labels) and for
         arguments starting with ``@`` (indirection).
    """
    tree = parse(src)
    out: list[ReferenceCallSite] = []
    routine_stem = path.stem
    for node in _walk_nodes(tree.root_node):
        if node.type in ("entry_reference", "extrinsic_function"):
            ref = _ref_from_call_node(node, src, routine_stem, path)
            if ref is not None:
                out.append(ref)
        elif node.type == "command":
            out.extend(_refs_from_bare_label_command(node, src, routine_stem, path))
    return out


def _ref_from_call_node(
    node, src: bytes, routine_stem: str, path: Path
) -> "ReferenceCallSite | None":
    text = src[node.start_byte : node.end_byte].decode("latin-1", errors="replace")
    offset = 0
    if node.type == "extrinsic_function" and text.startswith("$$"):
        text = text[2:]
        offset = 2
    m = _CALL_HEADER_RE.match(text)
    if not m or (m.group("label") is None and m.group("routine") is None):
        return None
    label = m.group("label")
    routine = m.group("routine") or routine_stem
    start_row = node.start_point[0]
    start_col = node.start_point[1] + offset
    end_col = start_col + (m.end() - m.start())
    return ReferenceCallSite(
        target_routine=routine.upper(),
        target_label=label.upper() if label else None,
        path=path,
        line=start_row + 1,
        column=start_col,
        end_column=end_col,
    )


# Command keywords whose argument is a label name (per M semantics).
# X/XECUTE evaluates an expression string, not a label, so it's excluded.
_LABEL_CALL_KEYWORDS = frozenset({"D", "DO", "G", "GOTO", "J", "JOB"})


def _refs_from_bare_label_command(
    cmd_node, src: bytes, routine_stem: str, path: Path
) -> list[ReferenceCallSite]:
    """Index ``D LBL`` / ``G LBL`` / ``J LBL`` arguments as intra-routine
    references to (current_routine, LBL).

    Skips arguments that are already wrapped in ``entry_reference`` or
    ``extrinsic_function`` (those are handled by the caller). Skips
    indirect arguments (anything that doesn't bottom out in a clean
    ``local_variable → identifier``).
    """
    keyword_node = next(
        (c for c in cmd_node.children if c.type == "command_keyword"), None
    )
    if keyword_node is None:
        return []
    keyword = src[keyword_node.start_byte : keyword_node.end_byte].decode(
        "latin-1", errors="replace"
    )
    if keyword.upper() not in _LABEL_CALL_KEYWORDS:
        return []
    arg_list = next((c for c in cmd_node.children if c.type == "argument_list"), None)
    if arg_list is None:
        return []
    out: list[ReferenceCallSite] = []
    for arg in arg_list.children:
        if arg.type != "argument":
            continue
        # Find a local_variable child wrapped through one variable layer.
        # Skip arguments containing entry_reference / extrinsic_function /
        # indirection — those are handled elsewhere or aren't label calls.
        local = _find_simple_local_variable(arg)
        if local is None:
            continue
        ident = next(
            (c for c in local.children if c.type == "identifier"), None
        )
        if ident is None:
            continue
        label_name = src[ident.start_byte : ident.end_byte].decode(
            "latin-1", errors="replace"
        )
        out.append(
            ReferenceCallSite(
                target_routine=routine_stem.upper(),
                target_label=label_name.upper(),
                path=path,
                line=arg.start_point[0] + 1,
                column=arg.start_point[1],
                end_column=arg.start_point[1] + (arg.end_byte - arg.start_byte),
            )
        )
    return out


def _find_simple_local_variable(arg_node):
    """Return the ``local_variable`` if ``arg_node`` is exactly
    ``argument → variable → local_variable`` (with no other interesting
    siblings). Used to filter out indirection / globals / expressions
    where it'd be wrong to index a label reference."""
    children = [c for c in arg_node.children if c.is_named]
    if len(children) != 1 or children[0].type != "variable":
        return None
    var_children = [c for c in children[0].children if c.is_named]
    if len(var_children) != 1 or var_children[0].type != "local_variable":
        return None
    return var_children[0]


def _walk_nodes(node):
    """Pre-order walk over every descendant of ``node``."""
    yield node
    for child in node.children:
        yield from _walk_nodes(child)


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
