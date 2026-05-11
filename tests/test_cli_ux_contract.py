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


# ────────────────────────────────────────────────────────────────────────
# PR 4 — domain failures exit 1, not 2
# ────────────────────────────────────────────────────────────────────────


class TestDomainFailuresExit1:
    """§3.7 — exit 2 is reserved for *usage* errors; missing manifests
    and missing binaries are *domain* failures → exit 1."""

    @pytest.mark.parametrize(
        "cmd",
        ["doc", "search", "manifest", "examples", "errors"],
    )
    def test_missing_manifest_exits_1(self, cmd: str, tmp_path: Path) -> None:
        # Run from a clean tmp dir with HOME stubbed so find_manifest()
        # walks up and finds nothing. Search needs a positional query;
        # the others tolerate missing positionals.
        env_extra = {"HOME": str(tmp_path)}
        argv = [cmd]
        if cmd == "search":
            argv.append("nopatternmatchesthis")
        elif cmd == "doc":
            argv.append("STDJSON")
        import os

        env = {**os.environ, **env_extra}
        env.pop("M_CLI_MANIFEST", None)
        r = subprocess.run(
            [str(M), *argv],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env=env,
        )
        assert r.returncode == 1, (cmd, r.stdout, r.stderr)
        assert "manifest" in r.stderr.lower(), (cmd, r.stderr)

    def test_missing_ydb_binary_exits_1(self, tmp_path: Path) -> None:
        import os

        env = {
            **os.environ,
            "PATH": str(tmp_path),  # no `ydb` here
        }
        env.pop("YDB", None)
        env.pop("ydb_dist", None)
        r = subprocess.run(
            [str(M), "build", str(tmp_path)],
            capture_output=True,
            text=True,
            env=env,
        )
        assert r.returncode == 1, (r.stdout, r.stderr)
        assert "ydb" in r.stderr.lower(), r.stderr


# ────────────────────────────────────────────────────────────────────────
# PR 5 — cwd default for fmt/lint/coverage; nothing-to-do exits 0 for
# test/watch (and the no-files-in-cwd fallback for fmt/lint/coverage)
# ────────────────────────────────────────────────────────────────────────


class TestCwdDefaultsAndNothingToDo:
    """§3.2 — leaves with a sensible default should run it; "nothing to
    do" is success, not failure."""

    @pytest.mark.parametrize("cmd", ["fmt", "lint", "coverage"])
    def test_bare_in_empty_dir_exits_0_with_message(
        self, cmd: str, tmp_path: Path
    ) -> None:
        """Bare invocation in a directory with no .m files: cwd is the
        default scope, finds nothing, exits 0 with a stdout message — no
        more confusing exit-2 'no .m files found' error."""
        r = run(cmd, cwd=str(tmp_path))
        assert r.returncode == 0, (cmd, r.stdout, r.stderr)
        # Message goes to stdout (it's a success), not stderr.
        assert r.stdout, (cmd, r.stdout, r.stderr)

    @pytest.mark.parametrize("cmd", ["fmt", "lint"])
    def test_bare_in_cwd_with_m_files_processes_them(
        self, cmd: str, tmp_path: Path
    ) -> None:
        """Cwd-default should actually find .m files in cwd."""
        (tmp_path / "FOO.m").write_text("FOO ; hello\n  QUIT\n")
        r = run(cmd, cwd=str(tmp_path))
        # Either 0 (success) or 1 (e.g. lint diagnostics) — but NOT 2
        # ("no .m files found" usage error).
        assert r.returncode in (0, 1), (cmd, r.stdout, r.stderr)

    @pytest.mark.parametrize("cmd", ["test", "watch"])
    def test_no_suites_discoverable_exits_0(
        self, cmd: str, tmp_path: Path
    ) -> None:
        """`m test` / `m watch` in an empty dir: nothing to test is not
        a failure — exit 0 with a stdout note."""
        extra: list[str] = ["--once"] if cmd == "watch" else []
        r = run(cmd, *extra, cwd=str(tmp_path))
        assert r.returncode == 0, (cmd, r.stdout, r.stderr)
        assert r.stdout, (cmd, r.stdout, r.stderr)
        assert "no" in r.stdout.lower() and "suite" in r.stdout.lower(), (
            cmd,
            r.stdout,
        )
