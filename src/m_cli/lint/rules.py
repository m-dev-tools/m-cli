"""Rule definitions for `m lint`.

Each rule is a callable that takes the source bytes, the parsed tree,
and the file path, and yields zero or more Diagnostics.

Rules are organised by tag (`xindex`, `sac`, …). The `--rules` toggle
filters which tag(s) run.

Step 2.0 ships a deliberately small subset of the 66-rule XINDEX set —
enough to validate the framework. Subsequent commits add rules
incrementally, each with a hand-crafted test and a VistA-corpus
regression check.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from m_cli.lint.diagnostic import Diagnostic, Severity

if TYPE_CHECKING:
    from tree_sitter import Tree

# ---------------------------------------------------------------------------
# Rule metadata + registry
# ---------------------------------------------------------------------------

RuleFn = Callable[[bytes, "Tree", Path], Iterator[Diagnostic]]


@dataclass(frozen=True)
class Rule:
    id: str
    severity: Severity
    title: str
    tags: tuple[str, ...]
    check: RuleFn


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

def _check_trailing_blanks(src: bytes, _tree, path: Path) -> Iterator[Diagnostic]:
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


register(Rule(
    id="M-XINDX-013",
    severity=Severity.WARNING,
    title="Blank(s) at end of line",
    tags=("xindex",),
    check=_check_trailing_blanks,
))


def _check_control_chars(src: bytes, _tree, path: Path) -> Iterator[Diagnostic]:
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


register(Rule(
    id="M-XINDX-018",
    severity=Severity.WARNING,
    title="Line contains a CONTROL (non-graphic) character",
    tags=("xindex",),
    check=_check_control_chars,
))


def _check_line_length(src: bytes, _tree, path: Path) -> Iterator[Diagnostic]:
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


register(Rule(
    id="M-XINDX-019",
    severity=Severity.STANDARD,
    title="Line is longer than 245 bytes",
    tags=("xindex",),
    check=_check_line_length,
))


def _check_null_line(src: bytes, tree, path: Path) -> Iterator[Diagnostic]:
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


register(Rule(
    id="M-XINDX-042",
    severity=Severity.WARNING,
    title="Null line (no commands or comment)",
    tags=("xindex",),
    check=_check_null_line,
))


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


def _collect_labels(tree, src: bytes) -> dict[str, list[tuple[int, int]]]:
    """Map label name → list of (line, col) where it is defined."""
    labels: dict[str, list[tuple[int, int]]] = {}
    for node in _walk(tree.root_node):
        if node.type == "label":
            name = _node_text(node, src)
            line, col = _node_line_col(node, src)
            labels.setdefault(name, []).append((line, col))
    return labels


def _check_first_label(src: bytes, tree, path: Path) -> Iterator[Diagnostic]:
    """M-XINDX-017 — First line label NOT routine name.

    The routine's first label must equal the file basename (without `.m`).
    Excludes routines starting with `%` (XINDEX exclusion).
    """
    for node in _walk(tree.root_node):
        if node.type == "label":
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
                        f"First line label ('{first_label}') does not match "
                        f"routine name ('{expected}')"
                    ),
                    path=path,
                    line=line,
                    column=col,
                    column_end=col + len(first_label),
                    line_text=_line_text(src, line),
                    extra={"first_label": first_label, "expected": expected},
                )
            return  # only check the first label


register(Rule(
    id="M-XINDX-017",
    severity=Severity.WARNING,
    title="First line label NOT routine name",
    tags=("xindex",),
    check=_check_first_label,
))


def _check_duplicate_labels(src: bytes, tree, path: Path) -> Iterator[Diagnostic]:
    """M-XINDX-015 — Duplicate label."""
    labels = _collect_labels(tree, src)
    for name, occurrences in labels.items():
        if len(occurrences) > 1:
            for line, col in occurrences[1:]:  # skip first definition
                yield Diagnostic(
                    rule_id="M-XINDX-015",
                    severity=Severity.WARNING,
                    message=(
                        f"Duplicate label: '{name}' "
                        f"(first defined at line {occurrences[0][0]})"
                    ),
                    path=path,
                    line=line,
                    column=col,
                    column_end=col + len(name),
                    line_text=_line_text(src, line),
                    extra={"label": name, "first_line": occurrences[0][0]},
                )


register(Rule(
    id="M-XINDX-015",
    severity=Severity.WARNING,
    title="Duplicate label",
    tags=("xindex",),
    check=_check_duplicate_labels,
))


def _check_missing_label_call(src: bytes, tree, path: Path) -> Iterator[Diagnostic]:
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
    labels = _collect_labels(tree, src)
    label_set = set(labels)
    this_routine = path.stem

    for node in _walk(tree.root_node):
        if node.type == "command":
            yield from _check_command_label_calls(node, src, label_set, this_routine, path)
        elif node.type == "extrinsic_function":
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


register(Rule(
    id="M-XINDX-014",
    severity=Severity.FATAL,
    title="Call to missing label in this routine",
    tags=("xindex",),
    check=_check_missing_label_call,
))


def _check_break_command(src: bytes, tree, path: Path) -> Iterator[Diagnostic]:
    """M-XINDX-025 — Break command used (BREAK is dev-only)."""
    for node in _walk(tree.root_node):
        if node.type == "command_keyword":
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


register(Rule(
    id="M-XINDX-025",
    severity=Severity.STANDARD,
    title="BREAK command used",
    tags=("xindex",),
    check=_check_break_command,
))


def _check_lowercase_command(src: bytes, tree, path: Path) -> Iterator[Diagnostic]:
    """M-XINDX-047 — Lowercase command(s) used in line.

    XINDEX flags commands written in lowercase. Modern style (and the
    m-tools 'lowercase pythonic MUMPS' convention) actually *prefers*
    lowercase, so this rule is provided for XINDEX-parity but not
    enabled in modern profiles. It is still in the `xindex` tag.
    """
    for node in _walk(tree.root_node):
        if node.type == "command_keyword":
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


register(Rule(
    id="M-XINDX-047",
    severity=Severity.STANDARD,
    title="Lowercase command(s) used in line",
    tags=("xindex",),
    check=_check_lowercase_command,
))


def _check_routine_size(src: bytes, _tree, path: Path) -> Iterator[Diagnostic]:
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


register(Rule(
    id="M-XINDX-035",
    severity=Severity.STANDARD,
    title="Routine exceeds SACC maximum size of 20000 bytes",
    tags=("xindex",),
    check=_check_routine_size,
))


def _check_second_line_sac(src: bytes, _tree, path: Path) -> Iterator[Diagnostic]:
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


register(Rule(
    id="M-XINDX-044",
    severity=Severity.STANDARD,
    title="2nd line of routine violates the SAC",
    tags=("xindex",),
    check=_check_second_line_sac,
))
