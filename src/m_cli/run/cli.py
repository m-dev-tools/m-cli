"""`m run` command — execute an M entryref via the active engine.

Routes through :func:`m_cli.engine.detect_engine` so the same command
works against any transport: docker (canonical default), SSH (legacy
vista-meta fallback), or local YottaDB. Mirrors the transport-detection
pattern used by `m doctor`'s ``_transport_intent`` and the engine
methods consumed by every other runtime tool.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Callable

from m_cli._exit import DOMAIN_FAILURE
from m_cli.engine import EngineNotConfigured, detect_engine
from m_cli.run.runner import EntryrefError, parse_entryref

# Type alias for an injectable subprocess runner used in unit tests.
RunnerFn = Callable[[list[str]], int]


def _default_runner(cmd: list[str]) -> int:
    """Run the command with stdout/stderr inherited; return rc."""
    proc = subprocess.run(cmd, check=False)
    return proc.returncode


def run_command(args: argparse.Namespace, *, runner: RunnerFn | None = None) -> int:
    runner_fn: RunnerFn = runner or _default_runner
    try:
        label, routine = parse_entryref(args.entryref)
    except EntryrefError as exc:
        print(f"m run: {exc}", file=sys.stderr)
        return 2

    try:
        engine = detect_engine()
    except EngineNotConfigured as exc:
        print(f"m run: {exc}", file=sys.stderr)
        return DOMAIN_FAILURE

    base_stage = engine.stage_routines(Path.cwd())
    extra_routines = list(getattr(args, "routines", None) or [])
    stage = (
        " ".join([*extra_routines, base_stage]) if extra_routines else base_stage
    )

    entryref = f"{label}^{routine}" if label else f"^{routine}"
    extra_args = list(getattr(args, "args", None) or [])
    cmd = engine.build_run_cmd(entryref, extra_args, stage)

    if not getattr(args, "quiet", False):
        transport = type(engine).__name__
        print(f"m run: {transport} → {entryref}", file=sys.stderr)

    return runner_fn(cmd)
