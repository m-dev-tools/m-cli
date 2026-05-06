"""`m run` command — thin wrapper around ``ydb -run``."""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Callable

from m_cli.run.runner import (
    EntryrefError,
    build_command,
    build_env,
    parse_entryref,
    resolve_ydb_binary,
)

# Type alias for an injectable subprocess runner used in unit tests.
RunnerFn = Callable[[list[str], dict[str, str]], int]


def _default_runner(cmd: list[str], env: dict[str, str]) -> int:
    """Run the command with stdout/stderr inherited; return rc."""
    proc = subprocess.run(cmd, env=env, check=False)
    return proc.returncode


def run_command(args: argparse.Namespace, *, runner: RunnerFn | None = None) -> int:
    runner_fn: RunnerFn = runner or _default_runner
    try:
        label, routine = parse_entryref(args.entryref)
    except EntryrefError as exc:
        print(f"m run: {exc}", file=sys.stderr)
        return 2

    binary = resolve_ydb_binary()
    if binary is None:
        print(
            "m run: no `ydb` binary found. Set $YDB, $ydb_dist, or "
            "ensure `ydb` is on PATH.",
            file=sys.stderr,
        )
        return 2

    env = build_env(routines=getattr(args, "routines", None))
    extra = list(getattr(args, "args", None) or [])
    cmd = build_command(binary, label, routine, extra)

    if not getattr(args, "quiet", False):
        entry = f"{label}^{routine}" if label else f"^{routine}"
        print(f"m run: {binary} -run {entry}", file=sys.stderr)

    return runner_fn(cmd, env)
