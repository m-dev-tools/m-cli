"""Rule definitions for `m lint`.

Each rule is a callable that takes the source bytes, the parsed tree,
the file path, and a per-file ``NodeIndex``, and yields zero or more
``Diagnostic`` instances.

Rules are organised by tag (``xindex``, ``sac``, …). The ``--rules``
toggle filters which tag(s) run.

XINDEX coverage policy
======================

42 of XINDEX's 66 rules are registered (37 single-file + 3 cross-routine
[M-XINDX-007/008/049] + 2 control-flow [M-XINDX-009/051]). The remaining 24 fall into
four buckets — recorded here so future contributors don't re-litigate
each one:

**Permanently skipped — redundant with the parser ERROR catch-all
(``M-XINDX-021`` already surfaces these as fatal diagnostics).**
XINDEX was a text-based scanner; tree-sitter-m gives us proper
structural validation, so these no longer need their own rules:

  1, 3      undefined command / undefined function — typo'd
            keywords show up as command_keyword + ERROR child
  5, 6      unmatched parens / unmatched quotes
  8, 10     FOR without ``=`` / unrecognized SET argument
  11, 12    invalid local / global variable name (parser only emits
            ``local_variable`` / ``global_variable`` nodes for valid
            identifiers; anything else is ERROR)
  37        invalid label
  40        space where a command should be
  53, 59    bad numeric literal / WRITE syntax
  51        block-structure mismatch (already mapped to M-XINDX-021)

**Deferred — out of scope for single-file lint.** These need a
workspace index of all routines, a call graph, or data-flow tracking;
none currently exist. Re-evaluate when a workspace-wide analysis
phase is funded:

  39        kill of protected variable (needs scope tracking)
  43        wrong argument count to function (needs signatures)
  52        cross-routine reference doesn't exist (needs workspace index)
  55        violates VA programming standards (catch-all — too vague
            without explicit mapping to specific SAC sections)
  63        GO/DO mismatch from block structure (needs control-flow
            analysis)

**Deferred — niche, low value-per-rule.** Each is doable on a single
file but the per-rule design and false-positive-tuning cost is high
relative to the editor-UX payoff. Pick these up if they surface as
real complaints from `m lint` users in the wild rather than working
through them mechanically:

  16        error in pattern code (M's ``?`` pattern grammar)
  38        call-to-this format-specific (XINDEX-internal classifier)
  46, 48, 49  postconditional / argument quirks per command

**Permanently skipped — engine-specific.**

  64, 66    Caché / ICR-specific rules (m-cli's source-level tools are
            engine-neutral; runtime tools target YottaDB)

A higher-leverage future direction than chasing the XINDEX edge cases:
refining ``M-XINDX-021`` to emit *specific* parse-error messages by
inspecting what comes before each ERROR node. ``FOOBAR`` parsing as
``FO`` (FOR abbreviation) + ERROR ``OBAR`` could become
"Unknown command keyword 'FOOBAR'"; ``$NOSUCH(...)`` parsing as
``$N`` + ERROR ``OSUCH(...)`` could become "Unknown intrinsic
function '$NOSUCH'". Best done after the LSP ships so the win lands
in-editor.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from m_cli.lint._index import NodeIndex
from m_cli.lint._keywords import standard_commands, standard_functions, standard_isvs
from m_cli.lint.diagnostic import Diagnostic, Severity

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Rule metadata + registry
# ---------------------------------------------------------------------------

# Standard rule signature: (src, tree, path, index) -> diags. Cross-
# routine rules (Rule.needs_workspace=True) take a 5th arg, a
# ``WorkspaceIndex``. The runner dispatches on ``needs_workspace``.
# We use ``Callable[..., ...]`` so both shapes type-check; the runtime
# dispatch is the source of truth.
RuleFn = Callable[..., Iterator[Diagnostic]]


@dataclass(frozen=True)
class Rule:
    id: str
    severity: Severity
    title: str
    tags: tuple[str, ...]
    check: RuleFn
    # Optional id of an `m fmt` rule that auto-fixes this diagnostic. The
    # LSP wrapper exposes this as a Quick Fix code action; CI tools can
    # surface it as "auto-fixable". `None` when no auto-fix exists.
    fixer_id: str | None = None
    # When True, ``check`` takes a 5th positional arg: a
    # ``WorkspaceIndex`` for cross-routine rules (M-XINDX-007 et al.).
    # The runner passes it through; rules that don't need workspace
    # context leave this False (the default) and use the standard
    # 4-arg signature.
    needs_workspace: bool = False


_REGISTRY: dict[str, Rule] = {}


def register(rule: Rule) -> Rule:
    if rule.id in _REGISTRY:
        raise ValueError(f"duplicate rule id: {rule.id}")
    _REGISTRY[rule.id] = rule
    return rule


def all_rules() -> list[Rule]:
    return sorted(_REGISTRY.values(), key=lambda r: r.id)


def rules_by_tag(tag: str) -> list[Rule]:
    return [r for r in _REGISTRY.values() if tag in r.tags]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_line(b: bytes) -> str:
    """Decode a line for human-readable output. M source is mostly ASCII;
    we pass through unknown bytes via latin-1."""
    return b.decode("latin-1", errors="replace")


def _walk(node) -> Iterator:
    """Pre-order tree walk."""
    yield node
    for child in node.children:
        yield from _walk(child)


# ---------------------------------------------------------------------------
# Text-based rules (don't need the AST)
# ---------------------------------------------------------------------------


def _check_trailing_blanks(
    src: bytes, _tree, path: Path, _index: NodeIndex
) -> Iterator[Diagnostic]:
    """M-XINDX-013 — Blank(s) at end of line."""
    for i, raw in enumerate(src.splitlines(), start=1):
        if raw.endswith((b" ", b"\t")):
            stripped = raw.rstrip(b" \t")
            yield Diagnostic(
                rule_id="M-XINDX-013",
                severity=Severity.WARNING,
                message="Blank(s) at end of line",
                path=path,
                line=i,
                column=len(stripped) + 1,
                column_end=len(raw) + 1,
                line_text=_decode_line(raw),
            )


register(
    Rule(
        id="M-XINDX-013",
        severity=Severity.WARNING,
        title="Blank(s) at end of line",
        tags=("xindex",),
        check=_check_trailing_blanks,
        fixer_id="trim-trailing-whitespace",
    )
)


def _check_control_chars(src: bytes, _tree, path: Path, _index: NodeIndex) -> Iterator[Diagnostic]:
    """M-XINDX-018 — Line contains a CONTROL (non-graphic) character."""
    for i, raw in enumerate(src.splitlines(), start=1):
        for col, byte in enumerate(raw, start=1):
            # Allow tab (9). Flag other controls (0-8, 11-31) and DEL (127).
            if (byte < 32 and byte != 9) or byte == 127:
                yield Diagnostic(
                    rule_id="M-XINDX-018",
                    severity=Severity.WARNING,
                    message=f"Line contains a CONTROL (non-graphic) character (byte 0x{byte:02x})",
                    path=path,
                    line=i,
                    column=col,
                    column_end=col + 1,
                    line_text=_decode_line(raw),
                )
                break  # one diagnostic per line is enough


register(
    Rule(
        id="M-XINDX-018",
        severity=Severity.WARNING,
        title="Line contains a CONTROL (non-graphic) character",
        tags=("xindex",),
        check=_check_control_chars,
    )
)


def _check_line_length(src: bytes, _tree, path: Path, _index: NodeIndex) -> Iterator[Diagnostic]:
    """M-XINDX-019 — Line is longer than 245 bytes (SACC limit)."""
    for i, raw in enumerate(src.splitlines(), start=1):
        if len(raw) > 245:
            yield Diagnostic(
                rule_id="M-XINDX-019",
                severity=Severity.STANDARD,
                message=f"Line is longer than 245 bytes ({len(raw)} bytes)",
                path=path,
                line=i,
                column=246,
                column_end=len(raw) + 1,
                line_text=_decode_line(raw[:80] + b"..."),
            )


register(
    Rule(
        id="M-XINDX-019",
        severity=Severity.STANDARD,
        title="Line is longer than 245 bytes",
        tags=("xindex",),
        check=_check_line_length,
    )
)


def _check_null_line(src: bytes, _tree, path: Path, _index: NodeIndex) -> Iterator[Diagnostic]:
    """M-XINDX-042 — Null line (no commands or comment).

    A line with only whitespace and a newline contributes nothing.
    First-and-only blank line at end of file is allowed.
    """
    lines = src.splitlines()
    for i, raw in enumerate(lines, start=1):
        if raw.strip() == b"" and i < len(lines):  # blank trailing line is fine
            yield Diagnostic(
                rule_id="M-XINDX-042",
                severity=Severity.WARNING,
                message="Null line (no commands or comment)",
                path=path,
                line=i,
                column=1,
                line_text="",
            )


register(
    Rule(
        id="M-XINDX-042",
        severity=Severity.WARNING,
        title="Null line (no commands or comment)",
        tags=("xindex",),
        check=_check_null_line,
    )
)


# ---------------------------------------------------------------------------
# AST-based rules
# ---------------------------------------------------------------------------


def _node_line_col(node, src: bytes) -> tuple[int, int]:
    """Return (1-based line, 1-based column) of a tree-sitter node."""
    return node.start_point[0] + 1, node.start_point[1] + 1


def _node_text(node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("latin-1", errors="replace")


def _line_text(src: bytes, line_num: int) -> str:
    """Get the (1-indexed) line as decoded text."""
    lines = src.splitlines()
    if 1 <= line_num <= len(lines):
        return _decode_line(lines[line_num - 1])
    return ""


def _collect_labels(index: NodeIndex, src: bytes) -> dict[str, list[tuple[int, int]]]:
    """Map label name → list of (line, col) where it is defined."""
    labels: dict[str, list[tuple[int, int]]] = {}
    for node in index.of("label"):
        name = _node_text(node, src)
        line, col = _node_line_col(node, src)
        labels.setdefault(name, []).append((line, col))
    return labels


def _check_first_label(src: bytes, _tree, path: Path, index: NodeIndex) -> Iterator[Diagnostic]:
    """M-XINDX-017 — First line label NOT routine name.

    The routine's first label must equal the file basename (without `.m`).
    Excludes routines starting with `%` (XINDEX exclusion).
    """
    for node in index.of("label"):
        first_label = _node_text(node, src)
        expected = path.stem
        if expected.startswith("%"):
            return
        if first_label != expected:
            line, col = _node_line_col(node, src)
            yield Diagnostic(
                rule_id="M-XINDX-017",
                severity=Severity.WARNING,
                message=(
                    f"First line label ('{first_label}') does not match routine name ('{expected}')"
                ),
                path=path,
                line=line,
                column=col,
                column_end=col + len(first_label),
                line_text=_line_text(src, line),
                extra={"first_label": first_label, "expected": expected},
            )
        return  # only check the first label


register(
    Rule(
        id="M-XINDX-017",
        severity=Severity.WARNING,
        title="First line label NOT routine name",
        tags=("xindex",),
        check=_check_first_label,
    )
)


def _check_duplicate_labels(
    src: bytes, _tree, path: Path, index: NodeIndex
) -> Iterator[Diagnostic]:
    """M-XINDX-015 — Duplicate label."""
    labels = _collect_labels(index, src)
    for name, occurrences in labels.items():
        if len(occurrences) > 1:
            for line, col in occurrences[1:]:  # skip first definition
                yield Diagnostic(
                    rule_id="M-XINDX-015",
                    severity=Severity.WARNING,
                    message=(
                        f"Duplicate label: '{name}' (first defined at line {occurrences[0][0]})"
                    ),
                    path=path,
                    line=line,
                    column=col,
                    column_end=col + len(name),
                    line_text=_line_text(src, line),
                    extra={"label": name, "first_line": occurrences[0][0]},
                )


register(
    Rule(
        id="M-XINDX-015",
        severity=Severity.WARNING,
        title="Duplicate label",
        tags=("xindex",),
        check=_check_duplicate_labels,
    )
)


def _check_missing_label_call(
    src: bytes, _tree, path: Path, index: NodeIndex
) -> Iterator[Diagnostic]:
    """M-XINDX-014 — Call to missing label '|' in this routine.

    Looks at:
      - `do <label>` / `do <label>(args)` / `goto <label>` / `job <label>`
        where the argument is a bare local-variable-shaped reference
        (no `^routine`) — these are in-routine label calls.
      - `do <label>^<routine>` / `$$<func>^<routine>` where the routine
        equals this file's routine name.
      - `$$<func>` / `$$<func>(args)` — extrinsic function calls in the
        current routine.

    Cross-routine calls (`label^OTHER`) are out of scope: XINDEX's full
    check resolves them via the routine database, which we don't have
    at lint time. We only flag in-routine calls.
    """
    labels = _collect_labels(index, src)
    label_set = set(labels)
    this_routine = path.stem

    for node in index.of("command"):
        yield from _check_command_label_calls(node, src, label_set, this_routine, path)
    for node in index.of("extrinsic_function"):
        yield from _check_extrinsic_label_call(node, src, label_set, this_routine, path)


def _check_command_label_calls(
    cmd_node, src: bytes, label_set: set[str], this_routine: str, path: Path
) -> Iterator[Diagnostic]:
    """For `do`/`goto`/`job` commands, walk arguments looking for label refs."""
    kw_node = next((c for c in cmd_node.children if c.type == "command_keyword"), None)
    if kw_node is None:
        return
    kw = _node_text(kw_node, src).upper()
    if kw not in ("D", "DO", "G", "GOTO", "J", "JOB"):
        return
    arg_list = next((c for c in cmd_node.children if c.type == "argument_list"), None)
    if arg_list is None:
        return
    for arg in arg_list.children:
        if arg.type != "argument":
            continue
        yield from _label_call_from_arg(arg, src, label_set, this_routine, path)


def _label_call_from_arg(
    arg_node, src: bytes, label_set: set[str], this_routine: str, path: Path
) -> Iterator[Diagnostic]:
    """The argument's payload is the first child node (modulo punctuation)."""
    payload = next(
        (c for c in arg_node.children if c.type not in ("(", ")", ",")),
        None,
    )
    if payload is None:
        return

    if payload.type == "entry_reference":
        # `label^routine` form. Label can be `identifier` OR `number`
        # (numeric labels). Routine after `^` is always `identifier`.
        children = list(payload.children)
        caret_idx = next(
            (i for i, c in enumerate(children) if c.type == "^"),
            None,
        )
        if caret_idx is not None:
            # Cross-routine: check the routine name after ^
            if caret_idx + 1 < len(children):
                target_routine = _node_text(children[caret_idx + 1], src)
                if target_routine != this_routine:
                    return  # cross-routine call: out of scope
            # Label is the node before ^ (may be empty for `^routine`)
            if caret_idx == 0:
                return  # `^routine` form — no in-routine label to check
            label_node = children[caret_idx - 1]
        else:
            # No ^ — bare label call (rare under entry_reference)
            if not children:
                return
            label_node = children[0]
        # We only check named labels; numeric labels (like `do 5^foo` or
        # `do 5` in same routine) are out of scope for the in-routine
        # missing-label check until we add numeric-label tracking.
        if label_node.type != "identifier":
            return
        label_name = _node_text(label_node, src)
    elif payload.type == "variable":
        # Bare-label form: variable > local_variable > identifier
        local_var = next((c for c in payload.children if c.type == "local_variable"), None)
        if local_var is None:
            return
        label_node = next((c for c in local_var.children if c.type == "identifier"), None)
        if label_node is None:
            return
        label_name = _node_text(label_node, src)
    else:
        return

    if label_name not in label_set:
        line, col = _node_line_col(label_node, src)
        yield Diagnostic(
            rule_id="M-XINDX-014",
            severity=Severity.FATAL,
            message=f"Call to missing label '{label_name}' in this routine",
            path=path,
            line=line,
            column=col,
            column_end=col + len(label_name),
            line_text=_line_text(src, line),
            extra={"label": label_name},
        )


def _check_extrinsic_label_call(
    func_node, src: bytes, label_set: set[str], this_routine: str, path: Path
) -> Iterator[Diagnostic]:
    """`$$func` / `$$func^routine` extrinsic function calls."""
    ids = [c for c in func_node.children if c.type == "identifier"]
    has_caret = any(c.type == "^" for c in func_node.children)
    if len(ids) < 1:
        return
    label_node = ids[0]
    if has_caret and len(ids) >= 2:
        target_routine = _node_text(ids[1], src)
        if target_routine != this_routine:
            return  # cross-routine call
    label_name = _node_text(label_node, src)
    if label_name not in label_set:
        line, col = _node_line_col(label_node, src)
        yield Diagnostic(
            rule_id="M-XINDX-014",
            severity=Severity.FATAL,
            message=f"Call to missing label '{label_name}' in this routine",
            path=path,
            line=line,
            column=col,
            column_end=col + len(label_name),
            line_text=_line_text(src, line),
            extra={"label": label_name},
        )


register(
    Rule(
        id="M-XINDX-014",
        severity=Severity.FATAL,
        title="Call to missing label in this routine",
        tags=("xindex",),
        check=_check_missing_label_call,
    )
)


def _check_break_command(src: bytes, _tree, path: Path, index: NodeIndex) -> Iterator[Diagnostic]:
    """M-XINDX-025 — Break command used (BREAK is dev-only)."""
    for node in index.of("command_keyword"):
        kw = _node_text(node, src).upper()
        if kw in ("B", "BREAK"):
            line, col = _node_line_col(node, src)
            yield Diagnostic(
                rule_id="M-XINDX-025",
                severity=Severity.STANDARD,
                message="BREAK command used (debug-only; should not appear in production code)",
                path=path,
                line=line,
                column=col,
                column_end=col + len(kw),
                line_text=_line_text(src, line),
            )


register(
    Rule(
        id="M-XINDX-025",
        severity=Severity.STANDARD,
        title="BREAK command used",
        tags=("xindex",),
        check=_check_break_command,
    )
)


def _check_lowercase_command(
    src: bytes, _tree, path: Path, index: NodeIndex
) -> Iterator[Diagnostic]:
    """M-XINDX-047 — Lowercase command(s) used in line.

    XINDEX flags commands written in lowercase. Modern style (and the
    m-tools 'lowercase pythonic MUMPS' convention) actually *prefers*
    lowercase, so this rule is provided for XINDEX-parity but not
    enabled in modern profiles. It is still in the `xindex` tag.
    """
    for node in index.of("command_keyword"):
        kw = _node_text(node, src)
        # If keyword has any lowercase letters, flag it
        if any(c.islower() for c in kw):
            line, col = _node_line_col(node, src)
            yield Diagnostic(
                rule_id="M-XINDX-047",
                severity=Severity.STANDARD,
                message=(
                    f"Lowercase command used: '{kw}' "
                    f"(XINDEX style; modern profiles often allow this)"
                ),
                path=path,
                line=line,
                column=col,
                column_end=col + len(kw),
                line_text=_line_text(src, line),
                extra={"command": kw},
            )


register(
    Rule(
        id="M-XINDX-047",
        severity=Severity.STANDARD,
        title="Lowercase command(s) used in line",
        tags=("xindex",),
        check=_check_lowercase_command,
        fixer_id="uppercase-command-keywords",
    )
)


def _check_routine_size(src: bytes, _tree, path: Path, _index: NodeIndex) -> Iterator[Diagnostic]:
    """M-XINDX-035 — Routine exceeds SACC maximum size of 20000 bytes."""
    if len(src) > 20000:
        yield Diagnostic(
            rule_id="M-XINDX-035",
            severity=Severity.STANDARD,
            message=f"Routine exceeds SACC maximum size of 20000 bytes ({len(src)} bytes)",
            path=path,
            line=1,
            column=1,
            extra={"size_bytes": len(src)},
        )


register(
    Rule(
        id="M-XINDX-035",
        severity=Severity.STANDARD,
        title="Routine exceeds SACC maximum size of 20000 bytes",
        tags=("xindex",),
        check=_check_routine_size,
    )
)


def _check_second_line_sac(
    src: bytes, _tree, path: Path, _index: NodeIndex
) -> Iterator[Diagnostic]:
    """M-XINDX-044 — 2nd line of routine violates the SAC.

    SAC requires the second line in the form ` ;;version;package;...;date;build`.
    """
    lines = src.splitlines()
    if len(lines) < 2:
        return
    second = lines[1]
    # Must start with ` ;;` (one indent space, two semicolons)
    if not re.match(rb"^[ \t]*;;", second):
        yield Diagnostic(
            rule_id="M-XINDX-044",
            severity=Severity.STANDARD,
            message=(
                "2nd line of routine violates the SAC "
                "(must start with ';;version;package;...;date;build')"
            ),
            path=path,
            line=2,
            column=1,
            line_text=_decode_line(second),
        )


register(
    Rule(
        id="M-XINDX-044",
        severity=Severity.STANDARD,
        title="2nd line of routine violates the SAC",
        tags=("xindex",),
        check=_check_second_line_sac,
    )
)


# ---------------------------------------------------------------------------
# Helpers for command-keyword-based rules
# ---------------------------------------------------------------------------


def _commands(index: NodeIndex, src: bytes) -> Iterator[tuple]:
    """Yield (command_node, keyword_text_upper, kw_node) for every command."""
    for node in index.of("command"):
        kw_node = next((c for c in node.children if c.type == "command_keyword"), None)
        if kw_node is None:
            continue
        kw = _node_text(kw_node, src).upper()
        yield node, kw, kw_node


def _arg_list(cmd_node):
    """Return the argument_list child or None."""
    return next((c for c in cmd_node.children if c.type == "argument_list"), None)


def _arguments(cmd_node):
    """Yield argument children of a command, or nothing if no arg_list."""
    al = _arg_list(cmd_node)
    if al is None:
        return
    for c in al.children:
        if c.type == "argument":
            yield c


def _has_postconditional(cmd_node) -> bool:
    """Check if the command itself has a `:condition` postconditional."""
    return any(c.type == "command_postconditional" for c in cmd_node.children)


def _arg_has_timeout(arg_node) -> bool:
    """Check if argument has an `argument_postconditional` (`:timeout`)."""
    return any(c.type == "argument_postconditional" for c in arg_node.children)


def _payload(arg_node):
    """First non-trivial child of an argument node."""
    return next(
        (c for c in arg_node.children if c.type not in ("(", ")", ",")),
        None,
    )


# ---------------------------------------------------------------------------
# Additional XINDEX rules
# ---------------------------------------------------------------------------


# --- M-XINDX-020: VIEW command used --------------------------------------
def _check_view_command(src, _tree, path, index):
    for cmd, kw, kw_node in _commands(index, src):
        if kw in ("V", "VIEW"):
            line, col = _node_line_col(kw_node, src)
            yield Diagnostic(
                rule_id="M-XINDX-020",
                severity=Severity.STANDARD,
                message="VIEW command used (non-portable; vendor-specific)",
                path=path,
                line=line,
                column=col,
                column_end=col + len(kw),
                line_text=_line_text(src, line),
            )


register(
    Rule(
        id="M-XINDX-020",
        severity=Severity.STANDARD,
        title="VIEW command used",
        tags=("xindex",),
        check=_check_view_command,
    )
)


# --- M-XINDX-022: Exclusive Kill (`KILL (var,...)`) ----------------------
def _check_exclusive_kill(src, _tree, path, index):
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("K", "KILL"):
            continue
        for arg in _arguments(cmd):
            payload = _payload(arg)
            if payload is not None and payload.type == "set_target_list":
                line, col = _node_line_col(kw_node, src)
                yield Diagnostic(
                    rule_id="M-XINDX-022",
                    severity=Severity.STANDARD,
                    message="Exclusive KILL — KILL (var,…) is non-standard / dangerous",
                    path=path,
                    line=line,
                    column=col,
                    column_end=col + len(kw),
                    line_text=_line_text(src, line),
                )
                break


register(
    Rule(
        id="M-XINDX-022",
        severity=Severity.STANDARD,
        title="Exclusive Kill",
        tags=("xindex",),
        check=_check_exclusive_kill,
    )
)


# --- M-XINDX-023: Unargumented Kill --------------------------------------
def _check_unargumented_kill(src, _tree, path, index):
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("K", "KILL"):
            continue
        if _arg_list(cmd) is None:
            line, col = _node_line_col(kw_node, src)
            yield Diagnostic(
                rule_id="M-XINDX-023",
                severity=Severity.STANDARD,
                message="Unargumented KILL — kills all locals; almost never what is intended",
                path=path,
                line=line,
                column=col,
                column_end=col + len(kw),
                line_text=_line_text(src, line),
            )


register(
    Rule(
        id="M-XINDX-023",
        severity=Severity.STANDARD,
        title="Unargumented Kill",
        tags=("xindex",),
        check=_check_unargumented_kill,
    )
)


# --- M-XINDX-024: Kill of unsubscripted global ---------------------------
def _check_kill_unsubscripted_global(src, _tree, path, index):
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("K", "KILL"):
            continue
        for arg in _arguments(cmd):
            payload = _payload(arg)
            if payload is None or payload.type != "variable":
                continue
            gv = next((c for c in payload.children if c.type == "global_variable"), None)
            if gv is None:
                continue
            has_subs = any(c.type == "subscripts" for c in gv.children)
            if not has_subs:
                line, col = _node_line_col(gv, src)
                yield Diagnostic(
                    rule_id="M-XINDX-024",
                    severity=Severity.STANDARD,
                    message="Kill of an unsubscripted global (kills the entire global tree)",
                    path=path,
                    line=line,
                    column=col,
                    column_end=col + len(_node_text(gv, src)),
                    line_text=_line_text(src, line),
                )


register(
    Rule(
        id="M-XINDX-024",
        severity=Severity.STANDARD,
        title="Kill of an unsubscripted global",
        tags=("xindex",),
        check=_check_kill_unsubscripted_global,
    )
)


# --- M-XINDX-026: Exclusive or Unargumented NEW --------------------------
def _check_new_exclusive_or_unargumented(src, _tree, path, index):
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("N", "NEW"):
            continue
        al = _arg_list(cmd)
        line, col = _node_line_col(kw_node, src)
        if al is None:
            yield Diagnostic(
                rule_id="M-XINDX-026",
                severity=Severity.STANDARD,
                message="Unargumented NEW (news everything; non-standard intent)",
                path=path,
                line=line,
                column=col,
                column_end=col + len(kw),
                line_text=_line_text(src, line),
            )
            continue
        for arg in _arguments(cmd):
            payload = _payload(arg)
            if payload is not None and payload.type == "set_target_list":
                yield Diagnostic(
                    rule_id="M-XINDX-026",
                    severity=Severity.STANDARD,
                    message="Exclusive NEW — NEW (var,…) is non-standard",
                    path=path,
                    line=line,
                    column=col,
                    column_end=col + len(kw),
                    line_text=_line_text(src, line),
                )
                break


register(
    Rule(
        id="M-XINDX-026",
        severity=Severity.STANDARD,
        title="Exclusive or Unargumented NEW command",
        tags=("xindex",),
        check=_check_new_exclusive_or_unargumented,
    )
)


# --- M-XINDX-027: $VIEW function used ------------------------------------
def _check_dollar_view(src, _tree, path, index):
    for node in index.of("intrinsic_function"):
        ids = [c for c in node.children if c.type == "identifier"]
        if ids:
            fname = "$" + _node_text(ids[0], src).upper()
            if fname in ("$V", "$VIEW"):
                line, col = _node_line_col(node, src)
                yield Diagnostic(
                    rule_id="M-XINDX-027",
                    severity=Severity.STANDARD,
                    message="$VIEW function used (non-portable; vendor-specific)",
                    path=path,
                    line=line,
                    column=col,
                    column_end=col + len(fname),
                    line_text=_line_text(src, line),
                )


register(
    Rule(
        id="M-XINDX-027",
        severity=Severity.STANDARD,
        title="$View function used",
        tags=("xindex",),
        check=_check_dollar_view,
    )
)


# --- M-XINDX-030: LABEL+OFFSET syntax ------------------------------------
def _check_label_offset(src, _tree, path, index):
    """`do TAG+1` or `goto TAG+5` — depending on offset is fragile."""
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("D", "DO", "G", "GOTO", "J", "JOB"):
            continue
        for arg in _arguments(cmd):
            payload = _payload(arg)
            if payload is None:
                continue
            # Walk for binary_expression where operator is + and lhs is a label-shaped variable
            for sub in _walk(payload):
                if sub.type != "binary_expression":
                    continue
                op = next((c for c in sub.children if c.type == "operator"), None)
                if op is None:
                    continue
                op_text = _node_text(op, src)
                if op_text != "+":
                    continue
                # Confirm this is in a DO/GOTO/JOB argument context (already filtered above).
                line, col = _node_line_col(sub, src)
                yield Diagnostic(
                    rule_id="M-XINDX-030",
                    severity=Severity.STANDARD,
                    message="LABEL+OFFSET syntax — offset-dependent calls are fragile",
                    path=path,
                    line=line,
                    column=col,
                    column_end=col + len(_node_text(sub, src)),
                    line_text=_line_text(src, line),
                )
                break  # one diagnostic per arg


register(
    Rule(
        id="M-XINDX-030",
        severity=Severity.STANDARD,
        title="LABEL+OFFSET syntax",
        tags=("xindex",),
        check=_check_label_offset,
    )
)


# --- M-XINDX-032: HALT command should be invoked through G ^XUSCLEAN -----
def _check_halt_command(src, _tree, path, index):
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("H", "HALT"):
            continue
        # Distinguish HALT (no args) from HANG (the same H abbreviation
        # rule). We treat unargumented H/HALT as HALT; H with an arg is HANG.
        if _arg_list(cmd) is None:
            line, col = _node_line_col(kw_node, src)
            yield Diagnostic(
                rule_id="M-XINDX-032",
                severity=Severity.STANDARD,
                message="HALT should be invoked through G ^XUSCLEAN",
                path=path,
                line=line,
                column=col,
                column_end=col + len(kw),
                line_text=_line_text(src, line),
            )


register(
    Rule(
        id="M-XINDX-032",
        severity=Severity.STANDARD,
        title="HALT should be invoked through G ^XUSCLEAN",
        tags=("xindex",),
        check=_check_halt_command,
    )
)


# --- M-XINDX-033: READ command without timeout ---------------------------
def _check_read_no_timeout(src, _tree, path, index):
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("R", "READ"):
            continue
        for arg in _arguments(cmd):
            if not _arg_has_timeout(arg):
                line, col = _node_line_col(kw_node, src)
                yield Diagnostic(
                    rule_id="M-XINDX-033",
                    severity=Severity.STANDARD,
                    message="READ command does not have a :timeout (will block indefinitely)",
                    path=path,
                    line=line,
                    column=col,
                    column_end=col + len(kw),
                    line_text=_line_text(src, line),
                )
                break  # one per command


register(
    Rule(
        id="M-XINDX-033",
        severity=Severity.STANDARD,
        title="READ command does not have a timeout",
        tags=("xindex",),
        check=_check_read_no_timeout,
    )
)


# --- M-XINDX-034: OPEN command should be invoked through ^%ZIS ----------
def _check_open_command(src, _tree, path, index):
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("O", "OPEN"):
            continue
        line, col = _node_line_col(kw_node, src)
        yield Diagnostic(
            rule_id="M-XINDX-034",
            severity=Severity.STANDARD,
            message="OPEN should be invoked through ^%ZIS (portability across devices)",
            path=path,
            line=line,
            column=col,
            column_end=col + len(kw),
            line_text=_line_text(src, line),
        )


register(
    Rule(
        id="M-XINDX-034",
        severity=Severity.STANDARD,
        title="OPEN should be invoked through ^%ZIS",
        tags=("xindex",),
        check=_check_open_command,
    )
)


# --- M-XINDX-029: CLOSE should be invoked through D ^%ZISC ---------------
def _check_close_command(src, _tree, path, index):
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("C", "CLOSE"):
            continue
        line, col = _node_line_col(kw_node, src)
        yield Diagnostic(
            rule_id="M-XINDX-029",
            severity=Severity.STANDARD,
            message="CLOSE should be invoked through D ^%ZISC",
            path=path,
            line=line,
            column=col,
            column_end=col + len(kw),
            line_text=_line_text(src, line),
        )


register(
    Rule(
        id="M-XINDX-029",
        severity=Severity.STANDARD,
        title="CLOSE should be invoked through D ^%ZISC",
        tags=("xindex",),
        check=_check_close_command,
    )
)


# --- M-XINDX-036: Should use TASKMAN instead of JOB ----------------------
def _check_job_command(src, _tree, path, index):
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("J", "JOB"):
            continue
        line, col = _node_line_col(kw_node, src)
        yield Diagnostic(
            rule_id="M-XINDX-036",
            severity=Severity.STANDARD,
            message="Should use TASKMAN instead of JOB command",
            path=path,
            line=line,
            column=col,
            column_end=col + len(kw),
            line_text=_line_text(src, line),
        )


register(
    Rule(
        id="M-XINDX-036",
        severity=Severity.STANDARD,
        title="Should use TASKMAN instead of JOB",
        tags=("xindex",),
        check=_check_job_command,
    )
)


# --- M-XINDX-041: Star or pound READ used --------------------------------
def _check_star_pound_read(src, _tree, path, index):
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("R", "READ"):
            continue
        for arg in _arguments(cmd):
            payload = _payload(arg)
            if payload is None or payload.type != "unary_expression":
                continue
            op = next((c for c in payload.children if c.type == "operator"), None)
            if op is None:
                continue
            op_text = _node_text(op, src)
            if op_text in ("*", "#"):
                line, col = _node_line_col(payload, src)
                yield Diagnostic(
                    rule_id="M-XINDX-041",
                    severity=Severity.INFO,
                    message=f"Star or pound READ used (R{op_text}…)",
                    path=path,
                    line=line,
                    column=col,
                    column_end=col + len(_node_text(payload, src)),
                    line_text=_line_text(src, line),
                )


register(
    Rule(
        id="M-XINDX-041",
        severity=Severity.INFO,
        title="Star or pound READ used",
        tags=("xindex",),
        check=_check_star_pound_read,
    )
)


# --- M-XINDX-045: Set to a '%' global ------------------------------------
def _check_set_percent_global(src, _tree, path, index):
    """`SET ^%FOO=...` — % globals are reserved for system use."""
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("S", "SET"):
            continue
        for arg in _arguments(cmd):
            payload = _payload(arg)
            if payload is None or payload.type != "binary_expression":
                continue
            # Left side must be variable > global_variable with identifier starting %
            children = list(payload.children)
            if not children:
                continue
            lhs = children[0]
            if lhs.type != "variable":
                continue
            gv = next((c for c in lhs.children if c.type == "global_variable"), None)
            if gv is None:
                continue
            id_node = next((c for c in gv.children if c.type == "identifier"), None)
            if id_node is None:
                continue
            name = _node_text(id_node, src)
            if name.startswith("%"):
                line, col = _node_line_col(gv, src)
                yield Diagnostic(
                    rule_id="M-XINDX-045",
                    severity=Severity.STANDARD,
                    message=f"Set to a '%' global (^{name}); reserved for system use",
                    path=path,
                    line=line,
                    column=col,
                    column_end=col + len(name) + 1,
                    line_text=_line_text(src, line),
                )


register(
    Rule(
        id="M-XINDX-045",
        severity=Severity.STANDARD,
        title="Set to a '%' global",
        tags=("xindex",),
        check=_check_set_percent_global,
    )
)


# --- M-XINDX-050: Extended reference -------------------------------------
def _check_extended_reference(src, _tree, path, index):
    """`^|"UCI"|GLOBAL(args)` — UCI / namespace extended reference."""
    for node in index.of("global_variable"):
        text = _node_text(node, src)
        if "|" in text or "[" in text:
            line, col = _node_line_col(node, src)
            yield Diagnostic(
                rule_id="M-XINDX-050",
                severity=Severity.STANDARD,
                message="Extended reference — UCI/namespace-bound calls reduce portability",
                path=path,
                line=line,
                column=col,
                column_end=col + len(text),
                line_text=_line_text(src, line),
            )


register(
    Rule(
        id="M-XINDX-050",
        severity=Severity.STANDARD,
        title="Extended reference",
        tags=("xindex",),
        check=_check_extended_reference,
    )
)


# --- M-XINDX-056: Patch number missing from second line ------------------
def _check_patch_number_missing(src, _tree, path, _index):
    """SAC second line: ` ;;version;package;**patch1,patch2**;date;build`."""
    lines = src.splitlines()
    if len(lines) < 2:
        return
    second = _decode_line(lines[1])
    # Must contain ** ... ** for patch list
    if not re.search(r"\*\*[^*]*\*\*", second) and second.lstrip().startswith(";;"):
        yield Diagnostic(
            rule_id="M-XINDX-056",
            severity=Severity.STANDARD,
            message="Patch number missing from second line (expected `**patch_list**`)",
            path=path,
            line=2,
            column=1,
            line_text=second,
        )


register(
    Rule(
        id="M-XINDX-056",
        severity=Severity.STANDARD,
        title="Patch number missing from second line",
        tags=("xindex",),
        check=_check_patch_number_missing,
    )
)


# --- M-XINDX-058: Routine code exceeds SACC max of 15000 -----------------
def _check_routine_code_size(src, _tree, path, _index):
    """Code lines (non-comment, non-blank) summed must not exceed 15000."""
    code_bytes = 0
    for line in src.splitlines():
        stripped = line.lstrip(b" \t")
        if not stripped or stripped.startswith(b";"):
            continue
        # Strip trailing comments (`; ...`) — heuristic
        if b";" in stripped:
            stripped = stripped.split(b";", 1)[0]
        code_bytes += len(stripped) + 1  # +1 for newline
    if code_bytes > 15000:
        yield Diagnostic(
            rule_id="M-XINDX-058",
            severity=Severity.STANDARD,
            message=f"Routine code exceeds SACC maximum of 15000 bytes ({code_bytes} bytes)",
            path=path,
            line=1,
            column=1,
            extra={"code_bytes": code_bytes},
        )


register(
    Rule(
        id="M-XINDX-058",
        severity=Severity.STANDARD,
        title="Routine code exceeds SACC max of 15000 bytes",
        tags=("xindex",),
        check=_check_routine_code_size,
    )
)


# --- M-XINDX-060: LOCK command missing timeout ---------------------------
def _check_lock_no_timeout(src, _tree, path, index):
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("L", "LOCK"):
            continue
        for arg in _arguments(cmd):
            if not _arg_has_timeout(arg):
                line, col = _node_line_col(kw_node, src)
                yield Diagnostic(
                    rule_id="M-XINDX-060",
                    severity=Severity.STANDARD,
                    message="LOCK missing :timeout (will block indefinitely)",
                    path=path,
                    line=line,
                    column=col,
                    column_end=col + len(kw),
                    line_text=_line_text(src, line),
                )
                break  # one per command


register(
    Rule(
        id="M-XINDX-060",
        severity=Severity.STANDARD,
        title="LOCK missing timeout",
        tags=("xindex",),
        check=_check_lock_no_timeout,
    )
)


# --- M-XINDX-061: Non-incremental LOCK -----------------------------------
def _check_non_incremental_lock(src, _tree, path, index):
    """`LOCK ^X` (without `+`) is global and dangerous; should be `LOCK +^X:5`."""
    for cmd, kw, kw_node in _commands(index, src):
        if kw not in ("L", "LOCK"):
            continue
        for arg in _arguments(cmd):
            payload = _payload(arg)
            if payload is None:
                continue
            # Incremental form: payload is unary_expression with `+` operator
            if payload.type == "unary_expression":
                op = next((c for c in payload.children if c.type == "operator"), None)
                if op is not None and _node_text(op, src) in ("+", "-"):
                    continue  # incremental ⇒ ok
            line, col = _node_line_col(payload, src)
            yield Diagnostic(
                rule_id="M-XINDX-061",
                severity=Severity.STANDARD,
                message="Non-incremental LOCK — releases all prior locks; use `LOCK +var`",
                path=path,
                line=line,
                column=col,
                column_end=col + len(_node_text(payload, src)),
                line_text=_line_text(src, line),
            )
            break  # one per command


register(
    Rule(
        id="M-XINDX-061",
        severity=Severity.STANDARD,
        title="Non-incremental LOCK",
        tags=("xindex",),
        check=_check_non_incremental_lock,
    )
)


# --- M-XINDX-062: First line of routine violates SAC ---------------------
def _check_first_line_sac(src, _tree, path, _index):
    """First line: ` <ROUTINE> ;<initials>/<routine> - <description> ;<date>`."""
    lines = src.splitlines()
    if not lines:
        return
    first = _decode_line(lines[0])
    # Must start with a label, then space, then ;... — basic shape
    # Allow `LABEL ;text` or `LABEL ;text ; more`
    if not re.match(r"^[A-Za-z%][A-Za-z0-9]*\s*[(].*[)]\s*;|^[A-Za-z%][A-Za-z0-9]*\s+;", first):
        yield Diagnostic(
            rule_id="M-XINDX-062",
            severity=Severity.STANDARD,
            message="First line of routine violates the SAC (expected `LABEL ;description`)",
            path=path,
            line=1,
            column=1,
            line_text=first,
        )


register(
    Rule(
        id="M-XINDX-062",
        severity=Severity.STANDARD,
        title="First line of routine violates the SAC",
        tags=("xindex",),
        check=_check_first_line_sac,
    )
)


# --- M-XINDX-002: Non-standard Z command ---------------------------------
def _check_non_standard_z_command(src, _tree, path, index):
    cmds = standard_commands()
    for cmd, kw, kw_node in _commands(index, src):
        if not kw.startswith("Z"):
            continue
        if kw in cmds:
            continue
        line, col = _node_line_col(kw_node, src)
        yield Diagnostic(
            rule_id="M-XINDX-002",
            severity=Severity.FATAL,
            message=f"Non-standard 'Z' command: {kw}",
            path=path,
            line=line,
            column=col,
            column_end=col + len(kw),
            line_text=_line_text(src, line),
        )


register(
    Rule(
        id="M-XINDX-002",
        severity=Severity.FATAL,
        title="Non-standard 'Z' command",
        tags=("xindex",),
        check=_check_non_standard_z_command,
    )
)


# --- M-XINDX-028: Non-standard $Z special variable -----------------------
def _check_non_standard_dollar_z_isv(src, _tree, path, index):
    isvs = {sv.upper() for sv in standard_isvs()}
    for node in index.of("intrinsic_special_variable"):
        text = _node_text(node, src).upper()
        # Strip args if any: `$ZX(...)` is technically not a variable
        if not text.startswith("$Z"):
            continue
        # Strip arguments: $ZHOROLOG vs $Z(args)
        bare = re.match(r"^\$Z[A-Z]*", text)
        if bare is None:
            continue
        name = bare.group(0)
        if name in isvs:
            continue
        line, col = _node_line_col(node, src)
        yield Diagnostic(
            rule_id="M-XINDX-028",
            severity=Severity.STANDARD,
            message=f"Non-standard $Z special variable: {name}",
            path=path,
            line=line,
            column=col,
            column_end=col + len(name),
            line_text=_line_text(src, line),
        )


register(
    Rule(
        id="M-XINDX-028",
        severity=Severity.STANDARD,
        title="Non-standard $Z special variable",
        tags=("xindex",),
        check=_check_non_standard_dollar_z_isv,
    )
)


# --- M-XINDX-031: Non-standard $Z function -------------------------------
def _check_non_standard_dollar_z_function(src, _tree, path, index):
    funcs = {fn.upper() for fn in standard_functions()}
    for node in index.of("intrinsic_function"):
        # function name is the leading $XXX before the (
        text = _node_text(node, src).upper()
        m = re.match(r"^\$Z[A-Z]*", text)
        if m is None:
            continue
        name = m.group(0)
        if name in funcs:
            continue
        line, col = _node_line_col(node, src)
        yield Diagnostic(
            rule_id="M-XINDX-031",
            severity=Severity.STANDARD,
            message=f"Non-standard $Z function: {name}",
            path=path,
            line=line,
            column=col,
            column_end=col + len(name),
            line_text=_line_text(src, line),
        )


register(
    Rule(
        id="M-XINDX-031",
        severity=Severity.STANDARD,
        title="Non-standard $Z function",
        tags=("xindex",),
        check=_check_non_standard_dollar_z_function,
    )
)


# --- M-XINDX-054: Access to SSVN's or $SYSTEM restricted to Kernel -------
def _check_ssvn_system_access(src, _tree, path, index):
    """Use of $SYSTEM or ^$ structured system variables."""
    for node in index.of("intrinsic_special_variable"):
        text = _node_text(node, src).upper()
        if text in ("$SY", "$SYSTEM"):
            line, col = _node_line_col(node, src)
            yield Diagnostic(
                rule_id="M-XINDX-054",
                severity=Severity.STANDARD,
                message="$SYSTEM access — restricted to Kernel package",
                path=path,
                line=line,
                column=col,
                column_end=col + len(text),
                line_text=_line_text(src, line),
            )


register(
    Rule(
        id="M-XINDX-054",
        severity=Severity.STANDARD,
        title="Access to SSVN's or $SYSTEM restricted to Kernel",
        tags=("xindex",),
        check=_check_ssvn_system_access,
    )
)


# --- M-XINDX-005, M-XINDX-006, M-XINDX-021, M-XINDX-051: parse errors ----
def _check_parse_errors(src, tree, path, index):
    """Surface tree-sitter ERROR / MISSING nodes as XINDEX-flavoured fatals.

    Tree-sitter ERROR nodes correspond to a number of XINDEX rules
    depending on context:
      M-XINDX-005 — Unmatched parenthesis
      M-XINDX-006 — Unmatched quotation marks
      M-XINDX-021 — General syntax error
      M-XINDX-051 — Block structure mismatch

    We can't always distinguish between them precisely without
    additional analysis, so we emit M-XINDX-021 (general syntax error)
    for every ERROR / missing node — XINDEX behaves similarly when its
    parser cannot localise the cause.

    Fast-path: when the parse tree has no errors at all, skip walking.
    `is_missing` can be set on any node type (not just `ERROR`), so when
    errors *are* present we fall back to a full walk to preserve byte-
    identical diagnostics with the pre-index implementation.
    """
    if not tree.root_node.has_error:
        return
    for node in _walk(tree.root_node):
        if node.type == "ERROR" or node.is_missing:
            line, col = _node_line_col(node, src)
            yield Diagnostic(
                rule_id="M-XINDX-021",
                severity=Severity.FATAL,
                message="General syntax error" + (" (missing token)" if node.is_missing else ""),
                path=path,
                line=line,
                column=col,
                column_end=col + max(1, len(_node_text(node, src))),
                line_text=_line_text(src, line),
            )


register(
    Rule(
        id="M-XINDX-021",
        severity=Severity.FATAL,
        title="General syntax error",
        tags=("xindex",),
        check=_check_parse_errors,
    )
)


# --- M-XINDX-057: Lower/mixed case in local variable name ----------------
def _check_local_variable_case(src, _tree, path, index):
    """M-XINDX-057 — Local variable name contains a lowercase letter.

    SAC §3.6 requires variable names to be uppercase A-Z, digits, and
    optionally a leading ``%``. We flag any ``local_variable`` whose
    identifier text contains a lowercase ASCII letter.

    Excludes ``intrinsic_special_variable`` (``$TEST``, ``$ZHOROLOG``)
    — those are tracked by separate rules and aren't subject to the
    SAC variable-naming rule.
    """
    seen_per_line: set[tuple[int, int, str]] = set()
    for var_node in index.of("local_variable"):
        ident = next((c for c in var_node.children if c.type == "identifier"), None)
        if ident is None:
            continue
        name = _node_text(ident, src)
        if not _has_lowercase(name):
            continue
        line, col = _node_line_col(ident, src)
        key = (line, col, name)
        if key in seen_per_line:
            continue
        seen_per_line.add(key)
        yield Diagnostic(
            rule_id="M-XINDX-057",
            severity=Severity.STANDARD,
            message=f"Lower/mixed case in local variable name: '{name}'",
            path=path,
            line=line,
            column=col,
            column_end=col + len(name),
            line_text=_line_text(src, line),
            extra={"name": name},
        )


def _has_lowercase(name: str) -> bool:
    return any("a" <= ch <= "z" for ch in name)


register(
    Rule(
        id="M-XINDX-057",
        severity=Severity.STANDARD,
        title="Lower/mixed case in local variable name",
        tags=("xindex", "sac"),
        check=_check_local_variable_case,
    )
)


# ---------------------------------------------------------------------------
# Cross-routine rules (Phase D)
# ---------------------------------------------------------------------------
#
# These rules need a ``WorkspaceIndex`` passed as a 5th positional arg.
# They opt in via ``Rule.needs_workspace=True``; the runner skips them
# when no workspace context is available.


def _check_cross_routine_missing_routine(
    src: bytes, _tree, path: Path, _index: NodeIndex, workspace
) -> Iterator[Diagnostic]:
    """M-XINDX-007 — Call to undefined routine.

    For each outbound reference (LABEL^ROUTINE, ^ROUTINE, $$LABEL^ROUTINE),
    if ``ROUTINE`` is not indexed anywhere in the workspace, flag it
    fatal. Only fires for cross-routine refs — intra-routine refs
    where the call writes ``$$LABEL`` (no ^routine) get the same
    treatment from the existing single-file M-XINDX-014.
    """
    refs = workspace.refs_from(path)
    for ref in refs:
        if ref.target_routine.upper() == path.stem.upper():
            # Intra-routine — covered by single-file rules; skip here.
            continue
        if workspace.has_routine(ref.target_routine):
            continue
        yield Diagnostic(
            rule_id="M-XINDX-007",
            severity=Severity.FATAL,
            message=f"Call to undefined routine ^{ref.target_routine}",
            path=path,
            line=ref.line,
            column=ref.column + 1,  # Diagnostic columns are 1-indexed
            column_end=ref.end_column + 1,
            line_text=_decode_line(src.splitlines()[ref.line - 1])
            if ref.line - 1 < len(src.splitlines())
            else "",
        )


register(
    Rule(
        id="M-XINDX-007",
        severity=Severity.FATAL,
        title="Call to undefined routine",
        tags=("xindex",),
        check=_check_cross_routine_missing_routine,
        needs_workspace=True,
    )
)


def _check_cross_routine_missing_label(
    src: bytes, _tree, path: Path, _index: NodeIndex, workspace
) -> Iterator[Diagnostic]:
    """M-XINDX-008 — Call to undefined label in another routine.

    For each outbound reference ``LABEL^ROUTINE`` where ROUTINE IS
    indexed but LABEL doesn't exist within ROUTINE, flag it fatal.
    Skips ``^ROUTINE``-style refs (no label named) and intra-routine
    refs (those are M-XINDX-014's job).
    """
    refs = workspace.refs_from(path)
    for ref in refs:
        if ref.target_label is None:
            continue  # ^ROUTINE form — no label to validate
        if ref.target_routine.upper() == path.stem.upper():
            continue  # intra-routine
        if not workspace.has_routine(ref.target_routine):
            continue  # M-XINDX-007 covers this case
        if workspace.lookup(ref.target_routine, ref.target_label) is not None:
            continue
        yield Diagnostic(
            rule_id="M-XINDX-008",
            severity=Severity.FATAL,
            message=(
                f"Call to undefined label "
                f"{ref.target_label}^{ref.target_routine}"
            ),
            path=path,
            line=ref.line,
            column=ref.column + 1,
            column_end=ref.end_column + 1,
            line_text=_decode_line(src.splitlines()[ref.line - 1])
            if ref.line - 1 < len(src.splitlines())
            else "",
        )


register(
    Rule(
        id="M-XINDX-008",
        severity=Severity.FATAL,
        title="Call to undefined label in another routine",
        tags=("xindex",),
        check=_check_cross_routine_missing_label,
        needs_workspace=True,
    )
)


def _check_label_never_referenced(
    src: bytes, tree, path: Path, _index: NodeIndex, workspace
) -> Iterator[Diagnostic]:
    """M-XINDX-049 — Label declared but never referenced anywhere.

    Walks each label in this file. The routine-entry label (whose
    name equals the routine name) is never flagged — it's the
    file's load-on-do entry, conventionally callable as ``D ^ROUTINE``
    even when no other site references it explicitly.
    """
    routine_upper = path.stem.upper()
    for line_node in tree.root_node.children:
        if line_node.type != "line":
            continue
        label_node = next(
            (c for c in line_node.children if c.type == "label"), None
        )
        if label_node is None:
            continue
        label_name = src[label_node.start_byte : label_node.end_byte].decode(
            "latin-1", errors="replace"
        )
        if label_name.upper() == routine_upper:
            continue  # routine entry — exempt
        # Inbound references that target this exact (routine, label).
        refs = workspace.references_to(routine_upper, label_name)
        if refs:
            continue
        yield Diagnostic(
            rule_id="M-XINDX-049",
            severity=Severity.WARNING,
            message=f"Label '{label_name}' is declared but never referenced",
            path=path,
            line=label_node.start_point[0] + 1,
            column=label_node.start_point[1] + 1,
            column_end=label_node.start_point[1] + 1 + len(label_name),
            line_text=_decode_line(src.splitlines()[label_node.start_point[0]])
            if label_node.start_point[0] < len(src.splitlines())
            else "",
        )


register(
    Rule(
        id="M-XINDX-049",
        severity=Severity.WARNING,
        title="Label declared but never referenced",
        tags=("xindex",),
        check=_check_label_never_referenced,
        needs_workspace=True,
    )
)


# ---------------------------------------------------------------------------
# Control-flow rules (single-file, AST pattern-based)
# ---------------------------------------------------------------------------


_TERMINATING_KEYWORDS = frozenset({"Q", "QUIT", "H", "HALT", "G", "GOTO"})


def _check_dead_code_after_quit(
    src: bytes, _tree, path: Path, index: NodeIndex
) -> Iterator[Diagnostic]:
    """M-XINDX-009 — Code after unconditional QUIT / HALT / GOTO.

    Within each label scope, find the first line whose first command
    is an unconditional terminator (no postconditional, no preceding
    IF on the same line). Any executable line after that — until the
    next label — is unreachable.

    Skips dot-block lines (control flow inside dot blocks is more
    nuanced; we don't model it). Skips lines that are just comments.
    """
    line_nodes = index.of("line")
    # Group lines by their owning label by walking in document order.
    current_label_terminated_at: int | None = None
    for line_node in line_nodes:
        # Reset the "terminated" state at every label boundary.
        if any(c.type == "label" for c in line_node.children):
            current_label_terminated_at = None
            continue
        # Skip dot-block lines; their flow isn't modelled here.
        if any(c.type == "dot_block_prefix" for c in line_node.children):
            continue
        # Find the first command_sequence on this line.
        cs = next((c for c in line_node.children if c.type == "command_sequence"), None)
        if cs is None:
            continue  # comment-only or empty
        cmds = [c for c in cs.children if c.type == "command"]
        if not cmds:
            continue

        line_no = line_node.start_point[0] + 1

        if current_label_terminated_at is not None:
            # Already saw a terminator earlier in this label; this line is dead.
            yield Diagnostic(
                rule_id="M-XINDX-009",
                severity=Severity.WARNING,
                message=(
                    "Unreachable code: line follows an unconditional "
                    f"terminator on line {current_label_terminated_at}"
                ),
                path=path,
                line=line_no,
                column=1,
                column_end=len(_decode_line(src.splitlines()[line_no - 1]))
                + 1
                if line_no - 1 < len(src.splitlines())
                else 1,
                line_text=_decode_line(src.splitlines()[line_no - 1])
                if line_no - 1 < len(src.splitlines())
                else "",
            )
            continue

        first = cmds[0]
        first_kw_node = next(
            (c for c in first.children if c.type == "command_keyword"), None
        )
        if first_kw_node is None:
            continue
        kw = src[first_kw_node.start_byte : first_kw_node.end_byte].decode(
            "latin-1", errors="replace"
        ).upper()
        if kw not in _TERMINATING_KEYWORDS:
            continue
        # Skip if the terminator carries a postconditional — then it's
        # only sometimes terminating and the rule below could be a false
        # positive.
        has_postcond = any(
            c.type in ("postconditional", "argument_postconditional")
            for c in first.children
        )
        if has_postcond:
            continue
        # Mark this label as terminated; subsequent lines are dead.
        current_label_terminated_at = line_no


register(
    Rule(
        id="M-XINDX-009",
        severity=Severity.WARNING,
        title="Unreachable code after unconditional QUIT / HALT / GOTO",
        tags=("xindex",),
        check=_check_dead_code_after_quit,
    )
)


_CONDITIONAL_KEYWORDS = frozenset({"I", "IF", "E", "ELSE"})


def _check_empty_conditional(
    src: bytes, _tree, path: Path, index: NodeIndex
) -> Iterator[Diagnostic]:
    """M-XINDX-051 — IF / ELSE with no body on the same line.

    M's IF and ELSE only gate commands that follow on the *same* line
    (per ANSI). ``IF X>0`` alone on a line — with no commands after
    the condition — is a logical no-op and almost always a typo
    (e.g. the user expected indentation-based scoping like Python).
    """
    line_nodes = index.of("line")
    for line_node in line_nodes:
        cs = next((c for c in line_node.children if c.type == "command_sequence"), None)
        if cs is None:
            continue
        cmds = [c for c in cs.children if c.type == "command"]
        if len(cmds) != 1:
            continue
        cmd = cmds[0]
        kw_node = next(
            (c for c in cmd.children if c.type == "command_keyword"), None
        )
        if kw_node is None:
            continue
        kw = src[kw_node.start_byte : kw_node.end_byte].decode(
            "latin-1", errors="replace"
        ).upper()
        if kw not in _CONDITIONAL_KEYWORDS:
            continue
        # Bare IF/ELSE with no body — flag.
        line_no = line_node.start_point[0] + 1
        col = kw_node.start_point[1] + 1
        yield Diagnostic(
            rule_id="M-XINDX-051",
            severity=Severity.WARNING,
            message=(
                f"{kw} has no body on the same line — M conditionals "
                "only gate commands that follow on the SAME line"
            ),
            path=path,
            line=line_no,
            column=col,
            column_end=col + len(kw),
            line_text=_decode_line(src.splitlines()[line_no - 1])
            if line_no - 1 < len(src.splitlines())
            else "",
        )


register(
    Rule(
        id="M-XINDX-051",
        severity=Severity.WARNING,
        title="IF / ELSE with no body on the same line",
        tags=("xindex",),
        check=_check_empty_conditional,
    )
)
