"""`m fmt --list-rules --json` — emit the fmt rule inventory.

Sister of :mod:`m_cli.lint.list_rules`. Source of truth = the in-process
:class:`FmtRule` registry plus the named preset functions
(canonical / pythonic / pythonic-lower / compact / sac), inverted to
give each rule a sorted ``presets`` list.

Drives ``dist/fmt-rules.json`` — exposed by tier-1 ``repo.meta.json``
as the ``fmt_rules`` payload. Editor plugins, CI dashboards, and AI
agents consume it to discover the available formatter rules and which
preset bundles include each one.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from m_cli.fmt.rules import (
    FmtRule,
    all_rules,
    canonical_rules,
    compact_rules,
    pythonic_lower_rules,
    pythonic_rules,
    sac_rules,
)

_PRESET_FUNCTIONS = {
    "canonical": canonical_rules,
    "pythonic": pythonic_rules,
    "pythonic-lower": pythonic_lower_rules,
    "compact": compact_rules,
    "sac": sac_rules,
}


def _presets_index() -> dict[str, list[str]]:
    """Reverse-index every fmt preset into a `rule_id → [preset, ...]`
    map. Each list is sorted for deterministic output."""
    index: dict[str, set[str]] = {}
    for name, fn in _PRESET_FUNCTIONS.items():
        try:
            rules = fn()
        except Exception:  # pragma: no cover — defensive
            continue
        for rule in rules:
            index.setdefault(rule.id, set()).add(name)
    return {rid: sorted(names) for rid, names in index.items()}


def _entry_for(rule: FmtRule, presets: list[str]) -> dict[str, Any]:
    return {
        "id": rule.id,
        "title": rule.title,
        "description": rule.description,
        "presets": presets,
    }


def build_fmt_inventory() -> list[dict[str, Any]]:
    """Return the full fmt rule inventory as a JSON-ready list,
    sorted by rule id for stable ``git diff`` output on the
    generated ``dist/fmt-rules.json``."""
    preset_idx = _presets_index()
    rules_sorted = sorted(all_rules(), key=lambda r: r.id)
    return [_entry_for(r, preset_idx.get(r.id, [])) for r in rules_sorted]


def list_rules_command(_args: argparse.Namespace) -> int:
    """`m fmt --list-rules` handler — JSON-only output (Phase 0)."""
    payload = build_fmt_inventory()
    json.dump(payload, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")
    return 0
