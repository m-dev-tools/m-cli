"""Tests for `m capabilities --json`.

`m capabilities` introspects the `m` argparse dispatcher and emits a
machine-readable view of every subcommand. It is the source of truth
for `dist/commands.json`, which the tier-1 `repo.meta.json` exposes as
`commands`.

Source of truth = the argparse subparser tree itself. There is no
hand-curated catalog: any subcommand registered in `src/m_cli/cli.py`
(or contributed by a plugin) appears automatically.

Per .github/docs/phase0-plan.md § D3.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import pytest

from m_cli import __version__
from m_cli.capabilities import build_capabilities, capabilities_command
from m_cli.cli import main

# ----------------------------------------------------------------- shape


def test_build_capabilities_returns_dict_with_version_and_subcommands():
    caps = build_capabilities()
    assert isinstance(caps, dict)
    assert caps.get("version") == __version__
    assert "subcommands" in caps
    assert isinstance(caps["subcommands"], dict)
    assert caps["subcommands"], "subcommands map must be non-empty"


def test_capabilities_includes_core_subcommands():
    caps = build_capabilities()
    names = set(caps["subcommands"].keys())
    # Core inner-loop tools — every release must surface them.
    for required in ("fmt", "lint", "test", "coverage", "lsp"):
        assert required in names, f"{required!r} missing from capabilities; got {sorted(names)}"


def test_each_subcommand_has_purpose_options_examples():
    caps = build_capabilities()
    for name, entry in caps["subcommands"].items():
        assert isinstance(entry, dict), f"{name}: entry must be a dict"
        # purpose: short human-readable line (argparse `help` / `description`)
        assert isinstance(entry.get("purpose"), str) and entry["purpose"], (
            f"{name}: purpose must be a non-empty string"
        )
        # options: list of {name, help, default, choices?}
        assert isinstance(entry.get("options"), list), f"{name}: options must be a list"
        for opt in entry["options"]:
            assert isinstance(opt, dict), f"{name}: option entry must be a dict"
            assert isinstance(opt.get("name"), str) and opt["name"], (
                f"{name}: option must have a non-empty name"
            )
            # `help` may be None (argparse SUPPRESS) but key must exist
            assert "help" in opt, f"{name}: option {opt['name']} missing 'help' key"
        # examples: list (possibly empty) of strings
        assert isinstance(entry.get("examples"), list), f"{name}: examples must be a list"
        for ex in entry["examples"]:
            assert isinstance(ex, str) and ex, f"{name}: example must be a non-empty string"


def test_fmt_options_include_rules_and_check():
    caps = build_capabilities()
    fmt = caps["subcommands"]["fmt"]
    opt_names = {o["name"] for o in fmt["options"]}
    assert "--rules" in opt_names
    assert "--check" in opt_names


def test_lint_options_include_format_and_error_on():
    caps = build_capabilities()
    lint = caps["subcommands"]["lint"]
    opt_names = {o["name"] for o in lint["options"]}
    assert "--format" in opt_names
    assert "--error-on" in opt_names


def test_choices_surface_on_options_that_have_them():
    caps = build_capabilities()
    lint_opts = {o["name"]: o for o in caps["subcommands"]["lint"]["options"]}
    fmt_opt = lint_opts.get("--format")
    assert fmt_opt is not None
    # --format choices on `m lint` are ('text', 'json', 'tap')
    assert "choices" in fmt_opt
    assert set(fmt_opt["choices"] or ()) == {"text", "json", "tap"}


# ----------------------------------------------------------------- CLI surface


def test_capabilities_command_emits_json_to_stdout():
    """The argparse handler writes JSON to stdout and returns 0."""
    import argparse

    args = argparse.Namespace(json=True)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = capabilities_command(args)
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload == build_capabilities()


def test_m_capabilities_json_dispatcher_exit_zero(capsys):
    """End-to-end: `m capabilities --json` via the dispatcher exits 0
    and writes a single valid JSON document to stdout."""
    rc = main(["capabilities", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["version"] == __version__
    assert "subcommands" in payload
    assert "fmt" in payload["subcommands"]


def test_m_capabilities_default_format_is_json():
    """Phase 0 contract: `m capabilities` is JSON-only. Plain
    `m capabilities` (no flag) still emits JSON — `--json` is accepted
    for explicitness but is the only output format today."""
    rc_default = main(["capabilities"])
    assert rc_default == 0


# ----------------------------------------------------------------- determinism


def test_build_capabilities_is_deterministic():
    """Two back-to-back calls return equal payloads — no timestamps,
    no env-dependent data. The dist/commands.json drift gate depends
    on this."""
    a = build_capabilities()
    b = build_capabilities()
    assert a == b


def test_subcommands_sorted_alphabetically():
    """Stable key order so `git diff dist/commands.json` is meaningful."""
    caps = build_capabilities()
    names = list(caps["subcommands"].keys())
    assert names == sorted(names), f"subcommand keys must be sorted; got {names}"


# ----------------------------------------------------------------- excludes


def test_plugin_dispatcher_args_are_excluded():
    """The dispatcher stashes `_plugin_registered` / `_plugin_conflicts`
    on the parser via `parser.set_defaults(...)`. Those are internal
    state, not user-facing options — they must not appear in the
    capabilities output."""
    caps = build_capabilities()
    for entry in caps["subcommands"].values():
        for opt in entry["options"]:
            assert not opt["name"].startswith("_plugin_"), (
                f"internal arg leaked into capabilities: {opt['name']}"
            )


@pytest.mark.parametrize("name", ["fmt", "lint", "test", "coverage", "lsp", "doctor", "new"])
def test_required_subcommand_purpose_is_helpful(name):
    """Every core subcommand has a non-trivial `purpose` (>= 10 chars)."""
    caps = build_capabilities()
    purpose = caps["subcommands"][name]["purpose"]
    assert len(purpose) >= 10, f"{name}: purpose too terse: {purpose!r}"
