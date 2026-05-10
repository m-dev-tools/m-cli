"""`m lint --list-rules --json` — emit the lint rule inventory.

The inventory is derived from the in-process registries:

  * :mod:`m_cli.lint.rules` — every registered :class:`Rule`
  * :mod:`m_cli.lint.profiles` — every registered :class:`Profile`,
    inverted to give each rule a sorted ``profiles`` list.

The output drives ``dist/lint-rules.json`` — exposed by tier-1
``repo.meta.json`` as the ``lint_rules`` payload — and feeds editor
plugins, CI dashboards, and AI agents that need to reason about the
rule set without running the linter.

Phase 0 omits per-rule docs URLs; Phase 1 will land an opt-in
``docs_url`` slot once the rule-doc site is live.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from m_cli.lint.profiles import list_profiles
from m_cli.lint.rules import Rule, all_rules


def _profiles_index() -> dict[str, list[str]]:
    """Reverse-index every profile's selector into a `rule_id → [profile, ...]`
    map. Each list is sorted for deterministic output."""
    index: dict[str, set[str]] = {}
    for profile in list_profiles():
        try:
            rules = profile.selector()
        except Exception:  # pragma: no cover — defensive
            continue
        for rule in rules:
            index.setdefault(rule.id, set()).add(profile.name)
    return {rid: sorted(names) for rid, names in index.items()}


def _entry_for(rule: Rule, profiles: list[str]) -> dict[str, Any]:
    return {
        "id": rule.id,
        "severity": rule.severity.value,
        "category": rule.category.value,
        "tags": sorted(rule.tags),
        "profiles": profiles,
        "fixer_id": rule.fixer_id,
        "description": rule.title,
        "replaces": list(rule.replaces),
    }


def build_rule_inventory() -> list[dict[str, Any]]:
    """Return the full lint rule inventory as a JSON-ready list,
    sorted by rule id for stable ``git diff`` output on the
    generated ``dist/lint-rules.json``."""
    profile_idx = _profiles_index()
    return [_entry_for(r, profile_idx.get(r.id, [])) for r in all_rules()]


def list_rules_command(_args: argparse.Namespace) -> int:
    """`m lint --list-rules` handler — JSON-only output (Phase 0)."""
    payload = build_rule_inventory()
    json.dump(payload, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")
    return 0
