"""CLI-UX conventions contract gate.

Pins the rules from
[`cli-ux-conventions-guide.md`](https://github.com/m-dev-tools/.github/blob/main/docs/dev-practices/cli-ux-conventions-guide.md)
against the installed `m` binary. Sliced per remediation PR per
`docs/plans/cli-ux-conventions-remediation.md` §5.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# Installed m binary (matches `.venv/bin/m` convention from CLAUDE.md).
M = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "m"


def run(*argv: str, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(M), *argv], capture_output=True, text=True, cwd=cwd
    )


# ────────────────────────────────────────────────────────────────────────
# PR 1 — dispatcher overview + concise synopsis + drop required=True
# ────────────────────────────────────────────────────────────────────────


class TestBareDispatcher:
    """§3.1 — bare dispatcher prints overview to stdout, exit 0."""

    def test_root_bare_exits_0(self) -> None:
        r = run()
        assert r.returncode == 0, r.stderr

    def test_root_bare_writes_to_stdout(self) -> None:
        r = run()
        assert r.stdout, "expected stdout overview"
        assert r.stderr == "", f"unexpected stderr: {r.stderr!r}"

    def test_root_bare_includes_usage_line(self) -> None:
        r = run()
        assert "USAGE" in r.stdout
        assert "m <command>" in r.stdout

    def test_root_bare_lists_commands_with_indent(self) -> None:
        """gh-style indented COMMANDS block — auto-sourced from registered
        subparsers, so this stays accurate as commands are added/removed."""
        r = run()
        assert "COMMANDS" in r.stdout
        # Spot-check a few well-known subcommands appear, indented.
        for name in ("fmt", "lint", "test", "doctor", "capabilities"):
            # Two-space indent + name + colon
            assert f"  {name}:" in r.stdout, f"missing indented entry for {name!r}"

    def test_root_bare_description_is_two_lines(self) -> None:
        """Two-line description (per user request), not a stale enumeration."""
        r = run()
        head = r.stdout.split("\nUSAGE", 1)[0].rstrip("\n")
        # Two non-empty lines before USAGE.
        non_empty = [line for line in head.splitlines() if line.strip()]
        assert len(non_empty) == 2, f"want 2 description lines, got {non_empty!r}"

    def test_root_bare_no_stale_subcommand_enumeration(self) -> None:
        """The old `--help` description listed 6 of 18 subcommands inline.
        Make sure bare overview doesn't reintroduce that pattern."""
        r = run()
        head = r.stdout.split("\nUSAGE", 1)[0]
        assert "fmt (format)" not in head
        assert "Subcommands: fmt" not in head

    def test_ci_bare_exits_0_with_overview(self) -> None:
        r = run("ci")
        assert r.returncode == 0, r.stderr
        assert "USAGE" in r.stdout
        assert "m ci <action>" in r.stdout or "m ci <command>" in r.stdout
        assert r.stderr == ""


class TestHelpOutput:
    """§3.3 — `--help` / `-h` to stdout, exit 0, concise synopsis."""

    @pytest.mark.parametrize(
        "argv",
        [
            ["--help"],
            ["-h"],
            ["fmt", "--help"],
            ["ci", "--help"],
            ["ci", "init", "--help"],
        ],
    )
    def test_help_to_stdout_exit_0(self, argv: list[str]) -> None:
        r = run(*argv)
        assert r.returncode == 0, (argv, r.stderr)
        assert r.stdout, argv
        assert r.stderr == "", (argv, r.stderr)

    def test_help_synopsis_is_one_line(self) -> None:
        """`metavar="<command>"` collapses the wrapping {fmt,lint,…} set."""
        r = run("--help")
        first = r.stdout.splitlines()[0]
        assert first.startswith("usage: m"), first
        assert "{fmt" not in first, first
        assert "<command>" in first, first

    def test_help_description_does_not_enumerate_subcommands(self) -> None:
        """Description sentence used to name 6 of 18 subcommands inline —
        that enumeration kept going stale. The positional-args block is
        the canonical listing."""
        r = run("--help")
        # The stale phrasing.
        assert "Subcommands: fmt" not in r.stdout
        assert "fmt (format)" not in r.stdout
        # But the positional-args block still names every subcommand.
        assert "fmt" in r.stdout and "lint" in r.stdout
        assert "capabilities" in r.stdout


# ────────────────────────────────────────────────────────────────────────
# PR 2 — `m ci init` requires `--write`; bare = preview
# ────────────────────────────────────────────────────────────────────────


class TestCiInitPreviewVsWrite:
    """Anti-pattern #4 / guide §3.2 — bare leaf must not mutate state."""

    def test_ci_init_bare_does_not_write(self, tmp_path: Path) -> None:
        r = run("ci", "init", "--path", str(tmp_path))
        assert r.returncode == 0, r.stderr
        assert not (tmp_path / ".github" / "workflows" / "m-ci.yml").exists()

    def test_ci_init_bare_preview_shows_yaml_on_stdout(self, tmp_path: Path) -> None:
        r = run("ci", "init", "--path", str(tmp_path))
        assert r.returncode == 0
        # Preview includes the would-be path and at least one workflow gate.
        assert "m-ci.yml" in r.stdout
        assert "m fmt --check" in r.stdout

    def test_ci_init_bare_preview_tells_user_how_to_opt_in(
        self, tmp_path: Path
    ) -> None:
        r = run("ci", "init", "--path", str(tmp_path))
        assert "--write" in r.stdout

    def test_ci_init_write_creates_file(self, tmp_path: Path) -> None:
        r = run("ci", "init", "--write", "--path", str(tmp_path))
        assert r.returncode == 0, r.stderr
        assert (tmp_path / ".github" / "workflows" / "m-ci.yml").is_file()


# ────────────────────────────────────────────────────────────────────────
# §3.5 — `--version` to stdout, exit 0 (already compliant; pinned)
# ────────────────────────────────────────────────────────────────────────


def test_version_to_stdout_exit_0() -> None:
    r = run("--version")
    assert r.returncode == 0
    assert r.stdout.startswith("m-cli ")
    assert r.stderr == ""


# ────────────────────────────────────────────────────────────────────────
# §3.4 — unknown subcommand at root: exit 2, stderr, names valid choices
# (already compliant; pinned)
# ────────────────────────────────────────────────────────────────────────


def test_unknown_subcommand_exits_2_named() -> None:
    r = run("__bogus__")
    assert r.returncode == 2
    assert "__bogus__" in r.stderr
    assert "usage: m" in r.stderr.lower()


# ────────────────────────────────────────────────────────────────────────
# PR 3 — unknown flag at a leaf shows that leaf's usage (not root)
# ────────────────────────────────────────────────────────────────────────


class TestUnknownFlagRoutesToSubparser:
    """§3.4 — unknown flag → the *node's* error/usage, not root's.

    Before PR 3, 13 of 18 leaves printed root usage when given a bogus
    flag — argparse's default behavior bubbles unknown args to the top.
    Two-pass parsing routes them to the resolved subparser instead.
    """

    @pytest.mark.parametrize(
        "leaf",
        [
            "fmt",
            "lint",
            "test",
            "watch",
            "coverage",
            "lsp",
            "doctor",
            "build",
            "doc",
            "search",
            "manifest",
            "examples",
            "errors",
            "plugins",
            "capabilities",
        ],
    )
    def test_leaf_unknown_flag_shows_leaf_usage(self, leaf: str) -> None:
        r = run(leaf, "--__bogus__")
        assert r.returncode == 2, (leaf, r.stdout, r.stderr)
        # Lowercase compare keeps this robust to "Usage:" vs "usage:".
        stderr_lc = r.stderr.lower()
        assert f"usage: m {leaf}" in stderr_lc, (leaf, r.stderr)
        # And NOT the root synopsis (regression guard for the old bug).
        assert "usage: m [-h]" not in stderr_lc, (leaf, r.stderr)

    def test_root_unknown_flag_still_shows_root_usage(self) -> None:
        r = run("--__bogus__")
        assert r.returncode == 2, r.stderr
        assert "usage: m" in r.stderr.lower()

    def test_nested_ci_init_unknown_flag_shows_init_usage(self) -> None:
        r = run("ci", "init", "--__bogus__")
        assert r.returncode == 2, r.stderr
        assert "usage: m ci init" in r.stderr.lower(), r.stderr
