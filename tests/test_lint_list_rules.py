"""Tests for `m lint --list-rules --json`.

The flag emits a machine-readable inventory of every registered lint
rule. Source of truth = the in-process `Rule` registry, plus the
`Profile` registry for the `profiles` reverse-index. Drives
``dist/lint-rules.json``, exposed by tier-1 ``repo.meta.json``.

Per .github/docs/phase0-plan.md § D6.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from m_cli.cli import main
from m_cli.lint.list_rules import build_rule_inventory, list_rules_command
from m_cli.lint.rules import all_rules


def test_build_rule_inventory_returns_list_of_rule_dicts():
    inv = build_rule_inventory()
    assert isinstance(inv, list)
    assert inv, "rule inventory must be non-empty"
    for entry in inv:
        assert isinstance(entry, dict)


def test_each_rule_entry_has_required_fields():
    """Per the Phase 0 contract: id, severity, category, tags, profiles,
    fixer_id (str or None), description. All field keys are required;
    values are typed."""
    inv = build_rule_inventory()
    for entry in inv:
        assert isinstance(entry["id"], str) and entry["id"]
        assert isinstance(entry["severity"], str) and entry["severity"]
        assert isinstance(entry["category"], str) and entry["category"]
        assert isinstance(entry["tags"], list)
        for t in entry["tags"]:
            assert isinstance(t, str)
        assert isinstance(entry["profiles"], list)
        for p in entry["profiles"]:
            assert isinstance(p, str)
        assert "fixer_id" in entry  # may be None
        assert entry["fixer_id"] is None or isinstance(entry["fixer_id"], str)
        assert isinstance(entry["description"], str) and entry["description"]


def test_inventory_matches_registry_size():
    inv = build_rule_inventory()
    assert len(inv) == len(all_rules())


def test_inventory_entries_sorted_by_id():
    inv = build_rule_inventory()
    ids = [e["id"] for e in inv]
    assert ids == sorted(ids), "inventory must be sorted by rule id for stable diffs"


def test_severity_values_are_lowercase_canonical():
    inv = build_rule_inventory()
    for entry in inv:
        assert entry["severity"] in {"error", "warning", "style", "info"}


def test_category_values_are_lowercase_canonical():
    inv = build_rule_inventory()
    valid = {
        "bug",
        "security",
        "concurrency",
        "performance",
        "style",
        "complexity",
        "documentation",
        "portability",
        "modernization",
    }
    for entry in inv:
        assert entry["category"] in valid, f"unknown category: {entry['category']}"


def test_xindx_013_present_with_expected_metadata():
    """Spot-check a well-known rule. M-XINDX-013 is the canonical
    fixable XINDEX rule (trailing whitespace; fixed by `m fmt
    trim-trailing-whitespace`)."""
    inv = build_rule_inventory()
    by_id = {e["id"]: e for e in inv}
    assert "M-XINDX-013" in by_id
    rule = by_id["M-XINDX-013"]
    assert rule["severity"] == "style"
    assert rule["category"] == "style"
    assert rule["fixer_id"] == "trim-trailing-whitespace"
    assert "xindex" in rule["tags"]
    assert "xindex" in rule["profiles"]
    assert "all" in rule["profiles"]


def test_profiles_reverse_index_consistent_with_profile_registry():
    """A rule's `profiles` list must equal the set of profiles whose
    selector includes the rule. This is the contract the LSP / IDEs
    will rely on."""
    from m_cli.lint.profiles import list_profiles

    inv = build_rule_inventory()
    by_id = {e["id"]: e for e in inv}
    expected: dict[str, set[str]] = {rid: set() for rid in by_id}
    for profile in list_profiles():
        for rule in profile.selector():
            expected.setdefault(rule.id, set()).add(profile.name)
    for rid, entry in by_id.items():
        assert set(entry["profiles"]) == expected[rid], (
            f"{rid}: profiles mismatch — "
            f"got {sorted(entry['profiles'])} expected {sorted(expected[rid])}"
        )


def test_profiles_lists_are_sorted():
    inv = build_rule_inventory()
    for entry in inv:
        assert entry["profiles"] == sorted(entry["profiles"])
        assert entry["tags"] == sorted(entry["tags"])


def test_list_rules_command_emits_json():
    import argparse

    args = argparse.Namespace()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = list_rules_command(args)
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload == build_rule_inventory()


def test_m_lint_list_rules_json_dispatcher_exit_zero(capsys):
    """End-to-end via the dispatcher: `m lint --list-rules --json`."""
    rc = main(["lint", "--list-rules", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert isinstance(payload, list)
    ids = {e["id"] for e in payload}
    assert "M-XINDX-013" in ids


def test_list_rules_implies_json_phase0(capsys):
    """Phase 0: `m lint --list-rules` (no --json) still emits JSON.
    Future formats can land in Phase 1."""
    rc = main(["lint", "--list-rules"])
    assert rc == 0
    out = capsys.readouterr().out
    json.loads(out)  # must parse


def test_build_rule_inventory_is_deterministic():
    """The dist/lint-rules.json drift gate depends on identical
    output across runs."""
    a = build_rule_inventory()
    b = build_rule_inventory()
    assert a == b
