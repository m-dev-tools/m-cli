"""Profile registry for ``m lint``.

A *profile* is a named, opinionated rule selection. Profiles are kept
separate from the rule registry on purpose:

  - The lint engine stays vendor- and dialect-neutral. It registers
    rules and runs them; it does not bake in any opinion about which
    rules belong together or which set is the "default".

  - Communities can ship their own profiles. The VA VistA Toolkit's
    ``^XINDEX`` is one such community profile; ``sac`` (VA SAC) is
    another. Future profiles like ``iris-style`` or ``ansi-strict``
    can live alongside without privileging any single dialect.

  - End users get a curated default (``default``) without having to
    care which community profile happens to back it today.

Each :class:`Profile` carries a name, a human-readable description,
and a ``selector`` callable that returns the rules to include. Tag-
backed profiles use :func:`m_cli.lint.rules.rules_by_tag`; an
explicit-list profile would use a closure over a fixed id set.

Public surface
==============

  - :class:`Profile`
  - :func:`register_profile`, :func:`get_profile`, :func:`list_profiles`
  - :func:`resolve_profile` — name → list[Rule]
  - :data:`DEFAULT_PROFILE` — the profile name used when no
    ``--rules`` flag and no ``[lint] rules`` config is set.

Resolution of the broader ``--rules`` syntax (profile name, comma-
separated rule IDs, or ``all``) lives in
:func:`m_cli.lint.runner.select_rules`, which delegates here for the
profile-name case.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from m_cli.lint.rules import Rule, all_rules, rules_by_tag

DEFAULT_PROFILE = "default"

# Read-only empty mapping used as the dataclass default for
# ``Profile.default_thresholds``. Plain ``{}`` would be a mutable
# default that the frozen dataclass rejects; ``MappingProxyType({})``
# is hashable and immutable.
_EMPTY_THRESHOLDS: Mapping[str, int] = MappingProxyType({})


def _portable(tag: str) -> Callable[[], list[Rule]]:
    """Return a selector for rules tagged ``tag`` AND NOT tagged ``vista``.

    Used by the engine-neutral profiles (``default``, ``xindex``, ``sac``)
    to exclude VA-Kernel-specific rules — those rules are XINDEX/SAC
    mandates *for VistA*, but on YottaDB or IRIS they would emit pure
    false positives (the Kernel APIs they require don't exist outside
    VistA). Users who want VA-Kernel checks select ``--rules=vista``.
    """

    def selector() -> list[Rule]:
        return [r for r in rules_by_tag(tag) if "vista" not in r.tags]

    return selector


@dataclass(frozen=True)
class Profile:
    """A named, opinionated rule selection (and optional config preset).

    ``selector`` is called each time the profile is resolved, so it
    sees rules registered after the profile itself was registered.
    Profiles defined here therefore stay correct as new rules are
    added to the registry.

    ``default_thresholds`` lets a profile bundle configuration
    presets (line-length ceilings, complexity caps, etc.) alongside
    the rule selection. The :func:`m_cli.lint.cli._resolve_thresholds`
    helper layers them under user-supplied ``[lint.thresholds]``
    config and CLI ``--threshold KEY=VAL`` overrides — so a user
    selecting ``--rules=pythonic`` gets the profile's tighter
    defaults (e.g. ``commands_per_line=1``, ``line_length=100``)
    unless they explicitly override them. Empty by default; only
    profiles like ``pythonic`` use this slot.
    """

    name: str
    description: str
    selector: Callable[[], list[Rule]]
    default_thresholds: Mapping[str, int] = field(default_factory=lambda: _EMPTY_THRESHOLDS)


_PROFILES: dict[str, Profile] = {}


def register_profile(profile: Profile) -> Profile:
    if profile.name in _PROFILES:
        raise ValueError(f"duplicate profile: {profile.name}")
    _PROFILES[profile.name] = profile
    return profile


def get_profile(name: str) -> Profile | None:
    return _PROFILES.get(name)


def list_profiles() -> list[Profile]:
    return sorted(_PROFILES.values(), key=lambda p: p.name)


def resolve_profile(name: str) -> list[Rule]:
    """Return the rules selected by profile ``name``.

    Raises ``KeyError`` for an unknown profile name. Callers typically
    translate that to a user-facing ``ValueError`` with the list of
    known profiles.
    """
    profile = _PROFILES.get(name)
    if profile is None:
        raise KeyError(name)
    return profile.selector()


# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------
#
# `default` is m-cli's curated daily-lint set — the M-MOD-NN
# modernization track minus the four pedantic style rules
# (M-MOD-009, 028, 031, 032) that fire heavily on real-world M code
# without surfacing genuine bugs. The change from "default = engine-
# neutral xindex subset" to "default = curated modern" reflects the
# Phase-1..6 validation finding that the legacy XINDEX subset (with
# its mandates around lowercase variables and lowercase commands)
# generates ~62K findings on a non-VA modern corpus while M-MOD's
# curated subset stays under ~6K — the engine-neutral xindex profile
# was never the right baseline for non-VistA code.
#
# VA shops who want the legacy XINDEX checks select `--rules=xindex`
# (or `--rules=xindex,vista`); they're still first-class profiles.


def _modern_minus_pedantic() -> list[Rule]:
    """Selector: M-MOD rules that aren't tagged `pedantic`."""
    return [r for r in rules_by_tag("modern") if "pedantic" not in r.tags]


register_profile(
    Profile(
        name="default",
        description=(
            "m-cli's curated daily-lint set — the M-MOD-NN modernization "
            "track minus the four pedantic style rules that fire heavily "
            "on real M code (M-MOD-009 commands-per-line, M-MOD-028 "
            "label-docstring, M-MOD-031 magic-numbers, M-MOD-032 single-"
            "letter-vars). The full M-MOD set is opt-in via "
            "`--rules=modern`; the pedantic subset alone via "
            "`--rules=pedantic`. VA shops use `--rules=xindex` "
            "(engine-neutral XINDEX port) or `--rules=xindex,vista` for "
            "the full VistA-flavoured rule set."
        ),
        selector=_modern_minus_pedantic,
    )
)

register_profile(
    Profile(
        name="xindex",
        description=(
            "VA VistA Toolkit `^XINDEX` port, engine-neutral subset — the "
            "34 of XINDEX's ported rules that don't depend on VA Kernel "
            "APIs. (The 8 VA-Kernel-specific rules — `OPEN→ZIS`, "
            "`HALT→XUSCLEAN`, banner format, etc. — live in the `vista` "
            "profile.) Rule IDs `M-XINDX-NN` mirror XINDEX's error codes "
            "1:1. XINDEX is a VA tool; not part of the M standard, not "
            "shipped by IRIS or YottaDB."
        ),
        selector=_portable("xindex"),
    )
)

register_profile(
    Profile(
        name="vista",
        description=(
            "VA VistA-Kernel-specific rules. The 8 rules that mandate VA "
            "Kernel API substitutes (`CLOSE`→`^%ZISC`, `OPEN`→`^%ZIS`, "
            "`HALT`→`^XUSCLEAN`, `JOB`→TASKMAN, `$SYSTEM` Kernel-only) "
            "and VistA banner conventions (1st-line / 2nd-line SAC, patch "
            "number on second line). These rules emit pure false positives "
            "outside VistA — opt in only when linting VistA M code."
        ),
        selector=lambda: rules_by_tag("vista"),
    )
)

register_profile(
    Profile(
        name="sac",
        description=(
            "VA SAC (Standards & Conventions) portable subset — rules "
            "tagged `sac` AND NOT tagged `vista`. The full SAC document "
            "mandates the VistA-Kernel rules in the `vista` profile, but "
            "those mandates emit false positives outside VistA; this "
            "profile gives non-VA shops VA-style discipline (line length, "
            "uppercase, KILL/NEW restrictions) without VistA-only checks."
        ),
        selector=_portable("sac"),
    )
)

register_profile(
    Profile(
        name="modern",
        description=(
            "Full M-MOD-NN modernization track — every rule tagged "
            "`modern`, including the four pedantic style rules that "
            "`default` excludes. Use this for the strict review pass; "
            "expect ~50K findings on a 4K-routine non-VA corpus, mostly "
            "from M-MOD-031/032 (single-letter vars, magic numbers). "
            "Independent of the legacy XINDEX baseline, though some "
            "M-MOD rules supersede an XINDEX rule via the `replaces` "
            "metadata."
        ),
        selector=lambda: rules_by_tag("modern"),
    )
)

register_profile(
    Profile(
        name="pedantic",
        description=(
            "Just the four pedantic style rules that `default` excludes "
            "from M-MOD: M-MOD-009 (commands-per-line), M-MOD-028 (label "
            "without docstring), M-MOD-031 (magic numbers), M-MOD-032 "
            "(single-letter vars). Useful when reviewing for style "
            "compliance specifically, or when running a focused style "
            "pass on a project that has opted into strict M conventions."
        ),
        selector=lambda: rules_by_tag("pedantic"),
    )
)

# `pythonic` — preset for developers coming to M from Python. Same
# rule selection as `modern` (all M-MOD including pedantic style
# rules — Python convention favors descriptive names, no magic
# numbers, one statement per line) plus tighter thresholds matching
# Python community norms (PEP-8-ish line length, McCabe ~10).
register_profile(
    Profile(
        name="pythonic",
        description=(
            "Python-style preset for developers coming to M from Python. "
            "Same rule selection as `modern` (30 rules — all M-MOD, "
            "including the four `pedantic` style rules: a Python-trained "
            "eye wants long descriptive names, no magic numbers, one "
            "statement per line, label docstrings). Bundles tighter "
            "thresholds: line_length=100 (PEP-8-ish), commands_per_line=1, "
            "argument_count=5, cyclomatic=10, cognitive=15, "
            "dot_block_depth=3, label_lines=30. Override any threshold "
            "via `[lint.thresholds]` in .m-cli.toml or `--threshold` on "
            "the CLI."
        ),
        selector=lambda: rules_by_tag("modern"),
        default_thresholds=MappingProxyType(
            {
                "line_length": 100,
                "commands_per_line": 1,
                "argument_count": 5,
                "cyclomatic": 10,
                "cognitive": 15,
                "dot_block_depth": 3,
                "label_lines": 30,
            }
        ),
    )
)

# `vista-full` — the canonical comprehensive lint pass for VistA.
# Combines XINDEX (engine-neutral VA legacy port), `vista` (VA Kernel
# banner + API-substitute mandates), and `sac` (VA SAC portable
# subset). About 50 unique rules. Recommended invocation:
#
#   m lint --rules=vista-full --target-engine=yottadb \
#          --error-on=error \
#          Packages/<Pkg>/Routines/
#
# pairs naturally with `[lint.vista] kernel_locals = "default"` and
# `[lint.vista] trusted_routines = "default"` in `.m-cli.toml` to
# turn off the M-MOD-024 / M-XINDX-007 false positives the VistA
# corpus pass surfaced (see m-stdlib/docs/vista-corpus-lint-results.md).
def _vista_full() -> list[Rule]:
    seen: set[str] = set()
    out: list[Rule] = []
    for tag in ("xindex", "vista", "sac"):
        for r in rules_by_tag(tag):
            if r.id not in seen:
                seen.add(r.id)
                out.append(r)
    return out


register_profile(
    Profile(
        name="vista-full",
        description=(
            "Canonical VistA-comprehensive lint pass: XINDEX (engine-"
            "neutral VA port) + vista (VA Kernel banner-format + API-"
            "substitute mandates) + sac (VA SAC portable subset). About "
            "50 unique rules. Recommended with --target-engine=yottadb "
            "and `[lint.vista] kernel_locals = \"default\"` + "
            "`[lint.vista] trusted_routines = \"default\"` in .m-cli.toml "
            "to turn off the M-MOD-024 / M-XINDX-007 false positives the "
            "VistA corpus pass surfaced. Loosened thresholds for VistA "
            "legacy: line_length=132, label_lines=50, argument_count=8."
        ),
        selector=_vista_full,
        default_thresholds=MappingProxyType(
            {
                # Legacy VistA terminal width (80-col is too tight)
                "line_length": 132,
                # Kernel-pattern labels run long
                "label_lines": 50,
                # Kernel APIs take many args
                "argument_count": 8,
            }
        ),
    )
)


register_profile(
    Profile(
        name="all",
        description="Every registered rule, regardless of tag or profile.",
        selector=all_rules,
    )
)


__all__ = [
    "DEFAULT_PROFILE",
    "Profile",
    "get_profile",
    "list_profiles",
    "register_profile",
    "resolve_profile",
]
