"""Orchestrate lint rules over a source file.

`lint_source(path, src, rule_filter)` parses the source, runs each
selected rule, and returns a sorted list of Diagnostics.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from m_cli.lint._index import NodeIndex
from m_cli.lint.diagnostic import Diagnostic
from m_cli.lint.rules import Rule, all_rules, rules_by_tag
from m_cli.parser import parse


def fixer_for(rule_id: str) -> str | None:
    """Return the ``m fmt`` rule id that auto-fixes ``rule_id``, if any.

    Public helper for tooling consumers (LSP wrapper, CI integrations)
    that want to resolve lint findings to their auto-fixers without
    importing the rule registry. Returns ``None`` when the rule is
    unknown or has no auto-fix.
    """
    rule = next((r for r in all_rules() if r.id == rule_id), None)
    return rule.fixer_id if rule is not None else None


def select_rules(rule_filter: str = "xindex") -> list[Rule]:
    """Pick rules by family or comma-separated id list.

    Accepted forms:
      - 'all'       — every registered rule
      - 'xindex'    — all rules tagged 'xindex'
      - 'sac'       — all rules tagged 'sac'
      - 'M-XINDX-013,M-XINDX-019' — explicit list of rule IDs
    """
    rule_filter = rule_filter.strip()
    if rule_filter == "all":
        return all_rules()
    # If it looks like a tag (no commas, no dashes), treat as tag
    if "," not in rule_filter and not rule_filter.startswith("M-"):
        return rules_by_tag(rule_filter)
    # Explicit comma-separated list of rule IDs
    requested = {r.strip() for r in rule_filter.split(",") if r.strip()}
    out = [r for r in all_rules() if r.id in requested]
    missing = requested - {r.id for r in out}
    if missing:
        raise ValueError(f"unknown rule id(s): {sorted(missing)}")
    return out


def lint_source(path: Path, src: bytes, rules: Iterable[Rule]) -> list[Diagnostic]:
    """Run a set of rules over a source and return sorted diagnostics.

    The parse tree is walked exactly once per file (via ``NodeIndex``)
    and shared across every rule — eliminating the previous N-rules ×
    N-walks redundancy.
    """
    tree = parse(src)
    index = NodeIndex(tree)
    diags: list[Diagnostic] = []
    for rule in rules:
        try:
            diags.extend(rule.check(src, tree, path, index))
        except Exception as e:
            # Don't let one buggy rule crash the whole lint pass.
            diags.append(_rule_crash_diagnostic(rule, path, e))
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
