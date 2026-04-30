"""Tests for the lint profile registry and CLI integration.

Profiles are the architectural separation between m-cli's vendor- and
dialect-neutral lint engine and the opinionated rule sets that ship
on top. These tests pin:

  - the built-in profile names and their selectors
  - that ``select_rules`` accepts every profile name + comma-list
  - that ``--list-profiles`` lists every registered profile
  - that the default profile is engine-neutral by name (``"default"``,
    not ``"xindex"``)
"""

from __future__ import annotations

import argparse

import pytest

from m_cli.config import Config
from m_cli.lint import (
    DEFAULT_PROFILE,
    Profile,
    get_profile,
    list_profiles,
    register_profile,
    resolve_profile,
    select_rules,
)
from m_cli.lint.cli import _print_profiles, _resolve_lint_rules, _resolve_target_engine

# ---------------------------------------------------------------------------
# Built-in profile registry
# ---------------------------------------------------------------------------


class TestBuiltinProfiles:
    def test_default_profile_name_is_engine_neutral(self):
        # The whole point of this module — the user-facing default is
        # not named after a VA tool.
        assert DEFAULT_PROFILE == "default"

    def test_registered_profiles(self):
        names = {p.name for p in list_profiles()}
        # The built-ins always ship.
        assert {
            "default",
            "xindex",
            "vista",
            "sac",
            "modern",
            "pedantic",
            "pythonic",
            "all",
        } <= names

    def test_default_resolves_to_some_rules(self):
        rules = resolve_profile("default")
        assert len(rules) > 0

    def test_xindex_only_pulls_xindex_tagged_rules(self):
        rules = resolve_profile("xindex")
        assert all("xindex" in r.tags for r in rules)
        assert len(rules) > 0

    def test_all_pulls_every_rule(self):
        from m_cli.lint.rules import all_rules

        assert {r.id for r in resolve_profile("all")} == {r.id for r in all_rules()}

    def test_sac_pulls_sac_tagged_rules(self):
        rules = resolve_profile("sac")
        assert all("sac" in r.tags for r in rules)

    def test_unknown_profile_raises(self):
        with pytest.raises(KeyError):
            resolve_profile("does-not-exist")


# ---------------------------------------------------------------------------
# SAC classification — pinned per the policy in rules.py module docstring.
# Adding or removing a SAC tag requires updating these sets and the
# rationale in rules.py.
# ---------------------------------------------------------------------------


# 31 XINDEX rules that map to a documented SAC section.
EXPECTED_SAC_RULE_IDS = frozenset(
    {
        "M-XINDX-002",  # non-Kernel Z command
        "M-XINDX-017",  # first-line label = routine name
        "M-XINDX-019",  # line ≤ 245 bytes
        "M-XINDX-020",  # VIEW command restricted
        "M-XINDX-022",  # exclusive KILL
        "M-XINDX-023",  # unargumented KILL
        "M-XINDX-024",  # KILL of unsubscripted global
        "M-XINDX-025",  # BREAK command
        "M-XINDX-026",  # exclusive / unargumented NEW
        "M-XINDX-027",  # $VIEW function
        "M-XINDX-028",  # $Z* ISV
        "M-XINDX-029",  # CLOSE → ZISC
        "M-XINDX-030",  # LABEL+OFFSET
        "M-XINDX-031",  # $Z* function
        "M-XINDX-032",  # HALT → XUSCLEAN
        "M-XINDX-033",  # READ timeout required
        "M-XINDX-034",  # OPEN → ZIS
        "M-XINDX-035",  # routine ≤ 20000 bytes
        "M-XINDX-036",  # JOB → TASKMAN
        "M-XINDX-041",  # */# READ format discouraged
        "M-XINDX-044",  # 2nd line SAC
        "M-XINDX-045",  # SET to %global
        "M-XINDX-047",  # uppercase commands required
        "M-XINDX-050",  # extended global reference
        "M-XINDX-054",  # $SYSTEM Kernel-only
        "M-XINDX-056",  # patch number on second line
        "M-XINDX-057",  # uppercase locals required
        "M-XINDX-058",  # code line ≤ 15000 bytes
        "M-XINDX-060",  # LOCK timeout required
        "M-XINDX-061",  # incremental LOCK required
        "M-XINDX-062",  # first-line SAC
    }
)

# 11 XINDEX-internal rules: bug detection, parse failures, hygiene, or
# control-flow smells with no documented SAC section.
EXPECTED_NON_SAC_RULE_IDS = frozenset(
    {
        "M-XINDX-007",  # undefined routine (cross-routine bug)
        "M-XINDX-008",  # undefined label (cross-routine bug)
        "M-XINDX-009",  # dead code after QUIT/HALT/GOTO
        "M-XINDX-013",  # trailing whitespace (hygiene)
        "M-XINDX-014",  # missing label (bug)
        "M-XINDX-015",  # duplicate label (bug)
        "M-XINDX-018",  # control character (hygiene)
        "M-XINDX-021",  # parse error
        "M-XINDX-042",  # null line
        "M-XINDX-049",  # unused label
        "M-XINDX-051",  # empty IF/ELSE
    }
)

# 8 VA-Kernel-specific rules: SAC mandates that require Kernel APIs
# (XUSCLEAN, ZIS, ZISC, TASKMAN, $SYSTEM Kernel-only) or VistA banner
# conventions. Tagged ("xindex", "sac", "vista"); excluded from the
# `xindex` and `sac` profiles via the `_portable()` selector and surfaced
# only by `--rules=vista`.
EXPECTED_VISTA_RULE_IDS = frozenset(
    {
        "M-XINDX-029",  # CLOSE → ^%ZISC
        "M-XINDX-032",  # HALT → ^XUSCLEAN
        "M-XINDX-034",  # OPEN → ^%ZIS
        "M-XINDX-036",  # JOB → TASKMAN
        "M-XINDX-044",  # 2nd line SAC banner
        "M-XINDX-054",  # $SYSTEM Kernel-only
        "M-XINDX-056",  # patch number on second line
        "M-XINDX-062",  # 1st line SAC banner
    }
)


class TestSacClassification:
    def test_sac_tag_membership_matches_policy(self):
        # The `sac` tag is provenance/policy: which rules *are* SAC mandates.
        # All 31 carry `sac` regardless of which profile surfaces them.
        from m_cli.lint.rules import all_rules

        sac_tagged = {r.id for r in all_rules() if "sac" in r.tags}
        assert sac_tagged == EXPECTED_SAC_RULE_IDS

    def test_sac_profile_excludes_vista(self):
        # The `sac` *profile* drops VistA-Kernel rules — those are SAC
        # mandates, but the Kernel APIs they require don't exist outside
        # VistA, so flagging them is pure noise for non-VA shops.
        sac_profile = {r.id for r in resolve_profile("sac")}
        assert sac_profile == EXPECTED_SAC_RULE_IDS - EXPECTED_VISTA_RULE_IDS

    def test_xindex_minus_sac_is_the_documented_smell_set(self):
        xindex_ids = {r.id for r in resolve_profile("xindex")}
        non_sac_in_xindex = xindex_ids - EXPECTED_SAC_RULE_IDS
        assert non_sac_in_xindex == EXPECTED_NON_SAC_RULE_IDS

    def test_every_sac_profile_rule_is_also_in_xindex_profile(self):
        # Both profiles exclude vista, so the inclusion holds at profile
        # level too. (At the tag level, `sac` is a subset of `xindex`
        # provenance — see test_sac_tag_membership_matches_policy.)
        sac_ids = {r.id for r in resolve_profile("sac")}
        xindex_ids = {r.id for r in resolve_profile("xindex")}
        assert sac_ids <= xindex_ids

    def test_classification_partitions_xindex_profile(self):
        # The `xindex` profile is exactly (SAC-portable ∪ non-SAC), where
        # SAC-portable = SAC-tagged minus vista-tagged. Disjoint by
        # construction.
        xindex_ids = {r.id for r in resolve_profile("xindex")}
        sac_portable = EXPECTED_SAC_RULE_IDS - EXPECTED_VISTA_RULE_IDS
        assert sac_portable.isdisjoint(EXPECTED_NON_SAC_RULE_IDS)
        assert xindex_ids == sac_portable | EXPECTED_NON_SAC_RULE_IDS


# ---------------------------------------------------------------------------
# vista profile — the 8 VA-Kernel-specific rules
# ---------------------------------------------------------------------------


class TestVistaProfile:
    def test_vista_profile_membership_matches_policy(self):
        vista_ids = {r.id for r in resolve_profile("vista")}
        assert vista_ids == EXPECTED_VISTA_RULE_IDS

    def test_vista_rules_carry_all_three_tags(self):
        # VA-Kernel rules came from XINDEX, are SAC mandates, AND target
        # VistA — all three tags apply.
        from m_cli.lint.rules import all_rules

        for r in all_rules():
            if r.id in EXPECTED_VISTA_RULE_IDS:
                assert "xindex" in r.tags, f"{r.id} missing xindex tag"
                assert "sac" in r.tags, f"{r.id} missing sac tag"
                assert "vista" in r.tags, f"{r.id} missing vista tag"

    def test_xindex_profile_does_not_surface_vista_rules(self):
        # Engine-neutrality of xindex profile: VistA-Kernel rules are
        # opt-in via the vista profile, never via xindex.
        xindex_ids = {r.id for r in resolve_profile("xindex")}
        assert xindex_ids.isdisjoint(EXPECTED_VISTA_RULE_IDS)

    def test_default_profile_does_not_surface_vista_rules(self):
        # The `default` profile aliases the xindex selector.
        default_ids = {r.id for r in resolve_profile("default")}
        assert default_ids.isdisjoint(EXPECTED_VISTA_RULE_IDS)

    def test_all_profile_includes_vista_rules(self):
        # `--rules=all` is the escape hatch — every registered rule fires
        # regardless of profile membership.
        all_ids = {r.id for r in resolve_profile("all")}
        assert EXPECTED_VISTA_RULE_IDS <= all_ids


# ---------------------------------------------------------------------------
# Pedantic profile split — `default` is M-MOD minus the four pedantic
# style rules. Pinned per the validation findings on the modern corpus
# (M-MOD-031/032 alone account for ~74% of all `modern`-profile findings).
# Adding or removing a `pedantic` tag requires updating the set below.
# ---------------------------------------------------------------------------


EXPECTED_PEDANTIC_RULE_IDS = frozenset(
    {
        "M-MOD-009",  # commands per line
        "M-MOD-028",  # label without docstring
        "M-MOD-031",  # magic numeric literal
        "M-MOD-032",  # single-letter local variable
    }
)


class TestPedanticSplit:
    def test_pedantic_profile_membership_matches_policy(self):
        ids = {r.id for r in resolve_profile("pedantic")}
        assert ids == EXPECTED_PEDANTIC_RULE_IDS

    def test_pedantic_rules_carry_modern_tag(self):
        # Pedantic rules ARE part of the M-MOD track — the `pedantic`
        # tag layers on top of `modern`. So `--rules=modern` still
        # picks them up.
        for r in resolve_profile("pedantic"):
            assert "modern" in r.tags, f"{r.id} pedantic but missing `modern` tag"

    def test_default_excludes_pedantic_rules(self):
        default_ids = {r.id for r in resolve_profile("default")}
        assert default_ids.isdisjoint(EXPECTED_PEDANTIC_RULE_IDS)

    def test_modern_includes_pedantic_rules(self):
        modern_ids = {r.id for r in resolve_profile("modern")}
        assert EXPECTED_PEDANTIC_RULE_IDS <= modern_ids

    def test_default_plus_pedantic_equals_modern(self):
        # The split is exhaustive: default ∪ pedantic = modern.
        default_ids = {r.id for r in resolve_profile("default")}
        pedantic_ids = {r.id for r in resolve_profile("pedantic")}
        modern_ids = {r.id for r in resolve_profile("modern")}
        assert default_ids | pedantic_ids == modern_ids

    def test_default_no_longer_aliases_xindex(self):
        # Architectural commitment: `default` is the M-MOD curated set,
        # NOT the legacy XINDEX engine-neutral subset. VA shops use
        # `--rules=xindex` explicitly.
        default_ids = {r.id for r in resolve_profile("default")}
        xindex_ids = {r.id for r in resolve_profile("xindex")}
        # default is M-MOD-only; xindex is M-XINDX-only.
        assert all(rid.startswith("M-MOD-") for rid in default_ids)
        assert all(rid.startswith("M-XINDX-") for rid in xindex_ids)
        assert default_ids.isdisjoint(xindex_ids)


# ---------------------------------------------------------------------------
# Pythonic profile — Python-style preset for newcomers from Python.
# Same rules as `modern` (all M-MOD including pedantic) plus tighter
# thresholds matching Python community norms (PEP-8-ish line length,
# one-statement-per-line, McCabe ~10).
# ---------------------------------------------------------------------------


class TestPythonicProfile:
    def test_pythonic_rule_set_matches_modern(self):
        pythonic_ids = {r.id for r in resolve_profile("pythonic")}
        modern_ids = {r.id for r in resolve_profile("modern")}
        assert pythonic_ids == modern_ids

    def test_pythonic_includes_pedantic_rules(self):
        # Python culture wants long names, no magic numbers, etc. —
        # the pedantic rules ARE the Python style.
        pythonic_ids = {r.id for r in resolve_profile("pythonic")}
        for rid in ("M-MOD-009", "M-MOD-028", "M-MOD-031", "M-MOD-032"):
            assert rid in pythonic_ids

    def test_pythonic_carries_threshold_defaults(self):
        from m_cli.lint.profiles import get_profile

        pythonic = get_profile("pythonic")
        assert pythonic is not None
        # Thresholds match the documented PEP-8-ish ceilings.
        assert pythonic.default_thresholds["line_length"] == 100
        assert pythonic.default_thresholds["commands_per_line"] == 1
        assert pythonic.default_thresholds["argument_count"] == 5
        assert pythonic.default_thresholds["cyclomatic"] == 10

    def test_default_profile_has_no_threshold_defaults(self):
        # Profiles without a preset return an empty dict — they don't
        # override the system-wide built-in thresholds.
        from m_cli.lint.profiles import get_profile

        default = get_profile("default")
        assert default is not None
        assert dict(default.default_thresholds) == {}


# ---------------------------------------------------------------------------
# Threshold layering: profile preset < config file < CLI flag.
# ---------------------------------------------------------------------------


class TestThresholdLayering:
    """``_resolve_thresholds`` layers profile presets, config, and CLI."""

    def test_profile_defaults_apply_when_no_other_overrides(self):
        from m_cli.lint.cli import _resolve_thresholds

        ns = argparse.Namespace(threshold=None)
        cfg = Config.empty()
        # Pretend pythonic is the active profile: pass its preset in.
        out = _resolve_thresholds(
            ns, cfg, profile_defaults={"line_length": 100}
        )
        assert out == {"line_length": 100}

    def test_config_overrides_profile_defaults(self):
        from m_cli.lint.cli import _resolve_thresholds

        ns = argparse.Namespace(threshold=None)
        cfg = Config(lint_thresholds={"line_length": 80})
        out = _resolve_thresholds(
            ns, cfg, profile_defaults={"line_length": 100, "cyclomatic": 10}
        )
        # config wins for line_length; profile's cyclomatic stays.
        assert out == {"line_length": 80, "cyclomatic": 10}

    def test_cli_overrides_config_and_profile(self):
        from m_cli.lint.cli import _resolve_thresholds

        ns = argparse.Namespace(threshold=["line_length=120"])
        cfg = Config(lint_thresholds={"line_length": 80})
        out = _resolve_thresholds(
            ns, cfg, profile_defaults={"line_length": 100, "cyclomatic": 10}
        )
        # CLI wins for line_length; profile's cyclomatic still present.
        assert out == {"line_length": 120, "cyclomatic": 10}

    def test_no_profile_defaults_falls_back_to_builtin(self):
        # Calling _resolve_thresholds without profile_defaults works
        # the same way it did before the layering change.
        from m_cli.lint.cli import _resolve_thresholds

        ns = argparse.Namespace(threshold=None)
        cfg = Config.empty()
        assert _resolve_thresholds(ns, cfg) == {}


# ---------------------------------------------------------------------------
# Profile registration (extension point)
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_and_lookup(self):
        from m_cli.lint.rules import all_rules

        name = "test-extension-profile"
        # First clean up if a prior test instance leaked one in.
        if get_profile(name) is not None:
            from m_cli.lint.profiles import _PROFILES

            _PROFILES.pop(name)
        register_profile(
            Profile(
                name=name,
                description="test fixture",
                selector=all_rules,
            )
        )
        assert get_profile(name) is not None
        # Tear down so subsequent tests see a clean registry.
        from m_cli.lint.profiles import _PROFILES

        _PROFILES.pop(name)

    def test_duplicate_registration_rejected(self):
        with pytest.raises(ValueError, match="duplicate profile"):
            register_profile(Profile(name="default", description="dup", selector=lambda: []))


# ---------------------------------------------------------------------------
# select_rules surface (public library API)
# ---------------------------------------------------------------------------


class TestSelectRulesSurface:
    def test_default_arg_is_default_profile(self):
        # No arg → DEFAULT_PROFILE → some rules.
        rules = select_rules()
        assert len(rules) > 0
        assert rules == resolve_profile(DEFAULT_PROFILE)

    def test_xindex_profile_works(self):
        rules = select_rules("xindex")
        assert all("xindex" in r.tags for r in rules)

    def test_unknown_profile_lists_known_ones(self):
        with pytest.raises(ValueError) as exc:
            select_rules("nonsense-profile")
        msg = str(exc.value)
        assert "nonsense-profile" in msg
        assert "default" in msg  # at least one known profile listed
        assert "xindex" in msg

    def test_comma_list_of_rule_ids(self):
        rules = select_rules("M-XINDX-013,M-XINDX-019")
        assert {r.id for r in rules} == {"M-XINDX-013", "M-XINDX-019"}

    def test_unknown_rule_id_raises(self):
        with pytest.raises(ValueError, match="unknown profile / rule"):
            select_rules("M-XINDX-99999")

    def test_mixed_profile_and_rule_ids_in_comma_list(self):
        # The comma form accepts profile names and rule IDs in any
        # combination — useful for `make lint-vista` (xindex + vista).
        rules = select_rules("xindex,vista")
        ids = {r.id for r in rules}
        # Should be the full union of the two profiles' selections.
        xindex_ids = {r.id for r in resolve_profile("xindex")}
        vista_ids = {r.id for r in resolve_profile("vista")}
        assert ids == xindex_ids | vista_ids
        # No duplicates — selecting twice doesn't double-count.
        assert len(rules) == len(ids)

    def test_profile_plus_rule_id(self):
        rules = select_rules("vista,M-XINDX-013")
        ids = {r.id for r in rules}
        assert ids == {r.id for r in resolve_profile("vista")} | {"M-XINDX-013"}

    def test_unknown_token_in_comma_list_lists_profiles(self):
        with pytest.raises(ValueError) as exc:
            select_rules("xindex,nonsense")
        msg = str(exc.value)
        assert "nonsense" in msg
        assert "known profiles" in msg


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCliFallback:
    def test_resolves_to_default_profile_when_unset(self):
        ns = argparse.Namespace(rules=None)
        cfg = Config.empty()
        assert _resolve_lint_rules(ns, cfg) == DEFAULT_PROFILE

    def test_cli_flag_wins_over_config(self):
        ns = argparse.Namespace(rules="xindex")
        cfg = Config(lint_rules="all")
        assert _resolve_lint_rules(ns, cfg) == "xindex"

    def test_config_used_when_flag_absent(self):
        ns = argparse.Namespace(rules=None)
        cfg = Config(lint_rules="xindex")
        assert _resolve_lint_rules(ns, cfg) == "xindex"


class TestThresholdResolution:
    """`_resolve_thresholds` merges config-file thresholds with
    `--threshold KEY=VAL` CLI overrides; CLI wins."""

    def test_no_args_no_config_returns_empty(self):
        from m_cli.lint.cli import _resolve_thresholds

        ns = argparse.Namespace(threshold=None)
        cfg = Config.empty()
        assert _resolve_thresholds(ns, cfg) == {}

    def test_config_thresholds_pass_through(self):
        from m_cli.lint.cli import _resolve_thresholds

        ns = argparse.Namespace(threshold=None)
        cfg = Config(lint_thresholds={"line_length": 120})
        assert _resolve_thresholds(ns, cfg) == {"line_length": 120}

    def test_cli_override_wins_over_config(self):
        from m_cli.lint.cli import _resolve_thresholds

        ns = argparse.Namespace(threshold=["line_length=80"])
        cfg = Config(lint_thresholds={"line_length": 120, "routine_lines": 500})
        # CLI overrides line_length but config keeps routine_lines.
        out = _resolve_thresholds(ns, cfg)
        assert out == {"line_length": 80, "routine_lines": 500}

    def test_cli_multiple_overrides(self):
        from m_cli.lint.cli import _resolve_thresholds

        ns = argparse.Namespace(
            threshold=["line_length=80", "routine_lines=2000"]
        )
        cfg = Config.empty()
        assert _resolve_thresholds(ns, cfg) == {
            "line_length": 80,
            "routine_lines": 2000,
        }

    def test_cli_malformed_spec_raises(self):
        from m_cli.lint.cli import _resolve_thresholds

        ns = argparse.Namespace(threshold=["line_length"])  # no =
        cfg = Config.empty()
        with pytest.raises(ValueError, match="KEY=VAL"):
            _resolve_thresholds(ns, cfg)

    def test_cli_non_int_value_raises(self):
        from m_cli.lint.cli import _resolve_thresholds

        ns = argparse.Namespace(threshold=["line_length=oops"])
        cfg = Config.empty()
        with pytest.raises(ValueError, match="integer"):
            _resolve_thresholds(ns, cfg)


class TestTargetEngineResolution:
    def test_default_is_any(self):
        ns = argparse.Namespace(target_engine=None)
        assert _resolve_target_engine(ns, Config.empty()) == "any"

    def test_cli_flag_wins(self):
        ns = argparse.Namespace(target_engine="iris")
        cfg = Config(lint_target_engine="yottadb")
        assert _resolve_target_engine(ns, cfg) == "iris"

    def test_config_used_when_flag_absent(self):
        ns = argparse.Namespace(target_engine=None)
        cfg = Config(lint_target_engine="yottadb")
        assert _resolve_target_engine(ns, cfg) == "yottadb"


class TestListProfiles:
    def test_list_profiles_output_includes_each_profile(self, capsys):
        rc = _print_profiles()
        assert rc == 0
        out = capsys.readouterr().out
        for name in ("default", "xindex", "sac", "modern", "all"):
            assert name in out
        # Lists rule counts so users can see what each profile resolves to.
        assert "rule(s)" in out
