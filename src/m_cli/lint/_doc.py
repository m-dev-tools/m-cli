"""Documentation-track rules (M-DOC-NN).

Greenfield rules that validate the M-doc tag grammar specified in
m-stdlib/docs/guides/m-doc-grammar.md. The grammar is an additive
extension of M's existing ``; doc:`` comment convention: tags like
``@param`` / ``@returns`` / ``@raises`` / ``@example`` / ``@since`` /
``@stable`` / ``@see`` / ``@deprecated`` / ``@internal`` are written
inside ``; doc:`` lines as the first non-whitespace token of the
body.

Currently shipped:

  - M-DOC-001 — public label missing required M-doc tags.

Each public label (top-level label that has a ``; doc:`` block AND is
not tagged ``@internal``) must carry:

  - ``@param NAME [TYPE] BODY`` — one per formal-list arg, NAME
    matching the formal-list left-to-right.
  - ``@returns [TYPE] BODY`` — required when any code path in the
    label body does ``quit <expression>``.
  - ``@raises CODE [BODY]`` — one per ``,U-STDxxx-NAME,`` value the
    label sets via ``set $ecode=`` (statically detected — transitive
    raises through helpers are NOT inferred).
  - ``@since vX.Y.Z`` — required.
  - ``@stable {experimental,stable,deprecated}`` — required.

The rule fires at WARNING severity in v1; promotion to ERROR is
deferred per ``module-tracker.md`` D2 (the SemVer CI gate decision).
WA3 in the m-stdlib discoverability tracker (``docs/tracking/
discoverability-tracker.md``) is the live work item for this rule.

The check is intentionally text-driven: it scans the comment-only
``; doc:`` lines that follow each label header. tree-sitter-m sees
these as ``comment`` nodes, but the M-doc grammar lives entirely in
their byte content — there is no AST distinction between a
``; doc:`` comment and any other comment. We use the line bucketing
that ``_modern.py`` already provides via ``_label_body_extents``, then
parse the doc-block text the same way ``tools/gen-manifest.py`` in
m-stdlib does.

NOTE on transitive raises: the grammar guide §5.3 says ``@raises`` is
required when "the label or any helper it transitively calls and does
not catch sets $ECODE". A transitive analyser would need a workspace-
wide call graph; the m-cli lint engine does not yet have one (it would
gate on M-XINDX-007/008's cross-routine pass). v1 of M-DOC-001
therefore only flags codes the label *itself* sets via
``set $ecode=,U-...,``. False negatives on transitive raises are
acceptable (the grammar guide already records this as deliberate
under-reporting; the manifest generator surfaces the `raised_in_body`
field for exactly this purpose).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from m_cli.lint._index import NodeIndex
from m_cli.lint._modern import _label_body_extents, _label_name
from m_cli.lint.context import LintContext
from m_cli.lint.diagnostic import Category, Diagnostic, Severity
from m_cli.lint.rules import Rule, register

_Node = Any

# Tags recognised by the M-doc grammar.
_KNOWN_TAGS = frozenset(
    {
        "@param",
        "@returns",
        "@raises",
        "@example",
        "@since",
        "@stable",
        "@see",
        "@deprecated",
        "@internal",
    }
)

# Match the formal-list inside a label header. Examples this catches:
#   ``parse(text,root)``
#   ``f(template,a1,a2,a3)``
#   ``now()``      → empty formal-list
#   ``parseFail``  → no parens at all (no formal-list)
_FORMAL_LIST_RE = re.compile(rb"^[A-Za-z][A-Za-z0-9]*\(([^)]*)\)")

# Match a ``; doc:`` line. Captures the body text (everything after the
# single-space delimiter that follows the colon). Leading whitespace
# in the body is preserved — it's the continuation signal.
_DOC_LINE_RE = re.compile(rb"^\s+;\s*doc:\s?(.*)$")

# Match a ``set $ecode=",U-STDxxx-NAME,"`` (or single-quoted) in body
# code. Used to identify codes the label itself raises.
_ECODE_SET_RE = re.compile(
    rb"""\$ecode\s*=\s*["'],U-([A-Z0-9-]+),["']""", re.IGNORECASE
)

# Match a ``quit <expression>`` line in label body — the extrinsic
# indicator. Allows postcondition (``quit:cond expr``).
_QUIT_VALUE_RE = re.compile(rb"^\s*(?:quit|q)(?::[^ ]+)?\s+\S")

# Valid ``@stable`` levels.
_STABLE_LEVELS = frozenset({"experimental", "stable", "deprecated"})


def _parse_doc_block(doc_lines: list[bytes]) -> dict:
    """Parse a list of ``; doc:`` body lines into a tag map.

    Mirrors ``tools/gen-manifest.py`` in m-stdlib.

    Returns ``{"tags": {tag: [body, ...]}, "internal": bool, "has_any": bool}``.
    Body strings here are the text *after* the tag name, joined with
    newlines for multi-line continuation. ``has_any`` is True iff the
    block contains any tag or any non-empty prose — used by the rule
    to distinguish "internal helper without doc" (skip) from "public
    label with doc block".
    """
    tags: dict[str, list[str]] = {}
    current_tag: str | None = None
    current_buf: list[str] = []
    internal = False
    has_any = False

    def flush() -> None:
        nonlocal current_tag, current_buf
        if current_tag is not None:
            tags.setdefault(current_tag, []).append("\n".join(current_buf).rstrip())
        current_tag = None
        current_buf = []

    for raw in doc_lines:
        if not raw.strip():
            flush()
            continue
        has_any = True
        try:
            stripped = raw.lstrip().decode("latin-1")
        except UnicodeDecodeError:
            stripped = raw.lstrip().decode("latin-1", errors="replace")
        first_token = stripped.split(None, 1)[0] if stripped else ""
        is_indented = bool(raw) and bytes([raw[0]]).isspace()

        if first_token in _KNOWN_TAGS:
            flush()
            if first_token == "@internal":
                internal = True
                continue
            current_tag = first_token
            tail = stripped[len(first_token):].lstrip()
            current_buf = [tail] if tail else []
        elif is_indented and current_tag is not None:
            current_buf.append(stripped)
        else:
            flush()

    flush()
    return {"tags": tags, "internal": internal, "has_any": has_any}


def _collect_doc_lines(src: bytes, header_line_0idx: int, end_line_0idx: int) -> list[bytes]:
    """Return the raw bodies of consecutive ``; doc:`` lines that form
    the doc block for the label whose header is at ``header_line_0idx``.

    Walks lines starting at ``header_line_0idx + 1`` (the line after
    the header) and collects every ``; doc:`` line until the first
    non-doc line. Matches the manifest generator's ``collect_doc_lines``.
    """
    lines = src.split(b"\n")
    out: list[bytes] = []
    i = header_line_0idx + 1
    # Skip leading blank lines (rare).
    while i < end_line_0idx and not lines[i].strip():
        i += 1
    while i < end_line_0idx:
        m = _DOC_LINE_RE.match(lines[i])
        if not m:
            break
        out.append(m.group(1).rstrip())
        i += 1
    return out


def _label_body_text(src: bytes, header_line_0idx: int, end_line_0idx: int) -> bytes:
    """Return the bytes of lines between header (exclusive) and the next
    label (exclusive). Used for ``quit <expr>`` and ``$ecode=`` scans."""
    lines = src.split(b"\n")
    return b"\n".join(lines[header_line_0idx + 1 : end_line_0idx])


def _formals_from_header(src: bytes, label_node) -> list[str]:
    """Return the formal-list arg names from the label header line.

    Empty list for a no-paren label or a label with empty parens.
    """
    line_no = label_node.start_point[0]
    lines = src.split(b"\n")
    if line_no >= len(lines):
        return []
    header_line = lines[line_no]
    # Strip leading whitespace before matching — labels start at col 0
    # but be defensive in case future grammars allow indented labels.
    m = _FORMAL_LIST_RE.match(header_line.lstrip())
    if not m:
        return []
    raw = m.group(1).decode("latin-1", errors="replace")
    return [arg.strip() for arg in raw.split(",") if arg.strip()]


def _quits_value(body_text: bytes) -> bool:
    """True if any line in body_text starts with ``quit`` (or ``q``)
    followed by a value expression. ``quit`` alone (no value) does
    NOT trigger this — that's a procedure return."""
    for line in body_text.split(b"\n"):
        stripped = line.lstrip()
        if not stripped:
            continue
        if _QUIT_VALUE_RE.match(line):
            return True
    return False


def _ecode_codes(body_text: bytes) -> list[str]:
    """Return the set of ``U-STDxxx-NAME`` codes the label body sets
    directly in code (not inside ``; doc:`` blocks).

    The doc-block exclusion avoids false positives when an ``@example``
    body contains ``set $ecode="..."``: that's documentation showing
    how a *caller* might react to the label's return, not a $ECODE the
    label itself raises. We strip every ``; doc:`` and other ``;``
    comment line before scanning.

    Order-preserving deduplication so the diagnostic message is
    deterministic.
    """
    out: list[str] = []
    code_lines: list[bytes] = []
    for line in body_text.split(b"\n"):
        # Drop pure-comment lines (any leading-whitespace ``;``).
        stripped = line.lstrip()
        if stripped.startswith(b";"):
            continue
        code_lines.append(line)
    code_text = b"\n".join(code_lines)
    for m in _ECODE_SET_RE.finditer(code_text):
        code = "U-" + m.group(1).decode("latin-1", errors="replace")
        if code not in out:
            out.append(code)
    return out


def _check_doc_tags(
    src: bytes, _tree, path: Path, index: NodeIndex, _ctx: LintContext
) -> Iterator[Diagnostic]:
    """M-DOC-001 — Public label missing required M-doc tags.

    Public label = top-level label that has a non-empty ``; doc:``
    block AND is not tagged ``@internal``. For each public label we
    check the required-tag set (see module docstring) and emit one
    Diagnostic per missing tag.
    """
    extents = _label_body_extents(src, index)
    if not extents:
        return

    for label, header_line, end_line in extents:
        doc_lines = _collect_doc_lines(src, header_line, end_line)
        if not doc_lines:
            continue
        parsed = _parse_doc_block(doc_lines)
        if parsed["internal"]:
            continue
        if not parsed["has_any"]:
            continue

        tags = parsed["tags"]
        name = _label_name(src, label)
        formals = _formals_from_header(src, label)
        body_text = _label_body_text(src, header_line, end_line)
        diag_line = header_line + 1  # 1-based for the Diagnostic

        # ---- @param coverage ------------------------------------------------
        param_names: list[str] = []
        for body in tags.get("@param", []):
            head = body.split(None, 1)
            if head:
                param_names.append(head[0])

        formal_set = set(formals)
        param_set = set(param_names)
        for missing in formals:
            if missing not in param_set:
                yield Diagnostic(
                    rule_id="M-DOC-001",
                    severity=Severity.WARNING,
                    message=(
                        f"Public label '{name}' missing @param for formal '{missing}'"
                    ),
                    path=path,
                    line=diag_line,
                    column=label.start_point[1] + 1,
                    column_end=label.start_point[1] + 1 + len(name),
                )
        for spurious in param_names:
            if spurious not in formal_set:
                yield Diagnostic(
                    rule_id="M-DOC-001",
                    severity=Severity.WARNING,
                    message=(
                        f"Public label '{name}' has @param '{spurious}' "
                        f"not in formal-list"
                    ),
                    path=path,
                    line=diag_line,
                    column=label.start_point[1] + 1,
                    column_end=label.start_point[1] + 1 + len(name),
                )

        # ---- @returns required when body has `quit <expr>` ------------------
        if _quits_value(body_text) and "@returns" not in tags:
            yield Diagnostic(
                rule_id="M-DOC-001",
                severity=Severity.WARNING,
                message=(
                    f"Public label '{name}' has 'quit <expression>' but no @returns"
                ),
                path=path,
                line=diag_line,
                column=label.start_point[1] + 1,
                column_end=label.start_point[1] + 1 + len(name),
            )

        # ---- @raises coverage for codes the body sets directly --------------
        declared_raises: set[str] = set()
        for body in tags.get("@raises", []):
            head = body.split(None, 1)
            if head:
                declared_raises.add(head[0])
        for code in _ecode_codes(body_text):
            if code not in declared_raises:
                yield Diagnostic(
                    rule_id="M-DOC-001",
                    severity=Severity.WARNING,
                    message=(
                        f"Public label '{name}' sets $ECODE=,{code}, "
                        f"but has no matching @raises"
                    ),
                    path=path,
                    line=diag_line,
                    column=label.start_point[1] + 1,
                    column_end=label.start_point[1] + 1 + len(name),
                )

        # ---- @since required ------------------------------------------------
        if "@since" not in tags:
            yield Diagnostic(
                rule_id="M-DOC-001",
                severity=Severity.WARNING,
                message=f"Public label '{name}' missing @since tag",
                path=path,
                line=diag_line,
                column=label.start_point[1] + 1,
                column_end=label.start_point[1] + 1 + len(name),
            )

        # ---- @stable required + value validated -----------------------------
        if "@stable" not in tags:
            yield Diagnostic(
                rule_id="M-DOC-001",
                severity=Severity.WARNING,
                message=f"Public label '{name}' missing @stable tag",
                path=path,
                line=diag_line,
                column=label.start_point[1] + 1,
                column_end=label.start_point[1] + 1 + len(name),
            )
        else:
            level_body = tags["@stable"][0].split(None, 1)
            level = level_body[0] if level_body else ""
            if level and level not in _STABLE_LEVELS:
                yield Diagnostic(
                    rule_id="M-DOC-001",
                    severity=Severity.WARNING,
                    message=(
                        f"Public label '{name}' @stable value '{level}' "
                        f"is not one of experimental/stable/deprecated"
                    ),
                    path=path,
                    line=diag_line,
                    column=label.start_point[1] + 1,
                    column_end=label.start_point[1] + 1 + len(name),
                )
            if level == "deprecated" and "@deprecated" not in tags:
                yield Diagnostic(
                    rule_id="M-DOC-001",
                    severity=Severity.WARNING,
                    message=(
                        f"Public label '{name}' is @stable deprecated but "
                        f"has no @deprecated tag"
                    ),
                    path=path,
                    line=diag_line,
                    column=label.start_point[1] + 1,
                    column_end=label.start_point[1] + 1 + len(name),
                )


register(
    Rule(
        id="M-DOC-001",
        severity=Severity.WARNING,
        category=Category.DOCUMENTATION,
        title="Public label missing required M-doc tags",
        # `modern` so the rule lands in default + modern + pythonic
        # profiles; `doc` for explicit selection (`--rules=M-DOC-001`
        # also works as a single-rule selector via the runner).
        tags=("modern", "doc"),
        check=_check_doc_tags,
        needs_context=True,
        replaces=(),
    )
)
