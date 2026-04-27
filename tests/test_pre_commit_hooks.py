"""Schema and integrity tests for ``.pre-commit-hooks.yaml``.

This is the file downstream M projects reference when they wire m-cli
into their ``.pre-commit-config.yaml``. Catches drift between the
declared hooks and the actual ``m`` CLI surface.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_FILE = REPO_ROOT / ".pre-commit-hooks.yaml"

REQUIRED_HOOK_FIELDS = {"id", "name", "description", "entry", "language", "files"}
EXPECTED_LANGUAGE = "python"
M_FILE_PATTERN = re.compile(r".*\.m$")


@pytest.fixture(scope="module")
def hooks() -> list[dict]:
    if not HOOKS_FILE.exists():
        pytest.fail(f"{HOOKS_FILE} is missing — pre-commit scaffold not present")
    with HOOKS_FILE.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, list), ".pre-commit-hooks.yaml must be a list of hooks"
    return data


def test_at_least_two_hooks_declared(hooks: list[dict]) -> None:
    """We expect a fmt-check hook and a lint hook at minimum."""
    ids = {h["id"] for h in hooks}
    assert "m-fmt-check" in ids
    assert "m-lint" in ids


def test_every_hook_has_required_fields(hooks: list[dict]) -> None:
    for hook in hooks:
        missing = REQUIRED_HOOK_FIELDS - hook.keys()
        assert not missing, f"hook {hook.get('id', '?')} missing fields: {missing}"


def test_hook_ids_are_unique(hooks: list[dict]) -> None:
    ids = [h["id"] for h in hooks]
    assert len(ids) == len(set(ids)), f"duplicate hook ids: {ids}"


def test_language_is_python(hooks: list[dict]) -> None:
    for hook in hooks:
        assert hook["language"] == EXPECTED_LANGUAGE, (
            f"hook {hook['id']} uses language={hook['language']!r}; "
            f"expected {EXPECTED_LANGUAGE!r} so pre-commit installs m-cli"
        )


def test_files_regex_matches_m_files(hooks: list[dict]) -> None:
    sample_paths = ["foo.m", "Routines/HELLO.m", "deeply/nested/X.m"]
    non_m_paths = ["foo.py", "README.md", "Makefile"]
    for hook in hooks:
        pattern = re.compile(hook["files"])
        for p in sample_paths:
            assert pattern.search(p), (
                f"hook {hook['id']!r} files regex {hook['files']!r} "
                f"does not match {p!r}"
            )
        for p in non_m_paths:
            assert not pattern.search(p), (
                f"hook {hook['id']!r} files regex {hook['files']!r} "
                f"unexpectedly matches non-M file {p!r}"
            )


def test_entries_invoke_known_m_subcommands(hooks: list[dict]) -> None:
    """Each hook ``entry`` must start with ``m <subcommand>`` for one of
    the subcommands actually exposed by the dispatcher."""
    from m_cli.cli import main as _main  # noqa: F401  -- ensures importable

    # Mirror of `m` subcommands. Update when the dispatcher gains a new one.
    valid_subcommands = {"fmt", "lint", "test", "watch"}

    for hook in hooks:
        argv = shlex.split(hook["entry"])
        assert argv, f"hook {hook['id']!r} has empty entry"
        assert argv[0] == "m", (
            f"hook {hook['id']!r} entry must start with 'm', got {argv[0]!r}"
        )
        assert len(argv) >= 2, f"hook {hook['id']!r} entry needs a subcommand"
        assert argv[1] in valid_subcommands, (
            f"hook {hook['id']!r} uses unknown subcommand {argv[1]!r}; "
            f"expected one of {sorted(valid_subcommands)}"
        )


def test_lint_hook_uses_fatal_threshold(hooks: list[dict]) -> None:
    """The lint hook must use ``--error-on=fatal`` so it only blocks
    commits on real bugs (not stylistic warnings)."""
    lint = next(h for h in hooks if h["id"] == "m-lint")
    entry = lint["entry"]
    assert "--error-on=fatal" in entry or "--error-on fatal" in entry, (
        f"m-lint hook entry must use --error-on=fatal, got {entry!r}"
    )


def test_fmt_check_hook_uses_check_mode(hooks: list[dict]) -> None:
    fmt = next(h for h in hooks if h["id"] == "m-fmt-check")
    assert "--check" in fmt["entry"], (
        f"m-fmt-check entry must use --check, got {fmt['entry']!r}"
    )


def test_descriptions_are_not_empty(hooks: list[dict]) -> None:
    for hook in hooks:
        assert hook["description"].strip(), (
            f"hook {hook['id']!r} has an empty description"
        )
