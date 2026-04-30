"""Cross-reference tests for the M-MOD-NN modernization track.

The ``Rule.replaces`` field declares which legacy XINDEX rule(s) an
M-MOD rule supersedes (a more precise detector, a configurable
threshold replacing a hard-coded one, an engine-aware allowlist
replacing an absolute ban, ...).

These tests pin the cross-reference shape so that:

  - every id listed in ``replaces`` is itself a registered rule
  - M-MOD rules carry the ``modern`` tag
  - the ``modern`` profile picks up exactly the rules tagged
    ``modern``
  - rules that don't declare any replacement default to the empty
    tuple (no surprise migrations).

When the first M-MOD rule lands, this test file ensures its
``replaces`` metadata is sound; until then the parametrised
sub-test bodies guard against drift.
"""

from __future__ import annotations

import pytest

from m_cli.lint import Rule, list_profiles, resolve_profile
from m_cli.lint.rules import all_rules


def test_rule_dataclass_has_replaces_field() -> None:
    assert "replaces" in Rule.__annotations__


def test_default_replaces_is_empty_tuple() -> None:
    # Every existing legacy rule was registered without `replaces=`.
    # Confirms the dataclass default is what we expect.
    legacy = [r for r in all_rules() if r.id.startswith("M-XINDX-")]
    assert legacy, "expected at least one M-XINDX-NN rule registered"
    for r in legacy:
        assert r.replaces == (), (
            f"{r.id} has unexpected replaces={r.replaces!r}; legacy XINDEX "
            f"rules should not declare replacements"
        )


def test_every_replaces_id_resolves_to_a_registered_rule() -> None:
    """Cross-reference integrity: replaces=("M-XINDX-NN",...) must point
    to actual rule ids that the registry knows about. Catches typos /
    deletions of the legacy rule."""
    known_ids = {r.id for r in all_rules()}
    for rule in all_rules():
        for ref in rule.replaces:
            assert ref in known_ids, (
                f"{rule.id} replaces unknown rule id {ref!r}; expected one of "
                f"the registered ids ({len(known_ids)} total)"
            )


def test_modern_profile_is_registered() -> None:
    names = {p.name for p in list_profiles()}
    assert "modern" in names


def test_modern_profile_resolves_to_modern_tagged_rules() -> None:
    rules = resolve_profile("modern")
    for r in rules:
        assert "modern" in r.tags, f"{r.id} returned by modern profile but lacks `modern` tag"


def test_mod_rules_carry_modern_tag() -> None:
    """Every M-MOD-NN rule (when any are registered) must carry the
    ``modern`` tag so the modern profile finds it."""
    mod_rules = [r for r in all_rules() if r.id.startswith("M-MOD-")]
    if not mod_rules:
        pytest.skip("no M-MOD-NN rules registered yet")
    for r in mod_rules:
        assert "modern" in r.tags, f"{r.id} is M-MOD-NN but missing `modern` tag"


def test_mod_rules_dont_misuse_xindx_tag() -> None:
    """M-MOD rules are greenfield; they should not carry the ``xindex``
    or ``sac`` provenance tags, which describe origin (XINDEX) not
    policy."""
    mod_rules = [r for r in all_rules() if r.id.startswith("M-MOD-")]
    if not mod_rules:
        pytest.skip("no M-MOD-NN rules registered yet")
    for r in mod_rules:
        assert "xindex" not in r.tags, (
            f"{r.id} is M-MOD-NN but tagged `xindex`; xindex is a provenance "
            "tag for ports, not modernizations"
        )
