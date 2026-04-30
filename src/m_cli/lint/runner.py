"""Orchestrate lint rules over a source file.

`lint_source(path, src, rule_filter)` parses the source, runs each
selected rule, and returns a sorted list of Diagnostics.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from m_cli.lint._directives import parse_directives
from m_cli.lint._index import NodeIndex
from m_cli.lint.diagnostic import Diagnostic
from m_cli.lint.profiles import (
    DEFAULT_PROFILE,
    get_profile,
    list_profiles,
    resolve_profile,
)
from m_cli.lint.rules import Rule, all_rules
from m_cli.parser import parse

if TYPE_CHECKING:
    from m_cli.lint.context import LintContext


def fixer_for(rule_id: str) -> str | None:
    """Return the ``m fmt`` rule id that auto-fixes ``rule_id``, if any.

    Public helper for tooling consumers (LSP wrapper, CI integrations)
    that want to resolve lint findings to their auto-fixers without
    importing the rule registry. Returns ``None`` when the rule is
    unknown or has no auto-fix.
    """
    rule = next((r for r in all_rules() if r.id == rule_id), None)
    return rule.fixer_id if rule is not None else None


def _apply_replaces_suppression(rules: list[Rule]) -> list[Rule]:
    """Drop any rule whose id is listed in another selected rule's
    ``replaces``.

    Rationale: if rule R declares ``replaces=("S",)`` and both R and S
    end up in the selection (e.g. ``--rules=all``, ``xindex,modern``),
    running both double-reports the same diagnostic under two ids.
    The replacement is by definition the more accurate detector — it
    wins. Users who need to compare can request the legacy rule
    explicitly with ``--rules=M-XINDX-NN`` (alone, with no
    replacement in the selection, suppression is a no-op).
    """
    selected_ids = {r.id for r in rules}
    suppressed: set[str] = set()
    for r in rules:
        for replaced in r.replaces:
            if replaced in selected_ids:
                suppressed.add(replaced)
    return [r for r in rules if r.id not in suppressed]


def select_rules(rule_filter: str = DEFAULT_PROFILE) -> list[Rule]:
    """Resolve a rule filter to a concrete rule list.

    The filter is one of:

      - a single profile name (``"default"``, ``"xindex"``, ``"vista"``,
        ``"sac"``, ``"modern"``, ``"all"``, …) — looked up in
        :mod:`m_cli.lint.profiles`.
      - a comma-separated list mixing profile names and rule IDs —
        each token is resolved as a profile first, falling back to
        rule-ID lookup. The result is the union, deduplicated by
        rule id and sorted (as ``all_rules()`` returns).

    Examples::

        select_rules("default")                 # default profile
        select_rules("xindex,vista")            # union of two profiles
        select_rules("M-XINDX-013,M-XINDX-019") # explicit rule IDs
        select_rules("xindex,M-MOD-001")        # mix profile + rule id

    Raises ``ValueError`` when any token resolves to neither a known
    profile nor a registered rule ID. The error message lists every
    registered profile so users can self-correct without reading the
    docs.

    Post-resolution: rules listed in another selected rule's
    ``replaces`` are dropped (see :func:`_apply_replaces_suppression`).
    """
    rule_filter = rule_filter.strip()
    # Single token, no comma, no `M-` prefix → must be a profile name.
    if "," not in rule_filter and not rule_filter.startswith("M-"):
        if get_profile(rule_filter) is None:
            known = ", ".join(p.name for p in list_profiles())
            raise ValueError(
                f"unknown profile {rule_filter!r} (known profiles: {known})"
            )
        return _apply_replaces_suppression(resolve_profile(rule_filter))

    # Comma list (or a single literal rule ID): each token is either a
    # profile name or a rule ID.
    tokens = [t.strip() for t in rule_filter.split(",") if t.strip()]
    known_ids = {r.id: r for r in all_rules()}
    selected: dict[str, Rule] = {}
    unknown: list[str] = []
    for tok in tokens:
        profile = get_profile(tok)
        if profile is not None:
            for r in profile.selector():
                selected[r.id] = r
        elif tok in known_ids:
            selected[tok] = known_ids[tok]
        else:
            unknown.append(tok)
    if unknown:
        known_profiles = ", ".join(p.name for p in list_profiles())
        raise ValueError(
            f"unknown profile / rule id(s): {sorted(unknown)} "
            f"(known profiles: {known_profiles}; or use M-XINDX-NN / M-MOD-NN ids)"
        )
    return _apply_replaces_suppression([r for _, r in sorted(selected.items())])


def lint_source(
    path: Path,
    src: bytes,
    rules: Iterable[Rule],
    *,
    ctx: "LintContext | None" = None,
    workspace=None,
) -> list[Diagnostic]:
    """Run a set of rules over a source and return sorted diagnostics.

    The parse tree is walked exactly once per file (via ``NodeIndex``)
    and shared across every rule — eliminating the previous N-rules ×
    N-walks redundancy.

    ``ctx`` is an optional :class:`m_cli.lint.context.LintContext`
    bundling per-run knobs: thresholds, target engine, workspace
    index, resolved Config. Rules with ``needs_context=True`` receive
    it as a 5th positional arg. When ``ctx`` is ``None`` and any rule
    needs it, a defaults-only context is constructed on the fly so
    that simple callers (``select_rules`` smoke tests, etc.) Just Work.

    ``workspace`` is a back-compat shortcut: when ``ctx`` is ``None``
    and ``workspace`` is given, a one-shot context is built around it
    so existing test code keeps working without rewrites.
    """
    from m_cli.lint.context import LintContext, ensure_context

    if ctx is None and workspace is not None:
        ctx = LintContext(thresholds={}, workspace=workspace)
    effective_ctx = ensure_context(ctx)

    tree = parse(src)
    index = NodeIndex(tree)
    diags: list[Diagnostic] = []
    for rule in rules:
        try:
            if rule.needs_context:
                diags.extend(rule.check(src, tree, path, index, effective_ctx))
            else:
                diags.extend(rule.check(src, tree, path, index))
        except Exception as e:
            # Don't let one buggy rule crash the whole lint pass.
            diags.append(_rule_crash_diagnostic(rule, path, e))

    # Apply ``; m-lint: disable=...`` inline-suppression directives.
    # Crash diagnostics are never suppressed — the user always wants
    # to know when a rule is misbehaving.
    suppressions = parse_directives(src)
    if suppressions.file_disable or suppressions.line_disable:
        diags = [
            d
            for d in diags
            if d.rule_id == "M-INTERNAL-RULE-CRASH"
            or not suppressions.is_suppressed(d.line, d.rule_id)
        ]

    diags.sort(key=lambda d: (d.path.as_posix(), d.line, d.column, d.rule_id))
    return diags


def _rule_crash_diagnostic(rule: Rule, path: Path, exc: Exception) -> Diagnostic:
    from m_cli.lint.diagnostic import Severity

    return Diagnostic(
        rule_id="M-INTERNAL-RULE-CRASH",
        severity=Severity.WARNING,
        message=f"Rule {rule.id} crashed: {type(exc).__name__}: {exc}",
        path=path,
        line=1,
        column=1,
    )
