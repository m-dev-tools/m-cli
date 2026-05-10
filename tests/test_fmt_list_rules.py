"""Tests for `m fmt --list-rules --json`.

Mirrors `m lint --list-rules --json` (D6) but for the fmt rule
registry. Source of truth = :mod:`m_cli.fmt.rules` (the FmtRule
registry) plus the fmt preset functions (canonical / pythonic /
pythonic-lower / compact / sac), inverted to give each rule a sorted
``presets`` list.

Drives ``dist/fmt-rules.json`` — exposed by tier-1 ``repo.meta.json``
as the ``fmt_rules`` payload.

Per .github/docs/phase0-plan.md § D7.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from m_cli.cli import main
from m_cli.fmt.list_rules import build_fmt_inventory, list_rules_command
from m_cli.fmt.rules import all_rules


def test_build_fmt_inventory_returns_list_of_rule_dicts():
    inv = build_fmt_inventory()
    assert isinstance(inv, list)
    assert inv, "fmt inventory must be non-empty"
    for entry in inv:
        assert isinstance(entry, dict)


def test_each_entry_has_required_fields():
    inv = build_fmt_inventory()
    for entry in inv:
        assert isinstance(entry["id"], str) and entry["id"]
        assert isinstance(entry["title"], str) and entry["title"]
        assert isinstance(entry["description"], str) and entry["description"]
        assert isinstance(entry["presets"], list)
        for p in entry["presets"]:
            assert isinstance(p, str)


def test_inventory_matches_registry_size():
    inv = build_fmt_inventory()
    assert len(inv) == len(all_rules())


def test_inventory_entries_sorted_by_id():
    inv = build_fmt_inventory()
    ids = [e["id"] for e in inv]
    assert ids == sorted(ids), "inventory must be sorted by id for stable diffs"


def test_trim_trailing_whitespace_present_with_canonical_preset():
    inv = build_fmt_inventory()
    by_id = {e["id"]: e for e in inv}
    assert "trim-trailing-whitespace" in by_id
    rule = by_id["trim-trailing-whitespace"]
    assert "canonical" in rule["presets"]


def test_uppercase_command_keywords_present():
    inv = build_fmt_inventory()
    by_id = {e["id"]: e for e in inv}
    assert "uppercase-command-keywords" in by_id
    assert "canonical" in by_id["uppercase-command-keywords"]["presets"]


def test_presets_reverse_index_consistent():
    """A rule's `presets` list must equal the set of presets whose
    function actually returns the rule."""
    from m_cli.fmt.rules import (
        canonical_rules,
        compact_rules,
        pythonic_lower_rules,
        pythonic_rules,
        sac_rules,
    )

    presets = {
        "canonical": canonical_rules(),
        "pythonic": pythonic_rules(),
        "pythonic-lower": pythonic_lower_rules(),
        "compact": compact_rules(),
        "sac": sac_rules(),
    }
    expected: dict[str, set[str]] = {}
    for preset_name, rules in presets.items():
        for r in rules:
            expected.setdefault(r.id, set()).add(preset_name)

    inv = build_fmt_inventory()
    for entry in inv:
        actual = set(entry["presets"])
        exp = expected.get(entry["id"], set())
        assert actual == exp, (
            f"{entry['id']}: presets mismatch — got {sorted(actual)} expected {sorted(exp)}"
        )


def test_presets_lists_are_sorted():
    inv = build_fmt_inventory()
    for entry in inv:
        assert entry["presets"] == sorted(entry["presets"])


def test_list_rules_command_emits_json():
    import argparse

    args = argparse.Namespace()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = list_rules_command(args)
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload == build_fmt_inventory()


def test_m_fmt_list_rules_json_dispatcher_exit_zero(capsys):
    """End-to-end via the dispatcher: `m fmt --list-rules --json`."""
    rc = main(["fmt", "--list-rules", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert isinstance(payload, list)
    ids = {e["id"] for e in payload}
    assert "trim-trailing-whitespace" in ids
    assert "uppercase-command-keywords" in ids


def test_list_rules_implies_json_phase0(capsys):
    rc = main(["fmt", "--list-rules"])
    assert rc == 0
    out = capsys.readouterr().out
    json.loads(out)


def test_build_fmt_inventory_is_deterministic():
    a = build_fmt_inventory()
    b = build_fmt_inventory()
    assert a == b
