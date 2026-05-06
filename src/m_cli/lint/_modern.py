"""Modernization-track rules (M-MOD-NN).

Greenfield rules derived from contemporary M idioms — independent of the
legacy XINDEX baseline, though most M-MOD-NN rules supersede an XINDEX
rule via the ``replaces=`` metadata. They ship under the ``modern``
profile and consume configurable thresholds via :class:`LintContext`.

Currently shipped:

  Phase 2 (M2, length / size metrics):
    - M-MOD-001 — line longer than configured limit (replaces M-XINDX-019)
    - M-MOD-002 — code line longer than configured limit (replaces M-XINDX-058)
    - M-MOD-003 — routine longer than configured LOC limit (replaces M-XINDX-035)
    - M-MOD-004 — label body longer than configured LOC limit (new)

  Phase 3 (M2, structural / complexity metrics):
    - M-MOD-005 — cyclomatic complexity per label > N
    - M-MOD-006 — cognitive complexity per label > N
    - M-MOD-007 — dot-block nesting depth > N
    - M-MOD-008 — argument count > N
    - M-MOD-009 — commands per line > N

Each rule reads its threshold from ``ctx.thresholds[KEY]`` where ``KEY``
is one of the names declared in :mod:`m_cli.lint.thresholds`. The
defaults are merged in at context-build time, so rules don't need to
guard against missing keys.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from m_cli.lint._index import NodeIndex
from m_cli.lint._keywords import engine_allowlist
from m_cli.lint.context import LintContext
from m_cli.lint.diagnostic import Category, Diagnostic, Severity
from m_cli.lint.rules import (
    Rule,
    _arg_has_timeout,
    _arguments,
    _commands,
    _node_line_col,
    _payload,
    register,
)

# tree-sitter Node has no clean importable stub; the rules pass it
# around as opaque ``Any``. This matches how the legacy XINDEX rules
# in rules.py treat it.
_Node = Any


def _node_text(node, src: bytes) -> str:
    """Decoded text of a node (latin-1 fallback for non-UTF-8 bytes)."""
    return src[node.start_byte : node.end_byte].decode("latin-1", errors="replace")


def _decode_line(b: bytes) -> str:
    """Decode a source line for display (M source is mostly ASCII; use
    latin-1 fallback for any non-UTF-8 bytes)."""
    return b.decode("latin-1", errors="replace")


def _label_body_extents(
    src: bytes, index: NodeIndex
) -> list[tuple[_Node, int, int]]:
    """Return ``[(label_node, header_line_0idx, end_line_0idx_exclusive), ...]``.

    ``end_line_0idx`` is the line of the next top-level label, or the
    total line count for the final label. Labels nested inside other
    nodes (e.g. inside an extrinsic-function reference) are excluded —
    only top-level labels (whose parent is a ``line`` node) are
    considered, since those are the only callable units.
    """
    label_nodes = [
        n
        for n in index.of("label")
        if n.parent is not None and n.parent.type == "line"
    ]
    if not label_nodes:
        return []
    total_lines = src.count(b"\n") + (0 if src.endswith(b"\n") else 1)
    out: list[tuple[_Node, int, int]] = []
    for i, label in enumerate(label_nodes):
        header_line = label.start_point[0]
        if i + 1 < len(label_nodes):
            next_header = label_nodes[i + 1].start_point[0]
        else:
            next_header = total_lines
        out.append((label, header_line, next_header))
    return out


def _label_for_line(
    line: int, label_extents: list[tuple[_Node, int, int]]
) -> tuple[_Node, int] | None:
    """Map a 0-based line number to ``(label_node, header_line_0idx)``,
    or None if the line is outside any label body (e.g. before the
    first label header)."""
    for label, header, end in label_extents:
        if header <= line < end:
            return (label, header)
    return None


def _label_name(src: bytes, label_node) -> str:
    return src[label_node.start_byte : label_node.end_byte].decode(
        "latin-1", errors="replace"
    )


def _dot_depth(prefix_text: str) -> int:
    """Count `.` continuation markers in a ``dot_block_prefix`` text.

    Examples: ``'. '`` → 1, ``'. . '`` → 2, ``'. . . '`` → 3.
    """
    return prefix_text.count(".")


# ---------------------------------------------------------------------------
# M-MOD-001 — Line length
# ---------------------------------------------------------------------------


def _check_line_length(
    src: bytes, _tree, path: Path, _index: NodeIndex, ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-001 — Line longer than the configured ``line_length`` limit.

    Modernizes M-XINDX-019, which hard-coded a 245-byte ceiling tied to
    early-90s terminal widths. The default 200 is a readability ceiling
    that matches contemporary editor / display conventions.
    """
    limit = ctx.thresholds["line_length"]
    for i, raw in enumerate(src.splitlines(), start=1):
        if len(raw) > limit:
            yield Diagnostic(
                rule_id="M-MOD-001",
                severity=Severity.STYLE,
                message=f"Line is {len(raw)} bytes (limit: {limit})",
                path=path,
                line=i,
                column=limit + 1,
                column_end=len(raw) + 1,
                line_text=_decode_line(raw),
            )


register(
    Rule(
        id="M-MOD-001",
        severity=Severity.STYLE,
        category=Category.STYLE,
        title="Line longer than configured limit",
        tags=("modern",),
        check=_check_line_length,
        needs_context=True,
        replaces=("M-XINDX-019",),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-002 — Code-line length (excludes comment-only lines)
# ---------------------------------------------------------------------------


def _check_code_line_length(
    src: bytes, _tree, path: Path, _index: NodeIndex, ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-002 — *Code* line longer than the configured limit.

    Skips comment-only lines (whose first non-whitespace byte is ``;``).
    Modernizes M-XINDX-058, which hard-coded a 15,000-byte ceiling
    rooted in a long-vanished compiled-token-table size. The default
    1000 is "pathological-line" territory — no normal code line gets
    this long.
    """
    limit = ctx.thresholds["code_line_length"]
    for i, raw in enumerate(src.splitlines(), start=1):
        # Comment-only lines (first non-whitespace char is `;`) are
        # exempt. Pure-blank lines are exempt by definition (length 0).
        stripped = raw.lstrip(b" \t")
        if not stripped or stripped.startswith(b";"):
            continue
        if len(raw) > limit:
            yield Diagnostic(
                rule_id="M-MOD-002",
                severity=Severity.STYLE,
                message=f"Code line is {len(raw)} bytes (limit: {limit})",
                path=path,
                line=i,
                column=limit + 1,
                column_end=len(raw) + 1,
                line_text=_decode_line(raw),
            )


register(
    Rule(
        id="M-MOD-002",
        severity=Severity.STYLE,
        category=Category.COMPLEXITY,
        title="Code line longer than configured limit",
        tags=("modern",),
        check=_check_code_line_length,
        needs_context=True,
        replaces=("M-XINDX-058",),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-003 — Routine length (LOC)
# ---------------------------------------------------------------------------


def _check_routine_lines(
    src: bytes, _tree, path: Path, _index: NodeIndex, ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-003 — Routine longer than the configured LOC limit.

    Modernizes M-XINDX-035, which measured *bytes* against a 20,000-byte
    MUMPS-77 routine cap that has not applied for two engine
    generations (YottaDB has effectively no routine size limit, IRIS
    allows orders of magnitude more). Lines-of-code is a more useful
    maintainability proxy than raw bytes.

    Counted lines include comment-only and blank lines — they still
    contribute to the "how big is this routine" gestalt. If users
    want comment-or-blank-excluding metrics, that's a separate rule.
    """
    limit = ctx.thresholds["routine_lines"]
    if not src:
        return
    line_count = src.count(b"\n")
    # If the file doesn't end with a newline, the last line still counts.
    if not src.endswith(b"\n"):
        line_count += 1
    if line_count > limit:
        yield Diagnostic(
            rule_id="M-MOD-003",
            severity=Severity.STYLE,
            message=f"Routine has {line_count} lines (limit: {limit})",
            path=path,
            line=1,
            column=1,
        )


register(
    Rule(
        id="M-MOD-003",
        severity=Severity.STYLE,
        category=Category.COMPLEXITY,
        title="Routine longer than configured LOC limit",
        tags=("modern",),
        check=_check_routine_lines,
        needs_context=True,
        replaces=("M-XINDX-035",),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-004 — Label body length (LOC)
# ---------------------------------------------------------------------------


def _check_label_lines(
    src: bytes, _tree, path: Path, index: NodeIndex, ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-004 — Label body longer than the configured LOC limit.

    A label's body runs from the line *after* the label's header through
    the line *before* the next top-level label (or to EOF for the final
    label). Encourages decomposition of mega-labels — there is no
    legacy XINDEX equivalent.
    """
    limit = ctx.thresholds["label_lines"]
    for label, header_line, next_header in _label_body_extents(src, index):
        # Body lines = next_header - header_line - 1 (header itself
        # doesn't count toward body LOC).
        body_lines = max(0, next_header - header_line - 1)
        if body_lines > limit:
            name = _label_name(src, label)
            yield Diagnostic(
                rule_id="M-MOD-004",
                severity=Severity.STYLE,
                message=(
                    f"Label '{name}' body has {body_lines} lines "
                    f"(limit: {limit})"
                ),
                path=path,
                line=header_line + 1,
                column=label.start_point[1] + 1,
                column_end=label.start_point[1] + 1 + len(name),
            )


register(
    Rule(
        id="M-MOD-004",
        severity=Severity.STYLE,
        category=Category.COMPLEXITY,
        title="Label body longer than configured LOC limit",
        tags=("modern",),
        check=_check_label_lines,
        needs_context=True,
        replaces=(),  # new rule — no legacy equivalent
    )
)


# ---------------------------------------------------------------------------
# Helpers shared by the complexity rules
# ---------------------------------------------------------------------------


# Command keywords that introduce a decision point for cyclomatic /
# cognitive complexity. The keyword text comparison is case-insensitive
# and accepts the abbreviated forms (M is case-insensitive for commands;
# both "I" and "IF" are valid). $SELECT arms and ``&&``/``||`` short-
# circuits inside expression text are NOT counted today — they would
# require parsing inside ``argument_list`` which tree-sitter-m does not
# yet do at this granularity. Document this as a known under-count;
# real-world cyclomatic for M-MOD-005 will read low for $SELECT-heavy
# code, which is a deliberate trade-off vs. false-positive risk.
_DECISION_KEYWORDS_UPPER = frozenset({"IF", "I", "FOR", "F", "ELSE", "E"})


def _is_decision_command_keyword(src: bytes, node) -> bool:
    """True if the given ``command_keyword`` node names a decision."""
    text = src[node.start_byte : node.end_byte].decode("latin-1", errors="replace")
    return text.upper() in _DECISION_KEYWORDS_UPPER


# ---------------------------------------------------------------------------
# M-MOD-005 — Cyclomatic complexity per label
# ---------------------------------------------------------------------------


def _check_cyclomatic(
    src: bytes, _tree, path: Path, index: NodeIndex, ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-005 — Cyclomatic complexity per label > N.

    Standard McCabe formula: ``decisions + 1``. We count:

      - ``IF`` / ``I`` command keywords
      - ``ELSE`` / ``E`` command keywords (a separate flow path from
        the matching IF, contra some McCabe conventions which count
        the IF/ELSE pair as one — we count both for stricter
        accounting)
      - ``FOR`` / ``F`` command keywords
      - every ``postconditional`` node (``S:cond``, ``Q:cond``, etc.)

    Known under-counts (deliberate, see helpers above): ``$SELECT``
    arms and short-circuit ``&&`` / ``||`` operators inside
    ``argument_list`` text are not parsed structurally and are not
    counted today.
    """
    extents = _label_body_extents(src, index)
    if not extents:
        return
    limit = ctx.thresholds["cyclomatic"]

    # Tally per label-header. Decision points are pre-bucketed to avoid
    # repeated O(decisions × labels) lookups on large files.
    counts: dict[int, int] = {header: 0 for _label, header, _end in extents}

    for kw in index.of("command_keyword"):
        if not _is_decision_command_keyword(src, kw):
            continue
        line = kw.start_point[0]
        bucket = _label_for_line(line, extents)
        if bucket is None:
            continue
        counts[bucket[1]] += 1

    for pc in index.of("postconditional"):
        line = pc.start_point[0]
        bucket = _label_for_line(line, extents)
        if bucket is None:
            continue
        counts[bucket[1]] += 1

    for label, header, _end in extents:
        cyclomatic = counts[header] + 1  # McCabe + 1
        if cyclomatic > limit:
            name = _label_name(src, label)
            yield Diagnostic(
                rule_id="M-MOD-005",
                severity=Severity.WARNING,
                message=(
                    f"Label '{name}' has cyclomatic complexity {cyclomatic} "
                    f"(limit: {limit})"
                ),
                path=path,
                line=header + 1,
                column=label.start_point[1] + 1,
                column_end=label.start_point[1] + 1 + len(name),
            )


register(
    Rule(
        id="M-MOD-005",
        severity=Severity.WARNING,
        category=Category.COMPLEXITY,
        title="Cyclomatic complexity per label exceeds configured limit",
        tags=("modern",),
        check=_check_cyclomatic,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-006 — Cognitive complexity per label
# ---------------------------------------------------------------------------


def _check_cognitive(
    src: bytes, _tree, path: Path, index: NodeIndex, ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-006 — Cognitive complexity per label > N.

    Sonar-style approximation: each decision point contributes 1 PLUS
    the dot-block depth of the line it sits on. So a decision at top
    level adds 1; a decision inside a depth-2 dot block adds 3
    (``1 + 2``). This penalises nesting more aggressively than raw
    McCabe — capturing "how hard is this to follow" rather than just
    "how many branches".

    Limitations (Phase 3 V1):

      - Same under-counts as M-MOD-005 (no ``$SELECT`` arms, no
        ``&&``/``||`` short-circuits parsed today).
      - Nesting depth uses dot-block prefix only; nesting inside
        compound expressions (e.g. ``$SELECT`` inside ``$SELECT``)
        is not penalised. Phase 7's data-flow / CFG work can graduate
        this to a stricter model if needed.
    """
    extents = _label_body_extents(src, index)
    if not extents:
        return
    limit = ctx.thresholds["cognitive"]

    # Pre-bucket dot_block_prefix nodes by line for O(1) depth lookup.
    depth_for_line: dict[int, int] = {}
    for prefix in index.of("dot_block_prefix"):
        line = prefix.start_point[0]
        text = src[prefix.start_byte : prefix.end_byte].decode("latin-1", errors="replace")
        depth_for_line[line] = max(depth_for_line.get(line, 0), _dot_depth(text))

    counts: dict[int, int] = {header: 0 for _label, header, _end in extents}

    def add_decision(line: int) -> None:
        bucket = _label_for_line(line, extents)
        if bucket is None:
            return
        depth = depth_for_line.get(line, 0)
        counts[bucket[1]] += 1 + depth

    for kw in index.of("command_keyword"):
        if _is_decision_command_keyword(src, kw):
            add_decision(kw.start_point[0])

    for pc in index.of("postconditional"):
        add_decision(pc.start_point[0])

    for label, header, _end in extents:
        if counts[header] > limit:
            name = _label_name(src, label)
            yield Diagnostic(
                rule_id="M-MOD-006",
                severity=Severity.WARNING,
                message=(
                    f"Label '{name}' has cognitive complexity {counts[header]} "
                    f"(limit: {limit})"
                ),
                path=path,
                line=header + 1,
                column=label.start_point[1] + 1,
                column_end=label.start_point[1] + 1 + len(name),
            )


register(
    Rule(
        id="M-MOD-006",
        severity=Severity.WARNING,
        category=Category.COMPLEXITY,
        title="Cognitive complexity per label exceeds configured limit",
        tags=("modern",),
        check=_check_cognitive,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-007 — Dot-block nesting depth
# ---------------------------------------------------------------------------


def _check_dot_block_depth(
    src: bytes, _tree, path: Path, index: NodeIndex, ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-007 — Dot-block nesting depth > N anywhere in the file.

    A dot-block prefix on a line — ``. `` (depth 1), ``. . `` (depth 2),
    etc. — counts the runtime nesting level of that line under DO
    blocks. We flag the deepest occurrence per excessive line so each
    over-deep block surfaces exactly once.
    """
    limit = ctx.thresholds["dot_block_depth"]
    for prefix in index.of("dot_block_prefix"):
        text = src[prefix.start_byte : prefix.end_byte].decode("latin-1", errors="replace")
        depth = _dot_depth(text)
        if depth > limit:
            yield Diagnostic(
                rule_id="M-MOD-007",
                severity=Severity.WARNING,
                message=f"Dot-block nesting depth {depth} (limit: {limit})",
                path=path,
                line=prefix.start_point[0] + 1,
                column=prefix.start_point[1] + 1,
                column_end=prefix.end_point[1] + 1,
            )


register(
    Rule(
        id="M-MOD-007",
        severity=Severity.WARNING,
        category=Category.COMPLEXITY,
        title="Dot-block nesting depth exceeds configured limit",
        tags=("modern",),
        check=_check_dot_block_depth,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-008 — Argument count per label
# ---------------------------------------------------------------------------


def _check_argument_count(
    src: bytes, _tree, path: Path, index: NodeIndex, ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-008 — Number of formal arguments to a label > N.

    Inspects the ``formals`` node (the parenthesised parameter list
    after the label name) and counts ``identifier`` children. M is
    untyped and positional, so call sites with seven-plus arguments
    are read-killers — encourage refactoring to a struct / array
    parameter.
    """
    limit = ctx.thresholds["argument_count"]
    for formals in index.of("formals"):
        # ``formals`` is a child of a ``line`` (a label header). Each
        # identifier child is one positional parameter; commas and the
        # parentheses themselves are siblings but not identifiers.
        n_args = sum(1 for c in formals.children if c.type == "identifier")
        if n_args > limit:
            # Find the sibling label node so the diagnostic anchors on
            # the label name (the formals' parent is a `line`, not the
            # label itself).
            parent = formals.parent
            label_node = None
            if parent is not None:
                label_node = next(
                    (c for c in parent.children if c.type == "label"), None
                )
            line = formals.start_point[0]
            col = formals.start_point[1]
            message = f"Label has {n_args} formal arguments (limit: {limit})"
            if label_node is not None:
                name = _label_name(src, label_node)
                line = label_node.start_point[0]
                col = label_node.start_point[1]
                message = (
                    f"Label '{name}' has {n_args} formal arguments "
                    f"(limit: {limit})"
                )
            yield Diagnostic(
                rule_id="M-MOD-008",
                severity=Severity.WARNING,
                message=message,
                path=path,
                line=line + 1,
                column=col + 1,
            )


register(
    Rule(
        id="M-MOD-008",
        severity=Severity.WARNING,
        category=Category.COMPLEXITY,
        title="Argument count exceeds configured limit",
        tags=("modern",),
        check=_check_argument_count,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-009 — Multiple commands per line
# ---------------------------------------------------------------------------


def _check_commands_per_line(
    src: bytes, _tree, path: Path, index: NodeIndex, ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-009 — More than N commands on a single line.

    Counts ``command`` children of each ``command_sequence`` node.
    Lines with no commands (blank or comment-only) are not counted
    — they have no command_sequence at all. The diagnostic anchors
    on the line's first command for navigability.
    """
    limit = ctx.thresholds["commands_per_line"]
    for seq in index.of("command_sequence"):
        commands = [c for c in seq.children if c.type == "command"]
        n = len(commands)
        if n > limit:
            first = commands[0]
            yield Diagnostic(
                rule_id="M-MOD-009",
                severity=Severity.STYLE,
                message=f"Line has {n} commands (limit: {limit})",
                path=path,
                line=seq.start_point[0] + 1,
                column=first.start_point[1] + 1,
                column_end=seq.end_point[1] + 1,
            )


register(
    Rule(
        id="M-MOD-009",
        severity=Severity.STYLE,
        category=Category.STYLE,
        title="Too many commands on a single line",
        # `pedantic` excludes this rule from the `default` profile
        # because real-world M heavily uses dense one-liners; opt in
        # via `--rules=modern` for the strict view.
        tags=("modern", "pedantic"),
        check=_check_commands_per_line,
        needs_context=True,
        replaces=(),
    )
)


# ===========================================================================
# Phase 4 — Tier 1 concurrency / transaction rules (single-file cut)
# ===========================================================================
#
# These rules catch the obvious intra-label cases of resource leaks
# (LOCK / TSTART / $ETRAP / OPEN). The path-sensitive versions
# (covering early QUIT exits, conditional release on every branch,
# etc.) wait for Phase 7's data-flow analyzer. Documented as a
# deliberate trade-off in the implementation plan.


# Keyword sets for command-keyword matching. M is case-insensitive
# for commands; abbreviations are a unique prefix. We accept the
# common short forms users actually write.
_LOCK_KEYWORDS = frozenset({"L", "LOCK"})
_TSTART_KEYWORDS = frozenset({"TS", "TSTART"})
_TCOMMIT_KEYWORDS = frozenset({"TC", "TCOMMIT"})
_TROLLBACK_KEYWORDS = frozenset({"TRO", "TROLLBACK"})
_OPEN_KEYWORDS = frozenset({"O", "OPEN"})
_CLOSE_KEYWORDS = frozenset({"C", "CLOSE"})
_NEW_KEYWORDS = frozenset({"N", "NEW"})
_SET_KEYWORDS = frozenset({"S", "SET"})


def _arg_lock_polarity(arg) -> str:
    """Classify a LOCK argument's polarity.

    Returns ``"+"`` for incremental acquire (``+^X``), ``"-"`` for
    incremental release (``-^X``), or ``"plain"`` for the replace form
    (``^X`` with no leading sign).
    """
    payload = _payload(arg)
    if payload is None:
        return "plain"
    if payload.type == "unary_expression":
        for c in payload.children:
            if c.type == "operator":
                t = c.text.decode("latin-1", errors="replace") if hasattr(c, "text") else ""
                if t == "+":
                    return "+"
                if t == "-":
                    return "-"
    return "plain"


# ---------------------------------------------------------------------------
# M-MOD-010 — LOCK without timeout (modern, ERROR severity)
# ---------------------------------------------------------------------------


def _check_lock_no_timeout_modern(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-010 — LOCK acquire without ``:timeout``.

    Modernizes M-XINDX-060: same detection but at ERROR severity (a
    LOCK without timeout is a deadlock waiting to happen — high-impact
    bug, not just a smell). Skips ``LOCK -^X`` release form (which
    legitimately doesn't need a timeout) and argumentless ``LOCK``
    (releases all; no timeout meaningful).
    """
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in _LOCK_KEYWORDS:
            continue
        for arg in _arguments(cmd):
            if _arg_lock_polarity(arg) == "-":
                # Release form — no timeout needed.
                continue
            if _arg_has_timeout(arg):
                continue
            line, col = _node_line_col(kw_node, src)
            yield Diagnostic(
                rule_id="M-MOD-010",
                severity=Severity.ERROR,
                message=(
                    "LOCK acquire without :timeout — will block indefinitely "
                    "(suggest `:5` or longer)"
                ),
                path=path,
                line=line,
                column=col,
                column_end=col + len(kw),
            )
            break  # one diagnostic per command


register(
    Rule(
        id="M-MOD-010",
        severity=Severity.ERROR,
        category=Category.CONCURRENCY,
        title="LOCK acquire without timeout (deadlock risk)",
        tags=("modern",),
        check=_check_lock_no_timeout_modern,
        needs_context=True,
        replaces=("M-XINDX-060",),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-011 — LOCK acquire/release imbalance per label
# ---------------------------------------------------------------------------


def _check_lock_leak(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-011 — Incremental LOCKs not balanced by releases in the same label.

    Walks each label's LOCK commands in source order, simulating the
    held-lock count: ``LOCK +X`` increments, ``LOCK -X`` decrements,
    argumentless ``LOCK`` resets to zero (M's "release all" semantic).
    If the count is non-zero at the end of the label, flag the first
    surviving acquire.

    Plain ``LOCK X`` (replace form) is intentionally ignored — it has
    dual semantics (release-all + acquire-X) and would introduce noise
    at this analysis depth. Modern style uses only the incremental
    forms anyway.

    Limitations (documented):

      - Intra-label only. Acquires released in a callee or by routine
        exit are flagged here; Phase 7's data-flow analyzer graduates
        to path-sensitive accounting.
    """
    extents = _label_body_extents(src, index)
    if not extents:
        return

    # Per-label running state, walked in source order.
    held: dict[int, list[_Node]] = {h: [] for _l, h, _e in extents}
    n_acquires: dict[int, int] = {h: 0 for _l, h, _e in extents}
    n_releases: dict[int, int] = {h: 0 for _l, h, _e in extents}

    for cmd, kw, kw_node in _commands(index, src):
        if kw not in _LOCK_KEYWORDS:
            continue
        bucket = _label_for_line(kw_node.start_point[0], extents)
        if bucket is None:
            continue
        header = bucket[1]
        args = list(_arguments(cmd))
        if not args:
            # Argumentless LOCK releases everything; the running held
            # set resets. Counts the operation as one release for the
            # diagnostic message.
            n_releases[header] += len(held[header])
            held[header].clear()
            continue
        for arg in args:
            polarity = _arg_lock_polarity(arg)
            if polarity == "+":
                held[header].append(kw_node)
                n_acquires[header] += 1
            elif polarity == "-":
                if held[header]:
                    held[header].pop()
                n_releases[header] += 1
            # plain form (no ±): not counted

    for label, header, _end in extents:
        if not held[header]:
            continue
        # Flag the FIRST surviving acquire.
        kw_node = held[header][0]
        line, col = _node_line_col(kw_node, src)
        name = _label_name(src, label)
        yield Diagnostic(
            rule_id="M-MOD-011",
            severity=Severity.ERROR,
            message=(
                f"LOCK leak in label '{name}': {n_acquires[header]} "
                f"incremental acquire(s), {n_releases[header]} release(s)"
            ),
            path=path,
            line=line,
            column=col,
        )


register(
    Rule(
        id="M-MOD-011",
        severity=Severity.ERROR,
        category=Category.CONCURRENCY,
        title="LOCK acquire without matching release in same label",
        tags=("modern",),
        check=_check_lock_leak,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-012 — TSTART without matching TCOMMIT/TROLLBACK per label
# ---------------------------------------------------------------------------


def _check_transaction_leak(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-012 — TSTART unbalanced by TCOMMIT/TROLLBACK in same label.

    Counts ``TSTART`` (or ``TS``) versus ``TCOMMIT`` (``TC``) +
    ``TROLLBACK`` (``TRO``) in each label body. If TSTARTs outnumber
    closers, flag the first unmatched TSTART.

    Same intra-label limitation as M-MOD-011. A nested helper label
    that legitimately closes the transaction will appear as a leak
    here until Phase 7's path-sensitive analysis lands.
    """
    extents = _label_body_extents(src, index)
    if not extents:
        return

    starts: dict[int, list[_Node]] = {h: [] for _l, h, _e in extents}
    closes: dict[int, int] = {h: 0 for _l, h, _e in extents}

    for _cmd, kw, kw_node in _commands(index, src):
        bucket = _label_for_line(kw_node.start_point[0], extents)
        if bucket is None:
            continue
        header = bucket[1]
        if kw in _TSTART_KEYWORDS:
            starts[header].append(kw_node)
        elif kw in _TCOMMIT_KEYWORDS or kw in _TROLLBACK_KEYWORDS:
            closes[header] += 1

    for label, header, _end in extents:
        n_start = len(starts[header])
        n_close = closes[header]
        if n_start > n_close:
            kw_node = starts[header][n_close]
            line, col = _node_line_col(kw_node, src)
            name = _label_name(src, label)
            yield Diagnostic(
                rule_id="M-MOD-012",
                severity=Severity.ERROR,
                message=(
                    f"Transaction leak in label '{name}': {n_start} TSTART(s), "
                    f"{n_close} TCOMMIT/TROLLBACK"
                ),
                path=path,
                line=line,
                column=col,
            )


register(
    Rule(
        id="M-MOD-012",
        severity=Severity.ERROR,
        category=Category.CONCURRENCY,
        title="TSTART without matching TCOMMIT/TROLLBACK in same label",
        tags=("modern",),
        check=_check_transaction_leak,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-013 — SET $ETRAP without NEW $ETRAP in same label
# ---------------------------------------------------------------------------


def _arg_assigns_etrap(arg, src: bytes) -> bool:
    """True when ``arg`` is a ``$ETRAP=...`` SET assignment.

    Walks the argument's first child for a ``binary_expression`` whose
    LHS is a ``special_variable`` named ``$ETRAP`` (case-insensitive,
    accepts ``$ET`` abbreviation per M conventions).
    """
    payload = _payload(arg)
    if payload is None or payload.type != "binary_expression":
        return False
    # The LHS is the first non-trivial child of the binary_expression.
    lhs = next(
        (c for c in payload.children if c.type not in ("=", "(", ")")),
        None,
    )
    if lhs is None or lhs.type != "special_variable":
        return False
    name = _node_text(lhs, src).upper()
    return name in ("$ETRAP", "$ET")


def _new_includes_etrap(arg, src: bytes) -> bool:
    """True when ``arg`` is the ``$ETRAP`` operand of a NEW command."""
    payload = _payload(arg)
    if payload is None or payload.type != "special_variable":
        return False
    return _node_text(payload, src).upper() in ("$ETRAP", "$ET")


def _check_etrap_leak(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-013 — SET $ETRAP=... without a same-label NEW $ETRAP.

    A ``SET $ETRAP=...`` persists past the label exit unless the
    label has previously stack-saved the ISV via ``NEW $ETRAP``.
    Without that NEW, the trap leaks to the caller — a notorious
    debugging headache.

    Detection: per label, track whether ``NEW $ETRAP`` appears
    anywhere in the body. If a ``SET $ETRAP=...`` exists in the
    same label without a matching NEW, flag the SET.
    """
    extents = _label_body_extents(src, index)
    if not extents:
        return

    has_new: dict[int, bool] = {h: False for _l, h, _e in extents}
    sets: dict[int, list[_Node]] = {h: [] for _l, h, _e in extents}

    for cmd, kw, kw_node in _commands(index, src):
        bucket = _label_for_line(kw_node.start_point[0], extents)
        if bucket is None:
            continue
        header = bucket[1]
        if kw in _NEW_KEYWORDS:
            for arg in _arguments(cmd):
                if _new_includes_etrap(arg, src):
                    has_new[header] = True
                    break
        elif kw in _SET_KEYWORDS:
            for arg in _arguments(cmd):
                if _arg_assigns_etrap(arg, src):
                    sets[header].append(kw_node)

    for _label, header, _end in extents:
        if has_new[header]:
            continue
        for kw_node in sets[header]:
            line, col = _node_line_col(kw_node, src)
            yield Diagnostic(
                rule_id="M-MOD-013",
                severity=Severity.ERROR,
                message=(
                    "SET $ETRAP without preceding NEW $ETRAP — error "
                    "trap will leak past the label exit"
                ),
                path=path,
                line=line,
                column=col,
            )


register(
    Rule(
        id="M-MOD-013",
        severity=Severity.ERROR,
        category=Category.BUG,
        title="$ETRAP set without NEW in same label (handler leak)",
        tags=("modern",),
        check=_check_etrap_leak,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-014 — OPEN without matching CLOSE in same label
# ---------------------------------------------------------------------------


def _check_open_close(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-014 — More OPEN commands than CLOSEs in the same label.

    Counts ``OPEN`` (or ``O``) commands with arguments versus
    ``CLOSE`` (or ``C``) commands (including argumentless CLOSE,
    which closes every device the process owns). If OPENs outnumber
    CLOSEs in a label and no argumentless CLOSE was issued, flag
    the first unmatched OPEN.

    Severity is WARNING (not ERROR) because the engine releases file
    handles on routine exit / process termination; the leak is a
    style and resource-discipline concern more than a hard bug.
    Same intra-label limitation as M-MOD-011 / 012.
    """
    extents = _label_body_extents(src, index)
    if not extents:
        return

    opens: dict[int, list[_Node]] = {h: [] for _l, h, _e in extents}
    closes: dict[int, int] = {h: 0 for _l, h, _e in extents}
    has_argumentless_close: dict[int, bool] = {h: False for _l, h, _e in extents}

    for cmd, kw, kw_node in _commands(index, src):
        bucket = _label_for_line(kw_node.start_point[0], extents)
        if bucket is None:
            continue
        header = bucket[1]
        args = list(_arguments(cmd))
        if kw in _OPEN_KEYWORDS and args:
            opens[header].append(kw_node)
        elif kw in _CLOSE_KEYWORDS:
            if not args:
                has_argumentless_close[header] = True
            else:
                closes[header] += len(args)

    for label, header, _end in extents:
        n_open = len(opens[header])
        if n_open == 0:
            continue
        if has_argumentless_close[header]:
            continue
        n_close = closes[header]
        if n_open > n_close:
            kw_node = opens[header][n_close]
            line, col = _node_line_col(kw_node, src)
            name = _label_name(src, label)
            yield Diagnostic(
                rule_id="M-MOD-014",
                severity=Severity.WARNING,
                message=(
                    f"Device leak in label '{name}': {n_open} OPEN(s), "
                    f"{n_close} CLOSE(s)"
                ),
                path=path,
                line=line,
                column=col,
            )


register(
    Rule(
        id="M-MOD-014",
        severity=Severity.WARNING,
        category=Category.CONCURRENCY,
        title="OPEN without matching CLOSE in same label",
        tags=("modern",),
        check=_check_open_close,
        needs_context=True,
        replaces=(),
    )
)


# ===========================================================================
# Phase 5 — Tier 2 control-flow + correctness rules
# ===========================================================================
#
# Pure AST-pattern rules; no flow analysis needed. The 6th rule from
# the implementation plan (M-MOD-017 — $TEST read after a command that
# resets it) is deferred to Phase 7: detecting user intent in the face
# of $TEST overwrites requires the data-flow analyzer that ships there.


# Intrinsic functions known to mutate state (so calling them in a
# postconditional silently produces side effects). Pure intrinsics
# (``$LENGTH``, ``$EXTRACT``, ``$SELECT``, ``$DATA``, ``$GET``,
# ``$ORDER``, ``$QUERY``, etc.) are NOT in this set — they're safe in
# any expression context.
_SIDE_EFFECTING_INTRINSICS_UPPER = frozenset(
    {"$INCREMENT", "$I", "$ZINCREMENT", "$ZI"}
)


# ---------------------------------------------------------------------------
# M-MOD-015 — $SELECT() without final default arm
# ---------------------------------------------------------------------------


def _select_arm_conditions(call_node) -> list:
    """Yield the condition node of each $SELECT arm in source order.

    A $SELECT arm is a ``cond:val`` pair separated by commas. The
    condition node is the one immediately preceding each top-level
    ``:`` literal child. Returns the list ordered by source position.
    """
    children = list(call_node.children)
    conds: list = []
    # Walk children, alternating cond → ':' → val → ',' → cond → ...
    expect_cond = True
    last_payload = None
    for c in children:
        if c.type in ("intrinsic_function_keyword", "(", ")"):
            continue
        if c.type == ",":
            expect_cond = True
            continue
        if c.type == ":":
            if expect_cond and last_payload is not None:
                conds.append(last_payload)
            expect_cond = False
            last_payload = None
            continue
        # Otherwise, it's an expression (cond OR val).
        if expect_cond:
            last_payload = c
        else:
            # Value side; ignore.
            pass
    return conds


def _check_select_no_default(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-015 — $SELECT() without a final ``1:`` default arm.

    Every $SELECT should end with a ``1:default-value`` arm. If no arm
    matches and there's no default, M raises a ``select`` error at
    runtime. Modern style: always provide an explicit default, even
    when the call sites "shouldn't" hit no-match.
    """
    for fn in index.of("function_call"):
        kw = next(
            (c for c in fn.children if c.type == "intrinsic_function_keyword"),
            None,
        )
        if kw is None:
            continue
        name = _node_text(kw, src).upper()
        if name not in ("$SELECT", "$S"):
            continue
        conds = _select_arm_conditions(fn)
        if not conds:
            continue  # malformed; let parse-error catch it
        last = conds[-1]
        # The "default" arm is one whose condition is the integer literal 1.
        # Any other expression — even ``1=1`` or ``$T`` — is rejected
        # because the user might genuinely intend a conditional.
        is_default = last.type == "number" and _node_text(last, src) == "1"
        if not is_default:
            yield Diagnostic(
                rule_id="M-MOD-015",
                severity=Severity.WARNING,
                message=(
                    "$SELECT without final `1:` default arm — runtime "
                    "<SELECT> error if no condition matches"
                ),
                path=path,
                line=fn.start_point[0] + 1,
                column=fn.start_point[1] + 1,
                column_end=fn.end_point[1] + 1,
            )


register(
    Rule(
        id="M-MOD-015",
        severity=Severity.WARNING,
        category=Category.BUG,
        title="$SELECT() without final default arm",
        tags=("modern",),
        check=_check_select_no_default,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-016 — Side-effecting postconditional
# ---------------------------------------------------------------------------


def _has_side_effect(node, src: bytes) -> bool:
    """True when ``node``'s subtree contains a known side-effecting call.

    Side effects we recognize today:
      - any ``extrinsic_function`` ($$call) — calls user code
      - ``function_call`` with intrinsic ``$INCREMENT`` / ``$ZINCREMENT``
        (atomic counter updates)

    Does NOT flag pure intrinsics (``$LENGTH``, ``$DATA``, ``$ORDER``,
    ``$SELECT``, ``$EXTRACT``, etc.) — those are safe in any expression.
    """
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type == "extrinsic_function":
            return True
        if n.type == "function_call":
            kw = next(
                (c for c in n.children if c.type == "intrinsic_function_keyword"),
                None,
            )
            if kw is not None:
                name = _node_text(kw, src).upper()
                if name in _SIDE_EFFECTING_INTRINSICS_UPPER:
                    return True
        stack.extend(n.children)
    return False


def _check_side_effect_postcond(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-016 — Postconditional argument has side effects.

    A postconditional (``S:cond X=...``, ``W:cond ...``) is evaluated
    for the truthy/falsy decision. If ``cond`` mutates state (calls
    ``$$user_fn``, ``$INCREMENT``, etc.), readers can't tell whether
    the side effect runs once, never, or always. Flag and prefer
    explicit ``IF`` form.
    """
    for pc in index.of("postconditional"):
        if _has_side_effect(pc, src):
            yield Diagnostic(
                rule_id="M-MOD-016",
                severity=Severity.WARNING,
                message=(
                    "Postconditional has side-effecting argument "
                    "(extrinsic call or $INCREMENT) — prefer explicit IF"
                ),
                path=path,
                line=pc.start_point[0] + 1,
                column=pc.start_point[1] + 1,
                column_end=pc.end_point[1] + 1,
            )


register(
    Rule(
        id="M-MOD-016",
        severity=Severity.WARNING,
        category=Category.BUG,
        title="Postconditional with side-effecting argument",
        tags=("modern",),
        check=_check_side_effect_postcond,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-018 — Argumentless FOR without Q-postconditional on the same line
# ---------------------------------------------------------------------------


def _check_for_no_quit(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-018 — Argumentless ``FOR`` with no Q-postconditional in same line.

    ``FOR`` with no argument loops forever unless something inside
    breaks out. Idiomatic: ``F  Q:done  W ...`` (the conditional QUIT
    is the loop exit). If the same ``command_sequence`` containing
    the argumentless FOR has no ``Q``/``QUIT`` with a postconditional,
    flag the FOR.

    Limitation: dot-block bodies (``F  D`` followed by ``. Q:done``)
    are not analyzed in V1 — Phase 7's CFG work covers them.
    """
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("F", "FOR"):
            continue
        # Argumentless: command has no argument_list child.
        if any(c.type == "argument_list" for c in cmd.children):
            continue
        # Look at sibling commands within the same command_sequence
        # for a Q/QUIT with a postconditional (the canonical exit).
        seq = cmd.parent
        if seq is None or seq.type != "command_sequence":
            continue
        has_exit = False
        for sib in seq.children:
            if sib is cmd or sib.type != "command":
                continue
            sib_kw = next(
                (c for c in sib.children if c.type == "command_keyword"),
                None,
            )
            if sib_kw is None:
                continue
            sib_kw_text = _node_text(sib_kw, src).upper()
            if sib_kw_text not in ("Q", "QUIT", "G", "GOTO", "H", "HALT"):
                continue
            has_postcond = any(c.type == "postconditional" for c in sib.children)
            if has_postcond:
                has_exit = True
                break
        if not has_exit:
            line, col = _node_line_col(kw_node, src)
            yield Diagnostic(
                rule_id="M-MOD-018",
                severity=Severity.WARNING,
                message=(
                    "Argumentless FOR with no conditional QUIT/GOTO/HALT "
                    "on the same line — infinite loop unless caller breaks out"
                ),
                path=path,
                line=line,
                column=col,
                column_end=col + len(kw),
            )


register(
    Rule(
        id="M-MOD-018",
        severity=Severity.WARNING,
        category=Category.BUG,
        title="Argumentless FOR without conditional exit on same line",
        tags=("modern",),
        check=_check_for_no_quit,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-019 — Broad pattern operator (`?.E`)
# ---------------------------------------------------------------------------


def _check_broad_pattern(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-019 — Pattern operator with ``?.E`` (accept-anything).

    ``X?.E`` is tautologically true: ``.E`` matches zero-or-more of
    *any* character. The match always succeeds, so the test is a
    no-op — usually a placeholder leftover or copy-paste error.

    We flag any ``pattern`` node consisting of exactly one
    ``pattern_atom`` whose text is ``.E`` (case-insensitive). More
    elaborate pattern smells (e.g. ``?.E1A.E`` — "anything containing
    one alpha") are NOT flagged because they actually constrain.
    """
    for pat in index.of("pattern"):
        atoms = [c for c in pat.children if c.type == "pattern_atom"]
        if len(atoms) != 1:
            continue
        text = _node_text(atoms[0], src).upper()
        if text == ".E":
            yield Diagnostic(
                rule_id="M-MOD-019",
                severity=Severity.WARNING,
                message=(
                    "Pattern `?.E` matches anything (tautology) — likely "
                    "placeholder or copy-paste leftover"
                ),
                path=path,
                line=pat.start_point[0] + 1,
                column=pat.start_point[1] + 1,
                column_end=pat.end_point[1] + 1,
            )


register(
    Rule(
        id="M-MOD-019",
        severity=Severity.WARNING,
        category=Category.BUG,
        title="Broad pattern operator (`?.E`) — tautological match",
        tags=("modern",),
        check=_check_broad_pattern,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-020 — By-reference call argument never written by callee (intra-routine)
# ---------------------------------------------------------------------------


def _enclosing_call_target(byref, src: bytes) -> tuple[str, bool] | None:
    """Resolve the call site enclosing a ``by_reference`` node.

    Returns ``(callee_name, is_cross_routine)`` or ``None`` when the
    enclosing structure is not a call we recognize. ``is_cross_routine``
    is True when the call has a ``^routine`` portion — the caller can
    skip those for intra-routine analysis.

    Recognized shapes (per tree-sitter-m's AST):
      - ``D label(.x,...)``   → byref.parent is ``subscripts``;
        ``subscripts.parent`` is ``local_variable`` (intra-routine);
        the callee identifier is a sibling of ``subscripts`` within
        the ``local_variable`` node.
      - ``D ^routine(.x,...)`` → same but ``subscripts.parent`` is
        ``global_variable`` (cross-routine).
      - ``S X=$$label(.x,...)`` → byref.parent is ``extrinsic_function``;
        the identifier and any ``^`` token are siblings of byref.
    """
    # Walk up until we find subscripts (DO call) or extrinsic_function.
    node = byref.parent
    while node is not None:
        if node.type == "subscripts":
            container = node.parent  # local_variable or global_variable
            if container is None:
                return None
            if container.type not in ("local_variable", "global_variable"):
                return None
            ident = next(
                (c for c in container.children if c.type == "identifier"),
                None,
            )
            if ident is None:
                return None
            return (
                _node_text(ident, src),
                container.type == "global_variable",
            )
        if node.type == "extrinsic_function":
            # Extrinsic: $$ <ident> [^ <routine>] ( ... )
            ident = next(
                (c for c in node.children if c.type == "identifier"),
                None,
            )
            cross = any(c.type == "^" for c in node.children)
            if ident is None:
                return None
            return (_node_text(ident, src), cross)
        node = node.parent
    return None


def _byref_position(byref) -> int:
    """Return the 0-based positional index of ``byref`` within its
    enclosing argument list (subscripts or extrinsic_function).

    Identity comparison (``c is byref``) doesn't work with tree-sitter
    Python bindings — every ``.parent`` / ``.children`` access produces
    fresh Node wrappers around the underlying C node. We match by
    (start_byte, end_byte) instead.
    """
    parent = byref.parent
    if parent is None:
        return -1
    target_range = (byref.start_byte, byref.end_byte)
    pos = 0
    for c in parent.children:
        if (c.start_byte, c.end_byte) == target_range and c.type == "by_reference":
            return pos
        if c.type in (
            "by_reference",
            "variable",
            "string",
            "number",
            "binary_expression",
            "function_call",
            "extrinsic_function",
        ):
            pos += 1
    return -1


def _check_byref_unused(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-020 — Caller passes ``.var`` but callee never writes that formal.

    For each ``by_reference`` argument at an intra-routine call site,
    resolve the callee's formal-name list (positionally) and verify
    that the corresponding formal is on the LHS of at least one SET
    in the callee's body. If never written, the caller's ``.var``
    is misleading — the value won't change.

    Phase 5 V1 covers intra-routine calls only (``D label(.x)`` and
    ``$$label(.x)``). Cross-routine variants (``D ^routine(.x)`` and
    ``$$label^routine(.x)``) wait for Phase 7's workspace-aware
    analysis.
    """
    extents = _label_body_extents(src, index)
    if not extents:
        return

    # Build {label_name → (formal_names, header_line, end_line)}
    label_formals: dict[str, tuple[list[str], int, int]] = {}
    for label_node, header, end in extents:
        # `formals` sits as a sibling of `label` under the line node.
        line_parent = label_node.parent
        if line_parent is None:
            continue
        formals = next(
            (c for c in line_parent.children if c.type == "formals"),
            None,
        )
        names = (
            [c for c in formals.children if c.type == "identifier"] if formals else []
        )
        label_formals[_label_name(src, label_node)] = (
            [_node_text(n, src) for n in names],
            header,
            end,
        )

    # Build {label_name → set of formal-name LHS-of-SET targets}
    written_per_label: dict[str, set[str]] = {n: set() for n in label_formals}
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in _SET_KEYWORDS:
            continue
        line = kw_node.start_point[0]
        owner = None
        for name, (_formals, hdr, end) in label_formals.items():
            if hdr <= line < end:
                owner = name
                break
        if owner is None:
            continue
        for arg in _arguments(cmd):
            payload = _payload(arg)
            if payload is None or payload.type != "binary_expression":
                continue
            lhs = next(
                (
                    c
                    for c in payload.children
                    if c.type not in ("=", "operator", "(", ")", ",")
                ),
                None,
            )
            if lhs is None or lhs.type != "variable":
                continue
            local = next(
                (c for c in lhs.children if c.type == "local_variable"),
                None,
            )
            if local is None:
                continue
            ident = next(
                (c for c in local.children if c.type == "identifier"),
                None,
            )
            if ident is None:
                continue
            written_per_label[owner].add(_node_text(ident, src))

    # Walk every by_reference; resolve callee; check if its formal is written.
    for byref in index.of("by_reference"):
        target = _enclosing_call_target(byref, src)
        if target is None:
            continue
        callee_name, is_cross = target
        if is_cross:
            continue  # cross-routine: deferred to Phase 7
        if callee_name not in label_formals:
            continue
        formals, _h, _e = label_formals[callee_name]
        pos = _byref_position(byref)
        if pos < 0 or pos >= len(formals):
            continue
        formal_name = formals[pos]
        if formal_name in written_per_label.get(callee_name, set()):
            continue
        # Not written — flag the caller's `.x` argument.
        ident = next(
            (c for c in byref.children if c.type == "identifier"),
            None,
        )
        var_name = _node_text(ident, src) if ident is not None else "?"
        yield Diagnostic(
            rule_id="M-MOD-020",
            severity=Severity.WARNING,
            message=(
                f"By-reference argument `.{var_name}` to '{callee_name}' but "
                f"the callee never writes its formal '{formal_name}'"
            ),
            path=path,
            line=byref.start_point[0] + 1,
            column=byref.start_point[1] + 1,
            column_end=byref.end_point[1] + 1,
        )


register(
    Rule(
        id="M-MOD-020",
        severity=Severity.WARNING,
        category=Category.BUG,
        title="By-reference argument never written by intra-routine callee",
        tags=("modern",),
        check=_check_byref_unused,
        needs_context=True,
        replaces=(),
    )
)


# ===========================================================================
# Phase 6 — Engine-aware Z-extension allowlists
# ===========================================================================
#
# These rules supersede the legacy M-XINDX-002 / 028 / 031 absolute-ban
# detectors. They consult ``ctx.target_engine`` and consult m-standard's
# per-engine ``standard_status`` field (via
# :func:`m_cli.lint._keywords.engine_allowlist`) to decide whether a
# given Z-token is portable on the target engine.
#
# - ``--target-engine=any`` (default): only ANSI tokens are safe.
#   Equivalent in spirit to the legacy rules' "non-standard means
#   non-ANSI" behavior.
# - ``--target-engine=yottadb``: ANSI + YDB extensions + multi-vendor
#   extensions are safe; IRIS-only extensions flagged.
# - ``--target-engine=iris``: ANSI + IRIS extensions + multi-vendor
#   extensions are safe; YDB-only extensions flagged.
#
# When m-standard is unavailable, the helper falls back to the simple
# ``standard_*()`` sets (= ANSI baseline) regardless of engine.


# Strip arguments / suffixes from a $Z-token: ``$ZH(arg)`` → ``$ZH``.
_Z_TOKEN_RE = re.compile(r"^\$Z[A-Z]*", re.IGNORECASE)


def _bare_z_name(text: str) -> str | None:
    """Return ``$Z...`` prefix of ``text`` (uppercased), or None."""
    m = _Z_TOKEN_RE.match(text)
    return m.group(0).upper() if m else None


# ---------------------------------------------------------------------------
# M-MOD-021 — Z-command not in target engine's documented set
# ---------------------------------------------------------------------------


def _check_z_command_engine_aware(
    src: bytes, _tree, path: Path, index: NodeIndex, ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-021 — Engine-aware Z-command portability check.

    Replaces M-XINDX-002's absolute "non-standard Z command" ban with a
    target-engine-relative check. ``ZBREAK`` is fine on YottaDB, fine
    on IRIS, but NOT in portable ("any") code. This rule lets users
    declare their target engine and stop fighting noise on legitimate
    engine extensions.
    """
    allowed = engine_allowlist(ctx.target_engine, "command")
    for _cmd, kw, kw_node in _commands(index, src):
        if not kw.startswith("Z"):
            continue
        if kw in allowed:
            continue
        line, col = _node_line_col(kw_node, src)
        yield Diagnostic(
            rule_id="M-MOD-021",
            severity=Severity.WARNING,
            message=(
                f"Z-command {kw!r} not in --target-engine={ctx.target_engine!r} "
                f"allowlist (per m-standard); non-portable on this target"
            ),
            path=path,
            line=line,
            column=col,
            column_end=col + len(kw),
        )


register(
    Rule(
        id="M-MOD-021",
        severity=Severity.WARNING,
        category=Category.PORTABILITY,
        title="Z-command not in target engine's documented set",
        tags=("modern",),
        check=_check_z_command_engine_aware,
        needs_context=True,
        replaces=("M-XINDX-002",),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-022 — $Z* ISV not in target engine's documented set
# ---------------------------------------------------------------------------


def _check_z_isv_engine_aware(
    src: bytes, _tree, path: Path, index: NodeIndex, ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-022 — Engine-aware $Z* ISV portability check.

    Replaces M-XINDX-028. Reads the ISV name (e.g. ``$ZHOROLOG``) and
    checks it against the target engine's allowlist. ``$ZHOROLOG`` is
    in both YDB and IRIS allowlists; ``$ZJOB`` (YDB) is not in IRIS;
    etc.
    """
    allowed = engine_allowlist(ctx.target_engine, "isv")
    # NB: tree-sitter-m calls the node ``special_variable`` (not
    # ``intrinsic_special_variable`` — the legacy M-XINDX-028 had a
    # typo that silently no-op'd; M-MOD-022 fixes the lookup). The
    # node has a ``special_variable_keyword`` child carrying the
    # bare name; its text equals the parent's text in current
    # tree-sitter-m versions, so reading the parent's text works.
    for node in index.of("special_variable"):
        text = _node_text(node, src)
        name = _bare_z_name(text)
        if name is None:
            continue
        if name in allowed:
            continue
        line, col = _node_line_col(node, src)
        yield Diagnostic(
            rule_id="M-MOD-022",
            severity=Severity.WARNING,
            message=(
                f"$Z* ISV {name} not in --target-engine="
                f"{ctx.target_engine!r} allowlist"
            ),
            path=path,
            line=line,
            column=col,
            column_end=col + len(name),
        )


register(
    Rule(
        id="M-MOD-022",
        severity=Severity.WARNING,
        category=Category.PORTABILITY,
        title="$Z* ISV not in target engine's documented set",
        tags=("modern",),
        check=_check_z_isv_engine_aware,
        needs_context=True,
        replaces=("M-XINDX-028",),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-023 — $Z* function not in target engine's documented set
# ---------------------------------------------------------------------------


def _check_z_function_engine_aware(
    src: bytes, _tree, path: Path, index: NodeIndex, ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-023 — Engine-aware $Z* function portability check.

    Replaces M-XINDX-031. The function name is read from the
    ``intrinsic_function_keyword`` child of each ``function_call``
    node; we strip arguments to get the bare name (e.g.
    ``$ZSEARCH(args)`` → ``$ZSEARCH``).
    """
    allowed = engine_allowlist(ctx.target_engine, "function")
    for fn in index.of("function_call"):
        kw = next(
            (c for c in fn.children if c.type == "intrinsic_function_keyword"),
            None,
        )
        if kw is None:
            continue
        text = _node_text(kw, src)
        if not text.upper().startswith("$Z"):
            continue
        name = _bare_z_name(text)
        if name is None or name in allowed:
            continue
        yield Diagnostic(
            rule_id="M-MOD-023",
            severity=Severity.WARNING,
            message=(
                f"$Z* function {name} not in --target-engine="
                f"{ctx.target_engine!r} allowlist"
            ),
            path=path,
            line=kw.start_point[0] + 1,
            column=kw.start_point[1] + 1,
            column_end=kw.start_point[1] + 1 + len(name),
        )


register(
    Rule(
        id="M-MOD-023",
        severity=Severity.WARNING,
        category=Category.PORTABILITY,
        title="$Z* function not in target engine's documented set",
        tags=("modern",),
        check=_check_z_function_engine_aware,
        needs_context=True,
        replaces=("M-XINDX-031",),
    )
)


# ===========================================================================
# Phase 8 — Documentation + style polish (M-MOD-028..035)
# ===========================================================================
#
# Cheap rules that round out the modern profile. Tier 4 / Tier 5 from
# the survey. Most are INFO/STYLE severity; the bug-like ones (NEW
# without args) are WARNING. Some have natural auto-fixers (M-MOD-034,
# M-MOD-035) but the auto-fix wiring waits for a corresponding
# ``m fmt`` rule.
#
# Phase 7 (data-flow) remains the only research-grade subproject left
# in the original plan; M-MOD-024..027 (path-sensitive concurrency)
# and M-MOD-017 ($TEST staleness) wait for it.


# Numeric literals exempted from M-MOD-031. -1, 0, 1, 2 are the
# universal "loop counter starts / ends / increments / boolean flags"
# canon — flagging them would generate pure noise.
_MAGIC_NUMBER_EXEMPT = frozenset({"-1", "0", "1", "2"})


# ---------------------------------------------------------------------------
# M-MOD-028 — Public label without docstring
# ---------------------------------------------------------------------------


def _check_label_docstring(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-028 — Each top-level label should carry a docstring.

    A docstring is either a same-line trailing comment on the label
    header (``mylabel ;description``) or a comment-only first body
    line (``mylabel\\n ; description\\n``). Neither = no docstring.
    Severity INFO — informational; users can disable per-rule for
    obviously-private helpers.
    """
    extents = _label_body_extents(src, index)
    if not extents:
        return
    # Pre-bucket comments by line for O(1) lookup.
    comment_lines: set[int] = set()
    for c in index.of("comment"):
        comment_lines.add(c.start_point[0])

    for label, header_line, end_line in extents:
        # Same-line comment (``mylabel ;doc``)?
        line_parent = label.parent
        if line_parent is not None and any(c.type == "comment" for c in line_parent.children):
            continue
        # First body line is a comment-only line?
        if header_line + 1 < end_line and (header_line + 1) in comment_lines:
            continue
        name = _label_name(src, label)
        yield Diagnostic(
            rule_id="M-MOD-028",
            severity=Severity.INFO,
            message=f"Label '{name}' has no docstring (header comment or first-body comment)",
            path=path,
            line=header_line + 1,
            column=label.start_point[1] + 1,
            column_end=label.start_point[1] + 1 + len(name),
        )


register(
    Rule(
        id="M-MOD-028",
        severity=Severity.INFO,
        category=Category.DOCUMENTATION,
        title="Label without docstring",
        # `pedantic` — many real-world M labels lack docstrings; opt
        # into the strict view via `--rules=modern`.
        tags=("modern", "pedantic"),
        check=_check_label_docstring,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-029 — Comment density per label below threshold
# ---------------------------------------------------------------------------


def _check_comment_density(
    src: bytes, _tree, path: Path, index: NodeIndex, ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-029 — Per-label comment density below configured percent.

    Counts the fraction of body lines containing any comment (full-line
    ``;...`` or inline ``code ;...``) and flags the label when it falls
    below ``ctx.thresholds["comment_density_pct"]``. Body line count
    excludes blank lines so the density isn't dominated by formatting
    spaces. Labels with very short bodies (≤3 lines) are exempt — too
    little signal to be useful.
    """
    extents = _label_body_extents(src, index)
    if not extents:
        return
    threshold_pct = ctx.thresholds["comment_density_pct"]
    # Bucket lines containing a comment.
    comment_lines: set[int] = set()
    for c in index.of("comment"):
        comment_lines.add(c.start_point[0])

    raw_lines = src.splitlines()

    for label, header_line, end_line in extents:
        # Body = lines AFTER the header, BEFORE the next label.
        body_lines = [
            i
            for i in range(header_line + 1, end_line)
            if i < len(raw_lines) and raw_lines[i].strip()  # non-blank
        ]
        if len(body_lines) <= 3:
            continue  # too small to measure meaningfully
        n_commented = sum(1 for i in body_lines if i in comment_lines)
        density_pct = (n_commented * 100) // len(body_lines)
        if density_pct < threshold_pct:
            name = _label_name(src, label)
            yield Diagnostic(
                rule_id="M-MOD-029",
                severity=Severity.INFO,
                message=(
                    f"Label '{name}' comment density {density_pct}% "
                    f"below threshold {threshold_pct}% "
                    f"({n_commented}/{len(body_lines)} non-blank lines)"
                ),
                path=path,
                line=header_line + 1,
                column=label.start_point[1] + 1,
                column_end=label.start_point[1] + 1 + len(name),
            )


register(
    Rule(
        id="M-MOD-029",
        severity=Severity.INFO,
        category=Category.DOCUMENTATION,
        title="Comment density per label below configured threshold",
        tags=("modern",),
        check=_check_comment_density,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-030 — TODO / FIXME without owner / ticket
# ---------------------------------------------------------------------------


# Match TODO / FIXME / XXX / HACK markers, then optional `(owner)` or
# `[ticket-ref]` annotation. Without one of those, we flag.
_TODO_MARKERS = ("TODO", "FIXME", "XXX", "HACK")
_TODO_RE = re.compile(
    r"\b(TODO|FIXME|XXX|HACK)\b\s*(\(([^)]+)\)|\[([^\]]+)\]|@(\w+)|([A-Z][A-Z0-9]+-\d+))?",
    re.IGNORECASE,
)


def _check_todo_ownership(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-030 — ``TODO`` / ``FIXME`` / ``XXX`` / ``HACK`` markers
    without an owner or ticket reference.

    Accepted forms (silent):
      ``;TODO(rafael) handle null``
      ``;FIXME [PROJ-123] race condition``
      ``;XXX @rafael revisit after Q3``
      ``;HACK PROJ-99 monkey-patch``

    Plain ``;TODO add validation`` (no owner / ticket) → flagged. The
    intent is to make accountability explicit so abandoned markers
    don't accumulate without a person or issue to dig in.
    """
    for c in index.of("comment"):
        text = _node_text(c, src)
        for match in _TODO_RE.finditer(text):
            marker = match.group(1).upper()
            # Groups 2/3/4/5/6 capture the various owner/ticket forms.
            has_attribution = any(match.group(g) for g in (2, 3, 4, 5, 6))
            if has_attribution:
                continue
            # Compute the column of the marker within the source line.
            marker_col_in_comment = match.start(1)
            line = c.start_point[0]
            # Find absolute column: line start + comment offset + marker offset.
            col = c.start_point[1] + marker_col_in_comment + 1
            yield Diagnostic(
                rule_id="M-MOD-030",
                severity=Severity.INFO,
                message=(
                    f"{marker} marker without owner or ticket reference "
                    f"— add ``({marker}(name))`` or ``[PROJ-NN]`` for "
                    f"accountability"
                ),
                path=path,
                line=line + 1,
                column=col,
                column_end=col + len(marker),
            )


register(
    Rule(
        id="M-MOD-030",
        severity=Severity.INFO,
        category=Category.DOCUMENTATION,
        title="TODO / FIXME / XXX / HACK without owner or ticket reference",
        tags=("modern",),
        check=_check_todo_ownership,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-031 — Magic numeric literal
# ---------------------------------------------------------------------------


def _check_magic_numbers(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-031 — Numeric literal not in {-1, 0, 1, 2}.

    Most numeric literals beyond the universal "boolean / loop counter"
    canon are magic — they should be NEW'd / SET'd to a named local
    or pulled from a parameter table. The exempt set is intentionally
    minimal; users with project-specific exempt sets can disable the
    rule via ``; m-lint: disable=M-MOD-031`` on a case-by-case basis.

    Negative literals (``-1``) parse as ``unary_expression -`` wrapping
    a ``number`` — we account for the sign here so ``-1`` is exempt
    but ``-99`` is not.

    Numbers inside the timeout part of a LOCK/OPEN/READ/JOB command
    (``argument_postconditional``) and the bound part of a numeric FOR
    (``F I=1:1:10`` — the ``1``s and ``10``) are exempt because those
    are domain literals the rule was never about.
    """
    for num in index.of("number"):
        text = _node_text(num, src)
        # Compose the effective text including a leading `-` if the
        # parent unary_expression wraps a single `-`.
        effective = text
        parent = num.parent
        if parent is not None and parent.type == "unary_expression":
            op = next(
                (c for c in parent.children if c.type == "operator"),
                None,
            )
            if op is not None:
                op_text = _node_text(op, src)
                if op_text == "-":
                    effective = "-" + text
                elif op_text == "+":
                    effective = text  # bare `+1` collapses to `1`
        if effective in _MAGIC_NUMBER_EXEMPT:
            continue
        # Skip numbers inside argument_postconditional (timeout, FOR step).
        if _ancestor_of_type(num, "argument_postconditional") is not None:
            continue
        yield Diagnostic(
            rule_id="M-MOD-031",
            severity=Severity.STYLE,
            message=f"Magic numeric literal {effective} — extract to a named constant",
            path=path,
            line=num.start_point[0] + 1,
            column=num.start_point[1] + 1,
            column_end=num.end_point[1] + 1,
        )


def _ancestor_of_type(node, target_type: str):
    """Return the nearest ancestor of ``target_type``, or None."""
    p = node.parent
    while p is not None:
        if p.type == target_type:
            return p
        p = p.parent
    return None


register(
    Rule(
        id="M-MOD-031",
        severity=Severity.STYLE,
        category=Category.STYLE,
        title="Magic numeric literal (extract to a named constant)",
        # `pedantic` — magic-number flagging is a strong stylistic
        # preference; M code uses raw constants heavily. Opt in via
        # `--rules=modern`.
        tags=("modern", "pedantic"),
        check=_check_magic_numbers,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-032 — Single-letter local variable outside FOR loop counter
# ---------------------------------------------------------------------------


def _for_loop_counter_names(src: bytes, index: NodeIndex) -> set[str]:
    """Return the set of local-variable names that appear as the loop
    counter in a numeric ``FOR I=...`` somewhere in the file.

    The detection heuristic: for each ``FOR`` / ``F`` command, the
    first argument's binary_expression LHS variable is the counter.
    Multi-counter ``F I=1:1:10,J=1:1:5`` are rare and only the first
    is captured today.
    """
    out: set[str] = set()
    for cmd, kw, _kw_node in _commands(index, src):
        if kw not in ("F", "FOR"):
            continue
        for arg in _arguments(cmd):
            payload = _payload(arg)
            if payload is None or payload.type != "binary_expression":
                break
            lhs = next(
                (c for c in payload.children if c.type == "variable"),
                None,
            )
            if lhs is None:
                break
            local = next(
                (c for c in lhs.children if c.type == "local_variable"),
                None,
            )
            if local is None:
                break
            ident = next(
                (c for c in local.children if c.type == "identifier"),
                None,
            )
            if ident is not None:
                out.add(_node_text(ident, src))
            break  # only the first arg is the counter
    return out


def _check_single_letter_var(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-032 — Single-letter local-variable name outside a FOR
    loop counter.

    M permits ``S X=1`` everywhere. Modern style: pick a meaningful
    name. The exception is FOR loop counters (``F I=1:1:10``) where
    short names are universally legible. We harvest the file's FOR
    counters once and exempt them globally.
    """
    exempt = _for_loop_counter_names(src, index)
    seen: set[tuple[int, int, int]] = set()  # (line, col, end_col)
    for var in index.of("local_variable"):
        ident = next(
            (c for c in var.children if c.type == "identifier"),
            None,
        )
        if ident is None:
            continue
        name = _node_text(ident, src)
        if len(name) != 1 or not name.isalpha():
            continue
        if name in exempt:
            continue
        loc = (
            ident.start_point[0],
            ident.start_point[1],
            ident.end_point[1],
        )
        if loc in seen:
            continue  # nested local_variable wrappers — emit once
        seen.add(loc)
        yield Diagnostic(
            rule_id="M-MOD-032",
            severity=Severity.STYLE,
            message=(
                f"Single-letter variable {name!r} outside FOR loop counter "
                f"— pick a meaningful name"
            ),
            path=path,
            line=ident.start_point[0] + 1,
            column=ident.start_point[1] + 1,
            column_end=ident.end_point[1] + 1,
        )


register(
    Rule(
        id="M-MOD-032",
        severity=Severity.STYLE,
        category=Category.STYLE,
        title="Single-letter local variable outside FOR loop counter",
        # `pedantic` — M tradition uses single-letter vars heavily;
        # the rule fires ~23K times on real corpora. Opt into the
        # strict view via `--rules=modern`.
        tags=("modern", "pedantic"),
        check=_check_single_letter_var,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-033 — Argumentless NEW
# ---------------------------------------------------------------------------


def _check_argumentless_new(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-033 — ``NEW`` with no arguments stack-saves every local.

    Almost always a mistake: the user meant ``NEW (varlist)`` (exclusive
    NEW) or ``NEW var,var2`` (specific NEW). The bare form is the
    catch-all "save every variable in this scope" — heavyweight and
    intent-obscuring.
    """
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("N", "NEW"):
            continue
        if any(c.type == "argument_list" for c in cmd.children):
            continue
        line, col = _node_line_col(kw_node, src)
        yield Diagnostic(
            rule_id="M-MOD-033",
            severity=Severity.WARNING,
            message=(
                "Argumentless NEW — stack-saves every local; use NEW (var,..) "
                "for exclusive scope or NEW var,var2 for specific names"
            ),
            path=path,
            line=line,
            column=col,
            column_end=col + len(kw),
        )


register(
    Rule(
        id="M-MOD-033",
        severity=Severity.WARNING,
        category=Category.BUG,
        title="Argumentless NEW (stack-saves every local — almost always a mistake)",
        tags=("modern",),
        check=_check_argumentless_new,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-034 — SET X=X+N → $INCREMENT(X[,N])
# ---------------------------------------------------------------------------


def _check_set_increment(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-034 — Suggest ``$INCREMENT()`` for ``SET X=X+N`` patterns.

    Modern engines provide atomic ``$INCREMENT`` (YDB) / ``$INCREMENT``
    (IRIS) — the same operation but race-free across processes. Even
    in single-process code, ``S X=$I(X)`` is more concise.

    Detection: SET arguments whose AST is::

        binary_expression X=X+N
          binary_expression X=X
          operator + (or -)
          number N

    The inner ``binary_expression``'s LHS and RHS variables must have
    the same identifier text (case-sensitive — M variables are too).
    """
    for cmd, kw, _kw_node in _commands(index, src):
        if kw not in _SET_KEYWORDS:
            continue
        for arg in _arguments(cmd):
            payload = _payload(arg)
            if payload is None or payload.type != "binary_expression":
                continue
            # Outer must have shape: binary_expression(inner, +/-, number).
            # Walk children once and capture the three pieces by type.
            inner = None
            op = None
            num = None
            for c in payload.children:
                if c.type == "binary_expression" and inner is None:
                    inner = c
                elif c.type == "operator" and op is None:
                    op = c
                elif c.type == "number" and num is None:
                    num = c
            if inner is None or op is None or num is None:
                continue
            op_text = _node_text(op, src)
            if op_text not in ("+", "-"):
                continue
            # Inner must be `var = var` — same identifier on both sides.
            inner_kids = [
                c
                for c in inner.children
                if c.type not in ("operator", "=")
            ]
            if len(inner_kids) != 2:
                continue
            lhs_var, rhs_var = inner_kids
            if lhs_var.type != "variable" or rhs_var.type != "variable":
                continue
            lhs_name = _node_text(lhs_var, src)
            rhs_name = _node_text(rhs_var, src)
            if lhs_name != rhs_name:
                continue
            num_text = _node_text(num, src)
            # Compose the $INCREMENT suggestion. `S X=X+1` → `$I(X)`
            # (no second arg). `S X=X-1` → `$I(X,-1)`. `S X=X+10` →
            # `$I(X,10)`. Keep the user's original token text so the
            # diagnostic mirrors what they wrote.
            if op_text == "+" and num_text == "1":
                suggestion = f"$INCREMENT({lhs_name})"
            else:
                signed = num_text if op_text == "+" else f"-{num_text}"
                suggestion = f"$INCREMENT({lhs_name},{signed})"
            yield Diagnostic(
                rule_id="M-MOD-034",
                severity=Severity.INFO,
                message=(
                    f"`SET {lhs_name}={lhs_name}{op_text}{num_text}` "
                    f"— prefer `SET {lhs_name}={suggestion}`"
                ),
                path=path,
                line=payload.start_point[0] + 1,
                column=payload.start_point[1] + 1,
                column_end=payload.end_point[1] + 1,
            )


register(
    Rule(
        id="M-MOD-034",
        severity=Severity.INFO,
        category=Category.MODERNIZATION,
        title="SET X=X+N → prefer $INCREMENT(X) for atomic counters",
        tags=("modern",),
        check=_check_set_increment,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-035 — $Z* function abbreviation → canonical name
# ---------------------------------------------------------------------------


def _check_z_function_canonical(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-035 — Prefer canonical $Z* function names over abbreviations.

    Modern style: write ``$ZDATE`` not ``$ZD``, ``$ZSEARCH`` not ``$ZS``,
    etc. The plan called this out as the ``$ZD`` legacy case
    specifically; we generalize it to every $Z* function whose
    abbreviation is in m-standard's data — same canonicalization
    intent the formatter applies to ANSI command keywords.

    Lookup: m-standard ``KeywordRecord`` rows have both ``canonical``
    and ``abbreviation``; if the call's keyword equals an abbreviation
    that is NOT also the canonical (i.e. there's a longer name), flag.
    """
    # Build {abbreviation_upper: canonical_upper} for $Z* functions.
    from m_cli.lint._keywords import keyword_records

    abbrev_to_canon: dict[str, str] = {}
    for rec in keyword_records():
        if rec.kind != "function":
            continue
        if not rec.canonical or not rec.abbreviation:
            continue
        if not rec.canonical.upper().startswith("$Z"):
            continue
        if rec.abbreviation.upper() == rec.canonical.upper():
            continue  # no abbreviation distinct from canonical
        abbrev_to_canon[rec.abbreviation.upper()] = rec.canonical.upper()

    if not abbrev_to_canon:
        return  # m-standard not available → silent rather than noisy

    for fn in index.of("function_call"):
        kw = next(
            (c for c in fn.children if c.type == "intrinsic_function_keyword"),
            None,
        )
        if kw is None:
            continue
        name = _node_text(kw, src).upper()
        canonical = abbrev_to_canon.get(name)
        if canonical is None:
            continue
        yield Diagnostic(
            rule_id="M-MOD-035",
            severity=Severity.INFO,
            message=(
                f"$Z* function {name} is the abbreviation; prefer canonical {canonical}"
            ),
            path=path,
            line=kw.start_point[0] + 1,
            column=kw.start_point[1] + 1,
            column_end=kw.end_point[1] + 1,
        )


register(
    Rule(
        id="M-MOD-035",
        severity=Severity.INFO,
        category=Category.MODERNIZATION,
        title="$Z* function abbreviation — prefer canonical name",
        tags=("modern",),
        check=_check_z_function_canonical,
        needs_context=True,
        replaces=(),
        fixer_id="expand-intrinsic-functions",
    )
)


# ===========================================================================
# Phase 7 — Path-sensitive rules (M-MOD-024..027)
# ===========================================================================
#
# These rules consume the per-label CFG + definite-assignment analyzer
# from m_cli.lint.flow. M-MOD-024 ships first; the lock/transaction/
# $ETRAP path-sensitive variants (M-MOD-025..027) graduate the
# Phase 4 intra-label rules to multi-path accounting in subsequent
# slices.


# ---------------------------------------------------------------------------
# M-MOD-024 — Read of local before any SET on every prior path
# ---------------------------------------------------------------------------


def _find_test_default_set_protections(cfg, src: bytes) -> dict[str, int]:
    """Detect the canonical M ``IF $G(X)="" SET X=default`` idiom
    (and ``$D`` variants) and return ``{var_name: protection_line}``
    where ``protection_line`` is the 1-based line of the IF.

    After this line, the variable is guaranteed defined on every path:
    if the IF condition was false (X already defined and non-empty,
    or X exists for the $D case), the IF skips the rest of the line
    and X retains its prior value; if the condition was true, the
    SET runs and assigns the default.

    Pattern matched (intra-line):

      IF <expr-containing-$G(X)-or-$D(X)>  SET X=...

    The IF and SET must be on the SAME line. Multi-line variants
    (``IF '$D(X) DO`` with a dot-block ``. SET X=...``) are not
    matched in this slice; document and accept until the false-
    positive volume on real corpora justifies adding them.
    """
    from m_cli.lint.flow.vars import (
        _is_defensive_intrinsic,
        argument_nodes,
        command_keyword,
        effects_of_argument,
    )

    protections: dict[str, int] = {}

    # Group command-blocks by source line, in source order.
    by_line: dict[int, list] = {}
    for block in cfg.blocks:
        if block.kind == "command":
            by_line.setdefault(block.line, []).append(block)

    def _vars_tested_defensively(if_cmd) -> set[str]:
        """Local-var names appearing inside ``$G(...)`` or ``$D(...)``
        in the IF's argument tree. The first ``variable`` child of a
        defensive function_call is the tested name."""
        names: set[str] = set()

        def visit(node) -> None:
            if (
                node.type == "function_call"
                and _is_defensive_intrinsic(node)
            ):
                seen_first_var = False
                for c in node.children:
                    if not seen_first_var and c.type == "variable":
                        seen_first_var = True
                        for cc in c.children:
                            if cc.type == "local_variable":
                                for ccc in cc.children:
                                    if ccc.type == "identifier":
                                        text = src[
                                            ccc.start_byte : ccc.end_byte
                                        ].decode("latin-1", errors="replace")
                                        if text:
                                            names.add(text)
                                        break
                                break
                        # Continue visiting siblings to handle
                        # second-arg expressions normally.
                        continue
                    visit(c)
                return
            for c in node.children:
                visit(c)

        for arg in argument_nodes(if_cmd):
            visit(arg)
        return names

    for line, blocks in by_line.items():
        for i, block in enumerate(blocks):
            cmd = block.command
            kw = command_keyword(cmd, src).upper()
            if kw not in ("I", "IF"):
                continue
            tested = _vars_tested_defensively(cmd)
            if not tested:
                continue
            # Look at the remaining same-line blocks for a SET
            # targeting any of the tested vars.
            for nb in blocks[i + 1 :]:
                ncmd = nb.command
                nkw = command_keyword(ncmd, src).upper()
                if nkw not in ("S", "SET"):
                    continue
                set_targets: set[str] = set()
                for arg in argument_nodes(ncmd):
                    eff = effects_of_argument(arg, src, "S")
                    set_targets |= eff.defs
                for var in tested & set_targets:
                    # Earliest-protecting line wins (a var protected
                    # on line 5 is also protected on line 10).
                    if var not in protections or line < protections[var]:
                        protections[var] = line

    return protections


def _check_read_of_undefined(
    src: bytes, _tree, path: Path, index: NodeIndex, ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-024 — Read of a local variable that may not have been
    SET on every path from the label entry.

    Forward MUST-analysis (definite assignment) over the per-label
    CFG. A variable V is reported at use site U iff V is not in the
    definitely-defined set entering U's block AND not defined by an
    earlier argument of the same command.

    By-reference parameters in ``DO``/``JOB`` calls (``D LBL(.X)``)
    are treated as DEFs — the callee may initialize the variable.

    Dedup: one diagnostic per (label, variable) — long runs of the
    same uninitialized read collapse to one finding to keep signal
    high.

    VistA Kernel auto-defined locals (``U`` / ``IO`` / ``DT`` /
    ``DUZ`` / ``%UCI`` etc.) are excluded from reporting when the
    config opts in via ``[lint.vista] kernel_locals = "default"`` or
    a custom list. The defaults live in
    :mod:`m_cli.lint._vista_kernel`. Without the opt-in the rule
    keeps its strict semantics — modern non-VA code shouldn't get
    a free pass on those names.

    Deliberate limitations (Phase 7+ follow-ups):

      - GOTO targets within the routine are over-approximated as exits;
        cross-label dataflow is out of scope for this slice.
      - FOR loops have no back-edge yet; the loop body is treated as
        straight-line and may under-report on a first-iteration read.
      - YDB device parameters (``OPEN file:(newversion)``) parse as
        local variables and may produce false positives on I/O code.
    """
    from m_cli.lint._vista_kernel import KERNEL_AUTO_DEFINED
    from m_cli.lint.flow import analyze, build_cfgs, formal_params
    from m_cli.lint.flow.vars import (
        argument_nodes,
        command_keyword,
        effects_of_argument,
        postcond_node,
        uses_in_subtree,
    )

    # VistA Kernel-locals allowlist. Only active when the project
    # opts in via [lint.vista] kernel_locals — default keeps strict.
    kernel_locals: frozenset[str] = frozenset()
    cfg_obj = ctx.config if ctx is not None else None
    if cfg_obj is not None:
        opt = cfg_obj.lint_vista_kernel_locals
        if opt == ("default",):
            kernel_locals = frozenset(KERNEL_AUTO_DEFINED)
        elif opt:
            kernel_locals = frozenset(opt)

    cfgs = build_cfgs(src, index)
    for cfg in cfgs:
        formals = tuple(formal_params(cfg.label_node, src))
        in_sets = analyze(cfg, src, formals=formals)
        reported: set[str] = set()
        # Map var-name → 1-based line at-or-after which the
        # ``IF $G(X)="" SET X=...`` (or ``$D``) test+default-set
        # idiom guarantees X is definitely defined for the rest of
        # the label. Strict-greater check (``use.line > line``)
        # avoids over-suppressing earlier same-line uses.
        protections = _find_test_default_set_protections(cfg, src)

        def _flag(use, reported=reported, label_name=cfg.label_name):
            if use.name in reported:
                return None
            if use.name in kernel_locals:
                return None
            if (
                use.name in protections
                and use.line > protections[use.name]
            ):
                return None
            reported.add(use.name)
            return Diagnostic(
                rule_id="M-MOD-024",
                severity=Severity.ERROR,
                message=(
                    f"Local '{use.name}' may be read before being "
                    f"definitely defined on every path from {label_name}"
                ),
                path=path,
                line=use.line,
                column=use.column,
                column_end=use.column + len(use.name),
            )

        for block in cfg.blocks:
            if block.kind != "command":
                continue
            cmd = block.command
            in_set = in_sets[block.id]
            running: set[str] = set(in_set)
            kw = command_keyword(cmd, src)

            pc = postcond_node(cmd)
            if pc is not None:
                for use in uses_in_subtree(pc, src):
                    if use.name in running:
                        continue
                    d = _flag(use)
                    if d is not None:
                        yield d

            for arg in argument_nodes(cmd):
                arg_effects = effects_of_argument(arg, src, kw)
                for use in arg_effects.uses:
                    if use.name in running:
                        continue
                    d = _flag(use)
                    if d is not None:
                        yield d
                running |= arg_effects.defs
                if arg_effects.kills_all:
                    running = set()
                else:
                    running -= arg_effects.kills


register(
    Rule(
        id="M-MOD-024",
        severity=Severity.ERROR,
        category=Category.BUG,
        title="Read of local variable before definite assignment",
        tags=("modern",),
        check=_check_read_of_undefined,
        needs_context=True,
        replaces=(),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-025 — LOCK leak across exit paths
# ---------------------------------------------------------------------------


def _check_lock_leak_path_sensitive(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-025 — At least one path from label entry to exit leaves
    a LOCK held.

    Path-sensitive graduation of M-MOD-011: a forward MAY-analysis
    (union meet) computes the set of LOCK targets that are held on
    at least one path entering the synthetic exit block. Any name in
    that set is a real leak — there's a sequence of branches that
    reaches the QUIT (or end-of-label) without a matching release.

    Reports one diagnostic per (label, leaked variable). The
    diagnostic anchors on the label header so the leak is obvious in
    an editor's outline; the message names the leaked variable(s).
    """
    from m_cli.lint.flow import build_cfgs
    from m_cli.lint.flow.lock_state import held_at_exit

    cfgs = build_cfgs(src, index)
    for cfg in cfgs:
        held = held_at_exit(cfg, src)
        if not held:
            continue
        label = cfg.label_node
        for name in sorted(held):
            yield Diagnostic(
                rule_id="M-MOD-025",
                severity=Severity.ERROR,
                message=(
                    f"LOCK on '{name}' may be held when {cfg.label_name} "
                    "exits — release on every path"
                ),
                path=path,
                line=label.start_point[0] + 1,
                column=label.start_point[1] + 1,
                column_end=label.end_point[1] + 1,
            )


register(
    Rule(
        id="M-MOD-025",
        severity=Severity.ERROR,
        category=Category.CONCURRENCY,
        title="LOCK leak across exit paths (path-sensitive)",
        tags=("modern",),
        check=_check_lock_leak_path_sensitive,
        needs_context=True,
        replaces=("M-MOD-011",),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-026 — TSTART leak across exit paths
# ---------------------------------------------------------------------------


def _check_transaction_leak_path_sensitive(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-026 — At least one path from label entry to exit leaves
    a transaction open.

    Path-sensitive graduation of M-MOD-012's intra-label balance
    check. A forward MAY-analysis (max meet) computes the worst-case
    transaction nesting depth on any path entering the synthetic
    exit block. Non-zero depth means at least one path forgets to
    close the transaction.
    """
    from m_cli.lint.flow import build_cfgs
    from m_cli.lint.flow.transaction_state import depth_at_exit

    cfgs = build_cfgs(src, index)
    for cfg in cfgs:
        depth = depth_at_exit(cfg, src)
        if depth <= 0:
            continue
        label = cfg.label_node
        yield Diagnostic(
            rule_id="M-MOD-026",
            severity=Severity.ERROR,
            message=(
                f"Transaction may be open when {cfg.label_name} exits "
                f"(max depth {depth}) — TCOMMIT/TROLLBACK on every path"
            ),
            path=path,
            line=label.start_point[0] + 1,
            column=label.start_point[1] + 1,
            column_end=label.end_point[1] + 1,
        )


register(
    Rule(
        id="M-MOD-026",
        severity=Severity.ERROR,
        category=Category.CONCURRENCY,
        title="TSTART leak across exit paths (path-sensitive)",
        tags=("modern",),
        check=_check_transaction_leak_path_sensitive,
        needs_context=True,
        replaces=("M-MOD-012",),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-027 — $ETRAP leak across exit paths (path-sensitive)
# ---------------------------------------------------------------------------


def _check_etrap_leak_path_sensitive(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-027 — ``SET $ETRAP=...`` not preceded by ``NEW $ETRAP``
    on every path.

    Path-sensitive graduation of M-MOD-013. For each ``SET $ETRAP``
    (or its abbreviation ``SET $ET``), the analyzer asks: was
    ``NEW $ETRAP`` executed on every path from the label entry to
    this block? If not, the new handler persists past label exit
    into whatever the caller was running with — almost always a bug.
    """
    from m_cli.lint.flow import build_cfgs
    from m_cli.lint.flow.etrap_state import analyze_etrap_protection
    from m_cli.lint.flow.vars import argument_nodes, command_keyword

    _SET_KW = frozenset({"S", "SET"})
    _ETRAP_NAMES = frozenset({"$ETRAP", "$ET"})

    def _set_targets_etrap(cmd) -> bool:
        if command_keyword(cmd, src) not in _SET_KW:
            return False
        for arg in argument_nodes(cmd):
            for c in arg.children:
                if c.type != "binary_expression":
                    continue
                # First child of binary_expression is the LHS.
                lhs = c.children[0] if c.children else None
                if lhs is None:
                    continue
                if lhs.type == "special_variable":
                    name = src[lhs.start_byte : lhs.end_byte].decode(
                        "latin-1", errors="replace"
                    ).upper()
                    if name in _ETRAP_NAMES:
                        return True
        return False

    cfgs = build_cfgs(src, index)
    for cfg in cfgs:
        protections = analyze_etrap_protection(cfg, src)
        for block in cfg.blocks:
            if block.kind != "command":
                continue
            cmd = block.command
            if cmd is None or not _set_targets_etrap(cmd):
                continue
            if protections[block.id]:
                continue
            yield Diagnostic(
                rule_id="M-MOD-027",
                severity=Severity.ERROR,
                message=(
                    f"SET $ETRAP without preceding NEW $ETRAP on every "
                    f"path from {cfg.label_name} — handler escapes the label"
                ),
                path=path,
                line=block.line,
                column=cmd.start_point[1] + 1,
                column_end=cmd.end_point[1] + 1,
            )


register(
    Rule(
        id="M-MOD-027",
        severity=Severity.ERROR,
        category=Category.BUG,
        title="$ETRAP leak across exit paths (path-sensitive)",
        tags=("modern",),
        check=_check_etrap_leak_path_sensitive,
        needs_context=True,
        replaces=("M-MOD-013",),
    )
)


# ---------------------------------------------------------------------------
# M-MOD-017 — Stale $TEST read
# ---------------------------------------------------------------------------


def _check_dollar_test_stale(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-017 — Reading ``$TEST`` without a $T-setting command on
    every prior path.

    Rounds out Phase 7. The last of the originally-deferred Phase 7
    rules — needs forward MUST analysis ("has a $T-setter run on
    every path?") which became available with the flow infrastructure.

    A $T-read at block B is flagged when ``flow.dollar_test.analyze_test_freshness``
    reports ``in_state[B] is False`` — there's at least one path
    from label entry to B where no setter ran, so the value of
    $TEST is whatever was left in the process from before this
    label was entered (almost certainly stale).

    Reports one diagnostic per (label, $TEST-read site) — many
    consecutive stale reads in a row would be over-noisy without
    the dedup.
    """
    from m_cli.lint.flow import build_cfgs
    from m_cli.lint.flow.dollar_test import analyze_test_freshness

    _DOLLAR_TEST_NAMES = frozenset({"$TEST", "$T"})

    def _walk_test_reads(node):
        """Yield every $TEST / $T special_variable node in the subtree."""
        if node.type == "special_variable":
            text = src[node.start_byte : node.end_byte].decode(
                "latin-1", errors="replace"
            ).upper()
            if text in _DOLLAR_TEST_NAMES:
                yield node
            return
        for c in node.children:
            yield from _walk_test_reads(c)

    cfgs = build_cfgs(src, index)
    for cfg in cfgs:
        freshness = analyze_test_freshness(cfg, src)
        reported_lines: set[int] = set()
        for block in cfg.blocks:
            if block.kind != "command":
                continue
            cmd = block.command
            if cmd is None:
                continue
            if freshness[block.id]:
                continue
            for tnode in _walk_test_reads(cmd):
                line = tnode.start_point[0] + 1
                if line in reported_lines:
                    continue
                reported_lines.add(line)
                yield Diagnostic(
                    rule_id="M-MOD-017",
                    severity=Severity.WARNING,
                    message=(
                        f"$TEST read in {cfg.label_name} without a "
                        "$T-setting command on every prior path — "
                        "value may be stale from a much earlier command"
                    ),
                    path=path,
                    line=line,
                    column=tnode.start_point[1] + 1,
                    column_end=tnode.end_point[1] + 1,
                )


register(
    Rule(
        id="M-MOD-017",
        severity=Severity.WARNING,
        category=Category.BUG,
        title="$TEST read without preceding $T-setter (stale read)",
        tags=("modern",),
        check=_check_dollar_test_stale,
        needs_context=True,
        replaces=(),
    )
)


# ===========================================================================
# Phase 9 — Taint analysis MVP (M-MOD-036)
# ===========================================================================
#
# The differentiating security feature of m-cli's lint suite. M's
# indirection (@expr, S @x=..., D @routine) makes injection lethal:
# any tainted value reaching such a sink is a remote-code-execution
# vector. M-MOD-036 reads the per-label taint state from
# m_cli.lint.flow.taint and flags any indirection or XECUTE site
# whose argument expression contains a tainted local.


# ---------------------------------------------------------------------------
# M-MOD-036 — Untrusted data flows into an indirection sink
# ---------------------------------------------------------------------------


def _check_taint_to_indirection(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-MOD-036 — A tainted local variable reaches an indirection
    or XECUTE sink.

    Sources (this MVP, hardcoded — config in a follow-up):
      * ``READ X`` taints X
      * Public-label formal parameters are tainted at entry

    Sinks:
      * Any ``indirection`` AST node (``@expr`` in any context)
      * ``XECUTE`` command's argument

    Sanitizers:
      * ``$L`` / ``$LENGTH`` / ``$A`` / ``$ASCII`` — output is a
        number; treated as clean regardless of input taint

    Reports one diagnostic per (label, tainted variable) pair —
    long fan-outs of the same tainted value into many sinks
    collapse to one finding.
    """
    from m_cli.lint.flow import build_cfgs
    from m_cli.lint.flow.taint import (
        TaintConfig,
        analyze_taint,
        expression_taints,
    )
    from m_cli.lint.flow.vars import (
        argument_nodes,
        command_keyword,
    )

    # Build TaintConfig from [lint.taint] config (if any). Defaults
    # apply when the user hasn't set a knob; explicit user values
    # always win.
    user_cfg = _ctx.config if _ctx is not None else None
    formals_tainted = (
        user_cfg.lint_taint_formals_tainted
        if user_cfg is not None and user_cfg.lint_taint_formals_tainted is not None
        else True
    )
    default_sanitizers = TaintConfig().sanitizers
    extra = (
        frozenset(user_cfg.lint_taint_extra_sanitizers)
        if user_cfg is not None
        else frozenset()
    )
    config = TaintConfig(
        formals_tainted=formals_tainted,
        sanitizers=default_sanitizers | extra,
    )
    sanitizers = config.sanitizers

    def _walk_indirections(node):
        """Yield every ``indirection`` node in the subtree (so we
        find ``@expr`` whether it appears at the top of a command,
        inside an expression, or inside a subscript)."""
        if node.type == "indirection":
            yield node
            return
        for c in node.children:
            yield from _walk_indirections(c)

    cfgs = build_cfgs(src, index)
    for cfg in cfgs:
        taint_sets = analyze_taint(cfg, src, config=config)
        reported_vars: set[str] = set()

        def _flag_for_subtree(
            subtree,
            in_tainted,
            sink_kind,
            anchor_node,
            reported_vars=reported_vars,
            label_name=cfg.label_name,
        ):
            """If ``subtree`` references a tainted var, yield a
            diagnostic naming the first such var. Returns the
            diagnostic (or None) — caller handles the yield."""
            if not expression_taints(
                subtree, src, in_tainted, sanitizers
            ):
                return None
            # Find the first tainted var name in the subtree (so the
            # diagnostic message can name it concretely).
            tainted_name = _first_tainted_name(
                subtree, src, in_tainted, sanitizers
            )
            if tainted_name is None or tainted_name in reported_vars:
                return None
            reported_vars.add(tainted_name)
            return Diagnostic(
                rule_id="M-MOD-036",
                severity=Severity.ERROR,
                message=(
                    f"Tainted local '{tainted_name}' flows into "
                    f"{sink_kind} in {label_name} — possible "
                    "code/SQL/path injection"
                ),
                path=path,
                line=anchor_node.start_point[0] + 1,
                column=anchor_node.start_point[1] + 1,
                column_end=anchor_node.end_point[1] + 1,
            )

        for block in cfg.blocks:
            if block.kind != "command":
                continue
            cmd = block.command
            if cmd is None:
                continue
            in_tainted = taint_sets[block.id]
            kw = command_keyword(cmd, src).upper()

            # Sink 1: every ``indirection`` node anywhere inside
            # the command (handles ``D @X``, ``S @X=v``, ``S Y=@X``,
            # ``S Y=A_@X``, etc. uniformly).
            for indir in _walk_indirections(cmd):
                d = _flag_for_subtree(
                    indir, in_tainted, "indirection (@…)", indir
                )
                if d is not None:
                    yield d

            # Sink 2: ``XECUTE`` argument — executes M code.
            if kw in ("X", "XECUTE"):
                for arg in argument_nodes(cmd):
                    d = _flag_for_subtree(
                        arg, in_tainted, "XECUTE argument", arg
                    )
                    if d is not None:
                        yield d


def _first_tainted_name(
    node, src: bytes, tainted, sanitizers
) -> str | None:
    """Return the first ``local_variable`` name in ``node``'s
    subtree that's in ``tainted``, walking the same way as
    :func:`expression_taints` (skipping sanitizer subtrees)."""
    from m_cli.lint.flow.taint import _identifier_text, _intrinsic_keyword

    found: list[str | None] = [None]

    def visit(n) -> None:
        if found[0] is not None:
            return
        if n.type == "global_variable":
            return
        if n.type == "function_call":
            kw = _intrinsic_keyword(n, src)
            if kw in sanitizers:
                return
            for c in n.children:
                visit(c)
            return
        if n.type == "local_variable":
            name = _identifier_text(n, src)
            if name in tainted:
                found[0] = name
                return
            for c in n.children:
                if c.type == "subscripts":
                    visit(c)
            return
        for c in n.children:
            visit(c)

    visit(node)
    return found[0]


register(
    Rule(
        id="M-MOD-036",
        severity=Severity.ERROR,
        category=Category.SECURITY,
        title="Untrusted data flows into an indirection sink",
        tags=("modern",),
        check=_check_taint_to_indirection,
        needs_context=True,
        replaces=(),
    )
)
